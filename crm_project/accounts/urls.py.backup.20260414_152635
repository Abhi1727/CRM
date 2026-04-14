from django.urls import path
from . import views
from . import api_views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # User management
    path('users/', views.user_list, name='user_list'),
    path('users/create/', views.create_user, name='create_user'),
    path('users/<int:user_id>/edit/', views.edit_user, name='edit_user'),
    path('users/<int:user_id>/delete/', views.delete_user, name='delete_user'),
    path('users/performance/', views.user_performance, name='user_performance'),
    path('team-hierarchy/', views.team_hierarchy, name='team_hierarchy'),
    
    # Lead assignment
    path('assign-lead/', views.assign_lead, name='assign_lead'),
    path('bulk-assign/', views.bulk_assign_leads, name='bulk_assign'),
    path('get-users-by-role/', views.get_users_by_role, name='get_users_by_role'),
    path('transfer-history/', views.lead_transfer_history, name='transfer_history'),
    
    # Username availability check
    path('check-username/', views.check_username_availability, name='check_username'),
    
    # Team leads by manager
    path('get-team-leads-by-manager/', views.get_team_leads_by_manager, name='get_team_leads_by_manager'),
    
    # Undo functionality
    path('undo-assignments/', views.undo_assignments, name='undo_assignments'),
    path('undo-history/', views.get_undo_history, name='get_undo_history'),
    
    # API endpoints
    path('api/users-for-reassignment/', api_views.get_all_users_for_reassignment, name='api_users_for_reassignment'),
    path('api/user/<int:user_id>/lead-summary/', api_views.get_user_lead_summary, name='api_user_lead_summary'),
]
