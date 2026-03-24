from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q, F
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.core.paginator import Paginator
from django.views.decorators.csrf import csrf_exempt
import pandas as pd
import json
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
    
    if status_filter:
        leads = leads.filter(status=status_filter)
    
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
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(leads, 25)  # 25 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'All Leads',
        'current_sort': sort_by,
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
    # Fresh leads - unassigned leads created within last 7 days, excluding sale_done leads
    from datetime import timedelta
    seven_days_ago = timezone.now() - timedelta(days=7)
    leads = request.hierarchy_context['accessible_leads'].filter(
        created_at__gte=seven_days_ago,
        assigned_user__isnull=True  # Only unassigned leads
    ).exclude(status='sale_done').select_related('created_by')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(leads, 25)  # 25 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'New Leads',
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_working(request):
    # Leads assigned to current user and not converted
    leads = request.hierarchy_context['accessible_leads'].filter(
        assigned_user=request.user
    ).exclude(status='sale_done').select_related('assigned_user', 'created_by')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(leads, 25)  # 25 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'My Working Leads',
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_transferred(request):
    """Leads that were transferred by or to users in the current user's hierarchy"""
    accessible_leads = request.hierarchy_context['accessible_leads']
    
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
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(transferred_leads, 25)  # 25 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'Transferred Leads',
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@hierarchy_required
def leads_converted(request):
    # Leads with sale_done status within user's hierarchy
    leads = request.hierarchy_context['accessible_leads'].filter(
        status='sale_done'
    ).select_related('assigned_user', 'created_by')
    
    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(leads, 25)  # 25 leads per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'status_choices': Lead.STATUS_CHOICES,
        'page_title': 'Converted Leads',
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
    }
    return render(request, 'dashboard/leads_list.html', context)

@login_required
@can_access_lead_required
def lead_detail(request, pk):
    lead = request.current_lead  # Set by the decorator
    activities = lead.activities.all()
    
    # Check if user can modify this lead
    can_modify = lead.can_be_assigned_by(request.user) or lead.assigned_user == request.user
    
    context = {
        'lead': lead,
        'activities': activities,
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

