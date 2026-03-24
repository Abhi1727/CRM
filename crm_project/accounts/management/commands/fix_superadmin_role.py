from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


User = get_user_model()


class Command(BaseCommand):
    help = "Convert any legacy 'superadmin' role users to 'owner' so they get full hierarchy permissions."

    def handle(self, *args, **options):
        superadmins = User.objects.filter(role="superadmin")
        if not superadmins.exists():
            self.stdout.write(self.style.WARNING("No users with role 'superadmin' found."))
            return

        for user in superadmins:
            old_role = user.role
            user.role = "owner"
            user.save(update_fields=["role"])
            self.stdout.write(self.style.SUCCESS(f"Updated user '{user.username}' from role '{old_role}' to 'owner'."))

        self.stdout.write(self.style.SUCCESS("All legacy superadmin users converted to owner."))
