#!/usr/bin/env python3
"""
Test script to verify copy/paste functionality is working in the CRM.
This script checks the CSS and JavaScript files for proper copy-friendly settings.
"""

import os
import re
import sys

def check_css_file():
    """Check if dashboard.css has the copy-friendly rules."""
    css_file = '/root/CRM/crm_project/static/css/dashboard.css'
    
    if not os.path.exists(css_file):
        print(f"ERROR: CSS file not found: {css_file}")
        return False
    
    with open(css_file, 'r') as f:
        content = f.read()
    
    # Check for universal copy-friendly rules
    universal_rules = [
        r'\*\s*\{[^}]*user-select:\s*auto\s*!important',
        r'body\s*,\s*div\s*,\s*span',
        r'user-select:\s*text\s*!important',
        r'-webkit-user-select:\s*text\s*!important',
        r'-moz-user-select:\s*text\s*!important',
        r'-ms-user-select:\s*text\s*!important',
        r'-webkit-touch-callout:\s*text\s*!important'
    ]
    
    missing_rules = []
    for rule in universal_rules:
        if not re.search(rule, content, re.IGNORECASE):
            missing_rules.append(rule)
    
    if missing_rules:
        print("WARNING: Missing CSS rules:")
        for rule in missing_rules:
            print(f"  - {rule}")
        return False
    else:
        print("SUCCESS: All copy-friendly CSS rules found")
        return True

def check_js_file():
    """Check if copy-fix.js exists and has the necessary functions."""
    js_file = '/root/CRM/crm_project/static/js/copy-fix.js'
    
    if not os.path.exists(js_file):
        print(f"ERROR: JavaScript file not found: {js_file}")
        return False
    
    with open(js_file, 'r') as f:
        content = f.read()
    
    # Check for key JavaScript functions
    js_functions = [
        'addEventListener.*contextmenu',
        'addEventListener.*copy',
        'addEventListener.*cut',
        'addEventListener.*paste',
        'addEventListener.*selectstart',
        'preventDefault',
        'oncontextmenu.*=.*null',
        'onselectstart.*=.*null'
    ]
    
    missing_functions = []
    for func in js_functions:
        if not re.search(func, content, re.IGNORECASE):
            missing_functions.append(func)
    
    if missing_functions:
        print("WARNING: Missing JavaScript functions:")
        for func in missing_functions:
            print(f"  - {func}")
        return False
    else:
        print("SUCCESS: All copy-fix JavaScript functions found")
        return True

def check_template_files():
    """Check if templates include the copy-fix script."""
    templates = [
        '/root/CRM/crm_project/templates/dashboard/base_dashboard.html',
        '/root/CRM/crm_project/templates/base.html'
    ]
    
    all_good = True
    for template in templates:
        if not os.path.exists(template):
            print(f"WARNING: Template not found: {template}")
            all_good = False
            continue
        
        with open(template, 'r') as f:
            content = f.read()
        
        if 'copy-fix.js' not in content:
            print(f"WARNING: Template missing copy-fix.js: {template}")
            all_good = False
        else:
            print(f"SUCCESS: Template includes copy-fix.js: {template}")
    
    return all_good

def main():
    print("=== Copy/Paste Functionality Test ===")
    print()
    
    css_ok = check_css_file()
    print()
    
    js_ok = check_js_file()
    print()
    
    templates_ok = check_template_files()
    print()
    
    if css_ok and js_ok and templates_ok:
        print("SUCCESS: All copy/paste fixes are properly implemented!")
        print()
        print("Next steps:")
        print("1. Restart the Django server")
        print("2. Test copy functionality in the browser")
        print("3. Use the test page: /test_copy_functionality.html")
        return 0
    else:
        print("ERROR: Some copy/paste fixes are missing!")
        return 1

if __name__ == '__main__':
    sys.exit(main())
