from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class Lead(models.Model):
    STATUS_CHOICES = [
        ('sale_done', 'Sale Done'),
        ('interested_follow_up', 'Interested - Follow Up'),
        ('not_available', 'Not Available'),
        ('rnr', 'RNR'),
        ('not_interested', 'Not Interested'),
        ('out_of_country', 'Out of Country'),
        ('getting_better_deal', 'Getting Better Deal'),
        ('product_expensive', 'Product is Expensive'),
        ('not_eligible_emi', 'Not Eligible for EMI'),
        ('wrong_number', 'Wrong Number'),
        ('switched_off', 'Switched Off'),
        ('closed', 'Closed'),
        ('call_back', 'Call Back'),
        ('in_few_months', 'In Few Months'),
        ('contacted', 'Contacted'),
        ('lead', 'Lead'),
    ]
    
    # From original database structure
    id_lead = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, null=True, blank=True)
    mobile = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=100, null=True, blank=True)
    alt_mobile = models.CharField(max_length=100, null=True, blank=True)
    whatsapp_no = models.CharField(max_length=100, null=True, blank=True)
    alt_email = models.EmailField(max_length=100, null=True, blank=True)
    
    # Address information
    address = models.CharField(max_length=150, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    postalcode = models.CharField(max_length=20, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    
    # Company and assignment with hierarchy support
    company_id = models.IntegerField(default=1)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads_created')
    assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads')
    modified_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='modified_leads')
    
    # Hierarchy assignment tracking
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assignments_made')
    assigned_at = models.DateTimeField(null=True, blank=True)
    assignment_history = models.JSONField(default=dict, blank=True)  # Track assignment changes
    
    # Status and conversion
    status = models.CharField(max_length=100, choices=STATUS_CHOICES, default='lead', null=True, blank=True)
    status_description = models.TextField(null=True, blank=True)
    converted = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    do_not_call = models.BooleanField(default=False)
    
    # Follow-up
    followup_datetime = models.DateTimeField(null=True, blank=True)
    followup_remarks = models.TextField(null=True, blank=True)
    date_reviewed = models.DateField(null=True, blank=True)
    
    # Internal reminder fields
    followup_priority = models.CharField(max_length=10, choices=[
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ], default='medium')
    internal_reminder_sent = models.BooleanField(default=False)
    last_internal_reminder = models.DateTimeField(null=True, blank=True)
    internal_reminder_count = models.PositiveIntegerField(default=0)
    team_followup_notes = models.TextField(blank=True, null=True)  # Internal team notes
    
    # Course/Product information
    course_id = models.CharField(max_length=36, null=True, blank=True)
    course_name = models.CharField(max_length=255, null=True, blank=True)
    course_amount = models.CharField(max_length=50, null=True, blank=True)
    
    # Lead source
    lead_source = models.CharField(max_length=100, null=True, blank=True)
    lead_source_description = models.TextField(null=True, blank=True)
    refered_by = models.CharField(max_length=100, null=True, blank=True)
    campaign_id = models.CharField(max_length=36, null=True, blank=True)
    
    # Revenue and sales
    exp_revenue = models.CharField(max_length=255, null=True, blank=True)
    exp_close_date = models.DateField(null=True, blank=True)
    
    # Transfer information
    transfer_from = models.CharField(max_length=255, null=True, blank=True)
    transfer_by = models.CharField(max_length=255, null=True, blank=True)
    transfer_date = models.DateTimeField(null=True, blank=True)
    
    # Additional fields
    description = models.TextField(null=True, blank=True)
    birthdate = models.DateField(null=True, blank=True)
    team_member = models.TextField(null=True, blank=True)
    next_step = models.TextField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Duplicate detection fields
    duplicate_status = models.CharField(max_length=20, choices=[
        ('new', 'New'),
        ('exact_duplicate', 'Exact Duplicate'),
        ('potential_duplicate', 'Potential Duplicate'),
        ('related', 'Related Lead')
    ], default='new')
    duplicate_info = models.JSONField(default=dict, blank=True)  # Store duplicate detection details
    
    # Duplicate management fields
    duplicate_group_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    duplicate_resolution_status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('resolved', 'Resolved'),
        ('ignored', 'Ignored'),
        ('merged', 'Merged')
    ], default='pending')
    last_assigned_agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_assigned_agent_leads')
    last_assigned_manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='last_assigned_manager_leads')
    duplicate_resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_duplicates')
    duplicate_resolved_at = models.DateTimeField(null=True, blank=True)
    duplicate_notes = models.TextField(null=True, blank=True)
    
    # Sales credit preservation fields
    primary_sales_credit = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales_credits', help_text="Original user who gets sales credit for converted leads")
    original_assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='original_assignments', help_text="Original user this lead was assigned to")
    sales_credit_preserved = models.BooleanField(default=False, help_text="Whether sales credit has been preserved due to user deletion")
    
    def __str__(self):
        return f"{self.name} - {self.mobile}"
    
    def save(self, *args, **kwargs):
        """Override save to implement smart cache invalidation"""
        # Get original values for change detection
        if self.pk:
            original = Lead.objects.filter(pk=self.pk).first()
            original_values = {
                'assigned_user_id': original.assigned_user_id if original else None,
                'status': original.status if original else None,
                'company_id': original.company_id if original else None,
            }
        else:
            original_values = {
                'assigned_user_id': None,
                'status': None,
                'company_id': None,
            }
        
        # Call the original save method
        super().save(*args, **kwargs)
        
        # Smart cache invalidation based on what changed
        self._invalidate_relevant_caches(original_values)
    
    def _invalidate_relevant_caches(self, original_values):
        """Invalidate relevant caches based on field changes"""
        from core.cache import CacheManager, QueryResultCache
        
        # Always invalidate dashboard stats for this company
        CacheManager.invalidate_company_cache(self.company_id)
        
        # If assigned user changed, invalidate their caches
        if original_values['assigned_user_id'] != self.assigned_user_id:
            if original_values['assigned_user_id']:
                CacheManager.invalidate_user_cache(original_values['assigned_user_id'], self.company_id)
            if self.assigned_user_id:
                CacheManager.invalidate_user_cache(self.assigned_user_id, self.company_id)
        
        # If status changed, invalidate query result caches
        if original_values['status'] != self.status:
            QueryResultCache.invalidate_query_cache(
                query_type='lead_statistics',
                company_id=self.company_id
            )
            
        # If company changed (rare), invalidate old company too
        if original_values['company_id'] != self.company_id and original_values['company_id']:
            CacheManager.invalidate_company_cache(original_values['company_id'])
    
    def delete(self, *args, **kwargs):
        """Override delete to implement cache invalidation"""
        company_id = self.company_id
        assigned_user_id = self.assigned_user_id
        
        # Call original delete
        super().delete(*args, **kwargs)
        
        # Invalidate relevant caches
        from core.cache import CacheManager, QueryResultCache
        CacheManager.invalidate_company_cache(company_id)
        
        if assigned_user_id:
            CacheManager.invalidate_user_cache(assigned_user_id, company_id)
        
        QueryResultCache.invalidate_query_cache(
            query_type='lead_statistics',
            company_id=company_id
        )
    
    class Meta:
        db_table = 'leads'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'status']),
            models.Index(fields=['assigned_user', 'status']),
            models.Index(fields=['created_by', 'created_at']),
            models.Index(fields=['followup_datetime']),
            models.Index(fields=['lead_source']),
            models.Index(fields=['assigned_user', 'company_id']),  # For hierarchy queries
            models.Index(fields=['created_by', 'company_id']),     # For hierarchy queries
            models.Index(fields=['status', 'created_at']),         # For filtering
            # Duplicate management indexes
            models.Index(fields=['duplicate_status', 'duplicate_resolution_status']),
            models.Index(fields=['duplicate_group_id']),
            models.Index(fields=['last_assigned_agent', 'duplicate_status']),
            models.Index(fields=['last_assigned_manager', 'duplicate_status']),
            models.Index(fields=['company_id', 'duplicate_status']),
            # Performance optimization indexes from plan
            models.Index(fields=['company_id', 'deleted', 'status']),
            models.Index(fields=['assigned_user', 'created_at']),
            models.Index(fields=['created_at', 'status']),
            models.Index(fields=['transfer_date', 'transfer_by']),
        ]
    
    def can_be_accessed_by(self, user):
        """Check if user can access this lead based on hierarchy"""
        return user.get_accessible_leads_queryset().filter(id_lead=self.id_lead).exists()
    
    def get_status_display_value(self, status_value):
        """Get display value for any status choice"""
        status_dict = dict(self.STATUS_CHOICES)
        return status_dict.get(status_value, status_value)
    
    def can_update_status_by(self, user):
        """Check if user can update this lead's status - more permissive than general access"""
        if self.company_id != user.company_id:
            return False
        if user.role == 'owner':
            return self.can_be_accessed_by(user)
        elif user.role == 'manager':
            # Managers can update status for leads in their accessible scope
            return self.can_be_accessed_by(user)
        elif user.role == 'team_lead':
            # Team leads can update status for leads assigned to their team members or themselves
            return (self.assigned_user == user or 
                   (self.assigned_user and self.assigned_user.team_lead == user))
        elif user.role == 'agent':
            # Agents can only update status for their own leads
            return self.assigned_user == user
        return False
    
    def can_be_assigned_by(self, user):
        """Check if user can assign this lead"""
        if self.company_id != user.company_id:
            return False
        if user.role == 'owner':
            return self.can_be_accessed_by(user)
        elif user.role == 'manager':
            # Manager can assign leads in their accessible scope OR leads assigned to their manager (owner)
            return (self.can_be_accessed_by(user) or 
                   (self.assigned_user and self.assigned_user.role == 'owner'))
        elif user.role == 'team_lead':
            # Team Lead can assign leads in their accessible scope OR leads assigned to their manager
            return (self.can_be_accessed_by(user) or 
                   (self.assigned_user and self.assigned_user.role in ['manager', 'owner']))
        return False
    
    def can_be_assigned_to_user(self, target_user, assigning_user):
        """Check if lead can be assigned to target user by assigning user following hierarchy"""
        # Owner can assign to anyone in their company
        if assigning_user.role == 'owner':
            return target_user.company_id == assigning_user.company_id
        
        # Manager can assign to themselves, their team leads and agents
        elif assigning_user.role == 'manager':
            return (target_user == assigning_user or
                   target_user.manager == assigning_user or 
                   (target_user.team_lead and target_user.team_lead.manager == assigning_user))
        
        # Team Lead can assign to themselves or their agents only
        elif assigning_user.role == 'team_lead':
            return (target_user == assigning_user or
                   target_user.team_lead == assigning_user)
        
        # Agent cannot assign leads
        return False
    
    def assign_to_user(self, user, assigned_by, bulk_assignment=False):
        """Assign lead to user with hierarchy validation"""
        if not self.can_be_assigned_by(assigned_by):
            raise PermissionError("User cannot assign this lead")
        
        # Check if this is a transfer (reassignment to different user OR bulk assignment from unassigned)
        is_transfer = (self.assigned_user and self.assigned_user != user) or (bulk_assignment and not self.assigned_user)
        
        # Track assignment history
        old_assignment = {
            'user': self.assigned_user.id if self.assigned_user else None, 
            'at': self.assigned_at.isoformat() if self.assigned_at else None
        }
        
        # If this is a transfer, populate transfer fields
        if is_transfer:
            if self.assigned_user:
                # Regular transfer from one user to another
                self.transfer_from = self.assigned_user.get_full_name() or self.assigned_user.username
            else:
                # Bulk assignment from unassigned state
                self.transfer_from = "Unassigned"
            self.transfer_by = assigned_by.get_full_name() or assigned_by.username
            self.transfer_date = timezone.now()
        
        self.assigned_user = user
        self.assigned_by = assigned_by
        self.assigned_at = timezone.now()
        
        # Update assignment history
        if 'assignments' not in self.assignment_history or not self.assignment_history:
            self.assignment_history = {'assignments': []}
        
        assignment_record = {
            'from': old_assignment,
            'to': {'user': user.id, 'at': self.assigned_at.isoformat()},
            'by': assigned_by.id
        }
        
        if is_transfer:
            assignment_record['action'] = 'transfer'
            assignment_record['transfer_from'] = self.transfer_from
            assignment_record['transfer_by'] = self.transfer_by
            assignment_record['transfer_date'] = self.transfer_date.isoformat()
        else:
            assignment_record['action'] = 'assignment'
        
        self.assignment_history['assignments'].append(assignment_record)
        
        # Update last assignment tracking for duplicate management
        if user.role == 'agent':
            self.last_assigned_agent = user
        elif user.role == 'manager':
            self.last_assigned_manager = user
        
        self.save()
        return True
    
    def get_reassignment_candidates(self):
        """Get reassignment candidates in priority order:
        1. Last assigned agent (if still active and accessible)
        2. Last assigned manager (if no agent available)
        3. Current assigned user (if different from above)
        """
        candidates = []
        
        # Check last assigned agent first
        if self.last_assigned_agent and self.last_assigned_agent.account_status == 'active':
            candidates.append({
                'user': self.last_assigned_agent,
                'priority': 1,
                'reason': 'Last Assigned Agent'
            })
        
        # Check last assigned manager
        if self.last_assigned_manager and self.last_assigned_manager.account_status == 'active':
            candidates.append({
                'user': self.last_assigned_manager,
                'priority': 2,
                'reason': 'Last Assigned Manager'
            })
        
        # Add current assigned user if not already in candidates
        if self.assigned_user and self.assigned_user.account_status == 'active':
            is_duplicate = any(c['user'].id == self.assigned_user.id for c in candidates)
            if not is_duplicate:
                candidates.append({
                    'user': self.assigned_user,
                    'priority': 3,
                    'reason': 'Current Assignment'
                })
        
        return sorted(candidates, key=lambda x: x['priority'])
    
    def resolve_duplicate(self, resolved_by, resolution_status='resolved', notes=None):
        """Mark duplicate as resolved with tracking"""
        self.duplicate_resolution_status = resolution_status
        self.duplicate_resolved_by = resolved_by
        self.duplicate_resolved_at = timezone.now()
        if notes:
            self.duplicate_notes = notes
        self.save()
        
        # Create activity log
        from .models import LeadActivity
        LeadActivity.objects.create(
            lead=self,
            user=resolved_by,
            activity_type='duplicate_resolution',
            description=f'Duplicate marked as {resolution_status}. {notes or ""}'
        )
    
    def get_duplicate_group(self):
        """Get all leads in the same duplicate group"""
        if not self.duplicate_group_id:
            return Lead.objects.none()
        
        return Lead.objects.filter(
            duplicate_group_id=self.duplicate_group_id,
            company_id=self.company_id
        ).exclude(id=self.id)
    
    def is_duplicate_of(self, other_lead):
        """Check if this lead is a duplicate of another lead"""
        if self.duplicate_group_id and other_lead.duplicate_group_id:
            return self.duplicate_group_id == other_lead.duplicate_group_id
        return False

