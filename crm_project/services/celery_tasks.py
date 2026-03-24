from celery import shared_task
from django.utils import timezone
from datetime import timedelta
import logging

from dashboard.models import InternalFollowUpReminder, Lead, User
from .internal_notification_service import InternalNotificationService
from .internal_reminder_service import InternalReminderService
from .team_followup_monitoring_service import TeamFollowUpMonitoringService
from .hierarchy_notification_service import HierarchyNotificationService

logger = logging.getLogger(__name__)

@shared_task
def send_internal_reminder_notifications():
    """
    Process and send scheduled internal reminders.
    This task should be run every minute to check for due reminders.
    """
    try:
        notification_service = InternalNotificationService()
        
        # Get pending reminders that are due
        now = timezone.now()
        pending_reminders = InternalFollowUpReminder.objects.filter(
            status='pending',
            scheduled_datetime__lte=now
        ).select_related('lead', 'user', 'created_by')[:100]  # Process in batches
        
        sent_count = 0
        failed_count = 0
        
        for reminder in pending_reminders:
            try:
                success = notification_service.send_reminder_notification(reminder)
                if success:
                    sent_count += 1
                    logger.info(f"Sent reminder {reminder.id} to {reminder.user.username}")
                else:
                    failed_count += 1
                    logger.warning(f"Failed to send reminder {reminder.id} to {reminder.user.username}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing reminder {reminder.id}: {e}")
        
        logger.info(f"Processed {pending_reminders.count()} reminders: {sent_count} sent, {failed_count} failed")
        
        return {
            'processed': pending_reminders.count(),
            'sent': sent_count,
            'failed': failed_count,
        }
        
    except Exception as e:
        logger.error(f"Error in send_internal_reminder_notifications task: {e}")
        return {'error': str(e)}

@shared_task
def check_team_overdue_followups():
    """
    Identify team overdue follow-ups and trigger escalations.
    This task should be run every hour.
    """
    try:
        monitoring_service = TeamFollowUpMonitoringService()
        hierarchy_service = HierarchyNotificationService()
        
        # Get all managers
        managers = User.objects.filter(role='manager', account_status='active')
        
        total_escalations = 0
        total_notified = 0
        
        for manager in managers:
            try:
                # Monitor overdue follow-ups for this manager's team
                results = monitoring_service.monitor_team_overdue_followups(manager)
                
                if results['critical_overdue']:
                    # Process escalations for critical items
                    for lead_data in results['critical_overdue']:
                        try:
                            lead = Lead.objects.get(id=lead_data['id'])
                            
                            # Create escalation event
                            escalation_data = {
                                'lead': lead,
                                'overdue_hours': (timezone.now() - lead.followup_datetime).total_seconds() / 3600
                            }
                            
                            success = hierarchy_service.send_hierarchy_notifications(
                                event_type='followup_overdue',
                                data=escalation_data
                            )
                            
                            if success:
                                total_escalations += 1
                                # Count escalation users
                                escalation_users = []
                                if lead.assigned_user.team_lead:
                                    escalation_users.append(lead.assigned_user.team_lead)
                                if lead.assigned_user.manager:
                                    escalation_users.append(lead.assigned_user.manager)
                                total_notified += len(set(escalation_users))
                                
                        except Exception as e:
                            logger.error(f"Error processing escalation for lead {lead_data['id']}: {e}")
                
                logger.info(f"Processed overdue follow-ups for manager {manager.username}: "
                           f"{results['total_overdue']} overdue, {results['escalations_sent']} escalations")
                
            except Exception as e:
                logger.error(f"Error processing overdue follow-ups for manager {manager.username}: {e}")
        
        logger.info(f"Overdue follow-up check completed: {total_escalations} escalations sent, "
                   f"{total_notified} team members notified")
        
        return {
            'escalations_sent': total_escalations,
            'team_members_notified': total_notified,
        }
        
    except Exception as e:
        logger.error(f"Error in check_team_overdue_followups task: {e}")
        return {'error': str(e)}

