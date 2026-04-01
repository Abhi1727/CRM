from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db.models import Q, Count
import json
import logging

from dashboard.models import Lead

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def get_all_users_for_reassignment(request):
    """
    Get all active users for admin manual lead reassignment.
    Only accessible to users with 'owner' role.
    Returns JSON with user ID, name, role, and current lead count.
    Excludes the user being deleted from the selection list.
    """
    try:
        # Check if current user is owner (admin-only access)
        if request.user.role != 'owner':
            logger.warning(f"Non-owner user {request.user.username} attempted to access reassignment API")
            return JsonResponse({
                'success': False,
                'error': 'Only owners can access user reassignment data'
            }, status=403)
        
        # Get the user being deleted (exclude from selection)
        user_to_delete_id = request.GET.get('exclude_user_id')
        
        # Get all active users in the company except the user being deleted and current user
        users_queryset = User.objects.filter(
            company_id=request.user.company_id,
            account_status='active'
        ).exclude(id=request.user.id)  # Exclude current admin
        
        # Exclude the user being deleted if specified
        if user_to_delete_id:
            users_queryset = users_queryset.exclude(id=int(user_to_delete_id))
        
        # Get lead counts for each user
        users_with_counts = users_queryset.annotate(
            lead_count=Count('assigned_leads', filter=Q(assigned_leads__status__in=['lead', 'interested_follow_up', 'contacted', 'sale_done']))
        ).order_by('role', 'username')
        
        users_data = []
        for user in users_with_counts:
            users_data.append({
                'id': user.id,
                'name': user.get_full_name() or user.username,
                'username': user.username,
                'role': user.get_role_display(),
                'role_value': user.role,
                'lead_count': user.lead_count,
                'email': user.email,
                'phone': user.phone,
            })
        
        logger.info(f"Owner {request.user.username} retrieved {len(users_data)} users for reassignment")
        
        return JsonResponse({
            'success': True,
            'users': users_data,
            'total_count': len(users_data)
        })
        
    except ValueError as e:
        logger.error(f"Invalid user ID in reassignment API: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid user ID provided'
        }, status=400)
        
    except Exception as e:
        logger.error(f"Error getting users for reassignment: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve users for reassignment'
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_user_lead_summary(request, user_id):
    """
    Get lead summary for a specific user to help admin make informed reassignment decisions.
    Only accessible to owners.
    """
    try:
        # Check if current user is owner
        if request.user.role != 'owner':
            return JsonResponse({
                'success': False,
                'error': 'Only owners can access user lead summaries'
            }, status=403)
        
        target_user = get_object_or_404(User, id=user_id, company_id=request.user.company_id)
        
        # Get lead statistics
        total_leads = Lead.objects.filter(assigned_user=target_user).count()
        active_leads = Lead.objects.filter(
            assigned_user=target_user,
            status__in=['lead', 'interested_follow_up', 'contacted']
        ).count()
        converted_leads = Lead.objects.filter(
            assigned_user=target_user,
            status='sale_done'
        ).count()
        
        # Get recent leads
        recent_leads = Lead.objects.filter(
            assigned_user=target_user
        ).order_by('-created_at')[:5]
        
        recent_leads_data = []
        for lead in recent_leads:
            recent_leads_data.append({
                'id': lead.id_lead,
                'name': lead.name,
                'status': lead.get_status_display(),
                'created_at': lead.created_at.strftime('%Y-%m-%d %H:%M'),
                'followup_datetime': lead.followup_datetime.strftime('%Y-%m-%d %H:%M') if lead.followup_datetime else None,
            })
        
        summary_data = {
            'user': {
                'id': target_user.id,
                'name': target_user.get_full_name() or target_user.username,
                'username': target_user.username,
                'role': target_user.get_role_display(),
                'email': target_user.email,
            },
            'lead_stats': {
                'total_leads': total_leads,
                'active_leads': active_leads,
                'converted_leads': converted_leads,
                'conversion_rate': (converted_leads / total_leads * 100) if total_leads > 0 else 0,
            },
            'recent_leads': recent_leads_data,
        }
        
        return JsonResponse({
            'success': True,
            'data': summary_data
        })
        
    except Exception as e:
        logger.error(f"Error getting user lead summary: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve user lead summary'
        }, status=500)
