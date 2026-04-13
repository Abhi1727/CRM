#!/usr/bin/env python
"""
Check users in the database
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

print("All users in database:")
for user in User.objects.all():
    role = getattr(user, "role", "N/A")
    print(f"ID: {user.id}, Username: '{user.username}', Full Name: '{user.get_full_name()}', Email: '{user.email}', Role: '{role}'")

print(f"\nTotal users: {User.objects.count()}")

# Search for users with the target emails
target_emails = [
    "rajsinghbbn9555@gmail.com",
    "himanshu@skystates.us", 
    "greshi@skystates.us",
    "abhishekk@skystates.us",
    "kanhaiya@skystates.us",
    "naitikt34@gmail.com"
]

print("\nSearching for target agents:")
for email in target_emails:
    try:
        user = User.objects.get(email=email)
        print(f"Found: ID {user.id}, Username: '{user.username}', Email: '{user.email}'")
    except User.DoesNotExist:
        print(f"Not found: {email}")

# Also check for Ashutosh Rai
try:
    ashutosh = User.objects.get(id=8)
    print(f"\nAshutosh Rai found: ID {ashutosh.id}, Username: '{ashutosh.username}', Email: '{ashutosh.email}'")
except User.DoesNotExist:
    print("\nAshutosh Rai (ID: 8) not found")
