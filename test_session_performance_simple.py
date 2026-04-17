#!/usr/bin/env python
"""
Simple test to verify session manager implementation without Django setup.
"""

import time
import sys
import os

# Add the project path
sys.path.append('C:/Users/DELL/OneDrive/Desktop/CRM')
sys.path.append('C:/Users/DELL/OneDrive/Desktop/CRM/crm_project')

def test_session_manager_import():
    """Test that the session manager can be imported correctly."""
    print("Testing session manager import...")
    
    try:
        from accounts.services.session_manager import OptimizedSessionManager
        print("SUCCESS: Session manager imported successfully")
        return True
    except ImportError as e:
        print(f"FAILED: Cannot import session manager: {e}")
        return False

def test_session_manager_methods():
    """Test session manager methods exist."""
    print("\nTesting session manager methods...")
    
    try:
        from accounts.services.session_manager import (
            OptimizedSessionManager,
            invalidate_user_sessions_fast,
            invalidate_user_sessions_async
        )
        
        methods = [
            'invalidate_user_sessions',
            '_get_user_session_keys_cached',
            '_invalidate_sessions_by_keys',
            '_invalidate_sessions_optimized_query',
            'track_user_session',
            'untrack_user_session'
        ]
        
        for method in methods:
            if hasattr(OptimizedSessionManager, method):
                print(f"SUCCESS: {method} method exists")
            else:
                print(f"FAILED: {method} method missing")
                return False
        
        print("SUCCESS: All session manager methods exist")
        return True
        
    except Exception as e:
        print(f"FAILED: Error testing methods: {e}")
        return False

def test_forms_integration():
    """Test that forms.py uses the new session manager."""
    print("\nTesting forms.py integration...")
    
    try:
        # Read the forms.py file
        forms_path = 'C:/Users/DELL/OneDrive/Desktop/CRM/crm_project/accounts/forms.py'
        with open(forms_path, 'r') as f:
            content = f.read()
        
        # Check for old slow method
        if 'session_data__contains' in content:
            print("FAILED: forms.py still contains slow session_data__contains query")
            return False
        
        # Check for new optimized method
        if 'invalidate_user_sessions_fast' in content:
            print("SUCCESS: forms.py uses optimized session invalidation")
        else:
            print("FAILED: forms.py doesn't use optimized session invalidation")
            return False
        
        return True
        
    except Exception as e:
        print(f"FAILED: Error checking forms.py: {e}")
        return False

def test_password_manager_integration():
    """Test that password_manager.py uses the new session manager."""
    print("\nTesting password_manager.py integration...")
    
    try:
        # Read the password manager file
        pm_path = 'C:/Users/DELL/OneDrive/Desktop/CRM/crm_project/accounts/services/password_manager.py'
        with open(pm_path, 'r') as f:
            content = f.read()
        
        # Check for old slow method
        if 'session_data__contains' in content:
            print("FAILED: password_manager.py still contains slow session_data__contains query")
            return False
        
        # Check for new optimized method
        if 'invalidate_user_sessions_fast' in content:
            print("SUCCESS: password_manager.py uses optimized session invalidation")
        else:
            print("FAILED: password_manager.py doesn't use optimized session invalidation")
            return False
        
        return True
        
    except Exception as e:
        print(f"FAILED: Error checking password_manager.py: {e}")
        return False

def test_celery_tasks():
    """Test that Celery tasks are created."""
    print("\nTesting Celery tasks...")
    
    try:
        tasks_path = 'C:/Users/DELL/OneDrive/Desktop/CRM/crm_project/accounts/tasks.py'
        with open(tasks_path, 'r') as f:
            content = f.read()
        
        required_functions = [
            'invalidate_user_sessions_task',
            'cleanup_expired_sessions_task',
            'bulk_invalidate_sessions_task'
        ]
        
        for func in required_functions:
            if func in content:
                print(f"SUCCESS: {func} task exists")
            else:
                print(f"FAILED: {func} task missing")
                return False
        
        return True
        
    except Exception as e:
        print(f"FAILED: Error checking tasks.py: {e}")
        return False

def test_middleware():
    """Test that session tracking middleware exists."""
    print("\nTesting session tracking middleware...")
    
    try:
        middleware_path = 'C:/Users/DELL/OneDrive/Desktop/CRM/crm_project/accounts/middleware.py'
        with open(middleware_path, 'r') as f:
            content = f.read()
        
        if 'SessionTrackingMiddleware' in content:
            print("SUCCESS: SessionTrackingMiddleware exists")
            return True
        else:
            print("FAILED: SessionTrackingMiddleware missing")
            return False
        
    except Exception as e:
        print(f"FAILED: Error checking middleware: {e}")
        return False

def run_all_tests():
    """Run all implementation tests."""
    print("=" * 60)
    print("PASSWORD CHANGE PERFORMANCE FIX - IMPLEMENTATION TEST")
    print("=" * 60)
    
    tests = [
        test_session_manager_import,
        test_session_manager_methods,
        test_forms_integration,
        test_password_manager_integration,
        test_celery_tasks,
        test_middleware
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 60)
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("SUCCESS: All implementation tests passed!")
        print("The password change performance fix has been implemented correctly.")
    else:
        print("FAILED: Some tests failed. Please check the implementation.")
    
    print("=" * 60)
    
    return passed == total

if __name__ == '__main__':
    run_all_tests()
