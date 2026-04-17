#!/usr/bin/env python
"""
Test script for admin password management functionality
"""

import os
import sys
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.settings')
django.setup()

from accounts.services.password_manager import PasswordManager, password_manager
from accounts.models import User
from django.test import TestCase
from django.contrib.auth import authenticate

def test_password_manager():
    """Test the password manager service"""
    print("=== Testing Password Manager Service ===")
    
    pm = PasswordManager()
    
    # Test password generation
    print("1. Testing password generation...")
    password = pm.generate_secure_password(12)
    print(f"Generated password: {password}")
    print(f"Password length: {len(password)}")
    
    # Test password validation
    print("\n2. Testing password validation...")
    validation = pm.validate_password_strength(password)
    print(f"Password valid: {validation['is_valid']}")
    print(f"Password score: {validation['score']}")
    if validation['errors']:
        print(f"Errors: {validation['errors']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    
    # Test weak password
    print("\n3. Testing weak password validation...")
    weak_validation = pm.validate_password_strength("weak")
    print(f"Weak password valid: {weak_validation['is_valid']}")
    print(f"Weak password errors: {weak_validation['errors']}")
    
    # Test permission checking
    print("\n4. Testing permission checking...")
    try:
        # Get test users
        owner = User.objects.filter(role='owner').first()
        manager = User.objects.filter(role='manager').first()
        team_lead = User.objects.filter(role='team_lead').first()
        agent = User.objects.filter(role='agent').first()
        
        if owner and manager:
            can_manage = pm.can_manage_user_password(owner, manager)
            print(f"Owner can manage manager password: {can_manage}")
        
        if manager and team_lead:
            can_manage = pm.can_manage_user_password(manager, team_lead)
            print(f"Manager can manage team lead password: {can_manage}")
        
        if team_lead and agent:
            can_manage = pm.can_manage_user_password(team_lead, agent)
            print(f"Team lead can manage agent password: {can_manage}")
        
        if agent and owner:
            can_manage = pm.can_manage_user_password(agent, owner)
            print(f"Agent can manage owner password: {can_manage}")
            
    except Exception as e:
        print(f"Permission test failed: {e}")
    
    print("\n=== Password Manager Service Test Complete ===\n")

def test_forms():
    """Test the password management forms"""
    print("=== Testing Password Management Forms ===")
    
    try:
        from accounts.forms import AdminPasswordForm, UserEditForm, PasswordVisibilityWidget
        
        # Test AdminPasswordForm
        print("1. Testing AdminPasswordForm...")
        
        # Get test users
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
            
            if form.is_valid():
                print("AdminPasswordForm validation: PASSED")
                # Test password generation
                generated_password = form.generate_secure_password()
                print(f"Generated password: {generated_password}")
            else:
                print(f"AdminPasswordForm validation: FAILED - {form.errors}")
        
        # Test UserEditForm with password fields
        print("\n2. Testing UserEditForm with password fields...")
        
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
            
            if form.is_valid():
                print("UserEditForm with password: PASSED")
                print(f"Can manage password: {form._can_manage_password()}")
            else:
                print(f"UserEditForm validation: FAILED - {form.errors}")
        
        print("\n=== Password Forms Test Complete ===\n")
        
    except Exception as e:
        print(f"Forms test failed: {e}")
        import traceback
        traceback.print_exc()

def test_password_change():
    """Test password change functionality"""
    print("=== Testing Password Change Functionality ===")
    
    try:
        # Get test users
        owner = User.objects.filter(role='owner').first()
        agent = User.objects.filter(role='agent').first()
        
        if not owner or not agent:
            print("Need test users (owner and agent) to test password change")
            return
        
        # Store original password
        original_password = 'test123'
        agent.set_password(original_password)
        agent.save()
        
        # Test password change
        new_password = 'NewSecurePass123!'
        result = password_manager.change_user_password(
            user=agent,
            new_password=new_password,
            changed_by=owner,
            send_notification=False,
            invalidate_sessions=False
        )
        
        print(f"Password change result: {result}")
        
        if result['success']:
            # Test authentication with new password
            authenticated_user = authenticate(
                username=agent.username,
                password=new_password
            )
            
            if authenticated_user:
                print("Authentication with new password: PASSED")
            else:
                print("Authentication with new password: FAILED")
            
            # Test authentication with old password (should fail)
            old_auth_user = authenticate(
                username=agent.username,
                password=original_password
            )
            
            if old_auth_user is None:
                print("Authentication with old password: CORRECTLY FAILED")
            else:
                print("Authentication with old password: UNEXPECTEDLY PASSED")
        
        print("\n=== Password Change Test Complete ===\n")
        
    except Exception as e:
        print(f"Password change test failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Run all tests"""
    print("Starting Admin Password Management Tests...\n")
    
    test_password_manager()
    test_forms()
    test_password_change()
    
    print("All tests completed!")

if __name__ == '__main__':
    main()
