#!/usr/bin/env python
"""
Check SQLite database for users
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
from dashboard.models import Lead

User = get_user_model()

print("=== SQLite Database Check ===")

# Check database engine
print(f"Database engine: {connection.vendor}")
print(f"Database name: {connection.settings_dict['NAME']}")

# Check all tables using SQLite syntax
try:
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables in database: {len(tables)}")
        print(f"Table names: {tables}")
        
        # Check accounts_user table
        if 'accounts_user' in tables:
            cursor.execute("SELECT COUNT(*) FROM accounts_user")
            user_count = cursor.fetchone()[0]
            print(f"Users in accounts_user: {user_count}")
            
            if user_count > 0:
                cursor.execute("SELECT id, username, email FROM accounts_user")
                users = cursor.fetchall()
                print("All users:")
                for user in users:
                    print(f"  ID: {user[0]}, Username: '{user[1]}', Email: '{user[2]}'")
        
        # Check dashboard_lead table
        if 'dashboard_lead' in tables:
            cursor.execute("SELECT COUNT(*) FROM dashboard_lead")
            lead_count = cursor.fetchone()[0]
            print(f"Leads in dashboard_lead: {lead_count}")
            
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
    print(f"Database error: {e}")

print("\n=== Django ORM Check ===")
print(f"Users via ORM: {User.objects.count()}")
print(f"Leads via ORM: {Lead.objects.count()}")

# Search for target emails directly
target_emails = [
    "rajsinghbbn9555@gmail.com",
    "himanshu@skystates.us", 
    "greshi@skystates.us",
    "abhishekk@skystates.us",
    "kanhaiya@skystates.us",
    "naitikt34@gmail.com"
]

print("\n=== Target Agent Search ===")
for email in target_emails:
    try:
        user = User.objects.get(email=email)
        print(f"FOUND: {user.username} (ID: {user.id}) - {email}")
    except User.DoesNotExist:
        print(f"NOT FOUND: {email}")

# Check for Ashutosh
try:
    ashutosh = User.objects.get(id=8)
    print(f"FOUND Ashutosh: {ashutosh.username} (ID: {ashutosh.id})")
except User.DoesNotExist:
    print("Ashutosh Rai (ID: 8) not found")
