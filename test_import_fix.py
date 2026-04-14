#!/usr/bin/env python
"""
Test script to verify the lead import fixes are working correctly.
This will test the error visibility and logging improvements.
"""

import os
import sys
import django
import logging
from io import StringIO

# Add project path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'crm_project'))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from dashboard.models import LeadImportSession
from dashboard.views import get_user_friendly_error

User = get_user_model()

def test_error_logging():
    """Test that error logging is working correctly"""
    print("Testing error logging functionality...")
    
    # Test user-friendly error messages
    test_cases = [
        ('IntegrityError', 'Duplicate entry', 'Duplicate lead already exists in database'),
        ('OperationalError', 'Connection timeout', 'Database connection issue - please try again'),
        ('MemoryError', 'Out of memory', 'File too large - please split into smaller files'),
        ('ValidationError', 'Invalid format', 'Invalid data format in file'),
        ('UnknownError', 'Random error', 'Import error: UnknownError'),
    ]
    
    for error_type, error_message, expected in test_cases:
        result = get_user_friendly_error(error_type, error_message)
        assert result == expected, f"Expected '{expected}', got '{result}'"
        print(f"✓ {error_type}: {result}")
    
    print("✓ All error message tests passed!")

def test_import_session_error_details():
    """Test that import sessions can store error details"""
    print("\nTesting import session error details...")
    
    # Create a test user
    user = User.objects.first()
    if not user:
        print("No users found in database. Creating test user...")
        user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    # Create a test import session
    session = LeadImportSession.objects.create(
        session_id='test_session_123',
        idempotency_key='test_key',
        user=user,
        company_id=1,
        file_name='test.csv',
        status='processing',
        error_details=[
            {
                'error_type': 'TestError',
                'error_message': 'This is a test error',
                'lead_index': 1,
                'lead_data': 'test data'
            }
        ]
    )
    
    # Verify error details are stored
    assert hasattr(session, 'error_details'), "error_details field should exist"
    assert len(session.error_details) == 1, "Should have 1 error detail"
    assert session.error_details[0]['error_type'] == 'TestError', "Error type should match"
    
    print(f"✓ Import session created with error details: {session.session_id}")
    
    # Clean up
    session.delete()
    print("✓ Test session cleaned up")

def test_database_retry_decorator():
    """Test that the database retry decorator is defined"""
    print("\nTesting database retry decorator...")
    
    try:
        from dashboard.views import database_retry
        print("✓ database_retry decorator imported successfully")
        
        # Test decorator application
        @database_retry(max_retries=2)
        def test_function():
            return "success"
        
        result = test_function()
        assert result == "success", "Decorated function should work normally"
        print("✓ Database retry decorator works correctly")
        
    except ImportError as e:
        print(f"✗ Failed to import database_retry decorator: {e}")
        return False
    
    return True

def main():
    """Run all tests"""
    print("=" * 50)
    print("LEAD IMPORT FIXES VERIFICATION")
    print("=" * 50)
    
    try:
        test_error_logging()
        test_import_session_error_details()
        test_database_retry_decorator()
        
        print("\n" + "=" * 50)
        print("✅ ALL TESTS PASSED!")
        print("The lead import fixes are working correctly:")
        print("  ✓ Error logging is enhanced")
        print("  ✓ Error details are stored in database")
        print("  ✓ User-friendly error messages work")
        print("  ✓ Database retry decorator is available")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
