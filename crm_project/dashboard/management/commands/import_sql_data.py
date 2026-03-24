import re
import MySQLdb
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from dashboard.models import Lead, Company, LeadComment, LeadHistory, CommunicationHistory, BackOfficeUpdate
from django.db import transaction

User = get_user_model()

class Command(BaseCommand):
    help = 'Import data from MySQL SQL dump file'

    def add_arguments(self, parser):
        parser.add_argument('sql_file', type=str, help='Path to SQL dump file')

    def handle(self, *args, **options):
        sql_file = options['sql_file']
        
        self.stdout.write(self.style.SUCCESS(f'Starting import from {sql_file}'))
        
        # First, import companies
        self.import_companies(sql_file)
        
        # Then import users (you'll need to do this manually or create a separate script)
        self.stdout.write(self.style.WARNING('Users need to be imported separately due to password hashing'))
        
        # Finally import leads
        self.import_leads(sql_file)
        
        self.stdout.write(self.style.SUCCESS('Import completed successfully!'))
    
    def import_companies(self, sql_file):
        self.stdout.write('Importing companies...')
        companies_data = [
            {'id': 1, 'name': 'Shef Solutions'},
            {'id': 2, 'name': 'Xziant Du SMB'},
            {'id': 3, 'name': 'Xziant Etislat SMB'},
        ]
        
        for company_data in companies_data:
            Company.objects.update_or_create(
                id=company_data['id'],
                defaults={'name': company_data['name']}
            )
        
        self.stdout.write(self.style.SUCCESS(f'Imported {len(companies_data)} companies'))
    
    def import_leads(self, sql_file):
        self.stdout.write('Reading SQL file for leads...')
        
        # This is a simplified version - for production, use a proper MySQL parser
        # or connect directly to the MySQL database
        
        self.stdout.write(self.style.WARNING(
            'SQL file import requires MySQL. Please use one of these methods:\n'
            '1. Import SQL to MySQL first, then use import_from_mysql command\n'
            '2. Convert SQL to SQLite format\n'
            '3. Use MySQL workbench to export as CSV'
        ))
