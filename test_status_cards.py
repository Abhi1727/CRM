#!/usr/bin/env python3
"""
Test script to verify clickable status cards implementation
"""

import os
import sys
import django
from django.conf import settings
from django.template import Template, Context
from django.urls import reverse

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
django.setup()

def test_template_syntax():
    """Test if the home template has valid syntax"""
    try:
        with open('crm_project/templates/dashboard/home.html', 'r') as f:
            template_content = f.read()
        
        # Create a template object to validate syntax
        template = Template(template_content)
        print("✅ Template syntax is valid")
        return True
    except Exception as e:
        print(f"❌ Template syntax error: {e}")
        return False

def test_url_patterns():
    """Test if the URL patterns are correctly defined"""
    try:
        # Test if the leads_all URL exists
        url = reverse('dashboard:leads_all')
        print(f"✅ URL pattern 'dashboard:leads_all' resolves to: {url}")
        return True
    except Exception as e:
        print(f"❌ URL pattern error: {e}")
        return False

def test_status_card_links():
    """Test if status card links are properly formatted"""
    try:
        with open('crm_project/templates/dashboard/home.html', 'r') as f:
            template_content = f.read()
        
        # Check for status card links
        status_links = template_content.count('class="status-card-link"')
        expected_links = 15  # Number of status types
        
        if status_links == expected_links:
            print(f"✅ Found {status_links} status card links (expected {expected_links})")
            return True
        else:
            print(f"❌ Found {status_links} status card links, expected {expected_links}")
            return False
    except Exception as e:
        print(f"❌ Error checking status card links: {e}")
        return False

def main():
    """Run all tests"""
    print("🔍 Testing Clickable Status Cards Implementation\n")
    
    tests = [
        ("Template Syntax", test_template_syntax),
        ("URL Patterns", test_url_patterns),
        ("Status Card Links", test_status_card_links),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        result = test_func()
        results.append(result)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Implementation is ready.")
    else:
        print("⚠️  Some tests failed. Please review the implementation.")

if __name__ == '__main__':
    main()
