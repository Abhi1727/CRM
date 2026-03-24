from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import logging

from dashboard.models import Lead, InternalFollowUpReminder, User
from services.team_followup_monitoring_service import TeamFollowUpMonitoringService
from services.hierarchy_notification_service import HierarchyNotificationService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Escalate overdue follow-ups to hierarchy'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--hours-overdue',
            type=int,
            default=8,
            help='Hours overdue before escalating (default: 8)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be escalated without actually escalating',
        )
        parser.add_argument(
            '--manager-id',
            type=int,
            help='Process only for specific manager (optional)',
        )
    
    def handle(self, *args, **options):
        hours_overdue = options['hours_overdue']
        dry_run = options['dry_run']
        manager_id = options['manager_id']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Starting overdue follow-up escalation (hours_overdue={hours_overdue}, dry_run={dry_run})"
            )
        )
        
        monitoring_service = TeamFollowUpMonitoringService()
        hierarchy_service = HierarchyNotificationService()
        
        # Get manager if specified
        manager = None
        if manager_id:
            try:
                manager = User.objects.get(id=manager_id, role='manager')
                self.stdout.write(f"Processing for manager: {manager.username}")
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Manager with ID {manager_id} not found")
                )
                return
        
        # Monitor overdue follow-ups
        results = monitoring_service.monitor_team_overdue_followups(manager)
        
        self.stdout.write(f"Found {results['total_overdue']} overdue follow-ups")
        
        if results['total_overdue'] == 0:
            self.stdout.write(self.style.SUCCESS("No overdue follow-ups to process"))
            return
        
        # Process critical escalations
        if results['critical_overdue']:
            self.stdout.write(f"Processing {len(results['critical_overdue'])} critical escalations")
            
            for lead_data in results['critical_overdue']:
                try:
                    lead = Lead.objects.get(id=lead_data['id'])
                    
                    if dry_run:
                        self.stdout.write(
                            f"[DRY RUN] Would escalate lead {lead.name} "
                            f"(assigned to {lead_data['assigned_user__username']})"
                        )
                    else:
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
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"✓ Escalated lead {lead.name} for {lead.assigned_user.username}"
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"✗ Failed to escalate lead {lead.name}"
                                )
                            )
                            
                except Exception as e:
                    logger.error(f"Error escalating lead {lead_data['id']}: {e}")
                    self.stdout.write(
                        self.style.ERROR(f"Error escalating lead {lead_data['id']}: {e}")
                    )
        
        # Show overdue breakdown
        self.stdout.write("\nOverdue by User:")
        for username, count in results['overdue_by_user'].items():
            self.stdout.write(f"  {username}: {count}")
        
        self.stdout.write("\nOverdue by Priority:")
        for priority, count in results['overdue_by_priority'].items():
            self.stdout.write(f"  {priority}: {count}")
        
        # Summary
        self.stdout.write(
            self.style.SUCCESS(
                f"\nEscalation Summary: {results['escalations_sent']} escalations sent, "
                f"{results['teams_notified']} team members notified"
            )
        )
        
        # Recommendations
        if results['critical_overdue']:
            self.stdout.write(
                self.style.WARNING(
                    "\n⚠️  Recommendations:"
                )
            )
            self.stdout.write("  - Review follow-up procedures with team")
            self.stdout.write("  - Consider additional training for users with high overdue counts")
            self.stdout.write("  - Monitor reminder acknowledgment rates")
