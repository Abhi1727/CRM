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
import pandas as pd
import json
import os
from datetime import datetime

from .models import Lead, LeadActivity, LeadHistory
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
    
    # Get leads by status
    leads_by_status = {}
    for status_code, status_name in Lead.STATUS_CHOICES:
        count = accessible_leads.filter(status=status_code).count()
        leads_by_status[status_code] = {
            'name': status_name,
            'count': count
        }
    
    # Role-specific metrics
    role_context = {}
    
    if request.user.role == 'agent':
        # Agent metrics
        my_leads = accessible_leads.filter(assigned_user=request.user)
        converted_leads = my_leads.filter(status='sale_done').count()
        pending_leads = my_leads.exclude(status='sale_done').count()
        
        role_context.update({
            'my_leads_count': my_leads.count(),
            'converted_leads': converted_leads,
            'pending_leads': pending_leads,
            'conversion_rate': (converted_leads / my_leads.count() * 100) if my_leads.count() > 0 else 0,
        })
    
    elif request.user.role == 'team_lead':
        # Team Lead metrics
        team_agents = request.user.get_accessible_users()
        agent_performance = []
        for agent in team_agents:
            agent_leads = accessible_leads.filter(assigned_user=agent)
            converted = agent_leads.filter(status='sale_done').count()
            agent_performance.append({
                'agent': agent,
                'total_leads': agent_leads.count(),
                'converted': converted,
                'conversion_rate': (converted / agent_leads.count() * 100) if agent_leads.count() > 0 else 0,
            })
        
        role_context.update({
            'team_agents_count': team_agents.count(),
            'agent_performance': agent_performance,
        })
    
    elif request.user.role == 'manager':
        # Manager metrics
        team_leads = request.user.get_accessible_users().filter(role='team_lead')
        team_performance = []
        for team_lead in team_leads:
            team_agents = User.objects.filter(team_lead=team_lead)
            team_leads_count = accessible_leads.filter(assigned_user__in=team_agents).count()
            team_converted = accessible_leads.filter(
                assigned_user__in=team_agents,
                status='sale_done'
            ).count()
            team_performance.append({
                'team_lead': team_lead,
                'total_leads': team_leads_count,
                'converted': team_converted,
                'conversion_rate': (team_converted / team_leads_count * 100) if team_leads_count > 0 else 0,
            })
        
        role_context.update({
            'team_leads_count': team_leads.count(),
            'team_performance': team_performance,
        })
    
    context = {
        'user': request.user,
        'role': request.user.get_role_display(),
        'greeting_time': greeting_time,
        'total_leads': total_leads,
        'today_follow_ups': today_follow_ups,
        'expected_revenue': exp_revenue,
        'actual_revenue': course_amount_total,
        'leads_by_status': leads_by_status,
        **role_context,  # Add role-specific metrics
    }
    return render(request, 'dashboard/home.html', context)

@login_required
def profile(request):
    return render(request, 'dashboard/profile.html')

