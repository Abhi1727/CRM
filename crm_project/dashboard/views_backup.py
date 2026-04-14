from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, QueryDict
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.db.models import Q, Count, Sum, Avg, Max, Min, Case, When, Value, IntegerField, F, Window, Prefetch
from django.utils import timezone
from django.urls import reverse
from django.core.cache import cache
from django.conf import settings
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import hashlib
import pandas as pd
import csv
import time
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict
import uuid

from .models import Lead, LeadActivity, LeadHistory, LeadImportSession, LeadOperationLog, BulkOperation, BulkOperationProgress
from .forms import (
    LeadForm, LeadAssignmentForm, BulkLeadAssignmentForm, 
    LeadImportForm, LeadStatusUpdateForm, RestrictedLeadForm
)
from accounts.permissions import hierarchy_required, role_required, can_access_lead_required
from accounts.models import User
from services.duplicate_detector import DuplicateDetector

logger = logging.getLogger(__name__)
from .bulk_assignment_processor import BulkAssignmentProcessor
from core.cache import CacheManager, QueryResultCache, cache_result, cached_view
from core.queries import OptimizedLeadManager, OptimizedUserManager, QueryOptimizer
from .queries import OptimizedDashboardQueries, QueryOptimizer as DashboardQueryOptimizer

# Role-based permission helpers
def _can_edit_lead_details(user, lead):
    """
    Check if user can edit lead details based on role.
    Only owners and managers can edit lead details.
    Team leads and agents can only update status/follow-up.
    """
    if user.role in ['owner', 'manager']:
        return True
    return False

def _can_edit_field_by_role(user, field_name):
    """
    Check if user can edit a specific field based on their role.
    Owners/Managers: Can edit all fields
    Team Leads/Agents: Can only edit status, followup_datetime, followup_remarks, description
    """
    if user.role in ['owner', 'manager']:
        return True
    
    # Restricted fields for team leads and agents
    restricted_fields = {
        'name', 'mobile', 'email', 'alt_mobile', 'whatsapp_no', 'alt_email', 
        'address', 'city', 'state', 'postalcode', 'country', 'birthdate', 
        'lead_source', 'lead_source_description', 'refered_by', 'campaign_id', 
        'course_name', 'course_amount', 'exp_revenue', 'exp_close_date', 
        'next_step', 'do_not_call'
    }
    
    # Team leads and agents can only edit these fields
    allowed_fields = {'status', 'followup_datetime', 'followup_remarks', 'description'}
    
    return field_name in allowed_fields

# Internal Reminder Views
@login_required
def internal_reminders(request):
    """Internal reminders dashboard page"""
    return render(request, 'dashboard/internal_reminders.html', {
        'role': request.user.get_role_display(),
    })

@login_required
@hierarchy_required
def team_dashboard(request):
    """Team follow-up dashboard page"""
    return render(request, 'dashboard/team_dashboard.html', {
        'role': request.user.get_role_display(),
    })

@login_required
@hierarchy_required
def home(request):
    # Get greeting based on time
    current_hour = datetime.now().hour
    if current_hour < 12:
        greeting_time = "Morning"
    elif current_hour < 18:
        greeting_time = "Afternoon"
    else:
        greeting_time = "Evening"
    
    # Use optimized dashboard queries
    try:
        dashboard_stats = OptimizedDashboardQueries.get_dashboard_statistics(
            request.user, request.user.company_id
        )
        
        # Format status distribution for template
        formatted_leads_by_status = {}
        for status_code, status_name in Lead.STATUS_CHOICES:
            formatted_leads_by_status[status_code] = {
                'name': status_name,
                'count': next(
                    (item['count'] for item in dashboard_stats['status_distribution'] 
                     if item['status'] == status_code), 0
                )
            }
        
        # Get follow-up reminders
        follow_up_reminders = OptimizedDashboardQueries.get_follow_up_reminders(
            request.user, request.user.company_id
        )
        
        # Prepare context based on user role
        context = {
            'user': request.user,
            'role': request.user.get_role_display(),
            'greeting_time': greeting_time,
            'total_leads': dashboard_stats['total_leads'],
            'today_follow_ups': dashboard_stats['today_follow_ups'],
            'expected_revenue': dashboard_stats['exp_revenue'],
            'actual_revenue': dashboard_stats['course_amount'],
            'leads_by_status': formatted_leads_by_status,
            'conversion_rate': dashboard_stats['conversion_rate'],
            'follow_up_reminders': follow_up_reminders,
        }
        
        # Add role-specific context
        user_performance = dashboard_stats['user_performance']
        if user_performance['type'] == 'agent':
            context.update({
                'my_leads_count': user_performance['total_leads'],
                'converted_leads': user_performance['converted_leads'],
                'pending_followups': user_performance['pending_followups'],
                'conversion_rate': user_performance['conversion_rate'],
            })
        elif user_performance['type'] == 'team_lead':
            context.update({
                'team_agents_count': user_performance['team_members_count'],
                'agent_performance': user_performance['agent_performance'],
                'team_conversion_rate': user_performance['team_conversion_rate'],
            })
        elif user_performance['type'] == 'manager':
            context.update({
                'team_leads_count': user_performance['team_leads_count'],
                'lead_performance': user_performance['lead_performance'],
                'manager_conversion_rate': user_performance['manager_conversion_rate'],
            })
        
        return render(request, 'dashboard/home.html', context)
        
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        # Fallback to basic dashboard
        return render(request, 'dashboard/home.html', {
            'user': request.user,
            'role': request.user.get_role_display(),
            'greeting_time': greeting_time,
            'error': 'Dashboard statistics temporarily unavailable'
        })

@login_required
def profile(request):
    return render(request, 'dashboard/profile.html')

VALID_PAGE_SIZES = {'5', '10', '25', '50', '100', '200', '500'}
LEAD_SORT_FIELDS = {
    'created_at': 'created_at',
    '-created_at': '-created_at',
    'name': 'name',
    '-name': '-name',
    'status': 'status',
    '-status': '-status',
    'assigned_user': 'assigned_user__username',
    '-assigned_user': '-assigned_user__username',
    'priority': 'followup_priority',
    '-priority': '-followup_priority',
}


def _normalize_page_size(raw_value, default=25):
    raw = str(raw_value or default).strip()
    if raw not in VALID_PAGE_SIZES:
        return default
    return int(raw)


def _extract_lead_filters(params):
    return {
        'status': params.get('status', '').strip(),
        'sort': params.get('sort', '-created_at').strip(),
        'page_size': _normalize_page_size(params.get('page_size', '25')),
        'search': params.get('search', '').strip(),
        'country': params.get('country', '').strip(),
        'course': params.get('course', '').strip(),
        'start_date': params.get('start_date', '').strip(),
        'end_date': params.get('end_date', '').strip(),
        'assigned_user': params.get('assigned_user', '').strip(),
        'preset': params.get('preset', '').strip(),
    }


def _apply_common_lead_filters(queryset, user, filters):
    import logging
    logger = logging.getLogger(__name__)
    
    # DEBUG: Log initial state
    logger.debug(f"DEBUG: _apply_common_lead_filters called")
    logger.debug(f"DEBUG: User: {user.username} (role: {user.role}, company_id: {user.company_id})")
    logger.debug(f"DEBUG: Initial queryset count: {queryset.count()}")
    logger.debug(f"DEBUG: Filters received: {filters}")
    
    if filters['status']:
        queryset = queryset.filter(status=filters['status'])
        logger.debug(f"DEBUG: After status filter ({filters['status']}): {queryset.count()}")

    if filters['search']:
        # Optimize search query by using database-specific optimizations
        search_term = filters['search'].strip()
        
        # Skip empty searches
        if not search_term:
            logger.debug(f"DEBUG: Empty search term, skipping search filter")
        else:
            # Use optimized search based on database engine
            if hasattr(queryset.model._meta.db_table, 'lower'):  # MySQL optimization
                # For MySQL, use LOWER() function for case-insensitive search
                search_conditions = (
                    Q(name__icontains=search_term) |
                    Q(email__icontains=search_term) |
                    Q(mobile__icontains=search_term) |
                    Q(alt_mobile__icontains=search_term) |
                    Q(alt_email__icontains=search_term)
                )
                
                # Add phone number search optimization (exact match for phone fields)
                if search_term.replace('-', '').replace(' ', '').isdigit():
                    search_conditions |= (
                        Q(mobile__regex=f'^[\\-\\s]*{re.escape(search_term)}[\\-\\s]*$') |
                        Q(alt_mobile__regex=f'^[\\-\\s]*{re.escape(search_term)}[\\-\\s]*$')
                    )
            else:
                # Standard search for other databases
                search_conditions = Q()
                search_fields = ['name', 'email', 'mobile', 'alt_mobile', 'alt_email']
                
                for field in search_fields:
                    search_conditions |= Q(**{f'{field}__icontains': search_term})
            
            queryset = queryset.filter(search_conditions)
            logger.debug(f"DEBUG: After search filter ({search_term}): {queryset.count()}")

    if filters['country']:
        queryset = queryset.filter(country__icontains=filters['country'])
        logger.debug(f"DEBUG: After country filter ({filters['country']}): {queryset.count()}")

    if filters['course']:
        queryset = queryset.filter(course_name__icontains=filters['course'])
        logger.debug(f"DEBUG: After course filter ({filters['course']}): {queryset.count()}")

    if filters['start_date']:
        try:
            start_date_obj = datetime.strptime(filters['start_date'], '%Y-%m-%d').date()
            # Convert to timezone-aware datetime for MySQL compatibility
            start_datetime = timezone.make_aware(datetime.combine(start_date_obj, time.min))
            
            # Optimize date range query by using a single Q object
            date_conditions = Q(
                created_at__gte=start_datetime
            ) | Q(
                assigned_at__gte=start_datetime
            ) | Q(
                transfer_date__gte=start_datetime
            )
            
            queryset = queryset.filter(date_conditions)
            logger.debug(f"DEBUG: After start_date filter ({filters['start_date']} -> {start_datetime}): {queryset.count()}")
        except ValueError:
            logger.debug(f"DEBUG: Invalid start_date format: {filters['start_date']}")

    if filters['end_date']:
        try:
            end_date_obj = datetime.strptime(filters['end_date'], '%Y-%m-%d').date()
            # Convert to timezone-aware datetime for MySQL compatibility
            end_datetime = timezone.make_aware(datetime.combine(end_date_obj, time.max))
            
            # Optimize date range query by using a single Q object
            date_conditions = Q(
                created_at__lte=end_datetime
            ) | Q(
                assigned_at__lte=end_datetime
            ) | Q(
                transfer_date__lte=end_datetime
            )
            
            queryset = queryset.filter(date_conditions)
            logger.debug(f"DEBUG: After end_date filter ({filters['end_date']} -> {end_datetime}): {queryset.count()}")
        except ValueError:
            logger.debug(f"DEBUG: Invalid end_date format: {filters['end_date']}")

    if filters['assigned_user']:
        try:
            queryset = queryset.filter(assigned_user_id=int(filters['assigned_user']))
            logger.debug(f"DEBUG: After assigned_user filter ({filters['assigned_user']}): {queryset.count()}")
        except ValueError:
            logger.debug(f"DEBUG: Invalid assigned_user format: {filters['assigned_user']}")

    # Handle preset filters with comprehensive logging
    if filters['preset']:
        logger.debug(f"DEBUG: Processing preset: {filters['preset']}")
        
        if filters['preset'] == 'my_team':
            accessible_users = user.get_accessible_users()
            logger.debug(f"DEBUG: Accessible users for {user.username}: {list(accessible_users.values_list('username', flat=True))}")
            
            if user.role in ['manager', 'owner']:
                queryset = queryset.filter(assigned_user__in=accessible_users)
            elif user.role == 'team_lead':
                queryset = queryset.filter(assigned_user__in=accessible_users)
            else:
                queryset = queryset.filter(assigned_user=user)
            logger.debug(f"DEBUG: After my_team preset: {queryset.count()}")
            
        elif filters['preset'] == 'my':
            # Check if user has any assigned leads
            user_assigned_leads = queryset.filter(assigned_user=user)
            user_assigned_count = user_assigned_leads.count()
            
            logger.debug(f"DEBUG: User {user.username} has {user_assigned_count} assigned leads")
            
            if user_assigned_count > 0:
                # User has assigned leads, show only their leads (current behavior)
                queryset = user_assigned_leads
                logger.debug(f"DEBUG: Showing user's assigned leads: {queryset.count()}")
            else:
                # User has no assigned leads, show all unassigned leads (new behavior)
                queryset = queryset.filter(assigned_user__isnull=True)
                logger.debug(f"DEBUG: User has no assigned leads, showing unassigned leads: {queryset.count()}")
            
        elif filters['preset'] == 'today':
            # Force Asia/Kolkata timezone for consistent date handling
            from django.utils.timezone import activate
            activate('Asia/Kolkata')
            
            today_kolkata = timezone.now().date()
            today_start = timezone.make_aware(datetime.combine(today_kolkata, time.min))
            today_end = timezone.make_aware(datetime.combine(today_kolkata, time.max))
            
            # Filter leads created today in Asia/Kolkata timezone
            queryset = queryset.filter(created_at__gte=today_start, created_at__lte=today_end)
            logger.debug(f"DEBUG: After today preset (Kolkata date={today_kolkata}, range={today_start} to {today_end}): {queryset.count()}")
            
        elif filters['preset'] == 'week':
            # Force Asia/Kolkata timezone for consistent date handling
            from django.utils.timezone import activate
            activate('Asia/Kolkata')
            
            week_ago_date = timezone.now().date() - timezone.timedelta(days=7)
            week_start = timezone.make_aware(datetime.combine(week_ago_date, time.min))
            queryset = queryset.filter(created_at__gte=week_start)
            logger.debug(f"DEBUG: After week preset (since={week_start} Kolkata): {queryset.count()}")
            
        elif filters['preset'] == 'month':
            # Force Asia/Kolkata timezone for consistent date handling
            from django.utils.timezone import activate
            activate('Asia/Kolkata')
            
            month_ago_date = timezone.now().date() - timezone.timedelta(days=30)
            month_start = timezone.make_aware(datetime.combine(month_ago_date, time.min))
            queryset = queryset.filter(created_at__gte=month_start)
            logger.debug(f"DEBUG: After month preset (since={month_start} Kolkata): {queryset.count()}")
            
        else:
            logger.debug(f"DEBUG: Unknown preset value: {filters['preset']}")

    logger.debug(f"DEBUG: Final queryset count: {queryset.count()}")
    return queryset


def _render_leads_list_page(request, base_queryset, page_title, default_sort='-created_at'):
    import logging
    logger = logging.getLogger(__name__)
    
    logger.debug(f"DEBUG: _render_leads_list_page called for {page_title}")
    logger.debug(f"DEBUG: Request GET params: {dict(request.GET)}")
    
    filters = _extract_lead_filters(request.GET)
    logger.debug(f"DEBUG: Extracted filters: {filters}")
    
    sort_by = filters['sort'] if filters['sort'] in LEAD_SORT_FIELDS else default_sort
    
    # Apply filters to base queryset
    filtered_queryset = _apply_common_lead_filters(base_queryset, request.user, filters)
    
    # Use optimized lead list function
    try:
        lead_list_data = OptimizedDashboardQueries.get_lead_list_optimized(
            filtered_queryset,
            filters,
            page_size=filters['page_size'],
            page=int(request.GET.get('page', 1))
        )
        
        # Apply sorting
        if sort_by in LEAD_SORT_FIELDS:
            lead_list_data['leads'] = lead_list_data['leads'].order_by(LEAD_SORT_FIELDS[sort_by])
        
        # Create paginator object for template compatibility
        paginator = Paginator([], filters['page_size'])  # Empty paginator
        paginator.count = lead_list_data['total_count']
        paginator.num_pages = lead_list_data['total_pages']
        
        # Create page object
        class MockPage:
            def __init__(self, object_list, number, paginator):
                self.object_list = object_list
                self.number = number
                self.paginator = paginator
                self.has_previous = number > 1
                self.has_next = number < paginator.num_pages
                self.previous_page_number = number - 1 if self.has_previous else None
                self.next_page_number = number + 1 if self.has_next else None
            
            def __len__(self):
                return len(self.object_list)
        
        page_obj = MockPage(lead_list_data['leads'], lead_list_data['page'], paginator)
        total_filtered_count = lead_list_data['total_count']
        
    except Exception as e:
        logger.error(f"Error in optimized lead list: {str(e)}")
        # Fallback to original method
        leads_qs = filtered_queryset.order_by(LEAD_SORT_FIELDS.get(sort_by, default_sort))
        total_filtered_count = leads_qs.count()
        paginator = Paginator(leads_qs, filters['page_size'])
        page_obj = paginator.get_page(request.GET.get('page'))

    filter_snapshot = request.GET.copy()
    filter_snapshot.pop('page', None)

    context = {
        'page_obj': page_obj,
        'leads': page_obj,
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': page_title,
        'current_sort': sort_by,
        'current_page_size': filters['page_size'],
        'search_query': filters['search'],
        'country_filter': filters['country'],
        'course_filter': filters['course'],
        'start_date': filters['start_date'],
        'end_date': filters['end_date'],
        'assigned_user_filter': filters['assigned_user'],
        'preset_filter': filters['preset'],
        'total_filtered_count': total_filtered_count,
        'current_page_count': len(page_obj.object_list),
        'selected_count': 0,
        'scope_count': total_filtered_count,
        'filter_snapshot': filter_snapshot.urlencode(),
        'active_filters_count': len([
            value for value in [
                filters['country'],
                filters['course'],
                filters['start_date'],
                filters['end_date'],
                filters['assigned_user'],
                filters['status'],
                filters['preset'],
                filters['search'],
            ] if value
        ]),
        'sort_options': [
            ('-created_at', 'Newest First'),
            ('created_at', 'Oldest First'),
            ('name', 'Name (A-Z)'),
            ('-name', 'Name (Z-A)'),
            ('status', 'Status (A-Z)'),
            ('-status', 'Status (Z-A)'),
            ('-priority', 'High Priority First'),
            ('priority', 'Low Priority First'),
            ('assigned_user', 'Assigned User (A-Z)'),
            ('-assigned_user', 'Assigned User (Z-A)'),
        ],
    }
    return render(request, 'dashboard/leads_list.html', context)


@login_required
@hierarchy_required
def leads_list(request):
    base_queryset = request.hierarchy_context['accessible_leads'].filter(deleted=False)
    return _render_leads_list_page(request, base_queryset, 'All Leads', default_sort='-created_at')

