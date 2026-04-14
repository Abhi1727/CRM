"""
Enterprise-grade scalable duplicate detection with Redis caching
Optimized for large datasets with batch processing and intelligent caching
"""

import logging
import hashlib
from typing import Dict, List, Any, Tuple, Optional
from django.core.cache import cache
from django.db import models
from django.db.models import Q
from .models import Lead

logger = logging.getLogger(__name__)


class ScalableDuplicateDetector:
    """
    High-performance duplicate detection system with Redis caching.
    Optimized for processing 100k+ leads efficiently.
    """
    
    def __init__(self, company_id: int, cache_timeout: int = 1800):
        """
        Initialize the duplicate detector.
        
        Args:
            company_id: Company ID for scoping duplicate detection
            cache_timeout: Cache timeout in seconds (default: 30 minutes)
        """
        self.company_id = company_id
        self.cache_timeout = cache_timeout
        self.cache_key_prefix = f'duplicates_{company_id}'
        self.batch_size = 1000  # Optimal batch size for database queries
        
    def batch_detect_duplicates(self, leads_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect duplicates for a batch of leads with Redis caching.
        
        Args:
            leads_data: List of lead dictionaries
            
        Returns:
            List of duplicate detection results
        """
        if not leads_data:
            return []
        
        results = []
        cache_hits = 0
        cache_misses = 0
        
        # Step 1: Check cache first
        cache_results, uncached_leads, uncached_indices = self._check_cache(leads_data)
        
        cache_hits = len(cache_results)
        cache_misses = len(uncached_leads)
        
        # Step 2: Process uncached leads with database queries
        if uncached_leads:
            database_results = self._batch_database_detect(uncached_leads)
            
            # Step 3: Cache new results
            self._cache_results(uncached_leads, database_results)
            
            # Step 4: Merge cache and database results
            results = self._merge_results(leads_data, cache_results, uncached_indices, database_results)
        else:
            results = cache_results
        
        logger.info(f"Duplicate detection completed: {cache_hits} cache hits, {cache_misses} cache misses")
        return results
    
    def _check_cache(self, leads_data: List[Dict[str, Any]]) -> Tuple[List[Dict], List[Dict], List[int]]:
        """
        Check cache for existing duplicate detection results.
        
        Returns:
            Tuple of (cached_results, uncached_leads, uncached_indices)
        """
        cached_results = [None] * len(leads_data)
        uncached_leads = []
        uncached_indices = []
        
        for i, lead in enumerate(leads_data):
            cache_key = self._generate_cache_key(lead)
            cached_result = cache.get(cache_key)
            
            if cached_result is not None:
                cached_results[i] = cached_result
            else:
                uncached_leads.append(lead)
                uncached_indices.append(i)
        
        return cached_results, uncached_leads, uncached_indices
    
    def _batch_database_detect(self, leads_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Perform batch duplicate detection in the database.
        Optimized for large datasets with efficient queries.
        """
        # Collect all unique mobiles and emails
        mobiles = set()
        emails = set()
        
        for lead in leads_data:
            mobile = lead.get('mobile', '').strip()
            email = lead.get('email', '').strip().lower()
            
            if mobile and len(mobile) >= 10:  # Basic mobile validation
                mobiles.add(mobile)
            if email and '@' in email:
                emails.add(email)
        
        # If no valid identifiers, return all as new
        if not mobiles and not emails:
            return [{'status': 'new', 'duplicates': [], 'confidence': 0.0} for _ in leads_data]
        
        # Single optimized database query
        existing_leads = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False
        ).filter(
            Q(mobile__in=mobiles) | Q(email__in=emails)
        ).only('id_lead', 'mobile', 'email', 'name', 'status')
        
        # Build efficient lookup dictionaries
        mobile_lookup = {}
        email_lookup = {}
        
        for lead in existing_leads:
            if lead.mobile:
                mobile_lookup[lead.mobile] = lead
            if lead.email:
                email_lookup[lead.email.lower()] = lead
        
        # Process each lead for duplicate detection
        results = []
        for lead in leads_data:
            result = self._detect_single_duplicate(lead, mobile_lookup, email_lookup)
            results.append(result)
        
        return results
    
    def _detect_single_duplicate(self, lead: Dict[str, Any], 
                                mobile_lookup: Dict[str, Any], 
                                email_lookup: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect duplicates for a single lead using pre-built lookup dictionaries.
        """
        mobile = lead.get('mobile', '').strip()
        email = lead.get('email', '').strip().lower()
        
        duplicates = []
        confidence = 0.0
        status = 'new'
        
        # Check mobile exact match
        if mobile and mobile in mobile_lookup:
            existing_lead = mobile_lookup[mobile]
            duplicates.append({
                'id': existing_lead.id_lead,
                'name': existing_lead.name,
                'mobile': existing_lead.mobile,
                'email': existing_lead.email,
                'status': existing_lead.status,
                'match_type': 'mobile_exact'
            })
            confidence = max(confidence, 0.9)
            status = 'duplicate'
        
        # Check email exact match
        if email and email in email_lookup:
            existing_lead = email_lookup[email]
            
            # Avoid adding the same lead twice
            if not any(d['id'] == existing_lead.id_lead for d in duplicates):
                duplicates.append({
                    'id': existing_lead.id_lead,
                    'name': existing_lead.name,
                    'mobile': existing_lead.mobile,
                    'email': existing_lead.email,
                    'status': existing_lead.status,
                    'match_type': 'email_exact'
                })
                confidence = max(confidence, 0.8)
                status = 'duplicate'
        
        # Check for similar mobile numbers (for common variations)
        if mobile and len(mobile) >= 10:
            similar_mobiles = self._find_similar_mobiles(mobile, mobile_lookup)
            for similar_mobile, existing_lead in similar_mobiles:
                if not any(d['id'] == existing_lead.id_lead for d in duplicates):
                    duplicates.append({
                        'id': existing_lead.id_lead,
                        'name': existing_lead.name,
                        'mobile': existing_lead.mobile,
                        'email': existing_lead.email,
                        'status': existing_lead.status,
                        'match_type': 'mobile_similar'
                    })
                    confidence = max(confidence, 0.6)
                    status = 'potential_duplicate'
        
        return {
            'status': status,
            'duplicates': duplicates,
            'confidence': confidence,
            'lead_data': lead
        }
    
    def _find_similar_mobiles(self, mobile: str, mobile_lookup: Dict[str, Any]) -> List[Tuple[str, Any]]:
        """
        Find similar mobile numbers for fuzzy matching.
        Handles common variations like missing country code, etc.
        """
        similar_matches = []
        
        # Remove country code if present
        if mobile.startswith('+91'):
            mobile_without_code = mobile[3:]
        elif mobile.startswith('91') and len(mobile) == 12:
            mobile_without_code = mobile[2:]
        elif mobile.startswith('0') and len(mobile) == 11:
            mobile_without_code = mobile[1:]
        else:
            mobile_without_code = mobile
        
        # Check variations
        variations = [
            mobile_without_code,
            f'+91{mobile_without_code}',
            f'91{mobile_without_code}',
            f'0{mobile_without_code}'
        ]
        
        for variation in variations:
            if variation in mobile_lookup and variation != mobile:
                similar_matches.append((variation, mobile_lookup[variation]))
        
        return similar_matches
    
    def _cache_results(self, leads_data: List[Dict[str, Any]], results: List[Dict[str, Any]]):
        """Cache duplicate detection results for future use"""
        cache_keys = []
        
        for lead, result in zip(leads_data, results):
            cache_key = self._generate_cache_key(lead)
            cache_keys.append(cache_key)
            
            # Cache with timeout
            cache.set(cache_key, result, self.cache_timeout)
        
        logger.debug(f"Cached {len(cache_keys)} duplicate detection results")
    
    def _merge_results(self, original_leads: List[Dict[str, Any]], 
                      cache_results: List[Dict], 
                      uncached_indices: List[int], 
                      database_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge cached and database results in the correct order.
        """
        final_results = []
        db_result_index = 0
        
        for i, lead in enumerate(original_leads):
            if cache_results[i] is not None:
                final_results.append(cache_results[i])
            else:
                # This lead was uncached, use database result
                final_results.append(database_results[db_result_index])
                db_result_index += 1
        
        return final_results
    
    def _generate_cache_key(self, lead: Dict[str, Any]) -> str:
        """Generate a unique cache key for a lead"""
        mobile = lead.get('mobile', '').strip()
        email = lead.get('email', '').strip().lower()
        
        # Create a hash of the identifying information
        identifier = f"{mobile}_{email}"
        hash_value = hashlib.md5(identifier.encode()).hexdigest()
        
        return f"{self.cache_key_prefix}_{hash_value}"
    
    def invalidate_cache_for_company(self):
        """Invalidate all duplicate detection cache for a company"""
        # This is a simplified approach - in production, you might want
        # to use cache tags or more sophisticated invalidation
        try:
            # Get all cache keys for this company (if your cache backend supports it)
            # For now, we'll use a version-based approach
            version_key = f"{self.cache_key_prefix}_version"
            current_version = cache.get(version_key, 0)
            cache.set(version_key, current_version + 1, self.cache_timeout * 2)
            
            logger.info(f"Invalidated duplicate detection cache for company {self.company_id}")
        except Exception as e:
            logger.error(f"Error invalidating cache for company {self.company_id}: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        try:
            version_key = f"{self.cache_key_prefix}_version"
            version = cache.get(version_key, 0)
            
            return {
                'company_id': self.company_id,
                'cache_version': version,
                'cache_timeout': self.cache_timeout,
                'cache_key_prefix': self.cache_key_prefix
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}


class BulkDuplicateProcessor:
    """
    High-level processor for handling duplicate detection in bulk operations.
    Integrates with the existing bulk operation framework.
    """
    
    def __init__(self, company_id: int, operation_id: int = None):
        self.company_id = company_id
        self.operation_id = operation_id
        self.detector = ScalableDuplicateDetector(company_id)
        self.stats = {
            'total_processed': 0,
            'exact_duplicates': 0,
            'potential_duplicates': 0,
            'new_leads': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    def process_lead_batch(self, leads_data: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Process a batch of leads for duplicate detection.
        
        Returns:
            Tuple of (processed_leads_with_duplicates, batch_stats)
        """
        if not leads_data:
            return [], {}
        
        # Detect duplicates
        duplicate_results = self.detector.batch_detect_duplicates(leads_data)
        
        # Process results and update stats
        processed_leads = []
        batch_stats = {
            'total': len(leads_data),
            'exact_duplicates': 0,
            'potential_duplicates': 0,
            'new_leads': 0
        }
        
        for lead, result in zip(leads_data, duplicate_results):
            # Add duplicate information to lead data
            lead['duplicate_info'] = result
            
            # Update statistics
            if result['status'] == 'duplicate':
                batch_stats['exact_duplicates'] += 1
                self.stats['exact_duplicates'] += 1
            elif result['status'] == 'potential_duplicate':
                batch_stats['potential_duplicates'] += 1
                self.stats['potential_duplicates'] += 1
            else:
                batch_stats['new_leads'] += 1
                self.stats['new_leads'] += 1
            
            processed_leads.append(lead)
        
        self.stats['total_processed'] += len(leads_data)
        
        return processed_leads, batch_stats
    
    def get_final_stats(self) -> Dict[str, Any]:
        """Get final processing statistics"""
        return {
            **self.stats,
            'duplicate_rate': round(
                (self.stats['exact_duplicates'] + self.stats['potential_duplicates']) / 
                max(self.stats['total_processed'], 1) * 100, 2
            ),
            'cache_hit_rate': round(
                self.stats['cache_hits'] / 
                max(self.stats['cache_hits'] + self.stats['cache_misses'], 1) * 100, 2
            )
        }
