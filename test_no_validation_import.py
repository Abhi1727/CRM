#!/usr/bin/env python
"""Test script to verify that import validation removal works correctly"""

import os
import sys
import django

# Setup Django
sys.path.append('crm_project')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from io import StringIO
from dashboard.views import ImportView

def test_csv_import_no_validation():
    """Test that CSV import accepts rows with missing data"""
    
    # Create test CSV content with missing required fields
    csv_content = """name,mobile,email,address
John Doe,,,
,9876543210,john@example.com,123 Street
Jane Smith,8765432109,,456 Avenue
,,,789 Road"""
    
    # Create a file-like object
    csv_file = StringIO(csv_content)
    csv_file.name = "test.csv"
    
    # Initialize ImportView
    import_view = ImportView()
    
    # Test the process_file_streaming function
    processed_rows = list(import_view._process_file_streaming(csv_file))
    
    print(f"✅ Successfully processed {len(processed_rows)} rows")
    print("\n📋 Processed data:")
    for i, row in enumerate(processed_rows, 1):
        print(f"Row {i}: name='{row.get('name', '')}', mobile='{row.get('mobile', '')}', email='{row.get('email', '')}'")
    
    # Verify all rows were accepted (no validation)
    assert len(processed_rows) == 4, f"Expected 4 rows, got {len(processed_rows)}"
    
    # Verify missing data is preserved as empty strings
    assert processed_rows[0]['mobile'] == '', "Row 1 mobile should be empty"
    assert processed_rows[0]['email'] == '', "Row 1 email should be empty"
    assert processed_rows[1]['name'] == '', "Row 2 name should be empty"
    assert processed_rows[2]['email'] == '', "Row 3 email should be empty"
    assert processed_rows[3]['name'] == '', "Row 4 name should be empty"
    assert processed_rows[3]['mobile'] == '', "Row 4 mobile should be empty"
    assert processed_rows[3]['email'] == '', "Row 4 email should be empty"
    
    print("\n✅ All validation tests passed!")
    print("✅ Import accepts all data regardless of missing fields")
    return True

if __name__ == "__main__":
    try:
        test_csv_import_no_validation()
        print("\n🎉 SUCCESS: Import validation removal is working correctly!")
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
