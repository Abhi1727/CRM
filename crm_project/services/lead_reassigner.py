from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadActivity, BulkOperation, BulkOperationProgress
from accounts.models import User
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
import uuid

User = get_user_model()
logger = logging.getLogger(__name__)

class LeadReassigner:
    """
    Intelligent lead reassignment service that preserves sales credit and performance data
    when users are deleted from the CRM system.
    """
    
    def __init__(self):
        self.role_hierarchy = {
            'owner': 4,
            'manager': 3, 
            'team_lead': 2,
            'agent': 1
        }
    
    def reassign_user_leads_to_specific(self, deleted_user, selected_user, deleted_by):
        """
        Reassign all leads from deleted_user to a specifically selected user.
        Admin-only manual reassignment that bypasses hierarchy.
        
        Args:
            deleted_user: User object being deleted
            selected_user: User object selected to receive the leads
            deleted_by: User object performing the deletion (admin)
            
        Returns:
            dict: Summary of manual reassignment results
        """
        logger.info(f"DEBUG: Starting manual lead reassignment from {deleted_user.username} to {selected_user.username} by admin {deleted_by.username}")
        logger.info(f"DEBUG: deleted_user.id: {deleted_user.id}, selected_user.id: {selected_user.id}, deleted_by.id: {deleted_by.id}")
        logger.info(f"DEBUG: deleted_user.role: {deleted_user.role}, selected_user.role: {selected_user.role}, deleted_by.role: {deleted_by.role}")
        
        try:
            with transaction.atomic():
                # Get all leads assigned to the deleted user
                user_leads = Lead.objects.filter(assigned_user=deleted_user)
                logger.info(f"DEBUG: Found {user_leads.count()} total leads for user {deleted_user.username}")
                
                # Separate active leads from converted leads based on status
                active_leads = user_leads.exclude(status='sale_done')  # Leads that are NOT sold
                converted_leads = user_leads.filter(status='sale_done')  # Leads that ARE sold
                
                logger.info(f"DEBUG: Found {active_leads.count()} active leads and {converted_leads.count()} converted leads for manual reassignment")
                
                # Log details of active leads
                for lead in active_leads:
                    logger.info(f"DEBUG: Active lead {lead.id_lead} - {lead.name} - Current assigned_user: {lead.assigned_user.username if lead.assigned_user else 'None'}")
                
                results = {
                    'active_leads_reassigned': 0,
                    'converted_leads_preserved': 0,
                    'total_revenue_preserved': 0,
                    'reassignment_details': [],
                    'preservation_details': [],
                    'manual_assignment': {
                        'from_user': deleted_user.username,
                        'to_user': selected_user.username,
                        'assigned_by': deleted_by.username,
                        'assignment_type': 'admin_manual'
                    }
                }
                
                logger.info(f"DEBUG: Results dictionary initialized: {results}")
                
                # Process active leads - reassign to selected user
                for lead in active_leads:
                    logger.info(f"DEBUG: Processing active lead {lead.id_lead} for manual reassignment")
                    self.perform_manual_reassignment(lead, selected_user, deleted_by, deleted_user)
                    results['active_leads_reassigned'] += 1
                    results['reassignment_details'].append({
                        'lead_id': lead.id_lead,
                        'lead_name': lead.name,
                        'from_user': deleted_user.username,
                        'to_user': selected_user.username,
                        'revenue': lead.exp_revenue or 0,
                        'assignment_type': 'admin_manual'
                    })
                    logger.info(f"DEBUG: Lead {lead.id_lead} successfully reassigned to {selected_user.username}")
                
                # Process converted leads - preserve sales credit (same as hierarchy method)
                for lead in converted_leads:
                    logger.info(f"DEBUG: Processing converted lead {lead.id_lead} for preservation")
                    preserved_revenue = self.preserve_sales_credit(lead, deleted_user)
                    results['converted_leads_preserved'] += 1
                    results['total_revenue_preserved'] += preserved_revenue
                    results['preservation_details'].append({
                        'lead_id': lead.id_lead,
                        'lead_name': lead.name,
                        'preserved_credit_user': deleted_user.username,
                        'preserved_revenue': preserved_revenue
                    })
                    logger.info(f"DEBUG: Lead {lead.id_lead} sales credit preserved, revenue: {preserved_revenue}")
                
                # Update preserved metrics for the deleted user
                self.update_preserved_metrics(deleted_user, converted_leads)
                
                # Handle hierarchy cleanup
                self.cleanup_hierarchy_relationships(deleted_user)
                
                logger.info(f"DEBUG: Manual lead reassignment completed successfully")
                logger.info(f"DEBUG: Final results: {results}")
                return results
                
        except Exception as e:
            logger.error(f"DEBUG: Error during manual lead reassignment from {deleted_user.username} to {selected_user.username}: {str(e)}")
            logger.error(f"DEBUG: Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"DEBUG: Traceback: {traceback.format_exc()}")
            raise

    def perform_manual_reassignment(self, lead, selected_user, deleted_by, deleted_user):
        """
        Execute manual lead reassignment by admin with enhanced activity logging.
        """
        logger.info(f"DEBUG: Manually reassigning lead {lead.id_lead} from {deleted_user.username} to {selected_user.username} by admin {deleted_by.username}")
        logger.info(f"DEBUG: Lead current assigned_user: {lead.assigned_user.username if lead.assigned_user else 'None'}")
        logger.info(f"DEBUG: Lead current status: {lead.status}")
        logger.info(f"DEBUG: Lead current transfer_from: {lead.transfer_from}")
        
        # Store old assignment for history
        old_user = deleted_user
        
        # Create special manual deletion transfer record
        lead.transfer_from = old_user.get_full_name() or old_user.username
        lead.transfer_by = deleted_by.get_full_name() or deleted_by.username
        lead.transfer_date = timezone.now()
        
        logger.info(f"DEBUG: Set transfer_from: {lead.transfer_from}, transfer_by: {lead.transfer_by}, transfer_date: {lead.transfer_date}")
        
        # Update assignment
        lead.assigned_user = selected_user
        lead.assigned_by = deleted_by
        lead.assigned_at = timezone.now()
        
        logger.info(f"DEBUG: Updated assigned_user to: {selected_user.username}, assigned_by: {deleted_by.username}, assigned_at: {lead.assigned_at}")
        
        # Update assignment history with manual deletion record
        if 'assignments' not in lead.assignment_history or not lead.assignment_history:
            lead.assignment_history = {'assignments': []}
            logger.info(f"DEBUG: Initialized assignment_history for lead {lead.id_lead}")
        
        manual_deletion_record = {
            'from': {'user': old_user.id, 'at': lead.assigned_at.isoformat()},
            'to': {'user': selected_user.id, 'at': timezone.now().isoformat()},
            'by': deleted_by.id,
            'action': 'admin_manual_reassignment',
            'transfer_from': lead.transfer_from,
            'transfer_by': lead.transfer_by,
            'transfer_date': lead.transfer_date.isoformat(),
            'reason': f'Admin {deleted_by.username} manually reassigned lead from deleted user {old_user.username}',
            'admin_choice': {
                'admin_id': deleted_by.id,
                'admin_username': deleted_by.username,
                'selected_user_id': selected_user.id,
                'selected_username': selected_user.username,
                'bypassed_hierarchy': True
            }
        }
        
        lead.assignment_history['assignments'].append(manual_deletion_record)
        logger.info(f"DEBUG: Added manual deletion record to assignment_history: {manual_deletion_record}")
        
        # Update last assignment tracking
        if selected_user.role == 'agent':
            lead.last_assigned_agent = selected_user
            logger.info(f"DEBUG: Set last_assigned_agent to {selected_user.username}")
        elif selected_user.role == 'manager':
            lead.last_assigned_manager = selected_user
            logger.info(f"DEBUG: Set last_assigned_manager to {selected_user.username}")
        
        lead.save()
        logger.info(f"DEBUG: Lead {lead.id_lead} saved successfully")
        
        # Create enhanced activity log for admin manual reassignment
        activity = LeadActivity.objects.create(
            lead=lead,
            user=deleted_by,
            activity_type='admin_manual_reassignment',
            description=f'Admin manually reassigned lead from {old_user.username} to {selected_user.username} due to user deletion'
        )
        logger.info(f"DEBUG: Created activity log entry: {activity.id} - {activity.description}")
        
        logger.info(f"DEBUG: Lead {lead.id_lead} successfully manually reassigned to {selected_user.username} by admin {deleted_by.username}")

    def reassign_user_leads(self, deleted_user, deleted_by):
        """
        Main entry point for reassigning leads when a user is deleted.
        Preserves all sales credit and performance data.
        
        Args:
            deleted_user: User object being deleted
            deleted_by: User object performing the deletion
            
        Returns:
            dict: Summary of reassignment results
        """
        logger.info(f"Starting lead reassignment for user {deleted_user.username} (ID: {deleted_user.id})")
        
        try:
            with transaction.atomic():
                # Get all leads assigned to the deleted user
                user_leads = Lead.objects.filter(assigned_user=deleted_user)
                
                # Separate active leads from converted leads based on status
                active_leads = user_leads.exclude(status='sale_done')  # Leads that are NOT sold
                converted_leads = user_leads.filter(status='sale_done')  # Leads that ARE sold
                
                logger.info(f"Found {active_leads.count()} active leads and {converted_leads.count()} converted leads")
                
                results = {
                    'active_leads_reassigned': 0,
                    'converted_leads_preserved': 0,
                    'total_revenue_preserved': 0,
                    'reassignment_details': [],
                    'preservation_details': []
                }
                
                # Use optimized bulk reassignment for active leads
                if active_leads:
                    reassign_results = self.reassign_user_leads_optimized(deleted_user, deleted_by, active_leads, converted_leads)
                    results.update(reassign_results)
                
                # Converted leads are now handled in the optimized function above
                
                # Update preserved metrics for the deleted user
                self.update_preserved_metrics(deleted_user, converted_leads)
                
                # Handle hierarchy cleanup
                self.cleanup_hierarchy_relationships(deleted_user)
                
                logger.info(f"Lead reassignment completed for {deleted_user.username}")
                return results
                
        except Exception as e:
            logger.error(f"Error during lead reassignment for user {deleted_user.username}: {str(e)}")
            raise
    
    def find_replacement_user(self, deleted_user):
        """
        Find appropriate replacement user based on hierarchy.
        Follows the hierarchy: Agent -> Team Lead -> Manager -> Owner
        """
        logger.info(f"Finding replacement user for {deleted_user.username} (role: {deleted_user.role})")
        
        if deleted_user.role == 'agent':
            # Agent deleted: reassign to team lead -> manager -> owner
            replacement = self._find_agent_replacement(deleted_user)
        elif deleted_user.role == 'team_lead':
            # Team lead deleted: reassign to manager -> owner
            replacement = self._find_team_lead_replacement(deleted_user)
        elif deleted_user.role == 'manager':
            # Manager deleted: reassign to owner
            replacement = self._find_manager_replacement(deleted_user)
        elif deleted_user.role == 'owner':
            # Owner deleted: reassign to next available owner or highest manager
            replacement = self._find_owner_replacement(deleted_user)
        else:
            replacement = None
        
        logger.info(f"Selected replacement: {replacement.username if replacement else 'None'}")
        return replacement
    
    def _find_agent_replacement(self, deleted_agent):
        """Find replacement for deleted agent: Team Lead -> Manager -> Owner"""
        # First try team lead
        if deleted_agent.team_lead and deleted_agent.team_lead.account_status == 'active':
            return deleted_agent.team_lead
        
        # Then try manager
        if deleted_agent.manager and deleted_agent.manager.account_status == 'active':
            return deleted_agent.manager
        
        # Finally try owner
        owner = User.objects.filter(
            company_id=deleted_agent.company_id,
            role='owner',
            account_status='active'
        ).first()
        
        return owner
    
    def _find_team_lead_replacement(self, deleted_team_lead):
        """Find replacement for deleted team lead: Manager -> Owner"""
        # First try manager
        if deleted_team_lead.manager and deleted_team_lead.manager.account_status == 'active':
            return deleted_team_lead.manager
        
        # Then try owner
        owner = User.objects.filter(
            company_id=deleted_team_lead.company_id,
            role='owner',
            account_status='active'
        ).first()
        
        return owner
    
    def _find_manager_replacement(self, deleted_manager):
        """Find replacement for deleted manager: Owner"""
        owner = User.objects.filter(
            company_id=deleted_manager.company_id,
            role='owner',
            account_status='active'
        ).first()
        
        return owner
    
    def _find_owner_replacement(self, deleted_owner):
        """Find replacement for deleted owner: Next owner or highest manager"""
        # Try to find another owner in the same company
        other_owner = User.objects.filter(
            company_id=deleted_owner.company_id,
            role='owner',
            account_status='active',
            id__ne=deleted_owner.id
        ).first()
        
        if other_owner:
            return other_owner
        
        # If no other owner, find the highest-level manager
        manager = User.objects.filter(
            company_id=deleted_owner.company_id,
            role='manager',
            account_status='active'
        ).first()
        
        return manager
    
    def perform_reassignment(self, lead, new_user, deleted_by):
        """
        Execute lead reassignment while preserving all historical data.
        """
        logger.info(f"Reassigning lead {lead.id_lead} from {lead.assigned_user.username} to {new_user.username}")
        
        # Store old assignment for history
        old_user = lead.assigned_user
        
        # Create special deletion transfer record
        lead.transfer_from = old_user.get_full_name() or old_user.username
        lead.transfer_by = deleted_by.get_full_name() or deleted_by.username
        lead.transfer_date = timezone.now()
        
        # Update assignment
        lead.assigned_user = new_user
        lead.assigned_by = deleted_by
        lead.assigned_at = timezone.now()
        
        # Update assignment history with deletion record
        if 'assignments' not in lead.assignment_history or not lead.assignment_history:
            lead.assignment_history = {'assignments': []}
        
        deletion_record = {
            'from': {'user': old_user.id, 'at': lead.assigned_at.isoformat()},
            'to': {'user': new_user.id, 'at': timezone.now().isoformat()},
            'by': deleted_by.id,
            'action': 'deletion_reassignment',
            'transfer_from': lead.transfer_from,
            'transfer_by': lead.transfer_by,
            'transfer_date': lead.transfer_date.isoformat(),
            'reason': f'User {old_user.username} deleted - lead reassigned'
        }
        
        lead.assignment_history['assignments'].append(deletion_record)
        
        # Update last assignment tracking
        if new_user.role == 'agent':
            lead.last_assigned_agent = new_user
        elif new_user.role == 'manager':
            lead.last_assigned_manager = new_user
        
        lead.save()
        
        # Create activity log
        LeadActivity.objects.create(
            lead=lead,
            user=deleted_by,
            activity_type='deletion_reassignment',
            description=f'Lead reassigned from {old_user.username} to {new_user.username} due to user deletion'
        )
        
        logger.info(f"Lead {lead.id_lead} successfully reassigned to {new_user.username}")
    
    def preserve_sales_credit(self, lead, deleted_user):
        """
        Preserve sales credit for converted leads.
        The original user maintains credit for their sales.
        """
        logger.info(f"Preserving sales credit for converted lead {lead.id_lead} by {deleted_user.username}")
        
        # Store original assignment information
        lead.primary_sales_credit = deleted_user
        lead.original_assigned_user = deleted_user
        lead.sales_credit_preserved = True
        
        # Add preservation note to assignment history
        if 'assignments' not in lead.assignment_history or not lead.assignment_history:
            lead.assignment_history = {'assignments': []}
        
        preservation_record = {
            'action': 'sales_credit_preservation',
            'preserved_credit_user': deleted_user.id,
            'preserved_credit_username': deleted_user.username,
            'preserved_at': timezone.now().isoformat(),
            'reason': f'User deletion - sales credit preserved for {deleted_user.username}',
            'lead_status': lead.status,
            'revenue': lead.exp_revenue
        }
        
        lead.assignment_history['assignments'].append(preservation_record)
        
        # Update status to reflect preservation
        if lead.status == 'sale_done':
            lead.status = 'sale_done'  # Keep as sale_done but mark as preserved
            lead.status_description = f"Sale completed - Credit preserved for {deleted_user.username}"
        
        lead.save()
        
        # Create preservation activity log
        LeadActivity.objects.create(
            lead=lead,
            activity_type='sales_credit_preserved',
            description=f'Sales credit preserved for {deleted_user.username} - Revenue: {lead.exp_revenue or 0}',
            user_id=None  # System action
        )
        
        # Calculate preserved revenue
        try:
            preserved_revenue = float(lead.exp_revenue or 0)
        except (ValueError, TypeError):
            preserved_revenue = 0
        
        logger.info(f"Sales credit preserved for lead {lead.id_lead} - Revenue: {preserved_revenue}")
        return preserved_revenue
    
    def update_preserved_metrics(self, deleted_user, converted_leads):
        """
        Update preserved performance metrics for the deleted user.
        """
        logger.info(f"Updating preserved metrics for {deleted_user.username}")
        
        # Count preserved converted leads and revenue
        preserved_converted_count = converted_leads.count()
        total_preserved_revenue = 0
        
        for lead in converted_leads:
            try:
                revenue = float(lead.exp_revenue or 0)
                total_preserved_revenue += revenue
            except (ValueError, TypeError):
                continue
        
        # Update user metrics (these will remain even after user is deactivated)
        deleted_user.preserved_leads_count = preserved_converted_count
        deleted_user.preserved_converted_count = preserved_converted_count
        deleted_user.preserved_revenue = total_preserved_revenue
        
        # Don't decrement the original leads_converted_count - preserve it
        # This ensures historical performance data remains intact
        
        deleted_user.save()
        
        logger.info(f"Updated preserved metrics for {deleted_user.username}: "
                   f"{preserved_converted_count} leads, {total_preserved_revenue} revenue")
    
    def cleanup_hierarchy_relationships(self, deleted_user):
        """
        Clean up hierarchy relationships when a user is deleted.
        """
        logger.info(f"Cleaning up hierarchy relationships for {deleted_user.username}")
        
        if deleted_user.role == 'team_lead':
            # Remove team lead reference from agents
            User.objects.filter(team_lead=deleted_user).update(team_lead=None)
            
        elif deleted_user.role == 'manager':
            # Remove manager reference from team leads and agents
            User.objects.filter(manager=deleted_user).update(manager=None)
            
        elif deleted_user.role == 'owner':
            # Owner deletion - no specific cleanup needed as other users remain
            pass
        
        logger.info(f"Hierarchy cleanup completed for {deleted_user.username}")
    
    def get_reassignment_summary(self, deleted_user):
        """
        Get a summary of what will happen to leads if this user is deleted.
        Used for display in the deletion confirmation page.
        """
        user_leads = Lead.objects.filter(assigned_user=deleted_user)
        active_leads = user_leads.exclude(status='sale_done')  # Leads that are NOT sold
        converted_leads = user_leads.filter(status='sale_done')  # Leads that ARE sold
        
        replacement_user = self.find_replacement_user(deleted_user)
        
        # Calculate total preserved revenue
        total_revenue = 0
        for lead in converted_leads:
            try:
                revenue = float(lead.exp_revenue or 0)
                total_revenue += revenue
            except (ValueError, TypeError):
                continue
        
        summary = {
            'user_name': deleted_user.get_full_name() or deleted_user.username,
            'user_role': deleted_user.get_role_display(),
            'active_leads_count': active_leads.count(),
            'converted_leads_count': converted_leads.count(),
            'total_preserved_revenue': total_revenue,
            'replacement_user': replacement_user.get_full_name() or replacement_user.username if replacement_user else None,
            'replacement_role': replacement_user.get_role_display() if replacement_user else None,
            'impact_level': self._calculate_impact_level(deleted_user, active_leads.count(), converted_leads.count())
        }
        
        return summary
    
    def _calculate_impact_level(self, user, active_count, converted_count):
        """Calculate the impact level of user deletion for warning purposes"""
        if converted_count > 50 or active_count > 100:
            return 'high'
        elif converted_count > 20 or active_count > 50:
            return 'medium'
        else:
            return 'low'
    
    def reassign_user_leads_optimized(self, deleted_user, deleted_by, active_leads=None, converted_leads=None):
        """Optimized bulk lead reassignment for user deletion"""
        start_time = time.time()
        
        with transaction.atomic():
            # Get all leads in single query if not provided
            if active_leads is None or converted_leads is None:
                user_leads = Lead.objects.filter(assigned_user=deleted_user).select_related('assigned_user')
                
                if active_leads is None:
                    active_leads = list(user_leads.exclude(status='sale_done'))
                if converted_leads is None:
                    converted_leads = list(user_leads.filter(status='sale_done'))
            
            # Find replacement user once (not per lead)
            replacement_user = self.find_replacement_user(deleted_user)
            
            results = {
                'active_leads_reassigned': 0,
                'converted_leads_preserved': 0,
                'total_revenue_preserved': 0,
                'reassignment_details': [],
                'preservation_details': []
            }
            
            if replacement_user and active_leads:
                # Bulk reassign active leads
                active_lead_ids = [lead.id_lead for lead in active_leads]
                update_count = Lead.objects.filter(id_lead__in=active_lead_ids).update(
                    assigned_user=replacement_user,
                    assigned_by=deleted_by,
                    assigned_at=timezone.now(),
                    transfer_from=deleted_user.get_full_name() or deleted_user.username,
                    transfer_by=deleted_by.get_full_name() or deleted_by.username,
                    transfer_date=timezone.now()
                )
                
                results['active_leads_reassigned'] = update_count
                
                # Bulk create assignment activities
                activity_data = [
                    LeadActivity(
                        lead_id=lead_id,
                        user=deleted_by,
                        activity_type='deletion_reassignment',
                        description=f'Lead reassigned from {deleted_user.username} to {replacement_user.username} due to user deletion'
                    )
                    for lead_id in active_lead_ids
                ]
                LeadActivity.objects.bulk_create(activity_data, batch_size=500)
                
                # Add reassignment details for reporting
                for lead in active_leads:
                    results['reassignment_details'].append({
                        'lead_id': lead.id_lead,
                        'lead_name': lead.name,
                        'from_user': deleted_user.username,
                        'to_user': replacement_user.username,
                        'revenue': lead.exp_revenue or 0
                    })
            
            # Bulk preserve converted leads (existing logic optimized)
            if converted_leads:
                preserved_revenue = self._bulk_preserve_sales_credit(converted_leads, deleted_user)
                results['converted_leads_preserved'] = len(converted_leads)
                results['total_revenue_preserved'] = preserved_revenue
            
            elapsed_time = time.time() - start_time
            logger.info(f"Optimized reassignment completed in {elapsed_time:.2f}s - "
                       f"Active: {results['active_leads_reassigned']}, "
                       f"Converted: {results['converted_leads_preserved']}")
            
            return results
    
    def reassign_user_leads_optimized_with_progress(self, deleted_user, deleted_by, operation=None, active_leads=None, converted_leads=None):
        """Optimized bulk lead reassignment for user deletion with progress tracking"""
        start_time = time.time()
        
        # Create operation if not provided
        if operation is None:
            operation_id = f"user_deletion_reassign_{uuid.uuid4().hex[:12]}"
            total_leads = Lead.objects.filter(assigned_user=deleted_user).count()
            operation = BulkOperation.objects.create(
                operation_id=operation_id,
                operation_type='user_deletion_reassign',
                user=deleted_by,
                company_id=deleted_user.company_id,
                total_items=total_leads,
                operation_config={
                    'deleted_user_id': deleted_user.id,
                    'deleted_user_name': deleted_user.username,
                    'deleted_by_id': deleted_by.id,
                    'deleted_by_name': deleted_by.username
                }
            )
            operation.start_operation()
        
        try:
            with transaction.atomic():
                # Get all leads in single query if not provided
                if active_leads is None or converted_leads is None:
                    user_leads = Lead.objects.filter(assigned_user=deleted_user).select_related('assigned_user')
                    
                    if active_leads is None:
                        active_leads = list(user_leads.exclude(status='sale_done'))
                    if converted_leads is None:
                        converted_leads = list(user_leads.filter(status='sale_done'))
                
                # Find replacement user once (not per lead)
                replacement_user = self.find_replacement_user(deleted_user)
                
                results = {
                    'active_leads_reassigned': 0,
                    'converted_leads_preserved': 0,
                    'total_revenue_preserved': 0,
                    'reassignment_details': [],
                    'preservation_details': []
                }
                
                # Process active leads with progress tracking
                if replacement_user and active_leads:
                    batch_size = 1000
                    total_batches = (len(active_leads) + batch_size - 1) // batch_size
                    
                    for batch_num in range(0, len(active_leads), batch_size):
                        batch_start_time = time.time()
                        batch_leads = active_leads[batch_num:batch_num + batch_size]
                        current_batch = (batch_num // batch_size) + 1
                        
                        batch_success = 0
                        batch_failed = 0
                        batch_errors = []
                        
                        try:
                            # Bulk reassign active leads in this batch
                            active_lead_ids = [lead.id_lead for lead in batch_leads]
                            update_count = Lead.objects.filter(id_lead__in=active_lead_ids).update(
                                assigned_user=replacement_user,
                                assigned_by=deleted_by,
                                assigned_at=timezone.now(),
                                transfer_from=deleted_user.get_full_name() or deleted_user.username,
                                transfer_by=deleted_by.get_full_name() or deleted_by.username,
                                transfer_date=timezone.now()
                            )
                            
                            batch_success = update_count
                            
                            # Bulk create assignment activities
                            activity_data = [
                                LeadActivity(
                                    lead_id=lead_id,
                                    user=deleted_by,
                                    activity_type='deletion_reassignment',
                                    description=f'Lead reassigned from {deleted_user.username} to {replacement_user.username} due to user deletion'
                                )
                                for lead_id in active_lead_ids
                            ]
                            LeadActivity.objects.bulk_create(activity_data, batch_size=500)
                            
                            # Add reassignment details for reporting
                            for lead in batch_leads:
                                results['reassignment_details'].append({
                                    'lead_id': lead.id_lead,
                                    'lead_name': lead.name,
                                    'from_user': deleted_user.username,
                                    'to_user': replacement_user.username,
                                    'revenue': lead.exp_revenue or 0
                                })
                            
                            results['active_leads_reassigned'] += batch_success
                            
                        except Exception as e:
                            batch_failed = len(batch_leads)
                            batch_errors.append({
                                'error': str(e),
                                'batch_num': current_batch,
                                'lead_count': len(batch_leads)
                            })
                        
                        batch_duration = time.time() - batch_start_time
                        
                        # Update progress
                        self._update_operation_progress(
                            operation, current_batch, len(batch_leads), total_batches,
                            batch_success, batch_failed, 0, batch_duration,
                            batch_errors[:5]  # Keep only first 5 errors
                        )
                
                # Process converted leads with progress tracking
                if converted_leads:
                    batch_size = 1000
                    total_converted_batches = (len(converted_leads) + batch_size - 1) // batch_size
                    
                    for batch_num in range(0, len(converted_leads), batch_size):
                        batch_start_time = time.time()
                        batch_leads = converted_leads[batch_num:batch_num + batch_size]
                        current_batch = (batch_num // batch_size) + 1
                        
                        batch_success = 0
                        batch_failed = 0
                        batch_errors = []
                        
                        try:
                            preserved_revenue = self._bulk_preserve_sales_credit(batch_leads, deleted_user)
                            batch_success = len(batch_leads)
                            results['converted_leads_preserved'] += batch_success
                            results['total_revenue_preserved'] += preserved_revenue
                            
                        except Exception as e:
                            batch_failed = len(batch_leads)
                            batch_errors.append({
                                'error': str(e),
                                'batch_num': current_batch,
                                'lead_count': len(batch_leads)
                            })
                        
                        batch_duration = time.time() - batch_start_time
                        
                        # Update progress for converted leads
                        self._update_operation_progress(
                            operation, current_batch, len(batch_leads), total_converted_batches,
                            batch_success, batch_failed, 0, batch_duration,
                            batch_errors[:5]
                        )
                
                elapsed_time = time.time() - start_time
                logger.info(f"Optimized reassignment with progress completed in {elapsed_time:.2f}s - "
                           f"Active: {results['active_leads_reassigned']}, "
                           f"Converted: {results['converted_leads_preserved']}")
                
                # Complete operation successfully
                operation.complete_operation(success=True)
                
                return results
                
        except Exception as e:
            # Complete operation with error
            operation.complete_operation(success=False, error_message=str(e))
            logger.error(f"Error in optimized reassignment with progress: {str(e)}")
            raise
    
    def _update_operation_progress(self, operation, batch_num, batch_size, total_batches, 
                                  batch_success, batch_failed, batch_skipped, batch_duration, error_samples=None):
        """Update operation progress with batch information"""
        update_id = f"{operation.operation_id}_batch_{batch_num}"
        
        # Calculate cumulative totals
        cumulative_processed = operation.processed_items + batch_success + batch_failed + batch_skipped
        cumulative_success = operation.success_items + batch_success
        cumulative_failed = operation.failed_items + batch_failed
        cumulative_skipped = operation.skipped_items + batch_skipped
        
        # Update main operation
        operation.update_progress(
            processed=batch_success + batch_failed + batch_skipped,
            success=batch_success,
            failed=batch_failed,
            skipped=batch_skipped
        )
        
        # Create detailed progress record
        BulkOperationProgress.objects.create(
            operation=operation,
            update_id=update_id,
            current_batch=batch_num,
            batch_size=batch_size,
            total_batches=total_batches,
            batch_success=batch_success,
            batch_failed=batch_failed,
            batch_skipped=batch_skipped,
            cumulative_processed=cumulative_processed,
            cumulative_success=cumulative_success,
            cumulative_failed=cumulative_failed,
            cumulative_skipped=cumulative_skipped,
            batch_duration=batch_duration,
            cumulative_duration=(timezone.now() - operation.started_at).total_seconds() if operation.started_at else 0,
            batch_rate=(batch_success + batch_failed + batch_skipped) / batch_duration if batch_duration > 0 else 0,
            error_samples=error_samples or []
        )
    
    def _bulk_preserve_sales_credit(self, converted_leads, deleted_user):
        """Bulk preserve sales credit for converted leads"""
        if not converted_leads:
            return 0
        
        # Bulk update converted leads
        lead_ids = [lead.id_lead for lead in converted_leads]
        Lead.objects.filter(id_lead__in=lead_ids).update(
            primary_sales_credit=deleted_user,
            original_assigned_user=deleted_user,
            sales_credit_preserved=True,
            status_description=f"Sale completed - Credit preserved for {deleted_user.username}"
        )
        
        # Bulk create preservation activities
        activity_data = [
            LeadActivity(
                lead_id=lead_id,
                activity_type='sales_credit_preserved',
                description=f'Sales credit preserved for {deleted_user.username} - Revenue: {lead.exp_revenue or 0}',
                user_id=None  # System action
            )
            for lead_id, lead in zip(lead_ids, converted_leads)
        ]
        LeadActivity.objects.bulk_create(activity_data, batch_size=500)
        
        # Calculate total preserved revenue
        total_revenue = sum(float(lead.exp_revenue or 0) for lead in converted_leads)
        return total_revenue
