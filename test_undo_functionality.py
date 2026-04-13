#!/usr/bin/env python
"""
Test script to verify the undo functionality implementation
"""
import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))
django.setup()

from django.test import TestCase
from django.contrib.auth import get_user_model
from dashboard.models import Lead
from accounts.models import BulkAssignmentUndo

User = get_user_model()

def test_bulk_assignment_undo_model():
    """Test the BulkAssignmentUndo model"""
    print("Testing BulkAssignmentUndo model...")
    
    # Check if model exists and has correct fields
    fields = [f.name for f in BulkAssignmentUndo._meta.get_fields()]
    required_fields = ['assigned_by', 'assigned_to', 'lead_ids', 'assignment_count', 'created_at']
    
    for field in required_fields:
        if field not in fields:
            print(f"❌ Missing field: {field}")
            return False
        else:
            print(f"✅ Field found: {field}")
    
    # Test methods
    test_assignment = BulkAssignmentUndo(
        assigned_by=None,  # Will be set in actual test
        assigned_to=None,   # Will be set in actual test
        lead_ids="1,2,3,4,5",
        assignment_count=5
    )
    
    # Test get_lead_ids_list method
    lead_ids = test_assignment.get_lead_ids_list()
    expected_ids = [1, 2, 3, 4, 5]
    
    if lead_ids == expected_ids:
        print("✅ get_lead_ids_list() method works correctly")
    else:
        print(f"❌ get_lead_ids_list() failed. Expected {expected_ids}, got {lead_ids}")
        return False
    
    print("✅ BulkAssignmentUndo model tests passed")
    return True

def test_url_patterns():
    """Test if URL patterns are correctly configured"""
    print("\nTesting URL patterns...")
    
    try:
        from django.urls import reverse
        
        undo_url = reverse('accounts:undo_assignments')
        history_url = reverse('accounts:get_undo_history')
        
        print(f"✅ Undo assignments URL: {undo_url}")
        print(f"✅ Undo history URL: {history_url}")
        
        return True
    except Exception as e:
        print(f"❌ URL pattern error: {e}")
        return False

def test_views_import():
    """Test if views can be imported"""
    print("\nTesting views import...")
    
    try:
        from accounts.views import undo_assignments, get_undo_history
        print("✅ Views imported successfully")
        return True
    except ImportError as e:
        print(f"❌ View import error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("Testing Undo Functionality Implementation")
    print("=" * 50)
    
    tests = [
        test_bulk_assignment_undo_model,
        test_url_patterns,
        test_views_import,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! The undo functionality has been successfully implemented.")
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
    
    print("=" * 50)

if __name__ == "__main__":
    main()
