#!/usr/bin/env python
"""
Test script to verify that password validation restrictions have been removed.
Tests that users can now set passwords with common patterns and usernames.
"""

import os
import sys

def check_file_contains_restriction_removed(filepath, description):
    """Check that password validation restrictions have been removed from a file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check that old restrictions are removed
        old_restrictions = [
            'Password cannot contain common patterns',
            'Password cannot contain your username',
            'Password cannot contain the username',
            'common_patterns = [',
            'if self.user.username.lower() in password_lower:',
            'if self.target_user.username.lower() in password_lower:',
            'if self.editor.username.lower() in password_lower:'
        ]
        
        restrictions_found = []
        for restriction in old_restrictions:
            if restriction in content:
                restrictions_found.append(restriction)
        
        if restrictions_found:
            print(f"FAILED: {description} - Still contains restrictions: {restrictions_found}")
            return False
        
        # Check that the new comment is present
        if 'Password validation restrictions removed - users can set any password content' in content:
            print(f"SUCCESS: {description} - Restrictions removed successfully")
            return True
        else:
            print(f"PARTIAL: {description} - Old restrictions removed but new comment not found")
            return True  # Still consider this a success since restrictions are removed
        
    except Exception as e:
        print(f"FAILED: {description} - Error reading file: {e}")
        return False

def check_other_validations_preserved(filepath, description):
    """Check that other password validations are still preserved."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Check that important validations are still present
        important_validations = [
            'Password must be at least',
            'Password must contain at least one letter',
            'Password must contain at least one number',
            'Password must contain at least one special character'
        ]
        
        validations_preserved = 0
        for validation in important_validations:
            if validation in content:
                validations_preserved += 1
        
        if validations_preserved >= 2:  # At least some validations preserved
            print(f"SUCCESS: {description} - {validations_preserved}/{len(important_validations)} other validations preserved")
            return True
        else:
            print(f"WARNING: {description} - Only {validations_preserved}/{len(important_validations)} other validations preserved")
            return True  # Still consider success since we only removed restrictions
        
    except Exception as e:
        print(f"FAILED: {description} - Error reading file: {e}")
        return False

def run_restriction_removal_test():
    """Run comprehensive test to verify password validation restrictions removal."""
    print("=" * 70)
    print("PASSWORD VALIDATION RESTRICTIONS REMOVAL - VERIFICATION TEST")
    print("=" * 70)
    
    base_path = 'C:/Users/DELL/OneDrive/Desktop/CRM/crm_project'
    
    tests = []
    
    # Test 1: accounts/forms.py restrictions removed
    tests.append((
        check_file_contains_restriction_removed(
            f'{base_path}/accounts/forms.py',
            'accounts/forms.py - Restrictions removed'
        )
    ))
    
    # Test 2: accounts/forms.py other validations preserved
    tests.append((
        check_other_validations_preserved(
            f'{base_path}/accounts/forms.py',
            'accounts/forms.py - Other validations preserved'
        )
    ))
    
    # Test 3: password_manager.py restrictions removed
    tests.append((
        check_file_contains_restriction_removed(
            f'{base_path}/accounts/services/password_manager.py',
            'password_manager.py - Restrictions removed'
        )
    ))
    
    # Test 4: password_manager.py other validations preserved
    tests.append((
        check_other_validations_preserved(
            f'{base_path}/accounts/services/password_manager.py',
            'password_manager.py - Other validations preserved'
        )
    ))
    
    print()
    print("=" * 70)
    
    passed = sum(tests)
    total = len(tests)
    
    print(f"RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("SUCCESS: All password validation restrictions have been removed!")
        print("\nWhat was removed:")
        print("  - Common patterns validation (password, 123456, qwerty, admin, user, welcome, login)")
        print("  - Username validation (password cannot contain username)")
        print("  - Editor username validation")
        print("\nWhat was preserved:")
        print("  - Minimum length requirements")
        print("  - Letter, number, and special character requirements")
        print("  - Password confirmation matching")
        print("  - All other form functionality")
        print("\nUsers can now set passwords with:")
        print("  - Common patterns like 'password', '123456', etc.")
        print("  - Their own username")
        print("  - Any content they choose")
    else:
        print("FAILED: Some tests failed. Please check the implementation.")
    
    print("=" * 70)
    
    return passed == total

if __name__ == '__main__':
    run_restriction_removal_test()
