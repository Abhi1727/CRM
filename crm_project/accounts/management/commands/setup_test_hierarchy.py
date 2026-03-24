from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dashboard.models import Lead

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a simple hierarchy for testing'

    def handle(self, *args, **options):
        # Get or create users
        owner = User.objects.filter(username='admin').first()
        manager = User.objects.filter(role='manager').first()
        team_lead = User.objects.filter(role='team_lead').first()
        agent = User.objects.filter(role='agent').first()
        
        if not all([owner, manager, team_lead, agent]):
            self.stdout.write(self.style.ERROR('Missing required users. Please create users first.'))
            return
        
        # Set up hierarchy
        manager.manager = owner
        manager.company_id = owner.company_id
        manager.save()
        
        team_lead.manager = manager
        team_lead.company_id = owner.company_id
        team_lead.save()
        
        agent.team_lead = team_lead
        agent.company_id = owner.company_id
        agent.save()
        
        # Create some test leads
        for i in range(5):
            Lead.objects.create(
                name=f'Test Lead {i+1}',
                mobile=f'999999999{i}',
                email=f'test{i+1}@example.com',
                company_id=owner.company_id,
                created_by=owner,
                assigned_user=agent if i < 3 else None
            )
        
        self.stdout.write(self.style.SUCCESS('Hierarchy created successfully!'))
        self.stdout.write(self.style.SUCCESS(f'Owner: {owner.username}'))
        self.stdout.write(self.style.SUCCESS(f'Manager: {manager.username} (reports to {owner.username})'))
        self.stdout.write(self.style.SUCCESS(f'Team Lead: {team_lead.username} (reports to {manager.username})'))
        self.stdout.write(self.style.SUCCESS(f'Agent: {agent.username} (reports to {team_lead.username})'))
        self.stdout.write(self.style.SUCCESS('Created 5 test leads'))
        self.stdout.write(self.style.SUCCESS('Now you can test bulk assignment!'))
