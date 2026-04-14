#!/usr/bin/env python3
"""
Test script to verify the logout fix implementation.
This script checks if the CSRF and session configurations are properly set.
"""

import os
import sys
import django
from django.conf import settings

# Add the project path
sys.path.append('/root/CRM/crm_project')

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

def test_settings():
    """Test if the settings are properly configured"""
    print("=== Testing Django Settings ===")
    
    # Check session engine - this is the critical fix
    print(f"SESSION_ENGINE: {settings.SESSION_ENGINE}")
    if hasattr(settings, 'SESSION_CACHE_ALIAS'):
        print(f"SESSION_CACHE_ALIAS: {settings.SESSION_CACHE_ALIAS}")
    else:
        print("SESSION_CACHE_ALIAS: Not configured (good for database sessions)")
    
    # Check session cookie settings
    print(f"SESSION_COOKIE_SECURE: {settings.SESSION_COOKIE_SECURE}")
    print(f"SESSION_COOKIE_HTTPONLY: {settings.SESSION_COOKIE_HTTPONLY}")
    print(f"SESSION_COOKIE_SAMESITE: {settings.SESSION_COOKIE_SAMESITE}")
    
    # Check CSRF settings
    print(f"CSRF_COOKIE_SECURE: {settings.CSRF_COOKIE_SECURE}")
    print(f"CSRF_COOKIE_HTTPONLY: {settings.CSRF_COOKIE_HTTPONLY}")
    print(f"CSRF_COOKIE_SAMESITE: {settings.CSRF_COOKIE_SAMESITE}")
    
    # Check CSRF trusted origins
    print(f"CSRF_TRUSTED_ORIGINS: {settings.CSRF_TRUSTED_ORIGINS}")
    
    # Verify the session engine fix - this is the critical part
    expected_engine = 'django.contrib.sessions.backends.db'
    if settings.SESSION_ENGINE == expected_engine:
        print("SUCCESS: SESSION_ENGINE correctly set to database backend")
    else:
        print(f"CRITICAL: SESSION_ENGINE is '{settings.SESSION_ENGINE}', expected '{expected_engine}'")
    
    # Verify SESSION_CACHE_ALIAS is removed
    if not hasattr(settings, 'SESSION_CACHE_ALIAS'):
        print("SUCCESS: SESSION_CACHE_ALIAS correctly removed")
    else:
        print(f"WARNING: SESSION_CACHE_ALIAS still exists as '{settings.SESSION_CACHE_ALIAS}'")
    
    # Verify the cookie settings
    if settings.DEBUG:
        expected_samesite = 'Lax'
        if settings.SESSION_COOKIE_SAMESITE == expected_samesite:
            print("SESSION_COOKIE_SAMESITE correctly set to 'Lax' for DEBUG mode")
        else:
            print(f"WARNING: SESSION_COOKIE_SAMESITE is '{settings.SESSION_COOKIE_SAMESITE}', expected '{expected_samesite}'")
    else:
        expected_samesite = 'None'
        if settings.SESSION_COOKIE_SAMESITE == expected_samesite:
            print("SESSION_COOKIE_SAMESITE correctly set to 'None' for production mode")
        else:
            print(f"WARNING: SESSION_COOKIE_SAMESITE is '{settings.SESSION_COOKIE_SAMESITE}', expected '{expected_samesite}'")

def test_template():
    """Test if the template includes CSRF token meta tag"""
    print("\n=== Testing Template Configuration ===")
    
    template_path = '/root/CRM/crm_project/templates/dashboard/base_dashboard.html'
    try:
        with open(template_path, 'r') as f:
            content = f.read()
            
        if 'csrf-token' in content:
            print("CSRF token meta tag found in base_dashboard.html")
            if '<meta name="csrf-token" content="{{ csrf_token }}">' in content:
                print("CSRF token meta tag correctly configured")
            else:
                print("WARNING: CSRF token meta tag found but may not be correctly formatted")
        else:
            print("WARNING: CSRF token meta tag not found in base_dashboard.html")
            
    except FileNotFoundError:
        print(f"ERROR: Template file not found at {template_path}")

def test_javascript():
    """Test if JavaScript includes CSRF handling"""
    print("\n=== Testing JavaScript Configuration ===")
    
    js_path = '/root/CRM/crm_project/static/js/dashboard.js'
    try:
        with open(js_path, 'r') as f:
            content = f.read()
            
        if 'getCSRFToken' in content:
            print("CSRF token helper function found in dashboard.js")
        else:
            print("WARNING: CSRF token helper function not found in dashboard.js")
            
        if 'setupCSRF' in content:
            print("CSRF setup function found in dashboard.js")
        else:
            print("WARNING: CSRF setup function not found in dashboard.js")
            
        if 'X-CSRFToken' in content:
            print("CSRF header configuration found in dashboard.js")
        else:
            print("WARNING: CSRF header configuration not found in dashboard.js")
            
    except FileNotFoundError:
        print(f"ERROR: JavaScript file not found at {js_path}")

def test_api_views():
    """Test if API views have proper CSRF protection"""
    print("\n=== Testing API Views Configuration ===")
    
    api_views_path = '/root/CRM/crm_project/dashboard/api_views.py'
    try:
        with open(api_views_path, 'r') as f:
            content = f.read()
            
        # Count @csrf_exempt occurrences
        csrf_exempt_count = content.count('@csrf_exempt')
        print(f"Found {csrf_exempt_count} occurrences of @csrf_exempt in api_views.py")
        
        if csrf_exempt_count == 0:
            print("All API views now have CSRF protection enabled")
        else:
            print(f"WARNING: {csrf_exempt_count} API views still have @csrf_exempt decorator")
            
        # Check for proper login_required decorators
        login_required_count = content.count('@login_required')
        print(f"Found {login_required_count} occurrences of @login_required in api_views.py")
        
    except FileNotFoundError:
        print(f"ERROR: API views file not found at {api_views_path}")

if __name__ == '__main__':
    print("Testing Lead Management Logout Fix Implementation")
    print("=" * 50)
    
    test_settings()
    test_template()
    test_javascript()
    test_api_views()
    
    print("\n" + "=" * 50)
    print("Test completed. Review the output above to verify all fixes are properly implemented.")
