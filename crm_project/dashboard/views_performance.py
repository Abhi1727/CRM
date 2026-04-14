"""
Performance monitoring and diagnostic views
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.core.cache import cache
from django.db import connection
from django.utils import timezone
from django.contrib.auth import get_user_model
import json
import time

from core.db_monitor import db_monitor
from .queries import OptimizedDashboardQueries

User = get_user_model()

def is_staff_user(user):
    """Check if user is staff or owner"""
    return user.is_staff or user.role == 'owner'

@login_required
@user_passes_test(is_staff_user)
def performance_dashboard(request):
    """Performance monitoring dashboard"""
    try:
        # Database health check
        db_health = db_monitor.test_connection_health()
        db_stats = db_monitor.get_connection_stats()
        
        # Cache statistics
        cache_stats = {}
        try:
            # Get cache info for each cache backend
            cache_stats['default'] = cache.keys('crm_default:*')[:10]  # Sample keys
            cache_stats['dashboard'] = cache.keys('crm_dashboard:*')[:10]
            cache_stats['hierarchy'] = cache.keys('crm_hierarchy:*')[:10]
        except Exception as e:
            cache_stats['error'] = str(e)
        
        # Recent query performance
        recent_queries = []
        if hasattr(connection, 'queries'):
            recent_queries = connection.queries[-10:]  # Last 10 queries
        
        # System metrics
        system_metrics = {
            'timestamp': timezone.now().isoformat(),
            'db_latency': db_health.get('latency_ms', 0),
            'db_status': db_health.get('status', 'unknown'),
            'active_connections': getattr(connection, 'connection', None) is not None,
        }
        
        context = {
            'db_health': db_health,
            'db_stats': db_stats,
            'cache_stats': cache_stats,
            'recent_queries': recent_queries,
            'system_metrics': system_metrics,
        }
        
        return render(request, 'dashboard/performance_dashboard.html', context)
        
    except Exception as e:
        return render(request, 'dashboard/performance_dashboard.html', {
            'error': f'Error loading performance data: {str(e)}'
        })

@login_required
@user_passes_test(is_staff_user)
def api_performance_stats(request):
    """API endpoint for performance statistics"""
    try:
        # Database performance
        db_health = db_monitor.test_connection_health()
        db_stats = db_monitor.get_connection_stats()
        
        # Cache hit rates (simplified)
        cache_info = {
            'default_cache_size': len(cache.keys('crm_default:*')) if hasattr(cache, 'keys') else 'unknown',
            'dashboard_cache_size': len(cache.keys('crm_dashboard:*')) if hasattr(cache, 'keys') else 'unknown',
        }
        
        # Test dashboard query performance
        start_time = time.time()
        try:
            dashboard_stats = OptimizedDashboardQueries.get_dashboard_statistics(
                request.user, request.user.company_id
            )
            dashboard_query_time = (time.time() - start_time) * 1000
        except Exception as e:
            dashboard_query_time = -1
            dashboard_stats = {'error': str(e)}
        
        return JsonResponse({
            'timestamp': timezone.now().isoformat(),
            'database': {
                'health': db_health,
                'stats': db_stats,
                'query_time_ms': round(dashboard_query_time, 2),
            },
            'cache': cache_info,
            'dashboard_stats': dashboard_stats,
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }, status=500)

@login_required
@user_passes_test(is_staff_user)
def clear_performance_cache(request):
    """Clear performance-related caches"""
    if request.method == 'POST':
        try:
            # Clear dashboard caches
            cache.delete_pattern('crm_dashboard:*')
            cache.delete_pattern('crm_hierarchy:*')
            cache.delete_pattern('crm_queries:*')
            
            return JsonResponse({
                'status': 'success',
                'message': 'Performance caches cleared successfully',
                'timestamp': timezone.now().isoformat()
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e),
                'timestamp': timezone.now().isoformat()
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@login_required
@user_passes_test(is_staff_user)
def test_bulk_assignment_performance(request):
    """Test bulk assignment performance with monitoring"""
    if request.method == 'POST':
        try:
            from .models import Lead
            from .tasks import bulk_lead_assignment_async
            from core.cache import CacheManager
            
            # Get sample leads for testing (limit to 50 for safety)
            sample_leads = Lead.objects.filter(
                company_id=request.user.company_id,
                deleted=False,
                assigned_user__isnull=True
            )[:50]
            
            if not sample_leads:
                return JsonResponse({
                    'status': 'error',
                    'message': 'No unassigned leads found for testing'
                }, status=400)
            
            lead_ids = list(sample_leads.values_list('id_lead', flat=True))
            
            # Create bulk operation for testing
            from .models import BulkOperation
            operation = BulkOperation.objects.create(
                operation_type='bulk_assign',
                user=request.user,
                company_id=request.user.company_id,
                requested_count=len(lead_ids)
            )
            
            # Start async task
            task = bulk_lead_assignment_async.delay(
                operation.id, lead_ids, request.user.id, batch_size=25
            )
            
            return JsonResponse({
                'status': 'success',
                'message': f'Bulk assignment test started for {len(lead_ids)} leads',
                'operation_id': operation.id,
                'task_id': task.id,
                'lead_count': len(lead_ids)
            })
            
        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)
