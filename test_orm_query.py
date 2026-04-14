#!/usr/bin/env python3
"""
Test the ORM query used in bulk assignment
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, '/root/CRM/crm_project')

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')

try:
    django.setup()
    
    from dashboard.models import Lead
    
    print("Testing ORM query...")
    
    # Test the query from bulk assignment processor
    leads = Lead.objects.filter(
        id_lead__in=[1, 2, 3],  # Test with some sample IDs
        company_id=1,
        deleted=False
    ).select_related('assigned_user').values(
        'id_lead', 'assigned_user_id', 'assigned_user__role'
    )
    
    print("Query executed successfully!")
    
    # Show the results
    for lead in leads:
        print(f"Lead ID: {lead['id_lead']}, Assigned User ID: {lead['assigned_user_id']}, Role: {lead['assigned_user__role']}")
    
    print("ORM query test completed successfully!")
    
except Exception as e:
    print(f"Error in ORM query: {e}")
    import traceback
    traceback.print_exc()
