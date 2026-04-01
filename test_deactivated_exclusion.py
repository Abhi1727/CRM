#!/usr/bin/env python
"""
Test script to verify that deactivated users are excluded from dropdowns.
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
from django.test import RequestFactory
from accounts.views import get_users_by_role, assign_lead, bulk_assign_leads
import logging

User = get_user_model()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_deactivated_user_exclusion():
    """Test that deactivated users are excluded from dropdowns"""
    logger.info("=== TESTING DEACTIVATED USER EXCLUSION ===")
    
    try:
        # Find users for testing
        admin_user = User.objects.filter(role='owner').first()
        if not admin_user:
            logger.error("No admin user found")
            return
        
        # Find an active agent
        active_agent = User.objects.filter(role='agent', is_active=True, account_status='active').first()
        if not active_agent:
            logger.error("No active agent found")
            return
        
        # Create a deactivated agent for testing
        deactivated_agent = User.objects.filter(role='agent').first()
        if deactivated_agent == active_agent:
            deactivated_agent = User.objects.filter(role='agent').exclude(id=active_agent.id).first()
        
        if not deactivated_agent:
            logger.error("No second agent found for deactivation test")
            return
        
        # Deactivate the agent
        logger.info(f"Deactivating user: {deactivated_agent.username}")
        deactivated_agent.is_active = False
        deactivated_agent.account_status = 'inactive'
        deactivated_agent.save()
        
        logger.info(f"Test setup:")
        logger.info(f"  Admin: {admin_user.username}")
        logger.info(f"  Active agent: {active_agent.username}")
        logger.info(f"  Deactivated agent: {deactivated_agent.username}")
        
        # Test 1: get_users_by_role API
        logger.info("=== TEST 1: get_users_by_role API ===")
        factory = RequestFactory()
        
        # Test API call for agents
        request = factory.get('/accounts/get-users-by-role/', {
            'role': 'agent'
        })
        request.user = admin_user
        request.META['HTTP_X_REQUESTED_WITH'] = 'XMLHttpRequest'
        
        # Mock hierarchy context
        request.hierarchy_context = {
            'accessible_users': admin_user.get_accessible_users(),
            'accessible_leads': admin_user.get_accessible_leads_queryset(),
            'hierarchy_level': admin_user.get_hierarchy_level(),
        }
        
        try:
            response = get_users_by_role(request)
            import json
            response_data = json.loads(response.content)
            
            users = response_data.get('users', [])
            logger.info(f"API returned {len(users)} users:")
            
            found_active = False
            found_deactivated = False
            
            for user in users:
                logger.info(f"  - {user['full_name']} (ID: {user['id']}, Role: {user['role']})")
                if user['id'] == active_agent.id:
                    found_active = True
                    logger.info(f"    ✅ Active agent {active_agent.username} found in API")
                if user['id'] == deactivated_agent.id:
                    found_deactivated = True
                    logger.warning(f"    ❌ Deactivated agent {deactivated_agent.username} found in API (should be excluded)")
            
            if found_active and not found_deactivated:
                logger.info("✅ API correctly excludes deactivated users")
            elif found_deactivated:
                logger.error("❌ API incorrectly includes deactivated users")
            else:
                logger.warning("⚠️ Active agent not found in API")
                
        except Exception as e:
            logger.error(f"Error testing API: {str(e)}")
        
        # Test 2: assign_lead view
        logger.info("=== TEST 2: assign_lead view ===")
        try:
            request = factory.get('/accounts/assign-lead/')
            request.user = admin_user
            request.hierarchy_context = {
                'accessible_users': admin_user.get_accessible_users(),
                'accessible_leads': admin_user.get_accessible_leads_queryset(),
                'hierarchy_level': admin_user.get_hierarchy_level(),
            }
            
            # This should not include deactivated users in the context
            response = assign_lead(request)
            
            # Check if deactivated user is in the context users
            # Note: We can't easily check the context from here, but the view should filter
            
            logger.info("✅ assign_lead view processed (check manually for deactivated user exclusion)")
            
        except Exception as e:
            logger.error(f"Error testing assign_lead view: {str(e)}")
        
        # Test 3: bulk_assign_leads view
        logger.info("=== TEST 3: bulk_assign_leads view ===")
        try:
            request = factory.get('/accounts/bulk-assign/')
            request.user = admin_user
            request.hierarchy_context = {
                'accessible_users': admin_user.get_accessible_users(),
                'accessible_leads': admin_user.get_accessible_leads_queryset(),
                'hierarchy_level': admin_user.get_hierarchy_level(),
            }
            
            response = bulk_assign_leads(request)
            
            logger.info("✅ bulk_assign_leads view processed (check manually for deactivated user exclusion)")
            
        except Exception as e:
            logger.error(f"Error testing bulk_assign_leads view: {str(e)}")
        
        # Restore the deactivated agent
        logger.info(f"Restoring user: {deactivated_agent.username}")
        deactivated_agent.is_active = True
        deactivated_agent.account_status = 'active'
        deactivated_agent.save()
        
        logger.info("=== DEACTIVATED USER EXCLUSION TEST COMPLETE ===")
        logger.info("Manual verification steps:")
        logger.info("1. Go to user deletion page and check dropdown")
        logger.info("2. Go to bulk assignment page and check dropdown")
        logger.info("3. Go to lead assignment page and check dropdown")
        logger.info("4. Deactivated users should NOT appear in any dropdown")
        
    except Exception as e:
        logger.error(f"Error during test: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == '__main__':
    test_deactivated_user_exclusion()
