#!/usr/bin/env python
"""
Test script to verify the "My Leads" preset functionality
"""
import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from accounts.models import User
from dashboard.models import Lead

def test_my_leads_preset():
    """Test the My Leads preset logic"""
    
    # Check available users
    users = User.objects.all()
    print(f"Available users:")
    for user in users:
        print(f"  - {user.username} (role: {user.role})")
    
    # Get first user to test (preferably one with no assigned leads)
    test_user = None
    for user in users:
        assigned_count = Lead.objects.filter(assigned_user=user).count()
        print(f"  {user.username} has {assigned_count} assigned leads")
        if assigned_count == 0:
            test_user = user
            break
    
    if not test_user:
        test_user = users.first()
    
    print(f"\nTesting with user: {test_user.username} (role: {test_user.role})")
    
    # Check user's assigned leads count
    assigned_leads = Lead.objects.filter(assigned_user=test_user)
    assigned_count = assigned_leads.count()
    print(f"User has {assigned_count} assigned leads")
    
    # Check unassigned leads count
    unassigned_leads = Lead.objects.filter(assigned_user__isnull=True)
    unassigned_count = unassigned_leads.count()
    print(f"Total unassigned leads: {unassigned_count}")
    
    # Simulate the preset logic
    if assigned_count > 0:
        result_queryset = assigned_leads
        print(f"Logic: Showing user's assigned leads ({result_queryset.count()})")
    else:
        result_queryset = unassigned_leads
        print(f"Logic: Showing unassigned leads ({result_queryset.count()})")
    
    # Show some sample leads from the result
    sample_leads = result_queryset[:5]
    print(f"\nSample leads from result:")
    for lead in sample_leads:
        print(f"  - ID: {lead.id_lead}, Name: {lead.name}, Assigned: {lead.assigned_user}")
        
    return result_queryset.count()

if __name__ == "__main__":
    print("Testing My Leads preset functionality...")
    print("=" * 50)
    count = test_my_leads_preset()
    print("=" * 50)
    print(f"Final result: {count} leads would be shown to the test user")
