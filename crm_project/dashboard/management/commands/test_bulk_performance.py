from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dashboard.models import Lead, BulkOperation
from dashboard.bulk_assignment_processor import BulkAssignmentProcessor
from core.cache import CacheManager
import time
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Test bulk assignment performance'

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting Bulk Assignment Performance Test")
        self.stdout.write("=" * 50)

        # Get owner user
        owner = User.objects.filter(role='owner').first()
        if not owner:
            self.stdout.write(self.style.ERROR("No owner user found for testing"))
            return

        # Test with different lead counts
        test_sizes = [50, 100, 200]
        results = []

        for size in test_sizes:
            self.stdout.write(f"\n📊 Testing with {size} leads...")
            
            # Create test data
            leads, agent = self.create_test_data(size, owner)
            if not leads or not agent:
                continue

            # Test optimized version
            optimized_result = self.test_optimized_bulk_assignment(leads, agent, owner)
            
            if optimized_result:
                results.append({
                    'size': size,
                    'optimized_time': optimized_result['execution_time'],
                    'leads_per_second': optimized_result['leads_per_second'],
                    'leads_processed': optimized_result['leads_processed'],
                    'errors': optimized_result['errors']
                })

            # Cleanup
            Lead.objects.filter(id_lead__in=[lead.id_lead for lead in leads]).delete()
            BulkOperation.objects.filter(user=owner).delete()

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("📊 PERFORMANCE TEST SUMMARY")
        self.stdout.write("=" * 50)

        for result in results:
            self.stdout.write(f"Size {result['size']}: {result['optimized_time']:.2f}s ({result['leads_per_second']:.1f} leads/sec)")

        # Save results
        with open('/root/CRM/test_results.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        self.stdout.write(f"\n✅ Performance testing completed")
        self.stdout.write("Results saved to test_results.json")

    def create_test_data(self, num_leads, owner):
        """Create test leads for performance testing."""
        self.stdout.write(f"Creating {num_leads} test leads...")
        
        # Create test agent
        agent, created = User.objects.get_or_create(
            username='test_agent_bulk',
            defaults={
                'email': 'agent@test.com',
                'first_name': 'Test',
                'last_name': 'Agent',
                'role': 'agent',
                'company_id': owner.company_id,
                'account_status': 'active'
            }
        )
        
        # Create test leads
        leads = []
        for i in range(num_leads):
            lead = Lead.objects.create(
                name=f'Test Lead {i+1}',
                email=f'testlead{i+1}@example.com',
                mobile=f'+1234567890{i%10}',
                company_id=owner.company_id,
                status='lead',
                assigned_user=None,
                assigned_by=None
            )
            leads.append(lead)
        
        self.stdout.write(f"Created {len(leads)} test leads")
        return leads, agent

    def test_optimized_bulk_assignment(self, leads, agent, owner):
        """Test the optimized bulk assignment processor."""
        self.stdout.write("\n=== Testing Optimized Bulk Assignment ===")
        
        lead_ids = [lead.id_lead for lead in leads]
        
        # Create bulk operation
        operation = BulkOperation.objects.create(
            operation_id=f'test_{int(time.time())}_{len(lead_ids)}',
            operation_type='bulk_assign',
            user=owner,
            company_id=owner.company_id,
            total_items=len(lead_ids)
        )
        
        # Initialize processor
        processor = BulkAssignmentProcessor(
            operation_id=operation.id,
            lead_ids=lead_ids,
            assigned_user_id=agent.id,
            assigned_by_id=owner.id,
            company_id=owner.company_id
        )
        
        # Measure performance
        start_time = time.time()
        
        try:
            result = processor.execute()
            end_time = time.time()
            
            execution_time = end_time - start_time
            
            self.stdout.write(self.style.SUCCESS(f"✅ Optimized assignment completed successfully!"))
            self.stdout.write(f"   Leads processed: {result['processed']}/{result['total']}")
            self.stdout.write(f"   Execution time: {execution_time:.2f} seconds")
            self.stdout.write(f"   Leads per second: {result['processed']/execution_time:.2f}")
            self.stdout.write(f"   Errors: {result['errors']}")
            
            return {
                'type': 'optimized',
                'execution_time': execution_time,
                'leads_processed': result['processed'],
                'leads_per_second': result['processed']/execution_time,
                'errors': result['errors'],
                'metrics': result['performance_metrics']
            }
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Optimized assignment failed: {str(e)}"))
            return None
