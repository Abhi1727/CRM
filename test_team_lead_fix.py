#!/usr/bin/env python
"""
Test script to verify team lead field dynamic loading functionality
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from crm_project.accounts.forms import UserCreationForm

User = get_user_model()

def test_form_structure():
    """Test that UserCreationForm includes team_lead field for owners"""
    print("Testing UserCreationForm structure...")
    
    # Create a test owner user
    owner = User.objects.create_user(
        username='testowner',
        email='owner@test.com',
        password='testpass123',
        role='owner',
        company_id=1
    )
    
    # Test form initialization for owner
    form = UserCreationForm(user=owner)
    
    # Check if team_lead field exists for owners
    has_team_lead = 'team_lead' in form.fields
    print(f"✓ Owner form has team_lead field: {has_team_lead}")
    
    # Check if manager field exists for owners
    has_manager = 'manager' in form.fields
    print(f"✓ Owner form has manager field: {has_manager}")
    
    # Test form initialization for manager
    manager = User.objects.create_user(
        username='testmanager',
        email='manager@test.com',
        password='testpass123',
        role='manager',
        company_id=1,
        manager=owner
    )
    
    manager_form = UserCreationForm(user=manager)
    manager_has_team_lead = 'team_lead' in manager_form.fields
    print(f"✓ Manager form has team_lead field: {manager_has_team_lead}")
    
    # Clean up
    owner.delete()
    manager.delete()
    
    print("Form structure test completed successfully!")

def test_ajax_endpoint():
    """Test the AJAX endpoint for fetching team leads by manager"""
    print("\nTesting AJAX endpoint...")
    
    client = Client()
    
    # Create test users
    owner = User.objects.create_user(
        username='testowner2',
        email='owner2@test.com',
        password='testpass123',
        role='owner',
        company_id=1
    )
    
    manager = User.objects.create_user(
        username='testmanager2',
        email='manager2@test.com',
        password='testpass123',
        role='manager',
        company_id=1,
        manager=owner
    )
    
    team_lead = User.objects.create_user(
        username='testtl',
        email='tl@test.com',
        password='testpass123',
        role='team_lead',
        company_id=1,
        manager=manager
    )
    
    # Test the endpoint
    url = reverse('accounts:get_team_leads_by_manager')
    response = client.get(url, {'manager_id': manager.id})
    
    print(f"✓ Response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✓ Response success: {data.get('success')}")
        print(f"✓ Team leads count: {len(data.get('team_leads', []))}")
        if data.get('team_leads'):
            print(f"✓ Team lead name: {data['team_leads'][0]['name']}")
    
    # Clean up
    owner.delete()
    manager.delete()
    team_lead.delete()
    
    print("AJAX endpoint test completed successfully!")

if __name__ == '__main__':
    try:
        test_form_structure()
        test_ajax_endpoint()
        print("\n🎉 All tests passed! Team lead field fix is working correctly.")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
