#!/usr/bin/env python3
"""
Test script to verify various filter combinations work correctly
with the Select All Filtered functionality.
"""

import os
import sys

# Setup Django first
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import django
django.setup()

from django.http import QueryDict
from urllib.parse import urlencode
from dashboard.views import _extract_lead_filters

def test_search_plus_status():
    """Test search query combined with status filter"""
    print("Testing search + status filter...")
    
    # Simulate JavaScript getCurrentFilterSnapshot() output
    snapshot_params = [
        ('search', 'john doe'),
        ('status', 'new'),
        ('sort', '-created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['search'] == 'john doe'
    assert filters['status'] == 'new'
    assert filters['sort'] == '-created_at'
    assert filters['country'] == ''
    assert filters['course'] == ''
    
    print("  PASSED")

def test_date_range_plus_country():
    """Test date range combined with country filter"""
    print("Testing date range + country filter...")
    
    snapshot_params = [
        ('start_date', '2024-01-01'),
        ('end_date', '2024-03-31'),
        ('country', 'US'),
        ('sort', 'created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['start_date'] == '2024-01-01'
    assert filters['end_date'] == '2024-03-31'
    assert filters['country'] == 'US'
    assert filters['sort'] == 'created_at'
    
    print("  PASSED")

def test_preset_plus_course():
    """Test preset filter combined with course filter"""
    print("Testing preset + course filter...")
    
    snapshot_params = [
        ('preset', 'my'),
        ('course', 'Data Science'),
        ('page_size', '50'),
        ('sort', '-created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['preset'] == 'my'
    assert filters['course'] == 'Data Science'
    assert filters['page_size'] == 50
    assert filters['sort'] == '-created_at'
    
    print("  PASSED")

def test_all_filters_combined():
    """Test all possible filters combined"""
    print("Testing all filters combined...")
    
    snapshot_params = [
        ('search', 'test user'),
        ('status', 'contacted'),
        ('country', 'IN'),
        ('course', 'Cyber Security'),
        ('start_date', '2024-02-01'),
        ('end_date', '2024-04-30'),
        ('assigned_user', '3'),
        ('preset', 'team'),
        ('page_size', '100'),
        ('sort', '-created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['search'] == 'test user'
    assert filters['status'] == 'contacted'
    assert filters['country'] == 'IN'
    assert filters['course'] == 'Cyber Security'
    assert filters['start_date'] == '2024-02-01'
    assert filters['end_date'] == '2024-04-30'
    assert filters['assigned_user'] == '3'
    assert filters['preset'] == 'team'
    assert filters['page_size'] == 100
    assert filters['sort'] == '-created_at'
    
    print("  PASSED")

def test_empty_and_partial_filters():
    """Test empty filter values and partial combinations"""
    print("Testing empty and partial filters...")
    
    # Test with some empty values (should be handled gracefully)
    snapshot_params = [
        ('search', ''),
        ('status', 'new'),
        ('country', ''),
        ('course', 'DevOps'),
        ('start_date', '2024-01-01'),
        ('end_date', ''),
        ('assigned_user', ''),
        ('preset', ''),
        ('sort', '-created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['search'] == ''
    assert filters['status'] == 'new'
    assert filters['country'] == ''
    assert filters['course'] == 'DevOps'
    assert filters['start_date'] == '2024-01-01'
    assert filters['end_date'] == ''
    assert filters['assigned_user'] == ''
    assert filters['preset'] == ''
    assert filters['sort'] == '-created_at'
    
    print("  PASSED")

def test_url_encoding_decoding():
    """Test that URL encoding/decoding works correctly"""
    print("Testing URL encoding/decoding...")
    
    # Test with special characters that need URL encoding
    snapshot_params = [
        ('search', 'john+doe@email.com'),  # + and @
        ('country', 'United States'),      # space
        ('course', 'Data Science & AI'),   # & and space
        ('sort', '-created_at')
    ]
    
    filter_snapshot = urlencode(snapshot_params)
    print(f"  Encoded snapshot: {filter_snapshot}")
    
    params = QueryDict(filter_snapshot, mutable=False)
    filters = _extract_lead_filters(params)
    
    assert filters['search'] == 'john+doe@email.com'
    assert filters['country'] == 'United States'
    assert filters['course'] == 'Data Science & AI'
    assert filters['sort'] == '-created_at'
    
    print("  PASSED")

def main():
    """Run all filter combination tests"""
    print("=" * 60)
    print("FILTER COMBINATION TESTS")
    print("=" * 60)
    print()
    
    try:
        test_search_plus_status()
        test_date_range_plus_country()
        test_preset_plus_course()
        test_all_filters_combined()
        test_empty_and_partial_filters()
        test_url_encoding_decoding()
        
        print()
        print("=" * 60)
        print("ALL FILTER COMBINATION TESTS PASSED!")
        print("=" * 60)
        print()
        print("Verified functionality:")
        print("  Search + Status filtering")
        print("  Date range + Country filtering")
        print("  Preset + Course filtering")
        print("  All filters combined")
        print("  Empty and partial filters")
        print("  URL encoding/decoding")
        print()
        print("The Select All Filtered button will now correctly")
        print("capture and process any combination of filters!")
        
        return True
        
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
