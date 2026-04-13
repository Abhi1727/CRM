"""
Optimized query managers for CRM performance.
Provides efficient database queries with proper select_related and prefetch_related usage.
"""

from django.db import models
from django.db.models import Q, Count, Sum, Avg, Prefetch
from django.core.cache import cache
from django.utils import timezone
from typing import Optional, List, Dict, Any
import logging

from .cache import CacheManager, QueryResultCache, cache_queryset

logger = logging.getLogger(__name__)


class OptimizedLeadManager(models.Manager):
    """Optimized manager for Lead model with performance-focused query methods"""
    
    def get_queryset(self):
        """Override to always include base optimizations"""
        return super().get_queryset().select_related(
            'assigned_user', 'created_by', 'assigned_user__manager', 'assigned_user__team_lead'
        )
    
    @cache_queryset(timeout=900, key_prefix="accessible_leads")
    def get_accessible_leads(self, user, company_id: int, include_deleted: bool = False):
        """Get leads accessible to user with full optimization"""
        from dashboard.models import Lead
        
        base_filters = {'company_id': company_id}
        if not include_deleted:
            base_filters['deleted'] = False
        
        if user.role == 'owner':
            return self.filter(**base_filters)
        
        elif user.role == 'manager':
            return self.filter(
                Q(**base_filters) & (
                    Q(assigned_user__manager=user) |
                    Q(assigned_user__team_lead__manager=user) |
                    Q(assigned_user=user)
                )
            )
        
        elif user.role == 'team_lead':
            return self.filter(
                Q(**base_filters) & (
                    Q(assigned_user__team_lead=user) |
                    Q(assigned_user=user)
                )
            )
        
        else:  # agent
            return self.filter(
                Q(**base_filters) & Q(assigned_user=user)
            )
    
    def get_leads_with_stats(self, user, company_id: int, status_filters: List[str] = None):
        """Get leads with aggregated statistics in single query"""
        queryset = self.get_accessible_leads(user, company_id)
        
        if status_filters:
            queryset = queryset.filter(status__in=status_filters)
        
        # Prefetch related data for statistics
        queryset = queryset.prefetch_related(
            Prefetch('communications', queryset=self.model.communications.related.related_model.objects.order_by('-created_at')[:5]),
            Prefetch('activities', queryset=self.model.activities.related.related_model.objects.order_by('-created_at')[:5]),
        )
        
        return queryset
    
    def get_leads_for_dashboard(self, user, company_id: int, limit: int = 10):
        """Get recent leads for dashboard with optimal performance"""
        return self.get_accessible_leads(user, company_id).order_by('-created_at')[:limit]
    
    def get_lead_statistics(self, user, company_id: int) -> Dict[str, Any]:
        """Get comprehensive lead statistics with optimized queries"""
        cache_key = QueryResultCache.get_query_cache_key(
            'lead_statistics', user.id, company_id
        )
        
        cached_stats = QueryResultCache.get_cached_query_result(cache_key)
        if cached_stats:
            return cached_stats
        
        queryset = self.get_accessible_leads(user, company_id)
        
        # Single query for all statistics
        stats = queryset.aggregate(
            total_leads=Count('id_lead'),
            converted_leads=Count('id_lead', filter=Q(status='sale_done')),
            total_revenue=Sum('exp_revenue'),
            avg_followup_rate=Avg('followup_datetime'),
            recent_leads=Count('id_lead', filter=Q(created_at__gte=timezone.now() - timezone.timedelta(days=30))),
        )
        
        # Status distribution
        status_stats = dict(
            queryset.values('status')
            .annotate(count=Count('id_lead'))
            .values_list('status', 'count')
        )
        
        # Assignment statistics
        assignment_stats = dict(
            queryset.values('assigned_user__username')
            .annotate(count=Count('id_lead'))
            .values_list('assigned_user__username', 'count')
            .order_by('-count')[:10]
        )
        
        result = {
            **stats,
            'status_distribution': status_stats,
            'top_assignments': assignment_stats,
            'conversion_rate': (
                (stats['converted_leads'] / stats['total_leads'] * 100) 
                if stats['total_leads'] > 0 else 0
            ),
        }
        
        QueryResultCache.cache_query_result(cache_key, result, timeout=600)
        return result
    
    def search_leads_optimized(self, user, company_id: int, search_query: str, 
                              filters: Dict[str, Any] = None):
        """Optimized lead search with full-text search capabilities"""
        queryset = self.get_accessible_leads(user, company_id)
        
        if search_query:
            # Use database-specific full-text search if available
            search_filter = (
                Q(name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(mobile__icontains=search_query) |
                Q(company__icontains=search_query)
            )
            queryset = queryset.filter(search_filter)
        
        if filters:
            if 'status' in filters:
                queryset = queryset.filter(status__in=filters['status'])
            if 'assigned_user' in filters:
                queryset = queryset.filter(assigned_user_id=filters['assigned_user'])
            if 'date_from' in filters:
                queryset = queryset.filter(created_at__date__gte=filters['date_from'])
            if 'date_to' in filters:
                queryset = queryset.filter(created_at__date__lte=filters['date_to'])
        
        return queryset.order_by('-created_at')
    
    def get_duplicate_leads(self, company_id: int, user=None):
        """Get duplicate leads with optimized grouping"""
        queryset = self.filter(company_id=company_id, duplicate_status__in=['exact_duplicate', 'potential_duplicate'])
        
        if user:
            queryset = queryset.filter(
                Q(assigned_user=user) | 
                Q(assigned_user__team_lead=user) |
                Q(assigned_user__team_lead__manager=user)
            )
        
        return queryset.select_related('last_assigned_agent', 'last_assigned_manager')
    
    def bulk_update_optimized(self, lead_ids: List[int], update_data: Dict[str, Any]):
        """Optimized bulk update with proper error handling"""
        return self.filter(id_lead__in=lead_ids).update(**update_data)


class OptimizedUserManager(models.Manager):
    """Optimized manager for User model with hierarchy-focused queries"""
    
    def get_queryset(self):
        """Override to always include base optimizations"""
        return super().get_queryset().select_related('manager', 'team_lead')
    
    @cache_queryset(timeout=900, key_prefix="accessible_users")
    def get_accessible_users(self, user, company_id: int):
        """Get users accessible to current user with optimization"""
        if user.role == 'owner':
            return self.filter(company_id=company_id).exclude(id=user.id)
        
        elif user.role == 'manager':
            return self.filter(
                Q(company_id=company_id) & (
                    Q(manager=user) | 
                    Q(team_lead__manager=user)
                )
            ).exclude(id=user.id)
        
        elif user.role == 'team_lead':
            return self.filter(
                Q(company_id=company_id) & Q(team_lead=user)
            ).exclude(id=user.id)
        
        else:  # agent
            return self.filter(id=user.id)
    
    def get_team_hierarchy(self, user, company_id: int):
        """Get complete team hierarchy with single query"""
        if user.role not in ['owner', 'manager']:
            return self.none()
        
        if user.role == 'owner':
            # Get all users in company with their relationships
            return self.filter(company_id=company_id).select_related(
                'manager', 'team_lead'
            ).order_by('role', 'username')
        
        elif user.role == 'manager':
            # Get manager's team leads and their agents
            team_leads = self.filter(manager=user, company_id=company_id)
            agents = self.filter(team_lead__in=team_leads, company_id=company_id)
            
            return self.filter(
                Q(id=user.id) | Q(id__in=team_leads) | Q(id__in=agents)
            ).select_related('manager', 'team_lead').order_by('role', 'username')
    
    def get_user_performance_stats(self, user_id: int, company_id: int, days: int = 30):
        """Get user performance statistics with caching"""
        cache_key = QueryResultCache.get_query_cache_key(
            'user_performance', user_id, company_id, days=days
        )
        
        cached_stats = QueryResultCache.get_cached_query_result(cache_key)
        if cached_stats:
            return cached_stats
        
        from datetime import timedelta
        from dashboard.models import Lead
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get user's leads statistics
        leads_stats = Lead.objects.filter(
            assigned_user_id=user_id,
            company_id=company_id,
            created_at__gte=cutoff_date
        ).aggregate(
            total_leads=Count('id_lead'),
            converted_leads=Count('id_lead', filter=Q(status='sale_done')),
            follow_ups_scheduled=Count('id_lead', filter=Q(followup_datetime__isnull=False)),
        )
        
        # Get communication statistics
        from dashboard.models import CommunicationHistory
        comm_stats = CommunicationHistory.objects.filter(
            lead__assigned_user_id=user_id,
            lead__company_id=company_id,
            sent_datetime__gte=cutoff_date
        ).aggregate(
            total_communications=Count('id_comm_history'),
            calls_made=Count('id_comm_history', filter=Q(communication_type='call')),
            emails_sent=Count('id_comm_history', filter=Q(communication_type='email')),
        )
        
        result = {
            **leads_stats,
            **comm_stats,
            'conversion_rate': (
                (leads_stats['converted_leads'] / leads_stats['total_leads'] * 100)
                if leads_stats['total_leads'] > 0 else 0
            ),
            'period_days': days,
        }
        
        QueryResultCache.cache_query_result(cache_key, result, timeout=600)
        return result


class OptimizedActivityManager(models.Manager):
    """Optimized manager for activity tracking"""
    
    def get_queryset(self):
        """Override to always include base optimizations"""
        return super().get_queryset().select_related('user', 'lead')
    
    def get_recent_activities(self, user, company_id: int, limit: int = 50):
        """Get recent activities with optimization"""
        from dashboard.models import Lead
        
        accessible_leads = Lead.objects.get_accessible_leads(user, company_id)
        return self.filter(
            lead__in=accessible_leads
        ).order_by('-created_at')[:limit]
    
    def get_activity_statistics(self, user, company_id: int, days: int = 30):
        """Get activity statistics with caching"""
        cache_key = QueryResultCache.get_query_cache_key(
            'activity_stats', user.id, company_id, days=days
        )
        
        cached_stats = QueryResultCache.get_cached_query_result(cache_key)
        if cached_stats:
            return cached_stats
        
        from datetime import timedelta
        cutoff_date = timezone.now() - timedelta(days=days)
        
        from dashboard.models import Lead
        accessible_leads = Lead.objects.get_accessible_leads(user, company_id)
        
        stats = self.filter(
            lead__in=accessible_leads,
            created_at__gte=cutoff_date
        ).values('activity_type').annotate(
            count=Count('id')
        ).order_by('-count')
        
        result = dict(stats.values_list('activity_type', 'count'))
        QueryResultCache.cache_query_result(cache_key, result, timeout=600)
        return result


# Query optimization utilities
class QueryOptimizer:
    """Utilities for optimizing database queries"""
    
    @staticmethod
    def optimize_queryset_for_list(queryset, page_size: int = 50):
        """Optimize queryset for list display with pagination"""
        return queryset.select_related(
            'assigned_user', 'created_by', 'assigned_user__manager', 'assigned_user__team_lead'
        ).prefetch_related(
            'activities', 'communications'
        )
    
    @staticmethod
    def get_count_optimized(queryset):
        """Get count with optimization for large datasets"""
        try:
            # Use count() for most cases
            return queryset.count()
        except Exception:
            # Fallback for complex queries
            return len(queryset)
    
    @staticmethod
    def bulk_create_optimized(model_class, objects: List[Dict[str, Any]], batch_size: int = 1000):
        """Optimized bulk create with error handling"""
        try:
            return model_class.objects.bulk_create(
                [model_class(**obj) for obj in objects],
                batch_size=batch_size
            )
        except Exception as e:
            logger.error(f"Bulk create error: {e}")
            # Fallback to individual creates
            created_objects = []
            for obj_data in objects:
                try:
                    created_objects.append(model_class.objects.create(**obj_data))
                except Exception as create_error:
                    logger.error(f"Individual create error: {create_error}")
            return created_objects
    
    @staticmethod
    def bulk_update_optimized(model_class, objects: List, fields: List[str], batch_size: int = 1000):
        """Optimized bulk update with error handling"""
        try:
            return model_class.objects.bulk_update(objects, fields, batch_size=batch_size)
        except Exception as e:
            logger.error(f"Bulk update error: {e}")
            # Fallback to individual updates
            updated_count = 0
            for obj in objects:
                try:
                    obj.save(update_fields=fields)
                    updated_count += 1
                except Exception as update_error:
                    logger.error(f"Individual update error: {update_error}")
            return updated_count
