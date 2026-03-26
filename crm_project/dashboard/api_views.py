from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import json
import logging

from dashboard.models import (
    Lead, InternalFollowUpReminder, InternalNotificationTemplate, 
    TeamNotificationPreference, User, LeadHistory, LeadActivity
)
from services.internal_reminder_service import InternalReminderService
from services.internal_notification_service import InternalNotificationService
from services.team_followup_monitoring_service import TeamFollowUpMonitoringService
from services.hierarchy_notification_service import HierarchyNotificationService

logger = logging.getLogger(__name__)

# New AJAX endpoints for countries, courses, and team members

@login_required
def get_countries(request):
    """Get distinct countries from leads for filter dropdown"""
    try:
        # Get accessible leads based on hierarchy
        if hasattr(request, 'hierarchy_context'):
            accessible_leads = request.hierarchy_context['accessible_leads']
        else:
            accessible_leads = Lead.objects.filter(company_id=request.user.company_id)
        
        # Get distinct countries
        countries = list(accessible_leads
                      .exclude(country__isnull=True, country__exact='')
                      .values_list('country', flat=True)
                      .distinct())
        
        # Filter out empty values and sort
        countries = [country for country in countries if country and country.strip()]
        countries.sort()
        
        return JsonResponse({'countries': countries})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_courses(request):
    """Get distinct courses from leads for filter dropdown"""
    try:
        # Get accessible leads based on hierarchy
        if hasattr(request, 'hierarchy_context'):
            accessible_leads = request.hierarchy_context['accessible_leads']
        else:
            accessible_leads = Lead.objects.filter(company_id=request.user.company_id)
        
        # Get distinct courses
        courses = list(accessible_leads
                    .exclude(course_name__isnull=True, course_name__exact='')
                    .values_list('course_name', flat=True)
                    .distinct())
        
        # Filter out empty values and sort
        courses = [course for course in courses if course and course.strip()]
        courses.sort()
        
        return JsonResponse({'courses': courses})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_team_members(request):
    """Get team members based on user hierarchy for filter dropdown"""
    try:
        user = request.user
        team_members = []
        
        if user.role == 'owner':
            # Owner can see all users in company
            members = User.objects.filter(
                company_id=user.company_id,
                account_status='active'
            ).exclude(id=user.id).order_by('username')
            
            for member in members:
                team_members.append({
                    'id': member.id,
                    'name': member.get_full_name() or member.username,
                    'role': member.get_role_display()
                })
                
        elif user.role == 'manager':
            # Manager can see team leads and agents they manage
            # Get team leads and their agents
            team_leads = User.objects.filter(
                Q(manager=user) | Q(team_lead=user),
                company_id=user.company_id,
                account_status='active'
            ).exclude(id=user.id)
            
            # Also get agents under those team leads
            agents = User.objects.filter(
                team_lead__in=team_leads,
                company_id=user.company_id,
                account_status='active'
            ).exclude(id=user.id)
            
            # Combine team leads and agents
            all_members = (team_leads | agents).distinct().order_by('username')
            
            for member in all_members:
                team_members.append({
                    'id': member.id,
                    'name': member.get_full_name() or member.username,
                    'role': member.get_role_display()
                })
                
        elif user.role == 'team_lead':
            # Team Lead can see their agents only
            agents = User.objects.filter(
                team_lead=user,
                company_id=user.company_id,
                account_status='active'
            ).exclude(id=user.id).order_by('username')
            
            for member in agents:
                team_members.append({
                    'id': member.id,
                    'name': member.get_full_name() or member.username,
                    'role': member.get_role_display()
                })
                
        elif user.role == 'agent':
            # Agent can only see themselves
            team_members.append({
                'id': user.id,
                'name': user.get_full_name() or user.username,
                'role': user.get_role_display()
            })
        
        return JsonResponse({'team_members': team_members})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# Internal Reminder Management API

