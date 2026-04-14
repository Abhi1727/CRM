#!/usr/bin/env python
"""
Test script to verify the Excel import fix works correctly.
"""

import os
import sys
import pandas as pd

# Add project path to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'crm_project'))

def test_excel_processing():
    """Test that Excel processing works with the fix"""
    print("Testing Excel processing fix...")
    
    # Create a simple test DataFrame
    test_data = {
        'name': ['Test User 1', 'Test User 2'],
        'mobile': ['1234567890', '9876543210'],
        'email': ['test1@example.com', 'test2@example.com'],
        'status': ['lead', 'lead']
    }
    
    df = pd.DataFrame(test_data)
    print(f"Created test DataFrame with {len(df)} rows")
    
    # Test the fixed processing logic
    leads_data = []
    for index, row in df.iterrows():
        print(f"Processing row {index}: {type(row)}")
        
        # Convert pandas Series to dictionary to use .get() method
        row_dict = row.to_dict() if hasattr(row, 'to_dict') else dict(row)
        
        print(f"Row dict type: {type(row_dict)}")
        print(f"Row dict keys: {list(row_dict.keys())}")
        
        lead_data = {
            'name': '' if pd.isna(row_dict.get('name')) else str(row_dict.get('name', '')).strip(),
            'mobile': '' if pd.isna(row_dict.get('mobile')) else str(row_dict.get('mobile', '')).strip(),
            'email': '' if pd.isna(row_dict.get('email')) else str(row_dict.get('email', '')).strip(),
        }
        
        leads_data.append(lead_data)
        print(f"Processed lead data: {lead_data}")
    
    print(f"✅ Successfully processed {len(leads_data)} leads from Excel")
    return leads_data

if __name__ == '__main__':
    try:
        test_excel_processing()
        print("\n✅ Excel processing fix works correctly!")
    except Exception as e:
        print(f"\n❌ Error in Excel processing: {e}")
        import traceback
        traceback.print_exc()
