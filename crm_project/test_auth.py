#!/usr/bin/env python
"""Test script to verify authentication functionality"""
import os
import django
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from accounts.models import User
from accounts.backends import EmailOrUsernameBackend

def test_authentication():
    print("Testing Authentication Backend")
    print("=" * 40)
    
    # Check if users exist
    users = User.objects.all()[:5]
    print(f"Found {User.objects.count()} users in database")
    
    for user in users:
        print(f"User: {user.username} | Email: {user.email}")
    
    # Test authentication backend
    backend = EmailOrUsernameBackend()
    
    # Test with username
    if users:
        test_user = users[0]
        print(f"\nTesting authentication for user: {test_user.username}")
        
        # Note: We can't test actual password without knowing it
        # But we can verify the backend methods work
        try:
            user_by_username = backend.get_user(test_user.id)
            print(f"Successfully retrieved user by ID: {user_by_username.username}")
        except Exception as e:
            print(f"Error retrieving user: {e}")
    
    print("\nEnvironment Variables:")
    print(f"DB_ENGINE: {os.getenv('DB_ENGINE')}")
    print(f"DB_HOST: {os.getenv('DB_HOST')}")
    print(f"DB_NAME: {os.getenv('DB_NAME')}")

if __name__ == '__main__':
    test_authentication()