@shared_task
def send_daily_team_summary():
    """
    Send daily team follow-up summaries to managers and owners.
    This task should be run once daily (e.g., at 9 AM).
    """
    try:
        notification_service = InternalNotificationService()
        
        # Skip weekends
        current_weekday = timezone.now().weekday()
        if current_weekday >= 5:  # Saturday (5) or Sunday (6)
            logger.info("Skipping daily team summary for weekend")
            return {'skipped': 'weekend'}
        
        # Get managers and owners
        managers = User.objects.filter(role='manager', account_status='active')
        owners = User.objects.filter(role='owner', account_status='active')
        
        sent_count = 0
        failed_count = 0
        
        # Send to managers
        for manager in managers:
            try:
                team_members = manager.get_accessible_users()
                
                if team_members.exists():
                    success = notification_service.send_team_summary(
                        team_users=team_members,
                        summary_type='daily'
                    )
                    
                    if success:
                        sent_count += 1
                        logger.info(f"Daily summary sent to manager {manager.username}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to send daily summary to manager {manager.username}")
                        
            except Exception as e:
                failed_count += 1
                logger.error(f"Error sending daily summary to manager {manager.username}: {e}")
        
        # Send to owners
        for owner in owners:
            try:
                team_members = User.objects.filter(
                    company_id=owner.company_id,
                    account_status='active'
                ).exclude(id=owner.id)
                
                if team_members.exists():
                    success = notification_service.send_team_summary(
                        team_users=team_members,
                        summary_type='daily'
                    )
                    
                    if success:
                        sent_count += 1
                        logger.info(f"Daily summary sent to owner {owner.username}")
                    else:
                        failed_count += 1
                        logger.warning(f"Failed to send daily summary to owner {owner.username}")
                        
            except Exception as e:
                failed_count += 1
                logger.error(f"Error sending daily summary to owner {owner.username}: {e}")
        
        logger.info(f"Daily team summary completed: {sent_count} sent, {failed_count} failed")
        
        return {
            'sent': sent_count,
            'failed': failed_count,
        }
        
    except Exception as e:
        logger.error(f"Error in send_daily_team_summary task: {e}")
        return {'error': str(e)}

@shared_task
def escalate_team_overdue_followups():
    """
    Escalate overdue follow-ups to hierarchy based on escalation rules.
    This task should be run every 30 minutes.
    """
    try:
        hierarchy_service = HierarchyNotificationService()
        
        # Get reminders that need escalation
        now = timezone.now()
        escalation_cutoff = now - timedelta(minutes=60)  # Default 1 hour
        
        reminders_needing_escalation = InternalFollowUpReminder.objects.filter(
            status='sent',
            sent_at__lt=escalation_cutoff,
            escalate_to_manager=True
        ).select_related('lead', 'user')
        
        escalated_count = 0
        
        for reminder in reminders_needing_escalation:
            try:
                # Determine escalation level based on how long ago it was sent
                hours_since_sent = (now - reminder.sent_at).total_seconds() / 3600
                
                if hours_since_sent >= 24:
                    escalation_level = 3  # Owner level
                elif hours_since_sent >= 8:
                    escalation_level = 2  # Manager level
                else:
                    escalation_level = 1  # Team lead level
                
                success = hierarchy_service.escalate_through_hierarchy(reminder, escalation_level)
                
                if success:
                    escalated_count += 1
                    logger.info(f"Escalated reminder {reminder.id} to level {escalation_level}")
                else:
                    logger.warning(f"Failed to escalate reminder {reminder.id}")
                    
            except Exception as e:
                logger.error(f"Error escalating reminder {reminder.id}: {e}")
        
        logger.info(f"Escalation task completed: {escalated_count} reminders escalated")
        
        return {
            'escalated': escalated_count,
        }
        
    except Exception as e:
        logger.error(f"Error in escalate_team_overdue_followups task: {e}")
        return {'error': str(e)}

