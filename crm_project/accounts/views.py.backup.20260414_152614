from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from django.http import QueryDict
from django.core.paginator import Paginator
from datetime import datetime
import uuid
from .models import User, BulkAssignmentUndo
from dashboard.models import Lead, LeadOperationLog
from .permissions import role_required, can_manage_user_required, hierarchy_required
from .forms import UserCreationForm, UserAssignmentForm, UserEditForm


def _apply_lead_snapshot_filters(queryset, user, filter_snapshot):
    params = QueryDict(filter_snapshot or '', mutable=False)

    search_query = params.get('search', '').strip()
    country_filter = params.get('country', '').strip()
    course_filter = params.get('course', '').strip()
    start_date = params.get('start_date', '').strip()
    end_date = params.get('end_date', '').strip()
    assigned_user_filter = params.get('assigned_user', '').strip()
    status_filter = params.get('status', '').strip()
    preset_filter = params.get('preset', '').strip()

    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if search_query:
        queryset = queryset.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(mobile__icontains=search_query) |
            Q(alt_mobile__icontains=search_query) |
            Q(alt_email__icontains=search_query)
        )
    if country_filter:
        queryset = queryset.filter(country__icontains=country_filter)
    if course_filter:
        queryset = queryset.filter(course_name__icontains=course_filter)

    if start_date:
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
            queryset = queryset.filter(
                Q(created_at__date__gte=start_date_obj) |
                Q(assigned_at__date__gte=start_date_obj) |
                Q(transfer_date__date__gte=start_date_obj)
            )
        except ValueError:
            pass

    if end_date:
        try:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            queryset = queryset.filter(
                Q(created_at__date__lte=end_date_obj) |
                Q(assigned_at__date__lte=end_date_obj) |
                Q(transfer_date__date__lte=end_date_obj)
            )
        except ValueError:
            pass

    if assigned_user_filter:
        try:
            queryset = queryset.filter(assigned_user_id=int(assigned_user_filter))
        except ValueError:
            pass

    if preset_filter == 'my_team':
        if user.role in ['manager', 'owner', 'team_lead']:
            queryset = queryset.filter(assigned_user__in=user.get_accessible_users())
        else:
            queryset = queryset.filter(assigned_user=user)
    elif preset_filter == 'my':
        queryset = queryset.filter(assigned_user=user)

    return queryset

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Check if user is blocked/inactive
            if not user.is_active or user.account_status == 'inactive':
                messages.error(request, 'Your account has been blocked by the administrator. Please contact your admin.')
                return redirect('accounts:login')
            
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('dashboard:home')
        else:
            # Check if user exists
            try:
                user_obj = User.objects.get(username=username)
                # Check if user is blocked/inactive
                if not user_obj.is_active or user_obj.account_status == 'inactive':
                    messages.error(request, 'Your account has been blocked by the administrator. Please contact your admin.')
                else:
                    messages.error(request, 'Invalid username or password.')
            except User.DoesNotExist:
                messages.error(request, 'Invalid username or password.')
    
    return render(request, 'accounts/login.html')

@login_required
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('accounts:login')

@login_required
@hierarchy_required
def user_list(request):
    """List users based on hierarchy"""
    accessible_users = request.hierarchy_context['accessible_users']
    page_size = request.GET.get('page_size', '20')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '20'
    page_size = int(page_size)
    
    # Optimize query with select_related for manager and team_lead
    accessible_users = accessible_users.select_related('manager', 'team_lead')
    
    # Filter by role if specified
    role_filter = request.GET.get('role')
    if role_filter:
        accessible_users = accessible_users.filter(role=role_filter)
    
    # Filter by status if specified
    status_filter = request.GET.get('status')
    if status_filter:
        accessible_users = accessible_users.filter(account_status=status_filter)
    
    # Pagination with configurable page size
    paginator = Paginator(accessible_users, page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'users': page_obj,  # Keep for backward compatibility
        'role_choices': User.ROLE_CHOICES,
        'status_choices': User.ACCOUNT_STATUS_CHOICES,
        'page_title': 'Users',
        'current_page_size': page_size,
    }
    return render(request, 'accounts/user_list.html', context)

