"""
Database connection monitoring utility for performance tracking.
"""

import time
import logging
from django.db import connection
from django.core.cache import caches
from django.conf import settings

logger = logging.getLogger(__name__)

class DatabaseMonitor:
    """Monitor database connection performance and health."""
    
    def __init__(self):
        self.cache = caches['default']
        self.stats_key = 'db_connection_stats'
    
    def test_connection_health(self):
        """Test database connection health and latency."""
        start_time = time.time()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            latency = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Update stats
            self._update_stats(latency, True)
            return {
                'status': 'healthy',
                'latency_ms': round(latency, 2),
                'timestamp': time.time()
            }
        except Exception as e:
            self._update_stats(0, False)
            logger.error(f"Database connection health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }
    
    def _update_stats(self, latency, success):
        """Update connection statistics in cache."""
        stats = self.cache.get(self.stats_key, {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'avg_latency': 0,
            'min_latency': float('inf'),
            'max_latency': 0,
            'last_check': None
        })
        
        stats['total_checks'] += 1
        stats['last_check'] = time.time()
        
        if success:
            stats['successful_checks'] += 1
            stats['avg_latency'] = (
                (stats['avg_latency'] * (stats['successful_checks'] - 1) + latency) / 
                stats['successful_checks']
            )
            stats['min_latency'] = min(stats['min_latency'], latency)
            stats['max_latency'] = max(stats['max_latency'], latency)
        else:
            stats['failed_checks'] += 1
        
        # Cache for 5 minutes
        self.cache.set(self.stats_key, stats, 300)
    
    def get_connection_stats(self):
        """Get current connection statistics."""
        return self.cache.get(self.stats_key, {})
    
    def check_pool_status(self):
        """Check connection pool status if available."""
        try:
            # Try to get pool information if using connection pooling
            if hasattr(connection, 'connection') and connection.connection:
                pool_info = {
                    'pool_active': getattr(connection.connection, 'pool_active', 'unknown'),
                    'pool_idle': getattr(connection.connection, 'pool_idle', 'unknown'),
                    'pool_size': getattr(connection.connection, 'pool_size', 'unknown'),
                }
                return pool_info
        except Exception as e:
            logger.warning(f"Could not get pool status: {e}")
        
        return {'message': 'Pool information not available'}

# Global instance
db_monitor = DatabaseMonitor()