@login_required
@hierarchy_required
def leads_fresh(request):
    base_queryset = request.hierarchy_context['accessible_leads'].filter(
        deleted=False,
        assigned_user__isnull=True
    ).exclude(status='sale_done')
    return _render_leads_list_page(request, base_queryset, 'New Leads', default_sort='-created_at')

@login_required
@hierarchy_required
def leads_working(request):
    base_queryset = request.hierarchy_context['accessible_leads'].filter(
        deleted=False,
        assigned_user=request.user
    ).exclude(status='sale_done')
    return _render_leads_list_page(request, base_queryset, 'My Working Leads', default_sort='-created_at')

@login_required
@hierarchy_required
def leads_transferred(request):
    # Show leads assigned by current user (including bulk assignments from unassigned)
    assigned_by_user_leads = request.hierarchy_context['accessible_leads'].filter(
        deleted=False,
        assigned_by=request.user,
        assigned_at__isnull=False
    )
    
    # Also include formal transfers
    transfer_leads = request.hierarchy_context['accessible_leads'].filter(
        deleted=False,
        transfer_by=request.user.username,
        transfer_date__isnull=False
    )
    
    # Combine both datasets
    base_queryset = (assigned_by_user_leads | transfer_leads).distinct()
    
    # Apply common filters including date filtering and presets
    filters = _extract_lead_filters(request.GET)
    filtered_queryset = _apply_common_lead_filters(base_queryset, request.user, filters)
    
    return _render_leads_list_page(request, filtered_queryset, 'Transferred Leads', default_sort='-created_at')

@login_required
@hierarchy_required
def leads_converted(request):
    base_queryset = request.hierarchy_context['accessible_leads'].filter(
        deleted=False,
        status='sale_done'
    )
    return _render_leads_list_page(request, base_queryset, 'Converted Leads', default_sort='-created_at')


@login_required
def lead_create(request):
    """Create a new lead.

    Only owners can create new leads. By default the lead is created under the 
    current user's company and assigned to the current user. Later it can be 
    reassigned using the existing assignment screens.
    """
    # Only owners can create leads
    if request.user.role != 'owner':
        messages.error(request, "You don't have permission to create new leads. Only owners can create leads.")
        return redirect("dashboard:leads_all")
    
    if request.method == "POST":
        form = LeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            # Basic hierarchy fields
            lead.company_id = request.user.company_id
            lead.created_by = request.user
            lead.assigned_user = request.user
            lead.save()

            messages.success(request, "Lead created successfully.")
            return redirect("dashboard:leads_all")
    else:
        form = LeadForm()

    context = {
        "form": form,
        "page_title": "Add New Lead",
    }
    return render(request, "dashboard/lead_form.html", context)

@login_required
@hierarchy_required
def leads_team(request):
    if request.user.role in ['owner', 'manager', 'team_lead']:
        base_queryset = request.hierarchy_context['accessible_leads'].filter(
            deleted=False,
            assigned_user__in=request.hierarchy_context['accessible_users']
        )
    else:
        base_queryset = Lead.objects.none()
    return _render_leads_list_page(request, base_queryset, 'My Team Leads', default_sort='-created_at')


@login_required
@hierarchy_required
def leads_trash(request):
    base_queryset = request.hierarchy_context['accessible_leads'].filter(deleted=True)
    return _render_leads_list_page(request, base_queryset, 'Trash Leads', default_sort='-created_at')

@login_required
@can_access_lead_required
def lead_detail(request, pk):
    lead = request.current_lead  # Set by the decorator
    
    # Fetch comprehensive history data with optimized queries
    activities = lead.activities.select_related('user').all()
    lead_history = lead.history.select_related('user').all()
    communications = lead.communications.all()
    bo_updates = lead.bo_updates.all()
    comments = lead.comments.select_related('user').all()
    
    # Parse assignment history from JSON field with optimized user fetching
    assignment_history = []
    if lead.assignment_history and 'assignments' in lead.assignment_history:
        assignment_data = lead.assignment_history['assignments']
        
        # Collect all user IDs needed for batch fetching
        user_ids = set()
        for assignment in assignment_data:
            if assignment.get('from', {}).get('user'):
                user_ids.add(assignment['from']['user'])
            if assignment.get('to', {}).get('user'):
                user_ids.add(assignment['to']['user'])
            if assignment.get('by'):
                user_ids.add(assignment['by'])
        
        # Batch fetch all users at once
        users_lookup = {
            user.id: user 
            for user in User.objects.filter(id__in=user_ids)
        }
        
        for assignment in assignment_data:
            # Get user objects from lookup
            from_user = users_lookup.get(assignment.get('from', {}).get('user'))
            to_user = users_lookup.get(assignment.get('to', {}).get('user'))
            by_user = users_lookup.get(assignment.get('by'))
            
            assignment_history.append({
                'action': assignment.get('action', 'assignment'),
                'from_user': from_user,
                'to_user': to_user,
                'by_user': by_user,
                'at': assignment.get('to', {}).get('at'),
                'transfer_from': assignment.get('transfer_from'),
                'transfer_by': assignment.get('transfer_by'),
                'transfer_date': assignment.get('transfer_date'),
                       })
    
    # Combine all history items into chronological order
    timeline = []
    
    # Add lead history items
    for history in lead_history:
        timeline.append({
            'type': 'lead_history',
            'timestamp': history.created_at,
            'data': history,
            'icon': 'history',
            'color': 'blue'
        })
    
    # Add communication history items
    for comm in communications:
        timeline.append({
            'type': 'communication',
            'timestamp': comm.sent_datetime or comm.receive_datetime or comm.created_at,
            'data': comm,
            'icon': 'phone' if comm.communication_type == 'call' else 'envelope',
            'color': 'green'
        })
    
    # Add activity items
    for activity in activities:
        timeline.append({
            'type': 'activity',
            'timestamp': activity.created_at,
            'data': activity,
            'icon': 'clipboard-check',
            'color': 'purple'
        })
    
    # Add back office updates
    for bo_update in bo_updates:
        timeline.append({
            'type': 'bo_update',
            'timestamp': bo_update.created_at,
            'data': bo_update,
            'icon': 'cog',
            'color': 'orange'
        })
    
    # Add comments
    for comment in comments:
        timeline.append({
            'type': 'comment',
            'timestamp': comment.created_at,
            'data': comment,
            'icon': 'comment',
            'color': 'indigo'
        })
    
    # Add assignment history items
    for assignment in assignment_history:
        if assignment.get('at'):
            try:
                from datetime import datetime
                timestamp = datetime.fromisoformat(assignment['at'].replace('Z', '+00:00'))
                timeline.append({
                    'type': 'assignment',
                    'timestamp': timestamp,
                    'data': assignment,
                    'icon': 'user-plus',
                    'color': 'teal'
                })
            except (ValueError, TypeError):
                pass
    
    # Sort timeline by timestamp (most recent first)
    timeline.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # Check if user can modify this lead based on role
    can_modify = _can_edit_lead_details(request.user, lead)
    
    context = {
        'lead': lead,
        'activities': activities,
        'lead_history': lead_history,
        'communications': communications,
        'bo_updates': bo_updates,
        'comments': comments,
        'assignment_history': assignment_history,
        'timeline': timeline,
        'can_modify': can_modify,
    }
    return render(request, 'dashboard/lead_detail.html', context)

@login_required
@can_access_lead_required
def lead_edit(request, pk):
    """Edit an existing lead using role-based form selection."""
    from django.core.exceptions import PermissionDenied
    
    lead = request.current_lead
    user_role = request.user.role

    # Debug: Log the current lead status
    print(f"DEBUG: Editing lead {lead.id_lead}, current status='{lead.status}', display='{lead.get_status_display()}'")
    print(f"DEBUG: User role: {user_role}")

    # Basic permission: allow if user can modify the lead or is its assignee
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    if not can_modify:
        raise PermissionDenied("You don't have permission to edit this lead.")

    # Define restricted fields for Team Lead/Agent roles
    restricted_fields = [
        "name", "mobile", "email", "alt_mobile", "whatsapp_no", "alt_email",
        "address", "city", "state", "postalcode", "country", "birthdate",
        "lead_source", "lead_source_description", "refered_by", "campaign_id",
        "course_name", "course_amount", "exp_revenue", "exp_close_date",
        "next_step", "do_not_call"
    ]

    if request.method == "POST":
        # Choose form based on user role
        if user_role in ['team_lead', 'agent']:
            form = RestrictedLeadForm(request.POST, instance=lead, user=request.user)
            print(f"DEBUG: Using RestrictedLeadForm for {user_role}")
        else:
            form = LeadForm(request.POST, instance=lead, restricted_fields=restricted_fields if user_role in ['team_lead', 'agent'] else None)
            print(f"DEBUG: Using LeadForm for {user_role}")

        if form.is_valid():
            updated_lead = form.save(commit=False)
            updated_lead.modified_user = request.user
            
            # Server-side validation: Check if user tried to modify restricted fields
            if user_role in ['team_lead', 'agent']:
                # Compare with original lead data to detect restricted field changes
                original_lead = Lead.objects.get(pk=lead.pk)
                restricted_changes = []
                
                for field in restricted_fields:
                    if hasattr(original_lead, field) and hasattr(updated_lead, field):
                        original_value = getattr(original_lead, field)
                        new_value = getattr(updated_lead, field)
                        if original_value != new_value:
                            restricted_changes.append(field)
                
                if restricted_changes:
                    # Log security violation
                    print(f"SECURITY: User {request.user.username} attempted to modify restricted fields: {restricted_changes}")
                    messages.error(request, "You don't have permission to modify personal information fields.")
                    return redirect("dashboard:lead_detail", pk=lead.id_lead)
            
            print(f"DEBUG: Form submitted, new status='{updated_lead.status}'")
            updated_lead.save()
            messages.success(request, "Lead updated successfully.")
            return redirect("dashboard:lead_detail", pk=lead.id_lead)
    else:
        # Choose form based on user role for GET requests
        if user_role in ['team_lead', 'agent']:
            form = RestrictedLeadForm(instance=lead, user=request.user)
            print(f"DEBUG: Using RestrictedLeadForm for {user_role}")
        else:
            form = LeadForm(instance=lead, restricted_fields=restricted_fields if user_role in ['team_lead', 'agent'] else None)
            print(f"DEBUG: Using LeadForm for {user_role}")
        
        # Debug: Check form initial values
        print(f"DEBUG: Form initialized, status field initial='{form.fields.get('status', {}).get('initial', 'N/A')}'")

    context = {
        "form": form,
        "page_title": f"Edit Lead - {lead.name}",
        "user_role": user_role,
        "is_restricted_form": user_role in ['team_lead', 'agent'],
    }
    return render(request, "dashboard/lead_form.html", context)

@login_required
@role_required('owner', 'manager')
def reports(request):
    recent_operations = LeadOperationLog.objects.filter(
        company_id=request.user.company_id
    ).order_by('-created_at')[:100]
    return render(request, 'dashboard/reports.html', {
        'recent_operations': recent_operations,
        'page_title': 'Reports',
    })

@login_required
def settings(request):
    """User settings page for profile and password management"""
    from accounts.forms import UserProfileForm, CustomPasswordChangeForm
    
    # Initialize forms
    profile_form = UserProfileForm(instance=request.user)
    password_form = CustomPasswordChangeForm(user=request.user)
    
    profile_success = False
    password_success = False
    
    if request.method == 'POST':
        # Determine which form was submitted
        if 'profile_submit' in request.POST:
            # Handle profile update
            profile_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Your profile has been updated successfully!')
                profile_success = True
                # Reset form to show updated data
                profile_form = UserProfileForm(instance=request.user)
        elif 'password_submit' in request.POST:
            # Handle password change
            password_form = CustomPasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                messages.success(request, 'Your password has been changed successfully!')
                password_success = True
                # Update the session to prevent logout
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, password_form.user)
                # Reset form
                password_form = CustomPasswordChangeForm(user=request.user)
    
    context = {
        'profile_form': profile_form,
        'password_form': password_form,
        'profile_success': profile_success,
        'password_success': password_success,
    }
    
    return render(request, 'dashboard/settings.html', context)


# Lead Assignment Views
@login_required
@can_access_lead_required
def lead_assign(request, pk):
    """Assign a single lead to a user"""
    lead = request.current_lead
    
    # Check if user can assign this lead
    if not lead.can_be_assigned_by(request.user):
        raise PermissionDenied("You don't have permission to assign this lead.")
    
    if request.method == "POST":
        form = LeadAssignmentForm(request.user, request.POST)
        if form.is_valid():
            assigned_user = form.cleaned_data['assigned_user']
            assignment_notes = form.cleaned_data.get('assignment_notes', '')
            
            # Check hierarchy validation
            if not lead.can_be_assigned_to_user(assigned_user, request.user):
                messages.error(request, "You cannot assign this lead to the selected user due to hierarchy restrictions.")
            else:
                # Assign the lead
                old_user = lead.assigned_user
                # Use bulk_assignment=True when assigning from unassigned state
                is_bulk_from_unassigned = not old_user
                lead.assign_to_user(assigned_user, request.user, bulk_assignment=is_bulk_from_unassigned)
                
                # Create assignment history record
                LeadHistory.objects.create(
                    lead=lead,
                    user=request.user,
                    field_name='assigned_user',
                    old_value=old_user.username if old_user else None,
                    new_value=assigned_user.username,
                    action=f'Assigned to {assigned_user.username}'
                )
                
                # Create activity log
                LeadActivity.objects.create(
                    lead=lead,
                    user=request.user,
                    activity_type='assignment',
                    description=f'Lead assigned to {assigned_user.username}. {assignment_notes}'
                )
                
                messages.success(request, f"Lead successfully assigned to {assigned_user.username}.")
                return redirect("dashboard:lead_detail", pk=lead.id_lead)
    else:
        form = LeadAssignmentForm(request.user)
    
    context = {
        'lead': lead,
        'form': form,
        'page_title': f'Assign Lead - {lead.name}',
    }
    return render(request, 'dashboard/lead_assign.html', context)


@login_required
@hierarchy_required
def bulk_lead_assign(request):
    """Bulk assign multiple leads to a user with progress tracking"""
    if request.method == "POST":
        form = BulkLeadAssignmentForm(request.user, request.POST)
        if form.is_valid():
            assigned_user = form.cleaned_data['assigned_user']
            assignment_notes = form.cleaned_data.get('assignment_notes', '')
            
            # Resolve the target leads using scope resolution
            base_queryset = request.hierarchy_context['accessible_leads']
            target_leads, action_scope = _resolve_bulk_scope_queryset(request, base_queryset)
            
            if not target_leads.exists():
                messages.error(request, "No accessible leads found for assignment.")
                return redirect("dashboard:leads_all")
            
            # Create bulk operation for progress tracking
            operation_id = f"bulk_assign_{uuid.uuid4().hex[:12]}"
            operation = BulkOperation.objects.create(
                operation_id=operation_id,
                operation_type='bulk_assign',
                user=request.user,
                company_id=request.user.company_id,
                total_items=target_leads.count(),
                operation_config={
                    'assigned_user_id': assigned_user.id,
                    'assigned_user_name': assigned_user.username,
                    'assignment_notes': assignment_notes,
                    'action_scope': action_scope
                },
                filter_snapshot={
                    'action_scope': action_scope,
                    'filter_snapshot': request.POST.get('filter_snapshot', ''),
                    'request_count_override': target_leads.count()
                }
            )
            
            # Start operation
            operation.start_operation()
            
            # Use optimized bulk assignment processor
            processor = BulkAssignmentProcessor(
                operation_id=operation.id,
                lead_ids=list(target_leads.values_list('id_lead', flat=True)),
                assigned_user_id=assigned_user.id,
                assigned_by_id=request.user.id,
                company_id=request.user.company_id
            )
            
            # Execute the optimized bulk assignment
            result = processor.execute()
            successful_assignments = result['processed']
            failed_assignments = result['errors']
            
            # Complete operation
            operation.complete_operation(
                success=True,
                error_message=f"Failed to assign {failed_assignments} leads" if failed_assignments > 0 else None
            )
            
            if successful_assignments > 0:
                messages.success(request, f"Successfully assigned {successful_assignments} leads to {assigned_user.username}. Operation ID: {operation_id}")
            if failed_assignments > 0:
                messages.warning(request, f"Failed to assign {failed_assignments} leads due to permission restrictions. Operation ID: {operation_id}")
            
            return redirect("dashboard:leads_all")
    else:
        form = BulkLeadAssignmentForm(request.user)
    
    context = {
        'form': form,
        'page_title': 'Bulk Lead Assignment',
    }
    return render(request, 'dashboard/bulk_lead_assign.html', context)


def _resolve_bulk_scope_queryset(request, base_queryset):
    """
    Resolve bulk action targets using explicit scope contract:
    - current_page: uses posted lead_ids
    - all_filtered: reconstructs queryset from posted filter snapshot
    """
    action_scope = request.POST.get('action_scope', 'current_page').strip() or 'current_page'
    selected_ids = request.POST.getlist('lead_ids')

    if action_scope == 'all_filtered':
        filter_snapshot = request.POST.get('filter_snapshot', '')
        params = QueryDict(filter_snapshot, mutable=False) if filter_snapshot else request.GET
        filters = _extract_lead_filters(params)
        scoped_qs = _apply_common_lead_filters(base_queryset, request.user, filters)

        excluded_ids = request.POST.getlist('excluded_ids')
        if excluded_ids:
            try:
                excluded_ids_int = [int(value) for value in excluded_ids if str(value).strip()]
                scoped_qs = scoped_qs.exclude(id_lead__in=excluded_ids_int)
            except ValueError:
                pass
        return scoped_qs, action_scope

    # current_page / explicit selection fallback
    try:
        selected_ids_int = [int(value) for value in selected_ids if str(value).strip()]
    except ValueError:
        selected_ids_int = []
    return base_queryset.filter(id_lead__in=selected_ids_int), action_scope


def _create_operation_log(request, operation_type, action_scope, scoped_qs, success_count=0, failed_count=0, skipped_count=0, metadata=None, requested_count_override=None):
    requested_count = requested_count_override if requested_count_override is not None else scoped_qs.count()
    operation_id = f"{operation_type}_{uuid.uuid4().hex[:12]}"
    LeadOperationLog.objects.create(
        operation_id=operation_id,
        operation_type=operation_type,
        user=request.user,
        company_id=request.user.company_id,
        action_scope=action_scope,
        filter_snapshot=request.POST.get('filter_snapshot', ''),
        requested_count=requested_count,
        processed_count=success_count + failed_count + skipped_count,
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        metadata=metadata or {},
    )
    return operation_id


