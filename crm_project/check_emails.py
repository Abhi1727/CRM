#!/usr/bin/env python
import os
import django

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from accounts.models import User
from django.db.models import Count

def check_email_duplicates():
    # Check for duplicate emails
    duplicate_emails = User.objects.values('email').annotate(count=Count('id')).filter(count__gt=1)
    print('Duplicate emails found:')
    for email_data in duplicate_emails:
        print(f'Email: {email_data["email"]} - Count: {email_data["count"]}')

    # Check total users and users with emails
    total_users = User.objects.count()
    users_with_email = User.objects.exclude(email='').exclude(email__isnull=True).count()
    users_with_unique_email = User.objects.values('email').annotate(count=Count('id')).filter(count=1).count()

    print(f'\nTotal users: {total_users}')
    print(f'Users with email: {users_with_email}')
    print(f'Users with unique email: {users_with_unique_email}')

    # Show some sample emails
    print('\nSample emails:')
    for user in User.objects.exclude(email='').exclude(email__isnull=True)[:10]:
        print(f'Username: {user.username} - Email: {user.email}')

if __name__ == '__main__':
    check_email_duplicates()
