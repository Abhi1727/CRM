from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm, PasswordChangeForm
from django.contrib.auth import authenticate
from .models import User as CustomUser
from dashboard.models import Lead

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
        
        # Set hierarchy relationships
        if self.creator.role == 'owner':
            if 'manager' in self.cleaned_data and self.cleaned_data['manager']:
                user.manager = self.cleaned_data['manager']
                if user.role == 'agent':
                    # Assign to the first team lead under this manager
                    team_lead = CustomUser.objects.filter(
                        role='team_lead', 
                        manager=self.cleaned_data['manager']
                    ).first()
                    if team_lead:
                        user.team_lead = team_lead
            elif user.role == 'manager':
                user.manager = self.creator
            elif user.role == 'team_lead':
                user.manager = self.creator
                
        elif self.creator.role == 'manager':
            if user.role == 'team_lead':
                user.manager = self.creator
            elif user.role == 'agent':
                if 'team_lead' in self.cleaned_data and self.cleaned_data['team_lead']:
                    user.team_lead = self.cleaned_data['team_lead']
                    user.manager = self.creator
                else:
                    user.manager = self.creator
                    
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
            
            # Check for common patterns
            common_patterns = ['password', '123456', 'qwerty', 'admin', 'user']
            password_lower = password.lower()
            if any(pattern in password_lower for pattern in common_patterns):
                raise forms.ValidationError('Password cannot contain common patterns like "password", "123456", etc.')
            
            # Check if password contains username
            if self.user.username.lower() in password_lower:
                raise forms.ValidationError('Password cannot contain your username')
        
        return password
