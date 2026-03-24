from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from dashboard.models import InternalFollowUpReminder

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up old completed/failed internal reminders'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days-old',
            type=int,
            default=30,
            help='Days to keep old reminders (default: 30)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--status',
            choices=['acknowledged', 'failed', 'cancelled', 'all'],
            default='all',
            help='Filter by status (default: all)',
        )
    
    def handle(self, *args, **options):
        days_old = options['days_old']
        dry_run = options['dry_run']
        status_filter = options['status']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting cleanup of internal reminders (days_old={days_old}, dry_run={dry_run}, status={status_filter})"
            )
        )
        
        # Calculate cutoff date
        cutoff_date = timezone.now() - timedelta(days=days_old)
        
        # Build query
        queryset = InternalFollowUpReminder.objects.filter(
            updated_at__lt=cutoff_date
        )
        
        if status_filter != 'all':
            queryset = queryset.filter(status=status_filter)
        
        # Get count before deletion
        total_to_delete = queryset.count()
        
        if total_to_delete == 0:
            self.stdout.write(self.style.SUCCESS("No old reminders to clean up"))
            return
        
        # Show breakdown by status
        status_breakdown = queryset.values('status').annotate(count=1)
        self.stdout.write(f"\nReminders to delete (older than {cutoff_date.strftime('%Y-%m-%d')})")
        for item in status_breakdown:
            self.stdout.write(f"  {item['status']}: {item['count']}")
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(f"\n[DRY RUN] Would delete {total_to_delete} reminders")
            )
            return
        
        # Perform deletion
        try:
            deleted_count, _ = queryset.delete()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ Successfully deleted {deleted_count} old internal reminders"
                )
            )
            
            # Show remaining counts by status
            remaining_counts = InternalFollowUpReminder.objects.values('status').annotate(count=1)
            self.stdout.write("\nRemaining reminders by status:")
            for item in remaining_counts:
                self.stdout.write(f"  {item['status']}: {item['count']}")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            self.stdout.write(
                self.style.ERROR(f"Error during cleanup: {e}")
            )
