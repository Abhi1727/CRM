#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from accounts.models import User
from dashboard.models import Lead
from django.utils import timezone
import datetime

def test_all_presets():
    print("=== Testing All Preset Functionality ===")
    
    # Test with owner user (should have access to all leads)
    owner = User.objects.filter(role='owner').first()
    if not owner:
        print("No owner user found!")
        return
    
    print(f"Testing with owner: {owner.username} (role: {owner.role})")
    
    # Get base queryset
    accessible_leads = owner.get_accessible_leads_queryset()
    print(f"Total accessible leads: {accessible_leads.count()}")
    
    # Test each preset
    print("\n--- Testing Presets ---")
    
    # Test 'my' preset
    my_leads = accessible_leads.filter(assigned_user=owner)
    print(f"My leads: {my_leads.count()}")
    
    # Test 'my_team' preset for owner
    accessible_users = owner.get_accessible_users()
    team_leads = accessible_leads.filter(assigned_user__in=accessible_users)
    print(f"Team leads: {team_leads.count()}")
    
    # Test 'today' preset
    today = timezone.now().date()
    today_start = timezone.make_aware(datetime.datetime.combine(today, datetime.time.min))
    today_end = timezone.make_aware(datetime.datetime.combine(today, datetime.time.max))
    today_leads = accessible_leads.filter(created_at__gte=today_start, created_at__lte=today_end)
    print(f"Today leads: {today_leads.count()}")
    
    # Test 'week' preset
    week_ago_date = timezone.now().date() - timezone.timedelta(days=7)
    week_start = timezone.make_aware(datetime.datetime.combine(week_ago_date, datetime.time.min))
    week_leads = accessible_leads.filter(created_at__gte=week_start)
    print(f"Week leads: {week_leads.count()}")
    
    # Test 'month' preset
    month_ago_date = timezone.now().date() - timezone.timedelta(days=30)
    month_start = timezone.make_aware(datetime.datetime.combine(month_ago_date, datetime.time.min))
    month_leads = accessible_leads.filter(created_at__gte=month_start)
    print(f"Month leads: {month_leads.count()}")
    
    # Test date range (like the original error)
    april9_start = timezone.make_aware(datetime.datetime.combine(datetime.date(2026, 4, 9), datetime.time.min))
    april9_end = timezone.make_aware(datetime.datetime.combine(datetime.date(2026, 4, 9), datetime.time.max))
    april9_leads = accessible_leads.filter(created_at__gte=april9_start, created_at__lte=april9_end)
    print(f"April 9 leads: {april9_leads.count()}")
    
    print("\n=== All Preset Tests Completed Successfully! ===")

if __name__ == "__main__":
    test_all_presets()
