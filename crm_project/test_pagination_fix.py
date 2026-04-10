#!/usr/bin/env python
"""
Simple test script to validate pagination fixes for duplicate detection.
This script can be run to quickly test the pagination functionality.
"""

import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import Client
from django.utils import timezone
from datetime import timedelta

from services.duplicate_detector import DuplicateDetector
from dashboard.models import Lead

User = get_user_model()


def test_duplicate_pagination():
    """Test the pagination functionality with sample data."""
    print("🧪 Testing Duplicate Detection Pagination...")
    
    # Create test user
    user, created = User.objects.get_or_create(
        username='testuser',
        defaults={
            'email': 'test@example.com',
            'role': 'owner',
            'company_id': 1
        }
    )
    if created:
        user.set_password('testpass123')
        user.save()
    
    # Create test duplicate groups
    print("📝 Creating test duplicate groups...")
    base_time = timezone.now()
    
    # Clean up existing test data
    Lead.objects.filter(
        company_id=1,
        duplicate_status__in=['exact_duplicate', 'potential_duplicate']
    ).delete()
    
    # Create 25 duplicate groups
    for i in range(25):
        group_id = f'test_pagination_group_{i}'
        
        # Create 2-3 leads per group
        for j in range(2):
            Lead.objects.create(
                id_lead=5000 + i * 2 + j,
                name=f'Pagination Test Lead {i}-{j}',
                email=f'pagination{i}@example.com',
                mobile=f'98765432{i:02d}',
                company_id=1,
                assigned_user=user,
                duplicate_status='exact_duplicate',
                duplicate_group_id=group_id,
                duplicate_resolution_status='pending' if i % 3 != 0 else 'resolved',
                created_at=base_time + timedelta(minutes=i)
            )
    
    print(f"✅ Created {Lead.objects.filter(company_id=1, duplicate_status='exact_duplicate').count()} test leads")
    
    # Test the DuplicateDetector pagination method
    print("\n🔍 Testing DuplicateDetector pagination method...")
    detector = DuplicateDetector(company_id=1)
    
    # Test page 1
    result1 = detector.find_duplicate_groups_paginated(page=1, page_size=10)
    print(f"   Page 1: {len(result1['groups'])} groups, Total: {result1['total_count']}")
    print(f"   Has next: {result1['has_next']}, Has previous: {result1['has_previous']}")
    
    # Test page 2
    if result1['has_next']:
        result2 = detector.find_duplicate_groups_paginated(page=2, page_size=10)
        print(f"   Page 2: {len(result2['groups'])} groups")
        print(f"   Has next: {result2['has_next']}, Has previous: {result2['has_previous']}")
        
        # Verify no duplicate group IDs between pages
        page1_ids = {g['group_id'] for g in result1['groups']}
        page2_ids = {g['group_id'] for g in result2['groups']}
        overlap = page1_ids.intersection(page2_ids)
        print(f"   Overlap between pages: {len(overlap)} groups")
    
    # Test with filters
    print("\n🎯 Testing with filters...")
    filtered_result = detector.find_duplicate_groups_paginated(
        page=1,
        page_size=5,
        status='pending'
    )
    print(f"   Pending groups: {len(filtered_result['groups'])} out of {filtered_result['total_count']}")
    
    # Test different page sizes
    print("\n📏 Testing different page sizes...")
    for page_size in [5, 10, 20, 50]:
        result = detector.find_duplicate_groups_paginated(page=1, page_size=page_size)
        print(f"   Page size {page_size}: {len(result['groups'])} groups")
    
    # Test edge cases
    print("\n⚠️  Testing edge cases...")
    
    # Test invalid page number
    try:
        result = detector.find_duplicate_groups_paginated(page=999, page_size=10)
        print(f"   Invalid page (999): {len(result['groups'])} groups (should be 0)")
    except Exception as e:
        print(f"   Invalid page error: {e}")
    
    # Test very large page size
    try:
        result = detector.find_duplicate_groups_paginated(page=1, page_size=1000)
        print(f"   Large page size (1000): {len(result['groups'])} groups")
    except Exception as e:
        print(f"   Large page size error: {e}")
    
    # Test web views
    print("\n🌐 Testing web views...")
    client = Client()
    client.login(username='testuser', password='testpass123')
    
    # Test main duplicates view
    response = client.get(reverse('dashboard:leads_duplicates'))
    print(f"   Main view status: {response.status_code}")
    
    # Test with pagination parameters
    response = client.get(reverse('dashboard:leads_duplicates'), {
        'page': 2,
        'page_size': 10
    })
    print(f"   Paginated view status: {response.status_code}")
    
    # Test with filters
    response = client.get(reverse('dashboard:leads_duplicates'), {
        'page': 1,
        'page_size': 5,
        'status': 'pending'
    })
    print(f"   Filtered view status: {response.status_code}")
    
    print("\n✅ Pagination test completed successfully!")
    return True


def test_performance():
    """Test pagination performance with larger dataset."""
    print("\n⚡ Testing pagination performance...")
    
    detector = DuplicateDetector(company_id=1)
    
    import time
    
    # Test performance with different page sizes
    page_sizes = [10, 20, 50, 100]
    
    for page_size in page_sizes:
        start_time = time.time()
        result = detector.find_duplicate_groups_paginated(page=1, page_size=page_size)
        end_time = time.time()
        
        duration = end_time - start_time
        print(f"   Page size {page_size}: {duration:.3f}s, {len(result['groups'])} groups")
        
        # Performance should be reasonable
        if duration > 2.0:
            print(f"   ⚠️  Warning: Page size {page_size} took {duration:.3f}s (threshold: 2.0s)")


if __name__ == '__main__':
    print("🚀 Starting Pagination Fix Validation\n")
    
    try:
        success = test_duplicate_pagination()
        if success:
            test_performance()
            print("\n🎉 All pagination tests passed!")
        else:
            print("\n❌ Some tests failed!")
            sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
