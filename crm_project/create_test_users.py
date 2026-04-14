import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
django.setup()

from django.contrib.auth import get_user_model
from accounts.models import User
from django.db import transaction

User = get_user_model()

# Test users data
test_users = [
    {
        'username': 'john_doe',
        'email': 'john.doe@company.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543210'
    },
    {
        'username': 'jane_smith',
        'email': 'jane.smith@company.com',
        'first_name': 'Jane',
        'last_name': 'Smith',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543211'
    },
    {
        'username': 'mike_wilson',
        'email': 'mike.wilson@company.com',
        'first_name': 'Mike',
        'last_name': 'Wilson',
        'password': 'User@123',
        'role': 'team_lead',
        'mobile': '9876543212'
    },
    {
        'username': 'sarah_jones',
        'email': 'sarah.jones@company.com',
        'first_name': 'Sarah',
        'last_name': 'Jones',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543213'
    },
    {
        'username': 'david_brown',
        'email': 'david.brown@company.com',
        'first_name': 'David',
        'last_name': 'Brown',
        'password': 'User@123',
        'role': 'manager',
        'mobile': '9876543214'
    },
    {
        'username': 'emily_davis',
        'email': 'emily.davis@company.com',
        'first_name': 'Emily',
        'last_name': 'Davis',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543215'
    },
    {
        'username': 'robert_miller',
        'email': 'robert.miller@company.com',
        'first_name': 'Robert',
        'last_name': 'Miller',
        'password': 'User@123',
        'role': 'team_lead',
        'mobile': '9876543216'
    },
    {
        'username': 'lisa_garcia',
        'email': 'lisa.garcia@company.com',
        'first_name': 'Lisa',
        'last_name': 'Garcia',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543217'
    },
    {
        'username': 'james_taylor',
        'email': 'james.taylor@company.com',
        'first_name': 'James',
        'last_name': 'Taylor',
        'password': 'User@123',
        'role': 'agent',
        'mobile': '9876543218'
    },
    {
        'username': 'maria_martinez',
        'email': 'maria.martinez@company.com',
        'first_name': 'Maria',
        'last_name': 'Martinez',
        'password': 'User@123',
        'role': 'team_lead',
        'mobile': '9876543219'
    }
]

@transaction.atomic
def create_test_users():
    created_count = 0
    updated_count = 0
    
    for user_data in test_users:
        username = user_data.pop('username')
        password = user_data.pop('password')
        
        user, created = User.objects.get_or_create(
            username=username,
            defaults=user_data
        )
        
        if created:
            user.set_password(password)
            user.save()
            created_count += 1
            print(f"Created user: {username}")
        else:
            # Update existing user
            for key, value in user_data.items():
                setattr(user, key, value)
            user.set_password(password)
            user.save()
            updated_count += 1
            print(f"Updated user: {username}")
    
    print(f"\nSummary: {created_count} users created, {updated_count} users updated")
    
    # Display all users
    print("\nAll users in database:")
    for user in User.objects.all():
        print(f"- {user.username} ({user.role}) - {user.email}")

if __name__ == '__main__':
    create_test_users()
