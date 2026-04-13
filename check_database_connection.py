#!/usr/bin/env python
"""
Check database connection and table structure
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.db import connection
from django.contrib.auth import get_user_model

User = get_user_model()

print("=== Database Connection Check ===")

# Check database connection
try:
    with connection.cursor() as cursor:
        # Check all tables
        cursor.execute("SHOW TABLES")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables in database: {len(tables)}")
        
        # Look for user-related tables
        user_tables = [t for t in tables if 'user' in t.lower() or 'auth' in t.lower()]
        print(f"User-related tables: {user_tables}")
        
        # Check accounts_user table specifically
        if 'accounts_user' in tables:
            cursor.execute("SELECT COUNT(*) FROM accounts_user")
            user_count = cursor.fetchone()[0]
            print(f"Users in accounts_user table: {user_count}")
            
            if user_count > 0:
                cursor.execute("SELECT id, username, email FROM accounts_user LIMIT 10")
                users = cursor.fetchall()
                print("Sample users from accounts_user:")
                for user in users:
                    print(f"  ID: {user[0]}, Username: {user[1]}, Email: {user[2]}")
        
        # Check for leads table
        if 'dashboard_lead' in tables:
            cursor.execute("SELECT COUNT(*) FROM dashboard_lead")
            lead_count = cursor.fetchone()[0]
            print(f"Leads in dashboard_lead table: {lead_count}")
            
            if lead_count > 0:
                cursor.execute("SELECT assigned_user_id, COUNT(*) FROM dashboard_lead GROUP BY assigned_user_id")
                assignments = cursor.fetchall()
                print("Lead assignments:")
                for assign in assignments:
                    user_id = assign[0]
                    count = assign[1]
                    if user_id:
                        print(f"  User ID {user_id}: {count} leads")
                    else:
                        print(f"  Unassigned: {count} leads")

except Exception as e:
    print(f"Database connection error: {e}")

print("\n=== Django ORM Check ===")
try:
    print(f"User model: {User}")
    print(f"User table name: {User._meta.db_table}")
    print(f"Users via ORM: {User.objects.count()}")
    
    # Try raw SQL query
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM accounts_user")
        raw_count = cursor.fetchone()[0]
        print(f"Users via raw SQL: {raw_count}")
        
except Exception as e:
    print(f"ORM error: {e}")
