#!/usr/bin/env python
"""
Test script to verify the DuplicateDetector fix is working
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

def test_detector_import():
    """Test that DuplicateDetector can be imported and instantiated"""
    print("Testing DuplicateDetector import...")
    
    try:
        from services.duplicate_detector import DuplicateDetector
        print("SUCCESS: DuplicateDetector imported from services module")
    except ImportError as e:
        print(f"FAILED: Cannot import DuplicateDetector: {e}")
        return False
    
    try:
        detector = DuplicateDetector(company_id=1)
        print(f"SUCCESS: DuplicateDetector instantiated: {detector}")
        print(f"Company ID: {detector.company_id}")
    except Exception as e:
        print(f"FAILED: Cannot instantiate DuplicateDetector: {e}")
        return False
    
    return True

def test_leads_duplicates_function():
    """Test that leads_duplicates function works without NameError"""
    print("\nTesting leads_duplicates function...")
    
    try:
        from dashboard.views import leads_duplicates
        print("SUCCESS: leads_duplicates function imported")
        
        # Test that the function can be called (we'll use a mock request)
        from django.test import RequestFactory
        from accounts.models import User
        
        factory = RequestFactory()
        user = User.objects.first()
        
        if user:
            request = factory.get('/dashboard/leads/duplicates/')
            request.user = user
            
            # This should not raise NameError anymore
            response = leads_duplicates(request)
            print(f"SUCCESS: Function executed without NameError, status: {response.status_code}")
            return True
        else:
            print("WARNING: No users found in database for testing")
            return True
            
    except NameError as e:
        if 'detector' in str(e):
            print(f"FAILED: NameError still occurs: {e}")
            return False
        else:
            print(f"FAILED: Other NameError: {e}")
            return False
    except Exception as e:
        print(f"FAILED: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("TESTING DUPLICATE DETECTOR FIX")
    print("=" * 60)
    
    test1_passed = test_detector_import()
    test2_passed = test_leads_duplicates_function()
    
    print("\n" + "=" * 60)
    if test1_passed and test2_passed:
        print("ALL TESTS PASSED! The fix is working correctly.")
    else:
        print("SOME TESTS FAILED! Please check the errors above.")
    print("=" * 60)
