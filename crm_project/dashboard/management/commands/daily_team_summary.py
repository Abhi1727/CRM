from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from dashboard.models import User
from services.internal_notification_service import InternalNotificationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Send daily team follow-up summaries'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--manager-id',
            type=int,
            help='Send summary for specific manager only (optional)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be sent without actually sending',
        )
        parser.add_argument(
            '--include-weekend',
            action='store_true',
            help='Include weekends in daily summaries (default: skip weekends)',
        )
    
    def handle(self, *args, **options):
        manager_id = options['manager_id']
        dry_run = options['dry_run']
        include_weekend = options['include_weekend']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting daily team summary generation (dry_run={dry_run}, include_weekend={include_weekend})"
            )
        )
        
        # Skip weekends unless explicitly included
        if not include_weekend:
            current_weekday = timezone.now().weekday()
            if current_weekday >= 5:  # Saturday (5) or Sunday (6)
                self.stdout.write(
                    self.style.WARNING("Skipping daily summary for weekend")
                )
                return
        
        notification_service = InternalNotificationService()
        
        # Get managers to send summaries to
        if manager_id:
            try:
                managers = [User.objects.get(id=manager_id, role='manager')]
                self.stdout.write(f"Sending summary for manager: {managers[0].username}")
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Manager with ID {manager_id} not found")
                )
                return
        else:
            managers = User.objects.filter(role='manager', account_status='active')
            self.stdout.write(f"Sending daily summaries to {managers.count()} managers")
        
        sent_count = 0
        failed_count = 0
        
        for manager in managers:
            try:
                # Get team members
                team_members = manager.get_accessible_users()
                
                if not team_members.exists():
                    self.stdout.write(
                        self.style.WARNING(f"No team members found for manager {manager.username}")
                    )
                    continue
                
                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Would send daily summary to {manager.username} "
                        f"({team_members.count()} team members)"
                    )
                    sent_count += 1
                else:
                    # Send daily summary
                    success = notification_service.send_team_summary(
                        team_users=team_members,
                        summary_type='daily'
                    )
                    
                    if success:
                        sent_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Daily summary sent to {manager.username}"
                            )
                        )
                    else:
                        failed_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f"✗ Failed to send daily summary to {manager.username}"
                            )
                        )
                
            except Exception as e:
                failed_count += 1
                logger.error(f"Error sending daily summary to manager {manager.username}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error sending daily summary to {manager.username}: {e}")
                )
        
        # Also send to owners if no specific manager was provided
        if not manager_id:
            owners = User.objects.filter(role='owner', account_status='active')
            
            for owner in owners:
                try:
                    # Get all users in owner's company
                    team_members = User.objects.filter(
                        company_id=owner.company_id,
                        account_status='active'
                    ).exclude(id=owner.id)
                    
                    if dry_run:
                        self.stdout.write(
                            f"[DRY RUN] Would send daily summary to owner {owner.username} "
                            f"({team_members.count()} total users)"
                        )
                        sent_count += 1
                    else:
                        success = notification_service.send_team_summary(
                            team_users=team_members,
                            summary_type='daily'
                        )
                        
                        if success:
                            sent_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"✓ Daily summary sent to owner {owner.username}"
                                )
                            )
                        else:
                            failed_count += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f"✗ Failed to send daily summary to owner {owner.username}"
                                )
                            )
                            
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error sending daily summary to owner {owner.username}: {e}")
                    self.stdout.write(
                        self.style.ERROR(f"Error sending daily summary to owner {owner.username}: {e}")
                    )
        
        # Summary
        total_processed = sent_count + failed_count
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDaily Summary Summary: {sent_count} sent, {failed_count} failed "
                f"out of {total_processed} total"
            )
        )
        
        # Next run suggestion
        if not include_weekend:
            next_weekday = (timezone.now() + timedelta(days=1)).weekday()
            if next_weekday >= 5:
                self.stdout.write(
                    self.style.WARNING(
                        "Note: Next run will be skipped due to weekend (use --include-weekend to override)"
                    )
                )
