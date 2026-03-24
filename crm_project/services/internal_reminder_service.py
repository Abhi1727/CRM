from datetime import datetime, timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from typing import List, Optional, Dict, Any
import logging

from dashboard.models import (
    Lead, InternalFollowUpReminder, InternalNotificationTemplate, 
    TeamNotificationPreference, User
)

logger = logging.getLogger(__name__)

class InternalReminderService:
    """
    Service for managing internal follow-up reminders for team members.
    Handles automatic creation, scheduling, and management of internal reminders.
    """
    
    def __init__(self):
        self.default_reminder_minutes = {
            'low': 60,
            'medium': 30,
            'high': 15,
            'urgent': 5
        }
    
    def create_reminder_for_lead(
        self, 
        lead: Lead, 
        user: User, 
        reminder_type: str = 'followup',
        priority: str = 'medium',
        reminder_before_minutes: Optional[int] = None,
        notification_channels: str = 'in_app',
        team_notes: str = '',
        escalate_to_manager: bool = False,
        escalate_to_team_lead: bool = False,
        escalation_minutes: int = 60,
        created_by: Optional[User] = None
    ) -> InternalFollowUpReminder:
        """
        Create an internal reminder for a lead's follow-up.
        
        Args:
            lead: The lead object
            user: The team member to notify
            reminder_type: Type of reminder
            priority: Priority level
            reminder_before_minutes: Minutes before follow-up to remind
            notification_channels: Notification channels to use
            team_notes: Additional team context
            escalate_to_manager: Whether to escalate to manager
            escalate_to_team_lead: Whether to escalate to team lead
            escalation_minutes: Minutes after reminder to escalate
            created_by: User who created the reminder
            
        Returns:
            InternalFollowUpReminder: The created reminder
        """
        if not lead.followup_datetime:
            raise ValueError("Lead must have a followup_datetime to create reminder")
        
        # Calculate reminder timing
        if reminder_before_minutes is None:
            reminder_before_minutes = self.default_reminder_minutes.get(priority, 30)
        
        scheduled_datetime = lead.followup_datetime - timedelta(minutes=reminder_before_minutes)
        
        # Don't create reminders for past times
        if scheduled_datetime < timezone.now():
            logger.warning(f"Skipping reminder creation for lead {lead.id} - scheduled time is in the past")
            return None
        
        # Generate title and message
        title = f"Follow-up Reminder: {lead.name}"
        message = self._generate_reminder_message(lead, user, priority, team_notes)
        
        # Create reminder
        reminder = InternalFollowUpReminder.objects.create(
            lead=lead,
            user=user,
            reminder_type=reminder_type,
            priority=priority,
            scheduled_datetime=scheduled_datetime,
            followup_datetime=lead.followup_datetime,
            reminder_before_minutes=reminder_before_minutes,
            notification_channels=notification_channels,
            title=title,
            message=message,
            team_notes=team_notes,
            escalate_to_manager=escalate_to_manager,
            escalate_to_team_lead=escalate_to_team_lead,
            escalation_minutes=escalation_minutes,
            created_by=created_by or user,
            company_id=lead.company_id
        )
        
        # Update lead's internal reminder tracking
        lead.internal_reminder_sent = True
        lead.last_internal_reminder = timezone.now()
        lead.internal_reminder_count += 1
        lead.save(update_fields=['internal_reminder_sent', 'last_internal_reminder', 'internal_reminder_count'])
        
        logger.info(f"Created internal reminder {reminder.id} for lead {lead.id} and user {user.username}")
        return reminder
    
    def create_bulk_reminders(
        self, 
        leads: List[Lead], 
        users: List[User],
        **kwargs
    ) -> List[InternalFollowUpReminder]:
        """
        Create reminders for multiple leads and users.
        
        Args:
            leads: List of leads
            users: List of users to notify for each lead
            **kwargs: Additional arguments for create_reminder_for_lead
            
        Returns:
            List[InternalFollowUpReminder]: Created reminders
        """
        reminders = []
        
        with transaction.atomic():
            for lead in leads:
                for user in users:
                    try:
                        reminder = self.create_reminder_for_lead(lead, user, **kwargs)
                        if reminder:
                            reminders.append(reminder)
                    except Exception as e:
                        logger.error(f"Failed to create reminder for lead {lead.id}, user {user.username}: {e}")
                        continue
        
        return reminders
    
    def update_reminder_for_lead(self, lead: Lead, user: User) -> Optional[InternalFollowUpReminder]:
        """
        Update or create reminder when lead's follow-up is changed.
        
        Args:
            lead: The lead with updated follow-up
            user: The team member assigned to the lead
            
        Returns:
            InternalFollowUpReminder: Updated or created reminder
        """
        # Cancel existing pending reminders for this lead and user
        self.cancel_pending_reminders(lead, user)
        
        # Create new reminder if follow-up is set
        if lead.followup_datetime and lead.followup_datetime > timezone.now():
            return self.create_reminder_for_lead(
                lead=lead,
                user=user,
                priority=lead.followup_priority,
                created_by=user
            )
        
        return None
    
    def cancel_pending_reminders(self, lead: Lead, user: User) -> int:
        """
        Cancel all pending reminders for a specific lead and user.
        
        Args:
            lead: The lead
            user: The user
            
        Returns:
            int: Number of reminders cancelled
        """
        count = InternalFollowUpReminder.objects.filter(
            lead=lead,
            user=user,
            status='pending'
        ).update(status='cancelled')
        
        logger.info(f"Cancelled {count} pending reminders for lead {lead.id}, user {user.username}")
        return count
    
    def get_pending_reminders_for_user(self, user: User) -> List[InternalFollowUpReminder]:
        """
        Get all pending reminders for a user.
        
        Args:
            user: The user
            
        Returns:
            List[InternalFollowUpReminder]: Pending reminders
        """
        return InternalFollowUpReminder.objects.filter(
            user=user,
            status='pending',
            scheduled_datetime__lte=timezone.now()
        ).order_by('scheduled_datetime')
    
    def get_overdue_reminders(self, minutes_overdue: int = 0) -> List[InternalFollowUpReminder]:
        """
        Get reminders that are overdue (past their follow-up time).
        
        Args:
            minutes_overdue: How many minutes past follow-up time to consider overdue
            
        Returns:
            List[InternalFollowUpReminder]: Overdue reminders
        """
        cutoff_time = timezone.now() - timedelta(minutes=minutes_overdue)
        
        return InternalFollowUpReminder.objects.filter(
            status='pending',
            followup_datetime__lt=cutoff_time
        ).order_by('followup_datetime')
    
    def get_reminders_needing_escalation(self) -> List[InternalFollowUpReminder]:
        """
        Get reminders that need escalation based on their escalation settings.
        
        Returns:
            List[InternalFollowUpReminder]: Reminders needing escalation
        """
        now = timezone.now()
        escalation_cutoff = now - timedelta(minutes=60)  # Default 1 hour
        
        return InternalFollowUpReminder.objects.filter(
            status='sent',
            sent_at__lt=escalation_cutoff,
            escalate_to_manager=True
        ).order_by('sent_at')
    
    def acknowledge_reminder(self, reminder_id: int, user: User) -> bool:
        """
        Mark a reminder as acknowledged by the user.
        
        Args:
            reminder_id: The reminder ID
            user: The user acknowledging
            
        Returns:
            bool: True if successful
        """
        try:
            reminder = InternalFollowUpReminder.objects.get(
                id=reminder_id,
                user=user,
                status='sent'
            )
            
            reminder.status = 'acknowledged'
            reminder.acknowledged_at = timezone.now()
            reminder.save(update_fields=['status', 'acknowledged_at'])
            
            logger.info(f"Reminder {reminder_id} acknowledged by {user.username}")
            return True
            
        except InternalFollowUpReminder.DoesNotExist:
            logger.error(f"Reminder {reminder_id} not found for user {user.username}")
            return False
    
    def snooze_reminder(
        self, 
        reminder_id: int, 
        user: User, 
        minutes: int = 30
    ) -> bool:
        """
        Snooze a reminder for specified minutes.
        
        Args:
            reminder_id: The reminder ID
            user: The user snoozing
            minutes: Minutes to snooze for
            
        Returns:
            bool: True if successful
        """
        try:
            reminder = InternalFollowUpReminder.objects.get(
                id=reminder_id,
                user=user,
                status='sent'
            )
            
            new_scheduled_time = timezone.now() + timedelta(minutes=minutes)
            reminder.scheduled_datetime = new_scheduled_time
            reminder.status = 'pending'
            reminder.save(update_fields=['scheduled_datetime', 'status'])
            
            logger.info(f"Reminder {reminder_id} snoozed by {user.username} for {minutes} minutes")
            return True
            
        except InternalFollowUpReminder.DoesNotExist:
            logger.error(f"Reminder {reminder_id} not found for user {user.username}")
            return False
    
    def get_user_reminder_preferences(self, user: User) -> Dict[str, Any]:
        """
        Get a user's notification preferences for reminders.
        
        Args:
            user: The user
            
        Returns:
            Dict: User preferences
        """
        preferences = {}
        
        for pref_type in TeamNotificationPreference.INTERNAL_NOTIFICATION_TYPES:
            try:
                pref = TeamNotificationPreference.objects.get(
                    user=user,
                    notification_type=pref_type[0]
                )
                preferences[pref_type[0]] = {
                    'in_app_enabled': pref.in_app_enabled,
                    'email_enabled': pref.email_enabled,
                    'sms_enabled': pref.sms_enabled,
                    'quiet_hours_start': pref.quiet_hours_start,
                    'quiet_hours_end': pref.quiet_hours_end,
                    'timezone': pref.timezone,
                }
            except TeamNotificationPreference.DoesNotExist:
                # Create default preferences
                preferences[pref_type[0]] = {
                    'in_app_enabled': True,
                    'email_enabled': True,
                    'sms_enabled': False,
                    'quiet_hours_start': None,
                    'quiet_hours_end': None,
                    'timezone': 'UTC',
                }
        
        return preferences
    
    def _generate_reminder_message(
        self, 
        lead: Lead, 
        user: User, 
        priority: str, 
        team_notes: str
    ) -> str:
        """
        Generate internal reminder message.
        
        Args:
            lead: The lead
            user: The user to notify
            priority: Priority level
            team_notes: Additional team context
            
        Returns:
            str: Formatted message
        """
        followup_time = lead.followup_datetime.strftime('%Y-%m-%d %I:%M %p')
        
        message = f"📋 Follow-up Reminder\n"
        message += f"Lead: {lead.name} (Mobile: {lead.mobile})\n"
        message += f"Follow-up: {followup_time}\n"
        message += f"Priority: {priority.title()}\n"
        
        if lead.followup_remarks:
            message += f"Notes: {lead.followup_remarks}\n"
        
        if team_notes:
            message += f"Team Notes: {team_notes}\n"
        
        return message
    
    def auto_create_reminders_for_new_lead(self, lead: Lead) -> None:
        """
        Automatically create reminders when a new lead is assigned or follow-up is set.
        
        Args:
            lead: The newly created/updated lead
        """
        if not lead.assigned_user or not lead.followup_datetime:
            return
        
        # Check if user wants automatic reminders
        user_prefs = self.get_user_reminder_preferences(lead.assigned_user)
        followup_prefs = user_prefs.get('followup_reminder', {})
        
        if followup_prefs.get('in_app_enabled', True):
            self.create_reminder_for_lead(
                lead=lead,
                user=lead.assigned_user,
                priority=lead.followup_priority,
                notification_channels='in_app'
            )
    
    def cleanup_old_reminders(self, days_old: int = 30) -> int:
        """
        Clean up old completed/failed reminders.
        
        Args:
            days_old: How many days to keep old reminders
            
        Returns:
            int: Number of reminders cleaned up
        """
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        count = InternalFollowUpReminder.objects.filter(
            status__in=['acknowledged', 'failed', 'cancelled'],
            updated_at__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {count} old reminders older than {days_old} days")
        return count
