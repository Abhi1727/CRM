from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.db.models import Q
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = [
        'username', 'email', 'role', 'first_name', 'last_name', 
        'account_status', 'hierarchy_info', 'created_at'
    ]
    list_filter = [
        'role', 'account_status', 'is_staff', 'is_superuser', 'is_active',
        'company_id', 'created_at'
    ]
    search_fields = ['username', 'email', 'first_name', 'last_name', 'phone']
    ordering = ['-created_at']
    
    fieldsets = UserAdmin.fieldsets + (
        ('CRM Information', {
            'fields': (
                'role', 'account_status', 'phone', 'mobile', 
                'profile_picture', 'company_id'
            )
        }),
        ('Hierarchy', {
            'fields': (
                'created_by', 'manager', 'team_lead'
            ),
            'description': 'Hierarchy relationships for role-based access control'
        }),
        ('Performance Metrics', {
            'fields': (
                'leads_assigned_count', 'leads_converted_count', 'last_activity'
            ),
            'description': 'Performance tracking fields'
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CRM Information', {
            'fields': (
                'role', 'email', 'first_name', 'last_name', 
                'phone', 'mobile', 'company_id'
            )
        }),
    )
    
    readonly_fields = ['created_by', 'leads_assigned_count', 'leads_converted_count', 'last_activity']
    
    def hierarchy_info(self, obj):
        """Display hierarchy information in list view"""
        info_parts = []
        
        if obj.created_by:
            info_parts.append(f"Created by: {obj.created_by.username}")
        
        if obj.manager:
            info_parts.append(f"Manager: {obj.manager.username}")
        
        if obj.team_lead:
            info_parts.append(f"Team Lead: {obj.team_lead.username}")
        
        if info_parts:
            return format_html('<br>'.join(info_parts))
        return '-'
    
    hierarchy_info.short_description = 'Hierarchy'
    
    def get_queryset(self, request):
        """Filter queryset based on user's hierarchy"""
        qs = super().get_queryset(request)
        
        # Superuser sees everything
        if request.user.is_superuser:
            return qs
        
        # Owner sees all users in their company
        if request.user.role == 'owner':
            return qs.filter(company_id=request.user.company_id)
        
        # Manager sees team leads and agents under them
        elif request.user.role == 'manager':
            return qs.filter(
                Q(manager=request.user) | 
                Q(team_lead__manager=request.user) |
                Q(id=request.user.id)
            )
        
        # Team Lead sees agents under them
        elif request.user.role == 'team_lead':
            return qs.filter(
                Q(team_lead=request.user) |
                Q(id=request.user.id)
            )
        
        # Agent sees only themselves
        else:
            return qs.filter(id=request.user.id)
    
    def get_form(self, request, obj=None, **kwargs):
        """Customize form based on user role"""
        form = super().get_form(request, obj, **kwargs)
        
        # Filter hierarchy fields based on current user
        if not request.user.is_superuser:
            if 'manager' in form.base_fields:
                if request.user.role == 'owner':
                    # Owner can assign any manager from their company
                    form.base_fields['manager'].queryset = User.objects.filter(
                        role='manager', 
                        company_id=request.user.company_id
                    )
                elif request.user.role == 'manager':
                    # Manager can only assign themselves
                    form.base_fields['manager'].queryset = User.objects.filter(
                        id=request.user.id
                    )
                else:
                    # Team leads and agents cannot assign managers
                    del form.base_fields['manager']
            
            if 'team_lead' in form.base_fields:
                if request.user.role in ['owner', 'manager']:
                    # Owner and manager can assign team leads
                    if request.user.role == 'owner':
                        team_leads = User.objects.filter(
                            role='team_lead',
                            company_id=request.user.company_id
                        )
                    else:  # manager
                        team_leads = User.objects.filter(
                            role='team_lead',
                            manager=request.user
                        )
                    form.base_fields['team_lead'].queryset = team_leads
                else:
                    # Team leads and agents cannot assign team leads
                    del form.base_fields['team_lead']
        
        return form
    
    def save_model(self, request, obj, form, change):
        """Set created_by and hierarchy relationships"""
        if not change:  # Creating new user
            obj.created_by = request.user
            obj.company_id = request.user.company_id
        
        # Ensure hierarchy rules are followed
        if request.user.role == 'manager' and obj.role in ['team_lead', 'agent']:
            obj.manager = request.user
        elif request.user.role == 'team_lead' and obj.role == 'agent':
            obj.team_lead = request.user
            obj.manager = request.user.manager
        
        super().save_model(request, obj, form, change)

