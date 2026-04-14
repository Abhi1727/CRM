#!/usr/bin/env python3
"""
Test script to verify bulk assignment field fix
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, '/root/CRM/crm_project')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
django.setup()

from dashboard.bulk_assignment_processor import BulkAssignmentProcessor
from dashboard.models import Lead, BulkOperation, User
from django.contrib.auth import get_user_model

def test_bulk_assignment():
    """Test the bulk assignment processor with fixed field references"""
    print("Testing bulk assignment processor...")
    
    try:
        # Get test users
        User = get_user_model()
        test_users = User.objects.filter(is_active=True)[:2]
        
        if len(test_users) < 2:
            print("Need at least 2 active users for testing")
            return
        
        assigned_user = test_users[0]
        assigned_by = test_users[1]
        
        print(f"Testing assignment from {assigned_by.username} to {assigned_user.username}")
        
        # Get some test leads
        test_leads = Lead.objects.filter(deleted=False)[:5]
        lead_ids = [lead.id_lead for lead in test_leads]
        
        if not lead_ids:
            print("No leads found for testing")
            return
        
        print(f"Testing with {len(lead_ids)} leads: {lead_ids}")
        
        # Create a test bulk operation
        operation = BulkOperation.objects.create(
            operation_type='bulk_assignment',
            user=assigned_by,
            company_id=assigned_by.company_id or 1,
            total_leads=len(lead_ids),
            status='pending'
        )
        
        print(f"Created bulk operation: {operation.id}")
        
        # Test the processor
        processor = BulkAssignmentProcessor(
            operation_id=operation.id,
            lead_ids=lead_ids,
            assigned_user_id=assigned_user.id,
            assigned_by_id=assigned_by.id,
            company_id=assigned_by.company_id or 1
        )
        
        print("Starting bulk assignment...")
        result = processor.execute()
        
        print("Bulk assignment completed successfully!")
        print(f"Result: {result}")
        
        # Clean up
        operation.delete()
        
    except Exception as e:
        print(f"Error during bulk assignment test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_bulk_assignment()
