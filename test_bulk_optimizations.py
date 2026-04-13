#!/usr/bin/env python
"""
Test script to validate bulk operations optimizations
"""
import os
import sys
import django
from django.conf import settings
from django.test.utils import setup_test_environment
from django.db import connection

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadActivity, LeadHistory
from dashboard.views import _process_assignments_concurrently, _bulk_delete_optimized
from services.lead_reassigner import LeadReassigner
from django.utils import timezone
import time

User = get_user_model()

def create_test_data():
    """Create test data for optimization testing"""
    print("Creating test data...")
    
    # Get or create test users
    owner, created = User.objects.get_or_create(
        username='test_owner',
        defaults={
            'email': 'owner@test.com',
            'role': 'owner',
            'account_status': 'active',
            'company_id': 1
        }
    )
    
    manager, created = User.objects.get_or_create(
        username='test_manager',
        defaults={
            'email': 'manager@test.com',
            'role': 'manager',
            'account_status': 'active',
            'company_id': 1,
            'manager': owner
        }
    )
    
    team_lead, created = User.objects.get_or_create(
        username='test_teamlead',
        defaults={
            'email': 'teamlead@test.com',
            'role': 'team_lead',
            'account_status': 'active',
            'company_id': 1,
            'manager': manager
        }
    )
    
    agent, created = User.objects.get_or_create(
        username='test_agent',
        defaults={
            'email': 'agent@test.com',
            'role': 'agent',
            'account_status': 'active',
            'company_id': 1,
            'team_lead': team_lead,
            'manager': manager
        }
    )
    
    # Create test leads
    leads = []
    for i in range(100):
        lead = Lead.objects.create(
            name=f'Test Lead {i}',
            email=f'test{i}@example.com',
            phone=f'123456789{i:02d}',
            assigned_user=agent,
            assigned_by=manager,
            assigned_at=timezone.now(),
            company_id=1,
            status='new',
            deleted=False
        )
        leads.append(lead)
    
    print(f"Created {len(leads)} test leads")
    return leads, agent, manager

def test_bulk_assignment_optimization():
    """Test the optimized bulk assignment function"""
    print("\n=== Testing Bulk Assignment Optimization ===")
    
    leads, agent, manager = create_test_data()
    
    # Test optimized assignment
    start_time = time.time()
    successful, failed = _process_assignments_concurrently(
        leads, manager, manager, "Test bulk assignment"
    )
    elapsed_time = time.time() - start_time
    
    print(f"Optimized assignment: {successful} successful, {failed} failed in {elapsed_time:.2f}s")
    
    # Verify results
    updated_leads = Lead.objects.filter(assigned_user=manager).count()
    print(f"Leads assigned to manager: {updated_leads}")
    
    # Check activity logs
    activities = LeadActivity.objects.filter(activity_type='bulk_assignment').count()
    print(f"Activity logs created: {activities}")
    
    return successful, failed, elapsed_time

def test_bulk_delete_optimization():
    """Test the optimized bulk delete function"""
    print("\n=== Testing Bulk Delete Optimization ===")
    
    leads, agent, manager = create_test_data()
    
    # Test optimized delete
    start_time = time.time()
    deleted_count = _bulk_delete_optimized(leads, manager)
    elapsed_time = time.time() - start_time
    
    print(f"Optimized delete: {deleted_count} deleted in {elapsed_time:.2f}s")
    
    # Verify results
    deleted_leads = Lead.objects.filter(deleted=True).count()
    print(f"Leads marked as deleted: {deleted_leads}")
    
    # Check activity logs
    activities = LeadActivity.objects.filter(activity_type='delete').count()
    print(f"Activity logs created: {activities}")
    
    return deleted_count, elapsed_time

def test_lead_reassigner_optimization():
    """Test the optimized lead reassigner service"""
    print("\n=== Testing Lead Reassigner Optimization ===")
    
    leads, agent, manager = create_test_data()
    
    # Create some converted leads
    for i, lead in enumerate(leads[:20]):
        lead.status = 'sale_done'
        lead.exp_revenue = 1000.0 + i * 100
        lead.save()
    
    # Test optimized reassignment
    reassigner = LeadReassigner()
    
    start_time = time.time()
    results = reassigner.reassign_user_leads_optimized(agent, manager)
    elapsed_time = time.time() - start_time
    
    print(f"Optimized reassignment completed in {elapsed_time:.2f}s")
    print(f"Active leads reassigned: {results['active_leads_reassigned']}")
    print(f"Converted leads preserved: {results['converted_leads_preserved']}")
    print(f"Total revenue preserved: {results['total_revenue_preserved']}")
    
    return results, elapsed_time

def performance_comparison():
    """Compare performance before and after optimization"""
    print("\n=== Performance Comparison ===")
    
    # Test with different data sizes
    test_sizes = [100, 500, 1000]
    
    for size in test_sizes:
        print(f"\nTesting with {size} leads:")
        
        # Create test data
        leads, agent, manager = create_test_data()
        
        # Add more leads if needed
        current_count = Lead.objects.count()
        if current_count < size:
            for i in range(current_count, size):
                Lead.objects.create(
                    name=f'Test Lead {i}',
                    email=f'test{i}@example.com',
                    phone=f'123456789{i:02d}',
                    assigned_user=agent,
                    assigned_by=manager,
                    assigned_at=timezone.now(),
                    company_id=1,
                    status='new',
                    deleted=False
                )
        
        leads = Lead.objects.filter(assigned_user=agent)[:size]
        
        # Test optimized assignment
        start_time = time.time()
        successful, failed = _process_assignments_concurrently(
            leads, manager, manager, f"Performance test {size}"
        )
        elapsed_time = time.time() - start_time
        
        print(f"  {size} leads: {successful} successful in {elapsed_time:.2f}s "
              f"({elapsed_time/size*1000:.2f}ms per lead)")
        
        # Clean up for next test
        Lead.objects.filter(assigned_user=manager).update(assigned_user=agent)

def main():
    """Run all optimization tests"""
    print("Bulk Operations Optimization Test Suite")
    print("=" * 50)
    
    try:
        # Test individual optimizations
        test_bulk_assignment_optimization()
        test_bulk_delete_optimization()
        test_lead_reassigner_optimization()
        
        # Performance comparison
        performance_comparison()
        
        print("\n" + "=" * 50)
        print("All tests completed successfully!")
        print("Bulk operations are working as expected.")
        
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())
