from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from .models import User

def role_required(*allowed_roles):
    """
    Decorator to require specific user roles
    Usage: @role_required('manager', 'owner')
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({'error': 'Insufficient permissions'}, status=403)
                raise PermissionDenied("You don't have permission to access this resource.")
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def hierarchy_required(view_func):
    """
    Decorator to ensure user can only access data within their hierarchy
    This decorator filters queryset based on user hierarchy
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        # Add hierarchy context to request
        request.hierarchy_context = {
            'accessible_users': request.user.get_accessible_users(),
            'accessible_leads': request.user.get_accessible_leads_queryset(),
            'hierarchy_level': request.user.get_hierarchy_level(),
        }
        return view_func(request, *args, **kwargs)
    return wrapper

def can_manage_user_required(view_func):
    """
    Decorator to check if current user can manage target user
    Expects 'user_id' in kwargs or request.POST
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        user_id = kwargs.get('user_id') or request.POST.get('user_id')
        if user_id:
            try:
                target_user = User.objects.get(id=user_id)
                if target_user.company_id != request.user.company_id:
                    raise PermissionDenied("You don't have permission to manage this user.")
                if not request.user.can_manage_user(target_user):
                    if request.headers.get('Accept') == 'application/json':
                        return JsonResponse({'error': 'Cannot manage this user'}, status=403)
                    raise PermissionDenied("You don't have permission to manage this user.")
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=404)
        return view_func(request, *args, **kwargs)
    return wrapper

def can_access_lead_required(view_func):
    """
    Decorator to check if user can access specific lead
    Expects 'lead_id' or 'pk' in kwargs
    """
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        lead_id = kwargs.get('lead_id') or kwargs.get('pk')
        if lead_id:
            from dashboard.models import Lead
            try:
                lead = Lead.objects.get(id_lead=lead_id)
                if not lead.can_be_accessed_by(request.user):
                    if request.headers.get('Accept') == 'application/json':
                        return JsonResponse({'error': 'Cannot access this lead'}, status=403)
                    raise PermissionDenied("You don't have permission to access this lead.")
                # Add lead to request context
                request.current_lead = lead
            except Lead.DoesNotExist:
                return JsonResponse({'error': 'Lead not found'}, status=404)
        return view_func(request, *args, **kwargs)
    return wrapper