def _create_bulk_operation(request, operation_type, total_items, operation_config=None, filter_snapshot=None, estimated_duration=None):
    """Create a bulk operation for progress tracking"""
    operation_id = f"{operation_type}_{uuid.uuid4().hex[:12]}"
    return BulkOperation.objects.create(
        operation_id=operation_id,
        operation_type=operation_type,
        user=request.user,
        company_id=request.user.company_id,
        total_items=total_items,
        operation_config=operation_config or {},
        filter_snapshot=filter_snapshot or {},
        estimated_duration=estimated_duration
    )


def _update_operation_progress(operation, batch_num, batch_size, total_batches, 
                              batch_success, batch_failed, batch_skipped, 
                              batch_duration, error_samples=None):
    """Update operation progress with batch information"""
    update_id = f"{operation.operation_id}_batch_{batch_num}"
    
    # Calculate cumulative totals
    cumulative_processed = operation.processed_items + batch_success + batch_failed + batch_skipped
    cumulative_success = operation.success_items + batch_success
    cumulative_failed = operation.failed_items + batch_failed
    cumulative_skipped = operation.skipped_items + batch_skipped
    
    # Update main operation
    operation.update_progress(
        processed=batch_success + batch_failed + batch_skipped,
        success=batch_success,
        failed=batch_failed,
        skipped=batch_skipped
    )
    
    # Create detailed progress record
    BulkOperationProgress.objects.create(
        operation=operation,
        update_id=update_id,
        current_batch=batch_num,
        batch_size=batch_size,
        total_batches=total_batches,
        batch_success=batch_success,
        batch_failed=batch_failed,
        batch_skipped=batch_skipped,
        cumulative_processed=cumulative_processed,
        cumulative_success=cumulative_success,
        cumulative_failed=cumulative_failed,
        cumulative_skipped=cumulative_skipped,
        batch_duration=batch_duration,
        cumulative_duration=(timezone.now() - operation.started_at).total_seconds() if operation.started_at else 0,
        batch_rate=(batch_success + batch_failed + batch_skipped) / batch_duration if batch_duration > 0 else 0,
        error_samples=error_samples or []
    )


def _process_assignments_concurrently_with_progress(leads_queryset, assigned_user, assigned_by, assignment_notes, operation):
    """Process assignments concurrently with progress tracking"""
    from django.db import transaction
    from .models import LeadActivity
    
    BATCH_SIZE = 1000
    total_leads = leads_queryset.count()
    total_batches = (total_leads + BATCH_SIZE - 1) // BATCH_SIZE
    
    successful_assignments = 0
    failed_assignments = 0
    
    def process_batch(batch_leads, batch_num):
        batch_success = 0
        batch_failed = 0
        batch_errors = []
        
        batch_start_time = time.time()
        
        try:
            with transaction.atomic():
                leads_to_update = []
                activities_to_create = []
                
                for lead in batch_leads:
                    try:
                        # Check assignment permission
                        if not lead.can_be_assigned_by(assigned_by):
                            batch_failed += 1
                            batch_errors.append({
                                'lead_id': lead.id_lead,
                                'error': 'Permission denied',
                                'lead_name': lead.name
                            })
                            continue
                        
                        # Check if can be assigned to target user
                        if not lead.can_be_assigned_to_user(assigned_user, assigned_by):
                            batch_failed += 1
                            batch_errors.append({
                                'lead_id': lead.id_lead,
                                'error': 'Cannot assign to this user (hierarchy restriction)',
                                'lead_name': lead.name
                            })
                            continue
                        
                        # Perform assignment
                        old_assigned_user = lead.assigned_user
                        lead.assign_to_user(assigned_user, assigned_by, bulk_assignment=True)
                        leads_to_update.append(lead)
                        
                        # Create activity log
                        activity_description = f'Assigned to {assigned_user.get_full_name() or assigned_user.username}'
                        if assignment_notes:
                            activity_description += f' - Notes: {assignment_notes}'
                        
                        activities_to_create.append(LeadActivity(
                            lead=lead,
                            user=assigned_by,
                            activity_type='assignment',
                            description=activity_description
                        ))
                        
                        batch_success += 1
                        
                    except Exception as e:
                        batch_failed += 1
                        batch_errors.append({
                            'lead_id': lead.id_lead,
                            'error': str(e),
                            'lead_name': lead.name
                        })
                
                # Bulk update leads
                if leads_to_update:
                    Lead.objects.bulk_update(leads_to_update, ['assigned_user', 'assigned_by', 'assigned_at', 'transfer_from', 'transfer_by', 'transfer_date', 'assignment_history', 'last_assigned_agent', 'last_assigned_manager'])
                
                # Bulk create activities
                if activities_to_create:
                    LeadActivity.objects.bulk_create(activities_to_create)
                
        except Exception as e:
            # If transaction fails, count all as failed
            batch_failed = len(batch_leads)
            batch_errors.append({
                'error': f'Batch transaction failed: {str(e)}',
                'batch_num': batch_num
            })
        
        batch_duration = time.time() - batch_start_time
        
        # Update progress
        _update_operation_progress(
            operation, batch_num, len(batch_leads), total_batches,
            batch_success, batch_failed, 0, batch_duration,
            batch_errors[:5]  # Keep only first 5 errors
        )
        
        return batch_success, batch_failed
    
    # Process batches in parallel
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        batch_num = 0
        
        for start in range(0, total_leads, BATCH_SIZE):
            batch_num += 1
            batch_leads = leads_queryset[start:start + BATCH_SIZE]
            future = executor.submit(process_batch, list(batch_leads), batch_num)
            futures.append(future)
        
        # Collect results
        for future in as_completed(futures):
            batch_success, batch_failed = future.result()
            successful_assignments += batch_success
            failed_assignments += batch_failed
    
    return successful_assignments, failed_assignments


@login_required
@hierarchy_required
def bulk_lead_delete(request):
    """Soft delete multiple leads selected from list views."""
    if request.method != "POST":
        return redirect("dashboard:leads_all")

    # Keep delete action limited to non-agent roles.
    if request.user.role == 'agent':
        messages.error(request, "You don't have permission to delete leads.")
        return redirect("dashboard:leads_all")

    accessible_base = request.hierarchy_context['accessible_leads'].filter(deleted=False)
    scoped_qs, action_scope = _resolve_bulk_scope_queryset(request, accessible_base)
    leads_to_delete = list(scoped_qs.select_related('assigned_user'))
    if not leads_to_delete:
        messages.error(request, "No accessible leads found for deletion.")
        return redirect("dashboard:leads_all")

    # Use optimized bulk delete
    deleted_count = _bulk_delete_optimized(leads_to_delete, request.user)

    requested_count = request.POST.get('scope_count')
    try:
        requested_count = int(requested_count)
    except (TypeError, ValueError):
        requested_count = len(leads_to_delete)
    denied_count = max(requested_count - len(leads_to_delete), 0)
    operation_id = _create_operation_log(
        request,
        operation_type='bulk_delete',
        action_scope=action_scope,
        scoped_qs=scoped_qs,
        success_count=deleted_count,
        failed_count=denied_count,
        metadata={'requested_count': requested_count},
    )

    if deleted_count:
        messages.success(request, f"Successfully deleted {deleted_count} leads. Operation ID: {operation_id}")
    if denied_count:
        messages.warning(request, f"{denied_count} selected leads were skipped due to access restrictions.")

    return redirect("dashboard:leads_all")


@login_required
@hierarchy_required
def bulk_lead_restore(request):
    if request.method != "POST":
        return redirect("dashboard:leads_trash")

    if request.user.role == 'agent':
        messages.error(request, "You don't have permission to restore leads.")
        return redirect("dashboard:leads_trash")

    base_queryset = request.hierarchy_context['accessible_leads'].filter(deleted=True)
    scoped_qs, action_scope = _resolve_bulk_scope_queryset(request, base_queryset)
    leads_to_restore = list(scoped_qs.select_related('assigned_user'))
    if not leads_to_restore:
        messages.error(request, "No trashed leads found for restore.")
        return redirect("dashboard:leads_trash")

    restored_count = 0
    activity_data = []
    leads_to_update = []
    
    for lead in leads_to_restore:
        lead.deleted = False
        lead.modified_user = request.user
        leads_to_update.append(lead)
        
        activity_data.append(LeadActivity(
            lead=lead,
            user=request.user,
            activity_type='restore',
            description='Lead restored from trash (bulk action).'
        ))
        restored_count += 1

    # Bulk update leads
    if leads_to_update:
        Lead.objects.bulk_update(leads_to_update, ['deleted', 'modified_user'])
    
    # Bulk create activities
    if activity_data:
        LeadActivity.objects.bulk_create(activity_data)

    operation_id = _create_operation_log(
        request,
        operation_type='bulk_restore',
        action_scope=action_scope,
        scoped_qs=scoped_qs,
        success_count=restored_count,
    )
    messages.success(request, f"Successfully restored {restored_count} leads. Operation ID: {operation_id}")
    return redirect("dashboard:leads_trash")


@login_required
@hierarchy_required
def leads_trash_purge(request):
    if request.method != "POST":
        return redirect("dashboard:leads_trash")
    if request.user.role != 'owner':
        messages.error(request, "Only owner can permanently purge trash.")
        return redirect("dashboard:leads_trash")

    confirm_text = request.POST.get('confirm_text', '').strip()
    if confirm_text != 'PURGE':
        messages.error(request, "Purge confirmation failed. Type PURGE to continue.")
        return redirect("dashboard:leads_trash")

    base_queryset = request.hierarchy_context['accessible_leads'].filter(deleted=True)
    scoped_qs, action_scope = _resolve_bulk_scope_queryset(request, base_queryset)
    purge_count = scoped_qs.count()
    if purge_count == 0:
        messages.error(request, "No trashed leads found to purge.")
        return redirect("dashboard:leads_trash")

    scoped_qs.delete()
    operation_id = _create_operation_log(
        request,
        operation_type='trash_purge',
        action_scope=action_scope,
        scoped_qs=base_queryset.none(),
        success_count=purge_count,
        requested_count_override=purge_count,
    )
    messages.success(request, f"Permanently purged {purge_count} leads. Operation ID: {operation_id}")
    return redirect("dashboard:leads_trash")


