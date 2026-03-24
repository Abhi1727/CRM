import re
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional
from django.db import models
from dashboard.models import Lead


class DuplicateDetector:
    """
    Enhanced duplicate detection service for CRM leads.
    Provides multiple levels of duplicate detection with configurable sensitivity.
    """
    
    def __init__(self, company_id: int):
        self.company_id = company_id
    
    def find_exact_duplicates(self, mobile: str = None, email: str = None) -> List[Lead]:
        """
        Find exact duplicates based on mobile or email match.
        """
        duplicates = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False
        )
        
        if mobile:
            mobile = self.normalize_phone_number(mobile)
            duplicates = duplicates.filter(mobile=mobile)
        
        if email:
            duplicates = duplicates.filter(email__iexact=email.lower().strip())
        
        return list(duplicates)
    
    def find_potential_duplicates(self, name: str = None, mobile: str = None, email: str = None) -> List[Lead]:
        """
        Find potential duplicates using fuzzy matching on names and exact matching on contact info.
        """
        if not name and not mobile and not email:
            return []
        
        duplicates = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False
        )
        
        # Filter by mobile if provided
        if mobile:
            mobile = self.normalize_phone_number(mobile)
            mobile_matches = duplicates.filter(mobile=mobile)
            if mobile_matches.exists():
                return list(mobile_matches)
        
        # Filter by email if provided
        if email:
            email_matches = duplicates.filter(email__iexact=email.lower().strip())
            if email_matches.exists():
                return list(email_matches)
        
        # If no exact matches, try fuzzy name matching
        if name:
            potential_matches = []
            all_leads = Lead.objects.filter(
                company_id=self.company_id,
                deleted=False
            )
            
            for lead in all_leads:
                if lead.name and self.calculate_name_similarity(name, lead.name) > 0.8:
                    potential_matches.append(lead)
            
            return potential_matches
        
        return []
    
    def find_related_leads(self, address: str = None, city: str = None, company: str = None) -> List[Lead]:
        """
        Find related leads based on address, city, or company matching.
        """
        if not address and not city and not company:
            return []
        
        duplicates = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False
        )
        
        if address:
            duplicates = duplicates.filter(address__iexact=address.strip())
        
        if city:
            duplicates = duplicates.filter(city__iexact=city.strip())
        
        if company:
            # This could match against course_name or a company field if available
            duplicates = duplicates.filter(course_name__iexact=company.strip())
        
        return list(duplicates)
    
    def normalize_phone_number(self, phone: str) -> str:
        """
        Normalize phone number to a standard format.
        Removes all non-numeric characters and handles country codes.
        """
        if not phone:
            return ""
        
        # Remove all non-numeric characters
        phone = re.sub(r'[^\d]', '', phone)
        
        # Remove leading zeros
        phone = phone.lstrip('0')
        
        # Handle Indian mobile numbers (10 digits)
        if len(phone) == 10:
            return phone
        
        # Handle numbers with country code (e.g., +91 for India)
        if len(phone) == 11 and phone.startswith('91'):
            return phone[2:]  # Remove '91' prefix
        
        if len(phone) == 12 and phone.startswith('091'):
            return phone[3:]  # Remove '091' prefix
        
        # For other formats, return as is or last 10 digits
        if len(phone) > 10:
            return phone[-10:]
        
        return phone
    
    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two names using SequenceMatcher.
        Returns a float between 0.0 and 1.0.
        """
        if not name1 or not name2:
            return 0.0
        
        # Clean and normalize names
        name1 = self._clean_name(name1)
        name2 = self._clean_name(name2)
        
        # Calculate similarity
        return SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
    
    def calculate_email_similarity(self, email1: str, email2: str) -> float:
        """
        Calculate similarity between two emails based on domain and username.
        Returns a float between 0.0 and 1.0.
        """
        if not email1 or not email2:
            return 0.0
        
        email1 = email1.lower().strip()
        email2 = email2.lower().strip()
        
        # Exact match
        if email1 == email2:
            return 1.0
        
        # Check domain similarity
        domain1 = email1.split('@')[-1] if '@' in email1 else ''
        domain2 = email2.split('@')[-1] if '@' in email2 else ''
        
        if domain1 and domain2:
            domain_similarity = SequenceMatcher(None, domain1, domain2).ratio()
            
            # If domains are very similar, check username similarity
            if domain_similarity > 0.8:
                username1 = email1.split('@')[0] if '@' in email1 else ''
                username2 = email2.split('@')[0] if '@' in email2 else ''
                username_similarity = SequenceMatcher(None, username1, username2).ratio()
                
                # Weight domain more heavily than username
                return (domain_similarity * 0.7) + (username_similarity * 0.3)
        
        return 0.0
    
    def _clean_name(self, name: str) -> str:
        """
        Clean and normalize name for comparison.
        """
        if not name:
            return ""
        
        # Remove extra whitespace and convert to lowercase
        name = ' '.join(name.split()).lower()
        
        # Remove common titles
        titles = ['mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'madam']
        for title in titles:
            name = re.sub(rf'\b{title}\.?\s*', '', name)
        
        # Remove special characters but keep spaces
        name = re.sub(r'[^\w\s]', '', name)
        
        return name.strip()
    
    def detect_duplicates_for_lead(self, lead_data: Dict) -> Dict:
        """
        Comprehensive duplicate detection for a single lead.
        Returns a dictionary with duplicate information.
        """
        name = lead_data.get('name', '').strip()
        mobile = lead_data.get('mobile', '').strip()
        email = lead_data.get('email', '').strip()
        address = lead_data.get('address', '').strip()
        city = lead_data.get('city', '').strip()
        company = lead_data.get('company', '').strip() or lead_data.get('course_name', '').strip()
        
        result = {
            'status': 'new',
            'duplicates': [],
            'duplicate_type': None,
            'confidence': 0.0
        }
        
        # Check for exact duplicates
        exact_duplicates = self.find_exact_duplicates(mobile, email)
        if exact_duplicates:
            result['status'] = 'exact_duplicate'
            result['duplicate_type'] = 'EXACT'
            result['confidence'] = 1.0
            result['duplicates'] = [
                {
                    'id': dup.id_lead,
                    'name': dup.name,
                    'mobile': dup.mobile,
                    'email': dup.email,
                    'status': dup.status,
                    'created_at': dup.created_at.isoformat() if dup.created_at else None
                }
                for dup in exact_duplicates
            ]
            return result
        
        # Check for potential duplicates
        potential_duplicates = self.find_potential_duplicates(name, mobile, email)
        if potential_duplicates:
            result['status'] = 'potential_duplicate'
            result['duplicate_type'] = 'POTENTIAL'
            result['confidence'] = 0.8
            result['duplicates'] = [
                {
                    'id': dup.id_lead,
                    'name': dup.name,
                    'mobile': dup.mobile,
                    'email': dup.email,
                    'status': dup.status,
                    'created_at': dup.created_at.isoformat() if dup.created_at else None,
                    'similarity': self.calculate_name_similarity(name, dup.name) if name else 0.0
                }
                for dup in potential_duplicates
            ]
            return result
        
        # Check for related leads
        related_leads = self.find_related_leads(address, city, company)
        if related_leads:
            result['status'] = 'related'
            result['duplicate_type'] = 'RELATED'
            result['confidence'] = 0.6
            result['duplicates'] = [
                {
                    'id': dup.id_lead,
                    'name': dup.name,
                    'mobile': dup.mobile,
                    'email': dup.email,
                    'status': dup.status,
                    'created_at': dup.created_at.isoformat() if dup.created_at else None
                }
                for dup in related_leads
            ]
        
        return result
    
    def batch_detect_duplicates(self, leads_data: List[Dict]) -> List[Dict]:
        """
        Detect duplicates for multiple leads in batch.
        Returns a list of duplicate detection results.
        """
        results = []
        
        for i, lead_data in enumerate(leads_data):
            result = self.detect_duplicates_for_lead(lead_data)
            result['row_index'] = i
            result['lead_data'] = lead_data
            results.append(result)
        
        return results
