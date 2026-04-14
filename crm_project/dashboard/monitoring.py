"""
Enterprise import monitoring and performance tracking
Provides real-time monitoring, alerting, and performance metrics for large-scale imports
"""

import logging
import psutil
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from django.core.cache import cache
from django.db import connection
from django.db import models
from django.conf import settings
from django.utils import timezone
from .models import BulkOperation, BulkOperationProgress

logger = logging.getLogger(__name__)


class ImportMonitor:
    """
    Real-time monitoring system for enterprise lead imports.
    Tracks performance metrics, resource usage, and provides alerting.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.start_time = datetime.now()
        self.metrics = {
            'start_time': self.start_time,
            'session_id': session_id,
            'processing_rate': 0.0,
            'memory_usage_mb': 0.0,
            'cpu_usage_percent': 0.0,
            'db_connections': 0,
            'error_rate': 0.0,
            'cache_hit_rate': 0.0,
            'disk_io_mb': 0.0,
            'network_io_mb': 0.0,
            'alerts': []
        }
        
        # Performance thresholds
        self.thresholds = {
            'memory_usage_mb': 500,  # Alert if > 500MB
            'processing_rate': 10,    # Alert if < 10 leads/sec
            'error_rate': 0.1,       # Alert if > 0.1%
            'cpu_usage_percent': 80, # Alert if > 80%
            'db_connections': 50,    # Alert if > 50 connections
        }
        
        # Initial system metrics
        self.initial_io = psutil.disk_io_counters()
        self.initial_net_io = psutil.net_io_counters()
    
    def track_performance(self, metric: str, value: float):
        """
        Track a performance metric and check thresholds.
        
        Args:
            metric: Metric name
            value: Metric value
        """
        self.metrics[metric] = value
        
        # Check if threshold exceeded and send alert
        if metric in self.thresholds:
            threshold = self.thresholds[metric]
            
            if metric == 'processing_rate' and value < threshold:
                self.send_alert(f'Low processing rate: {value:.1f} leads/sec (threshold: {threshold})', 'warning')
            elif metric == 'memory_usage_mb' and value > threshold:
                self.send_alert(f'High memory usage: {value:.1f}MB (threshold: {threshold}MB)', 'warning')
            elif metric == 'error_rate' and value > threshold:
                self.send_alert(f'High error rate: {value:.2f}% (threshold: {threshold}%)', 'error')
            elif metric == 'cpu_usage_percent' and value > threshold:
                self.send_alert(f'High CPU usage: {value:.1f}% (threshold: {threshold}%)', 'warning')
            elif metric == 'db_connections' and value > threshold:
                self.send_alert(f'High database connections: {value} (threshold: {threshold})', 'warning')
    
    def update_system_metrics(self):
        """Update system performance metrics"""
        try:
            # Memory usage
            process = psutil.Process()
            memory_info = process.memory_info()
            self.metrics['memory_usage_mb'] = memory_info.rss / 1024 / 1024
            
            # CPU usage
            self.metrics['cpu_usage_percent'] = process.cpu_percent()
            
            # Database connections
            with connection.cursor() as cursor:
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                result = cursor.fetchone()
                if result:
                    self.metrics['db_connections'] = int(result[1])
            
            # Disk I/O
            current_io = psutil.disk_io_counters()
            if self.initial_io and current_io:
                disk_read_mb = (current_io.read_bytes - self.initial_io.read_bytes) / 1024 / 1024
                disk_write_mb = (current_io.write_bytes - self.initial_io.write_bytes) / 1024 / 1024
                self.metrics['disk_io_mb'] = disk_read_mb + disk_write_mb
            
            # Network I/O
            current_net_io = psutil.net_io_counters()
            if self.initial_net_io and current_net_io:
                net_sent_mb = (current_net_io.bytes_sent - self.initial_net_io.bytes_sent) / 1024 / 1024
                net_recv_mb = (current_net_io.bytes_recv - self.initial_net_io.bytes_recv) / 1024 / 1024
                self.metrics['network_io_mb'] = net_sent_mb + net_recv_mb
            
            # Cache hit rate (if available)
            self.metrics['cache_hit_rate'] = self._get_cache_hit_rate()
            
        except Exception as e:
            logger.warning(f"Error updating system metrics: {e}")
    
    def _get_cache_hit_rate(self) -> float:
        """Get cache hit rate from Redis or Django cache"""
        try:
            # This is a simplified version - in production, you'd want
            # to get actual cache statistics from Redis
            cache_stats_key = f"import_cache_stats_{self.session_id}"
            stats = cache.get(cache_stats_key, {})
            
            hits = stats.get('hits', 0)
            misses = stats.get('misses', 0)
            total = hits + misses
            
            if total > 0:
                return (hits / total) * 100
            return 0.0
            
        except Exception as e:
            logger.debug(f"Error getting cache hit rate: {e}")
            return 0.0
    
    def send_alert(self, message: str, severity: str = 'warning'):
        """
        Send alert to monitoring system.
        
        Args:
            message: Alert message
            severity: Alert severity (info, warning, error, critical)
        """
        alert = {
            'timestamp': datetime.now().isoformat(),
            'message': message,
            'severity': severity,
            'session_id': self.session_id
        }
        
        self.metrics['alerts'].append(alert)
        
        # Log to Django
        log_method = {
            'info': logger.info,
            'warning': logger.warning,
            'error': logger.error,
            'critical': logger.critical
        }.get(severity, logger.warning)
        
        log_method(f'Import Alert [{self.session_id}]: {message}')
        
        # Send to external monitoring (if configured)
        self._send_external_alert(alert)
    
    def _send_external_alert(self, alert: Dict[str, Any]):
        """Send alert to external monitoring system"""
        try:
            if hasattr(settings, 'MONITORING_WEBHOOK') and settings.MONITORING_WEBHOOK:
                import requests
                
                requests.post(
                    settings.MONITORING_WEBHOOK,
                    json=alert,
                    timeout=5,
                    headers={'Content-Type': 'application/json'}
                )
        except Exception as e:
            logger.debug(f"Failed to send external alert: {e}")
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        elapsed_time = (datetime.now() - self.start_time).total_seconds()
        
        return {
            **self.metrics,
            'elapsed_time_seconds': elapsed_time,
            'formatted_elapsed_time': self._format_duration(elapsed_time),
            'alert_count': len(self.metrics['alerts']),
            'performance_grade': self._calculate_performance_grade()
        }
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
    
    def _calculate_performance_grade(self) -> str:
        """Calculate overall performance grade"""
        score = 100
        
        # Deduct points for poor metrics
        if self.metrics['memory_usage_mb'] > 200:
            score -= 10
        if self.metrics['processing_rate'] < 50:
            score -= 15
        if self.metrics['error_rate'] > 0.05:
            score -= 20
        if self.metrics['cpu_usage_percent'] > 60:
            score -= 10
        if len(self.metrics['alerts']) > 5:
            score -= 10
        
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
    
    def save_metrics(self):
        """Save metrics to cache for later analysis"""
        try:
            cache_key = f"import_metrics_{self.session_id}"
            cache.set(cache_key, self.metrics, 3600)  # Cache for 1 hour
        except Exception as e:
            logger.warning(f"Failed to save metrics: {e}")


class BulkOperationMonitor:
    """
    Monitor bulk operations across the system.
    Provides system-wide visibility into import performance.
    """
    
    @staticmethod
    def get_active_operations() -> List[Dict[str, Any]]:
        """Get all currently running bulk operations"""
        try:
            operations = BulkOperation.objects.filter(
                status__in=['pending', 'running']
            ).select_related('user').order_by('-start_time')
            
            result = []
            for op in operations:
                # Get latest progress
                latest_progress = BulkOperationProgress.objects.filter(
                    operation=op
                ).order_by('-created_at').first()
                
                operation_data = {
                    'id': op.id,
                    'operation_type': op.operation_type,
                    'status': op.status,
                    'user': op.user.username,
                    'description': op.description,
                    'start_time': op.start_time.isoformat() if op.start_time else None,
                    'total_items': op.total_items,
                    'processed_items': op.processed_items,
                    'processing_rate': op.processing_rate,
                    'percentage': 0
                }
                
                if op.total_items > 0:
                    operation_data['percentage'] = min(100, (op.processed_items / op.total_items) * 100)
                
                if latest_progress:
                    operation_data['last_update'] = latest_progress.created_at.isoformat()
                    operation_data['error_count'] = latest_progress.error_count
                
                result.append(operation_data)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting active operations: {e}")
            return []
    
    @staticmethod
    def get_system_performance_stats() -> Dict[str, Any]:
        """Get system-wide performance statistics"""
        try:
            # Database performance
            with connection.cursor() as cursor:
                cursor.execute("SHOW STATUS LIKE 'Threads_connected'")
                db_connections = cursor.fetchone()[1] if cursor.fetchone() else 0
                
                cursor.execute("SHOW STATUS LIKE 'Queries'")
                total_queries = cursor.fetchone()[1] if cursor.fetchone() else 0
            
            # System performance
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Recent operations performance
            recent_operations = BulkOperation.objects.filter(
                start_time__gte=timezone.now() - timedelta(hours=24),
                status='completed'
            )
            
            avg_processing_rate = 0
            if recent_operations.exists():
                avg_processing_rate = recent_operations.aggregate(
                    avg_rate=models.Avg('processing_rate')
                )['avg_rate'] or 0
            
            return {
                'timestamp': datetime.now().isoformat(),
                'database': {
                    'connections': int(db_connections),
                    'total_queries': int(total_queries)
                },
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_gb': memory.used / 1024 / 1024 / 1024,
                    'disk_percent': (disk.used / disk.total) * 100,
                    'disk_free_gb': disk.free / 1024 / 1024 / 1024
                },
                'operations': {
                    'active_count': BulkOperation.objects.filter(status__in=['pending', 'running']).count(),
                    'completed_today': recent_operations.count(),
                    'avg_processing_rate': avg_processing_rate
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting system performance stats: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def cleanup_old_metrics():
        """Clean up old metrics data"""
        try:
            # Clean up old bulk operation progress records
            cutoff_date = timezone.now() - timedelta(days=7)
            deleted_count = BulkOperationProgress.objects.filter(
                created_at__lt=cutoff_date
            ).delete()[0]
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old progress records")
            
            # Clean up old cache entries
            # This would need to be implemented based on your cache backend
            
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")


class PerformanceAnalyzer:
    """
    Analyze import performance and provide optimization recommendations.
    """
    
    @staticmethod
    def analyze_operation(operation_id: int) -> Dict[str, Any]:
        """Analyze a completed bulk operation and provide insights"""
        try:
            operation = BulkOperation.objects.get(id=operation_id)
            progress_records = BulkOperationProgress.objects.filter(
                operation=operation
            ).order_by('created_at')
            
            if not progress_records.exists():
                return {'error': 'No progress data available'}
            
            # Calculate performance metrics
            total_time = operation.duration or 0
            total_items = operation.processed_items or 0
            processing_rate = total_items / total_time if total_time > 0 else 0
            
            # Analyze batch performance
            batch_times = []
            batch_sizes = []
            error_rates = []
            
            for i, record in enumerate(progress_records):
                if i > 0:
                    prev_record = progress_records[i-1]
                    batch_time = (record.created_at - prev_record.created_at).total_seconds()
                    batch_size = record.items_processed - prev_record.items_processed
                    
                    if batch_time > 0 and batch_size > 0:
                        batch_times.append(batch_time)
                        batch_sizes.append(batch_size)
                        
                        error_rate = (record.error_count / batch_size) * 100 if batch_size > 0 else 0
                        error_rates.append(error_rate)
            
            # Generate recommendations
            recommendations = []
            
            if processing_rate < 20:
                recommendations.append("Consider increasing batch size for better performance")
            
            if batch_times and max(batch_times) > 30:
                recommendations.append("Some batches took too long - consider optimizing database queries")
            
            if error_rates and max(error_rates) > 5:
                recommendations.append("High error rate detected - improve data validation")
            
            avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
            avg_batch_size = sum(batch_sizes) / len(batch_sizes) if batch_sizes else 0
            
            return {
                'operation_id': operation_id,
                'performance_metrics': {
                    'total_time_seconds': total_time,
                    'total_items': total_items,
                    'processing_rate': processing_rate,
                    'avg_batch_time': avg_batch_time,
                    'avg_batch_size': avg_batch_size,
                    'error_rate': operation.error_count / total_items * 100 if total_items > 0 else 0
                },
                'batch_analysis': {
                    'batch_count': len(batch_times),
                    'min_batch_time': min(batch_times) if batch_times else 0,
                    'max_batch_time': max(batch_times) if batch_times else 0,
                    'avg_error_rate': sum(error_rates) / len(error_rates) if error_rates else 0
                },
                'recommendations': recommendations,
                'performance_grade': PerformanceAnalyzer._calculate_grade(processing_rate, total_time, total_items)
            }
            
        except BulkOperation.DoesNotExist:
            return {'error': 'Operation not found'}
        except Exception as e:
            logger.error(f"Error analyzing operation: {e}")
            return {'error': str(e)}
    
    @staticmethod
    def _calculate_grade(processing_rate: float, total_time: float, total_items: int) -> str:
        """Calculate performance grade for an operation"""
        score = 100
        
        if processing_rate < 10:
            score -= 30
        elif processing_rate < 25:
            score -= 15
        elif processing_rate < 50:
            score -= 5
        
        if total_time > 1800:  # > 30 minutes
            score -= 20
        elif total_time > 900:  # > 15 minutes
            score -= 10
        
        if total_items > 50000 and processing_rate < 100:
            score -= 15
        
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'
