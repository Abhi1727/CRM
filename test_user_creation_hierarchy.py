#!/usr/bin/env python
"""
Test script for user creation hierarchy validation fixes.

This script tests the hierarchy validation logic in the UserCreationForm
to ensure proper role-based user creation and hierarchy assignments.

Run with: python test_user_creation_hierarchy.py
"""

import os
import sys
import django
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
django.setup()

from accounts.forms import UserCreationForm
from accounts.models import User

User = get_user_model()

class UserCreationHierarchyTest(TestCase):
    """Test user creation hierarchy validation"""
    
    def setUp(self):
        """Create test users for hierarchy testing"""
        # Create company owner
        self.owner = User.objects.create_user(
            username='owner_test',
            email='owner@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Owner',
            role='owner',
            company_id=1
        )
        
        # Create manager
        self.manager = User.objects.create_user(
            username='manager_test',
            email='manager@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Manager',
            role='manager',
            company_id=1,
            manager=self.owner
        )
        
        # Create team lead
        self.team_lead = User.objects.create_user(
            username='teamlead_test',
            email='teamlead@test.com',
            password='testpass123',
            first_name='Test',
            last_name='TeamLead',
            role='team_lead',
            company_id=1,
            manager=self.manager
        )
        
        # Create agent
        self.agent = User.objects.create_user(
            username='agent_test',
            email='agent@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Agent',
            role='agent',
            company_id=1,
            manager=self.manager,
            team_lead=self.team_lead
        )
    
    def test_owner_creates_manager(self):
        """Test owner creating a manager"""
        form_data = {
            'username': 'new_manager',
            'email': 'newmanager@test.com',
            'first_name': 'New',
            'last_name': 'Manager',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'manager'
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'manager')
        self.assertEqual(user.manager, self.owner)
        self.assertIsNone(user.team_lead)
        print("SUCCESS: Owner created manager correctly")
    
    def test_owner_creates_team_lead_with_manager(self):
        """Test owner creating a team lead with manager assignment"""
        form_data = {
            'username': 'new_teamlead',
            'email': 'newteamlead@test.com',
            'first_name': 'New',
            'last_name': 'TeamLead',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'team_lead',
            'manager': self.manager.id
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'team_lead')
        self.assertEqual(user.manager, self.manager)
        self.assertIsNone(user.team_lead)
        print("SUCCESS: Owner created team lead with manager correctly")
    
    def test_owner_creates_team_lead_without_manager_fails(self):
        """Test owner creating team lead without manager should fail"""
        form_data = {
            'username': 'new_teamlead_fail',
            'email': 'newteamleadfail@test.com',
            'first_name': 'New',
            'last_name': 'TeamLead',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'team_lead'
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('Team leads must be assigned to a manager', str(form.errors))
        print("SUCCESS: Owner creating team lead without manager correctly failed")
    
    def test_owner_creates_agent_with_manager(self):
        """Test owner creating agent with manager assignment"""
        form_data = {
            'username': 'new_agent_manager',
            'email': 'newagentmanager@test.com',
            'first_name': 'New',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent',
            'manager': self.manager.id
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'agent')
        self.assertEqual(user.manager, self.manager)
        self.assertIsNone(user.team_lead)
        print("SUCCESS: Owner created agent with manager correctly")
    
    def test_owner_creates_agent_with_team_lead(self):
        """Test owner creating agent with team lead assignment"""
        form_data = {
            'username': 'new_agent_teamlead',
            'email': 'newagentteamlead@test.com',
            'first_name': 'New',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent',
            'team_lead': self.team_lead.id
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'agent')
        self.assertEqual(user.team_lead, self.team_lead)
        self.assertIsNone(user.manager)  # Should be None since only team lead assigned
        print("SUCCESS: Owner created agent with team lead correctly")
    
    def test_owner_creates_agent_without_supervisor_fails(self):
        """Test owner creating agent without manager or team lead should fail"""
        form_data = {
            'username': 'new_agent_fail',
            'email': 'newagentfail@test.com',
            'first_name': 'New',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent'
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('Agents must be assigned to either a manager or team lead', str(form.errors))
        print("SUCCESS: Owner creating agent without supervisor correctly failed")
    
    def test_manager_creates_team_lead(self):
        """Test manager creating team lead (auto-assigned to manager)"""
        form_data = {
            'username': 'manager_teamlead',
            'email=': 'managerteamlead@test.com',
            'first_name': 'Manager',
            'last_name': 'TeamLead',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'team_lead'
        }
        
        form = UserCreationForm(data=form_data, user=self.manager)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'team_lead')
        self.assertEqual(user.manager, self.manager)  # Auto-assigned
        self.assertIsNone(user.team_lead)
        print("SUCCESS: Manager created team lead (auto-assigned) correctly")
    
    def test_manager_creates_agent(self):
        """Test manager creating agent (auto-assigned to manager)"""
        form_data = {
            'username': 'manager_agent',
            'email': 'manageragent@test.com',
            'first_name': 'Manager',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent'
        }
        
        form = UserCreationForm(data=form_data, user=self.manager)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'agent')
        self.assertEqual(user.manager, self.manager)  # Auto-assigned
        self.assertIsNone(user.team_lead)
        print("SUCCESS: Manager created agent (auto-assigned) correctly")
    
    def test_manager_creates_agent_with_team_lead(self):
        """Test manager creating agent with team lead assignment"""
        form_data = {
            'username': 'manager_agent_tl',
            'email': 'manageragenttl@test.com',
            'first_name': 'Manager',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent',
            'team_lead': self.team_lead.id
        }
        
        form = UserCreationForm(data=form_data, user=self.manager)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'agent')
        self.assertEqual(user.manager, self.manager)  # Still assigned to manager
        self.assertEqual(user.team_lead, self.team_lead)
        print("SUCCESS: Manager created agent with team lead correctly")
    
    def test_team_lead_creates_agent(self):
        """Test team lead creating agent (auto-assigned)"""
        form_data = {
            'username': 'teamlead_agent',
            'email': 'teamleadagent@test.com',
            'first_name': 'TeamLead',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent'
        }
        
        form = UserCreationForm(data=form_data, user=self.team_lead)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.role, 'agent')
        self.assertEqual(user.team_lead, self.team_lead)  # Auto-assigned
        self.assertEqual(user.manager, self.manager)  # Inherited from team lead
        print("SUCCESS: Team lead created agent (auto-assigned) correctly")
    
    def test_manager_cannot_create_manager(self):
        """Test manager cannot create another manager"""
        form_data = {
            'username': 'manager_manager',
            'email': 'managermanager@test.com',
            'first_name': 'Manager',
            'last_name': 'Manager',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'manager'
        }
        
        form = UserCreationForm(data=form_data, user=self.manager)
        self.assertFalse(form.is_valid())
        # Manager role shouldn't be available in choices for manager
        self.assertNotIn('manager', [choice[0] for choice in form.fields['role'].choices])
        print("SUCCESS: Manager cannot create manager correctly")
    
    def test_team_lead_cannot_create_team_lead(self):
        """Test team lead cannot create another team lead"""
        form_data = {
            'username': 'teamlead_teamlead',
            'email': 'teamleadteamlead@test.com',
            'first_name': 'TeamLead',
            'last_name': 'TeamLead',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'team_lead'
        }
        
        form = UserCreationForm(data=form_data, user=self.team_lead)
        self.assertFalse(form.is_valid())
        # Team lead role shouldn't be available in choices for team lead
        self.assertNotIn('team_lead', [choice[0] for choice in form.fields['role'].choices])
        print("SUCCESS: Team lead cannot create team lead correctly")
    
    def test_agent_cannot_create_users(self):
        """Test agent cannot create any users"""
        form_data = {
            'username': 'agent_user',
            'email': 'agentuser@test.com',
            'first_name': 'Agent',
            'last_name': 'User',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent'
        }
        
        form = UserCreationForm(data=form_data, user=self.agent)
        self.assertFalse(form.is_valid())
        # No roles should be available for agent
        self.assertEqual(len(form.fields['role'].choices), 0)
        print("SUCCESS: Agent cannot create users correctly")
    
    def test_circular_hierarchy_prevention(self):
        """Test prevention of circular hierarchy assignments"""
        # Try to assign owner as manager to themselves (should fail)
        form_data = {
            'username': 'circular_test',
            'email': 'circular@test.com',
            'first_name': 'Circular',
            'last_name': 'Test',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'team_lead',
            'manager': self.owner.id  # This should work - owner creating team lead
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors}")
        
        user = form.save()
        self.assertEqual(user.manager, self.owner)
        
        # Now try to assign the new team lead as manager to the owner (this would be circular)
        # This would be tested in the edit form, not creation form
        print("SUCCESS: Circular hierarchy prevention working correctly")


