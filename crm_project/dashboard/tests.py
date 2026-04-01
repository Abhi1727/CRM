from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from dashboard.models import Lead, LeadActivity
from services.lead_reassigner import LeadReassigner
import json
import logging

User = get_user_model()

class AdminManualReassignmentTests(TestCase):
    """Test cases for admin-only manual lead reassignment feature"""
    
    def setUp(self):
        # Create company and users
        self.owner = User.objects.create_user(
            username='owner', 
            email='owner@test.com', 
            password='testpass123',
            role='owner',
            company_id=1
        )
        
        self.manager = User.objects.create_user(
            username='manager', 
            email='manager@test.com', 
            password='testpass123',
            role='manager',
            company_id=1
        )
        
        self.team_lead = User.objects.create_user(
            username='teamlead', 
            email='teamlead@test.com', 
            password='testpass123',
            role='team_lead',
            company_id=1
        )
        
        self.agent = User.objects.create_user(
            username='agent', 
            email='agent@test.com', 
            password='testpass123',
            role='agent',
            company_id=1
        )
        
        self.other_agent = User.objects.create_user(
            username='otheragent', 
            email='other@test.com', 
            password='testpass123',
            role='agent',
            company_id=1
        )
        
        # Set up team relationships
        self.agent.team_lead = self.team_lead
        self.agent.save()
        self.other_agent.team_lead = self.team_lead
        self.other_agent.save()
        
        # Create test leads for the agent to be deleted
        self.active_lead = Lead.objects.create(
            name='Active Lead',
            email='active@test.com',
            mobile='1234567890',
            assigned_user=self.agent,
            status='lead',
            exp_revenue=10000
        )
        
        self.converted_lead = Lead.objects.create(
            name='Converted Lead',
            email='converted@test.com',
            mobile='0987654321',
            assigned_user=self.agent,
            status='sale_done',
            exp_revenue=15000
        )
        
        self.client = Client()
    
    def test_admin_can_access_users_for_reassignment_api(self):
        """Test that admin (owner) can access the users-for-reassignment API"""
        self.client.login(username='owner', password='testpass123')
        
        response = self.client.get('/accounts/api/users-for-reassignment/?exclude_user_id=' + str(self.agent.id))
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        # Should return all active users except the deleted user and current admin
        user_ids = [user['id'] for user in data['users']]
        self.assertNotIn(self.agent.id, user_ids)  # Deleted user excluded
        self.assertNotIn(self.owner.id, user_ids)  # Current admin excluded
        self.assertIn(self.manager.id, user_ids)   # Other users included
        self.assertIn(self.team_lead.id, user_ids)
        self.assertIn(self.other_agent.id, user_ids)
    
    def test_non_admin_cannot_access_users_for_reassignment_api(self):
        """Test that non-admin users cannot access the users-for-reassignment API"""
        self.client.login(username='manager', password='testpass123')
        
        response = self.client.get('/accounts/api/users-for-reassignment/?exclude_user_id=' + str(self.agent.id))
        
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Only owners can access', data['error'])
    
    def test_manual_reassignment_method(self):
        """Test the manual reassignment method in LeadReassigner"""
        reassigner = LeadReassigner()
        
        # Perform manual reassignment
        results = reassigner.reassign_user_leads_to_specific(
            self.agent, self.other_agent, self.owner
        )
        
        # Check results
        self.assertEqual(results['active_leads_reassigned'], 1)
        self.assertEqual(results['converted_leads_preserved'], 1)
        self.assertEqual(results['total_revenue_preserved'], 15000)
        self.assertEqual(results['manual_assignment']['from_user'], 'agent')
        self.assertEqual(results['manual_assignment']['to_user'], 'otheragent')
        self.assertEqual(results['manual_assignment']['assigned_by'], 'owner')
        self.assertEqual(results['manual_assignment']['assignment_type'], 'admin_manual')
        
        # Check that active lead was reassigned
        self.active_lead.refresh_from_db()
        self.assertEqual(self.active_lead.assigned_user, self.other_agent)
        
        # Check that converted lead preserved sales credit
        self.converted_lead.refresh_from_db()
        self.assertEqual(self.converted_lead.primary_sales_credit, self.agent)
        self.assertTrue(self.converted_lead.sales_credit_preserved)
        
        # Check activity logs
        activities = LeadActivity.objects.filter(lead=self.active_lead)
        self.assertTrue(activities.filter(activity_type='admin_manual_reassignment').exists())
    
    def test_manual_reassignment_activity_logging(self):
        """Test that manual reassignment creates proper activity logs"""
        reassigner = LeadReassigner()
        
        reassigner.reassign_user_leads_to_specific(
            self.agent, self.other_agent, self.owner
        )
        
        # Check activity log for active lead
        activity = LeadActivity.objects.get(lead=self.active_lead)
        self.assertEqual(activity.activity_type, 'admin_manual_reassignment')
        self.assertEqual(activity.user, self.owner)
        self.assertIn('Admin manually reassigned lead', activity.description)
        self.assertIn('agent', activity.description)
        self.assertIn('otheragent', activity.description)
    
    def test_delete_user_with_manual_reassignment(self):
        """Test the complete delete_user flow with manual reassignment"""
        self.client.login(username='owner', password='testpass123')
        
        # Post with manual reassignment
        response = self.client.post('/accounts/users/' + str(self.agent.id) + '/delete/', {
            'reassignment_type': 'manual',
            'selected_user_id': str(self.other_agent.id)
        })
        
        # Should redirect to user list
        self.assertEqual(response.status_code, 302)
        
        # Check that user was deactivated
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_active)
        self.assertEqual(self.agent.account_status, 'inactive')
        
        # Check that leads were reassigned
        self.active_lead.refresh_from_db()
        self.assertEqual(self.active_lead.assigned_user, self.other_agent)
        
        # Check activity logs
        self.assertTrue(
            LeadActivity.objects.filter(
                lead=self.active_lead,
                activity_type='admin_manual_reassignment'
            ).exists()
        )
    
    def test_delete_user_with_hierarchy_reassignment(self):
        """Test the delete_user flow with automatic hierarchy reassignment"""
        self.client.login(username='owner', password='testpass123')
        
        # Post with hierarchy reassignment
        response = self.client.post('/accounts/users/' + str(self.agent.id) + '/delete/', {
            'reassignment_type': 'hierarchy'
        })
        
        # Should redirect to user list
        self.assertEqual(response.status_code, 302)
        
        # Check that leads were reassigned to team lead (hierarchy)
        self.active_lead.refresh_from_db()
        self.assertEqual(self.active_lead.assigned_user, self.team_lead)
        
        # Check activity logs for hierarchy reassignment
        self.assertTrue(
            LeadActivity.objects.filter(
                lead=self.active_lead,
                activity_type='deletion_reassignment'
            ).exists()
        )
    
    def test_manual_reassignment_validation(self):
        """Test validation for manual reassignment"""
        self.client.login(username='owner', password='testpass123')
        
        # Test with no selected user
        response = self.client.post('/accounts/users/' + str(self.agent.id) + '/delete/', {
            'reassignment_type': 'manual',
            'selected_user_id': ''
        })
        
        # Should return to deletion page with error
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selected user is not active')
    
    def test_user_lead_summary_api(self):
        """Test the user lead summary API endpoint"""
        self.client.login(username='owner', password='testpass123')
        
        response = self.client.get('/accounts/api/user/' + str(self.agent.id) + '/lead-summary/')
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])
        
        # Check summary data
        user_data = data['data']['user']
        self.assertEqual(user_data['username'], 'agent')
        
        lead_stats = data['data']['lead_stats']
        self.assertEqual(lead_stats['total_leads'], 2)
        self.assertEqual(lead_stats['active_leads'], 1)
        self.assertEqual(lead_stats['converted_leads'], 1)
        self.assertEqual(lead_stats['conversion_rate'], 50.0)
    
    def test_non_admin_cannot_access_lead_summary_api(self):
        """Test that non-admin users cannot access lead summary API"""
        self.client.login(username='manager', password='testpass123')
        
        response = self.client.get('/accounts/api/user/' + str(self.agent.id) + '/lead-summary/')
        
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.content)
        self.assertFalse(data['success'])
        self.assertIn('Only owners can access', data['error'])

