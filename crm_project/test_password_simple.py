#!/usr/bin/env python
"""
Simple test for password management functionality
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.settings')

import django
django.setup()

from accounts.services.password_manager import PasswordManager
from accounts.models import User

def test_password_service():
    print("=== Testing Password Management Service ===")
    
    pm = PasswordManager()
    
    # Test 1: Password Generation
    print("\n1. Testing password generation...")
    password = pm.generate_secure_password(12)
    print(f"Generated password: {password}")
    print(f"Length: {len(password)}")
    
    # Test 2: Password Validation
    print("\n2. Testing password validation...")
    validation = pm.validate_password_strength(password)
    print(f"Valid: {validation['is_valid']}")
    print(f"Score: {validation['score']}")
    
    # Test 3: Weak Password
    print("\n3. Testing weak password...")
    weak_validation = pm.validate_password_strength("weak")
    print(f"Weak password valid: {weak_validation['is_valid']}")
    print(f"Errors: {weak_validation['errors']}")
    
    # Test 4: Permission Check
    print("\n4. Testing permissions...")
    try:
        owner = User.objects.filter(role='owner').first()
        agent = User.objects.filter(role='agent').first()
        
        if owner and agent:
            can_manage = pm.can_manage_user_password(owner, agent)
            print(f"Owner can manage agent password: {can_manage}")
        else:
            print("No test users found")
    except Exception as e:
        print(f"Permission test error: {e}")
    
    print("\n=== Service Test Complete ===")

def test_forms():
    print("\n=== Testing Password Forms ===")
    
    try:
        from accounts.forms import AdminPasswordForm, UserEditForm
        
        print("\n1. Testing AdminPasswordForm...")
        owner = User.objects.filter(role='owner').first()
        agent = User.objects.filter(role='agent').first()
        
        if owner and agent:
            form = AdminPasswordForm(
                target_user=agent,
                editor=owner,
                data={
                    'new_password1': 'SecurePass123!',
                    'new_password2': 'SecurePass123!'
                }
            )
            
            print(f"Form valid: {form.is_valid()}")
            if not form.is_valid():
                print(f"Errors: {form.errors}")
        else:
            print("No test users found")
        
        print("\n2. Testing UserEditForm...")
        if owner and agent:
            form = UserEditForm(
                editor=owner,
                target_user=agent,
                instance=agent,
                data={
                    'first_name': agent.first_name,
                    'last_name': agent.last_name,
                    'email': agent.email,
                    'password': 'NewSecurePass123!',
                    'confirm_password': 'NewSecurePass123!'
                }
            )
            
            print(f"UserEditForm valid: {form.is_valid()}")
            print(f"Can manage password: {form._can_manage_password()}")
            if not form.is_valid():
                print(f"Errors: {form.errors}")
        
        print("\n=== Forms Test Complete ===")
        
    except Exception as e:
        print(f"Forms test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_password_service()
    test_forms()
    print("\n=== All Tests Complete ===")
