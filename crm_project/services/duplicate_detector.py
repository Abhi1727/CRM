import re
import uuid
from difflib import SequenceMatcher
from typing import List, Dict, Tuple, Optional
from django.db import models
from django.db.models import Q
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
        Find exact duplicates only when BOTH mobile and email match.
        """
        mobile = self.normalize_phone_number(mobile or "")
        email = (email or "").lower().strip()

        # Business rule: exact duplicate requires both fields to match.
        if not mobile or not email:
            return []

        duplicates = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False,
            mobile=mobile,
            email__iexact=email,
        )
        return list(duplicates)
    
    def find_potential_duplicates(self, name: str = None, mobile: str = None, email: str = None) -> List[Lead]:
        """
        Find potential duplicates using fuzzy matching on names.
        Contact-field exact matching is handled by find_exact_duplicates
        using strict mobile+email matching.
        """
        if not name and not mobile and not email:
            return []
        
        duplicates = Lead.objects.filter(
            company_id=self.company_id,
            deleted=False
        )
        
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
        mobile = str(lead_data.get('mobile', '')).strip()
        email = str(lead_data.get('email', '')).strip()
        
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
        # Business rule: if exact (mobile+email) is not matched against existing DB,
        # treat as new.
        return result
    
    def batch_detect_duplicates(self, leads_data: List[Dict]) -> List[Dict]:
        """
        Detect duplicates for multiple leads in batch.
        Returns a list of duplicate detection results.
        """
        if not leads_data:
            return []

        def _clean_text(value):
            return str(value or '').strip()

        def _dedupe_by_id(leads):
            seen = set()
            out = []
            for lead in leads:
                if lead.id_lead in seen:
                    continue
                seen.add(lead.id_lead)
                out.append(lead)
            return out

        def _serialize_lead(lead):
            return {
                'id': lead.id_lead,
                'name': lead.name,
                'mobile': lead.mobile,
                'email': lead.email,
                'status': lead.status,
                'created_at': lead.created_at.isoformat() if lead.created_at else None,
            }

        # Validate input data structure
        if not isinstance(leads_data, list):
            raise ValueError(f"Expected leads_data to be a list, got {type(leads_data)}")
        
        normalized_rows = []
        mobiles = set()
        emails = set()
        
        for i, row in enumerate(leads_data):
            # Validate each row is a dictionary
            if not isinstance(row, dict):
                raise ValueError(f"Expected row {i} to be a dictionary, got {type(row)}")
            
            # Safely extract values with .get() method
            mobile = self.normalize_phone_number(_clean_text(row.get('mobile', '')))
            email = _clean_text(row.get('email', '')).lower()

            normalized = {
                'index': i,
                'raw': row,  # Store the original row data
                'mobile': mobile,
                'email': email,
            }
            normalized_rows.append(normalized)

            if mobile:
                mobiles.add(mobile)
            if email:
                emails.add(email)

        q = Q()
        if mobiles:
            q |= Q(mobile__in=mobiles)
        if emails:
            q |= Q(email__in=emails)

        # OPTIMIZED: Single database query with O(1) lookup instead of loading all candidates
        candidate_qs = Lead.objects.filter(company_id=self.company_id, deleted=False)
        if q:
            candidate_qs = candidate_qs.filter(q).only(
                'id_lead', 'name', 'mobile', 'email', 'status', 'created_at'
            ).order_by('-created_at')
            # Build optimized lookup dictionary for O(1) duplicate checking
            by_mobile_email = {}
            for lead in candidate_qs:
                if lead.mobile and lead.email:
                    mobile_key = self.normalize_phone_number(lead.mobile)
                    email_key = lead.email.strip().lower()
                    if mobile_key and email_key:
                        by_mobile_email.setdefault((mobile_key, email_key), []).append(lead)
        else:
            by_mobile_email = {}

        results = []
        new_count = 0
        duplicate_count = 0
        missing_field_count = 0
        
        for row in normalized_rows:
            exact = []
            # Check if this lead has missing fields
            has_mobile = bool(row['mobile'])
            has_email = bool(row['email'])
            
            if not has_mobile and not has_email:
                missing_field_count += 1
                # No contact info - treat as new
                result = {
                    'status': 'new',
                    'duplicates': [],
                    'duplicate_type': None,
                    'confidence': 0.0,
                }
            elif has_mobile and has_email:
                # Both fields present - check for exact duplicates
                exact = _dedupe_by_id(
                    by_mobile_email.get((row['mobile'], row['email']), [])
                )
                if exact:
                    duplicate_count += 1
                    result = {
                        'status': 'exact_duplicate',
                        'duplicates': [_serialize_lead(dup) for dup in exact],
                        'duplicate_type': 'EXACT',
                        'confidence': 1.0,
                    }
                else:
                    new_count += 1
                    result = {
                        'status': 'new',
                        'duplicates': [],
                        'duplicate_type': None,
                        'confidence': 0.0,
                    }
            else:
                # Only one field present - treat as new (can't be exact duplicate)
                new_count += 1
                result = {
                    'status': 'new',
                    'duplicates': [],
                    'duplicate_type': None,
                    'confidence': 0.0,
                }

            result['row_index'] = row['index']
            result['lead_data'] = row['raw']  # Ensure lead_data is always included
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
    
    def find_duplicate_groups_paginated(self, status: str = None, duplicate_type: str = None, 
                                      search: str = None, assigned_user: str = None, 
                                      start_date: str = None, end_date: str = None,
                                      page: int = 1, page_size: int = 20, user_role: str = None, user=None) -> Dict:
        """
        Find duplicate groups with database-level pagination.
        Returns paginated results with total count.
        """
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        from django.db.models import Count, Max
        
        # Base queryset for groups
        leads_qs = Lead.objects.filter(
            company_id=self.company_id,
            duplicate_status__in=['exact_duplicate', 'potential_duplicate'],
            deleted=False
        ).exclude(duplicate_group_id__isnull=True)
        
        # Apply status filter
        if status:
            leads_qs = leads_qs.filter(duplicate_resolution_status=status)
        
        # Apply duplicate type filter
        if duplicate_type:
            leads_qs = leads_qs.filter(duplicate_status=duplicate_type)
        
        # Apply search filter
        if search:
            search_terms = search.strip()
            if search_terms:
                # Search across multiple fields
                search_filter = (
                    Q(name__icontains=search_terms) |
                    Q(mobile__icontains=search_terms) |
                    Q(email__icontains=search_terms) |
                    Q(duplicate_group_id__icontains=search_terms)
                )
                leads_qs = leads_qs.filter(search_filter)
        
        # Apply assigned user filter
        if assigned_user:
            leads_qs = leads_qs.filter(assigned_user_id=assigned_user)
        
        # Apply date range filter
        if start_date:
            leads_qs = leads_qs.filter(created_at__date__gte=start_date)
        if end_date:
            leads_qs = leads_qs.filter(created_at__date__lte=end_date)
        
        # Apply role-based filtering
        if user_role and user:
            if user_role == 'agent':
                leads_qs = leads_qs.filter(assigned_user=user)
            elif user_role == 'team_lead':
                team_agents = user.get_accessible_users()
                leads_qs = leads_qs.filter(assigned_user__in=team_agents)
            elif user_role == 'manager':
                team_users = user.get_accessible_users()
                leads_qs = leads_qs.filter(assigned_user__in=team_users)
            # owner sees all
        
        # Group by duplicate_group_id with aggregation
        groups_data = leads_qs.values('duplicate_group_id').annotate(
            lead_count=Count('id_lead'),
            max_created_at=Max('created_at'),
            status=Max('duplicate_resolution_status')
        ).order_by('-max_created_at')
        
        # Get total count
        total_count = groups_data.count()
        
        # Apply pagination
        paginator = Paginator(groups_data, page_size)
        
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        # Get full group data for current page
        group_ids = [item['duplicate_group_id'] for item in page_obj.object_list]
        groups_leads = Lead.objects.filter(
            duplicate_group_id__in=group_ids,
            company_id=self.company_id
        ).select_related('assigned_user').order_by('-created_at')
        
        # Organize leads by group
        groups_dict = {}
        for lead in groups_leads:
            group_id = lead.duplicate_group_id
            if group_id not in groups_dict:
                groups_dict[group_id] = {
                    'group_id': group_id,
                    'leads': [],
                    'status': lead.duplicate_resolution_status,
                    'created_at': lead.created_at
                }
            groups_dict[group_id]['leads'].append(lead)
        
        # Build result list in the same order as paginated groups
        result_groups = []
        for group_data in page_obj.object_list:
            group_id = group_data['duplicate_group_id']
            if group_id in groups_dict:
                result_groups.append(groups_dict[group_id])
        
        return {
            'page_obj': page_obj,
            'groups': result_groups,
            'total_count': total_count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'num_pages': paginator.num_pages,
            'current_page': page_obj.number,
            'start_index': page_obj.start_index(),
            'end_index': page_obj.end_index()
        }
    
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
