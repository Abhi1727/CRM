#!/usr/bin/env python
"""
Test script to simulate the exact form submission scenario where leads go to manager instead of selected agent.
"""

import os
import sys
import django

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead
from services.lead_reassigner import LeadReassigner
from django.test import RequestFactory
import logging

User = get_user_model()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def simulate_form_submission():
    """Simulate the exact form submission that's causing the issue"""
    logger.info("=== SIMULATING FORM SUBMISSION ISSUE ===")
    
    try:
        # Find users for testing
        admin_user = User.objects.filter(role='owner').first()
        if not admin_user:
            logger.error("No admin user found")
            return
        
        # Use agent1 (has manager1) as the agent to delete
        agent_to_delete = User.objects.filter(username='agent1').first()
        if not agent_to_delete:
            logger.error("Agent1 not found")
            return
        
        # Use testuser as the target agent (no manager)
        target_agent = User.objects.filter(username='testuser').first()
        if not target_agent:
            logger.error("Testuser (target agent) not found")
            return
        
        # The manager should be manager1
        manager = agent_to_delete.manager
        if not manager:
            logger.error("Agent1 has no manager - this scenario requires a manager")
            return
        
        logger.info(f"Test setup:")
        logger.info(f"  Admin: {admin_user.username}")
        logger.info(f"  Agent to delete: {agent_to_delete.username}")
        logger.info(f"  Target agent (should receive leads): {target_agent.username}")
        logger.info(f"  Manager (should NOT receive leads): {manager.username}")
        
        # Create test leads for the agent
        logger.info("Creating test leads...")
        leads_created = []
        for i in range(3):
            lead = Lead.objects.create(
                name=f"Form Test Lead {i+1}",
                email=f"formtest{i+1}@test.com",
                mobile=f"987654321{i}",
                country="India",
                course_name="Test Course",
                status='lead',
                assigned_user=agent_to_delete,
                assigned_by=admin_user,
                assigned_at=django.utils.timezone.now(),
                exp_revenue=str(2000.0 * (i + 1))
            )
            leads_created.append(lead)
        
        logger.info(f"Created {len(leads_created)} test leads for {agent_to_delete.username}")
        
        # Create a mock request to simulate the form submission
        factory = RequestFactory()
        
        # Test Case 1: Correct form submission with selected_user_id
        logger.info("=== TEST CASE 1: CORRECT FORM SUBMISSION ===")
        request = factory.post(f'/accounts/delete-user/{agent_to_delete.id}/', {
            'selected_user_id': str(target_agent.id),  # This should work correctly
            'csrfmiddlewaretoken': 'test-token'
        })
        request.user = admin_user
        
        logger.info(f"Simulating POST request with selected_user_id: {target_agent.id}")
        
        # Import and test the view function
        from accounts.views import delete_user
        
        # This should trigger manual reassignment
        try:
            response = delete_user(request, agent_to_delete.id)
            logger.info(f"Response status: {response.status_code}")
            
            # Check where the leads went
            target_agent_leads = Lead.objects.filter(assigned_user=target_agent, name__startswith="Form Test Lead")
            manager_leads = Lead.objects.filter(assigned_user=manager, name__startswith="Form Test Lead")
            
            logger.info(f"Results after correct form submission:")
            logger.info(f"  Leads assigned to target agent ({target_agent.username}): {target_agent_leads.count()}")
            logger.info(f"  Leads assigned to manager ({manager.username}): {manager_leads.count()}")
            
            if manager_leads.count() > 0:
                logger.error("❌ ISSUE REPRODUCED: Leads went to manager instead of target agent!")
                for lead in manager_leads:
                    logger.error(f"    - {lead.name} (ID: {lead.id_lead})")
            else:
                logger.info("✅ Manual reassignment worked correctly")
                
        except Exception as e:
            logger.error(f"Error in test case 1: {str(e)}")
        
        # Clean up for next test
        Lead.objects.filter(name__startswith="Form Test Lead").delete()
        
        # Test Case 2: Form submission WITHOUT selected_user_id (should use hierarchy)
        logger.info("=== TEST CASE 2: MISSING selected_user_id (should use hierarchy) ===")
        
        # Recreate leads
        for i in range(3):
            lead = Lead.objects.create(
                name=f"Hierarchy Test Lead {i+1}",
                email=f"hierarchytest{i+1}@test.com",
                mobile=f"55555555{i}",
                country="India",
                course_name="Test Course",
                status='lead',
                assigned_user=agent_to_delete,
                assigned_by=admin_user,
                assigned_at=django.utils.timezone.now(),
                exp_revenue=str(3000.0 * (i + 1))
            )
            leads_created.append(lead)
        
        # Simulate form submission without selected_user_id
        request = factory.post(f'/accounts/delete-user/{agent_to_delete.id}/', {
            'csrfmiddlewaretoken': 'test-token'
            # Note: NO selected_user_id - this should trigger hierarchy reassignment
        })
        request.user = admin_user
        
        logger.info("Simulating POST request WITHOUT selected_user_id (should use hierarchy)")
        
        try:
            response = delete_user(request, agent_to_delete.id)
            logger.info(f"Response status: {response.status_code}")
            
            # Check where the leads went (should go to manager via hierarchy)
            target_agent_leads = Lead.objects.filter(assigned_user=target_agent, name__startswith="Hierarchy Test Lead")
            manager_leads = Lead.objects.filter(assigned_user=manager, name__startswith="Hierarchy Test Lead")
            
            logger.info(f"Results after hierarchy reassignment:")
            logger.info(f"  Leads assigned to target agent ({target_agent.username}): {target_agent_leads.count()}")
            logger.info(f"  Leads assigned to manager ({manager.username}): {manager_leads.count()}")
            
            if manager_leads.count() > 0:
                logger.info("✅ Hierarchy reassignment worked correctly (leads went to manager)")
            else:
                logger.warning("⚠️ Unexpected: Hierarchy reassignment didn't work as expected")
                
        except Exception as e:
            logger.error(f"Error in test case 2: {str(e)}")
        
        # Clean up
        Lead.objects.filter(name__startswith="Hierarchy Test Lead").delete()
        
        logger.info("=== FORM SUBMISSION TEST COMPLETE ===")
        logger.info("If you're seeing leads go to manager when you select an agent,")
        logger.info("check the browser console and Django logs for DEBUG messages.")
        
    except Exception as e:
        logger.error(f"Error during form submission test: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    simulate_form_submission()
