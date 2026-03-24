from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Count, Q, Avg, F
from typing import List, Dict, Any, Optional
import logging

from dashboard.models import (
    Lead, InternalFollowUpReminder, User, TeamNotificationPreference
)
from .internal_notification_service import InternalNotificationService
from .internal_reminder_service import InternalReminderService

logger = logging.getLogger(__name__)

class TeamFollowUpMonitoringService:
    """
    Service for monitoring team follow-up compliance and performance.
    Handles overdue follow-ups, escalations, and team performance metrics.
    """
    
    def __init__(self):
        self.notification_service = InternalNotificationService()
        self.reminder_service = InternalReminderService()
    
    def monitor_team_overdue_followups(self, manager: Optional[User] = None) -> Dict[str, Any]:
        """
        Monitor and report on overdue follow-ups for a team.
        
        Args:
            manager: Manager to monitor team for (optional)
            
        Returns:
            Dict: Monitoring results
        """
        results = {
            'total_overdue': 0,
            'escalations_sent': 0,
            'teams_notified': 0,
            'overdue_by_user': {},
            'overdue_by_priority': {},
            'critical_overdue': []
        }
        
        # Get overdue follow-ups
        overdue_followups = self._get_overdue_followups(manager)
        results['total_overdue'] = overdue_followups.count()
        
        if results['total_overdue'] == 0:
            return results
        
        # Group by user
        overdue_by_user = overdue_followups.values('assigned_user__username').annotate(
            count=Count('id')
        ).order_by('-count')
        
        results['overdue_by_user'] = {
            item['assigned_user__username']: item['count'] 
            for item in overdue_by_user
        }
        
        # Group by priority
        overdue_by_priority = overdue_followups.values('followup_priority').annotate(
            count=Count('id')
        ).order_by('-count')
        
        results['overdue_by_priority'] = {
            item['followup_priority']: item['count'] 
            for item in overdue_by_priority
        }
        
        # Identify critical overdue (urgent priority or > 24 hours overdue)
        critical_cutoff = timezone.now() - timedelta(hours=24)
        critical_overdue = overdue_followups.filter(
            Q(followup_priority='urgent') | Q(followup_datetime__lt=critical_cutoff)
        )
        
        results['critical_overdue'] = list(critical_overdue.values(
            'id', 'name', 'mobile', 'assigned_user__username', 
            'followup_datetime', 'followup_priority'
        ))
        
        # Process escalations for critical items
        if results['critical_overdue']:
            escalation_results = self._process_critical_escalations(critical_overdue)
            results['escalations_sent'] = escalation_results['escalations_sent']
            results['teams_notified'] = escalation_results['teams_notified']
        
        return results
    
    def generate_team_performance_report(self, manager: User, days: int = 30) -> Dict[str, Any]:
        """
        Generate comprehensive team performance report.
        
        Args:
            manager: Manager requesting the report
            days: Number of days to analyze
            
        Returns:
            Dict: Performance report data
        """
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        # Get team members
        team_members = manager.get_accessible_users()
        
        report = {
            'period': f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}",
            'team_size': team_members.count(),
            'overall_metrics': self._calculate_overall_metrics(team_members, start_date, end_date),
            'individual_performance': self._calculate_individual_performance(team_members, start_date, end_date),
            'trend_analysis': self._analyze_trends(team_members, start_date, end_date),
            'compliance_metrics': self._calculate_compliance_metrics(team_members, start_date, end_date),
            'recommendations': []
        }
        
        # Generate recommendations
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def get_team_dashboard_data(self, user: User) -> Dict[str, Any]:
        """
        Get dashboard data for team overview.
        
        Args:
            user: User requesting dashboard data
            
        Returns:
            Dict: Dashboard data
        """
        team_members = user.get_accessible_users()
        now = timezone.now()
        
        dashboard_data = {
            'team_stats': {
                'total_members': team_members.count(),
                'active_today': team_members.filter(
                    last_activity__date=now.date()
                ).count(),
            },
            'followup_stats': {
                'scheduled_today': Lead.objects.filter(
                    assigned_user__in=team_members,
                    followup_datetime__date=now.date(),
                    followup_datetime__gte=now
                ).count(),
                'overdue': Lead.objects.filter(
                    assigned_user__in=team_members,
                    followup_datetime__lt=now,
                    status__in=['lead', 'interested_follow_up', 'contacted']
                ).count(),
                'completed_today': Lead.objects.filter(
                    assigned_user__in=team_members,
                    modified_at__date=now.date(),
                    status__in=['sale_done', 'not_interested', 'closed']
                ).count(),
            },
            'reminders_stats': {
                'pending_today': InternalFollowUpReminder.objects.filter(
                    user__in=team_members,
                    status='pending',
                    scheduled_datetime__date=now.date()
                ).count(),
                'sent_today': InternalFollowUpReminder.objects.filter(
                    user__in=team_members,
                    sent_at__date=now.date()
                ).count(),
                'acknowledged_today': InternalFollowUpReminder.objects.filter(
                    user__in=team_members,
                    acknowledged_at__date=now.date()
                ).count(),
            },
            'top_performers': self._get_top_performers(team_members, days=7),
            'urgent_items': self._get_urgent_team_items(team_members),
        }
        
        return dashboard_data
    
    def check_team_compliance(self, manager: User) -> Dict[str, Any]:
        """
        Check team compliance with follow-up procedures.
        
        Args:
            manager: Manager to check compliance for
            
        Returns:
            Dict: Compliance report
        """
        team_members = manager.get_accessible_users()
        now = timezone.now()
        
        compliance_report = {
            'overall_compliance_score': 0,
            'compliance_by_user': {},
            'violations': [],
            'improvement_areas': [],
        }
        
        total_score = 0
        user_count = 0
        
        for user in team_members:
            user_compliance = self._calculate_user_compliance(user)
            compliance_report['compliance_by_user'][user.username] = user_compliance
            
            if user_compliance['score'] > 0:
                total_score += user_compliance['score']
                user_count += 1
            
            # Check for violations
            if user_compliance['violations']:
                compliance_report['violations'].extend([
                    {
                        'user': user.username,
                        'violation': violation
                    }
                    for violation in user_compliance['violations']
                ])
        
        # Calculate overall compliance score
        if user_count > 0:
            compliance_report['overall_compliance_score'] = total_score / user_count
        
        # Identify improvement areas
        compliance_report['improvement_areas'] = self._identify_improvement_areas(
            compliance_report['compliance_by_user']
        )
        
        return compliance_report
    
    def _get_overdue_followups(self, manager: Optional[User] = None):
        """Get overdue follow-ups for a manager's team."""
        queryset = Lead.objects.filter(
            followup_datetime__lt=timezone.now(),
            status__in=['lead', 'interested_follow_up', 'contacted']
        )
        
        if manager:
            team_members = manager.get_accessible_users()
            queryset = queryset.filter(assigned_user__in=team_members)
        
        return queryset.select_related('assigned_user').order_by('followup_datetime')
    
    def _process_critical_escalations(self, critical_overdue) -> Dict[str, int]:
        """Process escalations for critical overdue items."""
        escalations_sent = 0
        teams_notified = 0
        
        for lead in critical_overdue:
            try:
                # Get escalation users for this lead's assigned user
                if lead.assigned_user:
                    escalation_users = []
                    if lead.assigned_user.team_lead:
                        escalation_users.append(lead.assigned_user.team_lead)
                    if lead.assigned_user.manager:
                        escalation_users.append(lead.assigned_user.manager)
                    
                    # Send escalation notifications
                    if escalation_users:
                        # Create escalation reminder
                        escalation_reminder = InternalFollowUpReminder.objects.create(
                            lead=lead,
                            user=lead.assigned_user,
                            reminder_type='escalation',
                            priority='urgent',
                            scheduled_datetime=timezone.now(),
                            followup_datetime=lead.followup_datetime,
                            notification_channels='all',
                            title=f"Escalation: {lead.name} Follow-up Overdue",
                            message=f"Critical: {lead.name} follow-up was due on {lead.followup_datetime}",
                            escalate_to_manager=True,
                            escalate_to_team_lead=True,
                            company_id=lead.company_id
                        )
                        
                        # Send notifications
                        success = self.notification_service.send_escalation_notification(
                            escalation_reminder, escalation_users
                        )
                        
                        if success:
                            escalations_sent += 1
                            teams_notified += len(set(escalation_users))
                
            except Exception as e:
                logger.error(f"Failed to process escalation for lead {lead.id}: {e}")
        
        return {
            'escalations_sent': escalations_sent,
            'teams_notified': teams_notified
        }
    
    def _calculate_overall_metrics(self, team_members, start_date, end_date) -> Dict[str, Any]:
        """Calculate overall team metrics."""
        leads = Lead.objects.filter(
            assigned_user__in=team_members,
            created_at__range=[start_date, end_date]
        )
        
        followups = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__range=[start_date, end_date]
        )
        
        completed = leads.filter(
            status__in=['sale_done', 'closed']
        )
        
        return {
            'total_leads': leads.count(),
            'total_followups': followups.count(),
            'completed_followups': completed.count(),
            'conversion_rate': (completed.count() / leads.count() * 100) if leads.count() > 0 else 0,
            'avg_followup_time': self._calculate_avg_followup_time(team_members, start_date, end_date),
        }
    
    def _calculate_individual_performance(self, team_members, start_date, end_date) -> List[Dict[str, Any]]:
        """Calculate individual performance metrics."""
        performance_data = []
        
        for user in team_members:
            leads = Lead.objects.filter(
                assigned_user=user,
                created_at__range=[start_date, end_date]
            )
            
            followups = Lead.objects.filter(
                assigned_user=user,
                followup_datetime__range=[start_date, end_date]
            )
            
            completed = leads.filter(
                status__in=['sale_done', 'closed']
            )
            
            overdue = Lead.objects.filter(
                assigned_user=user,
                followup_datetime__lt=timezone.now(),
                status__in=['lead', 'interested_follow_up', 'contacted']
            )
            
            performance_data.append({
                'user': user.username,
                'total_leads': leads.count(),
                'total_followups': followups.count(),
                'completed_followups': completed.count(),
                'overdue_count': overdue.count(),
                'conversion_rate': (completed.count() / leads.count() * 100) if leads.count() > 0 else 0,
                'followup_compliance': self._calculate_followup_compliance(user, start_date, end_date),
            })
        
        return sorted(performance_data, key=lambda x: x['conversion_rate'], reverse=True)
    
    def _analyze_trends(self, team_members, start_date, end_date) -> Dict[str, Any]:
        """Analyze performance trends over time."""
        # Simple trend analysis - compare with previous period
        previous_start = start_date - timedelta(days=(end_date - start_date).days)
        previous_end = start_date
        
        current_metrics = self._calculate_overall_metrics(team_members, start_date, end_date)
        previous_metrics = self._calculate_overall_metrics(team_members, previous_start, previous_end)
        
        return {
            'conversion_rate_trend': self._calculate_trend(
                current_metrics['conversion_rate'],
                previous_metrics['conversion_rate']
            ),
            'followup_volume_trend': self._calculate_trend(
                current_metrics['total_followups'],
                previous_metrics['total_followups']
            ),
            'completion_rate_trend': self._calculate_trend(
                (current_metrics['completed_followups'] / current_metrics['total_followups'] * 100) if current_metrics['total_followups'] > 0 else 0,
                (previous_metrics['completed_followups'] / previous_metrics['total_followups'] * 100) if previous_metrics['total_followups'] > 0 else 0
            ),
        }
    
    def _calculate_compliance_metrics(self, team_members, start_date, end_date) -> Dict[str, Any]:
        """Calculate team compliance metrics."""
        total_users = team_members.count()
        compliant_users = 0
        
        for user in team_members:
            compliance_score = self._calculate_user_compliance(user)['score']
            if compliance_score >= 80:  # 80% or higher is considered compliant
                compliant_users += 1
        
        return {
            'compliance_rate': (compliant_users / total_users * 100) if total_users > 0 else 0,
            'compliant_users': compliant_users,
            'total_users': total_users,
        }
    
    def _calculate_user_compliance(self, user: User) -> Dict[str, Any]:
        """Calculate compliance score for a single user."""
        score = 100  # Start with perfect score
        violations = []
        
        # Check for overdue follow-ups
        overdue_count = Lead.objects.filter(
            assigned_user=user,
            followup_datetime__lt=timezone.now(),
            status__in=['lead', 'interested_follow_up', 'contacted']
        ).count()
        
        if overdue_count > 0:
            score -= min(overdue_count * 10, 50)  # Deduct up to 50 points
            violations.append(f"{overdue_count} overdue follow-ups")
        
        # Check for missed reminders (reminders sent but not acknowledged)
        missed_reminders = InternalFollowUpReminder.objects.filter(
            user=user,
            status='sent',
            sent_at__lt=timezone.now() - timedelta(hours=24)
        ).count()
        
        if missed_reminders > 0:
            score -= min(missed_reminders * 5, 25)  # Deduct up to 25 points
            violations.append(f"{missed_reminders} unacknowledged reminders")
        
        return {
            'score': max(0, score),
            'violations': violations,
        }
    
    def _calculate_avg_followup_time(self, team_members, start_date, end_date) -> float:
        """Calculate average time to follow-up."""
        followups = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__range=[start_date, end_date],
            created_at__range=[start_date, end_date]
        ).exclude(
            followup_datetime__isnull=True
        )
        
        if not followups.exists():
            return 0.0
        
        total_time = sum(
            (f.followup_datetime - f.created_at).total_seconds() / 3600
            for f in followups
        )
        
        return total_time / followups.count()
    
    def _calculate_followup_compliance(self, user: User, start_date, end_date) -> float:
        """Calculate follow-up compliance rate for a user."""
        scheduled = Lead.objects.filter(
            assigned_user=user,
            followup_datetime__range=[start_date, end_date]
        ).count()
        
        if scheduled == 0:
            return 100.0
        
        completed = Lead.objects.filter(
            assigned_user=user,
            followup_datetime__range=[start_date, end_date],
            status__in=['sale_done', 'not_interested', 'closed', 'getting_better_deal']
        ).count()
        
        return (completed / scheduled) * 100
    
    def _calculate_trend(self, current: float, previous: float) -> str:
        """Calculate trend between two values."""
        if previous == 0:
            return 'up' if current > 0 else 'stable'
        
        change = ((current - previous) / previous) * 100
        
        if change > 5:
            return 'up'
        elif change < -5:
            return 'down'
        else:
            return 'stable'
    
    def _get_top_performers(self, team_members, days: int = 7) -> List[Dict[str, Any]]:
        """Get top performers for the period."""
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)
        
        performers = []
        for user in team_members:
            completed = Lead.objects.filter(
                assigned_user=user,
                modified_at__range=[start_date, end_date],
                status__in=['sale_done', 'closed']
            ).count()
            
            if completed > 0:
                performers.append({
                    'user': user.username,
                    'completed': completed,
                })
        
        return sorted(performers, key=lambda x: x['completed'], reverse=True)[:5]
    
    def _get_urgent_team_items(self, team_members) -> List[Dict[str, Any]]:
        """Get urgent items requiring attention."""
        urgent_items = []
        
        # Urgent overdue follow-ups
        urgent_overdue = Lead.objects.filter(
            assigned_user__in=team_members,
            followup_datetime__lt=timezone.now(),
            followup_priority='urgent',
            status__in=['lead', 'interested_follow_up', 'contacted']
        ).values('name', 'assigned_user__username', 'followup_datetime')[:5]
        
        for item in urgent_overdue:
            urgent_items.append({
                'type': 'urgent_overdue',
                'description': f"{item['name']} - {item['assigned_user__username']}",
                'priority': 'urgent',
            })
        
        return urgent_items
    
    def _identify_improvement_areas(self, compliance_by_user: Dict[str, Any]) -> List[str]:
        """Identify areas needing improvement."""
        areas = []
        
        # Check common issues across users
        overdue_issues = sum(
            1 for user_data in compliance_by_user.values()
            if any('overdue' in violation.lower() for violation in user_data['violations'])
        )
        
        reminder_issues = sum(
            1 for user_data in compliance_by_user.values()
            if any('reminder' in violation.lower() for violation in user_data['violations'])
        )
        
        if overdue_issues > len(compliance_by_user) * 0.5:
            areas.append("High rate of overdue follow-ups across team")
        
        if reminder_issues > len(compliance_by_user) * 0.3:
            areas.append("Poor reminder acknowledgment rates")
        
        return areas
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on report data."""
        recommendations = []
        
        # Based on compliance metrics
        if report['compliance_metrics']['compliance_rate'] < 80:
            recommendations.append("Consider additional training on follow-up procedures")
        
        # Based on overall metrics
        if report['overall_metrics']['conversion_rate'] < 20:
            recommendations.append("Review lead quality and sales process")
        
        # Based on trends
        if report['trend_analysis']['conversion_rate_trend'] == 'down':
            recommendations.append("Investigate reasons for declining conversion rates")
        
        return recommendations
