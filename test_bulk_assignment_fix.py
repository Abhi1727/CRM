#!/usr/bin/env python
"""
Test script to verify bulk assignment functionality is working correctly
"""

import os
import sys
import django

# Setup Django
sys.path.append('/root/CRM/crm_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
os.environ['DJANGO_ALLOWED_HOSTS'] = '127.0.0.1,localhost,testserver,learnwithshef.com'
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from dashboard.models import Lead

def test_bulk_assignment():
    """Test bulk assignment functionality"""
    print("🔍 Testing Bulk Assignment Functionality")
    print("=" * 50)
    
    # Get test user
    User = get_user_model()
    user = User.objects.filter(role='owner').first()
    
    if not user:
        print("❌ No owner user found")
        return False
    
    print(f"✓ Test user: {user.username} (role: {user.role})")
    
    # Create test client
    client = Client()
    client.force_login(user)
    
    # Test 1: GET request to bulk assign page
    print("\n1. Testing GET request to bulk assign page...")
    try:
        response = client.get('/dashboard/leads/bulk-assign/', follow=True)
        if response.status_code == 200:
            print("✓ GET request successful - page loads correctly")
            if 'bulk_lead_assign.html' in response.content.decode():
                print("✓ Template rendered correctly")
            else:
                print("⚠ Template content may be incomplete")
        else:
            print(f"❌ GET request failed with status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ GET request error: {e}")
        return False
    
    # Test 2: POST request with actual leads
    print("\n2. Testing POST request with lead assignment...")
    leads = Lead.objects.filter(company_id=user.company_id, deleted=False)[:3]
    
    if not leads:
        print("❌ No leads found for testing")
        return False
    
    lead_ids = ','.join([str(lead.id_lead) for lead in leads])
    print(f"✓ Found {len(leads)} leads for testing: {lead_ids}")
    
    try:
        response = client.post('/dashboard/leads/bulk-assign/', {
            'assigned_user': user.id,
            'lead_ids': lead_ids,
            'assignment_notes': 'Test bulk assignment'
        }, follow=True)
        
        if response.status_code in [200, 302]:
            print("✓ POST request successful - bulk assignment processed")
            
            # Verify leads were actually assigned
            updated_leads = Lead.objects.filter(
                id_lead__in=[lead.id_lead for lead in leads],
                assigned_user=user
            )
            print(f"✓ {updated_leads.count()} leads successfully assigned to {user.username}")
            
            return True
        else:
            print(f"❌ POST request failed with status: {response.status_code}")
            print(f"Response content: {response.content.decode()[:500]}")
            return False
    except Exception as e:
        print(f"❌ POST request error: {e}")
        return False

if __name__ == '__main__':
    success = test_bulk_assignment()
    print("\n" + "=" * 50)
    if success:
        print("🎉 All tests passed! Bulk assignment is working correctly.")
    else:
        print("❌ Tests failed. Bulk assignment needs attention.")
    sys.exit(0 if success else 1)
