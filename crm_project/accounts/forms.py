from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm, PasswordChangeForm
from django.contrib.auth import authenticate
from django.db.models import Q
from django.forms import Select
from django.utils.safestring import mark_safe
from .models import User as CustomUser
from dashboard.models import Lead

class TeamLeadSelectWidget(Select):
    """Custom select widget that includes manager data as data attributes"""
    
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        
        if value:
            try:
                # Handle both integer and ModelChoiceIteratorValue
                if hasattr(value, 'value'):
                    user_id = value.value
                else:
                    user_id = int(value)
                
                team_lead = CustomUser.objects.get(id=user_id)
                if team_lead.manager:
                    option['attrs']['data-manager-id'] = team_lead.manager.id
            except (CustomUser.DoesNotExist, ValueError, TypeError):
                pass
        
        return option

class UserCreationForm(BaseUserCreationForm):
    email = forms.EmailField(required=True, help_text='Required. Enter a valid email address.')
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    phone = forms.CharField(max_length=15, required=False)
    mobile = forms.CharField(max_length=20, required=False)
    
    def __init__(self, *args, **kwargs):
        self.creator = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        
        # Filter role choices based on creator's role
        role_choices = self._get_allowed_roles()
        self.fields['role'] = forms.ChoiceField(
            choices=role_choices,
            required=True,
            help_text='Select the role for this user'
        )
        
        # Add hierarchy fields if applicable
        if self.creator.role == 'manager':
            # Manager can only create team leads and agents
            team_leads = CustomUser.objects.filter(role='team_lead', manager=self.creator)
            if team_leads.exists():
                self.fields['team_lead'] = forms.ModelChoiceField(
                    queryset=team_leads,
                    required=False,
                    help_text='Assign to a team lead (for agents)'
                )
        
        elif self.creator.role == 'owner':
            # Owner can create managers, team leads, and agents
            managers = CustomUser.objects.filter(role='manager', company_id=self.creator.company_id)
            if managers.exists():
                self.fields['manager'] = forms.ModelChoiceField(
                    queryset=managers,
                    required=False,
                    help_text='Assign to a manager (for team leads and agents)'
                )
            
            # Add team lead field for owners (initially empty, will be populated via JavaScript)
            self.fields['team_lead'] = forms.ModelChoiceField(
                queryset=CustomUser.objects.none(),  # Empty initially
                required=False,
                help_text='Assign to a team lead (for agents)',
                widget=TeamLeadSelectWidget()
            )
    
    def _get_allowed_roles(self):
        """Get role choices based on creator's hierarchy level"""
        if self.creator.role == 'owner':
            return [
                ('manager', 'Manager'),
                ('team_lead', 'Team Lead'),
                ('agent', 'Agent'),
            ]
        elif self.creator.role == 'manager':
            return [
                ('team_lead', 'Team Lead'),
                ('agent', 'Agent'),
            ]
        elif self.creator.role == 'team_lead':
            return [
                ('agent', 'Agent'),
            ]
        else:
            return []  # Agents cannot create users
    
    def clean(self):
        """Cross-field validation for hierarchy assignments"""
        cleaned_data = super().clean()
        role = cleaned_data.get('role')
        manager = cleaned_data.get('manager')
        team_lead = cleaned_data.get('team_lead')
        
        # Validate hierarchy consistency
        if role == 'team_lead':
            # Team leads must have a manager (except when created by owner for themselves)
            if self.creator.role == 'owner' and not manager:
                raise forms.ValidationError('Team leads must be assigned to a manager.')
            elif self.creator.role == 'manager':
                # Manager creating team lead - assign to themselves
                cleaned_data['manager'] = self.creator
                
        elif role == 'agent':
            # Agents should have either a manager or team lead
            if self.creator.role == 'owner':
                if not manager and not team_lead:
                    raise forms.ValidationError('Agents must be assigned to either a manager or team lead.')
                
                # If team lead is assigned, ensure they report to the same manager
                if team_lead and manager:
                    if team_lead.manager != manager:
                        raise forms.ValidationError('Team lead must report to the same manager as this agent.')
                elif team_lead and not manager:
                    # If only team lead is assigned, set their manager as the agent's manager
                    cleaned_data['manager'] = team_lead.manager
                        
            elif self.creator.role == 'manager':
                # Manager creating agent - assign to themselves or their team lead
                if not team_lead:
                    cleaned_data['manager'] = self.creator
                else:
                    cleaned_data['manager'] = self.creator
                    
        elif role == 'manager':
            # Only owners can create managers
            if self.creator.role != 'owner':
                raise forms.ValidationError('Only owners can create managers.')
            # Managers report to the owner who created them
            cleaned_data['manager'] = self.creator
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.phone = self.cleaned_data['phone']
        user.mobile = self.cleaned_data['mobile']
        user.role = self.cleaned_data['role']
        user.company_id = self.creator.company_id
        user.created_by = self.creator
        
        # Set hierarchy relationships based on validated data
        if self.creator.role == 'owner':
            if user.role == 'manager':
                user.manager = self.creator
            elif user.role == 'team_lead':
                # Manager should already be validated in clean()
                user.manager = self.cleaned_data.get('manager')
            elif user.role == 'agent':
                # Manager and/or team lead should already be validated in clean()
                if 'manager' in self.cleaned_data:
                    user.manager = self.cleaned_data['manager']
                if 'team_lead' in self.cleaned_data:
                    user.team_lead = self.cleaned_data['team_lead']
                    
        elif self.creator.role == 'manager':
            if user.role == 'team_lead':
                user.manager = self.creator
            elif user.role == 'agent':
                user.manager = self.creator
                if 'team_lead' in self.cleaned_data and self.cleaned_data['team_lead']:
                    user.team_lead = self.cleaned_data['team_lead']
                    
        elif self.creator.role == 'team_lead':
            if user.role == 'agent':
                user.team_lead = self.creator
                user.manager = self.creator.manager
        
        if commit:
            user.save()
        return user
    
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'first_name', 'last_name', 'phone', 'mobile', 'password1', 'password2')
    
    def clean_manager(self):
        """Validate manager assignment"""
        manager = self.cleaned_data.get('manager')
        
        if manager:
            # Prevent circular hierarchy
            if manager == self.creator:
                raise forms.ValidationError('A user cannot be assigned to themselves as a manager.')
            
            # Ensure manager is actually a manager role
            if manager.role != 'manager':
                raise forms.ValidationError('Selected user must have manager role.')
            
            # Ensure manager is in the same company
            if manager.company_id != self.creator.company_id:
                raise forms.ValidationError('Manager must be from the same company.')
        
        return manager
    
    def clean_team_lead(self):
        """Validate team lead assignment"""
        team_lead = self.cleaned_data.get('team_lead')
        
        if team_lead:
            # Prevent circular hierarchy
            if team_lead == self.creator:
                raise forms.ValidationError('A user cannot be assigned to themselves as a team lead.')
            
            # Ensure team lead is actually a team lead role
            if team_lead.role != 'team_lead':
                raise forms.ValidationError('Selected user must have team lead role.')
            
            # Ensure team lead is in the same company
            if team_lead.company_id != self.creator.company_id:
                raise forms.ValidationError('Team lead must be from the same company.')
        
        return team_lead
    
    def clean_email(self):
        """Enhanced email validation for UserCreationForm"""
        email = self.cleaned_data.get('email')
        
        if not email:
            raise forms.ValidationError('Email address is required.')
        
        # Check if email already exists (unique constraint)
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email address already exists.')
        
        # Basic email format validation (Django EmailField already handles this)
        # but we can add additional validation here if needed
        
        return email.lower()  # Store emails in lowercase for consistency

