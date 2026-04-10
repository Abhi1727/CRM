"""
Comprehensive tests for duplicate detection pagination functionality.
Tests edge cases, performance, and user experience scenarios.
"""

import pytest
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from dashboard.models import Lead
from services.duplicate_detector import DuplicateDetector

User = get_user_model()


class DuplicatePaginationTestCase(TestCase):
    """Test pagination functionality for duplicate detection views."""
    
    def setUp(self):
        """Set up test data with various duplicate scenarios."""
        self.owner = User.objects.create_user(
            username='testowner',
            email='owner@test.com',
            password='testpass123',
            role='owner',
            company_id=1
        )
        
        self.manager = User.objects.create_user(
            username='testmanager',
            email='manager@test.com',
            password='testpass123',
            role='manager',
            company_id=1,
            manager=self.owner
        )
        
        self.agent = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='testpass123',
            role='agent',
            company_id=1,
            team_lead=self.manager
        )
        
        self.client = Client()
        self.client.login(username='testowner', password='testpass123')
        
        # Create test leads with duplicates
        self.create_test_duplicates()
    
    def create_test_duplicates(self):
        """Create test leads with various duplicate scenarios."""
        base_time = timezone.now()
        
        # Create 50 duplicate groups (100 leads total)
        for i in range(50):
            group_id = f'test_group_{i}'
            
            # Create 2 leads per group
            for j in range(2):
                Lead.objects.create(
                    id_lead=1000 + i * 2 + j,
                    name=f'Test Lead {i}-{j}',
                    email=f'test{i}@example.com',
                    mobile=f'987654321{i:02d}',
                    company_id=1,
                    assigned_user=self.agent if i % 2 == 0 else self.manager,
                    duplicate_status='exact_duplicate',
                    duplicate_group_id=group_id,
                    duplicate_resolution_status='pending' if i % 3 != 0 else 'resolved',
                    created_at=base_time + timedelta(minutes=i)
                )
        
        # Create some potential duplicates
        for i in range(10):
            Lead.objects.create(
                id_lead=2000 + i,
                name=f'Potential {i}',
                email=f'potential{i}@example.com',
                mobile='9876543299',
                company_id=1,
                assigned_user=self.agent,
                duplicate_status='potential_duplicate',
                duplicate_group_id=f'potential_group_{i}',
                duplicate_resolution_status='pending',
                created_at=base_time + timedelta(hours=i)
            )
    
    def test_leads_duplicates_pagination_basic(self):
        """Test basic pagination functionality."""
        url = reverse('dashboard:leads_duplicates')
        
        # Test first page
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'page_obj')
        self.assertContains(response, 'total_groups')
        
        # Test second page
        response = self.client.get(url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        
        # Test page size
        response = self.client.get(url, {'page_size': 10})
        self.assertEqual(response.status_code, 200)
    
    def test_pagination_edge_cases(self):
        """Test pagination edge cases."""
        url = reverse('dashboard:leads_duplicates')
        
        # Test invalid page number
        response = self.client.get(url, {'page': 'invalid'})
        self.assertEqual(response.status_code, 200)  # Should default to page 1
        
        # Test page beyond range
        response = self.client.get(url, {'page': 999})
        self.assertEqual(response.status_code, 200)  # Should show last page
        
        # Test invalid page size
        response = self.client.get(url, {'page_size': 'invalid'})
        self.assertEqual(response.status_code, 200)  # Should default to 20
        
        # Test page size not in allowed list
        response = self.client.get(url, {'page_size': 15})
        self.assertEqual(response.status_code, 200)  # Should default to 20
        
        # Test minimum page size
        response = self.client.get(url, {'page_size': 5})
        self.assertEqual(response.status_code, 200)
        
        # Test maximum page size
        response = self.client.get(url, {'page_size': 500})
        self.assertEqual(response.status_code, 200)
    
    def test_pagination_with_filters(self):
        """Test pagination combined with filters."""
        url = reverse('dashboard:leads_duplicates')
        
        # Test status filter with pagination
        response = self.client.get(url, {
            'status': 'pending',
            'page': 2,
            'page_size': 10
        })
        self.assertEqual(response.status_code, 200)
        
        # Test duplicate type filter with pagination
        response = self.client.get(url, {
            'type': 'exact_duplicate',
            'page': 1,
            'page_size': 25
        })
        self.assertEqual(response.status_code, 200)
        
        # Test combined filters with pagination
        response = self.client.get(url, {
            'status': 'resolved',
            'type': 'exact_duplicate',
            'page': 1,
            'page_size': 50
        })
        self.assertEqual(response.status_code, 200)
    
    def test_role_based_pagination(self):
        """Test pagination for different user roles."""
        urls = [
            reverse('dashboard:leads_duplicates'),
            reverse('dashboard:team_duplicate_leads'),
            reverse('dashboard:my_duplicate_leads')
        ]
        
        # Test as owner
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'page_obj')
        
        # Test as manager
        self.client.login(username='testmanager', password='testpass123')
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'page_obj')
        
        # Test as agent
        self.client.login(username='testagent', password='testpass123')
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'page_obj')
    
    def test_duplicate_detector_paginated_method(self):
        """Test the DuplicateDetector paginated method directly."""
        detector = DuplicateDetector(company_id=1)
        
        # Test basic pagination
        result = detector.find_duplicate_groups_paginated(page=1, page_size=20)
        
        self.assertIn('page_obj', result)
        self.assertIn('total_count', result)
        self.assertIn('groups', result)
        self.assertIn('has_next', result)
        self.assertIn('has_previous', result)
        self.assertIn('num_pages', result)
        self.assertIn('current_page', result)
        
        # Test pagination correctness
        self.assertEqual(result['current_page'], 1)
        self.assertLessEqual(len(result['groups']), 20)
        
        # Test second page
        result2 = detector.find_duplicate_groups_paginated(page=2, page_size=20)
        self.assertEqual(result2['current_page'], 2)
        
        # Ensure different pages have different content
        if result['has_next'] and result2['groups']:
            first_ids = {g['group_id'] for g in result['groups']}
            second_ids = {g['group_id'] for g in result2['groups']}
            # Should have minimal overlap (only possible if groups span pages)
            overlap = first_ids.intersection(second_ids)
            self.assertLessEqual(len(overlap), 1)
    
    def test_performance_with_large_dataset(self):
        """Test pagination performance with large datasets."""
        # Create additional test data
        for i in range(100, 200):  # Create 100 more groups
            group_id = f'perf_group_{i}'
            for j in range(3):  # 3 leads per group
                Lead.objects.create(
                    id_lead=3000 + i * 3 + j,
                    name=f'Perf Lead {i}-{j}',
                    email=f'perf{i}@example.com',
                    mobile=f'98765433{i:02d}',
                    company_id=1,
                    assigned_user=self.agent,
                    duplicate_status='exact_duplicate',
                    duplicate_group_id=group_id,
                    duplicate_resolution_status='pending',
                    created_at=timezone.now() + timedelta(seconds=i)
                )
        
        detector = DuplicateDetector(company_id=1)
        
        # Test performance with different page sizes
        import time
        
        start_time = time.time()
        result = detector.find_duplicate_groups_paginated(page=1, page_size=50)
        end_time = time.time()
        
        # Should complete within reasonable time (adjust threshold as needed)
        self.assertLess(end_time - start_time, 2.0)  # 2 seconds max
        self.assertLessEqual(len(result['groups']), 50)
        
        # Test performance with filters
        start_time = time.time()
        result = detector.find_duplicate_groups_paginated(
            page=1, 
            page_size=20,
            status='pending'
        )
        end_time = time.time()
        
        self.assertLess(end_time - start_time, 1.5)  # 1.5 seconds max
    
    def test_pagination_parameter_persistence(self):
        """Test that pagination parameters persist across page navigation."""
        url = reverse('dashboard:leads_duplicates')
        
        # Navigate with specific parameters
        response = self.client.get(url, {
            'status': 'pending',
            'type': 'exact_duplicate',
            'page_size': 10,
            'page': 2
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Check that pagination links preserve parameters
        content = response.content.decode()
        
        # Should contain the status parameter
        self.assertIn('status=pending', content)
        
        # Should contain the type parameter
        self.assertIn('type=exact_duplicate', content)
        
        # Should contain the page_size parameter
        self.assertIn('page_size=10', content)
    
    def test_empty_results_pagination(self):
        """Test pagination when no results are found."""
        url = reverse('dashboard:leads_duplicates')
        
        # Filter for non-existent status
        response = self.client.get(url, {
            'status': 'nonexistent',
            'type': 'nonexistent'
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Should handle empty results gracefully
        content = response.content.decode()
        self.assertIn('No duplicate groups found', content)
    
    def test_single_result_pagination(self):
        """Test pagination when only one result exists."""
        # Delete all but one duplicate group
        Lead.objects.filter(
            duplicate_status__in=['exact_duplicate', 'potential_duplicate']
        ).exclude(duplicate_group_id='test_group_0').delete()
        
        url = reverse('dashboard:leads_duplicates')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Should handle single result gracefully
        content = response.content.decode()
        # Should not show pagination controls for single page
        self.assertNotIn('page-btn', content)
    
    def test_url_parameter_encoding(self):
        """Test that URL parameters are properly encoded."""
        url = reverse('dashboard:leads_duplicates')
        
        # Test with special characters in filters
        response = self.client.get(url, {
            'status': 'pending',
            'page_size': 20,
            'page': 1
        })
        
        self.assertEqual(response.status_code, 200)
        
        # Check that pagination links are properly encoded
        content = response.content.decode()
        
        # Should not contain double ampersands
        self.assertNotIn('&&', content)
        
        # Should properly encode parameters
        self.assertIn('page_size=20', content)
    
    @patch('services.duplicate_detector.DuplicateDetector.find_duplicate_groups_paginated')
    def test_error_handling_in_pagination(self, mock_method):
        """Test error handling in pagination."""
        # Mock the method to raise an exception
        mock_method.side_effect = Exception("Database error")
        
        url = reverse('dashboard:leads_duplicates')
        
        # Should handle the error gracefully
        with self.assertRaises(Exception):
            self.client.get(url)
    
    def test_session_storage_integration(self):
        """Test that session storage works for expanded groups."""
        url = reverse('dashboard:leads_duplicates')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        
        # Check that JavaScript for session storage is included
        content = response.content.decode()
        self.assertIn('sessionStorage', content)
        self.assertIn('expandedDuplicateGroups', content)


class DuplicatePaginationIntegrationTestCase(TestCase):
    """Integration tests for duplicate pagination with real data flow."""
    
    def setUp(self):
        """Set up integration test environment."""
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@test.com',
            password='testpass123',
            role='owner',
            company_id=1
        )
        
        self.client = Client()
        self.client.login(username='integrationuser', password='testpass123')
    
    def test_end_to_end_pagination_flow(self):
        """Test complete pagination flow from user interaction to data retrieval."""
        # Create test data
        self.create_integration_data()
        
        url = reverse('dashboard:leads_duplicates')
        
        # Step 1: Load first page
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        # Step 2: Change page size
        response = self.client.get(url, {'page_size': 10})
        self.assertEqual(response.status_code, 200)
        
        # Step 3: Navigate to second page
        response = self.client.get(url, {'page': 2, 'page_size': 10})
        self.assertEqual(response.status_code, 200)
        
        # Step 4: Apply filter
        response = self.client.get(url, {
            'page': 1,
            'page_size': 10,
            'status': 'pending'
        })
        self.assertEqual(response.status_code, 200)
        
        # Step 5: Navigate with filter
        response = self.client.get(url, {
            'page': 2,
            'page_size': 10,
            'status': 'pending'
        })
        self.assertEqual(response.status_code, 200)
    
    def create_integration_data(self):
        """Create realistic test data for integration testing."""
        base_time = timezone.now()
        
        # Create realistic duplicate scenarios
        scenarios = [
            ('john.doe', 'john@example.com', '9876543210'),
            ('jane.smith', 'jane@example.com', '9876543211'),
            ('bob.wilson', 'bob@example.com', '9876543212'),
        ]
        
        for i, (name, email, mobile) in enumerate(scenarios):
            # Create duplicate group
            group_id = f'integration_group_{i}'
            
            for j in range(2):  # 2 duplicates per scenario
                Lead.objects.create(
                    id_lead=4000 + i * 2 + j,
                    name=f'{name} {j}',
                    email=email,
                    mobile=mobile,
                    company_id=1,
                    assigned_user=self.user,
                    duplicate_status='exact_duplicate',
                    duplicate_group_id=group_id,
                    duplicate_resolution_status='pending' if i % 2 == 0 else 'resolved',
                    created_at=base_time + timedelta(hours=i)
                )


if __name__ == '__main__':
    pytest.main([__file__])
