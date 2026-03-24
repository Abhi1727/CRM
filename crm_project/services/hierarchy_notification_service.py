from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q, Count
from typing import List, Dict, Any, Optional, Set
import logging

from dashboard.models import (
    Lead, InternalFollowUpReminder, User, TeamNotificationPreference
)
from .internal_notification_service import InternalNotificationService
from .internal_reminder_service import InternalReminderService

logger = logging.getLogger(__name__)

class HierarchyNotificationService:
    """
    Service for handling notifications based on organizational hierarchy.
    Manages escalation paths, role-based notifications, and cross-team visibility.
    """
    
    def __init__(self):
        self.notification_service = InternalNotificationService()
        self.reminder_service = InternalReminderService()
    
    def send_hierarchy_notifications(self, event_type: str, data: Dict[str, Any]) -> bool:
        """
        Send notifications based on hierarchy for various events.
        
        Args:
            event_type: Type of event (lead_assigned, followup_overdue, etc.)
            data: Event data
            
        Returns:
            bool: True if successful
        """
        try:
            if event_type == 'lead_assigned':
                return self._handle_lead_assignment(data)
            elif event_type == 'followup_overdue':
                return self._handle_overdue_followup(data)
            elif event_type == 'critical_escalation':
                return self._handle_critical_escalation(data)
            elif event_type == 'team_performance_alert':
                return self._handle_performance_alert(data)
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send hierarchy notification for {event_type}: {e}")
            return False
    
    def get_hierarchy_notification_recipients(
        self, 
        trigger_user: User, 
        notification_type: str,
        include_higher: bool = True,
        include_peers: bool = False,
        include_lower: bool = False
    ) -> List[User]:
        """
        Get notification recipients based on hierarchy.
        
        Args:
            trigger_user: User who triggered the notification
            notification_type: Type of notification
            include_higher: Include managers/team leads above
            include_peers: Include users at same level
            include_lower: Include users below in hierarchy
            
        Returns:
            List[User]: Notification recipients
        """
        recipients = []
        
        # Get users based on hierarchy
        if include_higher:
            # Add team lead and manager
            if trigger_user.team_lead:
                recipients.append(trigger_user.team_lead)
            if trigger_user.manager:
                recipients.append(trigger_user.manager)
            
            # Add owner if exists
            try:
                owner = User.objects.get(
                    company_id=trigger_user.company_id,
                    role='owner'
                )
                recipients.append(owner)
            except User.DoesNotExist:
                pass
        
        if include_peers:
            # Get users at same level with same manager/team lead
            if trigger_user.manager:
                peers = User.objects.filter(
                    manager=trigger_user.manager,
                    role=trigger_user.role
                ).exclude(id=trigger_user.id)
                recipients.extend(peers)
            elif trigger_user.team_lead:
                peers = User.objects.filter(
                    team_lead=trigger_user.team_lead,
                    role=trigger_user.role
                ).exclude(id=trigger_user.id)
                recipients.extend(peers)
        
        if include_lower:
            # Get users below in hierarchy
            if trigger_user.role == 'owner':
                # All users in company
                lower_users = User.objects.filter(
                    company_id=trigger_user.company_id
                ).exclude(id=trigger_user.id)
            elif trigger_user.role == 'manager':
                # Team leads and agents under this manager
                lower_users = User.objects.filter(
                    Q(manager=trigger_user.id) | Q(team_lead__manager=trigger_user.id)
                ).exclude(id=trigger_user.id)
            elif trigger_user.role == 'team_lead':
                # Agents under this team lead
                lower_users = User.objects.filter(
                    team_lead=trigger_user.id
                ).exclude(id=trigger_user.id)
            else:
                lower_users = User.objects.none()
            
            recipients.extend(lower_users)
        
        # Filter users who want this type of notification
        filtered_recipients = []
        for user in recipients:
            if self._user_wants_hierarchy_notification(user, notification_type):
                filtered_recipients.append(user)
        
        # Remove duplicates and return
        return list(set(filtered_recipients))
    
    def send_cross_team_notification(
        self, 
        manager: User, 
        message: str,
        notification_type: str = 'team_alert',
        include_all_teams: bool = False
    ) -> bool:
        """
        Send notification across multiple teams.
        
        Args:
            manager: Manager sending the notification
            message: Notification message
            notification_type: Type of notification
            include_all_teams: Include all teams in company
            
        Returns:
            bool: True if successful
        """
        try:
            if include_all_teams and manager.role == 'owner':
                # Send to all users in company
                recipients = User.objects.filter(
                    company_id=manager.company_id,
                    account_status='active'
                ).exclude(id=manager.id)
            else:
                # Send to manager's accessible users
                recipients = manager.get_accessible_users()
            
            success_count = 0
            for user in recipients:
                if self._user_wants_hierarchy_notification(user, notification_type):
                    try:
                        # Send in-app notification
                        success = self.notification_service._send_in_app_notification_direct(
                            user=user,
                            title="Team Notification",
                            message=message,
                            notification_type=notification_type
                        )
                        if success:
                            success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to send cross-team notification to {user.username}: {e}")
            
            logger.info(f"Cross-team notification sent to {success_count} users by {manager.username}")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Failed to send cross-team notification: {e}")
            return False
    
    def get_hierarchy_dashboard_data(self, user: User) -> Dict[str, Any]:
        """
        Get dashboard data filtered by hierarchy.
        
        Args:
            user: User requesting dashboard data
            
        Returns:
            Dict: Hierarchy-filtered dashboard data
        """
        accessible_users = user.get_accessible_users()
        
        dashboard_data = {
            'hierarchy_level': user.get_hierarchy_level(),
            'accessible_users_count': accessible_users.count(),
            'team_structure': self._get_team_structure(user),
            'followup_overview': self._get_hierarchy_followup_overview(accessible_users),
            'escalation_status': self._get_escalation_status(user),
            'performance_comparison': self._get_performance_comparison(user, accessible_users),
        }
        
        return dashboard_data
    
    def escalate_through_hierarchy(
        self, 
        reminder: InternalFollowUpReminder,
        escalation_level: int = 1
    ) -> bool:
        """
        Escalate a reminder through the hierarchy.
        
        Args:
            reminder: The reminder to escalate
            escalation_level: Level of escalation (1=team lead, 2=manager, 3=owner)
            
        Returns:
            bool: True if successful
        """
        try:
            escalation_users = []
            
            if escalation_level >= 1 and reminder.user.team_lead:
                escalation_users.append(reminder.user.team_lead)
            
            if escalation_level >= 2 and reminder.user.manager:
                escalation_users.append(reminder.user.manager)
            
            if escalation_level >= 3:
                # Add owner
                try:
                    owner = User.objects.get(
                        company_id=reminder.company_id,
                        role='owner'
                    )
                    escalation_users.append(owner)
                except User.DoesNotExist:
                    pass
            
            if escalation_users:
                # Create escalation reminder
                escalation_reminder = InternalFollowUpReminder.objects.create(
                    lead=reminder.lead,
                    user=reminder.user,
                    reminder_type='escalation',
                    priority='urgent',
                    scheduled_datetime=timezone.now(),
                    followup_datetime=reminder.followup_datetime,
                    notification_channels='all',
                    title=f"Hierarchy Escalation Level {escalation_level}: {reminder.lead.name}",
                    message=f"Escalated: {reminder.message}\nEscalation Level: {escalation_level}",
                    escalate_to_manager=(escalation_level >= 2),
                    escalate_to_team_lead=(escalation_level >= 1),
                    company_id=reminder.company_id
                )
                
                # Send notifications
                success = self.notification_service.send_escalation_notification(
                    escalation_reminder, escalation_users
                )
                
                if success:
                    logger.info(f"Hierarchy escalation level {escalation_level} sent for reminder {reminder.id}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to escalate reminder {reminder.id} through hierarchy: {e}")
            return False
    
    def _handle_lead_assignment(self, data: Dict[str, Any]) -> bool:
        """Handle lead assignment notifications."""
        try:
            lead = data.get('lead')
            assigned_user = data.get('assigned_user')
            assigned_by = data.get('assigned_by')
            
            if not all([lead, assigned_user]):
                return False
            
            # Get hierarchy recipients
            recipients = self.get_hierarchy_notification_recipients(
                trigger_user=assigned_user,
                notification_type='lead_assignment',
                include_higher=True,
                include_peers=False,
                include_lower=False
            )
            
            message = f"Lead Assignment: {lead.name} assigned to {assigned_user.get_full_name() or assigned_user.username}"
            
            success_count = 0
            for recipient in recipients:
                try:
                    success = self.notification_service._send_in_app_notification_direct(
                        user=recipient,
                        title="Lead Assignment",
                        message=message,
                        notification_type='lead_assignment'
                    )
                    if success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send lead assignment notification to {recipient.username}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Failed to handle lead assignment: {e}")
            return False
    
    def _handle_overdue_followup(self, data: Dict[str, Any]) -> bool:
        """Handle overdue follow-up notifications."""
        try:
            lead = data.get('lead')
            overdue_hours = data.get('overdue_hours', 0)
            
            if not lead or not lead.assigned_user:
                return False
            
            # Determine escalation level based on how overdue
            if overdue_hours >= 24:
                escalation_level = 2  # Manager level
            elif overdue_hours >= 8:
                escalation_level = 1  # Team lead level
            else:
                escalation_level = 0  # No escalation
            
            if escalation_level > 0:
                # Find or create reminder for escalation
                reminder = InternalFollowUpReminder.objects.filter(
                    lead=lead,
                    user=lead.assigned_user,
                    reminder_type='followup'
                ).first()
                
                if reminder:
                    return self.escalate_through_hierarchy(reminder, escalation_level)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle overdue follow-up: {e}")
            return False
    
    def _handle_critical_escalation(self, data: Dict[str, Any]) -> bool:
        """Handle critical escalation notifications."""
        try:
            lead = data.get('lead')
            reason = data.get('reason', 'Critical escalation required')
            
            if not lead or not lead.assigned_user:
                return False
            
            # Escalate to highest level (owner)
            reminder = InternalFollowUpReminder.objects.filter(
                lead=lead,
                user=lead.assigned_user
            ).first()
            
            if reminder:
                return self.escalate_through_hierarchy(reminder, escalation_level=3)
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to handle critical escalation: {e}")
            return False
    
    def _handle_performance_alert(self, data: Dict[str, Any]) -> bool:
        """Handle team performance alerts."""
        try:
            manager = data.get('manager')
            performance_data = data.get('performance_data', {})
            
            if not manager:
                return False
            
            # Get higher-level recipients
            recipients = self.get_hierarchy_notification_recipients(
                trigger_user=manager,
                notification_type='performance_alert',
                include_higher=True,
                include_peers=False,
                include_lower=False
            )
            
            message = f"Performance Alert: {manager.get_full_name() or manager.username}'s team"
            
            # Add performance summary
            if performance_data:
                message += f"\nConversion Rate: {performance_data.get('conversion_rate', 0):.1f}%"
                message += f"\nOverdue Follow-ups: {performance_data.get('overdue_count', 0)}"
            
            success_count = 0
            for recipient in recipients:
                try:
                    success = self.notification_service._send_in_app_notification_direct(
                        user=recipient,
                        title="Team Performance Alert",
                        message=message,
                        notification_type='performance_alert'
                    )
                    if success:
                        success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send performance alert to {recipient.username}: {e}")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Failed to handle performance alert: {e}")
            return False
    
    def _user_wants_hierarchy_notification(self, user: User, notification_type: str) -> bool:
        """Check if user wants hierarchy notifications."""
        try:
            preference = TeamNotificationPreference.objects.get(
                user=user,
                notification_type='team_reminder'  # Use team_reminder for hierarchy notifications
            )
            return preference.team_alerts_enabled
        except TeamNotificationPreference.DoesNotExist:
            return True  # Default to enabled
    
    def _get_team_structure(self, user: User) -> Dict[str, Any]:
        """Get team structure for the user."""
        structure = {
            'above': [],
            'peers': [],
            'below': []
        }
        
        # Users above in hierarchy
        if user.team_lead:
            structure['above'].append({
                'username': user.team_lead.username,
                'role': user.team_lead.role,
                'full_name': user.team_lead.get_full_name()
            })
        
        if user.manager:
            structure['above'].append({
                'username': user.manager.username,
                'role': user.manager.role,
                'full_name': user.manager.get_full_name()
            })
        
        # Peers at same level
        if user.manager:
            peers = User.objects.filter(
                manager=user.manager,
                role=user.role
            ).exclude(id=user.id)
        elif user.team_lead:
            peers = User.objects.filter(
                team_lead=user.team_lead,
                role=user.role
            ).exclude(id=user.id)
        else:
            peers = User.objects.none()
        
        structure['peers'] = [
            {
                'username': peer.username,
                'role': peer.role,
                'full_name': peer.get_full_name()
            }
            for peer in peers
        ]
        
        # Users below in hierarchy
        if user.role == 'owner':
            below = User.objects.filter(
                company_id=user.company_id
            ).exclude(id=user.id)
        elif user.role == 'manager':
            below = User.objects.filter(
                Q(manager=user.id) | Q(team_lead__manager=user.id)
            ).exclude(id=user.id)
        elif user.role == 'team_lead':
            below = User.objects.filter(
                team_lead=user.id
            ).exclude(id=user.id)
        else:
            below = User.objects.none()
        
        structure['below'] = [
            {
                'username': below_user.username,
                'role': below_user.role,
                'full_name': below_user.get_full_name()
            }
            for below_user in below
        ]
        
        return structure
    
    def _get_hierarchy_followup_overview(self, accessible_users) -> Dict[str, Any]:
        """Get follow-up overview for accessible users."""
        now = timezone.now()
        
        overview = {
            'total_scheduled_today': Lead.objects.filter(
                assigned_user__in=accessible_users,
                followup_datetime__date=now.date(),
                followup_datetime__gte=now
            ).count(),
            'total_overdue': Lead.objects.filter(
                assigned_user__in=accessible_users,
                followup_datetime__lt=now,
                status__in=['lead', 'interested_follow_up', 'contacted']
            ).count(),
            'urgent_overdue': Lead.objects.filter(
                assigned_user__in=accessible_users,
                followup_datetime__lt=now,
                followup_priority='urgent',
                status__in=['lead', 'interested_follow_up', 'contacted']
            ).count(),
        }
        
        return overview
    
    def _get_escalation_status(self, user: User) -> Dict[str, Any]:
        """Get escalation status for user's team."""
        now = timezone.now()
        last_24h = now - timedelta(hours=24)
        
        escalations = InternalFollowUpReminder.objects.filter(
            reminder_type='escalation',
            created_at__gte=last_24h
        )
        
        # Filter by user's accessible team
        if user.role != 'owner':
            team_users = user.get_accessible_users()
            escalations = escalations.filter(user__in=team_users)
        
        return {
            'escalations_last_24h': escalations.count(),
            'pending_escalations': escalations.filter(status='pending').count(),
            'resolved_escalations': escalations.filter(status='acknowledged').count(),
        }
    
    def _get_performance_comparison(self, user: User, accessible_users) -> Dict[str, Any]:
        """Get performance comparison between user and team."""
        # Get user's performance
        user_performance = self._get_user_performance(user)
        
        # Get team average performance
        team_performance = self._get_team_performance(accessible_users)
        
        return {
            'user_performance': user_performance,
            'team_average': team_performance,
            'comparison': {
                'conversion_rate_diff': user_performance['conversion_rate'] - team_performance['conversion_rate'],
                'followup_compliance_diff': user_performance['followup_compliance'] - team_performance['followup_compliance'],
            }
        }
    
    def _get_user_performance(self, user: User) -> Dict[str, float]:
        """Get performance metrics for a user."""
        # Last 30 days
        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)
        
        leads = Lead.objects.filter(
            assigned_user=user,
            created_at__range=[start_date, end_date]
        )
        
        completed = leads.filter(
            status__in=['sale_done', 'closed']
        )
        
        followups = Lead.objects.filter(
            assigned_user=user,
            followup_datetime__range=[start_date, end_date]
        )
        
        return {
            'conversion_rate': (completed.count() / leads.count() * 100) if leads.count() > 0 else 0,
            'followup_compliance': (followups.count() / leads.count() * 100) if leads.count() > 0 else 0,
        }
    
    def _get_team_performance(self, users) -> Dict[str, float]:
        """Get average performance metrics for a team."""
        if not users.exists():
            return {'conversion_rate': 0, 'followup_compliance': 0}
        
        total_conversion = 0
        total_compliance = 0
        user_count = 0
        
        for user in users:
            performance = self._get_user_performance(user)
            total_conversion += performance['conversion_rate']
            total_compliance += performance['followup_compliance']
            user_count += 1
        
        return {
            'conversion_rate': total_conversion / user_count if user_count > 0 else 0,
            'followup_compliance': total_compliance / user_count if user_count > 0 else 0,
        }