class LeadStatusUpdatePermissionTests(TestCase):
    def setUp(self):
        # Create users with different roles
        self.owner = User.objects.create_user(
            username='owner', 
            email='owner@test.com', 
            password='testpass123',
            role='owner'
        )
        
        self.manager = User.objects.create_user(
            username='manager', 
            email='manager@test.com', 
            password='testpass123',
            role='manager'
        )
        
        self.team_lead = User.objects.create_user(
            username='teamlead', 
            email='teamlead@test.com', 
            password='testpass123',
            role='team_lead'
        )
        
        self.agent = User.objects.create_user(
            username='agent', 
            email='agent@test.com', 
            password='testpass123',
            role='agent'
        )
        
        # Set up team relationships
        self.agent.team_lead = self.team_lead
        self.agent.save()
        
        # Create test leads
        self.lead1 = Lead.objects.create(
            name='Test Lead 1',
            email='lead1@test.com',
            mobile='1234567890',
            assigned_user=self.agent
        )
        
        self.lead2 = Lead.objects.create(
            name='Test Lead 2',
            email='lead2@test.com',
            mobile='1234567891',
            assigned_user=self.manager
        )
        
        self.lead3 = Lead.objects.create(
            name='Test Lead 3',
            email='lead3@test.com',
            mobile='1234567892',
            assigned_user=self.team_lead
        )

    def test_owner_can_update_any_lead_status(self):
        """Owner should be able to update status for any lead"""
        self.assertTrue(self.lead1.can_update_status_by(self.owner))
        self.assertTrue(self.lead2.can_update_status_by(self.owner))
        self.assertTrue(self.lead3.can_update_status_by(self.owner))

    def test_agent_can_only_update_own_leads(self):
        """Agent should only be able to update status for leads assigned to them"""
        self.assertTrue(self.lead1.can_update_status_by(self.agent))
        self.assertFalse(self.lead2.can_update_status_by(self.agent))
        self.assertFalse(self.lead3.can_update_status_by(self.agent))

    def test_team_lead_can_update_team_member_leads(self):
        """Team lead should be able to update status for their team members and their own leads"""
        self.assertTrue(self.lead1.can_update_status_by(self.team_lead))  # assigned to their agent
        self.assertFalse(self.lead2.can_update_status_by(self.team_lead))  # assigned to manager
        self.assertTrue(self.lead3.can_update_status_by(self.team_lead))  # assigned to themselves

    def test_manager_can_update_accessible_leads(self):
        """Manager should be able to update status for leads in their accessible scope"""
        # This test depends on the manager's accessible leads queryset logic
        # For now, we'll test the basic functionality
        self.assertTrue(self.lead2.can_update_status_by(self.manager))  # assigned to themselves
        
        # The manager's access to other leads depends on the hierarchy logic
        # which would need more complex test setup with proper relationships


