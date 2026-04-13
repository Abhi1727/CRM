#!/usr/bin/env python
"""
Undo script for specific bulk assignment operation
Operation ID: bulk_assign_e30945059d7842
Target: Restore 1988 leads from Ashutosh Rai to original assignments
"""

import os
import sys
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append(os.path.join(os.path.dirname(__file__), 'crm_project'))
django.setup()

from django.db import transaction
from django.utils import timezone
from accounts.models import User
from dashboard.models import Lead, LeadHistory, LeadActivity, LeadOperationLog
from datetime import datetime
import json

def undo_bulk_assignment():
    """Undo the specific bulk assignment operation"""
    
    print("=" * 80)
    print("UNDO BULK ASSIGNMENT OPERATION")
    print("=" * 80)
    
    # Get the target user (Ashutosh Rai)
    try:
        ashutosh = User.objects.get(id=8)
        print(f"Target user: {ashutosh.username} ({ashutosh.get_role_display()})")
    except User.DoesNotExist:
        print("❌ Ashutosh Rai (ID: 8) not found!")
        return False
    
    # Get all leads currently assigned to Ashutosh
    ashutosh_leads = Lead.objects.filter(assigned_user=ashutosh)
    total_leads = ashutosh_leads.count()
    
    print(f"\n📊 Current Status:")
    print(f"Total leads assigned to {ashutosh.username}: {total_leads}")
    
    if total_leads == 0:
        print("❌ No leads found assigned to Ashutosh!")
        return False
    
    # Analyze assignment history
    print(f"\n🔍 Analyzing assignment history...")
    restore_plan = {}
    unassigned_count = 0
    no_history_count = 0
    
    for lead in ashutosh_leads:
        if lead.assignment_history and isinstance(lead.assignment_history, dict):
            assignments = lead.assignment_history.get('assignments', [])
            if assignments:
                # Get the assignment before the last one (original assignment)
                if len(assignments) >= 2:
                    prev_assignment = assignments[-2]
                    prev_user_id = prev_assignment.get('assigned_to')
                    prev_user_name = prev_assignment.get('assigned_to_name', 'Unknown')
                    
                    # Try to find the user by ID first, then by name
                    original_user = None
                    if prev_user_id:
                        try:
                            original_user = User.objects.get(id=prev_user_id)
                        except User.DoesNotExist:
                            pass
                    
                    if not original_user and prev_user_name:
                        # Try to find by name
                        name_parts = prev_user_name.split()
                        if len(name_parts) >= 2:
                            first_name = name_parts[0]
                            last_name = ' '.join(name_parts[1:])
                            original_user = User.objects.filter(
                                first_name__iexact=first_name,
                                last_name__iexact=last_name
                            ).first()
                    
                    if original_user:
                        key = f"{original_user.username} ({original_user.get_role_display()})"
                        restore_plan[key] = restore_plan.get(key, {'user': original_user, 'leads': []})
                        restore_plan[key]['leads'].append(lead)
                    else:
                        # User not found, mark as unassigned
                        unassigned_count += 1
                else:
                    # Only one assignment, so it was previously unassigned
                    unassigned_count += 1
            else:
                no_history_count += 1
        else:
            no_history_count += 1
    
    print(f"\n📋 Restore Plan:")
    for key, data in restore_plan.items():
        print(f"- {key}: {len(data['leads'])} leads")
    print(f"- Previously Unassigned: {unassigned_count} leads")
    print(f"- No History: {no_history_count} leads")
    
    # Confirm before proceeding
    confirm = input(f"\n⚠️  This will restore {total_leads} leads from {ashutosh.username}. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("❌ Operation cancelled.")
        return False
    
    # Perform the undo operation
    try:
        with transaction.atomic():
            print(f"\n🔄 Starting undo operation...")
            
            restored_count = 0
            unassigned_count = 0
            
            # Restore leads to original users
            for key, data in restore_plan.items():
                user = data['user']
                leads = data['leads']
                
                print(f"Restoring {len(leads)} leads to {user.username}...")
                
                for lead in leads:
                    # Store current assignment in history before undoing
                    if not lead.assignment_history:
                        lead.assignment_history = {'assignments': []}
                    
                    # Add undo record to assignment history
                    lead.assignment_history.setdefault('assignments', []).append({
                        'action': 'bulk_assignment_undo',
                        'assigned_to': None,
                        'assigned_to_name': 'Unassigned',
                        'assigned_by': ashutosh.id,
                        'assigned_by_name': ashutosh.username,
                        'assigned_at': timezone.now().isoformat(),
                        'remarks': f'Undo bulk assignment operation bulk_assign_e30945059d7842'
                    })
                    
                    # Create lead history record
                    LeadHistory.objects.create(
                        lead=lead,
                        assigned_by=ashutosh,
                        assigned_to=user,
                        assigned_at=lead.assigned_at,
                        remarks='Bulk assignment undo - restored to original assignment'
                    )
                    
                    # Update the lead
                    lead.assigned_user = user
                    lead.assigned_by = None  # Clear bulk assignment marker
                    lead.transfer_from = None
                    lead.transfer_by = None
                    lead.transfer_date = None
                    lead.assignment_history = lead.assignment_history
                    lead.save()
                    
                    restored_count += 1
            
            # Handle leads that should be unassigned
            if unassigned_count > 0 or no_history_count > 0:
                print(f"Unassigning {unassigned_count + no_history_count} leads...")
                
                for lead in ashutosh_leads:
                    if lead not in [l for data in restore_plan.values() for l in data['leads']]:
                        # Create lead history record
                        LeadHistory.objects.create(
                            lead=lead,
                            assigned_by=ashutosh,
                            assigned_to=None,
                            assigned_at=lead.assigned_at,
                            remarks='Bulk assignment undo - set to unassigned'
                        )
                        
                        # Add undo record to assignment history
                        if not lead.assignment_history:
                            lead.assignment_history = {'assignments': []}
                        
                        lead.assignment_history.setdefault('assignments', []).append({
                            'action': 'bulk_assignment_undo',
                            'assigned_to': None,
                            'assigned_to_name': 'Unassigned',
                            'assigned_by': ashutosh.id,
                            'assigned_by_name': ashutosh.username,
                            'assigned_at': timezone.now().isoformat(),
                            'remarks': f'Undo bulk assignment operation bulk_assign_e30945059d7842'
                        })
                        
                        # Update the lead
                        lead.assigned_user = None
                        lead.assigned_by = None
                        lead.assigned_at = None
                        lead.transfer_from = None
                        lead.transfer_by = None
                        lead.transfer_date = None
                        lead.assignment_history = lead.assignment_history
                        lead.save()
                        
                        unassigned_count += 1
            
            # Create lead activity record
            LeadActivity.objects.create(
                lead=None,  # Bulk operation
                user=ashutosh,
                activity_type='bulk_assignment_undo',
                description=f'Undo bulk assignment: restored {restored_count} leads to original users, {unassigned_count} leads set to unassigned',
                metadata={
                    'operation_id': 'bulk_assign_e30945059d7842',
                    'restored_count': restored_count,
                    'unassigned_count': unassigned_count,
                    'total_leads': total_leads
                }
            )
            
            # Create operation log
            LeadOperationLog.objects.create(
                operation_id=f"undo_assign_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                operation_type='undo_assign',
                user=ashutosh,
                company_id=ashutosh.company_id,
                action_scope='undo',
                requested_count=total_leads,
                processed_count=total_leads,
                success_count=restored_count + unassigned_count,
                failed_count=0,
                metadata={
                    'original_operation_id': 'bulk_assign_e30945059d7842',
                    'restored_count': restored_count,
                    'unassigned_count': unassigned_count
                }
            )
            
            print(f"\n✅ Undo operation completed successfully!")
            print(f"📊 Results:")
            print(f"- Restored to original users: {restored_count} leads")
            print(f"- Set to unassigned: {unassigned_count} leads")
            print(f"- Total processed: {restored_count + unassigned_count} leads")
            
            return True
            
    except Exception as e:
        print(f"❌ Error during undo operation: {str(e)}")
        return False

if __name__ == "__main__":
    success = undo_bulk_assignment()
    if success:
        print("\n🎉 Bulk assignment undo completed successfully!")
    else:
        print("\n❌ Bulk assignment undo failed!")
    print("=" * 80)