@login_required
@hierarchy_required
def leads_list(request):
    leads = request.hierarchy_context['accessible_leads']
    status_filter = request.GET.get('status')
    sort_by = request.GET.get('sort', '-created_at')  # Default: newest first
    page_size = request.GET.get('page_size', '25')
    search_query = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    course_filter = request.GET.get('course', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    assigned_user_filter = request.GET.get('assigned_user', '').strip()
    preset_filter = request.GET.get('preset', '').strip()
    
    # Validate page size
    valid_page_sizes = ['5', '10', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '25'
    page_size = int(page_size)
    
    # Apply search filter
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    
    # Apply country filter
    if country_filter:
        leads = leads.filter(country__icontains=country_filter)
    
    # Apply course filter
    if course_filter:
        leads = leads.filter(course_name__icontains=course_filter)
    
    # Apply date range filter
    if start_date:
        from datetime import datetime
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            leads = leads.filter(created_at__date__gte=start_date_obj)
        except ValueError:
            pass  # Invalid date format, ignore filter
    
    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            leads = leads.filter(created_at__date__lte=end_date_obj)
        except ValueError:
            pass  # Invalid date format, ignore filter
    
    # Apply assigned user filter
    if assigned_user_filter:
        try:
            assigned_user_id = int(assigned_user_filter)
            leads = leads.filter(assigned_user_id=assigned_user_id)
        except ValueError:
            pass  # Invalid user ID, ignore filter
    
    # Handle preset filters
    if preset_filter == 'my_team':
        # Filter leads assigned to user's team members
        if request.user.role in ['manager', 'owner']:
            team_members = request.user.get_accessible_users()
            leads = leads.filter(assigned_user__in=team_members)
        elif request.user.role == 'team_lead':
            team_agents = request.user.get_accessible_users()
            leads = leads.filter(assigned_user__in=team_agents)
        else:  # agent - filter by their own leads only
            leads = leads.filter(assigned_user=request.user)
    elif preset_filter == 'my':
        # Filter leads assigned to current user
        leads = leads.filter(assigned_user=request.user)
    
    # Apply sorting
    valid_sort_fields = {
        'created_at': 'created_at',
        '-created_at': '-created_at',
        'name': 'name',
        '-name': '-name',
        'status': 'status',
        '-status': '-status',
        'assigned_user': 'assigned_user__username',
        '-assigned_user': '-assigned_user__username',
        'priority': 'priority',
        '-priority': '-priority',
    }
    
    if sort_by in valid_sort_fields:
        leads = leads.order_by(valid_sort_fields[sort_by])
    else:
        leads = leads.order_by('-created_at')  # Default: newest first
    
    # Optimize query with select_related
    leads = leads.select_related('assigned_user', 'created_by')
    
    # Pagination with configurable page size
    paginator = Paginator(leads, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'All Leads',
        'current_sort': sort_by,
        'current_page_size': page_size,
        'search_query': search_query,
        'country_filter': country_filter,
        'course_filter': course_filter,
        'start_date': start_date,
        'end_date': end_date,
        'assigned_user_filter': assigned_user_filter,
        'active_filters_count': len([filter for filter in [country_filter, course_filter, start_date, end_date, assigned_user_filter] if filter]),
        'sort_options': [
            ('-created_at', 'Newest First'),
            ('created_at', 'Oldest First'),
            ('name', 'Name (A-Z)'),
            ('-name', 'Name (Z-A)'),
            ('status', 'Status (A-Z)'),
            ('-status', 'Status (Z-A)'),
            ('-priority', 'High Priority First'),
            ('priority', 'Low Priority First'),
            ('assigned_user__username', 'Assigned User (A-Z)'),
            ('-assigned_user__username', 'Assigned User (Z-A)'),
        ]
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_fresh(request):
    # Fresh leads - show leads assigned to the current user
    page_size = request.GET.get('page_size', '25')
    search_query = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    course_filter = request.GET.get('course', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    assigned_user_filter = request.GET.get('assigned_user', '').strip()
    preset_filter = request.GET.get('preset', '').strip()
    
    # Validate page size
    valid_page_sizes = ['5', '10', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '25'
    page_size = int(page_size)
    
    accessible_leads = request.hierarchy_context['accessible_leads']
    
    # Get leads assigned to the current user, exclude sale_done leads
    leads = accessible_leads.filter(assigned_user=request.user).exclude(status='sale_done').select_related('created_by', 'assigned_user')
    
    # Apply search filter
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    
    # Pagination with configurable page size
    paginator = Paginator(leads, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'New Leads',
        'current_page_size': page_size,
        'search_query': search_query,
        'active_filters_count': len([filter for filter in [country_filter, course_filter, start_date, end_date, assigned_user_filter] if filter]),
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_working(request):
    # Leads assigned to current user and not converted
    page_size = request.GET.get('page_size', '25')
    search_query = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    course_filter = request.GET.get('course', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    assigned_user_filter = request.GET.get('assigned_user', '').strip()
    
    # Validate page size
    valid_page_sizes = ['5', '10', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '25'
    page_size = int(page_size)
    
    leads = request.hierarchy_context['accessible_leads'].filter(
        assigned_user=request.user
    ).exclude(status='sale_done').select_related('assigned_user', 'created_by')
    
    # Apply search filter
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    
    # Pagination with configurable page size
    paginator = Paginator(leads, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'My Working Leads',
        'current_page_size': page_size,
        'search_query': search_query,
        'active_filters_count': len([filter for filter in [country_filter, course_filter, start_date, end_date, assigned_user_filter] if filter]),
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_transferred(request):
    """Leads that were transferred by or to users in the current user's hierarchy"""
    accessible_leads = request.hierarchy_context['accessible_leads']
    page_size = request.GET.get('page_size', '25')
    search_query = request.GET.get('search', '').strip()
    country_filter = request.GET.get('country', '').strip()
    course_filter = request.GET.get('course', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    assigned_user_filter = request.GET.get('assigned_user', '').strip()
    
    # Validate page size
    valid_page_sizes = ['5', '10', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '25'
    page_size = int(page_size)
    
    # Get leads that have been transferred (have transfer_date not null)
    transferred_leads = accessible_leads.filter(
        transfer_date__isnull=False
    ).select_related('assigned_user', 'created_by', 'assigned_by')
    
    # For different roles, we might want to show different perspectives
    if request.user.role == 'owner':
        # Owner sees all transfers in the company
        transferred_leads = transferred_leads.filter(company_id=request.user.company_id)
    elif request.user.role == 'manager':
        # Manager sees transfers involving their team leads and agents
        team_users = request.user.get_accessible_users()
        transferred_leads = transferred_leads.filter(
            Q(assigned_user__in=team_users) |
            Q(transfer_by__in=team_users.values('username')) |
            Q(created_by__in=team_users)
        )
    elif request.user.role == 'team_lead':
        # Team Lead sees transfers involving their agents
        team_agents = request.user.get_accessible_users()
        transferred_leads = transferred_leads.filter(
            Q(assigned_user__in=team_agents) |
            Q(transfer_by__in=team_agents.values('username')) |
            Q(created_by__in=team_agents)
        )
    else:  # agent
        # Agent sees transfers of their own leads
        transferred_leads = transferred_leads.filter(
            Q(assigned_user=request.user) |
            Q(created_by=request.user)
        )
    
    # Apply search filter
    if search_query:
        transferred_leads = transferred_leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    
    # Pagination with configurable page size
    paginator = Paginator(transferred_leads, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'Transferred Leads',
        'current_page_size': page_size,
        'search_query': search_query,
        'active_filters_count': len([filter for filter in [country_filter, course_filter, start_date, end_date, assigned_user_filter] if filter]),
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_converted(request):
    # Leads with sale_done status within user's hierarchy
    page_size = request.GET.get('page_size', '25')
    search_query = request.GET.get('search', '').strip()
    
    # Validate page size
    valid_page_sizes = ['5', '10', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '25'
    page_size = int(page_size)
    
    leads = request.hierarchy_context['accessible_leads'].filter(
        status='sale_done'
    ).select_related('assigned_user', 'created_by')
    
    country_filter = request.GET.get('country', '').strip()
    course_filter = request.GET.get('course', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    assigned_user_filter = request.GET.get('assigned_user', '').strip()
    
    # Apply search filter
    if search_query:
        leads = leads.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    
    # Pagination with configurable page size
    paginator = Paginator(leads, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'Converted Leads',
        'current_page_size': page_size,
        'search_query': search_query,
        'active_filters_count': len([filter for filter in [country_filter, course_filter, start_date, end_date, assigned_user_filter] if filter]),
    }
    return render(request, 'dashboard/leads_list.html', context)


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
    # Leads assigned to team members based on hierarchy
    if request.user.role in ['owner', 'manager', 'team_lead']:
        accessible_users = request.hierarchy_context['accessible_users']
        leads = request.hierarchy_context['accessible_leads'].filter(
            assigned_user__in=accessible_users
        )
    else:
        leads = Lead.objects.none()
    
    context = {
        'leads': leads,
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'My Team Leads',
        'active_filters_count': 0,  # Team leads view doesn't have filters
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@can_access_lead_required
def lead_detail(request, pk):
    lead = request.current_lead  # Set by the decorator
    
    # Fetch comprehensive history data
    activities = lead.activities.all()
    lead_history = lead.history.all()
    communications = lead.communications.all()
    bo_updates = lead.bo_updates.all()
    comments = lead.comments.all()
    
    # Parse assignment history from JSON field
    assignment_history = []
    if lead.assignment_history and 'assignments' in lead.assignment_history:
        assignment_data = lead.assignment_history['assignments']
        for assignment in assignment_data:
            # Get user objects for assignment details
            from_user = None
            to_user = None
            by_user = None
            
            try:
                if assignment.get('from', {}).get('user'):
                    from_user = User.objects.get(id=assignment['from']['user'])
                if assignment.get('to', {}).get('user'):
                    to_user = User.objects.get(id=assignment['to']['user'])
                if assignment.get('by'):
                    by_user = User.objects.get(id=assignment['by'])
            except User.DoesNotExist:
                continue
            
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
def reports(request):
    return render(request, 'dashboard/reports.html')

@login_required
def settings(request):
    return render(request, 'dashboard/settings.html')


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
                lead.assign_to_user(assigned_user, request.user)
                
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
            
            for lead in accessible_leads:
                try:
                    # Check if user can assign this lead
                    can_assign = lead.can_be_assigned_by(request.user)
                    can_assign_to_target = lead.can_be_assigned_to_user(assigned_user, request.user)
                    
                    if can_assign and can_assign_to_target:
                        # Assign the lead
                        try:
                            lead.assign_to_user(assigned_user, request.user)
                            
                            # Create assignment history record
                            LeadHistory.objects.create(
                                lead=lead,
                                user=request.user,
                                field_name='assigned_user',
                                old_value=lead.assigned_user.username if lead.assigned_user else None,
                                new_value=assigned_user.username,
                                action=f'Bulk assigned to {assigned_user.username}'
                            )
                            
                            # Create activity log
                            LeadActivity.objects.create(
                                lead=lead,
                                user=request.user,
                                activity_type='bulk_assignment',
                                description=f'Bulk assigned to {assigned_user.username}. {assignment_notes}'
                            )
                            
                            successful_assignments += 1
                        except Exception as assign_error:
                            print(f"Error assigning lead {lead.name}: {assign_error}")
                            failed_assignments += 1
                    else:
                        failed_assignments += 1
                except Exception as e:
                    failed_assignments += 1
            
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
@csrf_exempt
def lead_import(request):
    """Import leads from CSV/Excel file with enhanced duplicate detection - only owners can import leads"""
    # Only owners can import leads
    if request.user.role != 'owner':
        messages.error(request, "You don't have permission to import leads. Only owners can import leads.")
        return redirect("dashboard:leads_all")
    
    if request.method == "POST":
        form = LeadImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            
            try:
                # Read the file content first to check if it's empty
                file_content = file.read()
                if not file_content.strip():
                    messages.error(request, "File is empty. Please upload a file with data.")
                    return render(request, 'dashboard/lead_import.html', {'form': form})
                
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
                
                # Check if dataframe is empty
                if df.empty:
                    messages.error(request, "No data found in file. Please check file content.")
                    return render(request, 'dashboard/lead_import.html', {'form': form})
                
                # Check if dataframe has columns
                if len(df.columns) == 0:
                    messages.error(request, "No columns found in file. Please check CSV format and headers.")
                    return render(request, 'dashboard/lead_import.html', {'form': form})
                
                # Validate required columns
                required_columns = ['name', 'mobile']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    messages.error(request, f"Missing required columns: {', '.join(missing_columns)}")
                    return render(request, 'dashboard/lead_import.html', {'form': form})
                
                # Step 2: Duplicate Detection
                # Convert DataFrame to list of dictionaries
                leads_data = []
                for index, row in df.iterrows():
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
                        'campaign_id': str(row.get('campaign_id', '')).strip(),
                        'course_name': str(row.get('course_name', '')).strip(),
                        'course_amount': str(row.get('course_amount', '')).strip(),
                        'exp_revenue': str(row.get('exp_revenue', '')).strip(),
                        'description': str(row.get('description', '')).strip(),
                        'company': str(row.get('company', '')).strip(),  # For related lead detection
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
                
                # Store results in session for preview
                request.session['import_data'] = {
                    'leads_data': leads_data,
                    'duplicate_results': duplicate_results,
                    'file_name': file.name,
                }
                
                # Redirect to preview page
                return redirect("dashboard:lead_import_preview")
                
            except Exception as e:
                print(f"Import error: {e}")
                import traceback
                traceback.print_exc()
                messages.error(request, f"Error processing file: {str(e)}. Please check file format and encoding.")
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
    
    # Get import data from session
    import_data = request.session.get('import_data')
    if not import_data:
        messages.error(request, "No import data found. Please upload a file first.")
        return redirect("dashboard:lead_import")
    
    leads_data = import_data['leads_data']
    duplicate_results = import_data['duplicate_results']
    file_name = import_data['file_name']
    
    # Calculate summary statistics
    summary = {
        'total': len(duplicate_results),
        'new': len([r for r in duplicate_results if r['status'] == 'new']),
        'exact_duplicates': len([r for r in duplicate_results if r['status'] == 'exact_duplicate']),
        'potential_duplicates': len([r for r in duplicate_results if r['status'] == 'potential_duplicate']),
        'related': len([r for r in duplicate_results if r['status'] == 'related']),
    }
    
    # Prepare table data with additional info
    table_data = []
    for result in duplicate_results:
        lead_data = result['lead_data']
        row = {
            'row_index': result['row_index'],
            'name': lead_data['name'],
            'mobile': lead_data['mobile'],
            'email': lead_data['email'],
            'status': result['status'],
            'duplicate_type': result['duplicate_type'],
            'confidence': result['confidence'],
            'duplicates': result['duplicates'],
            'action': 'import' if result['status'] == 'new' else 'skip',
            'selected': result['status'] == 'new',  # Auto-select new leads
        }
        table_data.append(row)
    
    context = {
        'page_title': 'Import Preview',
        'file_name': file_name,
        'summary': summary,
        'table_data': table_data,
        'leads_data': leads_data,
        'duplicate_results': duplicate_results,
    }
    
    return render(request, 'dashboard/lead_import_preview.html', context)


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
    
    # Get import data from session
    import_data = request.session.get('import_data')
    if not import_data:
        messages.error(request, "No import data found. Please upload a file first.")
        return redirect("dashboard:lead_import")
    
    leads_data = import_data['leads_data']
    duplicate_results = import_data['duplicate_results']
    
    # Get user decisions
    actions = request.POST.getlist('actions')
    selected_rows = request.POST.getlist('selected_rows')
    
    # Process import
    imported_count = 0
    skipped_count = 0
    updated_count = 0
    
    for i, result in enumerate(duplicate_results):
        lead_data = result['lead_data']
        
        # Determine action for this lead
        if str(i) in selected_rows:
            action = actions[i] if i < len(actions) else 'import'
        else:
            action = 'skip'
        
        if action == 'skip':
            skipped_count += 1
            continue
        
        try:
            if action == 'import' and result['status'] == 'new':
                # Create new lead
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
                    company_id=request.user.company_id,
                    created_by=request.user,
                    assigned_user=None,  # Leave unassigned by default
                    duplicate_status=result['status'],
                    duplicate_info=result,
                )
                
                # Handle date fields
                if 'exp_close_date' in lead_data:
                    lead.exp_close_date = lead_data['exp_close_date']
                if 'followup_datetime' in lead_data:
                    lead.followup_datetime = lead_data['followup_datetime']
                if 'birthdate' in lead_data:
                    lead.birthdate = lead_data['birthdate']
                
                lead.save()
                imported_count += 1
                
                # Log activity
                LeadActivity.objects.create(
                    lead=lead,
                    user=request.user,
                    activity_type='import',
                    description=f'Lead imported from {import_data["file_name"]}'
                )
            
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
                        description=f'Lead updated during import from {import_data["file_name"]}'
                    )
        
        except Exception as e:
            print(f"Error processing lead {i}: {e}")
            skipped_count += 1
            continue
    
    # Clear session data
    if 'import_data' in request.session:
        del request.session['import_data']
    
    # Show results
    if imported_count > 0:
        messages.success(request, f"Successfully imported {imported_count} new leads.")
    if updated_count > 0:
        messages.info(request, f"Updated {updated_count} existing leads.")
    if skipped_count > 0:
        messages.warning(request, f"Skipped {skipped_count} leads.")
    
    return redirect("dashboard:leads_all")


# Lead Status and History Views
@login_required
@can_access_lead_required
def lead_status_update(request, pk):
    """Update lead status with history tracking"""
    lead = request.current_lead
    
    # Check if user can modify this lead
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    if not can_modify:
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
                    action='Status Updated',
                    description=updated_lead.status_description
                )
                
                # Create activity log
                LeadActivity.objects.create(
                    lead=lead,
                    user=request.user,
                    activity_type='status_change',
                    description=f'Status changed from {old_status} to {updated_lead.status}'
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
    detector = DuplicateDetector(request.user.company_id)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get filter parameters
    status_filter = request.GET.get('status', 'pending')
    duplicate_type = request.GET.get('type', '')
    
    # Get duplicate groups
    groups = detector.find_duplicate_groups(status_filter)
    
    # Filter by duplicate type if specified
    if duplicate_type:
        filtered_groups = []
        for group in groups:
            group_has_type = any(
                lead.duplicate_status == duplicate_type 
                for lead in group['leads']
            )
            if group_has_type:
                filtered_groups.append(group)
        groups = filtered_groups
    
    # Sort groups by creation date (newest first)
    groups.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Get statistics
    stats = detector.get_duplicate_statistics()
    
    # Pagination with configurable page size
    paginator = Paginator(groups, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'groups': page_obj,
        'stats': stats,
        'status_filter': status_filter,
        'duplicate_type': duplicate_type,
        'page_title': 'Duplicate Leads',
        'current_page_size': page_size,
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
    detector = DuplicateDetector(request.user.company_id)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get duplicate groups based on user role
    if request.user.role == 'owner':
        groups = detector.find_duplicate_groups()
    elif request.user.role == 'manager':
        # Get groups for manager's team
        team_users = request.user.get_accessible_users()
        groups = []
        all_groups = detector.find_duplicate_groups()
        for group in all_groups:
            # Check if any lead in group belongs to manager's team
            if any(lead.assigned_user in team_users for lead in group['leads']):
                groups.append(group)
    elif request.user.role == 'team_lead':
        # Get groups for team lead's agents
        team_agents = request.user.get_accessible_users()
        groups = []
        all_groups = detector.find_duplicate_groups()
        for group in all_groups:
            # Check if any lead in group belongs to team lead's agents
            if any(lead.assigned_user in team_agents for lead in group['leads']):
                groups.append(group)
    else:  # agent
        # Get groups for agent's own leads
        groups = []
        all_groups = detector.find_duplicate_groups()
        for group in all_groups:
            # Check if any lead in group belongs to agent
            if any(lead.assigned_user == request.user for lead in group['leads']):
                groups.append(group)
    
    # Sort groups by creation date (newest first)
    groups.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Get team statistics
    team_stats = {}
    if request.user.role in ['owner', 'manager']:
        team_users = request.user.get_accessible_users() if request.user.role == 'manager' else User.objects.filter(company_id=request.user.company_id)
        
        for user in team_users:
            user_groups = []
            for group in groups:
                if any(lead.assigned_user == user for lead in group['leads']):
                    user_groups.append(group)
            
            team_stats[user.username] = {
                'groups_count': len(user_groups),
                'leads_count': sum(len(group['leads']) for group in user_groups),
                'pending_count': len([g for g in user_groups if g['status'] == 'pending']),
                'resolved_count': len([g for g in user_groups if g['status'] == 'resolved'])
            }
    
    # Pagination with configurable page size
    paginator = Paginator(groups, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'groups': page_obj,
        'team_stats': team_stats,
        'page_title': 'Team Duplicate Leads',
        'current_page_size': page_size,
        'show_team_stats': request.user.role in ['owner', 'manager']
    }
    return render(request, 'dashboard/team_duplicates.html', context)


@login_required
@hierarchy_required
def my_duplicate_leads(request):
    """Current user's duplicate leads"""
    detector = DuplicateDetector(request.user.company_id)
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Get groups that contain user's leads
    all_groups = detector.find_duplicate_groups()
    my_groups = []
    
    for group in all_groups:
        if any(lead.assigned_user == request.user for lead in group['leads']):
            my_groups.append(group)
    
    # Sort groups by creation date (newest first)
    my_groups.sort(key=lambda x: x['created_at'], reverse=True)
    
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
        'groups_count': len(my_groups)
    }
    
    # Pagination with configurable page size
    paginator = Paginator(my_groups, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'groups': page_obj,
        'my_stats': user_stats,
        'page_title': 'My Duplicate Leads',
        'current_page_size': page_size
    }
    return render(request, 'dashboard/my_duplicates.html', context)

