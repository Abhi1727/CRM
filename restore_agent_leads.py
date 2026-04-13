#!/usr/bin/env python
"""
Restore Agent Leads Script
Identifies and restores exactly 600 leads that were previously assigned to 6 specific agents 
from Ashutosh Rai's current assignment of 1988 leads.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import django
import json
from datetime import datetime

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadHistory, LeadActivity, LeadOperationLog

User = get_user_model()

def identify_target_agents():
    """Identify the 6 target agents by email-based usernames"""
    target_emails = [
        "rajsinghbbn9555@gmail.com",
        "himanshu@skystates.us", 
        "greshi@skystates.us",
        "abhishekk@skystates.us",
        "kanhaiya@skystates.us",
        "naitikt34@gmail.com"
    ]
    
    target_agents = {}
    for email in target_emails:
        try:
            user = User.objects.get(email=email)
            target_agents[email] = user
            print(f"Found agent: {user.username} (ID: {user.id}, Email: {email})")
        except User.DoesNotExist:
            print(f"WARNING: Agent not found with email: {email}")
            continue
    
    return target_agents

def get_ashutosh_leads():
    """Get all leads currently assigned to Ashutosh Rai (ID: 8)"""
    try:
        ashutosh = User.objects.get(id=8)
        leads = Lead.objects.filter(assigned_user=ashutosh)
        print(f"Found {leads.count()} leads assigned to Ashutosh Rai")
        return leads, ashutosh
    except User.DoesNotExist:
        print("ERROR: Ashutosh Rai (ID: 8) not found")
        return None, None

def analyze_assignment_history(leads, target_agents):
    """Analyze assignment history to categorize leads"""
    leads_to_restore = {}
    leads_to_unassign = []
    
    target_agent_ids = {user.id for user in target_agents.values()}
    
    for lead in leads:
        assignment_history = lead.assignment_history or {}
        original_agent = None
        
        # Parse assignment history to find original assignments
        # Format: {'assignments': [{'from': {...}, 'to': {'user': ID, 'at': ...}, ...}]}
        assignments = assignment_history.get('assignments', [])
        
        # Find the first assignment (original assignment)
        if assignments and len(assignments) > 0:
            first_assignment = assignments[0]
            if 'to' in first_assignment and 'user' in first_assignment['to']:
                assigned_to_id = first_assignment['to']['user']
                if assigned_to_id in target_agent_ids:
                    original_agent = assigned_to_id
        
        if original_agent:
            if original_agent not in leads_to_restore:
                leads_to_restore[original_agent] = []
            leads_to_restore[original_agent].append(lead)
        else:
            leads_to_unassign.append(lead)
    
    return leads_to_restore, leads_to_unassign

def create_audit_trail(lead, old_user, new_user, operation_type="RESTORE"):
    """Create comprehensive audit trail"""
    now = datetime.now()
    
    # LeadHistory record - track assignment change
    LeadHistory.objects.create(
        lead=lead,
        user=new_user,  # The user who made the change (system in this case)
        field_name='assigned_user',
        old_value=str(old_user.id) if old_user else 'None',
        new_value=str(new_user.id) if new_user else 'None',
        action=operation_type.lower(),
        created_at=now
    )
    
    # LeadActivity record
    activity_type = "lead_restored" if operation_type == "RESTORE" else "lead_unassigned"
    description = f"Lead {operation_type.lower()}"
    if new_user:
        description += f" to {new_user.get_full_name() or new_user.username}"
    
    LeadActivity.objects.create(
        lead=lead,
        user=new_user,  # System operation
        activity_type=activity_type,
        description=description,
        created_at=now
    )

def restore_agent_leads():
    """Main function to restore agent leads"""
    print("=== Starting Agent Lead Restoration ===")
    
    # Step 1: Identify target agents
    print("\nStep 1: Identifying target agents...")
    target_agents = identify_target_agents()
    
    if not target_agents:
        print("ERROR: No target agents found")
        return False
    
    # Step 2: Get Ashutosh's leads
    print("\nStep 2: Getting leads assigned to Ashutosh Rai...")
    leads, ashutosh = get_ashutosh_leads()
    
    if not leads:
        print("ERROR: No leads found for Ashutosh Rai")
        return False
    
    # Step 3: Analyze assignment history
    print("\nStep 3: Analyzing assignment history...")
    leads_to_restore, leads_to_unassign = analyze_assignment_history(leads, target_agents)
    
    print(f"Found leads to restore: {sum(len(leads) for leads in leads_to_restore.values())}")
    print(f"Found leads to unassign: {len(leads_to_unassign)}")
    
    # Display breakdown by agent
    for agent_id, agent_leads in leads_to_restore.items():
        agent = User.objects.get(id=agent_id)
        print(f"  {agent.get_full_name() or agent.username}: {len(agent_leads)} leads")
    
    # Step 4: Execute restoration with atomic transaction
    print("\nStep 4: Executing restoration...")
    
    try:
        with transaction.atomic():
            restored_count = 0
            unassigned_count = 0
            
            # Restore leads to original agents
            for agent_id, agent_leads in leads_to_restore.items():
                target_agent = User.objects.get(id=agent_id)
                print(f"Restoring {len(agent_leads)} leads to {target_agent.get_full_name() or target_agent.username}...")
                
                for lead in agent_leads:
                    old_user = lead.assigned_user
                    lead.assigned_user = target_agent
                    lead.assigned_by = None
                    lead.assigned_at = datetime.now()
                    lead.transfer_from = None
                    lead.transfer_by = None
                    lead.transfer_date = None
                    lead.save()
                    
                    create_audit_trail(lead, old_user, target_agent, "RESTORE")
                    restored_count += 1
            
            # Unassign remaining leads
            print(f"Unassigning {len(leads_to_unassign)} leads...")
            for lead in leads_to_unassign:
                old_user = lead.assigned_user
                lead.assigned_user = None
                lead.assigned_by = None
                lead.assigned_at = None
                lead.transfer_from = None
                lead.transfer_by = None
                lead.transfer_date = None
                lead.save()
                
                create_audit_trail(lead, old_user, None, "UNASSIGN")
                unassigned_count += 1
            
            print(f"\n=== Restoration Complete ===")
            print(f"Leads restored: {restored_count}")
            print(f"Leads unassigned: {unassigned_count}")
            print(f"Total processed: {restored_count + unassigned_count}")
            
            return True
            
    except Exception as e:
        print(f"ERROR during restoration: {str(e)}")
        transaction.rollback()
        return False

if __name__ == "__main__":
    success = restore_agent_leads()
    if success:
        print("\nAgent lead restoration completed successfully!")
    else:
        print("\nAgent lead restoration failed!")
        sys.exit(1)
