from datetime import datetime, time
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template import Template, Context
from typing import List, Dict, Any, Optional
import logging
import pytz

from dashboard.models import (
    InternalFollowUpReminder, InternalNotificationTemplate, 
    TeamNotificationPreference, User, Lead
)

logger = logging.getLogger(__name__)

class InternalNotificationService:
    """
    Service for sending internal notifications through multiple channels.
    Handles in-app, email, and SMS notifications for team members.
    """
    
    def __init__(self):
        self.default_from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@company.com')
        self.sms_enabled = getattr(settings, 'SMS_ENABLED', False)
    
    def send_reminder_notification(self, reminder: InternalFollowUpReminder) -> bool:
        """
        Send a reminder notification through the specified channels.
        
        Args:
            reminder: The reminder to send notification for
            
        Returns:
            bool: True if at least one channel succeeded
        """
        success = False
        channels = self._get_enabled_channels(reminder)
        
        # Check if user is in quiet hours
        if self._is_quiet_hours(reminder.user):
            logger.info(f"User {reminder.user.username} is in quiet hours, skipping notifications")
            return False
        
        for channel in channels:
            try:
                if channel == 'in_app':
                    success |= self._send_in_app_notification(reminder)
                elif channel == 'email':
                    success |= self._send_email_notification(reminder)
                elif channel == 'sms':
                    success |= self._send_sms_notification(reminder)
                
                # Track the last successful channel
                if success:
                    reminder.last_sent_channel = channel
                    
            except Exception as e:
                logger.error(f"Failed to send {channel} notification for reminder {reminder.id}: {e}")
                reminder.retry_count += 1
        
        # Update reminder status
        if success:
            reminder.status = 'sent'
            reminder.sent_at = timezone.now()
        elif reminder.retry_count >= reminder.max_retries:
            reminder.status = 'failed'
        
        reminder.save(update_fields=['status', 'sent_at', 'last_sent_channel', 'retry_count'])
        
        return success
    
    def send_escalation_notification(self, reminder: InternalFollowUpReminder, escalation_users: List[User]) -> bool:
        """
        Send escalation notification to specified users.
        
        Args:
            reminder: The reminder being escalated
            escalation_users: Users to notify
            
        Returns:
            bool: True if at least one notification succeeded
        """
        success = False
        
        for user in escalation_users:
            try:
                # Check user preferences for escalation notifications
                if not self._user_wants_escalation(user):
                    continue
                
                # Create escalation message
                escalation_message = self._generate_escalation_message(reminder, user)
                
                # Send through user's preferred channels
                channels = self._get_user_channels_for_type(user, 'escalation')
                
                for channel in channels:
                    if channel == 'in_app':
                        success |= self._send_in_app_escalation(reminder, user, escalation_message)
                    elif channel == 'email':
                        success |= self._send_email_escalation(reminder, user, escalation_message)
                    elif channel == 'sms':
                        success |= self._send_sms_escalation(reminder, user, escalation_message)
                        
            except Exception as e:
                logger.error(f"Failed to send escalation to user {user.username}: {e}")
        
        return success
    
    def send_team_summary(self, team_users: List[User], summary_type: str = 'daily') -> bool:
        """
        Send team follow-up summary to team members.
        
        Args:
            team_users: List of team members
            summary_type: 'daily' or 'weekly'
            
        Returns:
            bool: True if successful
        """
        success = False
        
        for user in team_users:
            try:
                # Check if user wants summaries
                if not self._user_wants_summary(user, summary_type):
                    continue
                
                # Generate summary data
                summary_data = self._generate_team_summary(user, summary_type)
                
                # Send through preferred channels
                channels = self._get_user_channels_for_type(user, f'{summary_type}_summary')
                
                for channel in channels:
                    if channel == 'email':
                        success |= self._send_email_summary(user, summary_data, summary_type)
                    elif channel == 'in_app':
                        success |= self._send_in_app_summary(user, summary_data, summary_type)
                        
            except Exception as e:
                logger.error(f"Failed to send {summary_type} summary to user {user.username}: {e}")
        
        return success
    
    def _get_enabled_channels(self, reminder: InternalFollowUpReminder) -> List[str]:
        """
        Get enabled notification channels for a reminder.
        
        Args:
            reminder: The reminder
            
        Returns:
            List[str]: Enabled channels
        """
        channels_map = {
            'in_app': ['in_app'],
            'email': ['email'],
            'sms': ['sms'],
            'email_sms': ['email', 'sms'],
            'all': ['in_app', 'email', 'sms']
        }
        
        return channels_map.get(reminder.notification_channels, ['in_app'])
    
    def _get_user_channels_for_type(self, user: User, notification_type: str) -> List[str]:
        """
        Get user's preferred channels for a specific notification type.
        
        Args:
            user: The user
            notification_type: Type of notification
            
        Returns:
            List[str]: User's preferred channels
        """
        try:
            preference = TeamNotificationPreference.objects.get(
                user=user,
                notification_type=notification_type
            )
            
            channels = []
            if preference.in_app_enabled:
                channels.append('in_app')
            if preference.email_enabled:
                channels.append('email')
            if preference.sms_enabled:
                channels.append('sms')
            
            return channels or ['in_app']  # Default to in-app if none enabled
            
        except TeamNotificationPreference.DoesNotExist:
            return ['in_app']  # Default
    
    def _is_quiet_hours(self, user: User) -> bool:
        """
        Check if user is currently in quiet hours.
        
        Args:
            user: The user to check
            
        Returns:
            bool: True if in quiet hours
        """
        try:
            preference = TeamNotificationPreference.objects.get(
                user=user,
                notification_type='followup_reminder'
            )
            
            if not preference.quiet_hours_start or not preference.quiet_hours_end:
                return False
            
            # Get user's current time
            user_timezone = pytz.timezone(preference.timezone)
            current_time = timezone.now().astimezone(user_timezone).time()
            
            start_time = preference.quiet_hours_start
            end_time = preference.quiet_hours_end
            
            # Check if current time is within quiet hours
            if start_time <= end_time:
                return start_time <= current_time <= end_time
            else:  # Overnight quiet hours
                return current_time >= start_time or current_time <= end_time
                
        except TeamNotificationPreference.DoesNotExist:
            return False
    
    def _send_in_app_notification(self, reminder: InternalFollowUpReminder) -> bool:
        """
        Send in-app notification.
        
        Args:
            reminder: The reminder
            
        Returns:
            bool: True if successful
        """
        try:
            # Create notification record (you might have a separate Notification model)
            # For now, we'll just log it
            logger.info(f"In-app notification sent to {reminder.user.username} for reminder {reminder.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send in-app notification: {e}")
            return False
    
    def _send_email_notification(self, reminder: InternalFollowUpReminder) -> bool:
        """
        Send email notification.
        
        Args:
            reminder: The reminder
            
        Returns:
            bool: True if successful
        """
        try:
            # Get email template
            template = self._get_template('followup_reminder', 'email')
            
            if template:
                # Render template with context
                context = self._get_template_context(reminder)
                subject = self._render_template(template.subject_template, context)
                body = self._render_template(template.body_template, context)
            else:
                # Default email format
                subject = f"Internal: Follow-up Reminder - {reminder.lead.name}"
                body = reminder.message
            
            # Send email
            send_mail(
                subject=subject,
                message=body,
                from_email=self.default_from_email,
                recipient_list=[reminder.user.email],
                fail_silently=False
            )
            
            logger.info(f"Email notification sent to {reminder.user.email} for reminder {reminder.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            return False
    
    def _send_sms_notification(self, reminder: InternalFollowUpReminder) -> bool:
        """
        Send SMS notification.
        
        Args:
            reminder: The reminder
            
        Returns:
            bool: True if successful
        """
        if not self.sms_enabled:
            return False
        
        try:
            # Get SMS template
            template = self._get_template('followup_reminder', 'sms')
            
            if template:
                context = self._get_template_context(reminder)
                message = self._render_template(template.body_template, context)
            else:
                # Default SMS format
                message = f"CRM Alert: Follow-up with {reminder.lead.name} due at {reminder.followup_datetime.strftime('%I:%M %p')}. Priority: {reminder.priority.title()}"
            
            # Send SMS (implement your SMS service integration)
            # For now, we'll just log it
            logger.info(f"SMS notification would be sent to {reminder.user.mobile} for reminder {reminder.id}: {message}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS notification: {e}")
            return False
    
    def _send_in_app_escalation(self, reminder: InternalFollowUpReminder, user: User, message: str) -> bool:
        """Send in-app escalation notification."""
        logger.info(f"In-app escalation sent to {user.username} for reminder {reminder.id}")
        return True
    
    def _send_email_escalation(self, reminder: InternalFollowUpReminder, user: User, message: str) -> bool:
        """Send email escalation notification."""
        try:
            subject = f"⚠️ Escalation: {reminder.lead.name} follow-up overdue"
            
            send_mail(
                subject=subject,
                message=message,
                from_email=self.default_from_email,
                recipient_list=[user.email],
                fail_silently=False
            )
            
            logger.info(f"Email escalation sent to {user.email} for reminder {reminder.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email escalation: {e}")
            return False
    
    def _send_sms_escalation(self, reminder: InternalFollowUpReminder, user: User, message: str) -> bool:
        """Send SMS escalation notification."""
        if not self.sms_enabled:
            return False
        
        logger.info(f"SMS escalation would be sent to {user.mobile} for reminder {reminder.id}")
        return True
    
    def _send_email_summary(self, user: User, summary_data: Dict[str, Any], summary_type: str) -> bool:
        """Send email summary to user."""
        try:
            subject = f"Team {summary_type.title()} Follow-up Summary"
            
            # Format summary data into email body
            body = self._format_summary_email(summary_data, summary_type)
            
            send_mail(
                subject=subject,
                message=body,
                from_email=self.default_from_email,
                recipient_list=[user.email],
                fail_silently=False
            )
            
            logger.info(f"Email {summary_type} summary sent to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email summary: {e}")
            return False
    
    def _send_in_app_summary(self, user: User, summary_data: Dict[str, Any], summary_type: str) -> bool:
        """Send in-app summary to user."""
        logger.info(f"In-app {summary_type} summary sent to {user.username}")
        return True
    
    def _get_template(self, template_type: str, channel: str) -> Optional[InternalNotificationTemplate]:
        """
        Get notification template for type and channel.
        
        Args:
            template_type: Type of template
            channel: Channel type
            
        Returns:
            InternalNotificationTemplate or None
        """
        try:
            return InternalNotificationTemplate.objects.get(
                template_type=template_type,
                channel=channel,
                is_active=True
            )
        except InternalNotificationTemplate.DoesNotExist:
            return None
    
    def _get_template_context(self, reminder: InternalFollowUpReminder) -> Dict[str, Any]:
        """
        Get template context for rendering.
        
        Args:
            reminder: The reminder
            
        Returns:
            Dict: Template context
        """
        return {
            'lead': reminder.lead,
            'user': reminder.user,
            'reminder': reminder,
            'followup_time': reminder.followup_datetime.strftime('%Y-%m-%d %I:%M %p'),
            'priority': reminder.priority.title(),
            'team_notes': reminder.team_notes,
        }
    
    def _render_template(self, template_string: str, context: Dict[str, Any]) -> str:
        """
        Render template string with context.
        
        Args:
            template_string: Template string
            context: Template context
            
        Returns:
            str: Rendered template
        """
        try:
            template = Template(template_string)
            return template.render(Context(context))
        except Exception as e:
            logger.error(f"Failed to render template: {e}")
            return template_string
    
    def _generate_escalation_message(self, reminder: InternalFollowUpReminder, user: User) -> str:
        """
        Generate escalation message.
        
        Args:
            reminder: The reminder being escalated
            user: User receiving escalation
            
        Returns:
            str: Escalation message
        """
        overdue_time = timezone.now() - reminder.followup_datetime
        overdue_hours = int(overdue_time.total_seconds() / 3600)
        
        message = f"⚠️ Escalation: {reminder.lead.name} follow-up overdue by {overdue_hours} hours\n"
        message += f"Assigned to: {reminder.user.get_full_name() or reminder.user.username}\n"
        message += f"Follow-up was due: {reminder.followup_datetime.strftime('%Y-%m-%d %I:%M %p')}\n"
        message += f"Priority: {reminder.priority.title()}\n"
        
        if reminder.team_notes:
            message += f"Team Notes: {reminder.team_notes}\n"
        
        message += f"Lead Mobile: {reminder.lead.mobile}\n"
        
        return message
    
    def _generate_team_summary(self, user: User, summary_type: str) -> Dict[str, Any]:
        """
        Generate team summary data.
        
        Args:
            user: The user
            summary_type: 'daily' or 'weekly'
            
        Returns:
            Dict: Summary data
        """
        # Get team members based on hierarchy
        team_members = user.get_accessible_users()
        
        # Calculate date range
        now = timezone.now()
        if summary_type == 'daily':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # weekly
            start_date = now - timedelta(days=7)
        
        # Get follow-up statistics
        total_followups = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__gte=start_date,
            followup_datetime__lte=now
        ).count()
        
        overdue_followups = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__lt=now,
            status__in=['lead', 'interested_follow_up', 'contacted']
        ).count()
        
        completed_followups = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__gte=start_date,
            followup_datetime__lte=now,
            status__in=['sale_done', 'not_interested', 'closed']
        ).count()
        
        return {
            'user': user,
            'summary_type': summary_type,
            'date_range': f"{start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
            'team_members': team_members.count(),
            'total_followups': total_followups,
            'overdue_followups': overdue_followups,
            'completed_followups': completed_followups,
            'completion_rate': (completed_followups / total_followups * 100) if total_followups > 0 else 0,
        }
    
    def _format_summary_email(self, summary_data: Dict[str, Any], summary_type: str) -> str:
        """
        Format summary data into email body.
        
        Args:
            summary_data: Summary statistics
            summary_type: Type of summary
            
        Returns:
            str: Formatted email body
        """
        body = f"Team {summary_type.title()} Follow-up Summary\n"
        body += f"Period: {summary_data['date_range']}\n"
        body += f"Team Members: {summary_data['team_members']}\n\n"
        
        body += f"📊 Statistics:\n"
        body += f"Total Follow-ups: {summary_data['total_followups']}\n"
        body += f"Completed: {summary_data['completed_followups']}\n"
        body += f"Overdue: {summary_data['overdue_followups']}\n"
        body += f"Completion Rate: {summary_data['completion_rate']:.1f}%\n"
        
        return body
    
    def _user_wants_escalation(self, user: User) -> bool:
        """Check if user wants escalation notifications."""
        try:
            preference = TeamNotificationPreference.objects.get(
                user=user,
                notification_type='escalation'
            )
            return preference.escalation_alerts_enabled
        except TeamNotificationPreference.DoesNotExist:
            return True  # Default to enabled
    
    def _user_wants_summary(self, user: User, summary_type: str) -> bool:
        """Check if user wants summary notifications."""
        try:
            preference = TeamNotificationPreference.objects.get(
                user=user,
                notification_type=f'{summary_type}_summary'
            )
            return getattr(preference, f'{summary_type}_summary_enabled', False)
        except TeamNotificationPreference.DoesNotExist:
            return False  # Default to disabled
