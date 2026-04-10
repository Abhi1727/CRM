from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, F, Case, When, IntegerField
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.http import QueryDict, Http404
from django.core.cache import cache
import pandas as pd
import json
import os
import uuid
import hashlib
from datetime import datetime, time

from .models import Lead, LeadActivity, LeadHistory, LeadImportSession, LeadOperationLog
from .forms import (
    LeadForm, LeadAssignmentForm, BulkLeadAssignmentForm, 
    LeadImportForm, LeadStatusUpdateForm
)
from accounts.permissions import hierarchy_required, role_required, can_access_lead_required
from accounts.models import User
from services.duplicate_detector import DuplicateDetector

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
    
    # Generate cache keys for dashboard statistics
    cache_key_prefix = f"dashboard_stats_{request.user.id}_{request.user.company_id}"
    
    # Try to get cached statistics
    cached_stats = cache.get(f"{cache_key_prefix}_main")
    
    if cached_stats:
        # Use cached data
        total_leads = cached_stats['total_leads']
        today_follow_ups = cached_stats['today_follow_ups']
        exp_revenue = cached_stats['exp_revenue']
        course_amount_total = cached_stats['course_amount_total']
        formatted_leads_by_status = cached_stats['formatted_leads_by_status']
    else:
        # Compute and cache statistics
        # Get user's accessible leads only
        accessible_leads = request.hierarchy_context['accessible_leads']
        
        # Get total leads count
        total_leads = accessible_leads.count()
        
        # Get today's follow-ups
        today = timezone.now().date()
        today_follow_ups = accessible_leads.filter(followup_datetime__date=today).count()
        
        # Get expected revenue
        exp_revenue = accessible_leads.aggregate(total=Sum('exp_revenue'))['total'] or 0
        
        # Get course amount total (as actual revenue)
        course_amount_total = accessible_leads.aggregate(total=Sum('course_amount'))['total'] or 0
        
        # Get leads by status with optimized single query
        leads_by_status = dict(
            accessible_leads.values('status')
            .annotate(count=Count('id_lead'))
            .values_list('status', 'count')
        )
        
        # Format leads_by_status to match expected structure
        formatted_leads_by_status = {}
        for status_code, status_name in Lead.STATUS_CHOICES:
            formatted_leads_by_status[status_code] = {
                'name': status_name,
                'count': leads_by_status.get(status_code, 0)
            }
        
        # Cache the main statistics for 5 minutes
        stats_data = {
            'total_leads': total_leads,
            'today_follow_ups': today_follow_ups,
            'exp_revenue': exp_revenue,
            'course_amount_total': course_amount_total,
            'formatted_leads_by_status': formatted_leads_by_status,
        }
        cache.set(f"{cache_key_prefix}_main", stats_data, 300)
    
    # Role-specific metrics with caching
    role_cache_key = f"{cache_key_prefix}_role_{request.user.role}"
    cached_role_stats = cache.get(role_cache_key)
    
    if cached_role_stats:
        role_context = cached_role_stats
    else:
        role_context = {}
        accessible_leads = request.hierarchy_context['accessible_leads']
        
        if request.user.role == 'agent':
            # Agent metrics - optimized with single query
            my_leads_qs = accessible_leads.filter(assigned_user=request.user)
            agent_stats = my_leads_qs.aggregate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done'))
            )
            
            total_leads_count = agent_stats['total_leads']
            converted_count = agent_stats['converted_leads']
            pending_count = total_leads_count - converted_count
            
            role_context.update({
                'my_leads_count': total_leads_count,
                'converted_leads': converted_count,
                'pending_leads': pending_count,
                'conversion_rate': (converted_count / total_leads_count * 100) if total_leads_count > 0 else 0,
            })
        
        elif request.user.role == 'team_lead':
            # Team Lead metrics - optimized with bulk query
            team_agents = request.user.get_accessible_users().select_related('team_lead')
            
            # Get all team agent lead stats in single query
            team_stats = accessible_leads.filter(
                assigned_user__in=team_agents
            ).values('assigned_user').annotate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done'))
            )
            
            # Create lookup dict for stats
            stats_lookup = {stat['assigned_user']: stat for stat in team_stats}
            
            agent_performance = []
            for agent in team_agents:
                agent_stat = stats_lookup.get(agent.id, {'total_leads': 0, 'converted_leads': 0})
                total_leads = agent_stat['total_leads']
                converted = agent_stat['converted_leads']
                
                agent_performance.append({
                    'agent': agent,
                    'total_leads': total_leads,
                    'converted': converted,
                    'conversion_rate': (converted / total_leads * 100) if total_leads > 0 else 0,
                })
            
            role_context.update({
                'team_agents_count': team_agents.count(),
                'agent_performance': agent_performance,
            })
        
        elif request.user.role == 'manager':
            # Manager metrics - optimized with bulk queries
            team_leads = request.user.get_accessible_users().filter(role='team_lead').select_related('manager')
            
            # Get all team agents for all team leads in single query
            all_team_agents = User.objects.filter(
                team_lead__in=team_leads
            ).select_related('team_lead')
            
            # Get lead stats for all team agents in single query
            team_stats = accessible_leads.filter(
                assigned_user__in=all_team_agents
            ).values('assigned_user__team_lead').annotate(
                total_leads=Count('id_lead'),
                converted_leads=Count('id_lead', filter=Q(status='sale_done'))
            )
            
            # Create lookup dict for team lead stats
            stats_lookup = {stat['assigned_user__team_lead']: stat for stat in team_stats}
            
            team_performance = []
            for team_lead in team_leads:
                team_stat = stats_lookup.get(team_lead.id, {'total_leads': 0, 'converted_leads': 0})
                total_leads = team_stat['total_leads']
                converted = team_stat['converted_leads']
                
                team_performance.append({
                    'team_lead': team_lead,
                    'total_leads': total_leads,
                    'converted': converted,
                    'conversion_rate': (converted / total_leads * 100) if total_leads > 0 else 0,
                })
            
            role_context.update({
                'team_leads_count': team_leads.count(),
                'team_performance': team_performance,
            })
        
        # Cache role-specific statistics for 5 minutes
        cache.set(role_cache_key, role_context, 300)
    
    context = {
        'user': request.user,
        'role': request.user.get_role_display(),
        'greeting_time': greeting_time,
        'total_leads': total_leads,
        'today_follow_ups': today_follow_ups,
        'expected_revenue': exp_revenue,
        'actual_revenue': course_amount_total,
        'leads_by_status': formatted_leads_by_status,
        **role_context,  # Add role-specific metrics
    }
    return render(request, 'dashboard/home.html', context)

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
            today = timezone.now().date()
            today_start = timezone.make_aware(datetime.combine(today, time.min))
            today_end = timezone.make_aware(datetime.combine(today, time.max))
            queryset = queryset.filter(created_at__gte=today_start, created_at__lte=today_end)
            logger.debug(f"DEBUG: After today preset (date={today}, range={today_start} to {today_end}): {queryset.count()}")
            
        elif filters['preset'] == 'week':
            week_ago_date = timezone.now().date() - timezone.timedelta(days=7)
            week_start = timezone.make_aware(datetime.combine(week_ago_date, time.min))
            queryset = queryset.filter(created_at__gte=week_start)
            logger.debug(f"DEBUG: After week preset (since={week_start}): {queryset.count()}")
            
        elif filters['preset'] == 'month':
            month_ago_date = timezone.now().date() - timezone.timedelta(days=30)
            month_start = timezone.make_aware(datetime.combine(month_ago_date, time.min))
            queryset = queryset.filter(created_at__gte=month_start)
            logger.debug(f"DEBUG: After month preset (since={month_start}): {queryset.count()}")
            
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
    leads_qs = _apply_common_lead_filters(base_queryset, request.user, filters)
    
    # Optimize: Apply ordering and select_related before count to avoid duplicate queries
    leads_qs = leads_qs.order_by(LEAD_SORT_FIELDS.get(sort_by, default_sort))
    
    # Use count() with optimization for large datasets
    try:
        # For MySQL, use SQL_CALC_FOUND_ROWS for better performance on large datasets
        total_filtered_count = leads_qs.count()
    except Exception:
        # Fallback to len() if count() fails
        total_filtered_count = len(leads_qs)
    
    logger.debug(f"DEBUG: Final filtered leads count: {total_filtered_count}")
    
    # Create paginator with optimized queryset
    paginator = Paginator(leads_qs, filters['page_size'])
    page_obj = paginator.get_page(request.GET.get('page'))
    
    # Optimize: Only apply select_related to the current page objects
    if page_obj.object_list:
        # Get the IDs from current page and fetch with select_related
        page_lead_ids = [lead.id_lead for lead in page_obj.object_list]
        optimized_leads = Lead.objects.filter(
            id_lead__in=page_lead_ids
        ).select_related(
            'assigned_user', 'created_by', 
            'assigned_user__manager', 'assigned_user__team_lead'
        ).order_by(LEAD_SORT_FIELDS.get(sort_by, default_sort))
        
        # Create a lookup dict for quick access
        leads_lookup = {lead.id_lead: lead for lead in optimized_leads}
        
        # Replace the page objects with optimized ones
        page_obj.object_list = [
            leads_lookup[lead.id_lead] for lead in page_obj.object_list
        ]

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
    return _render_leads_list_page(request, base_queryset, 'Transferred Leads', default_sort='-created_at')

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
    
    # Check if user can modify this lead
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    
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
    """Edit an existing lead using the same form as creation."""
    lead = request.current_lead

    # Basic permission: allow if user can modify the lead or is its assignee
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    if not can_modify:
        raise PermissionDenied("You don't have permission to edit this lead.")

    if request.method == "POST":
        form = LeadForm(request.POST, instance=lead)
        if form.is_valid():
            updated_lead = form.save(commit=False)
            updated_lead.modified_user = request.user
            updated_lead.save()
            messages.success(request, "Lead updated successfully.")
            return redirect("dashboard:lead_detail", pk=lead.id_lead)
    else:
        form = LeadForm(instance=lead)

    context = {
        "form": form,
        "page_title": f"Edit Lead - {lead.name}",
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
    """Bulk assign multiple leads to a user"""
    if request.method == "POST":
        form = BulkLeadAssignmentForm(request.user, request.POST)
        if form.is_valid():
            assigned_user = form.cleaned_data['assigned_user']
            lead_ids = form.cleaned_data['lead_ids'].split(',')
            assignment_notes = form.cleaned_data.get('assignment_notes', '')
            
            # Convert to integers and validate
            try:
                lead_ids = [int(id.strip()) for id in lead_ids if id.strip()]
            except ValueError:
                messages.error(request, "Invalid lead IDs provided.")
                return redirect("dashboard:leads_all")
            
            # Get leads that user can access
            accessible_leads = request.hierarchy_context['accessible_leads'].filter(id_lead__in=lead_ids)
            
            if not accessible_leads.exists():
                messages.error(request, "No accessible leads found for assignment.")
                return redirect("dashboard:leads_all")
            
            successful_assignments = 0
            failed_assignments = 0
            
            # Batch optimize: collect all valid assignments first
            valid_assignments = []
            assignment_history_data = []
            activity_data = []
            
            for lead in accessible_leads.select_related('assigned_user'):
                try:
                    # Check if user can assign this lead
                    can_assign = lead.can_be_assigned_by(request.user)
                    can_assign_to_target = lead.can_be_assigned_to_user(assigned_user, request.user)
                    
                    if can_assign and can_assign_to_target:
                        old_user = lead.assigned_user
                        valid_assignments.append({
                            'lead': lead,
                            'old_user': old_user,
                        })
                        
                        # Prepare assignment history data
                        assignment_history_data.append(LeadHistory(
                            lead=lead,
                            user=request.user,
                            field_name='assigned_user',
                            old_value=old_user.username if old_user else None,
                            new_value=assigned_user.username,
                            action=f'Bulk assigned to {assigned_user.username}'
                        ))
                        
                        # Prepare activity data
                        activity_data.append(LeadActivity(
                            lead=lead,
                            user=request.user,
                            activity_type='bulk_assignment',
                            description=f'Bulk assigned to {assigned_user.username}. {assignment_notes}'
                        ))
                        
                        successful_assignments += 1
                    else:
                        failed_assignments += 1
                except Exception as e:
                    failed_assignments += 1
            
            # Batch update assignments using bulk operations
            if valid_assignments:
                # Update lead assignments in batch
                leads_to_update = []
                for assignment in valid_assignments:
                    lead = assignment['lead']
                    old_user = assignment['old_user']
                    
                    # Update lead fields
                    lead.assigned_user = assigned_user
                    lead.assigned_by = request.user
                    lead.assigned_at = timezone.now()
                    
                    # Handle transfer fields
                    is_transfer = (old_user and old_user != assigned_user) or (not old_user)  # bulk assignment from unassigned
                    if is_transfer:
                        if old_user:
                            lead.transfer_from = old_user.get_full_name() or old_user.username
                        else:
                            lead.transfer_from = "Unassigned"
                        lead.transfer_by = request.user.get_full_name() or request.user.username
                        lead.transfer_date = timezone.now()
                    
                    leads_to_update.append(lead)
                
                # Bulk update leads
                Lead.objects.bulk_update(leads_to_update, [
                    'assigned_user', 'assigned_by', 'assigned_at', 
                    'transfer_from', 'transfer_by', 'transfer_date'
                ])
                
                # Bulk create history and activity records
                if assignment_history_data:
                    LeadHistory.objects.bulk_create(assignment_history_data)
                if activity_data:
                    LeadActivity.objects.bulk_create(activity_data)
            
            if successful_assignments > 0:
                messages.success(request, f"Successfully assigned {successful_assignments} leads to {assigned_user.username}.")
            if failed_assignments > 0:
                messages.warning(request, f"Failed to assign {failed_assignments} leads due to permission restrictions.")
            
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

    deleted_count = 0
    activity_data = []
    leads_to_update = []
    
    for lead in leads_to_delete:
        if lead.deleted:
            continue
        lead.deleted = True
        lead.modified_user = request.user
        leads_to_update.append(lead)
        
        activity_data.append(LeadActivity(
            lead=lead,
            user=request.user,
            activity_type='delete',
            description='Lead deleted from leads list (bulk action).'
        ))
        deleted_count += 1

    # Bulk update leads
    if leads_to_update:
        Lead.objects.bulk_update(leads_to_update, ['deleted', 'modified_user'])
    
    # Bulk create activities
    if activity_data:
        LeadActivity.objects.bulk_create(activity_data)

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
                
                # Read file based on extension with encoding handling
                if file.name.endswith('.csv'):
                    try:
                        # Try UTF-8 first
                        df = pd.read_csv(file, encoding='utf-8')
                    except UnicodeDecodeError:
                        try:
                            # Try common encodings
                            file.seek(0)
                            df = pd.read_csv(file, encoding='latin-1')
                        except UnicodeDecodeError:
                            try:
                                file.seek(0)
                                df = pd.read_csv(file, encoding='cp1252')
                            except UnicodeDecodeError:
                                file.seek(0)
                                df = pd.read_csv(file, encoding='utf-8-sig')
                else:
                    # Excel files usually handle encoding better
                    df = pd.read_excel(file)

                # Normalize column names so imports work with common header variants.
                df.columns = [str(col).strip().lower() for col in df.columns]
                
                # Check if dataframe is empty
                if df.empty:
                    return _error_response("No data found in file. Please check file content.", form_instance=form)
                
                # Check if dataframe has columns
                if len(df.columns) == 0:
                    return _error_response("No columns found in file. Please check CSV format and headers.", form_instance=form)
                
                # Validate required columns
                required_columns = ['name', 'mobile']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    return _error_response(
                        f"Missing required columns: {', '.join(missing_columns)}",
                        form_instance=form
                    )
                
                # Step 2: Duplicate Detection
                # Convert DataFrame to list of dictionaries
                leads_data = []
                for index, row in df.iterrows():
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
                        'company': '' if pd.isna(row.get('company')) else str(row.get('company', '')).strip(),  # For related lead detection
                    }
                    
                    # Add date fields if present
                    if 'exp_close_date' in row and pd.notna(row['exp_close_date']):
                        lead_data['exp_close_date'] = pd.to_datetime(row['exp_close_date']).date()
                    
                    if 'followup_datetime' in row and pd.notna(row['followup_datetime']):
                        lead_data['followup_datetime'] = pd.to_datetime(row['followup_datetime'])
                    
                    if 'birthdate' in row and pd.notna(row['birthdate']):
                        lead_data['birthdate'] = pd.to_datetime(row['birthdate']).date()
                    
                    leads_data.append(lead_data)
                
                # Initialize duplicate detector
                detector = DuplicateDetector(request.user.company_id)
                
                # Detect duplicates for all leads
                duplicate_results = detector.batch_detect_duplicates(leads_data)

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
    
    def _create_lead_from_import(lead_data, result, importing_user):
        lead = Lead.objects.create(
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

        if 'exp_close_date' in lead_data:
            lead.exp_close_date = lead_data['exp_close_date']
        if 'followup_datetime' in lead_data:
            lead.followup_datetime = lead_data['followup_datetime']
        if 'birthdate' in lead_data:
            lead.birthdate = lead_data['birthdate']

        lead.save()
        LeadActivity.objects.create(
            lead=lead,
            user=importing_user,
            activity_type='import',
            description=f'Lead imported from {import_session.file_name}'
        )
        return lead

    import_session.status = 'processing'
    import_session.save(update_fields=['status', 'updated_at'])

    # Process import in chunks for high-volume safety.
    imported_count = 0
    skipped_count = 0
    updated_count = 0
    failed_count = 0
    chunk_size = 500
    if len(duplicate_results) > 10000:
        messages.info(
            request,
            "Large import detected. Processing in chunked mode with reconciliation logging."
        )

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
                # Import explicitly selected rows, including duplicate-marked ones.
                _create_lead_from_import(lead_data, result, request.user)
                imported_count += 1
            
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
            
            successful_assignments = 0
            failed_assignments = 0
            
            for lead in leads:
                try:
                    # Check if user can assign this lead
                    if lead.can_be_assigned_by(request.user) and lead.can_be_assigned_to_user(assigned_user, request.user):
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
                            action=f'Bulk duplicate reassigned to {assigned_user.username}',
                            description=reassign_reason
                        )
                        
                        # Create activity log
                        LeadActivity.objects.create(
                            lead=lead,
                            user=request.user,
                            activity_type='bulk_duplicate_reassignment',
                            description=f'Bulk duplicate reassigned to {assigned_user.username}. {reassign_reason}'
                        )
                        
                        # Mark duplicate as resolved if requested
                        if resolve_duplicates:
                            lead.resolve_duplicate(
                                resolved_by=request.user,
                                resolution_status='resolved',
                                notes=f'Bulk reassigned to {assigned_user.username}. {reassign_reason}'
                            )
                        
                        successful_assignments += 1
                    else:
                        failed_assignments += 1
                except Exception as e:
                    failed_assignments += 1
            
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

