#!/usr/bin/env python
"""
Check leads and assignments in the database
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

print("Checking leads assigned to each user:")
for user in User.objects.all():
    lead_count = Lead.objects.filter(assigned_user=user).count()
    print(f"User ID {user.id} ({user.username}): {lead_count} leads")

print(f"\nTotal leads in database: {Lead.objects.count()}")

# Check for Ashutosh Rai specifically
try:
    ashutosh = User.objects.get(id=8)
    ashutosh_leads = Lead.objects.filter(assigned_user=ashutosh)
    print(f"\nAshutosh Rai (ID: 8) has {ashutosh_leads.count()} leads")
    
    # Sample assignment history
    if ashutosh_leads.exists():
        sample_lead = ashutosh_leads.first()
        print(f"Sample lead assignment history: {sample_lead.assignment_history}")
except User.DoesNotExist:
    print("\nAshutosh Rai (ID: 8) not found in database")

# Check for unassigned leads
unassigned_count = Lead.objects.filter(assigned_user__isnull=True).count()
print(f"\nUnassigned leads: {unassigned_count}")