class LeadReassignmentTestCase(TestCase):
    """Test cases for lead reassignment and sales credit preservation"""
    
    def setUp(self):
        """Set up test data"""
        self.logger = logging.getLogger(__name__)
        
        # Create test users in hierarchy
        self.owner = User.objects.create_user(
            username='test_owner',
            email='owner@test.com',
            password='test123',
            role='owner',
            company_id=1
        )
        
        self.manager = User.objects.create_user(
            username='test_manager',
            email='manager@test.com',
            password='test123',
            role='manager',
            company_id=1,
            manager=self.owner
        )
        
        self.team_lead = User.objects.create_user(
            username='test_teamlead',
            email='teamlead@test.com',
            password='test123',
            role='team_lead',
            company_id=1,
            manager=self.manager
        )
        
        self.agent = User.objects.create_user(
            username='test_agent',
            email='agent@test.com',
            password='test123',
            role='agent',
            company_id=1,
            manager=self.manager,
            team_lead=self.team_lead
        )
        
        # Create test leads
        self.active_lead = Lead.objects.create(
            name='Active Lead',
            mobile='1234567890',
            email='active@test.com',
            assigned_user=self.agent,
            created_by=self.owner,
            converted=False,
            exp_revenue='10000.00'
        )
        
        self.converted_lead = Lead.objects.create(
            name='Converted Lead',
            mobile='0987654321',
            email='converted@test.com',
            assigned_user=self.agent,
            created_by=self.owner,
            converted=True,
            status='sale_done',  # This is the key field for converted leads
            exp_revenue='25000.00'
        )
        
        # Initialize reassigner
        self.reassigner = LeadReassigner()
    
    def test_agent_deletion_lead_reassignment(self):
        """Test lead reassignment when an agent is deleted"""
        # Verify initial state
        self.assertEqual(Lead.objects.filter(assigned_user=self.agent).count(), 2)
        
        # Perform deletion
        results = self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify results
        self.assertEqual(results['active_leads_reassigned'], 1)
        self.assertEqual(results['converted_leads_preserved'], 1)
        self.assertEqual(results['total_revenue_preserved'], Decimal('25000.00'))
        
        # Verify active lead reassigned to team lead
        self.active_lead.refresh_from_db()
        self.assertEqual(self.active_lead.assigned_user, self.team_lead)
        self.assertIsNotNone(self.active_lead.transfer_from)
        self.assertEqual(self.active_lead.transfer_from, self.agent.username)
        
        # Verify converted lead preserved with original credit
        self.converted_lead.refresh_from_db()
        self.assertEqual(self.converted_lead.assigned_user, self.agent)  # Still assigned to agent
        self.assertEqual(self.converted_lead.primary_sales_credit, self.agent)
        self.assertTrue(self.converted_lead.sales_credit_preserved)
        
        # Verify preserved metrics updated
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.preserved_leads_count, 1)
        self.assertEqual(self.agent.preserved_converted_count, 1)
        self.assertEqual(self.agent.preserved_revenue, Decimal('25000.00'))
    
    def test_sales_credit_preservation_accuracy(self):
        """Test that sales credit preservation is accurate"""
        # Perform deletion
        results = self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify exact revenue preservation
        expected_revenue = Decimal('25000.00')
        self.assertEqual(results['total_revenue_preserved'], expected_revenue)
        
        # Verify converted lead has correct preservation
        self.converted_lead.refresh_from_db()
        self.assertEqual(self.converted_lead.primary_sales_credit, self.agent)
        self.assertTrue(self.converted_lead.sales_credit_preserved)
    
    def test_assignment_history_preservation(self):
        """Test that assignment history is properly preserved"""
        # Perform deletion
        self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify assignment history contains deletion record
        self.active_lead.refresh_from_db()
        assignments = self.active_lead.assignment_history.get('assignments', [])
        
        # Should have at least one deletion reassignment record
        deletion_records = [a for a in assignments if a.get('action') == 'deletion_reassignment']
        self.assertTrue(len(deletion_records) > 0)
        
        deletion_record = deletion_records[0]
        self.assertEqual(deletion_record['from']['user'], self.agent.id)
        self.assertEqual(deletion_record['to']['user'], self.team_lead.id)
        self.assertEqual(deletion_record['by'], self.owner.id)
        self.assertIn('User', deletion_record['reason'])
    
    def test_activity_logging(self):
        """Test that proper activity logs are created"""
        # Perform deletion
        self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify activity logs created
        activities = LeadActivity.objects.filter(lead=self.active_lead)
        self.assertTrue(activities.exists())
        
        # Check for specific activity types
        reassignment_activity = activities.filter(activity_type='deletion_reassignment').first()
        self.assertIsNotNone(reassignment_activity)
        self.assertIn('reassigned from', reassignment_activity.description)
    
    def test_hierarchy_fallback_logic(self):
        """Test hierarchy fallback logic when primary replacement is unavailable"""
        # Deactivate team lead to test fallback
        self.team_lead.account_status = 'inactive'
        self.team_lead.save()
        
        # Perform deletion - should fall back to manager
        results = self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify active lead reassigned to manager (fallback)
        self.active_lead.refresh_from_db()
        self.assertEqual(self.active_lead.assigned_user, self.manager)
    
    def test_reassignment_summary_accuracy(self):
        """Test that reassignment summary provides accurate information"""
        summary = self.reassigner.get_reassignment_summary(self.agent)
        
        # Verify summary data
        self.assertEqual(summary['active_leads_count'], 1)
        self.assertEqual(summary['converted_leads_count'], 1)
        self.assertEqual(summary['total_preserved_revenue'], Decimal('25000.00'))
        self.assertEqual(summary['replacement_user'], self.team_lead.username)
        self.assertEqual(summary['replacement_role'], 'Team Lead')
        self.assertEqual(summary['impact_level'], 'low')  # 1 converted lead = low impact
    
    def test_performance_metrics_preservation(self):
        """Test that original performance metrics are preserved"""
        # Set initial performance metrics
        self.agent.leads_converted_count = 5
        self.agent.save()
        
        # Perform deletion
        self.reassigner.reassign_user_leads(self.agent, self.owner)
        
        # Verify original metrics preserved
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.leads_converted_count, 5)  # Should remain unchanged
        self.assertEqual(self.agent.preserved_converted_count, 1)  # New preserved count
