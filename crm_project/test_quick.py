import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.settings')
django.setup()

from accounts.services.password_manager import PasswordManager
from accounts.models import User

print('=== Testing Password Manager ===')
pm = PasswordManager()

# Test password generation
password = pm.generate_secure_password(12)
print('Generated password:', password)

# Test password validation
validation = pm.validate_password_strength(password)
print('Password valid:', validation['is_valid'])
print('Password score:', validation['score'])

# Test permission checking
owner = User.objects.filter(role='owner').first()
agent = User.objects.filter(role='agent').first()

if owner and agent:
    can_manage = pm.can_manage_user_password(owner, agent)
    print('Owner can manage agent password:', can_manage)
else:
    print('No test users found')

print('=== Password Manager Test Complete ===')

# Test forms
from accounts.forms import AdminPasswordForm, UserEditForm

print('\n=== Testing Forms ===')

if owner and agent:
    # Test AdminPasswordForm
    form = AdminPasswordForm(
        target_user=agent,
        editor=owner,
        data={
            'new_password1': 'SecurePass123!',
            'new_password2': 'SecurePass123!'
        }
    )
    print('AdminPasswordForm valid:', form.is_valid())
    
    # Test UserEditForm
    form2 = UserEditForm(
        editor=owner,
        target_user=agent,
        instance=agent,
        data={
            'first_name': agent.first_name,
            'last_name': agent.last_name,
            'email': agent.email,
            'password': 'NewSecurePass123!',
            'confirm_password': 'NewSecurePass123!'
        }
    )
    print('UserEditForm valid:', form2.is_valid())
    print('Can manage password:', form2._can_manage_password())

print('=== All Tests Complete ===')