@login_required
@role_required('owner', 'manager', 'team_lead')
def create_user(request):
    """Create new user based on hierarchy rules"""
    if request.method == 'POST':
        form = UserCreationForm(request.POST, user=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('accounts:user_list')
    else:
        form = UserCreationForm(user=request.user)
    
    context = {
        'form': form,
        'page_title': 'Create User',
    }
    return render(request, 'accounts/create_user.html', context)

@login_required
@can_manage_user_required
def edit_user(request, user_id):
    """Edit user details with role-based permissions"""
    target_user = get_object_or_404(User, id=user_id, company_id=request.user.company_id)
    
    # Additional permission check: users can edit their own profile
    if target_user != request.user:
        if not request.user.can_manage_user(target_user):
            messages.error(request, 'You do not have permission to edit this user.')
            return redirect('accounts:user_list')
    
    if request.method == 'POST':
        form = UserEditForm(
            request.POST, 
            editor=request.user, 
            target_user=target_user,
            instance=target_user
        )
        
        if form.is_valid():
            try:
                updated_user = form.save()
                messages.success(request, f'User {updated_user.username} updated successfully.')
                return redirect('accounts:user_list')
            except Exception as e:
                messages.error(request, f'Error updating user: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserEditForm(
            editor=request.user, 
            target_user=target_user,
            instance=target_user
        )
    
    context = {
        'form': form,
        'target_user': target_user,
        'status_choices': User.ACCOUNT_STATUS_CHOICES,
        'page_title': f'Edit {target_user.username}',
        'can_edit_role': form._can_edit_role() if hasattr(form, '_can_edit_role') else False,
        'can_edit_hierarchy': form._can_edit_hierarchy() if hasattr(form, '_can_edit_hierarchy') else False,
        'can_edit_status': form._can_edit_status() if hasattr(form, '_can_edit_status') else False,
    }
    return render(request, 'accounts/edit_user.html', context)

@login_required
@hierarchy_required
def assign_lead(request):
    """Assign leads to team members following hierarchy rules"""
    accessible_users = request.hierarchy_context['accessible_users']
    accessible_leads = request.hierarchy_context['accessible_leads']
    
    if request.method == 'POST':
        form = UserAssignmentForm(request.POST, user=request.user)
        if form.is_valid():
            lead_id = form.cleaned_data['lead']
            assigned_user = form.cleaned_data['assigned_user']
            remarks = form.cleaned_data.get('remarks', '')
            
            # Get the lead and verify access
            try:
                lead = accessible_leads.get(id_lead=lead_id)
                
                # Verify hierarchy assignment rules
                if not lead.can_be_assigned_by(request.user):
                    messages.error(request, 'You cannot assign this lead due to hierarchy restrictions.')
                    return redirect('dashboard:leads_all')
                
                # Assign the lead
                success = lead.assign_to_user(assigned_user, request.user)
                if success:
                    messages.success(request, f'Lead "{lead.name}" has been assigned to {assigned_user.get_full_name() or assigned_user.username}.')
                    
                    # Add remarks to assignment history if provided
                    if remarks:
                        assignment_history = lead.assignment_history or {}
                        if not isinstance(assignment_history, dict):
                            assignment_history = {'assignments': []}
                        assignment_history.setdefault('assignments', []).append({
                            'action': 'assignment_with_remarks',
                            'assigned_to': assigned_user.id,
                            'assigned_to_name': assigned_user.get_full_name() or assigned_user.username,
                            'assigned_by': request.user.id,
                            'assigned_by_name': request.user.get_full_name() or request.user.username,
                            'assigned_at': timezone.now().isoformat(),
                            'remarks': remarks
                        })
                        lead.assignment_history = assignment_history
                        lead.save()
                else:
                    messages.error(request, 'Failed to assign lead. Please check hierarchy permissions.')
                    
            except Lead.DoesNotExist:
                messages.error(request, 'Lead not found or you do not have permission to assign it.')
        
        return redirect('dashboard:leads_all')
    
    # GET request - show assignment form
    lead_id = request.GET.get('lead_id')
    lead = None
    users = []
    
    # Filter out deactivated users from accessible users
    active_accessible_users = accessible_users.filter(
        is_active=True,
        account_status='active'
    )
    
    if lead_id:
        try:
            lead = accessible_leads.get(id_lead=lead_id)
            # Filter users based on hierarchy rules and active status
            users = [user for user in active_accessible_users if lead.can_be_assigned_to_user(user, request.user)]
        except Lead.DoesNotExist:
            messages.error(request, 'Lead not found.')
            return redirect('dashboard:leads_all')
    else:
        users = active_accessible_users
    
    form = UserAssignmentForm(user=request.user, initial={'lead': lead})
    context = {
        'form': form,
        'lead': lead,
        'users': users,
        'page_title': 'Assign Lead',
    }
    return render(request, 'accounts/assign_lead.html', context)

@login_required
@hierarchy_required
def get_users_by_role(request):
    """AJAX endpoint to get users filtered by role and/or search"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        role = request.GET.get('role', '').strip()
        search_query = request.GET.get('search', '').strip()
        exclude_user_id = request.GET.get('exclude_user_id')
        accessible_users = request.hierarchy_context['accessible_users']
        
        # Base queryset of active users
        active_users = accessible_users.filter(
            is_active=True,
            account_status='active'
        )
        
        # Apply role filter if provided
        if role:
            active_users = active_users.filter(role=role)
        
        # Apply search filter if provided
        if search_query:
            from django.db.models import Q, Case, When, Value, IntegerField
            search_conditions = (
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query)
            )
            active_users = active_users.filter(search_conditions)
            
            # Order by relevance when searching
            active_users = active_users.annotate(
                relevance=Case(
                    When(Q(username__iexact=search_query), then=Value(4)),
                    When(Q(first_name__iexact=search_query), then=Value(3)),
                    When(Q(last_name__iexact=search_query), then=Value(3)),
                    When(Q(email__iexact=search_query), then=Value(3)),
                    default=Value(1),
                    output_field=IntegerField()
                )
            ).order_by('-relevance', 'first_name', 'last_name')
        else:
            # Order alphabetically when not searching
            active_users = active_users.order_by('first_name', 'last_name')
        
        # Exclude specific user if needed
        if exclude_user_id:
            active_users = active_users.exclude(id=exclude_user_id)
        
        users = active_users.select_related('manager', 'team_lead')
        
        user_data = []
        for user in users:
            # Get real-time lead counts
            leads_assigned_count = Lead.objects.filter(
                assigned_user=user,
                company_id=request.user.company_id
            ).count()
            
            leads_converted_count = Lead.objects.filter(
                assigned_user=user,
                company_id=request.user.company_id,
                status='sale_done'
            ).count()
            
            user_data.append({
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'full_name': user.get_full_name() or user.username,
                'role': user.role,
                'role_display': user.get_role_display(),
                'leads_assigned_count': leads_assigned_count,
                'leads_converted_count': leads_converted_count,
                'profile_picture': user.profile_picture.url if user.profile_picture else None,
            })
        
        return JsonResponse({'users': user_data})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@hierarchy_required
def bulk_assign_leads(request):
    """Bulk assign multiple leads to team members"""
    accessible_users = request.hierarchy_context['accessible_users']
    accessible_leads = request.hierarchy_context['accessible_leads']
    
    if request.method == 'POST':
        assigned_user_id = request.POST.get('assigned_user')
        lead_ids = request.POST.getlist('lead_ids')
        remarks = request.POST.get('remarks', '') or request.POST.get('assignment_notes', '')
        action_scope = request.POST.get('action_scope', 'current_page').strip() or 'current_page'
        filter_snapshot = request.POST.get('filter_snapshot', '')
        
        if action_scope == 'current_page' and not lead_ids:
            messages.error(request, 'Please select at least one lead to assign.')
            return redirect('accounts:bulk_assign')
        
        try:
            assigned_user = accessible_users.get(id=assigned_user_id)
            
            # Verify user is active and can be assigned to
            if not assigned_user.is_active or assigned_user.account_status != 'active':
                messages.error(request, 'Cannot assign leads to deactivated user.')
                return redirect('accounts:bulk_assign')
            
            # Verify user can assign to this person
            if not request.user.can_manage_user(assigned_user):
                messages.error(request, 'You cannot assign leads to this user due to hierarchy restrictions.')
                return redirect('accounts:bulk_assign')
            
            if action_scope == 'all_filtered':
                target_leads_qs = _apply_lead_snapshot_filters(
                    accessible_leads.filter(deleted=False),
                    request.user,
                    filter_snapshot
                )
            else:
                target_leads_qs = accessible_leads.filter(id_lead__in=lead_ids, deleted=False)

            if not target_leads_qs.exists():
                messages.error(request, 'No leads found for bulk assignment in selected scope.')
                return redirect('dashboard:leads_all')

            successful_assignments = 0
            failed_assignments = 0
            assigned_lead_ids = []
            
            for lead in target_leads_qs:
                try:
                    if lead.can_be_assigned_by(request.user) and lead.can_be_assigned_to_user(assigned_user, request.user):
                        success = lead.assign_to_user(assigned_user, request.user)
                        if success:
                            successful_assignments += 1
                            assigned_lead_ids.append(lead.id_lead)
                            
                            # Add remarks to assignment history if provided
                            if remarks:
                                assignment_history = lead.assignment_history or {}
                                if not isinstance(assignment_history, dict):
                                    assignment_history = {'assignments': []}
                                assignment_history.setdefault('assignments', []).append({
                                    'action': 'bulk_assignment_with_remarks',
                                    'assigned_to': assigned_user.id,
                                    'assigned_to_name': assigned_user.get_full_name() or assigned_user.username,
                                    'assigned_by': request.user.id,
                                    'assigned_by_name': request.user.get_full_name() or request.user.username,
                                    'assigned_at': timezone.now().isoformat(),
                                    'remarks': remarks
                                })
                                lead.assignment_history = assignment_history
                                lead.save()
                        else:
                            failed_assignments += 1
                    else:
                        failed_assignments += 1
                        
                except Lead.DoesNotExist:
                    failed_assignments += 1
            
            if successful_assignments > 0:
                messages.success(request, f'Successfully assigned {successful_assignments} leads to {assigned_user.get_full_name() or assigned_user.username}.')
            
            if failed_assignments > 0:
                messages.warning(request, f'Failed to assign {failed_assignments} leads due to permission restrictions.')

            LeadOperationLog.objects.create(
                operation_id=f"bulk_assign_{uuid.uuid4().hex[:14]}",
                operation_type='bulk_assign',
                user=request.user,
                company_id=request.user.company_id,
                action_scope=action_scope,
                filter_snapshot=filter_snapshot,
                requested_count=target_leads_qs.count(),
                processed_count=successful_assignments + failed_assignments,
                success_count=successful_assignments,
                failed_count=failed_assignments,
                metadata={'assigned_user_id': assigned_user.id},
            )
            
            # Create BulkAssignmentUndo record if any assignments were successful
            if successful_assignments > 0 and assigned_lead_ids:
                BulkAssignmentUndo.objects.create(
                    assigned_by=request.user,
                    assigned_to=assigned_user,
                    lead_ids=','.join(map(str, assigned_lead_ids)),
                    assignment_count=successful_assignments
                )
                
        except User.DoesNotExist:
            messages.error(request, 'Selected user not found.')
        
        return redirect('dashboard:leads_all')
    
    # GET request - show bulk assignment form with pagination
    page_size = request.GET.get('page_size', '50')
    
    # Validate page size
    valid_page_sizes = ['5', '10', '20', '25', '50', '100', '200', '500']
    if page_size not in valid_page_sizes:
        page_size = '50'
    page_size = int(page_size)
    
    paginator = Paginator(accessible_leads.select_related('assigned_user'), page_size)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get available roles based on current user's role
    available_roles = []
    if request.user.role == 'owner':
        available_roles = [
            ('manager', 'Manager'),
            ('team_lead', 'Team Lead'),
            ('agent', 'Agent'),
        ]
    elif request.user.role == 'manager':
        available_roles = [
            ('team_lead', 'Team Lead'),
            ('agent', 'Agent'),
        ]
    elif request.user.role == 'team_lead':
        available_roles = [
            ('agent', 'Agent'),
        ]
    
    context = {
        'users': accessible_users.filter(
            is_active=True,
            account_status='active'
        ).select_related('manager', 'team_lead'),
        'page_obj': page_obj,
        'leads': page_obj,  # Keep for backward compatibility
        'available_roles': available_roles,
        'page_title': 'Bulk Assign Leads',
        'current_page_size': page_size,
    }
    return render(request, 'accounts/bulk_assign_leads.html', context)

@login_required
@hierarchy_required
def lead_transfer_history(request):
    """View lead transfer history"""
    accessible_leads = request.hierarchy_context['accessible_leads']
    
    # Get leads with assignment history
    leads_with_history = []
    for lead in accessible_leads:
        if lead.assignment_history:
            leads_with_history.append({
                'lead': lead,
                'history': lead.assignment_history
            })
    
    context = {
        'leads_with_history': leads_with_history,
        'page_title': 'Lead Transfer History',
    }
    return render(request, 'accounts/lead_transfer_history.html', context)

@login_required
@hierarchy_required
def user_performance(request):
    """Show user performance metrics based on hierarchy"""
    accessible_users = request.hierarchy_context['accessible_users']
    accessible_leads = request.hierarchy_context['accessible_leads']
    
    aggregated = {
        row['assigned_user']: row
        for row in accessible_leads.values('assigned_user').annotate(
            total_leads=Count('id_lead'),
            converted_leads=Count('id_lead', filter=Q(status='sale_done')),
        )
    }

    user_performance_data = []
    for user in accessible_users:
        stats = aggregated.get(user.id, {})
        total_leads = stats.get('total_leads', 0)
        converted_leads = stats.get('converted_leads', 0)
        performance_data = {
            'user': user,
            'total_leads': total_leads,
            'converted_leads': converted_leads,
            'conversion_rate': (converted_leads / total_leads * 100) if total_leads > 0 else 0,
            'last_activity': user.last_activity,
        }
        user_performance_data.append(performance_data)
    
    context = {
        'user_performance': user_performance_data,
        'page_title': 'User Performance',
    }
    return render(request, 'accounts/user_performance.html', context)

@login_required
@hierarchy_required
def team_hierarchy(request):
    """Show complete team hierarchy"""
    accessible_users = request.hierarchy_context['accessible_users']
    
    # Get all users based on current user's role
    if request.user.role == 'owner':
        all_users = User.objects.filter(company_id=request.user.company_id).select_related('manager', 'team_lead')
    elif request.user.role == 'manager':
        all_users = User.objects.filter(
            Q(manager=request.user) | Q(team_lead__manager=request.user) | Q(id=request.user.id)
        ).select_related('manager', 'team_lead')
    elif request.user.role == 'team_lead':
        all_users = User.objects.filter(
            Q(team_lead=request.user) | Q(id=request.user.id)
        ).select_related('manager', 'team_lead')
    else:
        all_users = User.objects.filter(id=request.user.id).select_related('manager', 'team_lead')
    
    # Build hierarchy structure
    hierarchy_data = []
    
    if request.user.role in ['owner', 'manager']:
        # Get managers (for owner) or self (for manager)
        if request.user.role == 'owner':
            managers = all_users.filter(role='manager')
        else:
            managers = [request.user]
        
        for manager in managers:
            manager_data = {
                'user': manager,
                'team_leads': [],
                'direct_agents': [],
            }
            
            # Get team leads under this manager
            team_leads = all_users.filter(role='team_lead', manager=manager)
            for team_lead in team_leads:
                team_lead_data = {
                    'user': team_lead,
                    'agents': list(all_users.filter(role='agent', team_lead=team_lead))
                }
                manager_data['team_leads'].append(team_lead_data)
            
            # Get direct agents under this manager (no team lead)
            direct_agents = all_users.filter(role='agent', manager=manager, team_lead__isnull=True)
            manager_data['direct_agents'] = list(direct_agents)
            
            hierarchy_data.append(manager_data)
    
    elif request.user.role == 'team_lead':
        # Show team lead and their agents
        team_lead_data = {
            'user': request.user,
            'agents': list(all_users.filter(role='agent', team_lead=request.user))
        }
        hierarchy_data = [team_lead_data]
    
    else:  # agent
        # Just show the agent
        hierarchy_data = [{'user': request.user, 'agents': []}]
    
    context = {
        'hierarchy_data': hierarchy_data,
        'current_user': request.user,
        'page_title': 'Team Hierarchy',
    }
    return render(request, 'accounts/team_hierarchy.html', context)

@login_required
@role_required('owner')
def delete_user(request, user_id):
    """Delete user with intelligent lead reassignment and sales credit preservation"""
    target_user = get_object_or_404(User, id=user_id, company_id=request.user.company_id)
    
    # Check if current user can delete the target user
    if not can_delete_user(request.user, target_user):
        messages.error(request, 'You do not have permission to delete this user.')
        return redirect('accounts:user_list')
    
    # Prevent deletion of admin/superuser
    if target_user.is_superuser:
        messages.error(request, 'Admin users cannot be deleted.')
        return redirect('accounts:user_list')
    
    # Prevent self-deletion
    if target_user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('accounts:user_list')
    
    # Import the lead reassignment service
    from services.lead_reassigner import LeadReassigner
    
    if request.method == 'POST':
        # Store user info for message
        username = target_user.username
        full_name = target_user.get_full_name() or username
        
        # Determine reassignment intent and selected user for manual reassignment
        reassignment_type = request.POST.get('reassignment_type', '').strip().lower()
        selected_user_id = request.POST.get('selected_user_id', '').strip()
        
        # DEBUG: Log the POST data and selected_user_id
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"DEBUG: User deletion POST request received for {target_user.username}")
        logger.info(f"DEBUG: POST data keys: {list(request.POST.keys())}")
        logger.info(f"DEBUG: selected_user_id from POST: {selected_user_id}")
        logger.info(f"DEBUG: selected_user_id type: {type(selected_user_id)}")
        logger.info(f"DEBUG: selected_user_id is empty: {not selected_user_id}")
        logger.info(f"DEBUG: selected_user_id is None: {selected_user_id is None}")
        logger.info(f"DEBUG: selected_user_id == '': {selected_user_id == ''}")
        logger.info(f"DEBUG: selected_user_id == '0': {selected_user_id == '0'}")
        
        # Log all POST data for complete visibility
        for key, value in request.POST.items():
            logger.info(f"DEBUG: POST[{key}] = {value}")
        
        try:
            # Initialize lead reassigner
            reassigner = LeadReassigner()
            
            # Get reassignment summary before deletion
            reassignment_summary = reassigner.get_reassignment_summary(target_user)
            
            # Manual reassignment requires a selected active user.
            if reassignment_type == 'manual' and not selected_user_id:
                messages.error(request, 'Selected user is not active.')
                return render(request, 'accounts/delete_user.html', {
                    'target_user': target_user,
                    'reassignment_summary': reassignment_summary,
                    'page_title': f'Delete {target_user.username}',
                    'error': 'Selected user is not active.'
                })

            # Perform lead reassignment based on user selection
            if selected_user_id:
                # Manual reassignment to selected user
                logger.info(f"DEBUG: Manual reassignment branch selected")
                logger.info(f"DEBUG: selected_user_id value: {selected_user_id}")
                
                selected_user = get_object_or_404(User, id=selected_user_id)
                
                logger.info(f"DEBUG: Selected user found: {selected_user.username}")
                logger.info(f"DEBUG: Selected user role: {selected_user.role}")
                logger.info(f"DEBUG: Selected user status: {selected_user.account_status}")
                
                # Validate selected user is active and in same company
                if selected_user.account_status != 'active':
                    logger.error(f"DEBUG: Selected user {selected_user.username} is not active")
                    messages.error(request, 'Selected user is not active.')
                    return render(request, 'accounts/delete_user.html', {
                        'target_user': target_user,
                        'reassignment_summary': reassignment_summary,
                        'page_title': f'Delete {target_user.username}',
                        'error': 'Selected user is not active.'
                    })
                
                if selected_user.company_id != request.user.company_id:
                    logger.error(f"DEBUG: Selected user {selected_user.username} is not in same company")
                    messages.error(request, 'Selected user is not in your company.')
                    return render(request, 'accounts/delete_user.html', {
                        'target_user': target_user,
                        'reassignment_summary': reassignment_summary,
                        'page_title': f'Delete {target_user.username}',
                        'error': 'Selected user is not in your company.'
                    })
                
                logger.info(f"DEBUG: Starting manual reassignment from {target_user.username} to {selected_user.username}")
                
                # Perform manual reassignment
                reassignment_results = reassigner.reassign_user_leads_to_specific(
                    target_user, selected_user, request.user
                )
                
                logger.info(f"DEBUG: Manual reassignment completed: {reassignment_results}")
                
                # Update summary for manual assignment
                reassignment_summary['replacement_user'] = selected_user.get_full_name() or selected_user.username
                reassignment_summary['replacement_role'] = selected_user.get_role_display()
                reassignment_summary['assignment_type'] = 'manual'
                
                logger.info(f"DEBUG: Summary updated for manual assignment")
                
            else:
                # Use automatic hierarchy reassignment as fallback
                logger.info(f"DEBUG: No selected_user_id provided, using hierarchy reassignment")
                logger.info(f"DEBUG: About to call reassigner.reassign_user_leads")
                reassignment_results = reassigner.reassign_user_leads(target_user, request.user)
                logger.info(f"DEBUG: Hierarchy reassignment completed: {reassignment_results}")
                reassignment_summary['assignment_type'] = 'hierarchy'
                
                # Log hierarchy replacement user info
                if 'replacement_user' in reassignment_summary:
                    logger.info(f"DEBUG: Hierarchy replacement user: {reassignment_summary['replacement_user']}")
                else:
                    logger.warning(f"DEBUG: No replacement_user found in reassignment_summary")
            
            # Soft delete by deactivating account and setting status to inactive
            target_user.is_active = False
            target_user.account_status = 'inactive'
            target_user.save()
            
            # Create comprehensive success message
            success_parts = []
            success_parts.append(f'User "{full_name}" has been deleted successfully and can no longer login.')
            
            if reassignment_results['active_leads_reassigned'] > 0:
                logger.info(f"DEBUG: Active leads reassigned: {reassignment_results['active_leads_reassigned']}")
                logger.info(f"DEBUG: Checking selected_user_id for message: {selected_user_id}")
                if selected_user_id:
                    logger.info(f"DEBUG: Using manual reassignment message")
                    success_parts.append(f'{reassignment_results["active_leads_reassigned"]} active leads manually reassigned to {reassignment_summary["replacement_user"]}.')
                else:
                    logger.info(f"DEBUG: Using hierarchy reassignment message")
                    success_parts.append(f'{reassignment_results["active_leads_reassigned"]} active leads reassigned to {reassignment_summary["replacement_user"]}.')
            
            if reassignment_results['converted_leads_preserved'] > 0:
                success_parts.append(f'{reassignment_results["converted_leads_preserved"]} converted leads preserved with original sales credit.')
                
                if reassignment_results['total_revenue_preserved'] > 0:
                    success_parts.append(f'₹{reassignment_results["total_revenue_preserved"]:,.2f} in sales revenue credit preserved.')
            
            success_parts.append('All performance metrics and sales data have been preserved.')
            
            messages.success(request, ' '.join(success_parts))
            
            # Log the deletion with reassignment details
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"DEBUG: Preparing final log entry")
            logger.info(f"DEBUG: selected_user_id for logging: {selected_user_id}")
            if selected_user_id:
                logger.info(f"DEBUG: Using manual reassignment log entry")
                logger.info(f'User {username} deleted by {request.user.username}. '
                           f'Manually reassigned {reassignment_results["active_leads_reassigned"]} leads to {selected_user.username}, '
                           f'preserved {reassignment_results["converted_leads_preserved"]} sales credits, '
                           f'total revenue preserved: ₹{reassignment_results["total_revenue_preserved"]}')
            else:
                logger.info(f"DEBUG: Using hierarchy reassignment log entry")
                logger.info(f'User {username} deleted by {request.user.username}. '
                           f'Reassigned {reassignment_results["active_leads_reassigned"]} leads, '
                           f'preserved {reassignment_results["converted_leads_preserved"]} sales credits, '
                           f'total revenue preserved: ₹{reassignment_results["total_revenue_preserved"]}')
            logger.info(f"DEBUG: Final log entry completed")
            
        except Exception as e:
            messages.error(request, f'Error during user deletion: {str(e)}')
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f'Error deleting user {username}: {str(e)}')
        
        return redirect('accounts:user_list')
    
    # GET request - show deletion confirmation with reassignment summary
    from services.lead_reassigner import LeadReassigner
    reassigner = LeadReassigner()
    reassignment_summary = reassigner.get_reassignment_summary(target_user)
    
    context = {
        'target_user': target_user,
        'reassignment_summary': reassignment_summary,
        'page_title': f'Delete {target_user.username}',
    }
    return render(request, 'accounts/delete_user.html', context)

def can_delete_user(current_user, target_user):
    """Check if current user can delete target user based on hierarchy"""
    if target_user.company_id != current_user.company_id:
        return False
    # Cannot delete admin/superuser
    if target_user.is_superuser:
        return False
    
    # Cannot delete self
    if current_user == target_user:
        return False
    
    # Owner can delete anyone except admin
    if current_user.role == 'owner':
        return True
    
    # Manager can delete their team leads and agents
    if current_user.role == 'manager':
        return (target_user.manager == current_user or 
                (target_user.team_lead and target_user.team_lead.manager == current_user))
    
    # Team Lead can delete their agents
    if current_user.role == 'team_lead':
        return target_user.team_lead == current_user
    
    # Agents cannot delete anyone
    return False


@login_required
@role_required('owner', 'manager', 'team_lead')
def check_username_availability(request):
    """
    Check if a username is available for use.
    Returns JSON response with availability status.
    """
    username = request.GET.get('username', '').strip()
    
    if not username:
        return JsonResponse({'available': False, 'message': 'Username is required'})
    
    # Validate username format
    import re
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', username):
        return JsonResponse({'available': False, 'message': 'Invalid username format'})
    
    # Check if username already exists
    exists = User.objects.filter(username__iexact=username).exists()
    
    if exists:
        return JsonResponse({'available': False, 'message': 'Username already taken'})
    else:
        return JsonResponse({'available': True, 'message': 'Username is available'})

@login_required
@role_required('owner', 'manager')
def get_team_leads_by_manager(request):
    """
    AJAX endpoint to get team leads for a specific manager.
    Returns JSON response with team leads data.
    """
    manager_id = request.GET.get('manager_id')
    
    if not manager_id:
        return JsonResponse({'error': 'Manager ID is required'}, status=400)
    
    try:
        manager = User.objects.get(id=manager_id, role='manager', company_id=request.user.company_id)
        
        # Get team leads under this manager
        team_leads = User.objects.filter(
            role='team_lead', 
            manager=manager, 
            company_id=request.user.company_id
        ).values('id', 'first_name', 'last_name', 'username')
        
        # Format team leads for select options
        team_leads_data = []
        for tl in team_leads:
            team_leads_data.append({
                'id': tl['id'],
                'name': f"{tl['first_name']} {tl['last_name']}".strip() or tl['username'],
                'username': tl['username']
            })
        
        return JsonResponse({
            'success': True,
            'team_leads': team_leads_data,
            'manager_name': f"{manager.first_name} {manager.last_name}".strip() or manager.username
        })
        
    except User.DoesNotExist:
        return JsonResponse({'error': 'Manager not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@hierarchy_required
def undo_assignments(request):
    """Undo a bulk assignment operation"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    assignment_id = request.POST.get('assignment_id')
    if not assignment_id:
        return JsonResponse({'success': False, 'message': 'Assignment ID is required'}, status=400)
    
    try:
        assignment = BulkAssignmentUndo.objects.get(
            id=assignment_id,
            assigned_by=request.user  # Users can only undo their own assignments
        )
        
        # Perform the undo operation
        undone_count = assignment.undo_assignment()
        
        if undone_count > 0:
            # Delete the undo record after successful undo
            assignment.delete()
            
            # Log the undo operation
            LeadOperationLog.objects.create(
                operation_id=f"undo_assign_{uuid.uuid4().hex[:14]}",
                operation_type='undo_assign',
                user=request.user,
                company_id=request.user.company_id,
                action_scope='undo',
                requested_count=assignment.assignment_count,
                processed_count=undone_count,
                success_count=undone_count,
                failed_count=0,
                metadata={
                    'original_assignment_id': assignment_id,
                    'original_assigned_to': assignment.assigned_to.id,
                    'undone_count': undone_count
                },
            )
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully undone assignment of {undone_count} leads.',
                'undone_count': undone_count
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No leads were found to undo. The assignment may have been already modified.'
            })
            
    except BulkAssignmentUndo.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Assignment not found or you do not have permission to undo it.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'An error occurred: {str(e)}'}, status=500)


@login_required
@hierarchy_required
def get_undo_history(request):
    """Get undo history for the current user"""
    try:
        # Get recent bulk assignments by the current user
        assignments = BulkAssignmentUndo.objects.filter(
            assigned_by=request.user
        ).select_related('assigned_to').order_by('-created_at')[:20]  # Last 20 assignments
        
        assignment_data = []
        for assignment in assignments:
            assignment_data.append({
                'id': assignment.id,
                'assigned_to_name': assignment.assigned_to.get_full_name() or assignment.assigned_to.username,
                'assigned_to_role': assignment.assigned_to.get_role_display(),
                'assignment_count': assignment.assignment_count,
                'created_at': assignment.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'created_at_formatted': assignment.created_at.strftime('%b %d, %Y at %I:%M %p'),
                'can_undo': True  # Users can undo their own assignments
            })
        
        return JsonResponse({
            'success': True,
            'assignments': assignment_data,
            'total_count': BulkAssignmentUndo.objects.filter(assigned_by=request.user).count()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'An error occurred: {str(e)}'}, status=500)
