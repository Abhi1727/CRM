from django import forms
from django.contrib.auth.forms import UserCreationForm as BaseUserCreationForm
from .models import User as CustomUser
from dashboard.models import Lead

class UserCreationForm(BaseUserCreationForm):
    email = forms.EmailField(required=True)
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
