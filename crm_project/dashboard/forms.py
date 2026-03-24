from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Lead


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "name",
            "mobile", 
            "email",
            "alt_mobile",
            "whatsapp_no",
            "alt_email",
            "address",
            "city",
            "state",
            "postalcode",
            "country",
            "status",
            "status_description",
            "lead_source",
            "lead_source_description",
            "refered_by",
            "campaign_id",
            "course_name",
            "course_amount",
            "exp_revenue",
            "exp_close_date",
            "followup_datetime",
            "followup_remarks",
            "description",
            "birthdate",
            "next_step",
            "do_not_call",
        ]
        widgets = {
            "followup_datetime": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "id": "followup_datetime",
                "name": "followup_datetime"
            }),
            "exp_close_date": forms.DateInput(attrs={
                "type": "date",
                "id": "exp_close_date",
                "name": "exp_close_date"
            }),
            "birthdate": forms.DateInput(attrs={
                "type": "date",
                "id": "birthdate",
                "name": "birthdate"
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                "id": "description",
                "name": "description"
            }),
            "status_description": forms.Textarea(attrs={
                "rows": 2,
                "id": "status_description",
                "name": "status_description"
            }),
            "lead_source_description": forms.Textarea(attrs={
                "rows": 2,
                "id": "lead_source_description",
                "name": "lead_source_description"
            }),
            "followup_remarks": forms.Textarea(attrs={
                "rows": 2,
                "id": "followup_remarks",
                "name": "followup_remarks"
            }),
            "next_step": forms.Textarea(attrs={
                "rows": 2,
                "id": "next_step",
                "name": "next_step"
            }),
        }
    
    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if mobile:
            # Check if mobile already exists for active leads
            if Lead.objects.filter(mobile=mobile, deleted=False).exclude(id_lead=self.instance.id_lead).exists():
                raise ValidationError("A lead with this mobile number already exists.")
        return mobile
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email already exists for active leads
            if Lead.objects.filter(email=email, deleted=False).exclude(id_lead=self.instance.id_lead).exists():
                raise ValidationError("A lead with this email already exists.")
        return email
    
    def clean_followup_datetime(self):
        followup_datetime = self.cleaned_data.get('followup_datetime')
        if followup_datetime and followup_datetime < timezone.now():
            raise ValidationError("Follow-up datetime cannot be in the past.")
        return followup_datetime


class LeadAssignmentForm(forms.Form):
    """Form for assigning leads to users with hierarchy validation"""
    assigned_user = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select User",
        widget=forms.Select(attrs={"class": "form-control", "id": "assigned_user", "name": "assigned_user"})
    )
    assignment_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3, 
            "placeholder": "Optional notes about this assignment...",
            "id": "assignment_notes",
            "name": "assignment_notes"
        })
    )
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter users based on hierarchy
        accessible_users = user.get_accessible_users()
        self.fields['assigned_user'].queryset = accessible_users


class BulkLeadAssignmentForm(forms.Form):
    """Form for bulk assignment of leads"""
    assigned_user = forms.ModelChoiceField(
        queryset=None,
        empty_label="Select User",
        widget=forms.Select(attrs={"class": "form-control", "id": "assigned_user", "name": "assigned_user"})
    )
    lead_ids = forms.CharField(
        widget=forms.HiddenInput(attrs={"id": "lead_ids", "name": "lead_ids"}),
        required=True
    )
    assignment_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 3, 
            "placeholder": "Optional notes about this bulk assignment...",
            "id": "assignment_notes", 
            "name": "assignment_notes"
        })
    )
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter users based on hierarchy
        accessible_users = user.get_accessible_users()
        self.fields['assigned_user'].queryset = accessible_users


class LeadImportForm(forms.Form):
    """Form for importing leads from CSV/Excel files"""
    file = forms.FileField(
        label="Select File",
        help_text="Upload a CSV or Excel file with lead data",
        widget=forms.FileInput(attrs={
            "accept": ".csv,.xlsx,.xls",
            "id": "file",
            "name": "file"
        })
    )
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Check file extension
            allowed_extensions = ['.csv', '.xlsx', '.xls']
            file_extension = file.name.lower().split('.')[-1]
            if f'.{file_extension}' not in allowed_extensions:
                raise ValidationError("Only CSV and Excel files are allowed.")
            
            # Check file size (max 10MB)
            if file.size > 10 * 1024 * 1024:
                raise ValidationError("File size must be less than 10MB.")
        
        return file


class LeadStatusUpdateForm(forms.ModelForm):
    """Form for updating lead status with history tracking"""
    class Meta:
        model = Lead
        fields = ['status', 'status_description', 'followup_datetime', 'followup_remarks']
        widgets = {
            'status_description': forms.Textarea(attrs={
                'rows': 3,
                'id': 'status_description',
                'name': 'status_description'
            }),
            'followup_datetime': forms.DateTimeInput(attrs={
                'type': 'datetime-local',
                'id': 'followup_datetime',
                'name': 'followup_datetime'
            }),
            'followup_remarks': forms.Textarea(attrs={
                'rows': 3,
                'id': 'followup_remarks',
                'name': 'followup_remarks'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status_description'].required = False
        self.fields['followup_datetime'].required = False
        self.fields['followup_remarks'].required = False
