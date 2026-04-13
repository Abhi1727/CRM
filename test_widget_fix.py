#!/usr/bin/env python
"""
Test script to verify TeamLeadSelectWidget fix
"""
import os
import sys
import django

# Add project path
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from accounts.forms import TeamLeadSelectWidget
from accounts.models import User

def test_widget():
    """Test the TeamLeadSelectWidget"""
    print("Testing TeamLeadSelectWidget...")
    
    # Create a test widget
    widget = TeamLeadSelectWidget()
    
    # Test with different value types
    test_values = [
        1,  # Integer
        "2",  # String
        None,  # None
    ]
    
    for value in test_values:
        try:
            option = widget.create_option('test_field', value, 'Test Label', False, 0)
            print(f"✅ Value {value!r}: Success")
            if 'data-manager-id' in option.get('attrs', {}):
                print(f"   - Manager ID: {option['attrs']['data-manager-id']}")
        except Exception as e:
            print(f"❌ Value {value!r}: Error - {e}")
    
    print("Widget test completed!")

if __name__ == '__main__':
    test_widget()
