from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Q
from django.core.exceptions import ValidationError
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
        if self.role == 'owner':
            return target_user.role in ['manager', 'team_lead', 'agent']
        elif self.role == 'manager':
            return target_user.role in ['team_lead', 'agent'] and target_user.manager == self
        elif self.role == 'team_lead':
            return target_user.role == 'agent' and target_user.team_lead == self
        return False
    
    def get_accessible_users(self):
        """Get users this user can access based on hierarchy"""
        if self.role == 'owner':
            return User.objects.filter(company_id=self.company_id).exclude(id=self.id)
        elif self.role == 'manager':
            return User.objects.filter(
                Q(manager=self) | Q(team_lead__manager=self)
            ).exclude(id=self.id)
        elif self.role == 'team_lead':
            return User.objects.filter(team_lead=self).exclude(id=self.id)
        else:
            return User.objects.filter(id=self.id)
    
    def get_accessible_leads_queryset(self):
        """Get leads this user can access based on hierarchy"""
        from dashboard.models import Lead  # Import here to avoid circular import
        
        if self.role == 'owner':
            return Lead.objects.filter(company_id=self.company_id)
        elif self.role == 'manager':
            return Lead.objects.filter(
                Q(assigned_user__manager=self) |
                Q(assigned_user__team_lead__manager=self) |
                Q(assigned_user=self)  # Manager can see their own leads too
            )
        elif self.role == 'team_lead':
            return Lead.objects.filter(
                Q(assigned_user__team_lead=self) |  # Leads assigned to their agents
                Q(assigned_user=self)  # Their own leads
            )
        else:  # agent
            return Lead.objects.filter(assigned_user=self)
    
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
        
        # Call the original save method
        super().save(*args, **kwargs)
