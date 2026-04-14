"""
Optimized database queries for dashboard performance
"""

from django.db import models
from django.db.models import Q, Count, Sum, Avg, Max, Min, Case, When, Value, IntegerField, F, Window, Prefetch
from django.core.cache import cache
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

class OptimizedDashboardQueries:
    """Optimized queries for dashboard operations"""
    
    @staticmethod
    def get_dashboard_statistics(user, company_id):
        """Get comprehensive dashboard statistics with minimal queries"""
        cache_key = f'dashboard_stats_{company_id}_{user.id}_{user.role}'
        cached_stats = cache.get(cache_key)
        
        if cached_stats:
            return cached_stats
        
        from dashboard.models import Lead
        
        # Base queryset with optimization
        base_qs = Lead.objects.filter(
            company_id=company_id,
            deleted=False
        )
        
        # Apply user hierarchy filtering
        if user.role != 'owner':
            accessible_users = user.get_accessible_users()
            base_qs = base_qs.filter(assigned_user__in=accessible_users)
        
        # Single query for all statistics
        stats = base_qs.aggregate(
            total_leads=Count('id_lead'),
            today_follow_ups=Count('id_lead', filter=Q(followup_datetime__date=timezone.now().date())),
            exp_revenue_sum=Sum('exp_revenue'),
            course_amount_sum=Sum('course_amount'),
            new_leads=Count('id_lead', filter=Q(assigned_user__isnull=True)),
            converted_leads=Count('id_lead', filter=Q(status='sale_done')),
        )
        
        # Status distribution in single query
        status_distribution = list(
            base_qs.values('status')
            .annotate(count=Count('id_lead'))
            .order_by('-count')
        )
        
        # User performance based on role
        user_performance = OptimizedDashboardQueries._get_user_performance(base_qs, user)
        
        result = {
            'total_leads': stats['total_leads'] or 0,
            'today_follow_ups': stats['today_follow_ups'] or 0,
            'exp_revenue': float(stats['exp_revenue_sum'] or 0),
            'course_amount': float(stats['course_amount_sum'] or 0),
            'new_leads': stats['new_leads'] or 0,
            'converted_leads': stats['converted_leads'] or 0,
            'status_distribution': status_distribution,
            'user_performance': user_performance,
            'conversion_rate': (
                (stats['converted_leads'] / stats['total_leads'] * 100) 
                if stats['total_leads'] > 0 else 0
            )
        }
        
        # Cache for 5 minutes
        cache.set(cache_key, result, 300)
        return result
    
    @staticmethod
    def _get_user_performance(base_qs, user):
        """Get user-specific performance metrics"""
        if user.role == 'agent':
            # Agent performance
            agent_stats = base_qs.filter(assigned_user=user).aggregate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done')),
                pending_followups=Count('id_lead', filter=Q(followup_datetime__lt=timezone.now())),
            )
            return {
                'type': 'agent',
                'total_leads': agent_stats['total_leads'] or 0,
                'converted_leads': agent_stats['converted_leads'] or 0,
                'pending_followups': agent_stats['pending_followups'] or 0,
                'conversion_rate': (
                    (agent_stats['converted_leads'] / agent_stats['total_leads'] * 100)
                    if agent_stats['total_leads'] > 0 else 0
                )
            }
        
        elif user.role == 'team_lead':
            # Team lead performance - aggregate for all team members
            team_members = user.get_accessible_users().filter(role='agent')
            team_stats = base_qs.filter(assigned_user__in=team_members).aggregate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done')),
                team_members_count=Count('assigned_user', distinct=True),
            )
            
            # Individual agent performance
            agent_performance = list(
                base_qs.filter(assigned_user__in=team_members)
                .values('assigned_user__username', 'assigned_user__id')
                .annotate(
                    total_leads=Count('id_lead'),
                    converted_leads=Count('id_lead', filter=Q(status='sale_done'))
                )
                .order_by('-converted_leads')[:10]
            )
            
            return {
                'type': 'team_lead',
                'total_leads': team_stats['total_leads'] or 0,
                'converted_leads': team_stats['converted_leads'] or 0,
                'team_members_count': team_stats['team_members_count'] or 0,
                'agent_performance': agent_performance,
                'team_conversion_rate': (
                    (team_stats['converted_leads'] / team_stats['total_leads'] * 100)
                    if team_stats['total_leads'] > 0 else 0
                )
            }
        
        elif user.role == 'manager':
            # Manager performance - aggregate for all team leads
            team_leads = user.get_accessible_users().filter(role='team_lead')
            manager_stats = base_qs.filter(
                assigned_user__team_lead__in=team_leads
            ).aggregate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done')),
                team_leads_count=Count('assigned_user__team_lead', distinct=True),
            )
            
            # Team lead performance
            lead_performance = list(
                base_qs.filter(assigned_user__team_lead__in=team_leads)
                .values('assigned_user__team_lead__username', 'assigned_user__team_lead__id')
                .annotate(
                    total_leads=Count('id_lead'),
                    converted_leads=Count('id_lead', filter=Q(status='sale_done'))
                )
                .order_by('-converted_leads')[:10]
            )
            
            return {
                'type': 'manager',
                'total_leads': manager_stats['total_leads'] or 0,
                'converted_leads': manager_stats['converted_leads'] or 0,
                'team_leads_count': manager_stats['team_leads_count'] or 0,
                'lead_performance': lead_performance,
                'manager_conversion_rate': (
                    (manager_stats['converted_leads'] / manager_stats['total_leads'] * 100)
                    if manager_stats['total_leads'] > 0 else 0
                )
            }
        
        return {'type': 'owner', 'message': 'Owner sees all data'}
    
    @staticmethod
    def get_lead_list_optimized(base_queryset, filters, page_size=25, page=1):
        """Optimized lead list with minimal queries"""
        # Apply filters
        queryset = base_queryset
        
        if filters.get('status'):
            queryset = queryset.filter(status=filters['status'])
        
        if filters.get('search'):
            search_term = filters['search']
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(email__icontains=search_term) |
                Q(mobile__icontains=search_term)
            )
        
        if filters.get('assigned_user'):
            queryset = queryset.filter(assigned_user_id=filters['assigned_user'])
        
        # Get total count efficiently
        total_count = queryset.count()
        
        # Apply ordering and pagination with select_related
        offset = (page - 1) * page_size
        leads = queryset.select_related(
            'assigned_user', 'created_by', 'assigned_user__team_lead', 'assigned_user__manager'
        ).order_by('-created_at')[offset:offset + page_size]
        
        return {
            'leads': leads,
            'total_count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        }
    
    @staticmethod
    def get_follow_up_reminders(user, company_id):
        """Get follow-up reminders with optimized queries"""
        from dashboard.models import Lead
        
        cache_key = f'followup_reminders_{company_id}_{user.id}'
        cached_reminders = cache.get(cache_key)
        
        if cached_reminders:
            return cached_reminders
        
        # Base queryset with optimization
        base_qs = Lead.objects.filter(
            company_id=company_id,
            deleted=False,
            followup_datetime__isnull=False
        )
        
        # Apply user hierarchy
        if user.role != 'owner':
            accessible_users = user.get_accessible_users()
            base_qs = base_qs.filter(assigned_user__in=accessible_users)
        
        # Get reminders categorized by time
        now = timezone.now()
        
        reminders = {
            'overdue': list(
                base_qs.filter(followup_datetime__lt=now)
                .select_related('assigned_user')
                .order_by('followup_datetime')[:20]
            ),
            'today': list(
                base_qs.filter(
                    followup_datetime__date=now.date(),
                    followup_datetime__gte=now
                )
                .select_related('assigned_user')
                .order_by('followup_datetime')[:20]
            ),
            'upcoming': list(
                base_qs.filter(
                    followup_datetime__gt=now.date(),
                    followup_datetime__lte=now + timedelta(days=7)
                )
                .select_related('assigned_user')
                .order_by('followup_datetime')[:20]
            )
        }
        
        # Cache for 10 minutes
        cache.set(cache_key, reminders, 600)
        return reminders


class QueryOptimizer:
    """General query optimization utilities"""
    
    @staticmethod
    def optimize_lead_queryset(queryset):
        """Apply common optimizations to lead querysets"""
        return queryset.select_related(
            'assigned_user', 'created_by', 'modified_user',
            'assigned_user__team_lead', 'assigned_user__manager'
        ).prefetch_related(
            'activities', 'comments', 'communications'
        )
    
    @staticmethod
    def bulk_update_with_history(queryset, updates, user):
        """Bulk update with history tracking"""
        from dashboard.models import LeadHistory
        
        # Get original values for history
        original_values = {}
        if 'status' in updates:
            original_values = dict(
                queryset.values_list('id_lead', 'status')
            )
        
        # Perform bulk update
        updated_count = queryset.update(**updates, updated_at=timezone.now())
        
        # Create history records in batch
        if original_values:
            history_objects = []
            for lead_id, old_status in original_values.items():
                if old_status != updates.get('status'):
                    history_objects.append(
                        LeadHistory(
                            lead_id=lead_id,
                            user=user,
                            field_name='status',
                            old_value=old_status,
                            new_value=updates.get('status'),
                            action='bulk_update'
                        )
                    )
            
            if history_objects:
                LeadHistory.objects.bulk_create(history_objects, batch_size=500)
        
        return updated_count
