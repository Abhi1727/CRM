#!/usr/bin/env python
"""
Debug script to reproduce the manual reassignment issue where leads go to manager instead of selected agent.
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
import logging

User = get_user_model()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def debug_manual_reassignment():
    """Debug the manual reassignment issue"""
    logger.info("=== DEBUGGING MANUAL REASSIGNMENT ISSUE ===")
    
    try:
        # Find users for testing
        admin_user = User.objects.filter(role='owner').first()
        if not admin_user:
            logger.error("No admin user found")
            return
        
        # Find an agent to delete
        agent_to_delete = User.objects.filter(role='agent').first()
        if not agent_to_delete:
            logger.error("No agent to delete found")
            return
        
        # Find another agent to receive leads
        target_agent = User.objects.filter(role='agent').exclude(id=agent_to_delete.id).first()
        if not target_agent:
            logger.error("No target agent found")
            return
        
        # Find the manager (this should NOT be used in manual reassignment)
        manager = agent_to_delete.manager
        if manager:
            logger.info(f"Agent {agent_to_delete.username} has manager: {manager.username}")
        else:
            logger.warning(f"Agent {agent_to_delete.username} has no manager")
        
        logger.info(f"Test setup:")
        logger.info(f"  Admin: {admin_user.username}")
        logger.info(f"  Agent to delete: {agent_to_delete.username}")
        logger.info(f"  Target agent: {target_agent.username}")
        logger.info(f"  Manager: {manager.username if manager else 'None'}")
        
        # Create test leads for the agent
        logger.info("Creating test leads...")
        leads_created = []
        for i in range(3):
            lead = Lead.objects.create(
                name=f"Debug Lead {i+1}",
                email=f"debug{i+1}@test.com",
                mobile=f"123456789{i}",
                country="India",
                course_name="Test Course",
                status='lead',
                assigned_user=agent_to_delete,
                assigned_by=admin_user,
                assigned_at=django.utils.timezone.now(),
                exp_revenue=str(1000.0 * (i + 1))
            )
            leads_created.append(lead)
        
        logger.info(f"Created {len(leads_created)} test leads for {agent_to_delete.username}")
        
        # Test manual reassignment
        logger.info("=== TESTING MANUAL REASSIGNMENT ===")
        reassigner = LeadReassigner()
        
        # This should reassign to target_agent, NOT manager
        logger.info(f"Calling reassign_user_leads_to_specific with target: {target_agent.username}")
        results = reassigner.reassign_user_leads_to_specific(
            agent_to_delete, target_agent, admin_user
        )
        
        logger.info(f"Manual reassignment results: {results}")
        
        # Verify where the leads actually went
        logger.info("=== VERIFYING RESULTS ===")
        
        # Check leads assigned to target agent
        target_agent_leads = Lead.objects.filter(assigned_user=target_agent, name__startswith="Debug Lead")
        logger.info(f"Leads assigned to target agent ({target_agent.username}): {target_agent_leads.count()}")
        for lead in target_agent_leads:
            logger.info(f"  - {lead.name} (ID: {lead.id_lead})")
        
        # Check leads assigned to manager (should be 0)
        if manager:
            manager_leads = Lead.objects.filter(assigned_user=manager, name__startswith="Debug Lead")
            logger.info(f"Leads assigned to manager ({manager.username}): {manager_leads.count()}")
            for lead in manager_leads:
                logger.warning(f"  - {lead.name} (ID: {lead.id_lead}) - THIS SHOULD NOT HAPPEN!")
        
        # Check leads still with deleted agent (should be 0)
        remaining_leads = Lead.objects.filter(assigned_user=agent_to_delete, name__startswith="Debug Lead")
        logger.info(f"Leads still with deleted agent ({agent_to_delete.username}): {remaining_leads.count()}")
        for lead in remaining_leads:
            logger.warning(f"  - {lead.name} (ID: {lead.id_lead}) - THIS SHOULD NOT HAPPEN!")
        
        # Check transfer records
        logger.info("=== CHECKING TRANSFER RECORDS ===")
        for lead in leads_created:
            lead.refresh_from_db()
            logger.info(f"Lead {lead.name}:")
            logger.info(f"  - Current assigned_user: {lead.assigned_user.username if lead.assigned_user else 'None'}")
            logger.info(f"  - transfer_from: {lead.transfer_from}")
            logger.info(f"  - transfer_by: {lead.transfer_by}")
            logger.info(f"  - transfer_date: {lead.transfer_date}")
        
        # Clean up test data
        logger.info("Cleaning up test data...")
        Lead.objects.filter(name__startswith="Debug Lead").delete()
        
        logger.info("=== DEBUGGING COMPLETE ===")
        
    except Exception as e:
        logger.error(f"Error during debugging: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    debug_manual_reassignment()
