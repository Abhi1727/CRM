#!/usr/bin/env python
"""
Manual Reassignment Verification Script

This script helps verify that the manual reassignment functionality
is working correctly in the CRM system.

Usage:
    python verify_manual_reassignment.py [--test-data]

Options:
    --test-data    Create test data for verification
"""

import os
import sys
import django
import argparse
from datetime import datetime

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadActivity
from services.lead_reassigner import LeadReassigner
import logging

User = get_user_model()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_data():
    """Create test data for manual reassignment verification"""
    logger.info("Creating test data...")
    
    try:
        # Get or create test company (assuming company exists)
        # For this test, we'll work with existing users
        
        # Find users for testing
        admin_user = User.objects.filter(role='owner').first()
        if not admin_user:
            logger.error("No admin user found. Please create an owner user first.")
            return False
            
        agent_to_delete = User.objects.filter(role='agent').first()
        if not agent_to_delete:
            logger.error("No agent user found. Please create an agent user first.")
            return False
            
        target_user = User.objects.filter(role='agent').exclude(id=agent_to_delete.id).first()
        if not target_user:
            target_user = User.objects.filter(role='team_lead').first()
        if not target_user:
            logger.error("No target user found for reassignment.")
            return False
        
        logger.info(f"Test users: Admin={admin_user.username}, Delete={agent_to_delete.username}, Target={target_user.username}")
        
        # Create test leads for the agent to be deleted
        leads_created = 0
        for i in range(5):
            lead = Lead.objects.create(
                name=f"Test Lead {i+1} for {agent_to_delete.username}",
                email=f"test{i+1}@example.com",
                mobile=f"123456789{i}",
                country="India",
                course_name="Test Course",
                status='lead',  # Active lead
                assigned_user=agent_to_delete,
                assigned_by=admin_user,
                assigned_at=datetime.now(),
                exp_revenue=str(1000.0 * (i + 1))
            )
            leads_created += 1
        
        # Create some converted leads
        for i in range(2):
            lead = Lead.objects.create(
                name=f"Converted Lead {i+1} for {agent_to_delete.username}",
                email=f"converted{i+1}@example.com",
                mobile=f"987654321{i}",
                country="India",
                course_name="Test Course",
                status='sale_done',  # Converted lead
                assigned_user=agent_to_delete,
                assigned_by=admin_user,
                assigned_at=datetime.now(),
                exp_revenue=str(5000.0 * (i + 1))
            )
            leads_created += 1
        
        logger.info(f"Created {leads_created} test leads for user {agent_to_delete.username}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating test data: {str(e)}")
        return False

