"""
Async tasks for CRM bulk operations and background processing
"""

from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from .models import Lead, BulkOperation, BulkOperationProgress
from core.cache import CacheManager, QueryResultCache
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def bulk_lead_assignment_async(self, operation_id, lead_ids, assigned_user_id, batch_size=1000):
    """
    Async bulk lead assignment with progress tracking
    """
    try:
        operation = BulkOperation.objects.get(id=operation_id)
        operation.status = 'running'
        operation.save()
        
        assigned_user = User.objects.get(id=assigned_user_id)
        total_leads = len(lead_ids)
        processed = 0
        errors = []
        
        # Process in batches
        for i in range(0, total_leads, batch_size):
            batch_ids = lead_ids[i:i + batch_size]
            batch_processed = 0
            batch_errors = []
            
            try:
                with transaction.atomic():
                    # Update leads in batch
                    updated_count = Lead.objects.filter(id_lead__in=batch_ids).update(
                        assigned_user_id=assigned_user_id,
                        updated_at=timezone.now()
                    )
                    
                    batch_processed = updated_count
                    
                    # Log activity for updated leads
                    leads = Lead.objects.filter(id_lead__in=batch_ids)
                    for lead in leads:
                        LeadActivity.objects.create(
                            lead=lead,
                            user=assigned_user,
                            action_type='assigned',
                            description=f'Assigned to {assigned_user.get_full_name() or assigned_user.username}',
                            old_value=None,
                            new_value=str(assigned_user.id)
                        )
                
            except Exception as e:
                logger.error(f"Batch assignment error: {str(e)}")
                batch_errors.append(str(e))
            
            # Update progress
            processed += batch_processed
            progress_percentage = (processed / total_leads) * 100
            
            # Update operation progress
            BulkOperationProgress.objects.create(
                operation=operation,
                batch_number=(i // batch_size) + 1,
                total_in_batch=len(batch_ids),
                processed_in_batch=batch_processed,
                errors_in_batch=len(batch_errors),
                error_sample=batch_errors[:5] if batch_errors else None
            )
            
            # Update main operation
            operation.total_processed = processed
            operation.progress_percentage = progress_percentage
            operation.estimated_completion = timezone.now() + timezone.timedelta(
                seconds=((total_leads - processed) / batch_size) * 2
            )
            
            if batch_errors:
                operation.errors += len(batch_errors)
                if not operation.error_sample:
                    operation.error_sample = batch_errors[:3]
            
            operation.save()
            
            # Update task progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': processed,
                    'total': total_leads,
                    'progress': progress_percentage,
                    'status': f'Processed {processed} of {total_leads} leads'
                }
            )
        
        # Mark operation as completed
        operation.status = 'completed'
        operation.completed_at = timezone.now()
        operation.save()
        
        # Invalidate relevant caches
        CacheManager.invalidate_user_cache(assigned_user_id, operation.company_id)
        QueryResultCache.invalidate_query_cache('lead_statistics', operation.company_id)
        
        return {
            'status': 'completed',
            'processed': processed,
            'total': total_leads,
            'errors': len(errors)
        }
        
    except Exception as e:
        logger.error(f"Bulk assignment task failed: {str(e)}")
        
        if 'operation' in locals():
            operation.status = 'failed'
            operation.error_message = str(e)
            operation.save()
        
        raise


@shared_task(bind=True)
def bulk_lead_deletion_async(self, operation_id, lead_ids, batch_size=1000):
    """
    Async bulk lead deletion with progress tracking
    """
    try:
        operation = BulkOperation.objects.get(id=operation_id)
        operation.status = 'running'
        operation.save()
        
        total_leads = len(lead_ids)
        processed = 0
        errors = []
        
        # Process in batches
        for i in range(0, total_leads, batch_size):
            batch_ids = lead_ids[i:i + batch_size]
            batch_processed = 0
            batch_errors = []
            
            try:
                with transaction.atomic():
                    # Soft delete leads in batch
                    updated_count = Lead.objects.filter(id_lead__in=batch_ids).update(
                        deleted=True,
                        updated_at=timezone.now()
                    )
                    
                    batch_processed = updated_count
                
            except Exception as e:
                logger.error(f"Batch deletion error: {str(e)}")
                batch_errors.append(str(e))
            
            # Update progress
            processed += batch_processed
            progress_percentage = (processed / total_leads) * 100
            
            # Update operation progress
            BulkOperationProgress.objects.create(
                operation=operation,
                batch_number=(i // batch_size) + 1,
                total_in_batch=len(batch_ids),
                processed_in_batch=batch_processed,
                errors_in_batch=len(batch_errors),
                error_sample=batch_errors[:5] if batch_errors else None
            )
            
            # Update main operation
            operation.total_processed = processed
            operation.progress_percentage = progress_percentage
            operation.estimated_completion = timezone.now() + timezone.timedelta(
                seconds=((total_leads - processed) / batch_size) * 2
            )
            
            if batch_errors:
                operation.errors += len(batch_errors)
                if not operation.error_sample:
                    operation.error_sample = batch_errors[:3]
            
            operation.save()
            
            # Update task progress
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': processed,
                    'total': total_leads,
                    'progress': progress_percentage,
                    'status': f'Deleted {processed} of {total_leads} leads'
                }
            )
        
        # Mark operation as completed
        operation.status = 'completed'
        operation.completed_at = timezone.now()
        operation.save()
        
        # Invalidate relevant caches
        CacheManager.invalidate_company_cache(operation.company_id)
        QueryResultCache.invalidate_query_cache('lead_statistics', operation.company_id)
        
        return {
            'status': 'completed',
            'processed': processed,
            'total': total_leads,
            'errors': len(errors)
        }
        
    except Exception as e:
        logger.error(f"Bulk deletion task failed: {str(e)}")
        
        if 'operation' in locals():
            operation.status = 'failed'
            operation.error_message = str(e)
            operation.save()
        
        raise


