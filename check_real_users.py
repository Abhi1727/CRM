#!/usr/bin/env python
"""
Check real users in the production database
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead

User = get_user_model()

print("=== Checking Real Database Users ===")
print(f"Database: MySQL - u571325480_new_crm")
print(f"Total users: {User.objects.count()}")

# Check all users
print("\nAll users in database:")
for user in User.objects.all().order_by('id'):
    role = getattr(user, "role", "N/A")
    print(f"ID: {user.id}, Username: '{user.username}', Email: '{user.email}', Role: '{role}'")

# Search for target agents by email
target_emails = [
    "rajsinghbbn9555@gmail.com",
    "himanshu@skystates.us", 
    "greshi@skystates.us",
    "abhishekk@skystates.us",
    "kanhaiya@skystates.us",
    "naitikt34@gmail.com"
]

print("\n=== Searching for Target Agents ===")
found_agents = {}
for email in target_emails:
    try:
        user = User.objects.get(email=email)
        found_agents[email] = user
        print(f"FOUND: ID {user.id}, Username: '{user.username}', Email: '{user.email}'")
    except User.DoesNotExist:
        print(f"NOT FOUND: {email}")

# Check for Ashutosh Rai
print("\n=== Checking for Ashutosh Rai ===")
try:
    ashutosh = User.objects.get(id=8)
    print(f"FOUND: ID {ashutosh.id}, Username: '{ashutosh.username}', Email: '{ashutosh.email}'")
    
    # Check his leads
    lead_count = Lead.objects.filter(assigned_user=ashutosh).count()
    print(f"Leads assigned to Ashutosh: {lead_count}")
    
except User.DoesNotExist:
    print("NOT FOUND: Ashutosh Rai (ID: 8)")

# Also search by username variations
print("\n=== Searching by Username Variations ===")
username_variations = [
    "rajsinghbbn9555",
    "himanshu", 
    "greshi",
    "abhishek",
    "kanhaiya",
    "naitik",
    "ashutosh"
]

for username in username_variations:
    users = User.objects.filter(username__icontains=username)
    if users.exists():
        for user in users:
            print(f"FOUND by username '{username}': ID {user.id}, Username: '{user.username}', Email: '{user.email}'")
    else:
        print(f"NOT FOUND by username '{username}'")

print(f"\n=== Summary ===")
print(f"Target agents found: {len(found_agents)}")
print(f"Total leads in database: {Lead.objects.count()}")