def verify_manual_reassignment():
    """Verify the manual reassignment functionality"""
    logger.info("Starting manual reassignment verification...")
    
    try:
        # Find test users
        admin_user = User.objects.filter(role='owner').first()
        agent_to_delete = User.objects.filter(role='agent').first()
        target_user = User.objects.filter(role='agent').exclude(id=agent_to_delete.id).first()
        
        if not all([admin_user, agent_to_delete, target_user]):
            logger.error("Missing test users for verification")
            return False
        
        logger.info(f"Testing with: Admin={admin_user.username}, Delete={agent_to_delete.username}, Target={target_user.username}")
        
        # Count leads before reassignment
        leads_before = Lead.objects.filter(assigned_user=agent_to_delete).count()
        target_leads_before = Lead.objects.filter(assigned_user=target_user).count()
        
        logger.info(f"Leads before: {agent_to_delete.username} has {leads_before}, {target_user.username} has {target_leads_before}")
        
        # Initialize reassigner
        reassigner = LeadReassigner()
        
        # Get reassignment summary
        summary = reassigner.get_reassignment_summary(agent_to_delete)
        logger.info(f"Reassignment summary: {summary}")
        
        # Perform manual reassignment
        logger.info("Performing manual reassignment...")
        results = reassigner.reassign_user_leads_to_specific(agent_to_delete, target_user, admin_user)
        
        logger.info(f"Manual reassignment results: {results}")
        
        # Verify results
        leads_after = Lead.objects.filter(assigned_user=agent_to_delete).count()
        target_leads_after = Lead.objects.filter(assigned_user=target_user).count()
        
        # Count converted leads that should remain with deleted user
        converted_leads_preserved = Lead.objects.filter(assigned_user=agent_to_delete, status='sale_done').count()
        active_leads_remaining = Lead.objects.filter(assigned_user=agent_to_delete).exclude(status='sale_done').count()
        
        logger.info(f"Leads after: {agent_to_delete.username} has {leads_after} ({converted_leads_preserved} converted preserved, {active_leads_remaining} active remaining), {target_user.username} has {target_leads_after}")
        
        # Check individual leads
        reassigned_leads = Lead.objects.filter(assigned_user=target_user, transfer_from=agent_to_delete.get_full_name() or agent_to_delete.username)
        logger.info(f"Found {reassigned_leads.count()} leads with correct transfer records")
        
        # Check activity logs
        activities = LeadActivity.objects.filter(activity_type='admin_manual_reassignment')
        logger.info(f"Found {activities.count()} manual reassignment activity logs")
        
        # Verification checks
        success = True
        
        if results['active_leads_reassigned'] == 0:
            logger.error("No active leads were reassigned")
            success = False
        
        # The deleted user should only have converted leads remaining
        if active_leads_remaining != 0:
            logger.error(f"Agent still has {active_leads_remaining} active leads after reassignment")
            success = False
        
        if converted_leads_preserved != results['converted_leads_preserved']:
            logger.error(f"Expected {results['converted_leads_preserved']} converted leads preserved, found {converted_leads_preserved}")
            success = False
        
        if target_leads_after <= target_leads_before:
            logger.error("Target user didn't receive additional leads")
            success = False
        
        if reassigned_leads.count() == 0:
            logger.error("No transfer records found")
            success = False
        
        if activities.count() == 0:
            logger.error("No activity logs created")
            success = False
        
        if success:
            logger.info("✅ Manual reassignment verification PASSED")
            logger.info(f"   - {results['active_leads_reassigned']} leads reassigned")
            logger.info(f"   - {results['converted_leads_preserved']} converted leads preserved")
            logger.info(f"   - {results['total_revenue_preserved']} revenue preserved")
            logger.info(f"   - {reassigned_leads.count()} transfer records created")
            logger.info(f"   - {activities.count()} activity logs created")
        else:
            logger.error("❌ Manual reassignment verification FAILED")
        
        return success
        
    except Exception as e:
        logger.error(f"Error during verification: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False

def cleanup_test_data():
    """Clean up test data"""
    logger.info("Cleaning up test data...")
    
    try:
        # Delete test leads
        test_leads = Lead.objects.filter(name__startswith="Test Lead")
        test_leads_count = test_leads.count()
        test_leads.delete()
        
        converted_leads = Lead.objects.filter(name__startswith="Converted Lead")
        converted_leads_count = converted_leads.count()
        converted_leads.delete()
        
        logger.info(f"Deleted {test_leads_count} test leads and {converted_leads_count} converted leads")
        
    except Exception as e:
        logger.error(f"Error cleaning up test data: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Verify manual reassignment functionality')
    parser.add_argument('--test-data', action='store_true', help='Create test data')
    parser.add_argument('--cleanup', action='store_true', help='Clean up test data')
    parser.add_argument('--verify', action='store_true', help='Run verification')
    
    args = parser.parse_args()
    
    if args.test_data:
        success = create_test_data()
        sys.exit(0 if success else 1)
    
    if args.verify:
        success = verify_manual_reassignment()
        sys.exit(0 if success else 1)
    
    if args.cleanup:
        cleanup_test_data()
        sys.exit(0)
    
    # Default: run full test
    logger.info("Running complete manual reassignment verification...")
    
    # Clean up any existing test data
    cleanup_test_data()
    
    # Create test data
    if not create_test_data():
        logger.error("Failed to create test data")
        sys.exit(1)
    
    # Run verification
    success = verify_manual_reassignment()
    
    # Clean up
    cleanup_test_data()
    
    if success:
        logger.info("🎉 Manual reassignment verification completed successfully!")
    else:
        logger.error("💥 Manual reassignment verification failed!")
    
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()
