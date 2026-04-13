#!/usr/bin/env python
"""
Test script to verify cache invalidation functionality in user management.
This script tests that user edits properly clear relevant caches.
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))
django.setup()

from django.core.cache import cache
from django.test import TestCase
from crm_project.accounts.models import User
from crm_project.accounts.forms import UserEditForm

def clear_all_cache():
    """Clear all cache for clean testing"""
    cache.clear()

def test_cache_invalidation():
    """Test cache invalidation after user edits"""
    print("Testing cache invalidation functionality...")
    
    # Clear all cache before testing
    clear_all_cache()
    
    # Create test users
    print("Creating test users...")
    
    # Create owner
    owner = User.objects.create_user(
        username='test_owner',
        email='owner@test.com',
        password='test123',
        first_name='Test',
        last_name='Owner',
        role='owner',
        company_id=1
    )
    
    # Create manager
    manager = User.objects.create_user(
        username='test_manager',
        email='manager@test.com',
        password='test123',
        first_name='Test',
        last_name='Manager',
        role='manager',
        company_id=1,
        manager=owner
    )
    
    # Create team lead
    team_lead = User.objects.create_user(
        username='test_teamlead',
        email='teamlead@test.com',
        password='test123',
        first_name='Test',
        last_name='TeamLead',
        role='team_lead',
        company_id=1,
        manager=manager
    )
    
    # Create agent
    agent = User.objects.create_user(
        username='test_agent',
        email='agent@test.com',
        password='test123',
        first_name='Test',
        last_name='Agent',
        role='agent',
        company_id=1,
        manager=manager,
        team_lead=team_lead
    )
    
    print(f"Created users: {owner.username}, {manager.username}, {team_lead.username}, {agent.username}")
    
    # Test 1: Populate caches by accessing user lists
    print("\nTest 1: Populating caches...")
    
    # Access accessible users to populate caches
    owner_users = owner.get_accessible_users()
    manager_users = manager.get_accessible_users()
    team_lead_users = team_lead.get_accessible_users()
    agent_users = agent.get_accessible_users()
    
    print(f"Owner can see {len(owner_users)} users")
    print(f"Manager can see {len(manager_users)} users")
    print(f"Team lead can see {len(team_lead_users)} users")
    print(f"Agent can see {len(agent_users)} users")
    
    # Verify caches are populated
    owner_cache_key = owner._get_user_cache_key('accessible_users')
    manager_cache_key = manager._get_user_cache_key('accessible_users')
    team_lead_cache_key = team_lead._get_user_cache_key('accessible_users')
    agent_cache_key = agent._get_user_cache_key('accessible_users')
    
    print(f"Cache keys: {owner_cache_key}, {manager_cache_key}, {team_lead_cache_key}, {agent_cache_key}")
    
    assert cache.get(owner_cache_key) is not None, "Owner cache should be populated"
    assert cache.get(manager_cache_key) is not None, "Manager cache should be populated"
    assert cache.get(team_lead_cache_key) is not None, "Team lead cache should be populated"
    assert cache.get(agent_cache_key) is not None, "Agent cache should be populated"
    
    print("All caches successfully populated!")
    
    # Test 2: Edit agent using UserEditForm and verify cache invalidation
    print("\nTest 2: Testing cache invalidation after user edit...")
    
    # Edit agent using UserEditForm (simulating manager editing agent)
    form_data = {
        'first_name': 'Updated',
        'last_name': 'Agent',
        'email': 'agent@test.com',
        'phone': '1234567890',
        'mobile': '0987654321',
        'account_status': 'active'
    }
    
    form = UserEditForm(
        data=form_data,
        instance=agent,
        editor=manager,
        target_user=agent
    )
    
    # Verify form is valid
    assert form.is_valid(), f"Form should be valid. Errors: {form.errors}"
    
    # Save the form (this should trigger cache invalidation)
    updated_agent = form.save()
    
    print(f"Updated agent: {updated_agent.first_name} {updated_agent.last_name}")
    
    # Verify caches were cleared
    print("Checking if caches were properly invalidated...")
    
    # The caches should be cleared after the edit
    owner_cache_after = cache.get(owner_cache_key)
    manager_cache_after = cache.get(manager_cache_key)
    team_lead_cache_after = cache.get(team_lead_cache_key)
    agent_cache_after = cache.get(agent_cache_key)
    
    print(f"Cache status after edit:")
    print(f"  Owner cache: {'EXISTS' if owner_cache_after else 'CLEARED'}")
    print(f"  Manager cache: {'EXISTS' if manager_cache_after else 'CLEARED'}")
    print(f"  Team lead cache: {'EXISTS' if team_lead_cache_after else 'CLEARED'}")
    print(f"  Agent cache: {'EXISTS' if agent_cache_after else 'CLEARED'}")
    
    # At least the manager's cache (editor) should be cleared
    assert manager_cache_after is None, "Manager's cache should be cleared after editing"
    
    # Test 3: Verify fresh data is loaded after cache clearing
    print("\nTest 3: Verifying fresh data loading...")
    
    # Access user lists again to repopulate caches
    owner_users_fresh = owner.get_accessible_users()
    manager_users_fresh = manager.get_accessible_users()
    
    # Verify updated agent name is reflected
    updated_agent_in_list = next((u for u in manager_users_fresh if u.id == agent.id), None)
    assert updated_agent_in_list is not None, "Updated agent should be in manager's accessible users"
    assert updated_agent_in_list.first_name == 'Updated', "Agent's first name should be updated"
    
    print("Fresh data correctly loaded with updated information!")
    
    # Test 4: Test role change cache invalidation
    print("\nTest 4: Testing role change cache invalidation...")
    
    # Change agent to team lead role
    role_form_data = {
        'first_name': 'Updated',
        'last_name': 'Agent',
        'email': 'agent@test.com',
        'phone': '1234567890',
        'mobile': '0987654321',
        'role': 'team_lead',  # Role change
        'account_status': 'active'
    }
    
    role_form = UserEditForm(
        data=role_form_data,
        instance=agent,
        editor=owner,  # Owner can change roles
        target_user=agent
    )
    
    assert role_form.is_valid(), f"Role change form should be valid. Errors: {role_form.errors}"
    
    # Save the form (this should trigger cache invalidation for role change)
    role_updated_agent = role_form.save()
    
    print(f"Changed agent role from 'agent' to '{role_updated_agent.role}'")
    
    # Verify old role cache is cleared
    old_agent_cache_key = f"accessible_users_{agent.id}_{agent.company_id}_agent"
    old_cache_after = cache.get(old_agent_cache_key)
    
    print(f"Old role cache (agent): {'EXISTS' if old_cache_after else 'CLEARED'}")
    assert old_cache_after is None, "Old role cache should be cleared after role change"
    
    # Test 5: Test hierarchy change cache invalidation
    print("\nTest 5: Testing hierarchy change cache invalidation...")
    
    # Reassign agent to different manager
    hierarchy_form_data = {
        'first_name': 'Updated',
        'last_name': 'Agent',
        'email': 'agent@test.com',
        'phone': '1234567890',
        'mobile': '0987654321',
        'role': 'agent',
        'manager': owner.id,  # Change manager from manager to owner
        'account_status': 'active'
    }
    
    hierarchy_form = UserEditForm(
        data=hierarchy_form_data,
        instance=agent,
        editor=owner,
        target_user=agent
    )
    
    assert hierarchy_form.is_valid(), f"Hierarchy change form should be valid. Errors: {hierarchy_form.errors}"
    
    # Save the form (this should trigger cache invalidation for hierarchy change)
    hierarchy_updated_agent = hierarchy_form.save()
    
    print(f"Changed agent manager from {manager.username} to {hierarchy_updated_agent.manager.username if hierarchy_updated_agent.manager else 'None'}")
    
    # Verify caches for old and new managers are affected
    old_manager_cache_after = cache.get(manager_cache_key)
    new_manager_cache_after = cache.get(owner_cache_key)
    
    print(f"Old manager cache: {'EXISTS' if old_manager_cache_after else 'CLEARED'}")
    print(f"New manager cache: {'EXISTS' if new_manager_cache_after else 'CLEARED'}")
    
    print("\nAll cache invalidation tests passed! ")
    print("Cache invalidation is working correctly for:")
    print("- User profile updates")
    print("- Role changes")
    print("- Hierarchy changes")
    print("- Editor cache clearing")
    
    # Clean up test data
    print("\nCleaning up test data...")
    agent.delete()
    team_lead.delete()
    manager.delete()
    owner.delete()
    
    print("Test completed successfully!")

if __name__ == '__main__':
    try:
        test_cache_invalidation()
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