@require_http_methods(["GET"])
@login_required
def api_internal_reminders(request):
    """List user's internal reminders"""
    user = request.user
    
    # Get query parameters
    status_filter = request.GET.get('status', 'all')
    priority_filter = request.GET.get('priority', 'all')
    limit = int(request.GET.get('limit', 50))
    
    # Build queryset
    reminders = InternalFollowUpReminder.objects.filter(user=user)
    
    if status_filter != 'all':
        reminders = reminders.filter(status=status_filter)
    
    if priority_filter != 'all':
        reminders = reminders.filter(priority=priority_filter)
    
    # Order and limit
    reminders = reminders.order_by('scheduled_datetime')[:limit]
    
    # Serialize
    data = []
    for reminder in reminders:
        data.append({
            'id': reminder.id,
            'title': reminder.title,
            'message': reminder.message,
            'priority': reminder.priority,
            'status': reminder.status,
            'scheduled_datetime': reminder.scheduled_datetime.isoformat(),
            'followup_datetime': reminder.followup_datetime.isoformat(),
            'lead': {
                'id': reminder.lead.id,
                'name': reminder.lead.name,
                'mobile': reminder.lead.mobile,
            },
            'team_notes': reminder.team_notes,
            'created_at': reminder.created_at.isoformat(),
        })
    
    return JsonResponse({
        'success': True,
        'data': data,
        'count': len(data),
    })

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def api_internal_reminders_create(request):
    """Create new internal reminder"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        lead_id = data.get('lead_id')
        if not lead_id:
            return JsonResponse({
                'success': False,
                'error': 'lead_id is required'
            }, status=400)
        
        lead = get_object_or_404(Lead, id=lead_id)
        
        # Check if user can create reminder for this lead
        if not lead.can_be_accessed_by(request.user):
            return JsonResponse({
                'success': False,
                'error': 'You cannot create reminders for this lead'
            }, status=403)
        
        reminder_service = InternalReminderService()
        
        # Create reminder
        reminder = reminder_service.create_reminder_for_lead(
            lead=lead,
            user=request.user,
            reminder_type=data.get('reminder_type', 'followup'),
            priority=data.get('priority', 'medium'),
            reminder_before_minutes=data.get('reminder_before_minutes'),
            notification_channels=data.get('notification_channels', 'in_app'),
            team_notes=data.get('team_notes', ''),
            escalate_to_manager=data.get('escalate_to_manager', False),
            escalate_to_team_lead=data.get('escalate_to_team_lead', False),
            escalation_minutes=data.get('escalation_minutes', 60),
            created_by=request.user
        )
        
        if not reminder:
            return JsonResponse({
                'success': False,
                'error': 'Failed to create reminder (past scheduled time?)'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': reminder.id,
                'title': reminder.title,
                'scheduled_datetime': reminder.scheduled_datetime.isoformat(),
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["PUT"])
@csrf_exempt
@login_required
def api_internal_reminders_update(request, reminder_id):
    """Update internal reminder"""
    try:
        reminder = get_object_or_404(
            InternalFollowUpReminder, 
            id=reminder_id, 
            user=request.user
        )
        
        data = json.loads(request.body)
        
        # Update allowed fields
        if 'priority' in data:
            reminder.priority = data['priority']
        
        if 'notification_channels' in data:
            reminder.notification_channels = data['notification_channels']
        
        if 'team_notes' in data:
            reminder.team_notes = data['team_notes']
        
        if 'escalate_to_manager' in data:
            reminder.escalate_to_manager = data['escalate_to_manager']
        
        if 'escalate_to_team_lead' in data:
            reminder.escalate_to_team_lead = data['escalate_to_team_lead']
        
        reminder.save()
        
        return JsonResponse({
            'success': True,
            'data': {
                'id': reminder.id,
                'updated_at': reminder.updated_at.isoformat(),
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["DELETE"])
@login_required
def api_internal_reminders_delete(request, reminder_id):
    """Cancel internal reminder"""
    try:
        reminder = get_object_or_404(
            InternalFollowUpReminder, 
            id=reminder_id, 
            user=request.user
        )
        
        if reminder.status not in ['pending', 'sent']:
            return JsonResponse({
                'success': False,
                'error': 'Cannot cancel reminder in current status'
            }, status=400)
        
        reminder.status = 'cancelled'
        reminder.save(update_fields=['status'])
        
        return JsonResponse({
            'success': True,
            'message': 'Reminder cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error cancelling internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def api_internal_reminders_acknowledge(request, reminder_id):
    """Acknowledge internal reminder"""
    try:
        reminder_service = InternalReminderService()
        success = reminder_service.acknowledge_reminder(reminder_id, request.user)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Reminder acknowledged successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to acknowledge reminder'
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error acknowledging internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def api_internal_reminders_snooze(request, reminder_id):
    """Snooze internal reminder"""
    try:
        data = json.loads(request.body)
        minutes = data.get('minutes', 30)
        
        reminder_service = InternalReminderService()
        success = reminder_service.snooze_reminder(reminder_id, request.user, minutes)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'Reminder snoozed for {minutes} minutes'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to snooze reminder'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error snoozing internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def api_internal_reminders_escalate(request, reminder_id):
    """Manual escalation of internal reminder"""
    try:
        reminder = get_object_or_404(
            InternalFollowUpReminder, 
            id=reminder_id, 
            user=request.user
        )
        
        data = json.loads(request.body)
        escalation_level = data.get('level', 1)
        
        hierarchy_service = HierarchyNotificationService()
        success = hierarchy_service.escalate_through_hierarchy(reminder, escalation_level)
        
        if success:
            return JsonResponse({
                'success': True,
                'message': f'Reminder escalated to level {escalation_level}'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to escalate reminder'
            }, status=400)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error escalating internal reminder: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# Team Notification Preferences API

@require_http_methods(["GET"])
@login_required
def api_notification_preferences(request):
    """Get team member preferences"""
    try:
        reminder_service = InternalReminderService()
        preferences = reminder_service.get_user_reminder_preferences(request.user)
        
        return JsonResponse({
            'success': True,
            'data': preferences
        })
        
    except Exception as e:
        logger.error(f"Error getting notification preferences: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["PUT"])
@csrf_exempt
@login_required
def api_notification_preferences_update(request):
    """Update team member preferences"""
    try:
        data = json.loads(request.body)
        
        for notification_type, prefs in data.items():
            # Get or create preference
            preference, created = TeamNotificationPreference.objects.get_or_create(
                user=request.user,
                notification_type=notification_type,
                defaults={
                    'in_app_enabled': prefs.get('in_app_enabled', True),
                    'email_enabled': prefs.get('email_enabled', True),
                    'sms_enabled': prefs.get('sms_enabled', False),
                    'quiet_hours_start': prefs.get('quiet_hours_start'),
                    'quiet_hours_end': prefs.get('quiet_hours_end'),
                    'timezone': prefs.get('timezone', 'UTC'),
                    'daily_summary_enabled': prefs.get('daily_summary_enabled', False),
                    'weekly_summary_enabled': prefs.get('weekly_summary_enabled', False),
                    'team_alerts_enabled': prefs.get('team_alerts_enabled', True),
                    'escalation_alerts_enabled': prefs.get('escalation_alerts_enabled', True),
                }
            )
            
            if not created:
                # Update existing preference
                preference.in_app_enabled = prefs.get('in_app_enabled', preference.in_app_enabled)
                preference.email_enabled = prefs.get('email_enabled', preference.email_enabled)
                preference.sms_enabled = prefs.get('sms_enabled', preference.sms_enabled)
                preference.quiet_hours_start = prefs.get('quiet_hours_start', preference.quiet_hours_start)
                preference.quiet_hours_end = prefs.get('quiet_hours_end', preference.quiet_hours_end)
                preference.timezone = prefs.get('timezone', preference.timezone)
                preference.daily_summary_enabled = prefs.get('daily_summary_enabled', preference.daily_summary_enabled)
                preference.weekly_summary_enabled = prefs.get('weekly_summary_enabled', preference.weekly_summary_enabled)
                preference.team_alerts_enabled = prefs.get('team_alerts_enabled', preference.team_alerts_enabled)
                preference.escalation_alerts_enabled = prefs.get('escalation_alerts_enabled', preference.escalation_alerts_enabled)
                preference.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Preferences updated successfully'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating notification preferences: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# Team Follow-up Dashboard API

@require_http_methods(["GET"])
@login_required
def api_followup_dashboard(request):
    """Team follow-up dashboard data"""
    try:
        monitoring_service = TeamFollowUpMonitoringService()
        dashboard_data = monitoring_service.get_team_dashboard_data(request.user)
        
        return JsonResponse({
            'success': True,
            'data': dashboard_data
        })
        
    except Exception as e:
        logger.error(f"Error getting follow-up dashboard: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@login_required
def api_followup_team(request):
    """Team follow-up overview"""
    try:
        # Get team members
        team_members = request.user.get_accessible_users()
        
        # Calculate team metrics
        now = timezone.now()
        
        team_data = {
            'members': [],
            'summary': {
                'total_members': team_members.count(),
                'active_today': team_members.filter(
                    last_activity__date=now.date()
                ).count(),
            }
        }
        
        for member in team_members:
            # Get member's follow-up stats
            member_leads = Lead.objects.filter(assigned_user=member)
            
            member_data = {
                'id': member.id,
                'username': member.username,
                'full_name': member.get_full_name(),
                'role': member.role,
                'total_leads': member_leads.count(),
                'scheduled_today': member_leads.filter(
                    followup_datetime__date=now.date(),
                    followup_datetime__gte=now
                ).count(),
                'overdue': member_leads.filter(
                    followup_datetime__lt=now,
                    status__in=['lead', 'interested_follow_up', 'contacted']
                ).count(),
                'completed_today': member_leads.filter(
                    modified_at__date=now.date(),
                    status__in=['sale_done', 'not_interested', 'closed']
                ).count(),
                'last_activity': member.last_activity.isoformat() if member.last_activity else None,
            }
            
            team_data['members'].append(member_data)
        
        return JsonResponse({
            'success': True,
            'data': team_data
        })
        
    except Exception as e:
        logger.error(f"Error getting team follow-up data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@login_required
def api_followup_overdue(request):
    """Team overdue follow-ups"""
    try:
        # Get team members
        team_members = request.user.get_accessible_users()
        
        # Get overdue follow-ups
        now = timezone.now()
        overdue_leads = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__lt=now,
            status__in=['lead', 'interested_follow_up', 'contacted']
        ).select_related('assigned_user').order_by('followup_datetime')
        
        overdue_data = []
        for lead in overdue_leads:
            overdue_hours = (now - lead.followup_datetime).total_seconds() / 3600
            
            overdue_data.append({
                'id': lead.id,
                'name': lead.name,
                'mobile': lead.mobile,
                'assigned_user': {
                    'id': lead.assigned_user.id,
                    'username': lead.assigned_user.username,
                    'full_name': lead.assigned_user.get_full_name(),
                },
                'followup_datetime': lead.followup_datetime.isoformat(),
                'priority': lead.followup_priority,
                'overdue_hours': round(overdue_hours, 1),
                'followup_remarks': lead.followup_remarks,
            })
        
        return JsonResponse({
            'success': True,
            'data': overdue_data,
            'count': len(overdue_data),
        })
        
    except Exception as e:
        logger.error(f"Error getting overdue follow-ups: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["GET"])
@login_required
def api_followup_performance(request):
    """Team performance metrics"""
    try:
        days = int(request.GET.get('days', 30))
        
        monitoring_service = TeamFollowUpMonitoringService()
        
        if request.user.role in ['manager', 'owner']:
            # Get team performance report
            report = monitoring_service.generate_team_performance_report(request.user, days)
        else:
            # Get individual performance
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            leads = Lead.objects.filter(
                assigned_user=request.user,
                created_at__range=[start_date, end_date]
            )
            
            completed = leads.filter(
                status__in=['sale_done', 'closed']
            )
            
            report = {
                'overall_metrics': {
                    'total_leads': leads.count(),
                    'completed_followups': completed.count(),
                    'conversion_rate': (completed.count() / leads.count() * 100) if leads.count() > 0 else 0,
                }
            }
        
        return JsonResponse({
            'success': True,
            'data': report
        })
        
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

# Hierarchy Management API

@require_http_methods(["GET"])
@login_required
def api_followup_hierarchy(request):
    """Hierarchy-based follow-up view"""
    try:
        hierarchy_service = HierarchyNotificationService()
        dashboard_data = hierarchy_service.get_hierarchy_dashboard_data(request.user)
        
        return JsonResponse({
            'success': True,
            'data': dashboard_data
        })
        
    except Exception as e:
        logger.error(f"Error getting hierarchy data: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@require_http_methods(["POST"])
@csrf_exempt
@login_required
def api_notify_team(request):
    """Send team notifications"""
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        notification_type = data.get('notification_type', 'team_alert')
        include_all_teams = data.get('include_all_teams', False)
        
        if not message:
            return JsonResponse({
                'success': False,
                'error': 'Message is required'
            }, status=400)
        
        if request.user.role not in ['manager', 'owner']:
            return JsonResponse({
                'success': False,
                'error': 'Only managers and owners can send team notifications'
            }, status=403)
        
        hierarchy_service = HierarchyNotificationService()
        success = hierarchy_service.send_cross_team_notification(
            manager=request.user,
            message=message,
            notification_type=notification_type,
            include_all_teams=include_all_teams
        )
        
        if success:
            return JsonResponse({
                'success': True,
                'message': 'Team notification sent successfully'
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Failed to send team notification'
            }, status=500)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error sending team notification: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def ajax_lead_status_update(request):
    """Quick status update via AJAX"""
    try:
        data = json.loads(request.body)
        lead_id = data.get('lead_id')
        new_status = data.get('status')
        followup_datetime = data.get('followup_datetime')
        followup_remarks = data.get('followup_remarks', '')
        
        if not lead_id or not new_status:
            return JsonResponse({
                'success': False,
                'error': 'Lead ID and status are required'
            }, status=400)
        
        # Get the lead
        lead = get_object_or_404(Lead, id_lead=lead_id)
        
        # Check if user can access this lead
        if not lead.can_be_accessed_by(request.user):
            return JsonResponse({
                'success': False,
                'error': 'You do not have permission to update this lead'
            }, status=403)
        
        # Store old status for history
        old_status = lead.status
        
        # Update lead status
        lead.status = new_status
        
        # Update follow-up information if provided
        if followup_datetime:
            from datetime import datetime
            try:
                # Parse the datetime string
                followup_dt = datetime.fromisoformat(followup_datetime.replace('Z', '+00:00'))
                lead.followup_datetime = followup_dt
            except ValueError:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid follow-up datetime format'
                }, status=400)
        
        if followup_remarks:
            lead.followup_remarks = followup_remarks
        
        lead.modified_user = request.user
        lead.save()
        
        # Create lead history record
        LeadHistory.objects.create(
            lead=lead,
            user=request.user,
            field_name='status',
            old_value=old_status,
            new_value=new_status,
            action='status_change'
        )
        
        # Create activity log
        LeadActivity.objects.create(
            lead=lead,
            user=request.user,
            activity_type='status_change',
            description=f'Status changed from {lead.get_status_display(old_status)} to {lead.get_status_display()}'
        )
        
        # Check if follow-up is needed for this status
        needs_followup = new_status in ['interested_follow_up', 'call_back', 'in_few_months']
        
        return JsonResponse({
            'success': True,
            'message': 'Status updated successfully',
            'new_status': new_status,
            'new_status_display': lead.get_status_display(),
            'needs_followup': needs_followup,
            'followup_datetime': lead.followup_datetime.isoformat() if lead.followup_datetime else None
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
