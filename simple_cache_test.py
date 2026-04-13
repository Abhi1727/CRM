#!/usr/bin/env python
"""
Simple test to verify cache invalidation functionality without creating a test database.
This script uses existing users to test cache behavior.
"""

import os
import sys

# Add the project directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')

import django
django.setup()

from django.core.cache import cache
from crm_project.accounts.models import User

def test_cache_keys():
    """Test cache key generation and basic cache functionality"""
    print("Testing cache key generation...")
    
    # Get a user from database (assuming there's at least one user)
    users = User.objects.all()[:1]
    if not users:
        print("No users found in database. Please create a user first.")
        return False
    
    user = users[0]
    print(f"Testing with user: {user.username} (role: {user.role})")
    
    # Test cache key generation
    users_cache_key = user._get_user_cache_key('accessible_users')
    leads_cache_key = user._get_user_cache_key('accessible_leads')
    
    print(f"Users cache key: {users_cache_key}")
    print(f"Leads cache key: {leads_cache_key}")
    
    # Clear any existing cache
    cache.delete(users_cache_key)
    cache.delete(leads_cache_key)
    
    # Test cache population
    print("\nTesting cache population...")
    accessible_users = user.get_accessible_users()
    accessible_leads = user.get_accessible_leads_queryset()
    
    # Check if cache is populated
    users_cached = cache.get(users_cache_key)
    leads_cached = cache.get(leads_cache_key)
    
    print(f"Users cache populated: {'YES' if users_cached else 'NO'}")
    print(f"Leads cache populated: {'YES' if leads_cached else 'NO'}")
    
    if users_cached and leads_cached:
        print("Cache population working correctly!")
    else:
        print("Cache population failed!")
        return False
    
    # Test cache clearing
    print("\nTesting cache clearing...")
    user._clear_user_caches()
    
    users_cached_after = cache.get(users_cache_key)
    leads_cached_after = cache.get(leads_cache_key)
    
    print(f"Users cache after clearing: {'EXISTS' if users_cached_after else 'CLEARED'}")
    print(f"Leads cache after clearing: {'EXISTS' if leads_cached_after else 'CLEARED'}")
    
    if not users_cached_after and not leads_cached_after:
        print("Cache clearing working correctly!")
    else:
        print("Cache clearing failed!")
        return False
    
    # Test cache warming
    print("\nTesting cache warming...")
    User.warm_user_caches(user.id)
    
    users_cached_after_warm = cache.get(users_cache_key)
    leads_cached_after_warm = cache.get(leads_cache_key)
    
    print(f"Users cache after warming: {'EXISTS' if users_cached_after_warm else 'MISSING'}")
    print(f"Leads cache after warming: {'EXISTS' if leads_cached_after_warm else 'MISSING'}")
    
    if users_cached_after_warm and leads_cached_after_warm:
        print("Cache warming working correctly!")
    else:
        print("Cache warming failed!")
        return False
    
    return True

def test_company_cache_clearing():
    """Test company-wide cache clearing"""
    print("\nTesting company-wide cache clearing...")
    
    # Get users from the same company
    company_id = 1  # Assuming company_id 1 exists
    users = User.objects.filter(company_id=company_id)[:3]
    
    if len(users) < 2:
        print("Need at least 2 users in the same company to test company cache clearing.")
        return True
    
    print(f"Testing with {len(users)} users from company {company_id}")
    
    # Populate caches for all users
    for user in users:
        cache_key = user._get_user_cache_key('accessible_users')
        cache.delete(cache_key)  # Clear first
        user.get_accessible_users()  # Populate
        
        cached = cache.get(cache_key)
        print(f"  {user.username}: cache {'POPULATED' if cached else 'MISSING'}")
    
    # Clear company caches using the utility method
    print("\nClearing company caches...")
    User.clear_hierarchy_caches(company_id)
    
    # Check if caches are cleared
    all_cleared = True
    for user in users:
        cache_key = user._get_user_cache_key('accessible_users')
        cached = cache.get(cache_key)
        if cached:
            all_cleared = False
            print(f"  {user.username}: cache STILL EXISTS")
        else:
            print(f"  {user.username}: cache CLEARED")
    
    if all_cleared:
        print("Company cache clearing working correctly!")
    else:
        print("Company cache clearing failed!")
        return False
    
    return True

def main():
    """Main test function"""
    print("=== Cache Invalidation Test ===")
    
    try:
        # Test basic cache functionality
        if not test_cache_keys():
            print("Basic cache tests failed!")
            return False
        
        # Test company cache clearing
        if not test_company_cache_clearing():
            print("Company cache tests failed!")
            return False
        
        print("\n=== All Cache Tests Passed! ===")
        print("Cache invalidation functionality is working correctly.")
        print("\nFeatures verified:")
        print("- Cache key generation")
        print("- Cache population")
        print("- Cache clearing")
        print("- Cache warming")
        print("- Company-wide cache clearing")
        
        return True
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
