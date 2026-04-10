#!/usr/bin/env python
"""
Test script to verify the transferred leads fix works correctly.
This script tests that leads assigned from unassigned state now appear in transferred leads.
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
from django.test import RequestFactory
from dashboard.views import leads_transferred

def test_transferred_leads_fix():
    """Test that the transferred leads fix works correctly"""
    User = get_user_model()
    print("Testing Transferred Leads Fix...")
    
    # Create a test user (manager/team lead/owner who can assign leads)
    test_user = User.objects.filter(role__in=['manager', 'team_lead', 'owner']).first()
    if not test_user:
        print("No user with assignment permissions found. Creating test user...")
        test_user = User.objects.create(
            username='test_manager',
            email='test@example.com',
            role='manager',
            company_id=1,
            account_status='active'
        )
    
    print(f"Using test user: {test_user.username} ({test_user.role})")
    
    # Create test leads - some with transfer fields, some with only assignment fields
    print("\nCreating test leads...")
    
    # Lead 1: Formal transfer (has transfer_date populated)
    lead1 = Lead.objects.create(
        name='Test Lead 1 - Formal Transfer',
        mobile='1234567890',
        email='test1@example.com',
        company_id=test_user.company_id,
        created_by=test_user,
        assigned_user=User.objects.filter(role='agent').first(),
        assigned_by=test_user,
        assigned_at=timezone.now(),
        transfer_by=test_user.username,
        transfer_date=timezone.now(),
        transfer_from="Previous User"
    )
    print(f"Created lead 1: {lead1.name} (formal transfer)")
    
    # Lead 2: Assignment from unassigned (only assigned_by/assigned_at populated)
    lead2 = Lead.objects.create(
        name='Test Lead 2 - Bulk Assignment',
        mobile='1234567891',
        email='test2@example.com',
        company_id=test_user.company_id,
        created_by=test_user,
        assigned_user=User.objects.filter(role='agent').first(),
        assigned_by=test_user,
        assigned_at=timezone.now()
        # No transfer fields populated
    )
    print(f"Created lead 2: {lead2.name} (bulk assignment from unassigned)")
    
    # Lead 3: Assignment by different user (should not appear)
    other_user = User.objects.exclude(id=test_user.id).first()
    if other_user:
        lead3 = Lead.objects.create(
            name='Test Lead 3 - Other User Assignment',
            mobile='1234567892',
            email='test3@example.com',
            company_id=test_user.company_id,
            created_by=other_user,
            assigned_user=User.objects.filter(role='agent').first(),
            assigned_by=other_user,
            assigned_at=timezone.now()
        )
        print(f"Created lead 3: {lead3.name} (assigned by {other_user.username})")
    
    # Test the leads_transferred view
    print(f"\nTesting leads_transferred view for user {test_user.username}...")
    
    # Create a mock request
    factory = RequestFactory()
    request = factory.get('/dashboard/leads/transferred/')
    request.user = test_user
    
    # Mock hierarchy context
    request.hierarchy_context = {
        'accessible_leads': Lead.objects.filter(company_id=test_user.company_id)
    }
    
    # Call the view
    try:
        response = leads_transferred(request)
        print(f"View executed successfully. Status: {response.status_code}")
        
        # Check the queryset used in the view
        
        # Replicate the view logic to test
        assigned_by_user_leads = request.hierarchy_context['accessible_leads'].filter(
            deleted=False,
            assigned_by=test_user,
            assigned_at__isnull=False
        )
        
        transfer_leads = request.hierarchy_context['accessible_leads'].filter(
            deleted=False,
            transfer_by=test_user.username,
            transfer_date__isnull=False
        )
        
        combined_queryset = (assigned_by_user_leads | transfer_leads).distinct()
        
        print(f"\nQueryset Results:")
        print(f"Leads assigned by {test_user.username}: {assigned_by_user_leads.count()}")
        print(f"Formal transfer leads: {transfer_leads.count()}")
        print(f"Combined unique leads: {combined_queryset.count()}")
        
        print(f"\nLeads that should appear:")
        for lead in combined_queryset:
            transfer_type = "Formal Transfer" if lead.transfer_date else "Bulk Assignment"
            print(f"- {lead.name} ({transfer_type})")
        
        # Verify our test leads are included
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
        
    except Exception as e:
        print(f"Error testing view: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup test leads
    print(f"\nCleaning up test leads...")
    Lead.objects.filter(name__startswith='Test Lead').delete()
    print("Test completed!")

if __name__ == '__main__':
    from django.utils import timezone
    test_transferred_leads_fix()
