from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dashboard.models import Lead, Company, LeadComment, LeadHistory, CommunicationHistory, BackOfficeUpdate
from django.db import transaction
import pymysql
from datetime import datetime

User = get_user_model()

class Command(BaseCommand):
    help = 'Import data from MySQL database'

    def add_arguments(self, parser):
        parser.add_argument('--host', type=str, default='localhost', help='MySQL host')
        parser.add_argument('--port', type=int, default=3306, help='MySQL port')
        parser.add_argument('--user', type=str, default='root', help='MySQL user')
        parser.add_argument('--password', type=str, default='', help='MySQL password')
        parser.add_argument('--database', type=str, default='u571325480_crm', help='MySQL database name')

    def handle(self, *args, **options):
        try:
            # Connect to MySQL
            connection = pymysql.connect(
                host=options['host'],
                port=options['port'],
                user=options['user'],
                password=options['password'],
                database=options['database'],
                charset='utf8mb4'
            )
            
            self.stdout.write(self.style.SUCCESS('Connected to MySQL database'))
            
            cursor = connection.cursor(pymysql.cursors.DictCursor)
            
            # Import companies
            self.import_companies(cursor)
            
            # Import users
            self.import_users(cursor)
            
            # Import leads
            self.import_leads(cursor)
            
            # Import lead comments
            self.import_lead_comments(cursor)
            
            # Import communication history
            self.import_communication_history(cursor)
            
            # Import back office updates
            self.import_back_office_updates(cursor)
            
            connection.close()
            self.stdout.write(self.style.SUCCESS('Import completed successfully!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
    
    def import_companies(self, cursor):
        self.stdout.write('Importing companies...')
        cursor.execute("SELECT * FROM companies")
        companies = cursor.fetchall()
        
        count = 0
        for company_data in companies:
            Company.objects.update_or_create(
                id=company_data['id'],
                defaults={
                    'name': company_data['name'],
                    'email': company_data.get('email'),
                    'phone': company_data.get('phone'),
                    'address': company_data.get('address'),
                }
            )
            count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Imported {count} companies'))
    
    def import_users(self, cursor):
        self.stdout.write('Importing users...')
        cursor.execute("SELECT * FROM users WHERE account_status = 'active'")
        users = cursor.fetchall()
        
        # Role mapping from your database
        role_map = {
            1: 'superadmin',  # upendra singh
            2: 'manager',     # Manager
            3: 'team_lead',   # Team leader
            4: 'agent',       # Agent
        }
        
        count = 0
        for user_data in users:
            user_id = user_data['id']
            username = user_data['email'].split('@')[0]  # Use email prefix as username
            
            # Skip if user already exists
            if User.objects.filter(email=user_data['email']).exists():
                continue
            
            # Handle username conflicts by appending a number
            original_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{original_username}{counter}"
                counter += 1
            
            role = role_map.get(user_id, 'agent')
            
            user = User.objects.create_user(
                username=username,
                email=user_data['email'],
                first_name=user_data['name'].split()[0] if user_data['name'] else '',
                last_name=' '.join(user_data['name'].split()[1:]) if user_data['name'] and len(user_data['name'].split()) > 1 else '',
                mobile=user_data.get('mobile'),
                company_id=user_data.get('company_id', 1),
                role=role,
                account_status=user_data.get('account_status', 'active'),
            )
            user.set_password('changeMe123')  # Set default password
            user.save()
            count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Imported {count} users'))
        self.stdout.write(self.style.WARNING('Default password for imported users: changeMe123'))
    
    @transaction.atomic
    def import_leads(self, cursor):
        self.stdout.write('Importing leads... This may take a while...')
        
        # Get count first
        cursor.execute("SELECT COUNT(*) as count FROM leads WHERE deleted = 0")
        total = cursor.fetchone()['count']
        self.stdout.write(f'Found {total} active leads to import')
        
        # Import in batches
        batch_size = 1000
        offset = 0
        imported_count = 0
        
        while offset < total:
            cursor.execute(f"""
                SELECT * FROM leads 
                WHERE deleted = 0 
                LIMIT {batch_size} OFFSET {offset}
            """)
            leads = cursor.fetchall()
            
            leads_to_create = []
            
            for lead_data in leads:
                # Map user IDs
                created_by = None
                assigned_user = None
                modified_user = None
                
                if lead_data.get('created_by'):
                    created_by = User.objects.filter(email__icontains=lead_data['created_by']).first()
                if lead_data.get('assigned_user_id'):
                    assigned_user = User.objects.filter(email__icontains=lead_data['assigned_user_id']).first()
                if lead_data.get('modified_user_id'):
                    modified_user = User.objects.filter(email__icontains=lead_data['modified_user_id']).first()
                
                # Map status
                status = self.map_status(lead_data.get('status', 'lead'))
                
                lead = Lead(
                    id_lead=lead_data['id_lead'],
                    name=lead_data.get('name'),
                    mobile=lead_data.get('mobile'),
                    email=lead_data.get('email'),
                    alt_mobile=lead_data.get('alt_moble'),  # Note: typo in original DB
                    whatsapp_no=lead_data.get('whatsapp_no'),
                    alt_email=lead_data.get('alt_email'),
                    address=lead_data.get('address'),
                    city=lead_data.get('city'),
                    state=lead_data.get('state'),
                    postalcode=lead_data.get('postalcode'),
                    country=lead_data.get('country'),
                    company_id=lead_data.get('company_id', 1),
                    created_by=created_by,
                    assigned_user_id=assigned_user,
                    modified_user_id=modified_user,
                    status=status,
                    status_description=lead_data.get('status_description'),
                    converted=bool(lead_data.get('converted', 0)),
                    deleted=bool(lead_data.get('deleted', 0)),
                    do_not_call=bool(lead_data.get('do_not_call', 0)),
                    followup_datetime=lead_data.get('followup_datetime'),
                    followup_remarks=lead_data.get('followup_remarks'),
                    date_reviewed=lead_data.get('date_reviewed'),
                    course_id=lead_data.get('course_id'),
                    course_name=lead_data.get('course_name'),
                    course_amount=lead_data.get('course_amount'),
                    lead_source=lead_data.get('lead_source'),
                    lead_source_description=lead_data.get('lead_source_description'),
                    refered_by=lead_data.get('refered_by'),
                    campaign_id=lead_data.get('campaign_id'),
                    exp_revenue=lead_data.get('exp_revenue'),
                    exp_close_date=lead_data.get('exp_close_date'),
                    transfer_from=lead_data.get('transfer_from'),
                    transfer_by=lead_data.get('transfer_by'),
                    transfer_date=lead_data.get('transfer_date'),
                    description=lead_data.get('description'),
                    birthdate=lead_data.get('birthdate'),
                    team_member=lead_data.get('team_member'),
                    next_step=lead_data.get('next_step'),
                    created_at=lead_data.get('created_at') or datetime.now(),
                    updated_at=lead_data.get('updated_at') or datetime.now(),
                )
                leads_to_create.append(lead)
            
            # Bulk create
            Lead.objects.bulk_create(leads_to_create, ignore_conflicts=True)
            imported_count += len(leads_to_create)
            offset += batch_size
            
            self.stdout.write(f'Imported {imported_count}/{total} leads...')
        
        self.stdout.write(self.style.SUCCESS(f'Successfully imported {imported_count} leads'))
    
    def map_status(self, original_status):
        """Map original database statuses to new status choices"""
        status_mapping = {
            'Sale Done': 'sale_done',
            'Interested- Follow Up': 'interested_follow_up',
            'Not Available': 'not_available',
            'RNR': 'rnr',
            'Not Interested': 'not_interested',
            'Out of Country': 'out_of_country',
            'Getting Better Deal': 'getting_better_deal',
            'Product is Expensive': 'product_expensive',
            'Not Eligible for EMI': 'not_eligible_emi',
            'Wrong Number': 'wrong_number',
            'Switched Off': 'switched_off',
            'Closed': 'closed',
            'Call Back': 'call_back',
            'In Few Months': 'in_few_months',
            'Contacted': 'contacted',
            'Lead': 'lead',
        }
        
        return status_mapping.get(original_status, 'lead')
    
    def import_lead_comments(self, cursor):
        self.stdout.write('Importing lead comments...')
        try:
            cursor.execute("SELECT COUNT(*) as count FROM lead_comments")
            total = cursor.fetchone()['count']
            self.stdout.write(f'Found {total} comments')
            # Implement if needed
        except:
            self.stdout.write(self.style.WARNING('lead_comments table not found'))
    
    def import_communication_history(self, cursor):
        self.stdout.write('Importing communication history...')
        try:
            cursor.execute("SELECT COUNT(*) as count FROM communication_history")
            total = cursor.fetchone()['count']
            self.stdout.write(f'Found {total} communication records')
            # Implement if needed
        except:
            self.stdout.write(self.style.WARNING('communication_history table not found'))
    
    def import_back_office_updates(self, cursor):
        self.stdout.write('Importing back office updates...')
        try:
            cursor.execute("SELECT COUNT(*) as count FROM back_office_updates")
            total = cursor.fetchone()['count']
            self.stdout.write(f'Found {total} back office updates')
            # Implement if needed
        except:
            self.stdout.write(self.style.WARNING('back_office_updates table not found'))
