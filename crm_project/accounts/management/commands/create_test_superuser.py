from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a superuser for testing'

    def handle(self, *args, **options):
        username = 'admin'
        email = 'admin@crm.com'
        password = 'admin123'
        
        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
                role='owner',
                first_name='Admin',
                last_name='User'
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser "{username}" created successfully!'))
            self.stdout.write(self.style.SUCCESS(f'Username: {username}'))
            self.stdout.write(self.style.SUCCESS(f'Password: {password}'))
        else:
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists!'))
