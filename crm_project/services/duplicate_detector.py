import re
import uuid
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional
from django.db import models
from django.utils import timezone
from dashboard.models import Lead
from accounts.models import User


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
        name = str(lead_data.get('name', '')).strip()
        mobile = str(lead_data.get('mobile', '')).strip()
        email = str(lead_data.get('email', '')).strip()
        address = str(lead_data.get('address', '')).strip()
        city = str(lead_data.get('city', '')).strip()
        company = str(lead_data.get('company', '')).strip() or str(lead_data.get('course_name', '')).strip()
        
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
    
    def create_duplicate_group(self, lead_ids: List[int], group_type: str = 'auto') -> str:
        """
        Create a duplicate group for the given lead IDs.
        Returns the group ID.
        """
        if not lead_ids:
            return None
        
        # Generate unique group ID
        group_id = f"{group_type}_{uuid.uuid4().hex[:8]}_{timezone.now().strftime('%Y%m%d')}"
        
        # Update all leads with the group ID
        Lead.objects.filter(id_lead__in=lead_ids).update(
            duplicate_group_id=group_id,
            duplicate_resolution_status='pending'
        )
        
        return group_id
    
    def find_duplicate_groups(self, status: str = None) -> List[Dict]:
        """
        Find all duplicate groups in the company.
        Returns list of groups with their leads.
        """
        leads = Lead.objects.filter(
            company_id=self.company_id,
            duplicate_status__in=['exact_duplicate', 'potential_duplicate'],
            deleted=False
        ).exclude(duplicate_group_id__isnull=True)
        
        if status:
            leads = leads.filter(duplicate_resolution_status=status)
        
        # Group by duplicate_group_id
        groups = {}
        for lead in leads:
            group_id = lead.duplicate_group_id
            if group_id not in groups:
                groups[group_id] = {
                    'group_id': group_id,
                    'leads': [],
                    'status': lead.duplicate_resolution_status,
                    'created_at': lead.created_at
                }
            groups[group_id]['leads'].append(lead)
        
        return list(groups.values())
    
    def get_duplicate_statistics(self) -> Dict:
        """
        Get duplicate statistics for the company.
        """
        total_leads = Lead.objects.filter(company_id=self.company_id, deleted=False).count()
        duplicate_leads = Lead.objects.filter(
            company_id=self.company_id,
            duplicate_status__in=['exact_duplicate', 'potential_duplicate'],
            deleted=False
        )
        
        stats = {
            'total_leads': total_leads,
            'duplicate_leads_count': duplicate_leads.count(),
            'duplicate_percentage': (duplicate_leads.count() / total_leads * 100) if total_leads > 0 else 0,
            'exact_duplicates': duplicate_leads.filter(duplicate_status='exact_duplicate').count(),
            'potential_duplicates': duplicate_leads.filter(duplicate_status='potential_duplicate').count(),
            'resolved_duplicates': duplicate_leads.filter(duplicate_resolution_status='resolved').count(),
            'pending_duplicates': duplicate_leads.filter(duplicate_resolution_status='pending').count(),
            'ignored_duplicates': duplicate_leads.filter(duplicate_resolution_status='ignored').count(),
        }
        
        # Count groups
        groups = self.find_duplicate_groups()
        stats['duplicate_groups'] = len(groups)
        
        return stats
    
    def auto_group_existing_duplicates(self) -> Dict:
        """
        Automatically group existing duplicates that don't have groups.
        Returns statistics about the grouping process.
        """
        # Find leads with duplicate status but no group
        ungrouped_duplicates = Lead.objects.filter(
            company_id=self.company_id,
            duplicate_status__in=['exact_duplicate', 'potential_duplicate'],
            duplicate_group_id__isnull=True,
            deleted=False
        )
        
        groups_created = 0
        leads_grouped = 0
        
        # Group by exact matches first
        exact_duplicates = ungrouped_duplicates.filter(duplicate_status='exact_duplicate')
        
        # Group by mobile number
        mobile_groups = {}
        for lead in exact_duplicates:
            if lead.mobile:
                mobile = self.normalize_phone_number(lead.mobile)
                if mobile not in mobile_groups:
                    mobile_groups[mobile] = []
                mobile_groups[mobile].append(lead.id_lead)
        
        for mobile, lead_ids in mobile_groups.items():
            if len(lead_ids) > 1:
                self.create_duplicate_group(lead_ids, 'mobile_exact')
                groups_created += 1
                leads_grouped += len(lead_ids)
        
        # Group by email
        email_groups = {}
        for lead in exact_duplicates:
            if lead.email:
                email = lead.email.lower().strip()
                if email not in email_groups:
                    email_groups[email] = []
                email_groups[email].append(lead.id_lead)
        
        for email, lead_ids in email_groups.items():
            if len(lead_ids) > 1:
                self.create_duplicate_group(lead_ids, 'email_exact')
                groups_created += 1
                leads_grouped += len(lead_ids)
        
        return {
            'groups_created': groups_created,
            'leads_grouped': leads_grouped,
            'mobile_groups': len(mobile_groups),
            'email_groups': len(email_groups)
        }
    
    def get_reassignment_recommendations(self, duplicate_group_id: str) -> Dict:
        """
        Get reassignment recommendations for a duplicate group.
        Analyzes assignment history and suggests best candidates.
        """
        leads = Lead.objects.filter(
            duplicate_group_id=duplicate_group_id,
            company_id=self.company_id
        )
        
        if not leads.exists():
            return {'candidates': [], 'recommendation': None}
        
        # Collect all assignment candidates
        all_candidates = []
        agent_counts = {}
        manager_counts = {}
        
        for lead in leads:
            candidates = lead.get_reassignment_candidates()
            all_candidates.extend(candidates)
            
            # Count assignments by role
            for candidate in candidates:
                user = candidate['user']
                if user.role == 'agent':
                    agent_counts[user.id] = agent_counts.get(user.id, 0) + 1
                elif user.role == 'manager':
                    manager_counts[user.id] = manager_counts.get(user.id, 0) + 1
        
        # Find most frequently assigned agents and managers
        top_agent = max(agent_counts.items(), key=lambda x: x[1]) if agent_counts else None
        top_manager = max(manager_counts.items(), key=lambda x: x[1]) if manager_counts else None
        
        recommendation = None
        if top_agent:
            user = User.objects.get(id=top_agent[0])
            recommendation = {
                'user': user,
                'reason': f'Most frequently assigned agent ({top_agent[1]} times)',
                'confidence': min(top_agent[1] * 0.2, 1.0)
            }
        elif top_manager:
            user = User.objects.get(id=top_manager[0])
            recommendation = {
                'user': user,
                'reason': f'Most frequently assigned manager ({top_manager[1]} times)',
                'confidence': min(top_manager[1] * 0.15, 1.0)
            }
        
        return {
            'candidates': all_candidates,
            'recommendation': recommendation,
            'agent_assignments': agent_counts,
            'manager_assignments': manager_counts
        }
