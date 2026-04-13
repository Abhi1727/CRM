#!/usr/bin/env python
"""
Check MySQL database for users after loading .env
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Now setup Django
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.db import connection
from django.contrib.auth import get_user_model
from dashboard.models import Lead

User = get_user_model()

print("=== MySQL Database Check ===")
print(f"DB_ENGINE: {os.getenv('DB_ENGINE')}")
print(f"DB_NAME: {os.getenv('DB_NAME')}")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"Database engine: {connection.vendor}")

# Check database connection
try:
    with connection.cursor() as cursor:
        # Test connection
        cursor.execute("SELECT 1")
        print("MySQL connection successful!")
        
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
                cursor.execute("SELECT id, username, email FROM accounts_user ORDER BY id LIMIT 20")
                users = cursor.fetchall()
                print("Sample users from accounts_user:")
                for user in users:
                    print(f"  ID: {user[0]}, Username: '{user[1]}', Email: '{user[2]}'")
        
        # Check for leads table
        if 'dashboard_lead' in tables:
            cursor.execute("SELECT COUNT(*) FROM dashboard_lead")
            lead_count = cursor.fetchone()[0]
            print(f"Leads in dashboard_lead table: {lead_count}")
            
            if lead_count > 0:
                cursor.execute("SELECT assigned_user_id, COUNT(*) FROM dashboard_lead GROUP BY assigned_user_id ORDER BY COUNT(*) DESC")
                assignments = cursor.fetchall()
                print("Lead assignments (top 10):")
                for assign in assignments[:10]:
                    user_id = assign[0]
                    count = assign[1]
                    if user_id:
                        print(f"  User ID {user_id}: {count} leads")
                    else:
                        print(f"  Unassigned: {count} leads")

except Exception as e:
    print(f"MySQL connection error: {e}")

print("\n=== Django ORM Check ===")
print(f"Users via ORM: {User.objects.count()}")
print(f"Leads via ORM: {Lead.objects.count()}")

# Search for target emails
target_emails = [
    "rajsinghbbn9555@gmail.com",
    "himanshu@skystates.us", 
    "greshi@skystates.us",
    "abhishekk@skystates.us",
    "kanhaiya@skystates.us",
    "naitikt34@gmail.com"
]

print("\n=== Target Agent Search ===")
found_agents = {}
for email in target_emails:
    try:
        user = User.objects.get(email=email)
        found_agents[email] = user
        print(f"FOUND: {user.username} (ID: {user.id}) - {email}")
    except User.DoesNotExist:
        print(f"NOT FOUND: {email}")

# Check for Ashutosh
try:
    ashutosh = User.objects.get(id=8)
    print(f"FOUND Ashutosh: {ashutosh.username} (ID: {ashutosh.id}) - {ashutosh.email}")
    
    # Check his leads
    lead_count = Lead.objects.filter(assigned_user=ashutosh).count()
    print(f"Leads assigned to Ashutosh: {lead_count}")
    
except User.DoesNotExist:
    print("Ashutosh Rai (ID: 8) not found")

print(f"\n=== Summary ===")
print(f"Target agents found: {len(found_agents)}")
print(f"Total users: {User.objects.count()}")
print(f"Total leads: {Lead.objects.count()}")
