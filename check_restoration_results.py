#!/usr/bin/env python
"""
Check restoration results
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadHistory, LeadActivity

User = get_user_model()

print("=== Restoration Results Check ===")

# Check Ashutosh's current leads
try:
    ashutosh = User.objects.get(id=8)
    ashutosh_leads = Lead.objects.filter(assigned_user=ashutosh).count()
    print(f"Ashutosh Rai now has: {ashutosh_leads} leads")
except User.DoesNotExist:
    print("Ashutosh Rai not found")

# Check target agents' leads
target_agents_info = [
    ("Raj", 18, "rajsinghbbn9555@gmail.com"),
    ("Himanshu", 10, "himanshu@skystates.us"),
    ("greshi", 13, "greshi@skystates.us"),
    ("Abhi", 11, "abhishekk@skystates.us"),
    ("Kanha", 16, "kanhaiya@skystates.us"),
    ("naitik", 17, "naitikt34@gmail.com")
]

print("\n=== Target Agents' Lead Counts ===")
total_restored = 0
for name, user_id, email in target_agents_info:
    try:
        agent = User.objects.get(id=user_id)
        lead_count = Lead.objects.filter(assigned_user=agent).count()
        total_restored += lead_count
        print(f"{name} (ID: {user_id}): {lead_count} leads")
    except User.DoesNotExist:
        print(f"{name} (ID: {user_id}): Not found")

# Check unassigned leads
unassigned_count = Lead.objects.filter(assigned_user__isnull=True).count()
print(f"\nUnassigned leads: {unassigned_count}")

# Total verification
total_leads = Lead.objects.count()
print(f"\nTotal leads in database: {total_leads}")
print(f"Accounted for: {ashutosh_leads + total_restored + unassigned_count}")

# Check recent audit trail
print("\n=== Recent Audit Trail ===")
recent_history = LeadHistory.objects.filter(
    created_at__gte='2026-04-11 01:50:00'
).order_by('-created_at')[:10]

for history in recent_history:
    print(f"{history.created_at}: {history.action} - {history.field_name} from {history.old_value} to {history.new_value}")

recent_activity = LeadActivity.objects.filter(
    created_at__gte='2026-04-11 01:50:00'
).order_by('-created_at')[:10]

for activity in recent_activity:
    print(f"{activity.created_at}: {activity.activity_type} - {activity.description}")

print(f"\n=== Summary ===")
print(f"Leads restored to agents: {total_restored}")
print(f"Leads unassigned: {unassigned_count}")
print(f"Leads remaining with Ashutosh: {ashutosh_leads}")
print(f"Expected: 600 restored, 1288 unassigned, 0 with Ashutosh")
print(f"Actual: {total_restored} restored, {unassigned_count} unassigned, {ashutosh_leads} with Ashutosh")