@login_required
@role_required('owner', 'manager')
def operations_report_csv(request):
    logs = LeadOperationLog.objects.filter(company_id=request.user.company_id).order_by('-created_at')[:5000]
    lines = [
        "operation_id,operation_type,scope,requested,processed,success,failed,skipped,created_at,user"
    ]
    for log in logs:
        user_label = log.user.username if log.user else ''
        lines.append(
            f"{log.operation_id},{log.operation_type},{log.action_scope},{log.requested_count},"
            f"{log.processed_count},{log.success_count},{log.failed_count},{log.skipped_count},"
            f"{log.created_at.isoformat()},{user_label}"
        )
    response = HttpResponse("\n".join(lines), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=\"operation_report.csv\"'
    return response


# Lead Import Views
@login_required
@hierarchy_required
def download_demo_file(request):
    """Download demo CSV file for lead import template"""
    from django.conf import settings
    
    file_path = os.path.join(settings.BASE_DIR, 'static/files/demo_leads.csv')
    
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="demo_leads.csv"'
            return response
    else:
        raise Http404("Demo file not found")


@login_required
@hierarchy_required
def lead_import(request):
    """Import leads from CSV/Excel file with enhanced duplicate detection - only owners can import leads"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def _error_response(message, status=400, form_instance=None):
        messages.error(request, message)
        if is_ajax:
            return JsonResponse({'ok': False, 'error': message}, status=status)
        return render(request, 'dashboard/lead_import.html', {'form': form_instance or LeadImportForm()})

    # Only owners can import leads
    if request.user.role != 'owner':
        message = "You don't have permission to import leads. Only owners can import leads."
        if is_ajax:
            return JsonResponse({'ok': False, 'error': message}, status=403)
        messages.error(request, message)
        return redirect("dashboard:leads_all")
    
    if request.method == "POST":
        form = LeadImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            
            try:
                # Read the file content first to check if it's empty
                file_content = file.read()
                if not file_content.strip():
                    return _error_response("File is empty. Please upload a file with data.", form_instance=form)
                
                # Reset file pointer to beginning for pandas
                file.seek(0)
                
                # OPTIMIZED: Streaming file processing to reduce memory usage
                def process_file_streaming(file):
                    """Process file in streaming mode to reduce memory usage"""
                    import csv
                    from io import TextIOWrapper
                    
                    leads_data = []
                    
                    if file.name.endswith('.csv'):
                        # STREAMING CSV PROCESSING
                        file.seek(0)
                        reader = None
                        
                        # Try different encodings for CSV files
                        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
                        for encoding in encodings:
                            try:
                                file.seek(0)
                                if hasattr(file, 'read'):
                                    # Handle Django uploaded file
                                    text_file = TextIOWrapper(file, encoding=encoding)
                                    reader = csv.DictReader(text_file)
                                else:
                                    reader = csv.DictReader(file)
                                break
                            except UnicodeDecodeError:
                                continue
                        
                        if not reader:
                            raise ValueError("Unable to read CSV file with any supported encoding")
                        
                        # Validate and normalize column names
                        if not reader.fieldnames:
                            raise ValueError("CSV file has no headers")
                        
                        column_names = [str(col).strip().lower() for col in reader.fieldnames]
                        
                        # Validate required columns
                        required_columns = ['name', 'mobile']
                        missing_columns = [col for col in required_columns if col not in column_names]
                        
                        if missing_columns:
                            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
                        
                        # Process rows in streaming mode
                        for row_num, row in enumerate(reader):
                            if row_num >= 100000:  # Safety limit
                                break
                            
                            lead_data = {
                                'name': row.get('name', '').strip(),
                                'mobile': row.get('mobile', '').strip(),
                                'email': row.get('email', '').strip(),
                                'alt_mobile': row.get('alt_mobile', '').strip(),
                                'whatsapp_no': row.get('whatsapp_no', '').strip(),
                                'alt_email': row.get('alt_email', '').strip(),
                                'address': row.get('address', '').strip(),
                                'city': row.get('city', '').strip(),
                                'state': row.get('state', '').strip(),
                                'postalcode': row.get('postalcode', '').strip(),
                                'country': row.get('country', '').strip(),
                                'status': row.get('status', 'lead').strip() or 'lead',
                                'status_description': row.get('status_description', '').strip(),
                                'lead_source': row.get('lead_source', '').strip(),
                                'lead_source_description': row.get('lead_source_description', '').strip(),
                                'refered_by': row.get('refered_by', '').strip(),
                                'campaign_id': row.get('campaign_id', '').strip(),
                                'course_name': row.get('course_name', '').strip(),
                                'course_amount': row.get('course_amount', '').strip(),
                                'exp_revenue': row.get('exp_revenue', '').strip(),
                                'description': row.get('description', '').strip(),
                                'company': row.get('company', '').strip(),  # For related lead detection
                            }
                            
                            # Handle date fields
                            if 'exp_close_date' in row and row['exp_close_date'].strip():
                                try:
                                    from datetime import datetime
                                    lead_data['exp_close_date'] = datetime.strptime(row['exp_close_date'].strip(), '%Y-%m-%d').date()
                                except ValueError:
                                    pass  # Skip invalid dates
                            
                            if 'followup_datetime' in row and row['followup_datetime'].strip():
                                try:
                                    from datetime import datetime
                                    lead_data['followup_datetime'] = datetime.strptime(row['followup_datetime'].strip(), '%Y-%m-%d %H:%M:%S')
                                except ValueError:
                                    pass  # Skip invalid dates
                            
                            if 'birthdate' in row and row['birthdate'].strip():
                                try:
                                    from datetime import datetime
                                    lead_data['birthdate'] = datetime.strptime(row['birthdate'].strip(), '%Y-%m-%d').date()
                                except ValueError:
                                    pass  # Skip invalid dates
                            
                            # VALIDATE REQUIRED FIELDS
                            if not lead_data['name'] or not lead_data['mobile']:
                                continue
                            
                            leads_data.append(lead_data)
                            
                            # PROCESS IN CHUNKS TO SAVE MEMORY
                            if len(leads_data) >= 5000:
                                yield leads_data
                                leads_data = []
                        
                        # PROCESS REMAINING RECORDS
                        if leads_data:
                            yield leads_data
                    
                    else:
                        # For Excel files, still use pandas but with memory optimization
                        df = pd.read_excel(file)
                        
                        # Normalize column names
                        df.columns = [str(col).strip().lower() for col in df.columns]
                        
                        # Check if dataframe is empty
                        if df.empty:
                            raise ValueError("No data found in Excel file")
                        
                        # Validate required columns
                        required_columns = ['name', 'mobile']
                        missing_columns = [col for col in required_columns if col not in df.columns]
                        
                        if missing_columns:
                            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
                        
                        # Process Excel data in chunks
                        leads_data = []
                        for index, row in df.iterrows():
                            if index >= 100000:  # Safety limit
                                break
                            
                            lead_data = {
                                'name': '' if pd.isna(row.get('name')) else str(row.get('name', '')).strip(),
                                'mobile': '' if pd.isna(row.get('mobile')) else str(row.get('mobile', '')).strip(),
                                'email': '' if pd.isna(row.get('email')) else str(row.get('email', '')).strip(),
                                'alt_mobile': '' if pd.isna(row.get('alt_mobile')) else str(row.get('alt_mobile', '')).strip(),
                                'whatsapp_no': '' if pd.isna(row.get('whatsapp_no')) else str(row.get('whatsapp_no', '')).strip(),
                                'alt_email': '' if pd.isna(row.get('alt_email')) else str(row.get('alt_email', '')).strip(),
                                'address': '' if pd.isna(row.get('address')) else str(row.get('address', '')).strip(),
                                'city': '' if pd.isna(row.get('city')) else str(row.get('city', '')).strip(),
                                'state': '' if pd.isna(row.get('state')) else str(row.get('state', '')).strip(),
                                'postalcode': '' if pd.isna(row.get('postalcode')) else str(row.get('postalcode', '')).strip(),
                                'country': '' if pd.isna(row.get('country')) else str(row.get('country', '')).strip(),
                                'status': '' if pd.isna(row.get('status')) else str(row.get('status', 'lead')).strip() or 'lead',
                                'status_description': '' if pd.isna(row.get('status_description')) else str(row.get('status_description', '')).strip(),
                                'lead_source': '' if pd.isna(row.get('lead_source')) else str(row.get('lead_source', '')).strip(),
                                'lead_source_description': '' if pd.isna(row.get('lead_source_description')) else str(row.get('lead_source_description', '')).strip(),
                                'refered_by': '' if pd.isna(row.get('refered_by')) else str(row.get('refered_by', '')).strip(),
                                'campaign_id': '' if pd.isna(row.get('campaign_id')) else str(row.get('campaign_id', '')).strip(),
                                'course_name': '' if pd.isna(row.get('course_name')) else str(row.get('course_name', '')).strip(),
                                'course_amount': '' if pd.isna(row.get('course_amount')) else str(row.get('course_amount', '')).strip(),
                                'exp_revenue': '' if pd.isna(row.get('exp_revenue')) else str(row.get('exp_revenue', '')).strip(),
                                'description': '' if pd.isna(row.get('description')) else str(row.get('description', '')).strip(),
                                'company': '' if pd.isna(row.get('company')) else str(row.get('company', '')).strip(),
                            }
                            
                            # Add date fields if present
                            if 'exp_close_date' in row and pd.notna(row['exp_close_date']):
                                lead_data['exp_close_date'] = pd.to_datetime(row['exp_close_date']).date()
                            if 'followup_datetime' in row and pd.notna(row['followup_datetime']):
                                lead_data['followup_datetime'] = pd.to_datetime(row['followup_datetime'])
                            if 'birthdate' in row and pd.notna(row['birthdate']):
                                lead_data['birthdate'] = pd.to_datetime(row['birthdate']).date()
                            
                            leads_data.append(lead_data)
                            
                            # PROCESS IN CHUNKS TO SAVE MEMORY
                            if len(leads_data) >= 5000:
                                yield leads_data
                                leads_data = []
                        
                        # PROCESS REMAINING RECORDS
                        if leads_data:
                            yield leads_data
                
                # OPTIMIZED: Process file in streaming mode and collect all leads
                all_leads_data = []
                try:
                    for leads_chunk in process_file_streaming(file):
                        all_leads_data.extend(leads_chunk)
                except Exception as e:
                    return _error_response(f"Error processing file: {str(e)}", form_instance=form)
                
                if not all_leads_data:
                    return _error_response("No valid lead data found in file. Please check file format and required columns.", form_instance=form)
                
                # Initialize duplicate detector
                detector = DuplicateDetector(request.user.company_id)
                
                # Detect duplicates for all leads (now optimized)
                duplicate_results = detector.batch_detect_duplicates(all_leads_data)

                # Build immutable import session for reliable preview/process reconciliation.
                file_hash = hashlib.sha256(file_content).hexdigest()
                idempotency_key = f"{request.user.company_id}:{file_hash}"
                existing_completed = LeadImportSession.objects.filter(
                    company_id=request.user.company_id,
                    idempotency_key=idempotency_key,
                    status='completed',
                ).first()
                if existing_completed:
                    messages.warning(
                        request,
                        "This file appears already processed before "
                        f"(session: {existing_completed.session_id}). "
                        "Continuing with a fresh import session."
                    )

                session_id = f"imp_{uuid.uuid4().hex[:16]}"
                summary = {
                    'total': len(duplicate_results),
                    'new': len([r for r in duplicate_results if r['status'] == 'new']),
                    'exact_duplicates': len([r for r in duplicate_results if r['status'] == 'exact_duplicate']),
                    'potential_duplicates': len([r for r in duplicate_results if r['status'] == 'potential_duplicate']),
                    'related': len([r for r in duplicate_results if r['status'] == 'related']),
                }

                LeadImportSession.objects.create(
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                    user=request.user,
                    company_id=request.user.company_id,
                    file_name=file.name,
                    file_hash=file_hash,
                    status='preview_ready',
                    payload={
                        'duplicate_results': duplicate_results,
                        'summary': summary,
                        'decisions': {},
                    },
                    total_rows=summary['total'],
                    new_rows=summary['new'],
                    exact_duplicates=summary['exact_duplicates'],
                    potential_duplicates=summary['potential_duplicates'],
                    related_rows=summary['related'],
                )

                _create_operation_log(
                    request,
                    operation_type='import_preview',
                    action_scope='all_filtered',
                    scoped_qs=request.hierarchy_context['accessible_leads'].none(),
                    success_count=summary['total'],
                    metadata={'session_id': session_id, 'file_name': file.name},
                    requested_count_override=summary['total'],
                )
                request.session['import_session_id'] = session_id
                
                # Redirect to preview page
                if is_ajax:
                    return JsonResponse({
                        'ok': True,
                        'redirect_url': reverse('dashboard:lead_import_preview')
                    })
                return redirect("dashboard:lead_import_preview")
                
            except Exception as e:
                print(f"Import error: {e}")
                import traceback
                traceback.print_exc()
                return _error_response(
                    f"Error processing file: {str(e)}. Please check file format and encoding.",
                    form_instance=form
                )
        return _error_response("Please upload a valid CSV/XLS/XLSX file.", form_instance=form)
    else:
        form = LeadImportForm()
    
    context = {
        'form': form,
        'page_title': 'Import Leads',
    }
    return render(request, 'dashboard/lead_import.html', context)


@login_required
@hierarchy_required
def lead_import_preview(request):
    """Preview import results with duplicate detection"""
    # Only owners can import leads
    if request.user.role != 'owner':
        messages.error(request, "You don't have permission to import leads. Only owners can import leads.")
        return redirect("dashboard:leads_all")
    
    session_id = request.session.get('import_session_id')
    if not session_id:
        messages.error(request, "No import data found. Please upload a file first.")
        return redirect("dashboard:lead_import")
    import_session = LeadImportSession.objects.filter(
        session_id=session_id,
        company_id=request.user.company_id
    ).first()
    if not import_session:
        messages.error(request, "Import session expired. Please upload file again.")
        return redirect("dashboard:lead_import")

    payload = import_session.payload or {}
    duplicate_results = payload.get('duplicate_results', [])
    summary = payload.get('summary', {})
    file_name = import_session.file_name
    
    # Prepare table data with additional info
    table_data = []
    for result in duplicate_results:
        lead_data = result['lead_data']
        duplicate_items = result['duplicates'][:3] if result.get('duplicates') else []
        row = {
            'row_index': result['row_index'],
            'name': lead_data['name'],
            'mobile': lead_data['mobile'],
            'email': lead_data['email'],
            'status': result['status'],
            'duplicate_type': result['duplicate_type'],
            'confidence': result['confidence'],
            'duplicates': duplicate_items,
            'duplicate_total': len(result.get('duplicates', [])),
            'extra_duplicates_count': max(len(result.get('duplicates', [])) - len(duplicate_items), 0),
            'action': 'import' if result['status'] == 'new' else 'skip',
            'selected': result['status'] == 'new',  # Auto-select new leads
        }
        table_data.append(row)

    # Large imports can create huge HTML payloads and freeze browsers.
    paginator = Paginator(table_data, 200)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_title': 'Import Preview',
        'import_session_id': import_session.session_id,
        'file_name': file_name,
        'summary': summary,
        'table_data': page_obj.object_list,
        'page_obj': page_obj,
        'duplicate_results': duplicate_results,
    }
    
    return render(request, 'dashboard/lead_import_preview.html', context)


@login_required
@hierarchy_required
def lead_import_status(request):
    """Return live import progress for the active import session."""
    if request.user.role != 'owner':
        return JsonResponse({'error': 'Permission denied'}, status=403)

    session_id = request.GET.get('session_id') or request.session.get('import_session_id')
    if not session_id:
        return JsonResponse({'error': 'No import session found'}, status=404)

    import_session = LeadImportSession.objects.filter(
        session_id=session_id,
        company_id=request.user.company_id
    ).first()
    if not import_session:
        return JsonResponse({'error': 'Import session not found'}, status=404)

    total_rows = import_session.total_rows or 0
    processed_rows = (
        (import_session.imported_rows or 0)
        + (import_session.updated_rows or 0)
        + (import_session.skipped_rows or 0)
        + (import_session.failed_rows or 0)
    )
    percent = int((processed_rows / total_rows) * 100) if total_rows > 0 else 0
    if import_session.status == 'completed':
        percent = 100

    return JsonResponse({
        'session_id': import_session.session_id,
        'status': import_session.status,
        'total_rows': total_rows,
        'processed_rows': processed_rows,
        'imported_rows': import_session.imported_rows or 0,
        'updated_rows': import_session.updated_rows or 0,
        'skipped_rows': import_session.skipped_rows or 0,
        'failed_rows': import_session.failed_rows or 0,
        'percent': percent,
    })


@login_required
@hierarchy_required
def lead_import_process(request):
    """Process the import with user decisions on duplicates"""
    # Only owners can import leads
    if request.user.role != 'owner':
        messages.error(request, "You don't have permission to import leads. Only owners can import leads.")
        return redirect("dashboard:leads_all")
    
    if request.method != 'POST':
        return redirect("dashboard:lead_import")
    
    session_id = request.session.get('import_session_id')
    if not session_id:
        messages.error(request, "No import data found. Please upload a file first.")
        return redirect("dashboard:lead_import")

    import_session = LeadImportSession.objects.filter(
        session_id=session_id,
        company_id=request.user.company_id
    ).first()
    if not import_session:
        messages.error(request, "Import session expired. Please upload file again.")
        return redirect("dashboard:lead_import")
    if import_session.status == 'completed':
        messages.warning(request, f"This import session was already processed: {import_session.session_id}")
        return redirect("dashboard:leads_all")

    payload = import_session.payload or {}
    duplicate_results = payload.get('duplicate_results', [])
    
    # Get user decisions
    selected_rows = request.POST.getlist('selected_rows')
    bulk_action_mode = request.POST.get('bulk_action_mode', 'custom').strip().lower()
    decisions = {}
    
    def _create_leads_bulk(lead_data_list, result_list, importing_user, import_session):
        """Bulk create leads for massive performance improvement"""
        from django.db import transaction
        
        # Prepare leads for bulk creation
        leads_to_create = []
        for lead_data, result in zip(lead_data_list, result_list):
            lead = Lead(
                name=lead_data['name'],
                mobile=lead_data['mobile'],
                email=lead_data['email'] if lead_data['email'] else None,
                alt_mobile=lead_data['alt_mobile'] if lead_data['alt_mobile'] else None,
                whatsapp_no=lead_data['whatsapp_no'] if lead_data['whatsapp_no'] else None,
                alt_email=lead_data['alt_email'] if lead_data['alt_email'] else None,
                address=lead_data['address'] if lead_data['address'] else None,
                city=lead_data['city'] if lead_data['city'] else None,
                state=lead_data['state'] if lead_data['state'] else None,
                postalcode=lead_data['postalcode'] if lead_data['postalcode'] else None,
                country=lead_data['country'] if lead_data['country'] else None,
                status=lead_data['status'],
                status_description=lead_data['status_description'] if lead_data['status_description'] else None,
                lead_source=lead_data['lead_source'] if lead_data['lead_source'] else None,
                lead_source_description=lead_data['lead_source_description'] if lead_data['lead_source_description'] else None,
                refered_by=lead_data['refered_by'] if lead_data['refered_by'] else None,
                campaign_id=lead_data['campaign_id'] if lead_data['campaign_id'] else None,
                course_name=lead_data['course_name'] if lead_data['course_name'] else None,
                course_amount=lead_data['course_amount'] if lead_data['course_amount'] else None,
                exp_revenue=lead_data['exp_revenue'] if lead_data['exp_revenue'] else None,
                description=lead_data['description'] if lead_data['description'] else None,
                company_id=importing_user.company_id,
                created_by=importing_user,
                assigned_user=None,  # Leave unassigned by default
                duplicate_status=result['status'],
                duplicate_info=result,
            )
            
            # Handle optional date fields
            if 'exp_close_date' in lead_data:
                lead.exp_close_date = lead_data['exp_close_date']
            if 'followup_datetime' in lead_data:
                lead.followup_datetime = lead_data['followup_datetime']
            if 'birthdate' in lead_data:
                lead.birthdate = lead_data['birthdate']
            
            leads_to_create.append(lead)
        
        # Bulk create leads with transaction safety
        with transaction.atomic():
            created_leads = Lead.objects.bulk_create(leads_to_create, batch_size=1000, ignore_conflicts=True)
            
            # Bulk create activities
            activities_to_create = [
                LeadActivity(
                    lead=lead,
                    user=importing_user,
                    activity_type='import',
                    description=f'Lead imported from {import_session.file_name}'
                )
                for lead in created_leads
            ]
            LeadActivity.objects.bulk_create(activities_to_create, batch_size=1000)
        
        return created_leads
    
    def _process_import_concurrently(duplicate_results, import_session, request):
        """Process import with parallel batch processing for maximum performance"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from django.db import transaction
        
        # Get user decisions
        selected_rows = request.POST.getlist('selected_rows')
        bulk_action_mode = request.POST.get('bulk_action_mode', 'custom').strip().lower()
        
        # Filter leads to import based on user decisions
        leads_to_import = []
        for i, result in enumerate(duplicate_results):
            # Determine action for this row
            if bulk_action_mode == 'import_all':
                action = 'import'
            elif bulk_action_mode == 'import_all_new':
                action = 'import' if result['status'] == 'new' else 'skip'
            else:
                action_field = request.POST.get(f'actions_{i}')
                if action_field is None:
                    action = 'import' if result['status'] == 'new' else 'skip'
                elif str(i) in selected_rows:
                    action = action_field
                else:
                    action = 'skip'
            
            if action == 'import':
                leads_to_import.append((result['lead_data'], result))
        
        # Split into batches for parallel processing
        batch_size = 1000
        batches = [
            leads_to_import[i:i+batch_size] 
            for i in range(0, len(leads_to_import), batch_size)
        ]
        
        imported_count = 0
        failed_count = 0
        
        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_batch = {
                executor.submit(_process_batch_with_transaction, batch, request.user, import_session): batch
                for batch in batches
            }
            
            for future in as_completed(future_to_batch):
                try:
                    batch_result = future.result()
                    imported_count += batch_result['imported']
                except Exception as e:
                    print(f"Batch processing error: {e}")
                    failed_count += len(future_to_batch[future])
        
        return imported_count, 0, 0, failed_count  # imported, skipped, updated, failed
    
    @transaction.atomic
    def _process_batch_with_transaction(batch, user, import_session):
        """Process a single batch with transaction safety"""
        if not batch:
            return {'imported': 0, 'skipped': 0, 'failed': 0}
        
        lead_data_list, result_list = zip(*batch)
        
        # Use the bulk create function
        from django.db import transaction
        with transaction.atomic():
            created_leads = _create_leads_bulk(list(lead_data_list), list(result_list), user, import_session)
        
        return {
            'imported': len(created_leads),
            'skipped': 0,
            'failed': 0
        }
    
    def _create_lead_from_import(lead_data, result, importing_user):
        """Legacy function for backward compatibility - use bulk operations instead"""
        leads = _create_leads_bulk([lead_data], [result], importing_user, import_session)
        return leads[0] if leads else None

    import_session.status = 'processing'
    import_session.save(update_fields=['status', 'updated_at'])

    # OPTIMIZED: Choose processing strategy based on dataset size
    total_leads = len(duplicate_results)
    
    if total_leads > 10000:
        # Use parallel processing for large datasets
        messages.info(request, f"Large dataset detected ({total_leads} leads). Using parallel processing for maximum performance.")
        imported_count, skipped_count, updated_count, failed_count = _process_import_concurrently(
            duplicate_results, import_session, request
        )
    else:
        # Use optimized sequential processing for smaller datasets
        imported_count = 0
        skipped_count = 0
        updated_count = 0
        failed_count = 0
        chunk_size = 5000  # 10X larger chunk size for better performance
        
        # Collect leads for bulk processing
        leads_to_import_batch = []
        results_to_import_batch = []
        
        # Get user decisions for sequential processing
        selected_rows = request.POST.getlist('selected_rows')
        bulk_action_mode = request.POST.get('bulk_action_mode', 'custom').strip().lower()
        decisions = {}
        
        for i, result in enumerate(duplicate_results):
            lead_data = result['lead_data']

            # Global bulk modes override per-row form payload and work across all pages.
            if bulk_action_mode == 'import_all':
                action = 'import'
            elif bulk_action_mode == 'import_all_new':
                action = 'import' if result['status'] == 'new' else 'skip'
            else:
                # With paginated preview, POST only contains rows from visible page.
                # Keep default behavior for rows not present in payload.
                action_field = request.POST.get(f'actions_{i}')
                if action_field is None:
                    action = 'import' if result['status'] == 'new' else 'skip'
                elif str(i) in selected_rows:
                    action = action_field
                else:
                    action = 'skip'
            decisions[str(i)] = action
            
            if action == 'skip':
                skipped_count += 1
                continue
            
            try:
                if action == 'import':
                    # Collect for bulk import processing
                    leads_to_import_batch.append(lead_data)
                    results_to_import_batch.append(result)
                    
                    # Process batch when chunk size reached or at end
                    if len(leads_to_import_batch) >= chunk_size or i == len(duplicate_results) - 1:
                        if leads_to_import_batch:
                            created_leads = _create_leads_bulk(leads_to_import_batch, results_to_import_batch, request.user, import_session)
                            imported_count += len(created_leads)
                            leads_to_import_batch = []
                            results_to_import_batch = []
                
                elif action == 'update' and result['duplicates']:
                    # Update existing lead (most recent duplicate)
                    duplicate_lead = Lead.objects.filter(
                        id_lead__in=[dup['id'] for dup in result['duplicates']]
                    ).order_by('-created_at').first()
                    
                    if duplicate_lead:
                        # Update fields with new data
                        if lead_data['name']:
                            duplicate_lead.name = lead_data['name']
                        if lead_data['email']:
                            duplicate_lead.email = lead_data['email']
                        if lead_data['address']:
                            duplicate_lead.address = lead_data['address']
                        if lead_data['city']:
                            duplicate_lead.city = lead_data['city']
                        if lead_data['state']:
                            duplicate_lead.state = lead_data['state']
                        
                        duplicate_lead.modified_user = request.user
                        duplicate_lead.duplicate_status = 'updated'
                        duplicate_lead.duplicate_info = result
                        duplicate_lead.save()
                        updated_count += 1
                        
                        # Log activity
                        LeadActivity.objects.create(
                            lead=duplicate_lead,
                            user=request.user,
                            activity_type='update',
                            description=f'Lead updated during import from {import_session.file_name}'
                        )
            
            except Exception as e:
                print(f"Error processing lead {i}: {e}")
                failed_count += 1
                continue

            # Persist progress every chunk.
            if (i + 1) % chunk_size == 0:
                import_session.imported_rows = imported_count
                import_session.updated_rows = updated_count
                import_session.skipped_rows = skipped_count
                import_session.failed_rows = failed_count
                import_session.payload = {
                    **payload,
                    'decisions': decisions,
                }
                import_session.save(update_fields=[
                    'imported_rows', 'updated_rows', 'skipped_rows', 'failed_rows',
                    'payload', 'updated_at'
                ])
    
    import_session.status = 'completed'
    import_session.imported_rows = imported_count
    import_session.updated_rows = updated_count
    import_session.skipped_rows = skipped_count
    import_session.failed_rows = failed_count
    import_session.payload = {
        **payload,
        'decisions': decisions,
    }
    import_session.save(update_fields=[
        'status', 'imported_rows', 'updated_rows', 'skipped_rows',
        'failed_rows', 'payload', 'updated_at'
    ])

    _create_operation_log(
        request,
        operation_type='import_process',
        action_scope='all_filtered',
        scoped_qs=request.hierarchy_context['accessible_leads'].none(),
        success_count=imported_count + updated_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        metadata={
            'session_id': import_session.session_id,
            'file_name': import_session.file_name,
            'imported': imported_count,
            'updated': updated_count,
        },
        requested_count_override=len(duplicate_results),
    )

    # Keep only session id; clear active import pointer.
    if 'import_session_id' in request.session:
        del request.session['import_session_id']
    
    # Show results
    completion_summary = (
        f"Import completed. Imported {imported_count}, updated {updated_count}, "
        f"skipped {skipped_count}, failed {failed_count}."
    )
    messages.success(request, completion_summary)

    if imported_count > 0:
        messages.success(request, f"Successfully imported {imported_count} new leads.")
    if updated_count > 0:
        messages.info(request, f"Updated {updated_count} existing leads.")
    if skipped_count > 0:
        messages.warning(request, f"Skipped {skipped_count} leads.")
    if failed_count > 0:
        messages.error(request, f"Failed to process {failed_count} leads. Check operations report for details.")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'ok': True,
            'summary': completion_summary,
            'redirect_url': reverse('dashboard:leads_all'),
            'imported': imported_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'failed': failed_count,
        })

    return redirect("dashboard:leads_all")


