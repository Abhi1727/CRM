from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import json
import logging

from dashboard.models import User
from services.team_followup_monitoring_service import TeamFollowUpMonitoringService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate team follow-up compliance reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--manager-id',
            type=int,
            help='Generate report for specific manager (optional)',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to analyze (default: 30)',
        )
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (optional, prints to console if not provided)',
        )
        parser.add_argument(
            '--format',
            choices=['json', 'text'],
            default='text',
            help='Output format (default: text)',
        )
    
    def handle(self, *args, **options):
        manager_id = options['manager_id']
        days = options['days']
        output_file = options['output']
        output_format = options['format']
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Generating team follow-up report (days={days}, format={output_format})"
            )
        )
        
        monitoring_service = TeamFollowUpMonitoringService()
        
        # Get manager(s) to generate reports for
        if manager_id:
            try:
                managers = [User.objects.get(id=manager_id, role='manager')]
                self.stdout.write(f"Generating report for manager: {managers[0].username}")
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Manager with ID {manager_id} not found")
                )
                return
        else:
            managers = User.objects.filter(role='manager', account_status='active')
            self.stdout.write(f"Generating reports for {managers.count()} managers")
        
        all_reports = []
        
        for manager in managers:
            try:
                # Generate comprehensive performance report
                report = monitoring_service.generate_team_performance_report(manager, days)
                
                # Generate compliance report
                compliance_report = monitoring_service.check_team_compliance(manager)
                
                # Combine reports
                combined_report = {
                    'manager': {
                        'username': manager.username,
                        'full_name': manager.get_full_name(),
                        'email': manager.email,
                    },
                    'performance_report': report,
                    'compliance_report': compliance_report,
                    'generated_at': timezone.now().isoformat(),
                }
                
                all_reports.append(combined_report)
                
                # Display summary for this manager
                self.stdout.write(
                    f"\n📊 {manager.username}'s Team Report:"
                )
                self.stdout.write(
                    f"  Team Size: {report['team_size']}"
                )
                self.stdout.write(
                    f"  Conversion Rate: {report['overall_metrics']['conversion_rate']:.1f}%"
                )
                self.stdout.write(
                    f"  Compliance Score: {compliance_report['overall_compliance_score']:.1f}%"
                )
                self.stdout.write(
                    f"  Total Leads: {report['overall_metrics']['total_leads']}"
                )
                
            except Exception as e:
                logger.error(f"Error generating report for manager {manager.username}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Error generating report for {manager.username}: {e}")
                )
        
        # Output results
        if output_format == 'json':
            output_data = {
                'report_metadata': {
                    'generated_at': timezone.now().isoformat(),
                    'days_analyzed': days,
                    'total_managers': len(all_reports),
                },
                'reports': all_reports,
            }
            
            output_content = json.dumps(output_data, indent=2, default=str)
        else:
            # Text format
            output_lines = [
                "TEAM FOLLOW-UP COMPLIANCE REPORTS",
                "=" * 50,
                f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
                f"Period: Last {days} days",
                f"Managers: {len(all_reports)}",
                "",
            ]
            
            for report_data in all_reports:
                manager = report_data['manager']
                perf = report_data['performance_report']
                comp = report_data['compliance_report']
                
                output_lines.extend([
                    f"MANAGER: {manager['username']} ({manager['full_name']})",
                    "-" * 40,
                    f"Team Size: {perf['team_size']}",
                    f"Total Leads: {perf['overall_metrics']['total_leads']}",
                    f"Conversion Rate: {perf['overall_metrics']['conversion_rate']:.1f}%",
                    f"Compliance Score: {comp['overall_compliance_score']:.1f}%",
                    f"Compliant Users: {comp['compliance_metrics']['compliant_users']}/{comp['compliance_metrics']['total_users']}",
                    "",
                ])
                
                # Top performers
                if perf['individual_performance']:
                    output_lines.append("Top Performers:")
                    for i, perf_data in enumerate(perf['individual_performance'][:3], 1):
                        output_lines.append(
                            f"  {i}. {perf_data['user']}: {perf_data['conversion_rate']:.1f}% conversion"
                        )
                    output_lines.append("")
                
                # Recommendations
                if perf['recommendations']:
                    output_lines.append("Recommendations:")
                    for rec in perf['recommendations']:
                        output_lines.append(f"  • {rec}")
                    output_lines.append("")
            
            output_content = "\n".join(output_lines)
        
        # Save to file or print to console
        if output_file:
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(output_content)
                self.stdout.write(
                    self.style.SUCCESS(f"Report saved to: {output_file}")
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to save report to {output_file}: {e}")
                )
        else:
            self.stdout.write("\n" + output_content)
        
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Generated reports for {len(all_reports)} managers"
            )
        )
