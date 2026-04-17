#!/usr/bin/env python
import os
import csv
from io import StringIO

def test_csv_processing():
    """Test the fixed CSV processing logic"""
    
    files_to_test = [
        "test  (1).csv",
        "../1000_leads_for_import.csv"
    ]
    
    for csv_file in files_to_test:
        print(f"\n=== Testing {csv_file} ===")
        
        if not os.path.exists(csv_file):
            print(f"File not found: {csv_file}")
            continue
            
        try:
            # Simulate the fixed CSV processing logic
            with open(csv_file, 'rb') as file:
                # Read file content first to avoid TextIOWrapper issues
                file_content = file.read()
                
                # Try different encodings for CSV files
                encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
                reader = None
                used_encoding = None
                
                for encoding in encodings:
                    try:
                        # Decode content and create string buffer for CSV reading
                        decoded_content = file_content.decode(encoding)
                        csv_buffer = StringIO(decoded_content)
                        reader = csv.DictReader(csv_buffer)
                        used_encoding = encoding
                        break
                    except UnicodeDecodeError:
                        continue
                
                if not reader:
                    print(f"Unable to read CSV file with any supported encoding")
                    continue
                
                print(f"Successfully read with encoding: {used_encoding}")
                print(f"Fieldnames: {reader.fieldnames}")
                
                # Read first few rows to test name extraction
                for i, row in enumerate(reader):
                    if i >= 3:  # Only test first 3 rows
                        break
                    
                    name = row.get('name', '').strip()
                    mobile = row.get('mobile', '').strip()
                    email = row.get('email', '').strip()
                    
                    print(f"Row {i+1}:")
                    print(f"  Name: '{name}'")
                    print(f"  Mobile: '{mobile}'")
                    print(f"  Email: '{email}'")
                    
                    if not name and mobile:
                        print(f"  ⚠️  WARNING: Name is empty but mobile exists!")
                    elif name:
                        print(f"  ✅ Name successfully extracted")
                
        except Exception as e:
            print(f"Error processing {csv_file}: {e}")

if __name__ == "__main__":
    test_csv_processing()
