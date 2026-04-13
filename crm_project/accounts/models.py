from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.cache import cache
import re

class User(AbstractUser):
    ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('manager', 'Manager'),
        ('team_lead', 'Team Lead'),
        ('agent', 'Agent'),
    )
    
    ACCOUNT_STATUS_CHOICES = (
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    )
    
    # Override email field to make it unique
    email = models.EmailField(unique=True, blank=False, null=False)
    
    # Core fields
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='agent')
    phone = models.CharField(max_length=15, blank=True, null=True)
    mobile = models.CharField(max_length=255, blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    company_id = models.IntegerField(default=1)
    account_status = models.CharField(max_length=20, choices=ACCOUNT_STATUS_CHOICES, default='active')
    
    # Hierarchy fields
    created_by = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='created_users')
    manager = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_team_leads', limit_choices_to={'role': 'manager'})
    team_lead = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='team_agents', limit_choices_to={'role': 'team_lead'})
    
    # Performance tracking
    leads_assigned_count = models.PositiveIntegerField(default=0)
    leads_converted_count = models.PositiveIntegerField(default=0)
    last_activity = models.DateTimeField(null=True, blank=True)
    
    # Preserved performance metrics (for deleted users)
    preserved_leads_count = models.PositiveIntegerField(default=0, help_text="Number of leads preserved after user deletion")
    preserved_converted_count = models.PositiveIntegerField(default=0, help_text="Number of converted leads preserved after user deletion")
    preserved_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Total revenue preserved from converted leads")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['role', 'account_status']),
            models.Index(fields=['manager', 'team_lead']),
            models.Index(fields=['company_id']),
            models.Index(fields=['email']),  # Add index for email lookups
        ]
    
    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"
    
    # Hierarchy helper methods
    def get_hierarchy_level(self):
        role_levels = {'owner': 4, 'manager': 3, 'team_lead': 2, 'agent': 1}
        return role_levels.get(self.role, 0)
    
    def can_manage_user(self, target_user):
        """Check if current user can manage target user based on hierarchy"""
        if not target_user or target_user.company_id != self.company_id:
            return False
        if self.role == 'owner':
            return target_user.role in ['manager', 'team_lead', 'agent']
        elif self.role == 'manager':
            return target_user.role in ['team_lead', 'agent'] and target_user.manager == self
        elif self.role == 'team_lead':
            return target_user.role == 'agent' and target_user.team_lead == self
        return False
    
    def get_accessible_users(self):
        """Get users this user can access based on hierarchy"""
        cache_key = f"accessible_users_{self.id}_{self.company_id}_{self.role}"
        cached_users = cache.get(cache_key)
        
        if cached_users:
            return cached_users
        
        if self.role == 'owner':
            users = User.objects.filter(company_id=self.company_id).exclude(id=self.id).select_related('manager', 'team_lead')
        elif self.role == 'manager':
            users = User.objects.filter(
                Q(manager=self) | Q(team_lead__manager=self)
            ).exclude(id=self.id).select_related('manager', 'team_lead')
        elif self.role == 'team_lead':
            users = User.objects.filter(team_lead=self).exclude(id=self.id).select_related('manager', 'team_lead')
        else:
            users = User.objects.filter(id=self.id).select_related('manager', 'team_lead')
        
        # Cache for 10 minutes
        cache.set(cache_key, users, 600)
        return users
    
    def get_accessible_leads_queryset(self):
        """Get leads this user can access based on hierarchy"""
        from dashboard.models import Lead  # Import here to avoid circular import
        
        cache_key = f"accessible_leads_{self.id}_{self.company_id}_{self.role}"
        cached_leads = cache.get(cache_key)
        
        if cached_leads:
            return cached_leads
        
        if self.role == 'owner':
            leads = Lead.objects.filter(company_id=self.company_id).select_related('assigned_user', 'created_by')
        elif self.role == 'manager':
            leads = Lead.objects.filter(
                Q(assigned_user__manager=self) |
                Q(assigned_user__team_lead__manager=self) |
                Q(assigned_user=self)  # Manager can see their own leads too
            ).select_related('assigned_user', 'created_by', 'assigned_user__manager', 'assigned_user__team_lead')
        elif self.role == 'team_lead':
            leads = Lead.objects.filter(
                Q(assigned_user__team_lead=self) |  # Leads assigned to their agents
                Q(assigned_user=self)  # Their own leads
            ).select_related('assigned_user', 'created_by', 'assigned_user__team_lead')
        else:  # agent
            leads = Lead.objects.filter(assigned_user=self).select_related('assigned_user', 'created_by')
        
        # Cache for 10 minutes
        cache.set(cache_key, leads, 600)
        return leads
    
    def save(self, *args, **kwargs):
        """
        Override save to automatically sync is_active with account_status
        This ensures that when account_status is changed, is_active is always kept in sync
        """
        # Auto-sync is_active with account_status
        if self.account_status == 'active':
            self.is_active = True
        elif self.account_status in ['inactive', 'suspended']:
            self.is_active = False
        
        # Clear relevant caches when user data changes
        self._clear_user_caches()
        
        # Call the original save method
        super().save(*args, **kwargs)
    
    def _clear_user_caches(self):
        """Clear all caches related to this user and their hierarchy"""
        from django.core.cache import cache
        
        # Clear this user's caches
        cache.delete(self._get_user_cache_key('accessible_users'))
        cache.delete(self._get_user_cache_key('accessible_leads'))
        
        # Clear caches for users who might be affected by this user's changes
        if self.manager:
            cache.delete(self.manager._get_user_cache_key('accessible_users'))
            cache.delete(self.manager._get_user_cache_key('accessible_leads'))
        
        if self.team_lead:
            cache.delete(self.team_lead._get_user_cache_key('accessible_users'))
            cache.delete(self.team_lead._get_user_cache_key('accessible_leads'))
        
        # Clear caches for users managed by this user (if this user is a manager/team_lead)
        if self.role in ['manager', 'team_lead']:
            affected_users = User.objects.filter(
                Q(manager=self) | Q(team_lead=self)
            ).values_list('id', 'role', 'company_id')
            
            for user_id, user_role, user_company_id in affected_users:
                cache.delete(f"accessible_users_{user_id}_{user_company_id}_{user_role}")
                cache.delete(f"accessible_leads_{user_id}_{user_company_id}_{user_role}")
        
        # Clear dashboard statistics caches for all users in the company
        self._clear_company_dashboard_caches()
    
    def _get_user_cache_key(self, cache_type):
        """Generate cache key for this user"""
        return f"{cache_type}_{self.id}_{self.company_id}_{self.role}"
    
    def _clear_company_dashboard_caches(self):
        """Clear all dashboard statistics caches for this company"""
        from django.core.cache import cache
        
        # Clear dashboard statistics caches for all users in the company
        all_company_users = User.objects.filter(company_id=self.company_id).values_list('id', flat=True)
        for user_id in all_company_users:
            cache.delete(f"dashboard_stats_{user_id}_{self.company_id}_main")
            cache.delete(f"dashboard_stats_{user_id}_{self.company_id}_role_owner")
            cache.delete(f"dashboard_stats_{user_id}_{self.company_id}_role_manager")
            cache.delete(f"dashboard_stats_{user_id}_{self.company_id}_role_team_lead")
            cache.delete(f"dashboard_stats_{user_id}_{self.company_id}_role_agent")
    
    @classmethod
    def clear_hierarchy_caches(cls, company_id, affected_user_ids=None):
        """Clear caches for specific users or entire company"""
        from django.core.cache import cache
        
        if affected_user_ids:
            # Clear caches for specific users
            users = cls.objects.filter(id__in=affected_user_ids).select_related('manager', 'team_lead')
            for user in users:
                cache.delete(user._get_user_cache_key('accessible_users'))
                cache.delete(user._get_user_cache_key('accessible_leads'))
                
                # Clear caches for their managers/team leads
                if user.manager:
                    cache.delete(user.manager._get_user_cache_key('accessible_users'))
                    cache.delete(user.manager._get_user_cache_key('accessible_leads'))
                
                if user.team_lead:
                    cache.delete(user.team_lead._get_user_cache_key('accessible_users'))
                    cache.delete(user.team_lead._get_user_cache_key('accessible_leads'))
        else:
            # Clear caches for entire company
            users = cls.objects.filter(company_id=company_id).values_list('id', 'role', 'company_id')
            for user_id, user_role, user_company_id in users:
                cache.delete(f"accessible_users_{user_id}_{user_company_id}_{user_role}")
                cache.delete(f"accessible_leads_{user_id}_{user_company_id}_{user_role}")
    
    @classmethod
    def warm_user_caches(cls, user_id):
        """Warm cache for a specific user by pre-loading their accessible data"""
        try:
            user = cls.objects.get(id=user_id)
            # This will trigger cache population
            user.get_accessible_users()
            user.get_accessible_leads_queryset()
        except cls.DoesNotExist:
            pass


class BulkAssignmentUndo(models.Model):
    """Tracks bulk assignment operations for undo functionality"""
    assigned_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bulk_assignments')
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_bulk_assignments')
    lead_ids = models.TextField(help_text="Comma-separated list of lead IDs")
    assignment_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['assigned_by', 'created_at']),
            models.Index(fields=['assigned_to', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.assigned_by.username} assigned {self.assignment_count} leads to {self.assigned_to.username} on {self.created_at.strftime('%Y-%m-%d %H:%M')}"
    
    def get_lead_ids_list(self):
        """Return lead IDs as a list of integers"""
        if self.lead_ids:
            return [int(id.strip()) for id in self.lead_ids.split(',') if id.strip().isdigit()]
        return []
    
    def undo_assignment(self):
        """Undo the bulk assignment by setting assigned_user back to None"""
        from dashboard.models import Lead
        
        lead_ids = self.get_lead_ids_list()
        if lead_ids:
            updated_count = Lead.objects.filter(
                id__in=lead_ids,
                assigned_user=self.assigned_to
            ).update(assigned_user=None)
            
            # Clear relevant caches
            self.assigned_to._clear_user_caches()
            self.assigned_by._clear_user_caches()
            
            return updated_count
        return 0