class LeadComment(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Comment on {self.lead.name} by {self.user}"
    
    class Meta:
        db_table = 'lead_comments'
        ordering = ['-created_at']

class LeadHistory(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='history')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    action = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.action} on {self.lead.name} - {self.field_name}"
    
    class Meta:
        db_table = 'lead_history'
        ordering = ['-created_at']
        verbose_name_plural = 'Lead Histories'

class CommunicationHistory(models.Model):
    COMMUNICATION_TYPES = [
        ('call', 'Call'),
        ('sms', 'SMS'),
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
    ]
    
    DIRECTION_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    
    id_comm_history = models.AutoField(primary_key=True)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='communications', db_column='id_lead')
    communication_type = models.CharField(max_length=50, choices=COMMUNICATION_TYPES, null=True, blank=True)
    template_details = models.TextField(null=True, blank=True)
    text_msg = models.TextField(null=True, blank=True)
    media_details = models.TextField(null=True, blank=True)
    call_recording = models.TextField(null=True, blank=True)
    sent_datetime = models.DateTimeField(null=True, blank=True)
    receive_datetime = models.DateTimeField(null=True, blank=True)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.communication_type} - {self.lead.name}"
    
    class Meta:
        db_table = 'communication_history'
        ordering = ['-created_at']
        verbose_name_plural = 'Communication Histories'

