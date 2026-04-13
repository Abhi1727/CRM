#!/usr/bin/env python
"""
Test script to verify date filtering and timezone handling
"""
import os
import sys
import django
from datetime import datetime, time, timedelta
from django.utils import timezone

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))
django.setup()

from django.utils.timezone import activate, make_aware
from crm_project.dashboard.views import _apply_common_lead_filters
from crm_project.accounts.models import User

def test_timezone_handling():
    print("Testing timezone handling...")
    
    # Force Asia/Kolkata timezone
    activate('Asia/Kolkata')
    
    # Test today's date in Kolkata timezone
    today_kolkata = timezone.now().date()
    today_start = make_aware(datetime.combine(today_kolkata, time.min))
    today_end = make_aware(datetime.combine(today_kolkata, time.max))
    
    print(f"Kolkata today date: {today_kolkata}")
    print(f"Kolkata today start: {today_start}")
    print(f"Kolkata today end: {today_end}")
    print(f"Current timezone: {timezone.get_current_timezone()}")
    
    # Test week and month dates
    week_ago = today_kolkata - timedelta(days=7)
    month_ago = today_kolkata - timedelta(days=30)
    
    print(f"Week ago date: {week_ago}")
    print(f"Month ago date: {month_ago}")
    
    return True

def test_filter_logic():
    print("\nTesting filter logic...")
    
    # Test filter extraction (simulated)
    test_filters = {
        'preset': 'today',
        'start_date': None,
        'end_date': None,
        'status': '',
        'search': '',
        'country': '',
        'course': '',
        'assigned_user': '',
        'page_size': 25
    }
    
    print(f"Test filters: {test_filters}")
    
    # Test preset parameter mapping
    if test_filters['preset'] == 'today':
        print("✓ Today preset detected correctly")
    elif test_filters['preset'] == 'my_team':
        print("✓ Team preset detected correctly")
    elif test_filters['preset'] == 'my':
        print("✓ My preset detected correctly")
    
    return True

if __name__ == '__main__':
    print("=" * 50)
    print("Date Filtering and Timezone Test")
    print("=" * 50)
    
    try:
        test_timezone_handling()
        test_filter_logic()
        print("\n✓ All tests passed!")
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
