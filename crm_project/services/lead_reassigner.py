from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadActivity
import logging

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
                
                # Process active leads - reassign to hierarchy
                for lead in active_leads:
                    replacement_user = self.find_replacement_user(deleted_user)
                    if replacement_user:
                        self.perform_reassignment(lead, replacement_user, deleted_by)
                        results['active_leads_reassigned'] += 1
                        results['reassignment_details'].append({
                            'lead_id': lead.id_lead,
                            'lead_name': lead.name,
                            'from_user': deleted_user.username,
                            'to_user': replacement_user.username,
                            'revenue': lead.exp_revenue or 0
                        })
                    else:
                        logger.warning(f"No replacement user found for lead {lead.id_lead}")
                
                # Process converted leads - preserve sales credit
                for lead in converted_leads:
                    preserved_revenue = self.preserve_sales_credit(lead, deleted_user)
                    results['converted_leads_preserved'] += 1
                    results['total_revenue_preserved'] += preserved_revenue
                    results['preservation_details'].append({
                        'lead_id': lead.id_lead,
                        'lead_name': lead.name,
                        'preserved_credit_user': deleted_user.username,
                        'preserved_revenue': preserved_revenue
                    })
                
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
