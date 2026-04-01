#!/usr/bin/env python
"""
Check existing user passwords and create test user with known password
"""
import os
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.contrib.auth import authenticate
from accounts.models import User

def check_users_and_create_test():
    """Check existing users and create test user with known password"""
    
    print("=== User Password Check ===\n")
    
    # List all users
    users = User.objects.all()
    print("Existing users:")
    for user in users:
        print(f"- {user.username} (Email: {user.email}, Active: {user.is_active})")
    
    # Create a test user with known password if it doesn't exist
    test_username = 'emailtest'
    test_email = 'emailtest@example.com'
    test_password = 'testpass123'
    
    if User.objects.filter(username=test_username).exists():
        print(f"\n✓ Test user '{test_username}' already exists")
        test_user = User.objects.get(username=test_username)
    else:
        print(f"\nCreating test user '{test_username}' with known password...")
        test_user = User.objects.create_user(
            username=test_username,
            email=test_email,
            password=test_password,
            first_name='Email',
            last_name='Test',
            role='agent'
        )
        print(f"✓ Created test user: {test_user.username} - Email: {test_user.email}")
    
    # Test authentication with known password
    print(f"\n=== Testing Authentication with Known Password ===")
    
    # Test 1: Username login
    print(f"1. Testing username login with '{test_username}'...")
    user_auth = authenticate(username=test_username, password=test_password)
    if user_auth:
        print(f"✓ Username login successful: {user_auth.username}")
    else:
        print("✗ Username login failed")
    
    # Test 2: Email login
    print(f"2. Testing email login with '{test_email}'...")
    user_auth_email = authenticate(username=test_email, password=test_password)
    if user_auth_email:
        print(f"✓ Email login successful: {user_auth_email.username}")
    else:
        print("✗ Email login failed")
    
    # Test 3: Case-insensitive email login
    print(f"3. Testing case-insensitive email login with '{test_email.upper()}'...")
    user_auth_case = authenticate(username=test_email.upper(), password=test_password)
    if user_auth_case:
        print(f"✓ Case-insensitive email login successful: {user_auth_case.username}")
    else:
        print("✗ Case-insensitive email login failed")
    
    print(f"\n=== Test Credentials ===")
    print(f"Username: {test_username}")
    print(f"Email: {test_email}")
    print(f"Password: {test_password}")
    print("\nYou can use these credentials to test login in the browser.")

if __name__ == '__main__':
    check_users_and_create_test()
