#!/usr/bin/env python
"""
Create test data for agent lead restoration
"""

import os
import sys
import django
import json
from datetime import datetime, timedelta

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crm_project'))
django.setup()

from django.contrib.auth import get_user_model
from dashboard.models import Lead, LeadHistory, LeadActivity, LeadOperationLog

User = get_user_model()

def create_test_users():
    """Create the target agents and Ashutosh Rai"""
    
    # Create target agents
    target_agents = [
        {"username": "Raj Singh", "email": "raj.singh@test.com", "role": "agent"},
        {"username": "Himanshu kjh", "email": "himanshu.kjh@test.com", "role": "agent"},
        {"username": "Greshi Chandrakar", "email": "greshi.chandrakar@test.com", "role": "agent"},
        {"username": "Abhishek Kumar", "email": "abhishek.kumar@test.com", "role": "agent"},
        {"username": "Kanhaiya Kumar", "email": "kanhaiya.kumar@test.com", "role": "agent"},
        {"username": "Naitik Kumar", "email": "naitik.kumar@test.com", "role": "agent"},
    ]
    
    created_agents = {}
    for agent_data in target_agents:
        user, created = User.objects.get_or_create(
            username=agent_data["username"],
            defaults={
                "email": agent_data["email"],
                "role": agent_data["role"],
                "is_active": True
            }
        )
        if created:
            user.set_password("password123")
            user.save()
            print(f"Created agent: {agent_data['username']}")
        else:
            print(f"Agent already exists: {agent_data['username']}")
        created_agents[agent_data["username"]] = user
    
    # Create Ashutosh Rai
    ashutosh, created = User.objects.get_or_create(
        id=8,
        defaults={
            "username": "Ashutosh Rai",
            "email": "ashutosh.rai@test.com",
            "role": "agent",
            "is_active": True
        }
    )
    if created:
        ashutosh.set_password("password123")
        ashutosh.save()
        print("Created Ashutosh Rai (ID: 8)")
    else:
        print("Ashutosh Rai (ID: 8) already exists")
    
    return created_agents, ashutosh

def create_test_leads(target_agents, ashutosh):
    """Create 1988 leads assigned to Ashutosh with assignment history"""
    
    print(f"Creating 1988 leads assigned to Ashutosh Rai...")
    
    # Create leads with assignment history pointing to original agents
    agent_list = list(target_agents.values())
    leads_per_agent = 100  # 100 leads per agent = 600 total
    remaining_leads = 1988 - (len(agent_list) * leads_per_agent)  # 1288 leads
    
    created_count = 0
    
    # Create leads that should be restored to agents (600 leads)
    for agent in agent_list:
        for i in range(leads_per_agent):
            lead = Lead.objects.create(
                name=f"Lead {created_count + 1}",
                email=f"lead{created_count + 1}@test.com",
                phone=f"123456789{created_count % 10}",
                assigned_user=ashutosh,
                assigned_by=None,
                assigned_at=datetime.now(),
                assignment_history=[
                    {
                        "assigned_to": agent.id,
                        "assigned_at": (datetime.now() - timedelta(days=5)).isoformat(),
                        "assigned_by": None
                    },
                    {
                        "assigned_to": ashutosh.id,
                        "assigned_at": (datetime.now() - timedelta(days=1)).isoformat(),
                        "assigned_by": None,
                        "transfer_from": agent.id
                    }
                ]
            )
            created_count += 1
    
    # Create leads that should be unassigned (1288 leads)
    for i in range(remaining_leads):
        lead = Lead.objects.create(
            name=f"Lead {created_count + 1}",
            email=f"lead{created_count + 1}@test.com",
            phone=f"123456789{created_count % 10}",
            assigned_user=ashutosh,
            assigned_by=None,
            assigned_at=datetime.now(),
            assignment_history=[
                {
                    "assigned_to": None,
                    "assigned_at": (datetime.now() - timedelta(days=5)).isoformat(),
                    "assigned_by": None
                },
                {
                    "assigned_to": ashutosh.id,
                    "assigned_at": (datetime.now() - timedelta(days=1)).isoformat(),
                    "assigned_by": None,
                    "transfer_from": None
                }
            ]
        )
        created_count += 1
    
    print(f"Created {created_count} test leads")
    return created_count

if __name__ == "__main__":
    print("=== Creating Test Data for Agent Lead Restoration ===")
    
    # Create test users
    target_agents, ashutosh = create_test_users()
    
    # Create test leads
    lead_count = create_test_leads(target_agents, ashutosh)
    
    print(f"\nTest data creation complete!")
    print(f"Target agents: {len(target_agents)}")
    print(f"Test leads created: {lead_count}")
    print(f"Leads assigned to Ashutosh: {Lead.objects.filter(assigned_user=ashutosh).count()}")