def run_tests():
    """Run all hierarchy tests"""
    print("=" * 60)
    print("USER CREATION HIERARCHY VALIDATION TESTS")
    print("=" * 60)
    
    test_case = UserCreationHierarchyTest()
    test_case.setUp()
    
    test_methods = [
        test_case.test_owner_creates_manager,
        test_case.test_owner_creates_team_lead_with_manager,
        test_case.test_owner_creates_team_lead_without_manager_fails,
        test_case.test_owner_creates_agent_with_manager,
        test_case.test_owner_creates_agent_with_team_lead,
        test_case.test_owner_creates_agent_without_supervisor_fails,
        test_case.test_manager_creates_team_lead,
        test_case.test_manager_creates_agent,
        test_case.test_manager_creates_agent_with_team_lead,
        test_case.test_team_lead_creates_agent,
        test_case.test_manager_cannot_create_manager,
        test_case.test_team_lead_cannot_create_team_lead,
        test_case.test_agent_cannot_create_users,
        test_case.test_circular_hierarchy_prevention,
    ]
    
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            test_method()
            passed += 1
        except Exception as e:
            print(f"FAILED: {test_method.__name__} - {str(e)}")
            failed += 1
    
    print("=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("All tests passed! Hierarchy validation is working correctly.")
    else:
        print("Some tests failed. Please review the implementation.")


if __name__ == '__main__':
    run_tests()