# Lead Status and History Views
@login_required
@can_access_lead_required
def lead_status_update(request, pk):
    """Update lead status with history tracking"""
    lead = request.current_lead
    
    # Check if user can modify this lead's status
    if not lead.can_update_status_by(request.user):
        raise PermissionDenied("You don't have permission to update this lead's status.")
    
    if request.method == "POST":
        form = LeadStatusUpdateForm(request.POST, instance=lead)
        if form.is_valid():
            old_status = lead.status
            updated_lead = form.save(commit=False)
            updated_lead.modified_user = request.user
            
            # Create history record if status changed
            if old_status != updated_lead.status:
                LeadHistory.objects.create(
                    lead=lead,
                    user=request.user,
                    field_name='status',
                    old_value=old_status,
                    new_value=updated_lead.status,
                    action='Status Updated'
                )
                
                # Create activity log
                LeadActivity.objects.create(
                    lead=lead,
                    user=request.user,
                    activity_type='status_change',
                    description=(
                        f'Status changed from {old_status} to {updated_lead.status}. '
                        f'{updated_lead.status_description or ""}'
                    ).strip()
                )
            
            updated_lead.save()
            messages.success(request, "Lead status updated successfully.")
            return redirect("dashboard:lead_detail", pk=lead.id_lead)
    else:
        form = LeadStatusUpdateForm(instance=lead)
    
    context = {
        'lead': lead,
        'form': form,
        'page_title': f'Update Status - {lead.name}',
    }
    return render(request, 'dashboard/lead_status_update.html', context)


@login_required
@can_access_lead_required
def lead_history(request, pk):
    """View lead history and assignment tracking"""
    lead = request.current_lead
    
    # Get all history records
    history_records = LeadHistory.objects.filter(lead=lead).order_by('-created_at')
    
    # Parse assignment history from JSON field
    assignment_history = []
    if lead.assignment_history and 'assignments' in lead.assignment_history:
        for assignment in lead.assignment_history['assignments']:
            assignment_history.append({
                'from_user_id': assignment['from']['user'] if assignment['from'].get('user') else None,
                'to_user_id': assignment['to']['user'],
                'assigned_at': assignment['to']['at'],
                'assigned_by_id': assignment['by']
            })
    
    context = {
        'lead': lead,
        'history_records': history_records,
        'assignment_history': assignment_history,
        'page_title': f'Lead History - {lead.name}',
    }
    return render(request, 'dashboard/lead_history.html', context)


# AJAX Views
@login_required
@hierarchy_required
def ajax_get_users_for_assignment(request):
    """Get users that can be assigned leads based on hierarchy"""
    try:
        users = request.user.get_accessible_users().values('id', 'username', 'role', 'first_name', 'last_name')
        users_list = list(users)
        return JsonResponse({'users': users_list})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@hierarchy_required
def ajax_get_available_roles(request):
    """Get available roles for lead assignment based on user hierarchy"""
    if request.method == "GET" and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            # Get available roles based on current user's role
            available_roles = []
            if request.user.role == 'owner':
                available_roles = [
                    {'value': 'manager', 'label': 'Manager'},
                    {'value': 'team_lead', 'label': 'Team Lead'},
                    {'value': 'agent', 'label': 'Agent'},
                ]
            elif request.user.role == 'manager':
                available_roles = [
                    {'value': 'team_lead', 'label': 'Team Lead'},
                    {'value': 'agent', 'label': 'Agent'},
                ]
            elif request.user.role == 'team_lead':
                available_roles = [
                    {'value': 'agent', 'label': 'Agent'},
                ]
            
            return JsonResponse({'roles': available_roles})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
@hierarchy_required
def ajax_bulk_assignment_data(request):
    """Get data for bulk assignment"""
    if request.method == "POST" and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        lead_ids = request.POST.getlist('lead_ids[]')
        
        # Get leads that user can access
        accessible_leads = request.hierarchy_context['accessible_leads'].filter(id_lead__in=lead_ids)
        
        leads_data = []
        for lead in accessible_leads:
            leads_data.append({
                'id': lead.id_lead,
                'name': lead.name,
                'mobile': lead.mobile,
                'current_assignment': lead.assigned_user.username if lead.assigned_user else 'Unassigned'
            })
        
        return JsonResponse({'leads': leads_data, 'total': len(leads_data)})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)


# Duplicate Leads Management Views
@login_required
@hierarchy_required
def leads_duplicates(request):
    """Main duplicate leads list view"""
    # Get pagination parameters
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'pending')
    duplicate_type = request.GET.get('type', '')
    
    # Get paginated duplicate groups
    groups = detector.find_duplicate_groups_paginated(
        status=status_filter,
        duplicate_type=duplicate_type,
        page=page_number,
        page_size=page_size
    )
    
    # Get statistics
    stats = detector.get_duplicate_statistics()
    
    context = {
        'page_obj': groups['page_obj'],
        'groups': groups['page_obj'],
        'stats': stats,
        'status_filter': status_filter,
        'duplicate_type': duplicate_type,
        'page_title': 'Duplicate Leads',
        'current_page_size': page_size,
        'total_groups': groups['total_count'],
        'resolution_status_choices': [
            ('pending', 'Pending'),
            ('resolved', 'Resolved'),
            ('ignored', 'Ignored'),
            ('merged', 'Merged')
        ],
        'duplicate_status_choices': [
            ('exact_duplicate', 'Exact Duplicate'),
            ('potential_duplicate', 'Potential Duplicate')
        ]
    }
    return render(request, 'dashboard/duplicates_list.html', context)


@login_required
@hierarchy_required
def lead_duplicate_detail(request, pk):
    """Detail view for a specific duplicate lead"""
    lead = get_object_or_404(Lead, pk=pk, company_id=request.user.company_id)
    
    # Check if user can access this lead
    if not lead.can_be_accessed_by(request.user):
        raise PermissionDenied("You don't have permission to access this lead.")
    
    # Get duplicate group
    duplicate_group = lead.get_duplicate_group()
    
    # Get reassignment recommendations
    detector = DuplicateDetector(request.user.company_id)
    recommendations = detector.get_reassignment_recommendations(lead.duplicate_group_id) if lead.duplicate_group_id else {}
    
    # Get assignment history
    assignment_history = []
    if lead.assignment_history and 'assignments' in lead.assignment_history:
        for assignment in lead.assignment_history['assignments']:
            from_user_id = assignment['from'].get('user') if assignment.get('from') else None
            to_user_id = assignment['to']['user']
            assigned_by_id = assignment['by']
            
            assignment_history.append({
                'from_user': User.objects.filter(id=from_user_id).first() if from_user_id else None,
                'to_user': User.objects.filter(id=to_user_id).first(),
                'assigned_by': User.objects.filter(id=assigned_by_id).first(),
                'assigned_at': assignment['to']['at'],
                'action': assignment.get('action', 'assignment'),
                'transfer_from': assignment.get('transfer_from'),
                'transfer_by': assignment.get('transfer_by')
            })
    
    # Check if user can modify this lead
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    
    context = {
        'lead': lead,
        'duplicate_group': duplicate_group,
        'recommendations': recommendations,
        'assignment_history': assignment_history,
        'can_modify': can_modify,
        'page_title': f'Duplicate Lead - {lead.name}'
    }
    return render(request, 'dashboard/duplicate_detail.html', context)


@login_required
@hierarchy_required
def lead_duplicate_reassign(request, pk):
    """Reassign a duplicate lead with smart defaults"""
    lead = get_object_or_404(Lead, pk=pk, company_id=request.user.company_id)
    
    # Check if user can assign this lead
    if not lead.can_be_assigned_by(request.user):
        raise PermissionDenied("You don't have permission to reassign this lead.")
    
    if request.method == "POST":
        assigned_user_id = request.POST.get('assigned_user')
        reassign_reason = request.POST.get('reassign_reason', '')
        auto_assign = request.POST.get('auto_assign') == 'on'
        
        try:
            assigned_user = User.objects.get(id=assigned_user_id)
            
            # Check hierarchy validation
            if not lead.can_be_assigned_to_user(assigned_user, request.user):
                messages.error(request, "You cannot assign this lead to the selected user due to hierarchy restrictions.")
                return redirect("dashboard:lead_duplicate_detail", pk=lead.id_lead)
            
            # Assign the lead
            old_user = lead.assigned_user
            lead.assign_to_user(assigned_user, request.user)
            
            # Create assignment history record
            LeadHistory.objects.create(
                lead=lead,
                user=request.user,
                field_name='assigned_user',
                old_value=old_user.username if old_user else None,
                new_value=assigned_user.username,
                action=f'Duplicate reassigned to {assigned_user.username}',
                description=reassign_reason
            )
            
            # Create activity log
            LeadActivity.objects.create(
                lead=lead,
                user=request.user,
                activity_type='duplicate_reassignment',
                description=f'Duplicate lead reassigned to {assigned_user.username}. {reassign_reason}'
            )
            
            # Mark duplicate as resolved if requested
            if request.POST.get('resolve_duplicate') == 'on':
                lead.resolve_duplicate(
                    resolved_by=request.user,
                    resolution_status='resolved',
                    notes=f'Reassigned to {assigned_user.username}. {reassign_reason}'
                )
            
            messages.success(request, f"Duplicate lead successfully reassigned to {assigned_user.username}.")
            return redirect("dashboard:lead_duplicate_detail", pk=lead.id_lead)
            
        except User.DoesNotExist:
            messages.error(request, "Selected user not found.")
        except Exception as e:
            messages.error(request, f"Error reassigning lead: {str(e)}")
    
    # Get reassignment candidates
    candidates = lead.get_reassignment_candidates()
    
    # Get all accessible users for admin override with real-time lead counts
    accessible_users = []
    if request.user.role in ['owner', 'manager']:
        users = request.user.get_accessible_users().filter(account_status='active')
        for user in users:
            # Get real-time lead count for each user
            lead_count = Lead.objects.filter(
                assigned_user=user,
                company_id=request.user.company_id
            ).count()
            accessible_users.append({
                'user': user,
                'lead_count': lead_count
            })
    
    context = {
        'lead': lead,
        'candidates': candidates,
        'accessible_users': accessible_users,
        'page_title': f'Reassign Duplicate - {lead.name}'
    }
    return render(request, 'dashboard/duplicate_reassign.html', context)


@login_required
@hierarchy_required
def bulk_duplicate_reassign(request):
    """Bulk reassign duplicate leads"""
    if request.method == "POST":
        group_ids = request.POST.getlist('group_ids')
        assigned_user_id = request.POST.get('assigned_user')
        reassign_reason = request.POST.get('reassign_reason', '')
        resolve_duplicates = request.POST.get('resolve_duplicates') == 'on'
        
        if not group_ids:
            messages.error(request, "No duplicate groups selected.")
            return redirect("dashboard:leads_duplicates")
        
        try:
            assigned_user = User.objects.get(id=assigned_user_id)
            
            # Get all leads in selected groups
            leads = Lead.objects.filter(
                duplicate_group_id__in=group_ids,
                company_id=request.user.company_id
            )
            
            # Use optimized bulk duplicate reassignment
            successful_assignments, failed_assignments = _bulk_reassign_duplicates_optimized(
                leads, assigned_user, request.user, reassign_reason, resolve_duplicates
            )
            
            if successful_assignments > 0:
                messages.success(request, f"Successfully reassigned {successful_assignments} duplicate leads to {assigned_user.username}.")
            if failed_assignments > 0:
                messages.warning(request, f"Failed to reassign {failed_assignments} leads due to permission restrictions.")
            
            return redirect("dashboard:leads_duplicates")
            
        except User.DoesNotExist:
            messages.error(request, "Selected user not found.")
        except Exception as e:
            messages.error(request, f"Error in bulk reassignment: {str(e)}")
    
    # Get duplicate groups for selection
    detector = DuplicateDetector(request.user.company_id)
    groups = detector.find_duplicate_groups('pending')
    
    # Get accessible users with real-time lead counts
    accessible_users = []
    if request.user.role in ['owner', 'manager']:
        users = request.user.get_accessible_users().filter(account_status='active')
        for user in users:
            # Get real-time lead count for each user
            lead_count = Lead.objects.filter(
                assigned_user=user,
                company_id=request.user.company_id
            ).count()
            accessible_users.append({
                'user': user,
                'lead_count': lead_count
            })
    
    context = {
        'groups': groups,
        'accessible_users': accessible_users,
        'page_title': 'Bulk Reassign Duplicates'
    }
    return render(request, 'dashboard/bulk_duplicate_reassign.html', context)


@login_required
@hierarchy_required
def team_duplicate_leads(request):
    """Team-specific duplicate leads view"""
    # Get pagination parameters
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get paginated duplicate groups based on user role
    detector = DuplicateDetector(request.user.company_id)
    groups = detector.find_duplicate_groups_paginated(
        page=page_number,
        page_size=page_size,
        user_role=request.user.role,
        user=request.user
    )
    
    # Get team statistics (limited to current page for performance)
    team_stats = {}
    if request.user.role in ['owner', 'manager']:
        team_users = request.user.get_accessible_users() if request.user.role == 'manager' else User.objects.filter(company_id=request.user.company_id)
        
        # Get statistics for current page only
        current_groups = groups['page_obj'].object_list
        for user in team_users:
            user_groups = []
            for group in current_groups:
                if any(lead.assigned_user == user for lead in group['leads']):
                    user_groups.append(group)
            
            team_stats[user.username] = {
                'groups_count': len(user_groups),
                'leads_count': sum(len(group['leads']) for group in user_groups),
                'pending_count': len([g for g in user_groups if g['status'] == 'pending']),
                'resolved_count': len([g for g in user_groups if g['status'] == 'resolved'])
            }
    
    context = {
        'page_obj': groups['page_obj'],
        'groups': groups['page_obj'],
        'team_stats': team_stats,
        'page_title': 'Team Duplicate Leads',
        'current_page_size': page_size,
        'total_groups': groups['total_count'],
        'show_team_stats': request.user.role in ['owner', 'manager']
    }
    return render(request, 'dashboard/team_duplicates.html', context)


@login_required
@hierarchy_required
def my_duplicate_leads(request):
    """Current user's duplicate leads"""
    # Get pagination parameters
    page_number = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get paginated groups for current user
    detector = DuplicateDetector(request.user.company_id)
    groups = detector.find_duplicate_groups_paginated(
        page=page_number,
        page_size=page_size,
        user_role='agent',
        user=request.user
    )
    
    # Get user's duplicate statistics
    user_leads = Lead.objects.filter(
        assigned_user=request.user,
        duplicate_status__in=['exact_duplicate', 'potential_duplicate']
    )
    
    user_stats = {
        'total_duplicate_leads': user_leads.count(),
        'exact_duplicates': user_leads.filter(duplicate_status='exact_duplicate').count(),
        'potential_duplicates': user_leads.filter(duplicate_status='potential_duplicate').count(),
        'pending_duplicates': user_leads.filter(duplicate_resolution_status='pending').count(),
        'resolved_duplicates': user_leads.filter(duplicate_resolution_status='resolved').count(),
        'groups_count': groups['total_count']  # Use total count from paginated result
    }
    
    context = {
        'page_obj': groups['page_obj'],
        'groups': groups['page_obj'],
        'my_stats': user_stats,
        'page_title': 'My Duplicate Leads',
        'current_page_size': page_size,
        'total_groups': groups['total_count']
    }
    return render(request, 'dashboard/my_duplicates.html', context)


# ============================================================================
# BULK OPERATIONS OPTIMIZATION FUNCTIONS
# ============================================================================

def _validate_bulk_assignments_optimized(leads, user, target_user):
    """Batch validate assignment permissions to eliminate individual checks"""
    # Pre-fetch user hierarchy data once
    user_hierarchy = user.get_hierarchy_data()
    target_hierarchy = target_user.get_hierarchy_data()
    
    # Batch validate using set operations and pre-computed permissions
    valid_assignments = []
    for lead in leads:
        # Use cached permission checks instead of individual queries
        if _can_assign_lead_cached(lead, user, user_hierarchy) and \
           _can_be_assigned_to_user_cached(lead, target_user, target_hierarchy):
            valid_assignments.append(lead)
    
    return valid_assignments


