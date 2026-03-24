from django.core.management.base import BaseCommand
from django.utils import timezone
from dashboard.models import Lead
from accounts.models import User
import random
from datetime import timedelta

class Command(BaseCommand):
    help = 'Create dummy leads for testing the hierarchical assignment system'

    def handle(self, *args, **options):
        # Sample data
        first_names = ['John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa', 'James', 'Mary', 
                       'William', 'Patricia', 'Richard', 'Jennifer', 'Charles', 'Linda', 'Joseph', 'Barbara', 
                       'Thomas', 'Susan', 'Christopher', 'Jessica', 'Daniel', 'Karen', 'Matthew', 'Nancy']
        
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 
                       'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 
                       'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez']
        
        courses = ['Python Programming', 'Web Development', 'Data Science', 'Machine Learning', 'Digital Marketing',
                   'Mobile App Development', 'Cloud Computing', 'Cybersecurity', 'Blockchain', 'AI & Deep Learning',
                   'React Development', 'Node.js Backend', 'Database Design', 'DevOps', 'UI/UX Design']
        
        sources = ['Website', 'Facebook', 'Instagram', 'LinkedIn', 'Google Ads', 'Referral', 'Email Campaign', 
                   'WhatsApp', 'Phone Call', 'Walk-in', 'Webinar', 'YouTube', 'Twitter', 'Direct Mail']
        
        statuses = ['lead', 'interested_follow_up', 'sale_done']
        
        cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 
                 'San Diego', 'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'Fort Worth', 'Columbus', 'Charlotte']
        
        # Get existing users for assignment
        users = list(User.objects.filter(is_active=True))
        
        if not users:
            self.stdout.write(self.style.ERROR('No users found. Please create users first.'))
            return
        
        created_count = 0
        updated_count = 0
        
        self.stdout.write('Creating dummy leads...')
        
        for i in range(50):  # Create 50 dummy leads
            # Generate random data
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            full_name = f"{first_name} {last_name}"
            
            # Random phone number
            phone = f"+1{random.randint(200, 999)}{random.randint(200, 999)}{random.randint(1000, 9999)}"
            
            # Random email
            email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 99)}@example.com"
            
            # Random course and source
            course = random.choice(courses)
            source = random.choice(sources)
            status = random.choice(statuses)
            
            # Random dates
            days_ago = random.randint(1, 90)
            created_at = timezone.now() - timedelta(days=days_ago)
            updated_at = created_at + timedelta(hours=random.randint(1, 72))
            
            # Random address
            city = random.choice(cities)
            address = f"{random.randint(100, 9999)} {random.choice(['Main St', 'Oak Ave', 'Elm St', 'Park Ave', 'First St'])}"
            
            # Random revenue
            revenue = random.choice([0, 0, 0, 299, 499, 799, 999, 1299, 1599, 1999])
            
            # Check if lead already exists (by email or phone)
            existing_lead = Lead.objects.filter(email=email).first()
            if existing_lead:
                # Update existing lead
                existing_lead.name = full_name
                existing_lead.mobile = phone
                existing_lead.course_name = course
                existing_lead.lead_source = source
                existing_lead.status = status
                existing_lead.created_at = created_at
                existing_lead.updated_at = updated_at
                existing_lead.address = address
                existing_lead.city = city
                existing_lead.exp_revenue = str(revenue)
                
                # Randomly assign to a user (30% chance)
                if random.random() < 0.3 and users:
                    existing_lead.assigned_user = random.choice(users)
                
                existing_lead.save()
                updated_count += 1
            else:
                # Create new lead
                lead = Lead.objects.create(
                    name=full_name,
                    email=email,
                    mobile=phone,
                    course_name=course,
                    lead_source=source,
                    status=status,
                    address=address,
                    city=city,
                    exp_revenue=str(revenue),
                    created_at=created_at,
                    updated_at=updated_at,
                    created_by=random.choice(users) if users else None
                )
                
                # Randomly assign to a user (30% chance)
                if random.random() < 0.3 and users:
                    lead.assigned_user = random.choice(users)
                    lead.save()
                
                created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_count} new leads and updated {updated_count} existing leads.'
            )
        )
        
        # Show summary
        total_leads = Lead.objects.count()
        assigned_leads = Lead.objects.filter(assigned_user__isnull=False).count()
        unassigned_leads = total_leads - assigned_leads
        
        self.stdout.write(f'\nLead Summary:')
        self.stdout.write(f'  Total Leads: {total_leads}')
        self.stdout.write(f'  Assigned Leads: {assigned_leads}')
        self.stdout.write(f'  Unassigned Leads: {unassigned_leads}')
        
        # Show leads by status
        self.stdout.write(f'\nLeads by Status:')
        for status in statuses:
            count = Lead.objects.filter(status=status).count()
            self.stdout.write(f'  {status}: {count}')
        
        self.stdout.write('\nDummy leads created successfully! You can now test the assignment feature.')