@shared_task
def process_team_performance_alerts():
    """
    Process team performance alerts and notify managers.
    This task should be run once daily (e.g., at 6 PM).
    """
    try:
        monitoring_service = TeamFollowUpMonitoringService()
        hierarchy_service = HierarchyNotificationService()
        
        # Get all managers
        managers = User.objects.filter(role='manager', account_status='active')
        
        alerts_sent = 0
        
        for manager in managers:
            try:
                # Generate performance report
                report = monitoring_service.generate_team_performance_report(manager, days=7)
                
                # Check if performance alert is needed
                should_alert = False
                
                # Alert if conversion rate is below 15%
                if report['overall_metrics']['conversion_rate'] < 15:
                    should_alert = True
                
                # Alert if compliance rate is below 70%
                if report['compliance_metrics']['compliance_rate'] < 70:
                    should_alert = True
                
                # Alert if there are many overdue follow-ups
                overdue_count = sum(
                    user_data['overdue_count'] 
                    for user_data in report['individual_performance']
                )
                if overdue_count > report['team_size'] * 2:  # More than 2 overdue per team member
                    should_alert = True
                
                if should_alert:
                    # Send performance alert
                    alert_data = {
                        'manager': manager,
                        'performance_data': report['overall_metrics'],
                    }
                    
                    success = hierarchy_service.send_hierarchy_notifications(
                        event_type='team_performance_alert',
                        data=alert_data
                    )
                    
                    if success:
                        alerts_sent += 1
                        logger.info(f"Performance alert sent for manager {manager.username}")
                    else:
                        logger.warning(f"Failed to send performance alert for manager {manager.username}")
                
            except Exception as e:
                logger.error(f"Error processing performance alert for manager {manager.username}: {e}")
        
        logger.info(f"Team performance alerts completed: {alerts_sent} alerts sent")
        
        return {
            'alerts_sent': alerts_sent,
        }
        
    except Exception as e:
        logger.error(f"Error in process_team_performance_alerts task: {e}")
        return {'error': str(e)}

@shared_task
def cleanup_old_internal_reminders():
    """
    Clean up old completed/failed internal reminders.
    This task should be run once daily (e.g., at 2 AM).
    """
    try:
        reminder_service = InternalReminderService()
        
        # Clean up reminders older than 30 days
        deleted_count = reminder_service.cleanup_old_internal_reminders(days_old=30)
        
        logger.info(f"Cleanup task completed: {deleted_count} old reminders deleted")
        
        return {
            'deleted': deleted_count,
        }
        
    except Exception as e:
        logger.error(f"Error in cleanup_old_internal_reminders task: {e}")
        return {'error': str(e)}

@shared_task
def auto_create_reminders_for_new_leads():
    """
    Automatically create reminders for newly assigned leads.
    This task should be run every 5 minutes.
    """
    try:
        reminder_service = InternalReminderService()
        
        # Get leads that were recently assigned but don't have reminders yet
        recent_cutoff = timezone.now() - timedelta(minutes=10)
        
        leads_needing_reminders = Lead.objects.filter(
            assigned_user__isnull=False,
            followup_datetime__isnull=False,
            followup_datetime__gt=timezone.now(),
            internal_reminder_sent=False,
            modified_at__gte=recent_cutoff
        ).select_related('assigned_user')
        
        created_count = 0
        
        for lead in leads_needing_reminders:
            try:
                reminder_service.auto_create_reminders_for_new_lead(lead)
                created_count += 1
                logger.info(f"Auto-created reminder for lead {lead.id} assigned to {lead.assigned_user.username}")
                
            except Exception as e:
                logger.error(f"Error auto-creating reminder for lead {lead.id}: {e}")
        
        logger.info(f"Auto-reminder task completed: {created_count} reminders created")
        
        return {
            'created': created_count,
        }
        
    except Exception as e:
        logger.error(f"Error in auto_create_reminders_for_new_leads task: {e}")
        return {'error': str(e)}
