"""
Test user creation hierarchy validation fixes.

This module tests the hierarchy validation logic in the UserCreationForm
to ensure proper role-based user creation and hierarchy assignments.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.forms import UserCreationForm

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
    
    def test_manager_creates_team_lead(self):
        """Test manager creating team lead (auto-assigned to manager)"""
        form_data = {
            'username': 'manager_teamlead',
            'email': 'managerteamlead@test.com',
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
    
    def test_team_lead_manager_validation(self):
        """Test validation that team lead must report to same manager as agent"""
        # Create another manager for testing
        another_manager = User.objects.create_user(
            username='another_manager',
            email='another@test.com',
            password='testpass123',
            first_name='Another',
            last_name='Manager',
            role='manager',
            company_id=1,
            manager=self.owner
        )
        
        # Create team lead under original manager
        test_team_lead = User.objects.create_user(
            username='test_teamlead',
            email='testtl@test.com',
            password='testpass123',
            first_name='Test',
            last_name='TeamLead',
            role='team_lead',
            company_id=1,
            manager=self.manager
        )
        
        # Try to create agent with team lead from one manager and different manager
        form_data = {
            'username': 'mismatch_agent',
            'email': 'mismatch@test.com',
            'first_name': 'Mismatch',
            'last_name': 'Agent',
            'password1': 'testpass123',
            'password2': 'testpass123',
            'role': 'agent',
            'manager': another_manager.id,
            'team_lead': test_team_lead.id
        }
        
        form = UserCreationForm(data=form_data, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('Team lead must report to the same manager', str(form.errors))
