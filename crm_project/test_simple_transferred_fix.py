#!/usr/bin/env python
"""
Simple test to verify the transferred leads fix works correctly.
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead
from django.utils import timezone

User = get_user_model()

def test_simple_fix():
    """Simple test of the transferred leads logic"""
    print("Simple Test of Transferred Leads Fix...")
    
    # Get or create a test user
    test_user = User.objects.first()
    if not test_user:
        print("No users found. Creating test user...")
        test_user = User.objects.create(
            username='test_user',
            email='test@example.com',
            role='manager',
            company_id=1,
            account_status='active'
        )
    
    print(f"Using test user: {test_user.username} ({test_user.role})")
    
    # Clean up any existing test leads
    Lead.objects.filter(name__startswith='Test Lead').delete()
    
    # Create test leads
    print("\nCreating test leads...")
    
    # Lead 1: Formal transfer
    lead1 = Lead.objects.create(
        name='Test Lead 1 - Formal Transfer',
        mobile='1234567890',
        email='test1@example.com',
        company_id=test_user.company_id,
        created_by=test_user,
        assigned_user=test_user,  # Assign to self for simplicity
        assigned_by=test_user,
        assigned_at=timezone.now(),
        transfer_by=test_user.username,
        transfer_date=timezone.now(),
        transfer_from="Previous User"
    )
    print(f"Created lead 1: {lead1.name}")
    
    # Lead 2: Assignment from unassigned (only assigned_by/assigned_at)
    lead2 = Lead.objects.create(
        name='Test Lead 2 - Bulk Assignment',
        mobile='1234567891',
        email='test2@example.com',
        company_id=test_user.company_id,
        created_by=test_user,
        assigned_user=test_user,
        assigned_by=test_user,
        assigned_at=timezone.now()
        # No transfer fields
    )
    print(f"Created lead 2: {lead2.name}")
    
    # Lead 3: Assignment by different user
    other_user = User.objects.exclude(id=test_user.id).first()
    if other_user:
        lead3 = Lead.objects.create(
            name='Test Lead 3 - Other User Assignment',
            mobile='1234567892',
            email='test3@example.com',
            company_id=test_user.company_id,
            created_by=other_user,
            assigned_user=other_user,
            assigned_by=other_user,
            assigned_at=timezone.now()
        )
        print(f"Created lead 3: {lead3.name} (assigned by {other_user.username})")
    
    # Test the new logic directly
    print(f"\nTesting the new leads_transferred logic...")
    
    # This is the new logic from the view
    all_leads = Lead.objects.filter(company_id=test_user.company_id, deleted=False)
    print(f"Total leads in company: {all_leads.count()}")
    
    assigned_by_user_leads = all_leads.filter(
        assigned_by=test_user,
        assigned_at__isnull=False
    )
    print(f"Leads assigned by {test_user.username}: {assigned_by_user_leads.count()}")
    for lead in assigned_by_user_leads:
        print(f"  - {lead.name}")
    
    transfer_leads = all_leads.filter(
        transfer_by=test_user.username,
        transfer_date__isnull=False
    )
    print(f"Formal transfer leads: {transfer_leads.count()}")
    for lead in transfer_leads:
        print(f"  - {lead.name}")
    
    combined_queryset = (assigned_by_user_leads | transfer_leads).distinct()
    print(f"Combined unique leads: {combined_queryset.count()}")
    for lead in combined_queryset:
        transfer_type = "Formal Transfer" if lead.transfer_date else "Bulk Assignment"
        print(f"  - {lead.name} ({transfer_type})")
    
    # Verify expected results
    print(f"\nVerification:")
    lead_ids = [lead.id_lead for lead in combined_queryset]
    
    if lead1.id_lead in lead_ids:
        print("SUCCESS: Lead 1 (formal transfer) is included")
    else:
        print("ERROR: Lead 1 (formal transfer) is missing")
        
    if lead2.id_lead in lead_ids:
        print("SUCCESS: Lead 2 (bulk assignment) is included")
    else:
        print("ERROR: Lead 2 (bulk assignment) is missing")
        
    if other_user and lead3.id_lead in lead_ids:
        print("ERROR: Lead 3 (other user assignment) should not be included")
    else:
        print("SUCCESS: Lead 3 (other user assignment) is correctly excluded")
    
    # Test the bulk assignment enhancement
    print(f"\nTesting bulk assignment enhancement...")
    
    # Create a new unassigned lead
    new_lead = Lead.objects.create(
        name='Test Lead 4 - New Unassigned',
        mobile='1234567893',
        email='test4@example.com',
        company_id=test_user.company_id,
        created_by=test_user
        # No assigned_user, assigned_by, assigned_at
    )
    print(f"Created new unassigned lead: {new_lead.name}")
    
    # Assign it using the enhanced method
    agent_user = User.objects.filter(role='agent').first() or test_user
    print(f"Assigning to {agent_user.username} with bulk_assignment=True...")
    
    new_lead.assign_to_user(agent_user, test_user, bulk_assignment=True)
    
    # Check if transfer fields were populated
    new_lead.refresh_from_db()
    print(f"After assignment:")
    print(f"  assigned_user: {new_lead.assigned_user}")
    print(f"  assigned_by: {new_lead.assigned_by}")
    print(f"  assigned_at: {new_lead.assigned_at}")
    print(f"  transfer_from: {new_lead.transfer_from}")
    print(f"  transfer_by: {new_lead.transfer_by}")
    print(f"  transfer_date: {new_lead.transfer_date}")
    
    if new_lead.transfer_from == "Unassigned" and new_lead.transfer_by:
        print("SUCCESS: Bulk assignment from unassigned populated transfer fields")
    else:
        print("ERROR: Bulk assignment from unassigned did not populate transfer fields")
    
    # Cleanup
    print(f"\nCleaning up test leads...")
    Lead.objects.filter(name__startswith='Test Lead').delete()
    print("Test completed!")

if __name__ == '__main__':
    test_simple_fix()
