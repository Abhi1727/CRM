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

def test_user_hierarchy():
    print("=== Testing User Hierarchy and Presets ===")
    sys.stdout.flush()
    
    # Test with a team lead user
    team_lead = User.objects.filter(role='team_lead').first()
    print(f"Team lead found: {team_lead is not None}")
    sys.stdout.flush()
    
    if team_lead:
        print(f"\nTesting with team lead: {team_lead.username} (role: {team_lead.role})")
        sys.stdout.flush()
        
        # Test accessible users
        accessible_users = team_lead.get_accessible_users()
        print(f"Accessible users count: {accessible_users.count()}")
        print(f"Accessible users: {list(accessible_users.values_list('username', flat=True))}")
        sys.stdout.flush()
        
        # Test accessible leads
        accessible_leads = team_lead.get_accessible_leads_queryset()
        print(f"Accessible leads count: {accessible_leads.count()}")
        sys.stdout.flush()
        
        # Test specific preset scenarios
        print("\n--- Testing preset scenarios ---")
        sys.stdout.flush()
        
        # Test 'my' preset
        my_leads = accessible_leads.filter(assigned_user=team_lead)
        print(f"My leads count: {my_leads.count()}")
        sys.stdout.flush()
        
        # Test 'my_team' preset for team lead
        team_leads = accessible_leads.filter(assigned_user__in=accessible_users)
        print(f"Team leads count: {team_leads.count()}")
        sys.stdout.flush()
        
        # Test date-based presets
        today = timezone.now().date()
        today_leads = accessible_leads.filter(created_at__date=today)
        print(f"Today leads count: {today_leads.count()}")
        sys.stdout.flush()
        
        week_ago = timezone.now().date() - timezone.timedelta(days=7)
        week_leads = accessible_leads.filter(created_at__date__gte=week_ago)
        print(f"Week leads count: {week_leads.count()}")
        sys.stdout.flush()
        
        month_ago = timezone.now().date() - timezone.timedelta(days=30)
        month_leads = accessible_leads.filter(created_at__date__gte=month_ago)
        print(f"Month leads count: {month_leads.count()}")
        sys.stdout.flush()
    else:
        print("No team lead found in database!")
        sys.stdout.flush()
    
    # Test with an agent user
    agent = User.objects.filter(role='agent').first()
    print(f"\nAgent found: {agent is not None}")
    sys.stdout.flush()
    
    if agent:
        print(f"\nTesting with agent: {agent.username} (role: {agent.role})")
        sys.stdout.flush()
        
        # Test accessible users
        accessible_users = agent.get_accessible_users()
        print(f"Accessible users count: {accessible_users.count()}")
        sys.stdout.flush()
        
        # Test accessible leads
        accessible_leads = agent.get_accessible_leads_queryset()
        print(f"Accessible leads count: {accessible_leads.count()}")
        sys.stdout.flush()
        
        # Test 'my' preset for agent
        my_leads = accessible_leads.filter(assigned_user=agent)
        print(f"My leads count: {my_leads.count()}")
        sys.stdout.flush()
        
        # Test 'my_team' preset for agent (should fallback to 'my')
        team_leads = accessible_leads.filter(assigned_user__in=accessible_users)
        print(f"Team leads count (fallback): {team_leads.count()}")
        sys.stdout.flush()
    else:
        print("No agent found in database!")
        sys.stdout.flush()

if __name__ == "__main__":
    test_user_hierarchy()
    print("Test completed!")
    sys.stdout.flush()
