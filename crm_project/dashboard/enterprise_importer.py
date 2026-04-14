"""
Enterprise-grade lead import orchestrator
Handles large-scale imports with background processing, progress tracking, and error handling
"""

import logging
import time
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
from django.core.cache import cache
from django.db import transaction, connection
from django.contrib.auth import get_user_model
from celery import shared_task
from .models import Lead, BulkOperation, BulkOperationProgress
from .streaming_parser import StreamingLeadParser, ImportProgressTracker
from .scalable_duplicate_detector import BulkDuplicateProcessor

logger = logging.getLogger(__name__)
User = get_user_model()


class EnterpriseLeadImporter:
    """
    Main orchestrator for enterprise-scale lead imports.
    Handles streaming processing, duplicate detection, and database operations.
    """
    
    def __init__(self, company_id: int, user_id: int, operation_id: int):
        self.company_id = company_id
        self.user_id = user_id
        self.operation_id = operation_id
        self.user = User.objects.get(id=user_id)
        
        # Initialize components
        self.duplicate_processor = BulkDuplicateProcessor(company_id, operation_id)
        self.progress_tracker = None
        
        # Configuration
        self.chunk_size = 2000  # Records per chunk
        self.batch_size = 1000  # Database batch size
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        
        # Statistics
        self.stats = {
            'total_rows': 0,
            'processed_rows': 0,
            'imported_leads': 0,
            'duplicate_leads': 0,
            'error_rows': 0,
            'start_time': None,
            'end_time': None,
            'processing_rate': 0.0
        }
    
    def import_leads_from_file(self, file_handler, file_name: str) -> Dict[str, Any]:
        """
        Main entry point for importing leads from a file.
        
        Args:
            file_handler: File object (Django UploadedFile)
            file_name: Original file name
            
        Returns:
            Import result statistics
        """
        self.stats['start_time'] = datetime.now()
        
        try:
            # Initialize streaming parser
            parser = StreamingLeadParser(file_handler, chunk_size=self.chunk_size)
            file_info = parser.get_file_info()
            
            # Estimate total rows for progress tracking
            estimated_rows = file_info.get('estimated_rows', 0)
            self.stats['total_rows'] = estimated_rows
            
            # Initialize progress tracking
            self.progress_tracker = ImportProgressTracker(
                session_id=str(self.operation_id),
                estimated_total=estimated_rows
            )
            self.progress_tracker.start()
            
            # Update operation status
            operation = BulkOperation.objects.get(id=self.operation_id)
            operation.status = 'running'
            operation.total_items = estimated_rows
            operation.save()
            
            # Process file in chunks
            logger.info(f"Starting enterprise import: {file_name}, estimated rows: {estimated_rows}")
            
            for chunk_num, chunk_data in enumerate(parser.parse_chunks()):
                try:
                    # Process chunk with duplicate detection
                    processed_chunk, chunk_stats = self._process_chunk(chunk_data, chunk_num + 1)
                    
                    # Update statistics
                    self._update_stats(chunk_stats)
                    
                    # Update progress
                    self._update_progress()
                    
                    # Log progress
                    if chunk_num % 10 == 0:  # Log every 10 chunks
                        logger.info(f"Processed chunk {chunk_num + 1}, "
                                  f"progress: {self.stats['processed_rows']}/{self.stats['total_rows']}")
                
                except Exception as e:
                    logger.error(f"Error processing chunk {chunk_num + 1}: {e}")
                    self.stats['error_rows'] += len(chunk_data)
                    continue
            
            # Finalize import
            return self._finalize_import()
            
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            self._mark_operation_failed(str(e))
            raise
    
    def _process_chunk(self, chunk_data: List[Dict[str, Any]], chunk_num: int) -> tuple:
        """
        Process a single chunk of lead data.
        
        Returns:
            Tuple of (processed_leads, chunk_stats)
        """
        # Step 1: Duplicate detection
        processed_leads, duplicate_stats = self.duplicate_processor.process_lead_batch(chunk_data)
        
        # Step 2: Separate new leads from duplicates
        new_leads = []
        chunk_result = {
            'total': len(chunk_data),
            'new_leads': 0,
            'duplicate_leads': 0,
            'errors': 0
        }
        
        for lead_data in processed_leads:
            duplicate_info = lead_data.get('duplicate_info', {})
            
            if duplicate_info.get('status') == 'new':
                # Prepare lead for database insertion
                lead_obj = self._prepare_lead_object(lead_data)
                if lead_obj:
                    new_leads.append(lead_obj)
                    chunk_result['new_leads'] += 1
                else:
                    chunk_result['errors'] += 1
            else:
                # Handle duplicate (could update existing lead or create duplicate record)
                self._handle_duplicate_lead(lead_data, duplicate_info)
                chunk_result['duplicate_leads'] += 1
        
        # Step 3: Bulk insert new leads
        if new_leads:
            self._bulk_insert_leads(new_leads, chunk_num)
        
        return processed_leads, chunk_result
    
    def _prepare_lead_object(self, lead_data: Dict[str, Any]) -> Optional[Lead]:
        """
        Prepare a Lead object from lead data.
        
        Returns:
            Lead object or None if invalid
        """
        try:
            # Extract and validate required fields
            name = lead_data.get('name', '').strip()
            mobile = lead_data.get('mobile', '').strip()
            
            if not name or not mobile:
                logger.warning(f"Skipping invalid lead: missing name or mobile")
                return None
            
            # Create Lead object
            lead = Lead(
                name=name,
                mobile=mobile,
                email=lead_data.get('email', '').strip() or None,
                alt_mobile=lead_data.get('alt_mobile', '').strip() or None,
                whatsapp_no=lead_data.get('whatsapp_no', '').strip() or None,
                alt_email=lead_data.get('alt_email', '').strip() or None,
                address=lead_data.get('address', '').strip() or None,
                city=lead_data.get('city', '').strip() or None,
                state=lead_data.get('state', '').strip() or None,
                postalcode=lead_data.get('postalcode', '').strip() or None,
                country=lead_data.get('country', '').strip() or None,
                status=lead_data.get('status', 'lead'),
                status_description=lead_data.get('status_description', '').strip() or None,
                lead_source=lead_data.get('lead_source', '').strip() or None,
                lead_source_description=lead_data.get('lead_source_description', '').strip() or None,
                refered_by=lead_data.get('refered_by', '').strip() or None,
                campaign_id=lead_data.get('campaign_id', '').strip() or None,
                course_name=lead_data.get('course_name', '').strip() or None,
                course_amount=lead_data.get('course_amount', '').strip() or None,
                exp_revenue=lead_data.get('exp_revenue', '').strip() or None,
                description=lead_data.get('description', '').strip() or None,
                
                # System fields
                company_id=self.company_id,
                created_by=self.user,
                assigned_user=self.user,  # Default assignment to importing user
                modified_user=self.user,
                
                # Date fields
                exp_close_date=lead_data.get('exp_close_date'),
                followup_datetime=lead_data.get('followup_datetime'),
                birthdate=lead_data.get('birthdate'),
                
                # Metadata
                row_number=lead_data.get('row_number'),
                import_session_id=str(self.operation_id)
            )
            
            return lead
            
        except Exception as e:
            logger.error(f"Error preparing lead object: {e}")
            return None
    
    def _handle_duplicate_lead(self, lead_data: Dict[str, Any], duplicate_info: Dict[str, Any]):
        """
        Handle a duplicate lead (could update existing lead or log duplicate).
        """
        try:
            # For now, we'll just log the duplicate
            # In future, this could update existing leads or create duplicate records
            duplicates = duplicate_info.get('duplicates', [])
            if duplicates:
                for duplicate in duplicates:
                    logger.info(f"Duplicate found: {duplicate.get('id')} - {duplicate.get('match_type')}")
            
        except Exception as e:
            logger.error(f"Error handling duplicate lead: {e}")
    
    def _bulk_insert_leads(self, leads: List[Lead], chunk_num: int):
        """
        Bulk insert leads into the database with error handling.
        """
        if not leads:
            return
        
        try:
            # Use chunked transactions for better performance
            with transaction.atomic():
                # Insert in smaller batches to prevent memory issues
                for i in range(0, len(leads), self.batch_size):
                    batch = leads[i:i + self.batch_size]
                    
                    try:
                        Lead.objects.bulk_create(batch, batch_size=self.batch_size)
                        
                        # Create activity logs for the batch
                        self._create_activity_logs(batch)
                        
                    except Exception as e:
                        logger.error(f"Error inserting batch {chunk_num}-{i//self.batch_size}: {e}")
                        # Continue with next batch
                        continue
            
            logger.info(f"Successfully inserted {len(leads)} leads in chunk {chunk_num}")
            
        except Exception as e:
            logger.error(f"Error in bulk insert for chunk {chunk_num}: {e}")
            raise
    
    def _create_activity_logs(self, leads: List[Lead]):
        """
        Create activity logs for imported leads.
        """
        try:
            # Use LeadOperationLog for activity tracking instead of ActivityLog
            from .models import LeadOperationLog
            
            activities = []
            for lead in leads:
                activities.append(LeadOperationLog(
                    user=self.user,
                    company_id=self.company_id,
                    operation_type='lead_imported',
                    action_scope='bulk_import',
                    lead=lead,
                    description=f"Lead '{lead.name}' imported via enterprise bulk import",
                    metadata={
                        'import_session_id': str(self.operation_id),
                        'bulk_operation_id': self.operation_id
                    }
                ))
            
            if activities:
                LeadOperationLog.objects.bulk_create(activities, batch_size=500)
                
        except Exception as e:
            logger.warning(f"Error creating activity logs: {e}")
            # Don't fail the import for activity log issues
    
    def _update_stats(self, chunk_stats: Dict[str, Any]):
        """Update import statistics"""
        self.stats['processed_rows'] += chunk_stats['total']
        self.stats['imported_leads'] += chunk_stats['new_leads']
        self.stats['duplicate_leads'] += chunk_stats['duplicate_leads']
        self.stats['error_rows'] += chunk_stats['errors']
    
    def _update_progress(self):
        """Update progress tracking"""
        if self.progress_tracker:
            self.progress_tracker.update_progress(
                processed=self.stats['processed_rows'],
                errors=self.stats['error_rows']
            )
            
            # Update database operation progress
            self._update_operation_progress()
    
    def _update_operation_progress(self):
        """Update BulkOperation progress in database"""
        try:
            operation = BulkOperation.objects.get(id=self.operation_id)
            progress_data = self.progress_tracker.get_progress_data()
            
            operation.processed_items = self.stats['processed_rows']
            operation.status = 'running'
            
            # Calculate processing rate
            elapsed_time = progress_data.get('elapsed_time', 0)
            if elapsed_time > 0:
                operation.processing_rate = self.stats['processed_rows'] / elapsed_time
            
            operation.save()
            
            # Create detailed progress record
            BulkOperationProgress.objects.create(
                operation=operation,
                batch_number=self.stats['processed_rows'] // self.chunk_size,
                items_processed=self.stats['processed_rows'],
                items_created=self.stats['imported_leads'],
                items_updated=0,
                processing_time=0.1,  # Placeholder
                memory_usage_mb=0,  # Could be implemented with psutil
                error_count=self.stats['error_rows']
            )
            
        except Exception as e:
            logger.error(f"Error updating operation progress: {e}")
    
    def _finalize_import(self) -> Dict[str, Any]:
        """Finalize the import and return results"""
        self.stats['end_time'] = datetime.now()
        
        # Calculate final statistics
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        if duration > 0:
            self.stats['processing_rate'] = self.stats['processed_rows'] / duration
        
        # Mark operation as completed
        self._mark_operation_completed()
        
        # Get duplicate processor stats
        duplicate_stats = self.duplicate_processor.get_final_stats()
        
        result = {
            'status': 'completed',
            'stats': self.stats,
            'duplicate_stats': duplicate_stats,
            'duration_seconds': duration,
            'processing_rate': self.stats['processing_rate'],
            'success_rate': round(
                (self.stats['imported_leads'] / max(self.stats['processed_rows'], 1)) * 100, 2
            )
        }
        
        logger.info(f"Import completed: {self.stats['imported_leads']} leads imported, "
                   f"{self.stats['duplicate_leads']} duplicates found, "
                   f"{self.stats['error_rows']} errors")
        
        return result
    
    def _mark_operation_completed(self):
        """Mark the bulk operation as completed"""
        try:
            operation = BulkOperation.objects.get(id=self.operation_id)
            operation.status = 'completed'
            operation.processed_items = self.stats['processed_rows']
            operation.items_created = self.stats['imported_leads']
            operation.end_time = datetime.now()
            
            if self.stats['end_time'] and self.stats['start_time']:
                operation.duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            
            operation.save()
            
        except Exception as e:
            logger.error(f"Error marking operation completed: {e}")
    
    def _mark_operation_failed(self, error_message: str):
        """Mark the bulk operation as failed"""
        try:
            operation = BulkOperation.objects.get(id=self.operation_id)
            operation.status = 'failed'
            operation.error_message = error_message
            operation.end_time = datetime.now()
            operation.save()
            
        except Exception as e:
            logger.error(f"Error marking operation failed: {e}")


