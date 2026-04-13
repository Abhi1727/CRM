#!/usr/bin/env python
"""
Test script to verify password form functionality
"""
import os
import sys
import django

# Add the project directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth import get_user_model
from accounts.forms import CustomPasswordChangeForm, UserProfileForm

User = get_user_model()

def test_password_form():
    """Test the password change form"""
    print("Testing Password Form...")
    
    # Create a mock request
    factory = RequestFactory()
    request = factory.post('/settings/', {
        'old_password': 'testpass123',
        'new_password1': 'newsecurepass456',
        'new_password2': 'newsecurepass456',
        'password_submit': 'Change Password'
    })
    
    # Get or create a test user
    try:
        user = User.objects.first()
        if not user:
            print("No users found in database. Creating test user...")
            user = User.objects.create_user(
                username='testuser',
                email='test@example.com',
                password='testpass123',
                first_name='Test',
                last_name='User'
            )
    except Exception as e:
        print(f"Error getting user: {e}")
        return
    
    print(f"Testing with user: {user.username}")
    
    # Test form initialization
    try:
        form = CustomPasswordChangeForm(user=user)
        print("✓ Form initialized successfully")
        print(f"  Form fields: {list(form.fields.keys())}")
        
        # Check if fields have proper attributes
        for field_name, field in form.fields.items():
            attrs = field.widget.attrs
            print(f"  {field_name}: class={attrs.get('class', 'None')}, placeholder={attrs.get('placeholder', 'None')}")
            
    except Exception as e:
        print(f"✗ Form initialization failed: {e}")
        return
    
    # Test form with data
    try:
        form = CustomPasswordChangeForm(user=user, data=request.POST)
        print("\n✓ Form with data initialized successfully")
        
        if form.is_valid():
            print("✓ Form is valid")
            try:
                form.save()
                print("✓ Password saved successfully")
            except Exception as e:
                print(f"✗ Password save failed: {e}")
        else:
            print("✗ Form is invalid")
            for field, errors in form.errors.items():
                print(f"  {field}: {errors}")
                
    except Exception as e:
        print(f"✗ Form with data failed: {e}")

def test_profile_form():
    """Test the profile form"""
    print("\nTesting Profile Form...")
    
    try:
        user = User.objects.first()
        if not user:
            print("No users found")
            return
            
        form = UserProfileForm(instance=user)
        print("✓ Profile form initialized successfully")
        print(f"  Form fields: {list(form.fields.keys())}")
        
        # Check field attributes
        for field_name, field in form.fields.items():
            attrs = field.widget.attrs
            print(f"  {field_name}: class={attrs.get('class', 'None')}")
            
    except Exception as e:
        print(f"✗ Profile form failed: {e}")

if __name__ == '__main__':
    test_password_form()
    test_profile_form()
