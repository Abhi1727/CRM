from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dashboard.models import Lead


User = get_user_model()


class Command(BaseCommand):
    help = "Create a demo hierarchy: owner -> manager -> team lead -> agents and some sample leads"

    def handle(self, *args, **options):
        # Ensure an owner exists (use existing admin owner if present)
        owner = User.objects.filter(role="owner").first()
        if not owner:
            owner = User.objects.create_superuser(
                username="admin",
                email="admin@crm.com",
                password="admin123",
                role="owner",
                first_name="Admin",
                last_name="User",
            )
            self.stdout.write(self.style.SUCCESS("Created owner user 'admin' (password: admin123)"))
        else:
            self.stdout.write(self.style.WARNING(f"Using existing owner: {owner.username}"))

        # Create testing manager
        manager, created = User.objects.get_or_create(
            username="testing_manager",
            defaults={
                "email": "testing_manager@example.com",
                "role": "manager",
                "first_name": "Testing",
                "last_name": "Manager",
                "company_id": owner.company_id,
                "created_by": owner,
            },
        )
        if created:
            manager.set_password("manager123")
            manager.save()
            self.stdout.write(self.style.SUCCESS("Created manager 'testing_manager' (password: manager123)"))
        else:
            self.stdout.write(self.style.WARNING("Manager 'testing_manager' already exists"))

        # Create testing team lead under manager
        team_lead, created = User.objects.get_or_create(
            username="testing_team_lead",
            defaults={
                "email": "testing_team_lead@example.com",
                "role": "team_lead",
                "first_name": "Testing",
                "last_name": "TeamLead",
                "company_id": owner.company_id,
                "created_by": owner,
                "manager": manager,
            },
        )
        if created:
            team_lead.set_password("teamlead123")
            team_lead.save()
            self.stdout.write(self.style.SUCCESS("Created team lead 'testing_team_lead' (password: teamlead123)"))
        else:
            self.stdout.write(self.style.WARNING("Team lead 'testing_team_lead' already exists"))

        # Create two testing agents under the team lead
        agents_info = [
            ("testing_agent1", "Testing", "AgentOne"),
            ("testing_agent2", "Testing", "AgentTwo"),
        ]

        agents = []
        for username, first_name, last_name in agents_info:
            agent, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "role": "agent",
                    "first_name": first_name,
                    "last_name": last_name,
                    "company_id": owner.company_id,
                    "created_by": team_lead,
                    "manager": manager,
                    "team_lead": team_lead,
                },
            )
            if created:
                agent.set_password("agent123")
                agent.save()
                self.stdout.write(
                    self.style.SUCCESS(f"Created agent '{username}' (password: agent123)")
                )
            else:
                self.stdout.write(self.style.WARNING(f"Agent '{username}' already exists"))
            agents.append(agent)

        # Create some demo leads and assign down the hierarchy
        if not agents:
            self.stdout.write(self.style.ERROR("No agents available to assign leads."))
            return

        self.stdout.write("Creating sample leads for testing hierarchy dashboards...")

        # Simple named leads to make it obvious in UI
        demo_leads = [
            ("Owner Lead 1", owner, None, "lead"),
            ("Manager Lead 1", manager, None, "interested_follow_up"),
            ("Team Lead Lead 1", team_lead, None, "not_available"),
            ("Agent1 Lead - Won", agents[0], True, "sale_done"),
            ("Agent1 Lead - Working", agents[0], False, "interested_follow_up"),
            ("Agent2 Lead - Won", agents[1], True, "sale_done"),
            ("Agent2 Lead - Lost", agents[1], False, "not_interested"),
        ]

        created_count = 0
        for name, assigned_user, converted, status in demo_leads:
            lead, created = Lead.objects.get_or_create(
                name=name,
                mobile="+10000000000",
                defaults={
                    "company_id": owner.company_id,
                    "created_by": owner,
                    "assigned_user": assigned_user,
                    "status": status,
                    "converted": bool(converted) if converted is not None else False,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} demo leads (or reused existing)."))
        self.stdout.write(self.style.SUCCESS("Demo hierarchy and leads ready for testing."))
