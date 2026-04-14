#!/usr/bin/env python3
"""
Check database field names for leads table
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
    
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("DESCRIBE leads")
        columns = cursor.fetchall()
        
        print("Lead table columns:")
        for col in columns:
            field_name = col[0]
            if 'assigned' in field_name or 'user' in field_name:
                print(f"  {field_name} - {col[1]} - {col[2]}")
        
        # Check specific fields we're using in queries
        required_fields = ['assigned_user_id', 'assigned_by_id', 'assigned_at', 'transfer_from', 'transfer_by', 'transfer_date', 'assignment_history']
        
        print("\nChecking required fields:")
        existing_columns = [col[0] for col in columns]
        
        for field in required_fields:
            if field in existing_columns:
                print(f"  ✓ {field}")
            else:
                print(f"  ✗ {field} - MISSING")
                
        # Also check for the foreign key field names
        fk_fields = ['assigned_user', 'assigned_by']
        print("\nChecking foreign key field names:")
        for field in fk_fields:
            if field in existing_columns:
                print(f"  ✓ {field}")
            else:
                print(f"  ✗ {field} - MISSING")
                
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
