#!/usr/bin/env python
"""
Test script to verify the UserEditForm role field fix.
This script tests that the role field shows the correct initial value.
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
django.setup()

from django.test import RequestFactory
from accounts.forms import UserEditForm
from accounts.models import User as CustomUser

def test_role_field_initial_value():
    """Test that role field shows correct initial value"""
    print("Testing UserEditForm role field initial value...")
    
    # Create test users
    owner = CustomUser.objects.create_user(
        username='testowner',
        email='owner@test.com',
        first_name='Test',
        last_name='Owner',
        password='testpass123',
        role='owner',
        company_id=1
    )
    
    manager = CustomUser.objects.create_user(
        username='testmanager',
        email='manager@test.com',
        first_name='Test',
        last_name='Manager',
        password='testpass123',
        role='manager',
        company_id=1,
        manager=owner
    )
    
    team_lead = CustomUser.objects.create_user(
        username='testteamlead',
        email='teamlead@test.com',
        first_name='Test',
        last_name='TeamLead',
        password='testpass123',
        role='team_lead',
        company_id=1,
        manager=manager
    )
    
    agent = CustomUser.objects.create_user(
        username='testagent',
        email='agent@test.com',
        first_name='Test',
        last_name='Agent',
        password='testpass123',
        role='agent',
        company_id=1,
        manager=manager,
        team_lead=team_lead
    )
    
    # Test 1: Owner editing agent
    print("\n1. Testing Owner editing Agent...")
    form = UserEditForm(editor=owner, target_user=agent)
    if 'role' in form.fields:
        initial_role = form.fields['role'].initial
        print(f"   Agent's current role: {agent.role}")
        print(f"   Form field initial value: {initial_role}")
        print(f"   ✓ PASS" if initial_role == agent.role else f"   ✗ FAIL - Expected {agent.role}, got {initial_role}")
    else:
        print("   Role field not present (expected for owner)")
    
    # Test 2: Manager editing team lead
    print("\n2. Testing Manager editing Team Lead...")
    form = UserEditForm(editor=manager, target_user=team_lead)
    if 'role' in form.fields:
        initial_role = form.fields['role'].initial
        print(f"   Team Lead's current role: {team_lead.role}")
        print(f"   Form field initial value: {initial_role}")
        print(f"   ✓ PASS" if initial_role == team_lead.role else f"   ✗ FAIL - Expected {team_lead.role}, got {initial_role}")
    else:
        print("   Role field not present")
    
    # Test 3: Manager editing agent
    print("\n3. Testing Manager editing Agent...")
    form = UserEditForm(editor=manager, target_user=agent)
    if 'role' in form.fields:
        initial_role = form.fields['role'].initial
        print(f"   Agent's current role: {agent.role}")
        print(f"   Form field initial value: {initial_role}")
        print(f"   ✓ PASS" if initial_role == agent.role else f"   ✗ FAIL - Expected {agent.role}, got {initial_role}")
    else:
        print("   Role field not present")
    
    # Test 4: Team lead editing own profile (should not have role field)
    print("\n4. Testing Team Lead editing own profile...")
    form = UserEditForm(editor=team_lead, target_user=team_lead)
    if 'role' in form.fields:
        print("   ✗ FAIL - Role field should not be present for team leads")
    else:
        print("   ✓ PASS - Role field correctly not present")
    
    # Test 5: Agent editing own profile (should not have role field)
    print("\n5. Testing Agent editing own profile...")
    form = UserEditForm(editor=agent, target_user=agent)
    if 'role' in form.fields:
        print("   ✗ FAIL - Role field should not be present for agents")
    else:
        print("   ✓ PASS - Role field correctly not present")
    
    print("\n" + "="*50)
    print("Test completed!")
    
    # Cleanup
    owner.delete()
    manager.delete()
    team_lead.delete()
    agent.delete()

if __name__ == '__main__':
    test_role_field_initial_value()