def _can_assign_lead_cached(lead, user, user_hierarchy):
    """Cached version of can_be_assigned_by permission check"""
    # Cache key includes lead, user, and hierarchy version
    cache_key = f"can_assign_{lead.id_lead}_{user.id}_{user_hierarchy.get('version', 0)}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Compute permission and cache for 5 minutes
    can_assign = lead.can_be_assigned_by(user)
    cache.set(cache_key, can_assign, 300)
    
    return can_assign


def _can_be_assigned_to_user_cached(lead, target_user, target_hierarchy):
    """Cached version of can_be_assigned_to_user permission check"""
    # Cache key includes lead, target user, and hierarchy version
    cache_key = f"can_assign_to_{lead.id_lead}_{target_user.id}_{target_hierarchy.get('version', 0)}"
    
    # Try cache first
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result
    
    # Compute permission and cache for 5 minutes
    can_assign = lead.can_be_assigned_to_user(target_user, target_user)
    cache.set(cache_key, can_assign, 300)
    
    return can_assign


def _process_assignments_concurrently(leads, assigned_user, request_user, assignment_notes="", batch_size=1000):
    """Process lead assignments in parallel batches"""
    start_time = time.time()
    
    # Validate permissions in batch first
    valid_leads = _validate_bulk_assignments_optimized(leads, request_user, assigned_user)
    failed_count = len(leads) - len(valid_leads)
    
    if not valid_leads:
        return 0, failed_count
    
    # Split into batches for parallel processing
    batches = [valid_leads[i:i+batch_size] for i in range(0, len(valid_leads), batch_size)]
    
    successful_count = 0
    
    # Process batches concurrently
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_batch = {
            executor.submit(_process_assignment_batch, batch, assigned_user, request_user, assignment_notes): batch
            for batch in batches
        }
        
        for future in as_completed(future_to_batch):
            try:
                batch_result = future.result()
                successful_count += batch_result
            except Exception as e:
                # Log error and count as failed
                failed_count += len(future_to_batch[future])
    
    elapsed_time = time.time() - start_time
    logger.info(f"Processed {len(valid_leads)} assignments in {elapsed_time:.2f}s using {len(batches)} batches")
    
    return successful_count, failed_count


@transaction.atomic
def _process_assignment_batch(leads, assigned_user, request_user, assignment_notes=""):
    """Process a single batch of assignments with bulk operations"""
    if not leads:
        return 0
    
    # Prepare bulk update data
    leads_to_update = []
    history_data = []
    activity_data = []
    
    for lead in leads:
        # Store old user for history
        old_user = lead.assigned_user
        
        # Update lead assignment fields
        lead.assigned_user = assigned_user
        lead.assigned_by = request_user
        lead.assigned_at = timezone.now()
        
        # Handle transfer fields
        if old_user and old_user != assigned_user:
            lead.transfer_from = old_user.get_full_name() or old_user.username
            lead.transfer_by = request_user.get_full_name() or request_user.username
            lead.transfer_date = timezone.now()
        
        leads_to_update.append(lead)
        
        # Prepare history data
        history_data.append(LeadHistory(
            lead=lead,
            user=request_user,
            field_name='assigned_user',
            old_value=old_user.username if old_user else None,
            new_value=assigned_user.username,
            action=f'Bulk assigned to {assigned_user.username}'
        ))
        
        # Prepare activity data
        description = f'Bulk assigned to {assigned_user.username}'
        if assignment_notes:
            description += f'. {assignment_notes}'
        
        activity_data.append(LeadActivity(
            lead=lead,
            user=request_user,
            activity_type='bulk_assignment',
            description=description
        ))
    
    # Execute bulk operations
    Lead.objects.bulk_update(leads_to_update, [
        'assigned_user', 'assigned_by', 'assigned_at', 
        'transfer_from', 'transfer_by', 'transfer_date'
    ])
    
    LeadHistory.objects.bulk_create(history_data, batch_size=500)
    LeadActivity.objects.bulk_create(activity_data, batch_size=500)
    
    return len(leads_to_update)


def _bulk_delete_optimized(leads, request_user):
    """Optimized bulk delete with direct bulk operations"""
    if not leads:
        return 0
    
    # Filter out already deleted leads in one query
    lead_ids = [lead.id_lead for lead in leads]
    leads_to_delete = Lead.objects.filter(
        id_lead__in=lead_ids,
        deleted=False
    )
    
    # Direct bulk update without individual processing
    update_count = leads_to_delete.update(
        deleted=True,
        modified_user=request_user
    )
    
    if update_count > 0:
        # Bulk create activities
        activity_data = [
            LeadActivity(
                lead_id=lead_id,
                user=request_user,
                activity_type='delete',
                description='Lead deleted from leads list (bulk action).'
            )
            for lead_id in leads_to_delete.values_list('id_lead', flat=True)
        ]
        
        LeadActivity.objects.bulk_create(activity_data, batch_size=500)
    
    return update_count


def _bulk_reassign_duplicates_optimized(leads, assigned_user, request_user, reassign_reason="", resolve_duplicates=False):
    """Optimized bulk duplicate reassignment"""
    # Batch validate permissions
    valid_leads = _validate_bulk_assignments_optimized(leads, request_user, assigned_user)
    failed_count = len(leads) - len(valid_leads)
    
    if not valid_leads:
        return 0, failed_count
    
    # Separate by duplicate resolution needs
    to_reassign = []
    to_resolve = []
    
    for lead in valid_leads:
        if lead.duplicate_status in ['exact_duplicate', 'potential_duplicate']:
            to_resolve.append(lead)
        else:
            to_reassign.append(lead)
    
    successful_count = 0
    
    # Bulk reassign regular duplicates
    if to_reassign:
        reassign_success = _process_assignments_concurrently(
            to_reassign, assigned_user, request_user, reassign_reason
        )
        successful_count += reassign_success[0]
        failed_count += reassign_success[1]
    
    # Bulk resolve exact duplicates
    if to_resolve:
        resolve_success = _bulk_resolve_duplicates(to_resolve, assigned_user, request_user, reassign_reason)
        successful_count += resolve_success
    
    return successful_count, failed_count


@transaction.atomic
def _bulk_resolve_duplicates(leads, assigned_user, request_user, reassign_reason=""):
    """Bulk resolve duplicate leads"""
    if not leads:
        return 0
    
    lead_ids = [lead.id_lead for lead in leads]
    
    # Bulk update duplicate resolution
    update_count = Lead.objects.filter(id_lead__in=lead_ids).update(
        assigned_user_id=assigned_user.id,
        assigned_by_id=request_user.id,
        assigned_at=timezone.now(),
        duplicate_status='resolved',
        duplicate_resolution_status='resolved',
        status_description=f'Bulk reassigned to {assigned_user.username}'
    )
    
    if update_count > 0:
        # Bulk create resolution activities
        description = f'Bulk duplicate reassigned to {assigned_user.username}'
        if reassign_reason:
            description += f'. {reassign_reason}'
        
        activity_data = [
            LeadActivity(
                lead_id=lead_id,
                user=request_user,
                activity_type='bulk_duplicate_reassignment',
                description=description
            )
            for lead_id in lead_ids
        ]
        
        LeadActivity.objects.bulk_create(activity_data, batch_size=500)
    
    return update_count