class BackOfficeUpdate(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='bo_updates')
    bo_cat = models.CharField(max_length=255, null=True, blank=True)
    bo_date = models.DateField(null=True, blank=True)
    bo_status = models.CharField(max_length=255, null=True, blank=True)
    bo_ref = models.CharField(max_length=255, null=True, blank=True)
    bo_remarks = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"BO Update - {self.lead.name}"
    
    class Meta:
        db_table = 'back_office_updates'
        ordering = ['-created_at']

class Company(models.Model):
    name = models.CharField(max_length=255)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'companies'
        verbose_name_plural = 'Companies'

# Keep the old LeadActivity model for compatibility
class LeadActivity(models.Model):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    activity_type = models.CharField(max_length=50)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.lead.name} - {self.activity_type}"
    
    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Lead Activities'


class LeadOperationLog(models.Model):
    OPERATION_CHOICES = [
        ('import_preview', 'Import Preview'),
        ('import_process', 'Import Process'),
        ('bulk_delete', 'Bulk Delete'),
        ('bulk_restore', 'Bulk Restore'),
        ('trash_purge', 'Trash Purge'),
        ('bulk_assign', 'Bulk Assign'),
    ]

    operation_id = models.CharField(max_length=64, unique=True, db_index=True)
    operation_type = models.CharField(max_length=32, choices=OPERATION_CHOICES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    company_id = models.IntegerField(default=1, db_index=True)
    action_scope = models.CharField(max_length=20, default='current_page')
    filter_snapshot = models.TextField(blank=True, null=True)

    requested_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'operation_type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.operation_type} ({self.operation_id})"


class LeadImportSession(models.Model):
    STATUS_CHOICES = [
        ('preview_ready', 'Preview Ready'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    idempotency_key = models.CharField(max_length=128, db_index=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    company_id = models.IntegerField(default=1, db_index=True)
    file_name = models.CharField(max_length=255)
    file_hash = models.CharField(max_length=64, blank=True, null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='preview_ready')
    payload = models.JSONField(default=dict, blank=True)

    total_rows = models.PositiveIntegerField(default=0)
    new_rows = models.PositiveIntegerField(default=0)
    exact_duplicates = models.PositiveIntegerField(default=0)
    potential_duplicates = models.PositiveIntegerField(default=0)
    related_rows = models.PositiveIntegerField(default=0)
    imported_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    failed_rows = models.PositiveIntegerField(default=0)
    error_details = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'status', 'created_at']),
            models.Index(fields=['company_id', 'idempotency_key']),
        ]

    def __str__(self):
        return f"ImportSession {self.session_id} ({self.status})"

class InternalFollowUpReminder(models.Model):
    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    REMINDER_TYPES = [
        ('followup', 'Follow-up Reminder'),
        ('task', 'Task Reminder'),
        ('meeting', 'Meeting Reminder'),
        ('deadline', 'Deadline Reminder'),
        ('escalation', 'Escalation Reminder'),
    ]
    
    NOTIFICATION_CHANNELS = [
        ('in_app', 'In-App Only'),
        ('email', 'Internal Email Only'),
        ('sms', 'Internal SMS Only'),
        ('email_sms', 'Email + SMS'),
        ('all', 'All Internal Channels'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('acknowledged', 'Acknowledged'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Core fields
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='internal_reminders')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='internal_reminders')  # Team member to notify
    reminder_type = models.CharField(max_length=20, choices=REMINDER_TYPES, default='followup')
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    
    # Timing
    scheduled_datetime = models.DateTimeField()
    followup_datetime = models.DateTimeField()  # Original lead follow-up time
    reminder_before_minutes = models.PositiveIntegerField(default=30)  # Minutes before follow-up
    
    # Internal notification settings
    notification_channels = models.CharField(max_length=20, choices=NOTIFICATION_CHANNELS, default='in_app')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Internal content (team-focused)
    title = models.CharField(max_length=200)
    message = models.TextField()  # Internal message format
    team_notes = models.TextField(blank=True, null=True)  # Additional team context
    
    # Escalation settings
    escalate_to_manager = models.BooleanField(default=False)
    escalate_to_team_lead = models.BooleanField(default=False)
    escalation_minutes = models.PositiveIntegerField(default=60)  # Minutes after reminder to escalate
    
    # Tracking
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    last_sent_channel = models.CharField(max_length=20, blank=True, null=True)
    retry_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    
    # Hierarchy support
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_internal_reminders')
    company_id = models.IntegerField(default=1)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_follow_up_reminders'
        indexes = [
            models.Index(fields=['scheduled_datetime', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['lead', 'status']),
            models.Index(fields=['priority', 'scheduled_datetime']),
            models.Index(fields=['company_id', 'status']),
        ]
        ordering = ['scheduled_datetime']
    
    def __str__(self):
        return f"Internal Reminder: {self.title} - {self.user.username}"
    
    def get_escalation_users(self):
        """Get users to escalate to based on hierarchy"""
        users = []
        if self.escalate_to_team_lead and self.user.team_lead:
            users.append(self.user.team_lead)
        if self.escalate_to_manager and self.user.manager:
            users.append(self.user.manager)
        return users

class InternalNotificationTemplate(models.Model):
    TEMPLATE_TYPES = [
        ('followup_reminder', 'Follow-up Reminder'),
        ('overdue_followup', 'Overdue Follow-up'),
        ('urgent_followup', 'Urgent Follow-up'),
        ('escalation', 'Escalation Notice'),
        ('daily_summary', 'Daily Team Summary'),
        ('weekly_summary', 'Weekly Team Summary'),
        ('team_performance', 'Team Performance Alert'),
    ]
    
    CHANNEL_TYPES = [
        ('in_app', 'In-App'),
        ('email', 'Internal Email'),
        ('sms', 'Internal SMS'),
    ]
    
    name = models.CharField(max_length=100)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    channel = models.CharField(max_length=10, choices=CHANNEL_TYPES)
    
    # Internal template content with placeholders
    subject_template = models.CharField(max_length=200, blank=True, null=True)  # For internal email
    body_template = models.TextField()  # Internal message format
    
    # Settings
    is_active = models.BooleanField(default=True)
    company_id = models.IntegerField(default=1)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'internal_notification_templates'
        indexes = [
            models.Index(fields=['template_type', 'channel']),
            models.Index(fields=['company_id', 'is_active']),
        ]
        ordering = ['template_type', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.get_template_type_display()}"

class TeamNotificationPreference(models.Model):
    INTERNAL_NOTIFICATION_TYPES = [
        ('followup_reminder', 'My Follow-up Reminders'),
        ('overdue_followup', 'My Overdue Follow-ups'),
        ('team_reminder', 'Team Follow-up Alerts'),
        ('escalation', 'Escalation Notices'),
        ('daily_summary', 'Daily Team Summary'),
        ('weekly_summary', 'Weekly Team Summary'),
        ('performance_alert', 'Performance Alerts'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='team_notification_preferences')
    notification_type = models.CharField(max_length=50, choices=INTERNAL_NOTIFICATION_TYPES)
    
    # Internal channel preferences
    in_app_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    
    # Internal timing preferences
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Internal frequency preferences
    daily_summary_enabled = models.BooleanField(default=False)
    weekly_summary_enabled = models.BooleanField(default=False)
    team_alerts_enabled = models.BooleanField(default=True)
    escalation_alerts_enabled = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'team_notification_preferences'
        unique_together = ['user', 'notification_type']
        indexes = [
            models.Index(fields=['user', 'notification_type']),
        ]
        ordering = ['user', 'notification_type']
    
    def __str__(self):
        return f"{self.user.username} - {self.get_notification_type_display()}"


class BulkOperation(models.Model):
    """Track bulk operations with progress and status"""
    
    OPERATION_TYPES = [
        ('bulk_assign', 'Bulk Assign'),
        ('bulk_delete', 'Bulk Delete'),
        ('bulk_reassign_duplicates', 'Bulk Reassign Duplicates'),
        ('user_deletion_reassign', 'User Deletion Reassign'),
        ('bulk_import', 'Bulk Import'),
        ('bulk_export', 'Bulk Export'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    # Core identification
    operation_id = models.CharField(max_length=64, unique=True, db_index=True)
    operation_type = models.CharField(max_length=50, choices=OPERATION_TYPES)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='bulk_operations')
    company_id = models.IntegerField(default=1, db_index=True)
    
    # Status and timing
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    estimated_duration = models.PositiveIntegerField(null=True, blank=True, help_text="Estimated duration in seconds")
    
    # Progress tracking
    total_items = models.PositiveIntegerField(default=0)
    processed_items = models.PositiveIntegerField(default=0)
    success_items = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    skipped_items = models.PositiveIntegerField(default=0)
    
    # Progress percentage (calculated field)
    progress_percentage = models.FloatField(default=0.0, help_text="Progress percentage (0-100)")
    
    # Configuration and metadata
    operation_config = models.JSONField(default=dict, blank=True, help_text="Operation configuration")
    filter_snapshot = models.JSONField(default=dict, blank=True, help_text="Filter parameters snapshot")
    metadata = models.JSONField(default=dict, blank=True, help_text="Additional metadata")
    
    # Error handling
    error_message = models.TextField(null=True, blank=True)
    error_details = models.JSONField(default=dict, blank=True, help_text="Detailed error information")
    
    # Performance metrics
    items_per_second = models.FloatField(default=0.0, help_text="Processing rate")
    peak_memory_usage = models.BigIntegerField(null=True, blank=True, help_text="Peak memory usage in bytes")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'bulk_operations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['company_id', 'operation_type', 'status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['operation_id']),
        ]
    
    def __str__(self):
        return f"{self.get_operation_type_display()} ({self.operation_id})"
    
    def start_operation(self):
        """Mark operation as started"""
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])
    
    def complete_operation(self, success=True, error_message=None):
        """Mark operation as completed"""
        self.status = 'completed' if success else 'failed'
        self.completed_at = timezone.now()
        if error_message:
            self.error_message = error_message
        
        # Calculate final progress
        if self.total_items > 0:
            self.progress_percentage = 100.0
        
        # Calculate processing rate
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()
            if duration > 0:
                self.items_per_second = self.processed_items / duration
        
        self.save(update_fields=['status', 'completed_at', 'error_message', 'progress_percentage', 'items_per_second'])
    
    def update_progress(self, processed=0, success=0, failed=0, skipped=0):
        """Update operation progress"""
        self.processed_items += processed
        self.success_items += success
        self.failed_items += failed
        self.skipped_items += skipped
        
        # Calculate progress percentage
        if self.total_items > 0:
            self.progress_percentage = min(100.0, (self.processed_items / self.total_items) * 100.0)
        
        # Calculate processing rate
        if self.started_at:
            elapsed = (timezone.now() - self.started_at).total_seconds()
            if elapsed > 0:
                self.items_per_second = self.processed_items / elapsed
        
        self.save(update_fields=[
            'processed_items', 'success_items', 'failed_items', 
            'skipped_items', 'progress_percentage', 'items_per_second'
        ])
    
    def cancel_operation(self, reason=None):
        """Cancel the operation"""
        self.status = 'cancelled'
        self.completed_at = timezone.now()
        if reason:
            self.error_message = reason
        self.save(update_fields=['status', 'completed_at', 'error_message'])
    
    def get_eta_seconds(self):
        """Get estimated time remaining in seconds"""
        if self.status != 'running' or self.processed_items == 0:
            return None
        
        elapsed = (timezone.now() - self.started_at).total_seconds()
        if elapsed == 0:
            return None
        
        rate = self.processed_items / elapsed
        if rate == 0:
            return None
        
        remaining_items = self.total_items - self.processed_items
        return remaining_items / rate
    
    def get_eta_display(self):
        """Get human-readable ETA"""
        eta_seconds = self.get_eta_seconds()
        if eta_seconds is None:
            return "Calculating..."
        
        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            return f"{int(eta_seconds / 60)}m {int(eta_seconds % 60)}s"
        else:
            hours = int(eta_seconds / 3600)
            minutes = int((eta_seconds % 3600) / 60)
            return f"{hours}h {minutes}m"


class BulkOperationProgress(models.Model):
    """Detailed progress tracking for bulk operations"""
    
    # Core identification
    operation = models.ForeignKey(BulkOperation, on_delete=models.CASCADE, related_name='progress_updates')
    update_id = models.CharField(max_length=64, db_index=True)  # Unique identifier for this update
    
    # Progress information
    current_batch = models.PositiveIntegerField(default=0, help_text="Current batch number")
    batch_size = models.PositiveIntegerField(default=0, help_text="Size of current batch")
    total_batches = models.PositiveIntegerField(default=0, help_text="Total number of batches")
    
    # Batch results
    batch_success = models.PositiveIntegerField(default=0)
    batch_failed = models.PositiveIntegerField(default=0)
    batch_skipped = models.PositiveIntegerField(default=0)
    
    # Cumulative results
    cumulative_processed = models.PositiveIntegerField(default=0)
    cumulative_success = models.PositiveIntegerField(default=0)
    cumulative_failed = models.PositiveIntegerField(default=0)
    cumulative_skipped = models.PositiveIntegerField(default=0)
    
    # Performance metrics
    batch_duration = models.FloatField(default=0.0, help_text="Duration of this batch in seconds")
    cumulative_duration = models.FloatField(default=0.0, help_text="Total elapsed time in seconds")
    batch_rate = models.FloatField(default=0.0, help_text="Items per second for this batch")
    
    # Additional information
    batch_details = models.JSONField(default=dict, blank=True, help_text="Detailed batch information")
    error_samples = models.JSONField(default=list, blank=True, help_text="Sample errors from this batch")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'bulk_operation_progress'
        ordering = ['created_at']
        unique_together = ['operation', 'update_id']
        indexes = [
            models.Index(fields=['operation', 'created_at']),
            models.Index(fields=['operation', 'current_batch']),
        ]
    
    def __str__(self):
        return f"Progress Update {self.update_id} for {self.operation.operation_id}"
    
    @property
    def progress_percentage(self):
        """Calculate progress percentage"""
        if self.operation.total_items == 0:
            return 0.0
        return min(100.0, (self.cumulative_processed / self.operation.total_items) * 100.0)
