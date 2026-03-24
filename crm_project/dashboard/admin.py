from django.contrib import admin
from .models import Lead, LeadActivity, LeadComment, LeadHistory, CommunicationHistory, BackOfficeUpdate, Company

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['id_lead', 'name', 'mobile', 'email', 'status', 'assigned_user_id', 'company_id', 'created_at']
    list_filter = ['status', 'company_id', 'converted', 'deleted', 'created_at']
    search_fields = ['name', 'mobile', 'email', 'whatsapp_no']
    date_hierarchy = 'created_at'
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'mobile', 'email', 'alt_mobile', 'whatsapp_no', 'alt_email')
        }),
        ('Address', {
            'fields': ('address', 'city', 'state', 'postalcode', 'country')
        }),
        ('Assignment', {
            'fields': ('company_id', 'created_by', 'assigned_user_id', 'modified_user_id')
        }),
        ('Status', {
            'fields': ('status', 'status_description', 'converted', 'deleted', 'do_not_call')
        }),
        ('Follow-up', {
            'fields': ('followup_datetime', 'followup_remarks', 'date_reviewed', 'next_step')
        }),
        ('Course/Product', {
            'fields': ('course_id', 'course_name', 'course_amount')
        }),
        ('Lead Source', {
            'fields': ('lead_source', 'lead_source_description', 'refered_by', 'campaign_id')
        }),
        ('Revenue', {
            'fields': ('exp_revenue', 'exp_close_date')
        }),
        ('Transfer', {
            'fields': ('transfer_from', 'transfer_by', 'transfer_date')
        }),
        ('Additional', {
            'fields': ('description', 'birthdate', 'team_member')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )

@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ['lead', 'activity_type', 'user', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['lead__name', 'description']

@admin.register(LeadComment)
class LeadCommentAdmin(admin.ModelAdmin):
    list_display = ['lead', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['lead__name', 'comment']

@admin.register(LeadHistory)
class LeadHistoryAdmin(admin.ModelAdmin):
    list_display = ['lead', 'field_name', 'action', 'user', 'created_at']
    list_filter = ['action', 'field_name', 'created_at']
    search_fields = ['lead__name']

@admin.register(CommunicationHistory)
class CommunicationHistoryAdmin(admin.ModelAdmin):
    list_display = ['lead', 'communication_type', 'direction', 'sent_datetime', 'created_at']
    list_filter = ['communication_type', 'direction', 'created_at']
    search_fields = ['lead__name', 'text_msg']

@admin.register(BackOfficeUpdate)
class BackOfficeUpdateAdmin(admin.ModelAdmin):
    list_display = ['lead', 'bo_cat', 'bo_status', 'bo_date', 'created_at']
    list_filter = ['bo_status', 'bo_cat', 'created_at']
    search_fields = ['lead__name', 'bo_remarks']

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'email', 'phone', 'created_at']
    search_fields = ['name', 'email']