class UserAssignmentForm(forms.Form):
    """Form for assigning leads to users"""
    lead = forms.ModelChoiceField(
        queryset=Lead.objects.all(),
        required=True,
        help_text='Select the lead to assign'
    )
    assigned_user = forms.ModelChoiceField(
        queryset=CustomUser.objects.all(),
        required=True,
        help_text='Select the user to assign this lead to'
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Add any remarks about this assignment...'}),
        required=False,
        help_text='Optional remarks about this assignment'
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        
        # Filter leads based on user's accessible leads
        accessible_leads = self.user.get_accessible_leads_queryset()
        self.fields['lead'].queryset = accessible_leads
        
        # Filter users based on hierarchy
        accessible_users = self.user.get_accessible_users()
        self.fields['assigned_user'].queryset = accessible_users

class LeadStatusUpdateForm(forms.Form):
    """Form for updating lead status"""
    status = forms.ChoiceField(
        choices=[],  # Will be populated in __init__
        required=True
    )
    status_description = forms.CharField(
        widget=forms.Textarea,
        required=False,
        help_text='Add description for status change'
    )
    followup_datetime = forms.DateTimeField(
        required=False,
        help_text='Schedule follow-up (if applicable)'
    )
    followup_remarks = forms.CharField(
        widget=forms.Textarea,
        required=False,
        help_text='Follow-up remarks'
    )
    
    def __init__(self, *args, **kwargs):
        lead_status_choices = kwargs.pop('status_choices', [])
        super().__init__(*args, **kwargs)
        self.fields['status'].choices = lead_status_choices

class UserSearchForm(forms.Form):
    """Form for searching users"""
    search = forms.CharField(
        max_length=100,
        required=False,
        help_text='Search by name, email, or username'
    )
    role = forms.ChoiceField(
        choices=[('', 'All Roles')] + list(CustomUser.ROLE_CHOICES),
        required=False
    )
    status = forms.ChoiceField(
        choices=[('', 'All Status')] + list(CustomUser.ACCOUNT_STATUS_CHOICES),
        required=False
    )
    company_id = forms.IntegerField(
        required=False,
        help_text='Filter by company ID'
    )

class UserProfileForm(forms.ModelForm):
    """Form for users to edit their own profile information"""
    
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'mobile', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your phone number'
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter your mobile number'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        self.fields['profile_picture'].required = False  # Make profile picture optional
        
        # Restrict fields based on user role
        user = kwargs.get('instance')
        if user and user.role == 'agent':
            # Agents cannot change username or email
            self.fields['email'].disabled = True
            self.fields['email'].help_text = 'Email cannot be changed by agents. Contact your manager for assistance.'
            # Note: username is not in the form fields, but if it were, we'd disable it too
        
        # Add help text
        self.fields['first_name'].help_text = 'Your first name as it appears on official documents'
        self.fields['last_name'].help_text = 'Your last name as it appears on official documents'
        if user and user.role != 'agent':
            self.fields['email'].help_text = 'We\'ll use this for account notifications'
        self.fields['phone'].help_text = 'Your primary contact number'
        self.fields['mobile'].help_text = 'Your mobile number (optional)'
        self.fields['profile_picture'].help_text = 'Upload a professional profile picture (JPG, PNG, max 2MB) - Optional'
    
    def clean_email(self):
        """Enhanced email validation for UserProfileForm"""
        email = self.cleaned_data.get('email')
        user = getattr(self, 'instance', None)
        
        # Skip email validation for agents since they can't change it
        if user and user.role == 'agent':
            return user.email  # Return the original email
        
        if not email:
            raise forms.ValidationError('Email address is required.')
        
        # Check if email is already used by another user (case-insensitive)
        existing_user = CustomUser.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).first()
        if existing_user:
            raise forms.ValidationError('This email address is already in use by another account.')
        
        return email.lower()  # Store emails in lowercase for consistency
    
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            # Basic phone validation - allow digits, spaces, +, -, (, )
            import re
            if not re.match(r'^[\d\s\-\(\)\+]+$', phone):
                raise forms.ValidationError('Please enter a valid phone number')
            if len(phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')) < 10:
                raise forms.ValidationError('Phone number must be at least 10 digits')
        return phone
    
    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if mobile:
            # Basic mobile validation
            import re
            if not re.match(r'^[\d\s\-\(\)\+]+$', mobile):
                raise forms.ValidationError('Please enter a valid mobile number')
            if len(mobile.replace(' ', '').replace('-', '').replace('(', '').replace(')', '').replace('+', '')) < 10:
                raise forms.ValidationError('Mobile number must be at least 10 digits')
        return mobile
    
    def clean_profile_picture(self):
        profile_picture = self.cleaned_data.get('profile_picture')
        if profile_picture:
            # Check file size (max 2MB)
            if profile_picture.size > 2 * 1024 * 1024:
                raise forms.ValidationError('Profile picture must be smaller than 2MB')
            
            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif']
            if profile_picture.content_type not in allowed_types:
                raise forms.ValidationError('Profile picture must be a JPEG, PNG, or GIF image')
        return profile_picture

class CustomPasswordChangeForm(PasswordChangeForm):
    """Custom password change form with enhanced validation"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize field widgets and labels
        self.fields['old_password'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your current password'
        })
        self.fields['new_password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter your new password'
        })
        self.fields['new_password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm your new password'
        })
        
        # Add help text
        self.fields['old_password'].help_text = 'Enter your current password for security verification'
        self.fields['new_password1'].help_text = 'Password must be at least 8 characters long and contain letters and numbers'
        self.fields['new_password2'].help_text = 'Enter the same password as above for verification'
    
    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if password:
            # Enhanced password validation
            if len(password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long')
            
            # Check for at least one letter
            if not any(c.isalpha() for c in password):
                raise forms.ValidationError('Password must contain at least one letter')
            
            # Check for at least one digit
            if not any(c.isdigit() for c in password):
                raise forms.ValidationError('Password must contain at least one number')
            
            # Password validation restrictions removed - users can set any password content
        
        return password


class PasswordVisibilityWidget(forms.widgets.TextInput):
    """Custom password widget with visibility toggle"""
    
    def __init__(self, attrs=None):
        default_attrs = {
            'class': 'form-control',
            'placeholder': 'Enter password'
        }
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)
    
    def render(self, name, value, attrs=None, renderer=None):
        from django.utils.safestring import mark_safe
        from django.utils.html import escape
        
        if attrs is None:
            attrs = {}
        
        # Add password visibility toggle attributes
        attrs['data-password-toggle'] = 'true'
        attrs['autocomplete'] = 'new-password'
        
        # Render the input field
        input_html = super().render(name, value, attrs, renderer)
        
        # Add the visibility toggle button
        toggle_html = f'''
        <div class="input-group">
            {input_html}
            <button type="button" class="btn btn-outline-secondary password-toggle-btn" data-target="{attrs.get('id', name)}">
                <i class="bi bi-eye" id="{attrs.get('id', name)}-icon"></i>
            </button>
        </div>
        '''
        
        return mark_safe(toggle_html)


class AdminPasswordForm(forms.Form):
    """Form for admins to set new passwords for users"""
    
    new_password1 = forms.CharField(
        widget=PasswordVisibilityWidget,
        label='New Password',
        help_text='Password must be at least 8 characters long and contain letters and numbers'
    )
    new_password2 = forms.CharField(
        widget=PasswordVisibilityWidget,
        label='Confirm Password',
        help_text='Enter the same password as above for verification'
    )
    
    def __init__(self, *args, **kwargs):
        self.target_user = kwargs.pop('target_user', None)
        self.editor = kwargs.pop('editor', None)
        super().__init__(*args, **kwargs)
        
        # Add password generation button
        self.fields['new_password1'].help_text += (
            '<br><button type="button" class="btn btn-sm btn-outline-primary generate-password-btn" '
            'data-target="id_new_password1">Generate Secure Password</button>'
        )
    
    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if password:
            # Enhanced password validation
            if len(password) < 8:
                raise forms.ValidationError('Password must be at least 8 characters long')
            
            # Check for at least one letter
            if not any(c.isalpha() for c in password):
                raise forms.ValidationError('Password must contain at least one letter')
            
            # Check for at least one digit
            if not any(c.isdigit() for c in password):
                raise forms.ValidationError('Password must contain at least one number')
            
            # Check for at least one special character (optional but recommended)
            special_chars = '!@#$%^&*()_+-=[]{}|;:,.<>?'
            if not any(c in special_chars for c in password):
                raise forms.ValidationError('Password must contain at least one special character')
            
            # Password validation restrictions removed - users can set any password content
        
        return password
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('new_password1')
        password2 = cleaned_data.get('new_password2')
        
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('The two password fields didn\'t match.')
        
        return cleaned_data
    
    def save(self):
        """Save the new password to the target user"""
        if not self.target_user:
            raise ValueError('Target user is required')
        
        password = self.cleaned_data['new_password1']
        self.target_user.set_password(password)
        self.target_user.save()
        
        return self.target_user
    
    def generate_secure_password(self):
        """Generate a secure random password"""
        import secrets
        import string
        
        # Define character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special = '!@#$%^&*()_+-=[]{}|;:,.<>?'
        
        # Ensure password has at least one character from each set
        password = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special)
        ]
        
        # Fill the rest of the password with random characters from all sets
        all_chars = lowercase + uppercase + digits + special
        for _ in range(8):  # Make it 12 characters total
            password.append(secrets.choice(all_chars))
        
        # Shuffle the password to avoid predictable patterns
        secrets.SystemRandom().shuffle(password)
        
        return ''.join(password)


class UserEditForm(forms.ModelForm):
    """Form for editing user details with role-based permissions"""
    
    def __init__(self, *args, **kwargs):
        self.editor = kwargs.pop('editor')
        self.target_user = kwargs.pop('target_user')
        super().__init__(*args, **kwargs)
        
        # Set up basic fields
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['email'].required = True
        
        # Add role field if editor can change roles
        if self._can_edit_role():
            role_choices = self._get_allowed_roles_for_edit()
            if role_choices:
                # Ensure the current role is in the allowed choices
                current_role = self.target_user.role
                allowed_role_values = [choice[0] for choice in role_choices]
                
                # Only add the field if current role is allowed, otherwise use first allowed role
                initial_role = current_role if current_role in allowed_role_values else role_choices[0][0]
                
                self.fields['role'] = forms.ChoiceField(
                    choices=role_choices,
                    required=True,
                    initial=initial_role,
                    help_text='Select the role for this user'
                )
        
        # Add hierarchy fields if editor can manage hierarchy
        if self._can_edit_hierarchy():
            self._add_hierarchy_fields()
        
        # Add account status field if editor can change status
        if self._can_edit_status():
            self.fields['account_status'] = forms.ChoiceField(
                choices=self.target_user.ACCOUNT_STATUS_CHOICES,
                required=True,
                initial=self.target_user.account_status,
                help_text='Account status'
            )
        
        # Add password management fields if editor can manage passwords
        if self._can_manage_password():
            self.fields['password'] = forms.CharField(
                widget=PasswordVisibilityWidget,
                required=False,
                label='New Password',
                help_text='Leave blank to keep current password. Must be at least 8 characters with letters, numbers, and special characters.'
            )
            self.fields['confirm_password'] = forms.CharField(
                widget=PasswordVisibilityWidget,
                required=False,
                label='Confirm Password',
                help_text='Enter the same password as above for verification'
            )
        
        # Restrict fields based on permissions
        self._restrict_fields()
    
    def _can_edit_role(self):
        """Check if editor can change the target user's role"""
        # Owner can change anyone's role
        if self.editor.role == 'owner':
            return True
        
        # Manager can change roles of team leads and agents in their hierarchy
        if self.editor.role == 'manager':
            return (self.target_user.manager == self.editor or 
                   (self.target_user.team_lead and self.target_user.team_lead.manager == self.editor))
        
        # Team leads and agents cannot change roles
        return False
    
    def _can_edit_hierarchy(self):
        """Check if editor can change the target user's hierarchy"""
        # Owner can change anyone's hierarchy
        if self.editor.role == 'owner':
            return True
        
        # Manager can change hierarchy of team leads and agents in their team
        if self.editor.role == 'manager':
            return (self.target_user.manager == self.editor or 
                   (self.target_user.team_lead and self.target_user.team_lead.manager == self.editor))
        
        # Team leads can only edit their own profile (no hierarchy changes)
        if self.editor.role == 'team_lead':
            return self.target_user == self.editor
        
        # Agents cannot change hierarchy
        return False
    
    def _can_edit_status(self):
        """Check if editor can change account status"""
        # Owner and manager can change status
        if self.editor.role in ['owner', 'manager']:
            return True
        
        # Team lead can only change their own status to inactive (deactivate themselves)
        if self.editor.role == 'team_lead':
            return self.target_user == self.editor
        
        # Agents cannot change status
        return False
    
    def _can_manage_password(self):
        """Check if editor can manage the target user's password"""
        # Owner can manage anyone's password
        if self.editor.role == 'owner':
            return True
        
        # Manager can manage passwords of team leads and agents in their hierarchy
        if self.editor.role == 'manager':
            return (self.target_user.manager == self.editor or 
                   (self.target_user.team_lead and self.target_user.team_lead.manager == self.editor))
        
        # Team lead can manage passwords of agents only
        if self.editor.role == 'team_lead':
            return (self.target_user.role == 'agent' and 
                   self.target_user.team_lead == self.editor)
        
        # Agents cannot manage other users' passwords
        return False
    
    def _get_allowed_roles_for_edit(self):
        """Get role choices based on editor's role and hierarchy"""
        if self.editor.role == 'owner':
            return [
                ('manager', 'Manager'),
                ('team_lead', 'Team Lead'),
                ('agent', 'Agent'),
            ]
        elif self.editor.role == 'manager':
            # Manager can edit roles of team leads and agents in their hierarchy
            if self.target_user.role in ['team_lead', 'agent']:
                return [
                    ('team_lead', 'Team Lead'),
                    ('agent', 'Agent'),
                ]
            return []
        else:
            return []  # Team leads and agents cannot change roles
    
    def _add_hierarchy_fields(self):
        """Add manager and team lead assignment fields"""
        if self.editor.role == 'owner':
            # Owner can assign managers
            managers = CustomUser.objects.filter(role='manager', company_id=self.editor.company_id)
            if managers.exists():
                self.fields['manager'] = forms.ModelChoiceField(
                    queryset=managers,
                    required=False,
                    initial=self.target_user.manager,
                    help_text='Assign to a manager (for team leads and agents)'
                )
            
            # Owner can also assign team leads directly
            team_leads = CustomUser.objects.filter(role='team_lead', company_id=self.editor.company_id)
            if team_leads.exists():
                self.fields['team_lead'] = forms.ModelChoiceField(
                    queryset=team_leads,
                    required=False,
                    initial=self.target_user.team_lead,
                    help_text='Assign to a team lead (for agents)',
                    widget=TeamLeadSelectWidget()
                )
        
        elif self.editor.role == 'manager':
            # Manager can assign team leads to agents
            team_leads = CustomUser.objects.filter(role='team_lead', manager=self.editor)
            if team_leads.exists():
                self.fields['team_lead'] = forms.ModelChoiceField(
                    queryset=team_leads,
                    required=False,
                    initial=self.target_user.team_lead,
                    help_text='Assign to a team lead (for agents)',
                    widget=TeamLeadSelectWidget()
                )
    
    def _restrict_fields(self):
        """Restrict fields based on editor's permissions"""
        # Agents can only edit basic fields of their own profile
        if self.editor.role == 'agent':
            if self.target_user != self.editor:
                raise forms.ValidationError("Agents can only edit their own profile.")
            
            # Agents cannot change email
            self.fields['email'].disabled = True
            self.fields['email'].help_text = 'Email cannot be changed by agents. Contact your manager for assistance.'
        
        # Team leads can only edit their own profile (no role/hierarchy changes)
        elif self.editor.role == 'team_lead' and self.target_user != self.editor:
            raise forms.ValidationError("Team leads can only edit their own profile.")
    
    def clean_email(self):
        """Enhanced email validation"""
        email = self.cleaned_data.get('email')
        
        # Skip email validation for agents since they can't change it
        if self.editor.role == 'agent':
            return self.target_user.email  # Return the original email
        
        if not email:
            raise forms.ValidationError('Email address is required.')
        
        # Check if email is already used by another user (case-insensitive)
        existing_user = CustomUser.objects.filter(email__iexact=email).exclude(pk=self.target_user.pk).first()
        if existing_user:
            raise forms.ValidationError('This email address is already in use by another account.')
        
        return email.lower()
    
    def clean_role(self):
        """Validate role changes"""
        if 'role' not in self.cleaned_data:
            return self.target_user.role
        
        new_role = self.cleaned_data['role']
        old_role = self.target_user.role
        
        # Prevent self-role modification that would break hierarchy
        if self.target_user == self.editor:
            # User cannot demote themselves if they have subordinates
            if old_role in ['owner', 'manager', 'team_lead'] and new_role not in [old_role]:
                # Check if user has subordinates
                has_subordinates = CustomUser.objects.filter(
                    Q(manager=self.target_user) | Q(team_lead=self.target_user),
                    company_id=self.target_user.company_id
                ).exists()
                
                if has_subordinates:
                    raise forms.ValidationError('You cannot change your role while you have subordinates.')
        
        return new_role
    
    def clean_manager(self):
        """Validate manager assignment"""
        if 'manager' not in self.cleaned_data:
            return self.target_user.manager
        
        manager = self.cleaned_data['manager']
        
        # Prevent circular hierarchy
        if manager and manager == self.target_user:
            raise forms.ValidationError('A user cannot be their own manager.')
        
        # Prevent assigning someone with higher role as subordinate
        if manager and manager.role == 'agent':
            raise forms.ValidationError('Cannot assign an agent as a manager.')
        
        return manager
    
    def clean_team_lead(self):
        """Validate team lead assignment"""
        if 'team_lead' not in self.cleaned_data:
            return self.target_user.team_lead
        
        team_lead = self.cleaned_data['team_lead']
        
        # Prevent circular hierarchy
        if team_lead and team_lead == self.target_user:
            raise forms.ValidationError('A user cannot be their own team lead.')
        
        # Team lead must be a team lead role
        if team_lead and team_lead.role != 'team_lead':
            raise forms.ValidationError('Only team leads can be assigned as team leads.')
        
        return team_lead
    
    def clean(self):
        """Cross-field validation"""
        cleaned_data = super().clean()
        
        # Validate hierarchy consistency
        manager = cleaned_data.get('manager')
        team_lead = cleaned_data.get('team_lead')
        role = cleaned_data.get('role', self.target_user.role)
        
        # Team leads must have a manager
        if role == 'team_lead' and not manager and self.editor.role == 'owner':
            raise forms.ValidationError('Team leads must be assigned to a manager.')
        
        # If team lead is assigned, ensure they report to the same manager
        if team_lead and manager:
            if team_lead.manager != manager:
                raise forms.ValidationError('Team lead must report to the same manager as this user.')
        
        # Agents should have either a manager or team lead
        if role == 'agent' and not manager and not team_lead:
            # Only enforce this for new assignments or when editor is owner/manager
            if self.editor.role in ['owner', 'manager']:
                raise forms.ValidationError('Agents must be assigned to either a manager or team lead.')
        
        # Validate password fields if present
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password or confirm_password:
            if not password and not confirm_password:
                pass  # Both empty, no password change
            elif password and not confirm_password:
                self.add_error('confirm_password', 'Please confirm the password.')
            elif not password and confirm_password:
                self.add_error('password', 'Please enter a password.')
            elif password != confirm_password:
                self.add_error('confirm_password', 'Passwords do not match.')
            else:
                # Password strength validation
                if len(password) < 8:
                    self.add_error('password', 'Password must be at least 8 characters long.')
                
                # Check for at least one letter
                if not any(c.isalpha() for c in password):
                    self.add_error('password', 'Password must contain at least one letter.')
                
                # Check for at least one digit
                if not any(c.isdigit() for c in password):
                    self.add_error('password', 'Password must contain at least one number.')
                
                # Check for at least one special character
                special_chars = '!@#$%^&*()_+-=[]{}|;:,.<>?'
                if not any(c in special_chars for c in password):
                    self.add_error('password', 'Password must contain at least one special character.')
                
                # Password validation restrictions removed - users can set any password content
        
        return cleaned_data
    
    def save(self, commit=True):
        """Save the user with hierarchy updates and cache invalidation"""
        from django.core.cache import cache
        
        # Store original values for cache invalidation logic
        original_role = self.target_user.role
        original_manager = self.target_user.manager
        original_team_lead = self.target_user.team_lead
        original_status = self.target_user.account_status
        
        user = super().save(commit=False)
        
        # Update role if changed
        if 'role' in self.cleaned_data:
            user.role = self.cleaned_data['role']
        
        # Update hierarchy if changed
        if 'manager' in self.cleaned_data:
            user.manager = self.cleaned_data['manager']
        
        if 'team_lead' in self.cleaned_data:
            user.team_lead = self.cleaned_data['team_lead']
        
        # Update account status if changed
        if 'account_status' in self.cleaned_data:
            user.account_status = self.cleaned_data['account_status']
            # Automatically set is_active based on account_status
            if user.account_status == 'active':
                user.is_active = True
            elif user.account_status in ['inactive', 'suspended']:
                user.is_active = False
        
        # Handle password change if provided
        password_changed = False
        if self._can_manage_password() and self.cleaned_data.get('password'):
            import logging
            logger = logging.getLogger(__name__)
            
            logger.info(f"Password change for user {user.username} by {self.editor.username}")
            user.set_password(self.cleaned_data['password'])
            password_changed = True
        
        if commit:
            user.save()
            
            # Log password change if it occurred
            if password_changed:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Password successfully changed for user {user.username} by {self.editor.username}")
                
                # Invalidate user sessions if password was changed (except for self-changes)
                if user != self.editor:
                    # Use optimized session invalidation for fast performance
                    from accounts.services.session_manager import invalidate_user_sessions_fast
                    
                    # Clear all sessions for the target user to force re-login (optimized)
                    session_count = invalidate_user_sessions_fast(user.id, timeout=30)
                    
                    if session_count > 0:
                        logger.info(f"Invalidated {session_count} sessions for user {user.username} after password change")
            
            # Additional cache invalidation for the editor and affected users
            self._clear_editor_caches(original_role, original_manager, original_team_lead, original_status)
        
        return user
    
    def _clear_editor_caches(self, original_role, original_manager, original_team_lead, original_status):
        """Clear caches for the editor and users affected by the edit"""
        from django.core.cache import cache
        
        # Clear editor's caches (they need to see updated data)
        editor = self.editor
        cache.delete(editor._get_user_cache_key('accessible_users'))
        cache.delete(editor._get_user_cache_key('accessible_leads'))
        
        # If role changed, clear old role cache and new role cache
        if original_role != self.target_user.role:
            cache.delete(f"accessible_users_{self.target_user.id}_{self.target_user.company_id}_{original_role}")
            cache.delete(f"accessible_leads_{self.target_user.id}_{self.target_user.company_id}_{original_role}")
        
        # If hierarchy changed, clear caches for affected users
        hierarchy_changed = (
            original_manager != self.target_user.manager or
            original_team_lead != self.target_user.team_lead
        )
        
        if hierarchy_changed:
            # Clear caches for old hierarchy members
            if original_manager:
                cache.delete(original_manager._get_user_cache_key('accessible_users'))
                cache.delete(original_manager._get_user_cache_key('accessible_leads'))
            
            if original_team_lead:
                cache.delete(original_team_lead._get_user_cache_key('accessible_users'))
                cache.delete(original_team_lead._get_user_cache_key('accessible_leads'))
            
            # Clear caches for new hierarchy members
            if self.target_user.manager:
                cache.delete(self.target_user.manager._get_user_cache_key('accessible_users'))
                cache.delete(self.target_user.manager._get_user_cache_key('accessible_leads'))
            
            if self.target_user.team_lead:
                cache.delete(self.target_user.team_lead._get_user_cache_key('accessible_users'))
                cache.delete(self.target_user.team_lead._get_user_cache_key('accessible_leads'))
        
        # If status changed, clear caches for users who manage this user
        if original_status != self.target_user.account_status:
            managers_to_clear = set()
            if self.target_user.manager:
                managers_to_clear.add(self.target_user.manager)
            if self.target_user.team_lead:
                managers_to_clear.add(self.target_user.team_lead)
            
            for manager in managers_to_clear:
                cache.delete(manager._get_user_cache_key('accessible_users'))
                cache.delete(manager._get_user_cache_key('accessible_leads'))
        
        # Clear dashboard statistics caches for the company using the utility method
        self.target_user._clear_company_dashboard_caches()
    
    class Meta:
        model = CustomUser
        fields = ['first_name', 'last_name', 'email', 'phone', 'mobile']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email address'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'mobile': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter mobile number'
            }),
        }
