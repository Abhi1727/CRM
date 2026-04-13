#!/usr/bin/env python
"""
Check model structures
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

from dashboard.models import Lead, LeadHistory, LeadActivity, LeadOperationLog

print("=== Model Structure Check ===")

# Check Lead model
print("\nLead model fields:")
for field in Lead._meta.fields:
    print(f"  {field.name}: {field.__class__.__name__}")

# Check LeadHistory model
print("\nLeadHistory model fields:")
for field in LeadHistory._meta.fields:
    print(f"  {field.name}: {field.__class__.__name__}")

# Check LeadActivity model  
print("\nLeadActivity model fields:")
for field in LeadActivity._meta.fields:
    print(f"  {field.name}: {field.__class__.__name__}")

# Check LeadOperationLog model
print("\nLeadOperationLog model fields:")
for field in LeadOperationLog._meta.fields:
    print(f"  {field.name}: {field.__class__.__name__}")

# Check sample lead assignment history
from django.contrib.auth import get_user_model
User = get_user_model()

try:
    ashutosh = User.objects.get(id=8)
    sample_lead = Lead.objects.filter(assigned_user=ashutosh).first()
    if sample_lead:
        print(f"\nSample lead assignment history: {sample_lead.assignment_history}")
        print(f"Sample lead assigned_at: {sample_lead.assigned_at}")
        print(f"Sample lead assigned_by: {sample_lead.assigned_by}")
except Exception as e:
    print(f"Error checking sample lead: {e}")
