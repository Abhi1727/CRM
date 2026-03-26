from django.core.management.base import BaseCommand
from django.utils import timezone
from services.duplicate_detector import DuplicateDetector
from dashboard.models import Lead


class Command(BaseCommand):
    help = 'Auto-group existing duplicate leads that dont have groups'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--company-id',
            type=int,
            default=1,
            help='Company ID to process (default: 1)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be grouped without making changes'
        )
    
    def handle(self, *args, **options):
        company_id = options['company_id']
        dry_run = options['dry_run']
        
        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Starting duplicate grouping for company {company_id}...")
        
        # Initialize duplicate detector
        detector = DuplicateDetector(company_id)
        
        # Get statistics before grouping
        stats_before = detector.get_duplicate_statistics()
        self.stdout.write(f"Before grouping:")
        self.stdout.write(f"  - Total leads: {stats_before['total_leads']}")
        self.stdout.write(f"  - Duplicate leads: {stats_before['duplicate_leads_count']}")
        self.stdout.write(f"  - Duplicate groups: {stats_before['duplicate_groups']}")
        
        if dry_run:
            self.stdout.write("\n[DRY RUN] Would group the following duplicates:")
        
        # Auto-group existing duplicates
        result = detector.auto_group_existing_duplicates()
        
        if dry_run:
            self.stdout.write(f"  - Groups that would be created: {result['groups_created']}")
            self.stdout.write(f"  - Leads that would be grouped: {result['leads_grouped']}")
            self.stdout.write(f"  - Mobile groups: {result['mobile_groups']}")
            self.stdout.write(f"  - Email groups: {result['email_groups']}")
        else:
            self.stdout.write(f"\nGrouping completed:")
            self.stdout.write(f"  - Groups created: {result['groups_created']}")
            self.stdout.write(f"  - Leads grouped: {result['leads_grouped']}")
            self.stdout.write(f"  - Mobile groups: {result['mobile_groups']}")
            self.stdout.write(f"  - Email groups: {result['email_groups']}")
            
            # Get statistics after grouping
            stats_after = detector.get_duplicate_statistics()
            self.stdout.write(f"\nAfter grouping:")
            self.stdout.write(f"  - Total leads: {stats_after['total_leads']}")
            self.stdout.write(f"  - Duplicate leads: {stats_after['duplicate_leads_count']}")
            self.stdout.write(f"  - Duplicate groups: {stats_after['duplicate_groups']}")
            
            # Show improvement
            if stats_before['duplicate_groups'] > 0:
                improvement = ((stats_after['duplicate_groups'] - stats_before['duplicate_groups']) / stats_before['duplicate_groups']) * 100
                self.stdout.write(f"\nImprovement: {improvement:+.1f}% more duplicate groups identified")
        
        self.stdout.write(self.style.SUCCESS(f"{'[DRY RUN] ' if dry_run else ''}Duplicate grouping completed successfully!"))
