from django.urls import path
from . import views
from . import api_views
from . import views_performance

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
    path("leads/import/status/", views.lead_import_status, name="lead_import_status"),
    path("leads/import/process/", views.lead_import_process, name="lead_import_process"),
    
    # Enterprise Import URLs
    path("leads/import/enterprise/", views.enterprise_lead_import, name="enterprise_lead_import"),
    path("leads/import/enterprise/progress/<int:operation_id>/", views.enterprise_import_progress, name="enterprise_import_progress"),
    path("leads/import/enterprise/cancel/<int:operation_id>/", views.enterprise_import_cancel, name="enterprise_import_cancel"),
    path("leads/fresh/", views.leads_fresh, name="leads_fresh"),
    path("leads/working/", views.leads_working, name="leads_working"),
    path("leads/transferred/", views.leads_transferred, name="leads_transferred"),
    path("leads/converted/", views.leads_converted, name="leads_converted"),
    path("leads/team/", views.leads_team, name="leads_team"),
    path("leads/trash/", views.leads_trash, name="leads_trash"),
    path("leads/bulk-assign/", views.bulk_lead_assign, name="bulk_lead_assign"),
    path("leads/bulk-delete/", views.bulk_lead_delete, name="bulk_lead_delete"),
    path("leads/bulk-restore/", views.bulk_lead_restore, name="bulk_lead_restore"),
    path("leads/trash/purge/", views.leads_trash_purge, name="leads_trash_purge"),
    path("reports/operations.csv", views.operations_report_csv, name="operations_report_csv"),
    # Duplicate leads management
    path("leads/duplicates/", views.leads_duplicates, name="leads_duplicates"),
    path("leads/duplicates/team/", views.team_duplicate_leads, name="team_duplicate_leads"),
    path("leads/duplicates/my-duplicates/", views.my_duplicate_leads, name="my_duplicate_leads"),
    path("leads/duplicates/bulk-reassign/", views.bulk_duplicate_reassign, name="bulk_duplicate_reassign"),
    path("leads/duplicates/bulk-resolve/", views.bulk_duplicate_resolve, name="bulk_duplicate_resolve"),
    path("leads/duplicates/bulk-ignore/", views.bulk_duplicate_ignore, name="bulk_duplicate_ignore"),
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
    path("ajax/available-roles/", api_views.get_available_roles, name="get_available_roles"),
    
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
    
    # Inline Editing API
    path("ajax/inline-field-update/", api_views.ajax_inline_field_update, name="ajax_inline_field_update"),
    path("ajax/field-validation-rules/", api_views.get_lead_field_validation_rules, name="get_lead_field_validation_rules"),
    
    # Bulk Operations Progress Tracking API
    path("api/bulk-operation-progress/<str:operation_id>/", api_views.bulk_operation_progress, name="bulk_operation_progress"),
    path("api/running-operations/", api_views.running_operations, name="running_operations"),
    path("api/bulk-operation-cancel/<str:operation_id>/", api_views.bulk_operation_cancel, name="bulk_operation_cancel"),
    path("api/bulk-operations-history/", api_views.bulk_operations_history, name="bulk_operations_history"),
    path("api/bulk-operation-details/<str:operation_id>/", api_views.bulk_operation_details, name="bulk_operation_details"),
    
    # Import Progress Tracking API
    path("api/import-progress/", api_views.import_progress, name="import_progress"),
    path("api/running-imports/", api_views.running_imports, name="running_imports"),
    path("api/import-cancel/", api_views.cancel_import, name="cancel_import"),
    path("api/import-history/", api_views.import_history, name="import_history"),
    
    # Performance Monitoring URLs
    path("performance/", views_performance.performance_dashboard, name="performance_dashboard"),
    path("api/performance/stats/", views_performance.api_performance_stats, name="api_performance_stats"),
    path("api/performance/clear-cache/", views_performance.clear_performance_cache, name="clear_performance_cache"),
    path("api/performance/test-bulk-assignment/", views_performance.test_bulk_assignment_performance, name="test_bulk_assignment_performance"),
]