@shared_task(bind=True, soft_time_limit=1800, time_limit=3600)  # 30 min soft, 60 min hard limit
def enterprise_bulk_import_async(self, operation_id: int, file_path: str, 
                                 company_id: int, user_id: int, file_name: str):
    """
    Celery task for enterprise-scale bulk lead import.
    
    Args:
        operation_id: BulkOperation ID for tracking
        file_path: Path to the uploaded file
        company_id: Company ID
        user_id: User ID who initiated the import
        file_name: Original file name
    """
    try:
        logger.info(f"Starting enterprise import task: operation_id={operation_id}, file={file_name}")
        
        # Update task state
        self.update_state(state='PROGRESS', meta={'status': 'Initializing import...'})
        
        # Initialize importer
        importer = EnterpriseLeadImporter(company_id, user_id, operation_id)
        
        # Open file and start import
        with open(file_path, 'rb') as file_handler:
            result = importer.import_leads_from_file(file_handler, file_name)
        
        # Clean up temporary file
        import os
        try:
            os.remove(file_path)
        except OSError:
            logger.warning(f"Could not remove temporary file: {file_path}")
        
        logger.info(f"Enterprise import completed: {result}")
        
        return {
            'status': 'success',
            'operation_id': operation_id,
            'result': result
        }
        
    except Exception as e:
        logger.error(f"Enterprise import task failed: {e}", exc_info=True)
        
        # Mark operation as failed
        try:
            from .models import BulkOperation
            operation = BulkOperation.objects.get(id=operation_id)
            operation.status = 'failed'
            operation.error_message = str(e)
            operation.end_time = datetime.now()
            operation.save()
        except Exception as op_error:
            logger.error(f"Error marking operation failed: {op_error}")
        
        # Clean up temporary file
        import os
        try:
            os.remove(file_path)
        except OSError:
            pass
        
        # Re-raise to mark task as failed
        raise
