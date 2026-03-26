from django.urls import path
from . import views
from . import api_views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("profile/", views.profile, name="profile"),
    path("internal-reminders/", views.internal_reminders, name="internal_reminders"),
    path("team-dashboard/", views.team_dashboard, name="team_dashboard"),
    path("leads/", views.leads_list, name="leads_all"),
    path("leads/new/", views.lead_create, name="lead_create"),
    path("leads/import/", views.lead_import, name="lead_import"),
    path("leads/import/demo/", views.download_demo_file, name="download_demo_file"),
    path("leads/import/preview/", views.lead_import_preview, name="lead_import_preview"),
    path("leads/import/process/", views.lead_import_process, name="lead_import_process"),
    path("leads/fresh/", views.leads_fresh, name="leads_fresh"),
    path("leads/working/", views.leads_working, name="leads_working"),
    path("leads/transferred/", views.leads_transferred, name="leads_transferred"),
    path("leads/converted/", views.leads_converted, name="leads_converted"),
    path("leads/team/", views.leads_team, name="leads_team"),
    path("leads/bulk-assign/", views.bulk_lead_assign, name="bulk_lead_assign"),
    # Duplicate leads management
    path("leads/duplicates/", views.leads_duplicates, name="leads_duplicates"),
    path("leads/duplicates/team/", views.team_duplicate_leads, name="team_duplicate_leads"),
    path("leads/duplicates/my-duplicates/", views.my_duplicate_leads, name="my_duplicate_leads"),
    path("leads/duplicates/bulk-reassign/", views.bulk_duplicate_reassign, name="bulk_duplicate_reassign"),
    path("leads/<int:pk>/duplicate/", views.lead_duplicate_detail, name="lead_duplicate_detail"),
    path("leads/<int:pk>/duplicate/reassign/", views.lead_duplicate_reassign, name="lead_duplicate_reassign"),
    path("leads/<int:pk>/", views.lead_detail, name="lead_detail"),
    path("leads/<int:pk>/edit/", views.lead_edit, name="lead_edit"),
    path("leads/<int:pk>/assign/", views.lead_assign, name="lead_assign"),
    path("leads/<int:pk>/status/", views.lead_status_update, name="lead_status_update"),
    path("leads/<int:pk>/history/", views.lead_history, name="lead_history"),
    path("reports/", views.reports, name="reports"),
    path("settings/", views.settings, name="settings"),
    
    # AJAX endpoints for advanced filters
    path("ajax/get-countries/", api_views.get_countries, name="get_countries"),
    path("ajax/get-courses/", api_views.get_courses, name="get_courses"),
    path("ajax/get-team-members/", api_views.get_team_members, name="get_team_members"),
    
    # Internal Reminder API endpoints
    path("api/internal/reminders/", api_views.api_internal_reminders, name="api_internal_reminders"),
    path("api/internal/reminders/create/", api_views.api_internal_reminders_create, name="api_internal_reminders_create"),
    path("api/internal/reminders/<int:reminder_id>/update/", api_views.api_internal_reminders_update, name="api_internal_reminders_update"),
    path("api/internal/reminders/<int:reminder_id>/delete/", api_views.api_internal_reminders_delete, name="api_internal_reminders_delete"),
    path("api/internal/reminders/<int:reminder_id>/acknowledge/", api_views.api_internal_reminders_acknowledge, name="api_internal_reminders_acknowledge"),
    path("api/internal/reminders/<int:reminder_id>/snooze/", api_views.api_internal_reminders_snooze, name="api_internal_reminders_snooze"),
    path("api/internal/reminders/<int:reminder_id>/escalate/", api_views.api_internal_reminders_escalate, name="api_internal_reminders_escalate"),
    
    # Team Notification Preferences API
    path("api/internal/notifications/preferences/", api_views.api_notification_preferences, name="api_notification_preferences"),
    path("api/internal/notifications/preferences/update/", api_views.api_notification_preferences_update, name="api_notification_preferences_update"),
    
    # Team Follow-up Dashboard API
    path("api/internal/followups/dashboard/", api_views.api_followup_dashboard, name="api_followup_dashboard"),
    path("api/internal/followups/team/", api_views.api_followup_team, name="api_followup_team"),
    path("api/internal/followups/overdue/", api_views.api_followup_overdue, name="api_followup_overdue"),
    path("api/internal/followups/performance/", api_views.api_followup_performance, name="api_followup_performance"),
    
    # Hierarchy Management API
    path("api/internal/followups/hierarchy/", api_views.api_followup_hierarchy, name="api_followup_hierarchy"),
    path("api/internal/followups/notify-team/", api_views.api_notify_team, name="api_notify_team"),
    
    # Quick Status Update API
    path("ajax/lead-status-update/", api_views.ajax_lead_status_update, name="ajax_lead_status_update"),
]
