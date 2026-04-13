"""
Celery configuration for CRM async processing
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')

app = Celery('crm')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

# Configure Celery for performance
app.conf.update(
    # Task execution
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Worker configuration
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    
    # Task routing
    task_routes={
        'dashboard.tasks.bulk_lead_assignment': {'queue': 'bulk_operations'},
        'dashboard.tasks.bulk_lead_deletion': {'queue': 'bulk_operations'},
        'dashboard.tasks.bulk_lead_import': {'queue': 'bulk_operations'},
        'dashboard.tasks.send_notifications': {'queue': 'notifications'},
        'dashboard.tasks.generate_reports': {'queue': 'reports'},
    },
    
    # Task time limits
    task_soft_time_limit=300,  # 5 minutes
    task_time_limit=600,       # 10 minutes
    
    # Result backend
    result_backend='django-cache',
    result_expires=3600,  # 1 hour
    
    # Beat scheduler for periodic tasks
    beat_schedule={
        'cleanup-old-cache': {
            'task': 'dashboard.tasks.cleanup_old_cache',
            'schedule': 3600.0,  # Every hour
        },
        'update-dashboard-stats': {
            'task': 'dashboard.tasks.update_dashboard_stats',
            'schedule': 300.0,   # Every 5 minutes
        },
    },
)

@app.task(bind=True)
def debug_task(self):
    """Debug task for testing Celery connectivity"""
    print(f'Request: {self.request!r}')