@shared_task
def cleanup_old_cache():
    """
    Periodic task to clean up expired cache entries
    """
    try:
        # Clear expired cache entries
        cache_keys = cache.keys('*')
        expired_count = 0
        
        for key in cache_keys:
            try:
                # Check if cache entry exists and is expired
                value = cache.get(key)
                if value is None:
                    expired_count += 1
                    cache.delete(key)
            except:
                continue
        
        logger.info(f"Cleaned up {expired_count} expired cache entries")
        return {'cleaned_entries': expired_count}
        
    except Exception as e:
        logger.error(f"Cache cleanup failed: {str(e)}")
        raise


@shared_task
def update_dashboard_stats():
    """
    Periodic task to update dashboard statistics cache
    """
    try:
        from django.contrib.auth.models import User
        from core.queries import OptimizedLeadManager
        
        # Get all companies
        companies = User.objects.values_list('company_id', flat=True).distinct()
        
        updated_companies = 0
        for company_id in companies:
            try:
                # Invalidate and refresh dashboard stats for this company
                CacheManager.invalidate_company_cache(company_id)
                QueryResultCache.invalidate_query_cache('dashboard_main_stats', company_id)
                updated_companies += 1
                
            except Exception as e:
                logger.error(f"Failed to update stats for company {company_id}: {str(e)}")
                continue
        
        logger.info(f"Updated dashboard stats for {updated_companies} companies")
        return {'updated_companies': updated_companies}
        
    except Exception as e:
        logger.error(f"Dashboard stats update failed: {str(e)}")
        raise


@shared_task
def send_bulk_notifications(user_ids, notification_type, message_data):
    """
    Async bulk notification sending
    """
    try:
        from .models import Notification
        
        sent_count = 0
        errors = []
        
        for user_id in user_ids:
            try:
                Notification.objects.create(
                    user_id=user_id,
                    notification_type=notification_type,
                    message=message_data.get('message', ''),
                    data=message_data
                )
                sent_count += 1
                
            except Exception as e:
                errors.append(f"Failed to send to user {user_id}: {str(e)}")
        
        logger.info(f"Sent {sent_count} notifications, {len(errors)} errors")
        return {
            'sent': sent_count,
            'errors': len(errors),
            'error_details': errors
        }
        
    except Exception as e:
        logger.error(f"Bulk notification failed: {str(e)}")
        raise


@shared_task
def generate_report_async(report_type, user_id, filters, company_id):
    """
    Async report generation
    """
    try:
        from .reports import ReportGenerator
        
        generator = ReportGenerator()
        report_data = generator.generate_report(
            report_type=report_type,
            user_id=user_id,
            filters=filters,
            company_id=company_id
        )
        
        # Cache the report
        cache_key = f"report_{report_type}_{user_id}_{timezone.now().timestamp()}"
        cache.set(cache_key, report_data, timeout=3600)  # 1 hour
        
        logger.info(f"Generated {report_type} report for user {user_id}")
        return {
            'report_type': report_type,
            'cache_key': cache_key,
            'generated_at': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Report generation failed: {str(e)}")
        raise


@shared_task
def optimize_database_tables():
    """
    Periodic task to optimize database tables
    """
    try:
        from django.db import connection
        
        optimized_tables = []
        
        with connection.cursor() as cursor:
            # Get list of tables
            cursor.execute("SHOW TABLES")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Optimize each table
            for table in tables:
                try:
                    cursor.execute(f"OPTIMIZE TABLE `{table}`")
                    optimized_tables.append(table)
                except Exception as e:
                    logger.warning(f"Failed to optimize table {table}: {str(e)}")
        
        logger.info(f"Optimized {len(optimized_tables)} database tables")
        return {
            'optimized_tables': optimized_tables,
            'total_optimized': len(optimized_tables)
        }
        
    except Exception as e:
        logger.error(f"Database optimization failed: {str(e)}")
        raise