@ l o g i n _ r e q u i r e d  
 @ h i e r a r c h y _ r e q u i r e d  
 d e f   l e a d _ i m p o r t _ a j a x ( r e q u e s t ) :  
         " " " A J A X   e n d p o i n t   f o r   m o d a l - b a s e d   l e a d   i m p o r t   w i t h   p r o g r e s s   t r a c k i n g " " "  
         i f   r e q u e s t . u s e r . r o l e   ! =   ' o w n e r ' :  
                 r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' P e r m i s s i o n   d e n i e d .   O n l y   o w n e r s   c a n   i m p o r t   l e a d s . ' } ,   s t a t u s = 4 0 3 )  
          
         i f   r e q u e s t . m e t h o d   ! =   ' P O S T ' :  
                 r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' I n v a l i d   r e q u e s t   m e t h o d ' } ,   s t a t u s = 4 0 5 )  
          
         a c t i o n   =   r e q u e s t . P O S T . g e t ( ' a c t i o n ' ,   ' p r e v i e w ' )  
          
         i f   a c t i o n   = =   ' p r e v i e w ' :  
                 r e t u r n   h a n d l e _ i m p o r t _ p r e v i e w ( r e q u e s t )  
         e l i f   a c t i o n   = =   ' i m p o r t ' :  
                 r e t u r n   h a n d l e _ i m p o r t _ s t a r t ( r e q u e s t )  
         e l s e :  
                 r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' I n v a l i d   a c t i o n ' } ,   s t a t u s = 4 0 0 )  
  
  
 d e f   h a n d l e _ i m p o r t _ p r e v i e w ( r e q u e s t ) :  
         " " " H a n d l e   f i l e   p r e v i e w   f o r   i m p o r t   m o d a l " " "  
         t r y :  
                 f i l e   =   r e q u e s t . F I L E S . g e t ( ' f i l e ' )  
                 i f   n o t   f i l e :  
                         r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' N o   f i l e   p r o v i d e d ' } )  
                  
                 #   R e a d   f i l e   c o n t e n t  
                 f i l e _ c o n t e n t   =   f i l e . r e a d ( )  
                 i f   n o t   f i l e _ c o n t e n t . s t r i p ( ) :  
                         r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' F i l e   i s   e m p t y ' } )  
                  
                 f i l e . s e e k ( 0 )  
                  
                 #   P r o c e s s   f i l e   b a s e d   o n   t y p e  
                 i f   f i l e . n a m e . e n d s w i t h ( ' . c s v ' ) :  
                         l e a d s _ d a t a ,   h e a d e r s   =   p r o c e s s _ c s v _ p r e v i e w ( f i l e )  
                 e l s e :  
                         #   F o r   E x c e l   f i l e s ,   u s e   p a n d a s  
                         l e a d s _ d a t a ,   h e a d e r s   =   p r o c e s s _ e x c e l _ p r e v i e w ( f i l e )  
                  
                 #   D e t e c t   d u p l i c a t e s  
                 d e t e c t o r   =   D u p l i c a t e D e t e c t o r ( r e q u e s t . u s e r . c o m p a n y _ i d )  
                 d u p l i c a t e _ r e s u l t s   =   d e t e c t o r . b a t c h _ d e t e c t _ d u p l i c a t e s ( l e a d s _ d a t a )  
                  
                 #   P r e p a r e   p r e v i e w   d a t a   ( f i r s t   1 0   r o w s )  
                 p r e v i e w _ d a t a   =   [ ]  
                 f o r   i ,   l e a d _ d a t a   i n   e n u m e r a t e ( l e a d s _ d a t a [ : 1 0 ] ) :  
                         p r e v i e w _ d a t a . a p p e n d ( l e a d _ d a t a )  
                  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' h e a d e r s ' :   h e a d e r s ,  
                         ' p r e v i e w ' :   p r e v i e w _ d a t a ,  
                         ' t o t a l _ r e c o r d s ' :   l e n ( l e a d s _ d a t a ) ,  
                         ' d u p l i c a t e s ' :   l e n ( d u p l i c a t e _ r e s u l t s . g e t ( ' d u p l i c a t e s ' ,   [ ] ) ) ,  
                         ' d u p l i c a t e _ d e t a i l s ' :   d u p l i c a t e _ r e s u l t s . g e t ( ' d u p l i c a t e s ' ,   [ ] ) [ : 5 ]     #   F i r s t   5   d u p l i c a t e s  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 l o g g e r . e r r o r ( f " I m p o r t   p r e v i e w   e r r o r :   { s t r ( e ) } " )  
                 r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   f ' P r e v i e w   f a i l e d :   { s t r ( e ) } ' } )  
  
  
 d e f   p r o c e s s _ c s v _ p r e v i e w ( f i l e ) :  
         " " " P r o c e s s   C S V   f i l e   f o r   p r e v i e w " " "  
         f r o m   i o   i m p o r t   T e x t I O W r a p p e r  
          
         #   T r y   d i f f e r e n t   e n c o d i n g s  
         e n c o d i n g s   =   [ ' u t f - 8 ' ,   ' u t f - 8 - s i g ' ,   ' l a t i n - 1 ' ,   ' c p 1 2 5 2 ' ]  
         r e a d e r   =   N o n e  
          
         f o r   e n c o d i n g   i n   e n c o d i n g s :  
                 t r y :  
                         f i l e . s e e k ( 0 )  
                         t e x t _ f i l e   =   T e x t I O W r a p p e r ( f i l e ,   e n c o d i n g = e n c o d i n g )  
                         r e a d e r   =   c s v . D i c t R e a d e r ( t e x t _ f i l e )  
                         b r e a k  
                 e x c e p t   U n i c o d e D e c o d e E r r o r :  
                         c o n t i n u e  
          
         i f   n o t   r e a d e r :  
                 r a i s e   V a l u e E r r o r ( " U n a b l e   t o   r e a d   C S V   f i l e   w i t h   a n y   s u p p o r t e d   e n c o d i n g " )  
          
         #   G e t   h e a d e r s  
         h e a d e r s   =   l i s t ( r e a d e r . f i e l d n a m e s )   i f   r e a d e r . f i e l d n a m e s   e l s e   [ ]  
          
         #   P r o c e s s   d a t a  
         l e a d s _ d a t a   =   [ ]  
         f o r   r o w _ n u m ,   r o w   i n   e n u m e r a t e ( r e a d e r ) :  
                 i f   r o w _ n u m   > =   1 0 0 0 :     #   L i m i t   p r e v i e w   t o   1 0 0 0   r e c o r d s  
                         b r e a k  
                  
                 l e a d _ d a t a   =   {  
                         ' n a m e ' :   r o w . g e t ( ' n a m e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' m o b i l e ' :   r o w . g e t ( ' m o b i l e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' e m a i l ' :   r o w . g e t ( ' e m a i l ' ,   ' ' ) . s t r i p ( ) ,  
                         ' a l t _ m o b i l e ' :   r o w . g e t ( ' a l t _ m o b i l e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' w h a t s a p p _ n o ' :   r o w . g e t ( ' w h a t s a p p _ n o ' ,   ' ' ) . s t r i p ( ) ,  
                         ' a l t _ e m a i l ' :   r o w . g e t ( ' a l t _ e m a i l ' ,   ' ' ) . s t r i p ( ) ,  
                         ' a d d r e s s ' :   r o w . g e t ( ' a d d r e s s ' ,   ' ' ) . s t r i p ( ) ,  
                         ' c i t y ' :   r o w . g e t ( ' c i t y ' ,   ' ' ) . s t r i p ( ) ,  
                         ' s t a t e ' :   r o w . g e t ( ' s t a t e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' p o s t a l c o d e ' :   r o w . g e t ( ' p o s t a l c o d e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' c o u n t r y ' :   r o w . g e t ( ' c o u n t r y ' ,   ' ' ) . s t r i p ( ) ,  
                         ' s t a t u s ' :   r o w . g e t ( ' s t a t u s ' ,   ' l e a d ' ) . s t r i p ( )   o r   ' l e a d ' ,  
                         ' s t a t u s _ d e s c r i p t i o n ' :   r o w . g e t ( ' s t a t u s _ d e s c r i p t i o n ' ,   ' ' ) . s t r i p ( ) ,  
                         ' l e a d _ s o u r c e ' :   r o w . g e t ( ' l e a d _ s o u r c e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' l e a d _ s o u r c e _ d e s c r i p t i o n ' :   r o w . g e t ( ' l e a d _ s o u r c e _ d e s c r i p t i o n ' ,   ' ' ) . s t r i p ( ) ,  
                         ' r e f e r e d _ b y ' :   r o w . g e t ( ' r e f e r e d _ b y ' ,   ' ' ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ n a m e ' :   r o w . g e t ( ' c a m p a i g n _ n a m e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ m e d i u m ' :   r o w . g e t ( ' c a m p a i g n _ m e d i u m ' ,   ' ' ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ s o u r c e ' :   r o w . g e t ( ' c a m p a i g n _ s o u r c e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' n o t e s ' :   r o w . g e t ( ' n o t e s ' ,   ' ' ) . s t r i p ( ) ,  
                         ' b u d g e t ' :   r o w . g e t ( ' b u d g e t ' ,   ' ' ) . s t r i p ( ) ,  
                         ' r e q u i r e m e n t ' :   r o w . g e t ( ' r e q u i r e m e n t ' ,   ' ' ) . s t r i p ( ) ,  
                         ' f o l l o w _ u p _ d a t e ' :   r o w . g e t ( ' f o l l o w _ u p _ d a t e ' ,   ' ' ) . s t r i p ( ) ,  
                         ' r o w _ n u m ' :   r o w _ n u m   +   2     #   + 2   f o r   C S V   ( 1   f o r   h e a d e r ,   1   f o r   0 - b a s e d )  
                 }  
                 l e a d s _ d a t a . a p p e n d ( l e a d _ d a t a )  
          
         r e t u r n   l e a d s _ d a t a ,   h e a d e r s  
  
  
 d e f   p r o c e s s _ e x c e l _ p r e v i e w ( f i l e ) :  
         " " " P r o c e s s   E x c e l   f i l e   f o r   p r e v i e w " " "  
         #   R e a d   E x c e l   f i l e  
         d f   =   p d . r e a d _ e x c e l ( f i l e )  
          
         #   N o r m a l i z e   c o l u m n   n a m e s  
         d f . c o l u m n s   =   [ s t r ( c o l ) . s t r i p ( ) . l o w e r ( )   f o r   c o l   i n   d f . c o l u m n s ]  
          
         #   V a l i d a t e   r e q u i r e d   c o l u m n s  
         r e q u i r e d _ c o l u m n s   =   [ ' n a m e ' ,   ' m o b i l e ' ]  
         m i s s i n g _ c o l u m n s   =   [ c o l   f o r   c o l   i n   r e q u i r e d _ c o l u m n s   i f   c o l   n o t   i n   d f . c o l u m n s ]  
          
         i f   m i s s i n g _ c o l u m n s :  
                 r a i s e   V a l u e E r r o r ( f " M i s s i n g   r e q u i r e d   c o l u m n s :   { ' ,   ' . j o i n ( m i s s i n g _ c o l u m n s ) } " )  
          
         #   C o n v e r t   t o   l i s t   o f   d i c t i o n a r i e s  
         l e a d s _ d a t a   =   [ ]  
         f o r   i n d e x ,   r o w   i n   d f . i t e r r o w s ( ) :  
                 i f   i n d e x   > =   1 0 0 0 :     #   L i m i t   p r e v i e w   t o   1 0 0 0   r e c o r d s  
                         b r e a k  
                  
                 l e a d _ d a t a   =   {  
                         ' n a m e ' :   s t r ( r o w . g e t ( ' n a m e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' m o b i l e ' :   s t r ( r o w . g e t ( ' m o b i l e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' e m a i l ' :   s t r ( r o w . g e t ( ' e m a i l ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' a l t _ m o b i l e ' :   s t r ( r o w . g e t ( ' a l t _ m o b i l e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' w h a t s a p p _ n o ' :   s t r ( r o w . g e t ( ' w h a t s a p p _ n o ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' a l t _ e m a i l ' :   s t r ( r o w . g e t ( ' a l t _ e m a i l ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' a d d r e s s ' :   s t r ( r o w . g e t ( ' a d d r e s s ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' c i t y ' :   s t r ( r o w . g e t ( ' c i t y ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' s t a t e ' :   s t r ( r o w . g e t ( ' s t a t e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' p o s t a l c o d e ' :   s t r ( r o w . g e t ( ' p o s t a l c o d e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' c o u n t r y ' :   s t r ( r o w . g e t ( ' c o u n t r y ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' s t a t u s ' :   s t r ( r o w . g e t ( ' s t a t u s ' ,   ' l e a d ' ) ) . s t r i p ( )   o r   ' l e a d ' ,  
                         ' s t a t u s _ d e s c r i p t i o n ' :   s t r ( r o w . g e t ( ' s t a t u s _ d e s c r i p t i o n ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' l e a d _ s o u r c e ' :   s t r ( r o w . g e t ( ' l e a d _ s o u r c e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' l e a d _ s o u r c e _ d e s c r i p t i o n ' :   s t r ( r o w . g e t ( ' l e a d _ s o u r c e _ d e s c r i p t i o n ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' r e f e r e d _ b y ' :   s t r ( r o w . g e t ( ' r e f e r e d _ b y ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ n a m e ' :   s t r ( r o w . g e t ( ' c a m p a i g n _ n a m e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ m e d i u m ' :   s t r ( r o w . g e t ( ' c a m p a i g n _ m e d i u m ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' c a m p a i g n _ s o u r c e ' :   s t r ( r o w . g e t ( ' c a m p a i g n _ s o u r c e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' n o t e s ' :   s t r ( r o w . g e t ( ' n o t e s ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' b u d g e t ' :   s t r ( r o w . g e t ( ' b u d g e t ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' r e q u i r e m e n t ' :   s t r ( r o w . g e t ( ' r e q u i r e m e n t ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' f o l l o w _ u p _ d a t e ' :   s t r ( r o w . g e t ( ' f o l l o w _ u p _ d a t e ' ,   ' ' ) ) . s t r i p ( ) ,  
                         ' r o w _ n u m ' :   i n d e x   +   2     #   + 2   f o r   E x c e l   ( 1   f o r   h e a d e r ,   1   f o r   0 - b a s e d )  
                 }  
                 l e a d s _ d a t a . a p p e n d ( l e a d _ d a t a )  
          
         h e a d e r s   =   l i s t ( d f . c o l u m n s )  
         r e t u r n   l e a d s _ d a t a ,   h e a d e r s  
  
  
 d e f   h a n d l e _ i m p o r t _ s t a r t ( r e q u e s t ) :  
         " " " H a n d l e   s t a r t i n g   t h e   i m p o r t   p r o c e s s " " "  
         t r y :  
                 f i l e   =   r e q u e s t . F I L E S . g e t ( ' f i l e ' )  
                 i f   n o t   f i l e :  
                         r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   ' N o   f i l e   p r o v i d e d ' } )  
                  
                 #   C r e a t e   i m p o r t   s e s s i o n  
                 f i l e _ h a s h   =   h a s h l i b . s h a 2 5 6 ( f i l e . r e a d ( ) ) . h e x d i g e s t ( )  
                 f i l e . s e e k ( 0 )  
                  
                 i m p o r t _ s e s s i o n   =   L e a d I m p o r t S e s s i o n . o b j e c t s . c r e a t e (  
                         c o m p a n y _ i d = r e q u e s t . u s e r . c o m p a n y _ i d ,  
                         u s e r = r e q u e s t . u s e r ,  
                         f i l e _ n a m e = f i l e . n a m e ,  
                         f i l e _ h a s h = f i l e _ h a s h ,  
                         s t a t u s = ' p r o c e s s i n g ' ,  
                         t o t a l _ r e c o r d s = 0 ,  
                         p r o c e s s e d _ r e c o r d s = 0 ,  
                         s u c c e s s f u l _ r e c o r d s = 0 ,  
                         f a i l e d _ r e c o r d s = 0 ,  
                         d u p l i c a t e _ h a n d l i n g = r e q u e s t . P O S T . g e t ( ' d u p l i c a t e _ h a n d l i n g ' ,   ' s k i p ' ) ,  
                         a s s i g n _ t o = r e q u e s t . P O S T . g e t ( ' a s s i g n _ t o ' ,   ' m e ' )  
                 )  
                  
                 #   S t a r t   a s y n c   i m p o r t   p r o c e s s i n g   ( f o r   n o w ,   p r o c e s s   s y n c h r o n o u s l y )  
                 #   I n   p r o d u c t i o n ,   t h i s   s h o u l d   b e   m o v e d   t o   C e l e r y   o r   s i m i l a r  
                 f r o m   t h r e a d i n g   i m p o r t   T h r e a d  
                  
                 d e f   p r o c e s s _ i m p o r t _ a s y n c ( ) :  
                         t r y :  
                                 p r o c e s s _ i m p o r t _ j o b ( i m p o r t _ s e s s i o n . i d ,   f i l e ,   r e q u e s t )  
                         e x c e p t   E x c e p t i o n   a s   e :  
                                 l o g g e r . e r r o r ( f " A s y n c   i m p o r t   e r r o r :   { s t r ( e ) } " )  
                                 i m p o r t _ s e s s i o n . s t a t u s   =   ' f a i l e d '  
                                 i m p o r t _ s e s s i o n . e r r o r _ m e s s a g e   =   s t r ( e )  
                                 i m p o r t _ s e s s i o n . s a v e ( )  
                  
                 #   S t a r t   p r o c e s s i n g   i n   b a c k g r o u n d  
                 t h r e a d   =   T h r e a d ( t a r g e t = p r o c e s s _ i m p o r t _ a s y n c )  
                 t h r e a d . d a e m o n   =   T r u e  
                 t h r e a d . s t a r t ( )  
                  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s u c c e s s ' :   T r u e ,  
                         ' s e s s i o n _ i d ' :   i m p o r t _ s e s s i o n . i d  
                 } )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 l o g g e r . e r r o r ( f " I m p o r t   s t a r t   e r r o r :   { s t r ( e ) } " )  
                 r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   F a l s e ,   ' e r r o r ' :   f ' I m p o r t   f a i l e d   t o   s t a r t :   { s t r ( e ) } ' } )  
  
  
 d e f   p r o c e s s _ i m p o r t _ j o b ( s e s s i o n _ i d ,   f i l e ,   r e q u e s t ) :  
         " " " P r o c e s s   t h e   a c t u a l   i m p o r t   j o b " " "  
         i m p o r t _ s e s s i o n   =   L e a d I m p o r t S e s s i o n . o b j e c t s . g e t ( i d = s e s s i o n _ i d )  
          
         t r y :  
                 #   P r o c e s s   f i l e  
                 f i l e . s e e k ( 0 )  
                 i f   f i l e . n a m e . e n d s w i t h ( ' . c s v ' ) :  
                         l e a d s _ d a t a ,   _   =   p r o c e s s _ c s v _ p r e v i e w ( f i l e )  
                 e l s e :  
                         l e a d s _ d a t a ,   _   =   p r o c e s s _ e x c e l _ p r e v i e w ( f i l e )  
                  
                 i m p o r t _ s e s s i o n . t o t a l _ r e c o r d s   =   l e n ( l e a d s _ d a t a )  
                 i m p o r t _ s e s s i o n . s a v e ( )  
                  
                 #   P r o c e s s   l e a d s   i n   b a t c h e s  
                 b a t c h _ s i z e   =   1 0 0  
                 p r o c e s s e d _ c o u n t   =   0  
                 s u c c e s s _ c o u n t   =   0  
                 e r r o r _ c o u n t   =   0  
                 e r r o r _ d e t a i l s   =   [ ]  
                  
                 d e t e c t o r   =   D u p l i c a t e D e t e c t o r ( r e q u e s t . u s e r . c o m p a n y _ i d )  
                  
                 f o r   i   i n   r a n g e ( 0 ,   l e n ( l e a d s _ d a t a ) ,   b a t c h _ s i z e ) :  
                         b a t c h   =   l e a d s _ d a t a [ i : i   +   b a t c h _ s i z e ]  
                          
                         f o r   l e a d _ d a t a   i n   b a t c h :  
                                 t r y :  
                                         #   H a n d l e   d u p l i c a t e s  
                                         d u p l i c a t e _ r e s u l t   =   d e t e c t o r . d e t e c t _ s i n g l e _ d u p l i c a t e ( l e a d _ d a t a )  
                                          
                                         i f   d u p l i c a t e _ r e s u l t   a n d   i m p o r t _ s e s s i o n . d u p l i c a t e _ h a n d l i n g   = =   ' s k i p ' :  
                                                 e r r o r _ c o u n t   + =   1  
                                                 c o n t i n u e  
                                         e l i f   d u p l i c a t e _ r e s u l t   a n d   i m p o r t _ s e s s i o n . d u p l i c a t e _ h a n d l i n g   = =   ' u p d a t e ' :  
                                                 #   U p d a t e   e x i s t i n g   l e a d  
                                                 e x i s t i n g _ l e a d   =   d u p l i c a t e _ r e s u l t [ 0 ]  
                                                 u p d a t e _ l e a d _ f r o m _ i m p o r t ( e x i s t i n g _ l e a d ,   l e a d _ d a t a )  
                                                 s u c c e s s _ c o u n t   + =   1  
                                         e l s e :  
                                                 #   C r e a t e   n e w   l e a d  
                                                 c r e a t e _ l e a d _ f r o m _ i m p o r t ( l e a d _ d a t a ,   r e q u e s t ,   i m p o r t _ s e s s i o n )  
                                                 s u c c e s s _ c o u n t   + =   1  
                                          
                                         p r o c e s s e d _ c o u n t   + =   1  
                                          
                                         #   U p d a t e   p r o g r e s s  
                                         i f   p r o c e s s e d _ c o u n t   %   1 0   = =   0 :     #   U p d a t e   e v e r y   1 0   r e c o r d s  
                                                 i m p o r t _ s e s s i o n . p r o c e s s e d _ r e c o r d s   =   p r o c e s s e d _ c o u n t  
                                                 i m p o r t _ s e s s i o n . s u c c e s s f u l _ r e c o r d s   =   s u c c e s s _ c o u n t  
                                                 i m p o r t _ s e s s i o n . f a i l e d _ r e c o r d s   =   e r r o r _ c o u n t  
                                                 i m p o r t _ s e s s i o n . s a v e ( )  
                                                  
                                 e x c e p t   E x c e p t i o n   a s   e :  
                                         e r r o r _ c o u n t   + =   1  
                                         e r r o r _ d e t a i l s . a p p e n d ( {  
                                                 ' r o w ' :   l e a d _ d a t a . g e t ( ' r o w _ n u m ' ,   0 ) ,  
                                                 ' f i e l d ' :   ' g e n e r a l ' ,  
                                                 ' m e s s a g e ' :   s t r ( e )  
                                         } )  
                  
                 #   F i n a l   u p d a t e  
                 i m p o r t _ s e s s i o n . p r o c e s s e d _ r e c o r d s   =   p r o c e s s e d _ c o u n t  
                 i m p o r t _ s e s s i o n . s u c c e s s f u l _ r e c o r d s   =   s u c c e s s _ c o u n t  
                 i m p o r t _ s e s s i o n . f a i l e d _ r e c o r d s   =   e r r o r _ c o u n t  
                 i m p o r t _ s e s s i o n . s t a t u s   =   ' c o m p l e t e d '  
                 i m p o r t _ s e s s i o n . e r r o r _ d e t a i l s   =   e r r o r _ d e t a i l s [ : 1 0 0 ]     #   L i m i t   t o   1 0 0   e r r o r s  
                 i m p o r t _ s e s s i o n . s a v e ( )  
                  
         e x c e p t   E x c e p t i o n   a s   e :  
                 i m p o r t _ s e s s i o n . s t a t u s   =   ' f a i l e d '  
                 i m p o r t _ s e s s i o n . e r r o r _ m e s s a g e   =   s t r ( e )  
                 i m p o r t _ s e s s i o n . s a v e ( )  
  
  
 d e f   c r e a t e _ l e a d _ f r o m _ i m p o r t ( l e a d _ d a t a ,   r e q u e s t ,   i m p o r t _ s e s s i o n ) :  
         " " " C r e a t e   a   n e w   l e a d   f r o m   i m p o r t   d a t a " " "  
         #   H a n d l e   a s s i g n m e n t  
         a s s i g n e d _ t o   =   N o n e  
         i f   i m p o r t _ s e s s i o n . a s s i g n _ t o   = =   ' m e ' :  
                 a s s i g n e d _ t o   =   r e q u e s t . u s e r  
         e l i f   i m p o r t _ s e s s i o n . a s s i g n _ t o   = =   ' u n a s s i g n e d ' :  
                 a s s i g n e d _ t o   =   N o n e  
          
         l e a d   =   L e a d . o b j e c t s . c r e a t e (  
                 c o m p a n y _ i d = r e q u e s t . u s e r . c o m p a n y _ i d ,  
                 n a m e = l e a d _ d a t a [ ' n a m e ' ] ,  
                 m o b i l e = l e a d _ d a t a [ ' m o b i l e ' ] ,  
                 e m a i l = l e a d _ d a t a . g e t ( ' e m a i l ' ,   ' ' ) ,  
                 a l t _ m o b i l e = l e a d _ d a t a . g e t ( ' a l t _ m o b i l e ' ,   ' ' ) ,  
                 w h a t s a p p _ n o = l e a d _ d a t a . g e t ( ' w h a t s a p p _ n o ' ,   ' ' ) ,  
                 a l t _ e m a i l = l e a d _ d a t a . g e t ( ' a l t _ e m a i l ' ,   ' ' ) ,  
                 a d d r e s s = l e a d _ d a t a . g e t ( ' a d d r e s s ' ,   ' ' ) ,  
                 c i t y = l e a d _ d a t a . g e t ( ' c i t y ' ,   ' ' ) ,  
                 s t a t e = l e a d _ d a t a . g e t ( ' s t a t e ' ,   ' ' ) ,  
                 p o s t a l c o d e = l e a d _ d a t a . g e t ( ' p o s t a l c o d e ' ,   ' ' ) ,  
                 c o u n t r y = l e a d _ d a t a . g e t ( ' c o u n t r y ' ,   ' ' ) ,  
                 s t a t u s = l e a d _ d a t a . g e t ( ' s t a t u s ' ,   ' l e a d ' ) ,  
                 s t a t u s _ d e s c r i p t i o n = l e a d _ d a t a . g e t ( ' s t a t u s _ d e s c r i p t i o n ' ,   ' ' ) ,  
                 l e a d _ s o u r c e = l e a d _ d a t a . g e t ( ' l e a d _ s o u r c e ' ,   ' ' ) ,  
                 l e a d _ s o u r c e _ d e s c r i p t i o n = l e a d _ d a t a . g e t ( ' l e a d _ s o u r c e _ d e s c r i p t i o n ' ,   ' ' ) ,  
                 r e f e r e d _ b y = l e a d _ d a t a . g e t ( ' r e f e r e d _ b y ' ,   ' ' ) ,  
                 c a m p a i g n _ n a m e = l e a d _ d a t a . g e t ( ' c a m p a i g n _ n a m e ' ,   ' ' ) ,  
                 c a m p a i g n _ m e d i u m = l e a d _ d a t a . g e t ( ' c a m p a i g n _ m e d i u m ' ,   ' ' ) ,  
                 c a m p a i g n _ s o u r c e = l e a d _ d a t a . g e t ( ' c a m p a i g n _ s o u r c e ' ,   ' ' ) ,  
                 n o t e s = l e a d _ d a t a . g e t ( ' n o t e s ' ,   ' ' ) ,  
                 b u d g e t = l e a d _ d a t a . g e t ( ' b u d g e t ' ,   ' ' ) ,  
                 r e q u i r e m e n t = l e a d _ d a t a . g e t ( ' r e q u i r e m e n t ' ,   ' ' ) ,  
                 f o l l o w _ u p _ d a t e = l e a d _ d a t a . g e t ( ' f o l l o w _ u p _ d a t e ' ,   ' ' ) ,  
                 a s s i g n e d _ t o = a s s i g n e d _ t o ,  
                 c r e a t e d _ b y = r e q u e s t . u s e r ,  
                 i s _ i m p o r t e d = T r u e ,  
                 i m p o r t _ s e s s i o n = i m p o r t _ s e s s i o n  
         )  
          
         #   L o g   a c t i v i t y  
         L e a d A c t i v i t y . o b j e c t s . c r e a t e (  
                 l e a d = l e a d ,  
                 u s e r = r e q u e s t . u s e r ,  
                 a c t i v i t y _ t y p e = ' c r e a t e d ' ,  
                 d e s c r i p t i o n = ' L e a d   c r e a t e d   v i a   b u l k   i m p o r t '  
         )  
  
  
 d e f   u p d a t e _ l e a d _ f r o m _ i m p o r t ( e x i s t i n g _ l e a d ,   l e a d _ d a t a ) :  
         " " " U p d a t e   a n   e x i s t i n g   l e a d   f r o m   i m p o r t   d a t a " " "  
         #   U p d a t e   r e l e v a n t   f i e l d s  
         i f   l e a d _ d a t a . g e t ( ' e m a i l ' ) :  
                 e x i s t i n g _ l e a d . e m a i l   =   l e a d _ d a t a [ ' e m a i l ' ]  
         i f   l e a d _ d a t a . g e t ( ' a l t _ m o b i l e ' ) :  
                 e x i s t i n g _ l e a d . a l t _ m o b i l e   =   l e a d _ d a t a [ ' a l t _ m o b i l e ' ]  
         i f   l e a d _ d a t a . g e t ( ' w h a t s a p p _ n o ' ) :  
                 e x i s t i n g _ l e a d . w h a t s a p p _ n o   =   l e a d _ d a t a [ ' w h a t s a p p _ n o ' ]  
         i f   l e a d _ d a t a . g e t ( ' a d d r e s s ' ) :  
                 e x i s t i n g _ l e a d . a d d r e s s   =   l e a d _ d a t a [ ' a d d r e s s ' ]  
         i f   l e a d _ d a t a . g e t ( ' c i t y ' ) :  
                 e x i s t i n g _ l e a d . c i t y   =   l e a d _ d a t a [ ' c i t y ' ]  
         i f   l e a d _ d a t a . g e t ( ' s t a t e ' ) :  
                 e x i s t i n g _ l e a d . s t a t e   =   l e a d _ d a t a [ ' s t a t e ' ]  
         i f   l e a d _ d a t a . g e t ( ' p o s t a l c o d e ' ) :  
                 e x i s t i n g _ l e a d . p o s t a l c o d e   =   l e a d _ d a t a [ ' p o s t a l c o d e ' ]  
         i f   l e a d _ d a t a . g e t ( ' n o t e s ' ) :  
                 e x i s t i n g _ l e a d . n o t e s   =   l e a d _ d a t a [ ' n o t e s ' ]  
          
         e x i s t i n g _ l e a d . s a v e ( )  
  
  
 @ l o g i n _ r e q u i r e d  
 @ h i e r a r c h y _ r e q u i r e d  
 d e f   l e a d _ i m p o r t _ p r o g r e s s ( r e q u e s t ,   s e s s i o n _ i d ) :  
         " " " G e t   i m p o r t   p r o g r e s s   f o r   a   s e s s i o n " " "  
         i f   r e q u e s t . u s e r . r o l e   ! =   ' o w n e r ' :  
                 r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' P e r m i s s i o n   d e n i e d ' } ,   s t a t u s = 4 0 3 )  
          
         t r y :  
                 s e s s i o n   =   L e a d I m p o r t S e s s i o n . o b j e c t s . g e t ( i d = s e s s i o n _ i d ,   c o m p a n y _ i d = r e q u e s t . u s e r . c o m p a n y _ i d )  
                  
                 p e r c e n t a g e   =   0  
                 i f   s e s s i o n . t o t a l _ r e c o r d s   >   0 :  
                         p e r c e n t a g e   =   ( s e s s i o n . p r o c e s s e d _ r e c o r d s   /   s e s s i o n . t o t a l _ r e c o r d s )   *   1 0 0  
                  
                 r e t u r n   J s o n R e s p o n s e ( {  
                         ' s t a t u s ' :   s e s s i o n . s t a t u s ,  
                         ' p e r c e n t a g e ' :   p e r c e n t a g e ,  
                         ' p r o c e s s e d ' :   s e s s i o n . p r o c e s s e d _ r e c o r d s ,  
                         ' s u c c e s s f u l ' :   s e s s i o n . s u c c e s s f u l _ r e c o r d s ,  
                         ' e r r o r s ' :   s e s s i o n . f a i l e d _ r e c o r d s ,  
                         ' t o t a l ' :   s e s s i o n . t o t a l _ r e c o r d s ,  
                         ' e r r o r _ d e t a i l s ' :   s e s s i o n . e r r o r _ d e t a i l s   o r   [ ]  
                 } )  
                  
         e x c e p t   L e a d I m p o r t S e s s i o n . D o e s N o t E x i s t :  
                 r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' S e s s i o n   n o t   f o u n d ' } ,   s t a t u s = 4 0 4 )  
  
  
 @ l o g i n _ r e q u i r e d  
 @ h i e r a r c h y _ r e q u i r e d  
 d e f   l e a d _ i m p o r t _ c a n c e l ( r e q u e s t ,   s e s s i o n _ i d ) :  
         " " " C a n c e l   a n   i m p o r t   s e s s i o n " " "  
         i f   r e q u e s t . u s e r . r o l e   ! =   ' o w n e r ' :  
                 r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' P e r m i s s i o n   d e n i e d ' } ,   s t a t u s = 4 0 3 )  
          
         i f   r e q u e s t . m e t h o d   ! =   ' P O S T ' :  
                 r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' I n v a l i d   r e q u e s t   m e t h o d ' } ,   s t a t u s = 4 0 5 )  
          
         t r y :  
                 s e s s i o n   =   L e a d I m p o r t S e s s i o n . o b j e c t s . g e t ( i d = s e s s i o n _ i d ,   c o m p a n y _ i d = r e q u e s t . u s e r . c o m p a n y _ i d )  
                  
                 i f   s e s s i o n . s t a t u s   i n   [ ' p r o c e s s i n g ' ,   ' p e n d i n g ' ] :  
                         s e s s i o n . s t a t u s   =   ' c a n c e l l e d '  
                         s e s s i o n . s a v e ( )  
                         r e t u r n   J s o n R e s p o n s e ( { ' s u c c e s s ' :   T r u e } )  
                 e l s e :  
                         r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' C a n n o t   c a n c e l   c o m p l e t e d   i m p o r t ' } ,   s t a t u s = 4 0 0 )  
                  
         e x c e p t   L e a d I m p o r t S e s s i o n . D o e s N o t E x i s t :  
                 r e t u r n   J s o n R e s p o n s e ( { ' e r r o r ' :   ' S e s s i o n   n o t   f o u n d ' } ,   s t a t u s = 4 0 4 )  
 

@login_required
@hierarchy_required
def lead_import_ajax(request):
    """AJAX endpoint for modal-based lead import with progress tracking"""
    if request.user.role != 'owner':
        return JsonResponse({'success': False, 'error': 'Permission denied. Only owners can import leads.'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)
    
    action = request.POST.get('action', 'preview')
    
    if action == 'preview':
        return handle_import_preview(request)
    elif action == 'import':
        return handle_import_start(request)
    else:
        return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)


def handle_import_preview(request):
    """Handle file preview for import modal"""
    try:
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'success': False, 'error': 'No file provided'})
        
        # Read file content
        file_content = file.read()
        if not file_content.strip():
            return JsonResponse({'success': False, 'error': 'File is empty'})
        
        file.seek(0)
        
        # Process file based on type
        if file.name.endswith('.csv'):
            leads_data, headers = process_csv_preview(file)
        else:
            # For Excel files, use pandas
            leads_data, headers = process_excel_preview(file)
        
        # Detect duplicates
        detector = DuplicateDetector(request.user.company_id)
        duplicate_results = detector.batch_detect_duplicates(leads_data)
        
        # Prepare preview data (first 10 rows)
        preview_data = []
        for i, lead_data in enumerate(leads_data[:10]):
            preview_data.append(lead_data)
        
        return JsonResponse({
            'success': True,
            'headers': headers,
            'preview': preview_data,
            'total_records': len(leads_data),
            'duplicates': len(duplicate_results.get('duplicates', [])),
            'duplicate_details': duplicate_results.get('duplicates', [])[:5]  # First 5 duplicates
        })
        
    except Exception as e:
        logger.error(f"Import preview error: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Preview failed: {str(e)}'})


def process_csv_preview(file):
    """Process CSV file for preview"""
    from io import TextIOWrapper
    
    # Try different encodings
    encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
    reader = None
    
    for encoding in encodings:
        try:
            file.seek(0)
            text_file = TextIOWrapper(file, encoding=encoding)
            reader = csv.DictReader(text_file)
            break
        except UnicodeDecodeError:
            continue
    
    if not reader:
        raise ValueError("Unable to read CSV file with any supported encoding")
    
    # Get headers
    headers = list(reader.fieldnames) if reader.fieldnames else []
    
    # Process data
    leads_data = []
    for row_num, row in enumerate(reader):
        if row_num >= 1000:  # Limit preview to 1000 records
            break
        
        lead_data = {
            'name': row.get('name', '').strip(),
            'mobile': row.get('mobile', '').strip(),
            'email': row.get('email', '').strip(),
            'alt_mobile': row.get('alt_mobile', '').strip(),
            'whatsapp_no': row.get('whatsapp_no', '').strip(),
            'alt_email': row.get('alt_email', '').strip(),
            'address': row.get('address', '').strip(),
            'city': row.get('city', '').strip(),
            'state': row.get('state', '').strip(),
            'postalcode': row.get('postalcode', '').strip(),
            'country': row.get('country', '').strip(),
            'status': row.get('status', 'lead').strip() or 'lead',
            'status_description': row.get('status_description', '').strip(),
            'lead_source': row.get('lead_source', '').strip(),
            'lead_source_description': row.get('lead_source_description', '').strip(),
            'refered_by': row.get('refered_by', '').strip(),
            'campaign_name': row.get('campaign_name', '').strip(),
            'campaign_medium': row.get('campaign_medium', '').strip(),
            'campaign_source': row.get('campaign_source', '').strip(),
            'notes': row.get('notes', '').strip(),
            'budget': row.get('budget', '').strip(),
            'requirement': row.get('requirement', '').strip(),
            'follow_up_date': row.get('follow_up_date', '').strip(),
            'row_num': row_num + 2  # +2 for CSV (1 for header, 1 for 0-based)
        }
        leads_data.append(lead_data)
    
    return leads_data, headers


def process_excel_preview(file):
    """Process Excel file for preview"""
    # Read Excel file
    df = pd.read_excel(file)
    
    # Normalize column names
    df.columns = [str(col).strip().lower() for col in df.columns]
    
    # Validate required columns
    required_columns = ['name', 'mobile']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
    
    # Convert to list of dictionaries
    leads_data = []
    for index, row in df.iterrows():
        if index >= 1000:  # Limit preview to 1000 records
            break
        
        lead_data = {
            'name': str(row.get('name', '')).strip(),
            'mobile': str(row.get('mobile', '')).strip(),
            'email': str(row.get('email', '')).strip(),
            'alt_mobile': str(row.get('alt_mobile', '')).strip(),
            'whatsapp_no': str(row.get('whatsapp_no', '')).strip(),
            'alt_email': str(row.get('alt_email', '')).strip(),
            'address': str(row.get('address', '')).strip(),
            'city': str(row.get('city', '')).strip(),
            'state': str(row.get('state', '')).strip(),
            'postalcode': str(row.get('postalcode', '')).strip(),
            'country': str(row.get('country', '')).strip(),
            'status': str(row.get('status', 'lead')).strip() or 'lead',
            'status_description': str(row.get('status_description', '')).strip(),
            'lead_source': str(row.get('lead_source', '')).strip(),
            'lead_source_description': str(row.get('lead_source_description', '')).strip(),
            'refered_by': str(row.get('refered_by', '')).strip(),
            'campaign_name': str(row.get('campaign_name', '')).strip(),
            'campaign_medium': str(row.get('campaign_medium', '')).strip(),
            'campaign_source': str(row.get('campaign_source', '')).strip(),
            'notes': str(row.get('notes', '')).strip(),
            'budget': str(row.get('budget', '')).strip(),
            'requirement': str(row.get('requirement', '')).strip(),
            'follow_up_date': str(row.get('follow_up_date', '')).strip(),
            'row_num': index + 2  # +2 for Excel (1 for header, 1 for 0-based)
        }
        leads_data.append(lead_data)
    
    headers = list(df.columns)
    return leads_data, headers


def handle_import_start(request):
    """Handle starting the import process"""
    try:
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'success': False, 'error': 'No file provided'})
        
        # Create import session
        file_hash = hashlib.sha256(file.read()).hexdigest()
        file.seek(0)
        
        import_session = LeadImportSession.objects.create(
            company_id=request.user.company_id,
            user=request.user,
            file_name=file.name,
            file_hash=file_hash,
            status='processing',
            total_records=0,
            processed_records=0,
            successful_records=0,
            failed_records=0,
            duplicate_handling=request.POST.get('duplicate_handling', 'skip'),
            assign_to=request.POST.get('assign_to', 'me')
        )
        
        # Start async import processing (for now, process synchronously)
        # In production, this should be moved to Celery or similar
        from threading import Thread
        
        def process_import_async():
            try:
                process_import_job(import_session.id, file, request)
            except Exception as e:
                logger.error(f"Async import error: {str(e)}")
                import_session.status = 'failed'
                import_session.error_message = str(e)
                import_session.save()
        
        # Start processing in background
        thread = Thread(target=process_import_async)
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            'success': True,
            'session_id': import_session.id
        })
        
    except Exception as e:
        logger.error(f"Import start error: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Import failed to start: {str(e)}'})


def process_import_job(session_id, file, request):
    """Process the actual import job"""
    import_session = LeadImportSession.objects.get(id=session_id)
    
    try:
        # Process file
        file.seek(0)
        if file.name.endswith('.csv'):
            leads_data, _ = process_csv_preview(file)
        else:
            leads_data, _ = process_excel_preview(file)
        
        import_session.total_records = len(leads_data)
        import_session.save()
        
        # Process leads in batches
        batch_size = 100
        processed_count = 0
        success_count = 0
        error_count = 0
        error_details = []
        
        detector = DuplicateDetector(request.user.company_id)
        
        for i in range(0, len(leads_data), batch_size):
            batch = leads_data[i:i + batch_size]
            
            for lead_data in batch:
                try:
                    # Handle duplicates
                    duplicate_result = detector.detect_single_duplicate(lead_data)
                    
                    if duplicate_result and import_session.duplicate_handling == 'skip':
                        error_count += 1
                        continue
                    elif duplicate_result and import_session.duplicate_handling == 'update':
                        # Update existing lead
                        existing_lead = duplicate_result[0]
                        update_lead_from_import(existing_lead, lead_data)
                        success_count += 1
                    else:
                        # Create new lead
                        create_lead_from_import(lead_data, request, import_session)
                        success_count += 1
                    
                    processed_count += 1
                    
                    # Update progress
                    if processed_count % 10 == 0:  # Update every 10 records
                        import_session.processed_records = processed_count
                        import_session.successful_records = success_count
                        import_session.failed_records = error_count
                        import_session.save()
                        
                except Exception as e:
                    error_count += 1
                    error_details.append({
                        'row': lead_data.get('row_num', 0),
                        'field': 'general',
                        'message': str(e)
                    })
        
        # Final update
        import_session.processed_records = processed_count
        import_session.successful_records = success_count
        import_session.failed_records = error_count
        import_session.status = 'completed'
        import_session.error_details = error_details[:100]  # Limit to 100 errors
        import_session.save()
        
    except Exception as e:
        import_session.status = 'failed'
        import_session.error_message = str(e)
        import_session.save()


def create_lead_from_import(lead_data, request, import_session):
    """Create a new lead from import data"""
    # Handle assignment
    assigned_to = None
    if import_session.assign_to == 'me':
        assigned_to = request.user
    elif import_session.assign_to == 'unassigned':
        assigned_to = None
    
    lead = Lead.objects.create(
        company_id=request.user.company_id,
        name=lead_data['name'],
        mobile=lead_data['mobile'],
        email=lead_data.get('email', ''),
        alt_mobile=lead_data.get('alt_mobile', ''),
        whatsapp_no=lead_data.get('whatsapp_no', ''),
        alt_email=lead_data.get('alt_email', ''),
        address=lead_data.get('address', ''),
        city=lead_data.get('city', ''),
        state=lead_data.get('state', ''),
        postalcode=lead_data.get('postalcode', ''),
        country=lead_data.get('country', ''),
        status=lead_data.get('status', 'lead'),
        status_description=lead_data.get('status_description', ''),
        lead_source=lead_data.get('lead_source', ''),
        lead_source_description=lead_data.get('lead_source_description', ''),
        refered_by=lead_data.get('refered_by', ''),
        campaign_name=lead_data.get('campaign_name', ''),
        campaign_medium=lead_data.get('campaign_medium', ''),
        campaign_source=lead_data.get('campaign_source', ''),
        notes=lead_data.get('notes', ''),
        budget=lead_data.get('budget', ''),
        requirement=lead_data.get('requirement', ''),
        follow_up_date=lead_data.get('follow_up_date', ''),
        assigned_to=assigned_to,
        created_by=request.user,
        is_imported=True,
        import_session=import_session
    )
    
    # Log activity
    LeadActivity.objects.create(
        lead=lead,
        user=request.user,
        activity_type='created',
        description='Lead created via bulk import'
    )


def update_lead_from_import(existing_lead, lead_data):
    """Update an existing lead from import data"""
    # Update relevant fields
    if lead_data.get('email'):
        existing_lead.email = lead_data['email']
    if lead_data.get('alt_mobile'):
        existing_lead.alt_mobile = lead_data['alt_mobile']
    if lead_data.get('whatsapp_no'):
        existing_lead.whatsapp_no = lead_data['whatsapp_no']
    if lead_data.get('address'):
        existing_lead.address = lead_data['address']
    if lead_data.get('city'):
        existing_lead.city = lead_data['city']
    if lead_data.get('state'):
        existing_lead.state = lead_data['state']
    if lead_data.get('postalcode'):
        existing_lead.postalcode = lead_data['postalcode']
    if lead_data.get('notes'):
        existing_lead.notes = lead_data['notes']
    
    existing_lead.save()


@login_required
@hierarchy_required
def lead_import_progress(request, session_id):
    """Get import progress for a session"""
    if request.user.role != 'owner':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    try:
        session = LeadImportSession.objects.get(id=session_id, company_id=request.user.company_id)
        
        percentage = 0
        if session.total_records > 0:
            percentage = (session.processed_records / session.total_records) * 100
        
        return JsonResponse({
            'status': session.status,
            'percentage': percentage,
            'processed': session.processed_records,
            'successful': session.successful_records,
            'errors': session.failed_records,
            'total': session.total_records,
            'error_details': session.error_details or []
        })
        
    except LeadImportSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)


@login_required
@hierarchy_required
def lead_import_cancel(request, session_id):
    """Cancel an import session"""
    if request.user.role != 'owner':
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)
    
    try:
        session = LeadImportSession.objects.get(id=session_id, company_id=request.user.company_id)
        
        if session.status in ['processing', 'pending']:
            session.status = 'cancelled'
            session.save()
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'error': 'Cannot cancel completed import'}, status=400)
        
    except LeadImportSession.DoesNotExist:
        return JsonResponse({'error': 'Session not found'}, status=404)
