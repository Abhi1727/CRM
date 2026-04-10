#!/usr/bin/env python3
"""
Simple test to verify clickable status cards implementation
"""

import os
import re

def test_status_card_links():
    """Test if status card links are properly formatted"""
    try:
        with open('crm_project/templates/dashboard/home.html', 'r') as f:
            template_content = f.read()
        
        # Check for status card links
        status_links = template_content.count('class="status-card-link"')
        expected_links = 15  # Number of status types
        
        print(f"Found {status_links} status card links (expected {expected_links})")
        
        # Check for URL patterns
        url_patterns = re.findall(r'href="{% url \'dashboard:leads_all\' %}\?status=([^"]+)"', template_content)
        print(f"Found {len(url_patterns)} URL patterns with status parameters:")
        for pattern in url_patterns:
            print(f"  - ?status={pattern}")
        
        # Check for CSS classes
        css_classes = re.findall(r'class="([^"]*)"', template_content)
        status_card_classes = [cls for cls in css_classes if 'status-card' in cls]
        print(f"Found status card CSS classes: {set(status_card_classes)}")
        
        return status_links == expected_links and len(url_patterns) == expected_links
    except Exception as e:
        print(f"Error checking status card links: {e}")
        return False

def test_css_styling():
    """Test if CSS styling is added"""
    try:
        with open('crm_project/static/css/dashboard.css', 'r') as f:
            css_content = f.read()
        
        # Check for status-card-link CSS
        has_status_card_link = '.status-card-link' in css_content
        has_hover_effect = '.status-card-link:hover' in css_content
        has_focus_effect = '.status-card-link:focus' in css_content
        
        print(f"CSS .status-card-link found: {has_status_card_link}")
        print(f"CSS hover effect found: {has_hover_effect}")
        print(f"CSS focus effect found: {has_focus_effect}")
        
        return has_status_card_link and has_hover_effect and has_focus_effect
    except Exception as e:
        print(f"Error checking CSS: {e}")
        return False

def test_javascript_functionality():
    """Test if JavaScript functionality is added"""
    try:
        with open('crm_project/templates/dashboard/home.html', 'r') as f:
            template_content = f.read()
        
        # Check for JavaScript
        has_script_tag = '<script>' in template_content and '</script>' in template_content
        has_event_listeners = 'addEventListener' in template_content
        has_ripple_effect = 'status-card-ripple' in template_content
        has_loading_state = 'loading' in template_content.lower()
        
        print(f"JavaScript script tags found: {has_script_tag}")
        print(f"Event listeners found: {has_event_listeners}")
        print(f"Ripple effect found: {has_ripple_effect}")
        print(f"Loading state found: {has_loading_state}")
        
        return has_script_tag and has_event_listeners
    except Exception as e:
        print(f"Error checking JavaScript: {e}")
        return False

def main():
    """Run all tests"""
    print("🔍 Testing Clickable Status Cards Implementation\n")
    
    tests = [
        ("Status Card Links", test_status_card_links),
        ("CSS Styling", test_css_styling),
        ("JavaScript Functionality", test_javascript_functionality),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        result = test_func()
        results.append(result)
        print(f"{'✅ PASSED' if result else '❌ FAILED'}\n")
    
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
