from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import JsonResponse
from django.core.paginator import Paginator
from .models import User
from dashboard.models import Lead
from .permissions import role_required, can_manage_user_required, hierarchy_required
from .forms import UserCreationForm, UserAssignmentForm

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard:home')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        # Debug information
        print(f"Login attempt - Username: {username}")
        print(f"Login attempt - Password provided: {'Yes' if password else 'No'}")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            print(f"Authentication successful for: {user.username}")
            
            # Check if user is blocked/inactive
            if not user.is_active or user.account_status == 'inactive':
                messages.error(request, 'Your account has been blocked by the administrator. Please contact your admin.')
                return redirect('accounts:login')
            
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            return redirect('dashboard:home')
        else:
            print(f"Authentication failed for: {username}")
            # Check if user exists
            try:
                user_obj = User.objects.get(username=username)
                print(f"User exists: {user_obj.username}, Active: {user_obj.is_active}")
                print(f"Has password: {user_obj.has_usable_password()}")
                
                # Check if user is blocked/inactive
                if not user_obj.is_active or user_obj.account_status == 'inactive':
                    messages.error(request, 'Your account has been blocked by the administrator. Please contact your admin.')
                else:
                    messages.error(request, 'Invalid username or password.')
            except User.DoesNotExist:
                print(f"User does not exist: {username}")
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
    """Edit user details"""
    target_user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        # Handle user update logic
        target_user.first_name = request.POST.get('first_name', '')
        target_user.last_name = request.POST.get('last_name', '')
        target_user.email = request.POST.get('email', '')
        target_user.phone = request.POST.get('phone', '')
        target_user.mobile = request.POST.get('mobile', '')
        target_user.account_status = request.POST.get('account_status', 'active')
        
        target_user.save()
        messages.success(request, f'User {target_user.username} updated successfully.')
        return redirect('accounts:user_list')
    
    context = {
        'target_user': target_user,
        'status_choices': User.ACCOUNT_STATUS_CHOICES,
        'page_title': f'Edit {target_user.username}',
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
                        assignment_history = lead.assignment_history or []
                        assignment_history.append({
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
    
    if lead_id:
        try:
            lead = accessible_leads.get(id_lead=lead_id)
            # Filter users based on hierarchy rules
            users = [user for user in accessible_users if lead.can_be_assigned_to_user(user, request.user)]
        except Lead.DoesNotExist:
            messages.error(request, 'Lead not found.')
            return redirect('dashboard:leads_all')
    else:
        users = accessible_users
    
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
    """AJAX endpoint to get users filtered by role"""
    if request.method == 'GET' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        role = request.GET.get('role')
        accessible_users = request.hierarchy_context['accessible_users']
        
        if role:
            users = accessible_users.filter(role=role).select_related('manager', 'team_lead')
        else:
            users = accessible_users.select_related('manager', 'team_lead')
        
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
                status='converted'
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
        remarks = request.POST.get('remarks', '')
        
        if not lead_ids:
            messages.error(request, 'Please select at least one lead to assign.')
            return redirect('accounts:bulk_assign')
        
        try:
            assigned_user = accessible_users.get(id=assigned_user_id)
            
            # Verify user can assign to this person
            if not request.user.can_manage_user(assigned_user):
                messages.error(request, 'You cannot assign leads to this user due to hierarchy restrictions.')
                return redirect('accounts:bulk_assign')
            
            successful_assignments = 0
            failed_assignments = 0
            
            for lead_id in lead_ids:
                try:
                    lead = accessible_leads.get(id_lead=lead_id)
                    
                    if lead.can_be_assigned_by(request.user) and lead.can_be_assigned_to_user(assigned_user, request.user):
                        success = lead.assign_to_user(assigned_user, request.user)
                        if success:
                            successful_assignments += 1
                            
                            # Add remarks to assignment history if provided
                            if remarks:
                                assignment_history = lead.assignment_history or []
                                assignment_history.append({
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
        'users': accessible_users.select_related('manager', 'team_lead'),
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
    
    user_performance_data = []
    for user in accessible_users:
        user_leads = accessible_leads.filter(assigned_user=user)
        converted_leads = user_leads.filter(status='sale_done')
        
        performance_data = {
            'user': user,
            'total_leads': user_leads.count(),
            'converted_leads': converted_leads.count(),
            'conversion_rate': (converted_leads.count() / user_leads.count() * 100) if user_leads.count() > 0 else 0,
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
    """Delete user with hierarchy-based permissions"""
    target_user = get_object_or_404(User, id=user_id)
    
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
    
    if request.method == 'POST':
        # Store user info for message
        username = target_user.username
        full_name = target_user.get_full_name() or username
        
        # Soft delete by deactivating account and setting status to inactive
        target_user.is_active = False
        target_user.account_status = 'inactive'
        target_user.save()
        
        # Note: We preserve all user data including leads, comments, and history
        # Only login access is blocked - no data is deleted or reassigned
        
        messages.success(request, f'User "{full_name}" has been deleted successfully and can no longer login.')
        return redirect('accounts:user_list')
    
    context = {
        'target_user': target_user,
        'page_title': f'Delete {target_user.username}',
    }
    return render(request, 'accounts/delete_user.html', context)

def can_delete_user(current_user, target_user):
    """Check if current user can delete target user based on hierarchy"""
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
@role_required(['owner', 'manager', 'team_lead'])
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

