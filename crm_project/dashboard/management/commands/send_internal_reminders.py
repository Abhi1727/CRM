from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from dashboard.models import InternalFollowUpReminder
from services.internal_notification_service import InternalNotificationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process and send scheduled internal reminders'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of reminders to process in each batch',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting internal reminder processing (dry_run={dry_run}, batch_size={batch_size})"
            )
        )
        
        notification_service = InternalNotificationService()
        
        # Get pending reminders that are due
        now = timezone.now()
        pending_reminders = InternalFollowUpReminder.objects.filter(
            status='pending',
            scheduled_datetime__lte=now
        ).select_related('lead', 'user', 'created_by')[:batch_size]
        
        total_reminders = pending_reminders.count()
        sent_count = 0
        failed_count = 0
        
        self.stdout.write(f"Found {total_reminders} pending reminders to process")
        
        for reminder in pending_reminders:
            try:
                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would send reminder {reminder.id} to {reminder.user.username} "
                        f"for lead {reminder.lead.name}"
                    )
                    sent_count += 1
                else:
                    success = notification_service.send_reminder_notification(reminder)
                    if success:
                        sent_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Sent reminder {reminder.id} to {reminder.user.username}"
                            )
                        )
                    else:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"✗ Failed to send reminder {reminder.id} to {reminder.user.username}"
                            )
                        )
                        
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing reminder {reminder.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error processing reminder {reminder.id}: {e}")
                )
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSummary: {sent_count} sent, {failed_count} failed out of {total_reminders} total"
            )
        )
        
        # Check for reminders that need retry
        retry_reminders = InternalFollowUpReminder.objects.filter(
            status='failed',
            retry_count__lt=3,
            updated_at__lt=now - timedelta(minutes=30)  # Wait 30 minutes before retry
        ).count()
        
        if retry_reminders > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Found {retry_reminders} failed reminders eligible for retry"
                )
            )
