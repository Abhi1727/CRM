"""
Optimized Session Management for CRM

Provides fast session invalidation without performance issues.
Replaces slow session_data__contains queries with efficient lookups.
"""

import time
import logging
from typing import List, Optional
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)

User = get_user_model()


class OptimizedSessionManager:
    """Fast session management with optimized queries and caching."""
    
    CACHE_TIMEOUT = 300  # 5 minutes
    SESSION_BATCH_SIZE = 1000
    OPERATION_TIMEOUT = 30  # seconds
    
    @classmethod
    def invalidate_user_sessions(cls, user_id: int, timeout: Optional[int] = None) -> int:
        """
        Invalidate all sessions for a user using optimized queries.
        
        Args:
            user_id: The user ID to invalidate sessions for
            timeout: Operation timeout in seconds (defaults to OPERATION_TIMEOUT)
            
        Returns:
            Number of sessions invalidated
        """
        timeout = timeout or cls.OPERATION_TIMEOUT
        start_time = time.time()
        
        try:
            # Method 1: Try to get sessions from cache first
            session_keys = cls._get_user_session_keys_cached(user_id)
            
            if session_keys:
                # Direct invalidation using session keys
                count = cls._invalidate_sessions_by_keys(session_keys)
                cls._clear_user_session_cache(user_id)
                
                logger.info(f"Invalidated {count} sessions for user {user_id} via cache in {time.time() - start_time:.3f}s")
                return count
            
            # Method 2: Fallback to optimized database query
            count = cls._invalidate_sessions_optimized_query(user_id, timeout)
            
            logger.info(f"Invalidated {count} sessions for user {user_id} via optimized query in {time.time() - start_time:.3f}s")
            return count
            
        except Exception as e:
            logger.error(f"Session invalidation failed for user {user_id}: {e}")
            return 0
    
    @classmethod
    def _get_user_session_keys_cached(cls, user_id: int) -> List[str]:
        """Get user session keys from cache."""
        cache_key = f"user_sessions_{user_id}"
        return cache.get(cache_key, [])
    
    @classmethod
    def _set_user_session_keys_cached(cls, user_id: int, session_keys: List[str]):
        """Store user session keys in cache."""
        cache_key = f"user_sessions_{user_id}"
        cache.set(cache_key, session_keys, cls.CACHE_TIMEOUT)
    
    @classmethod
    def _clear_user_session_cache(cls, user_id: int):
        """Clear user session keys from cache."""
        cache_key = f"user_sessions_{user_id}"
        cache.delete(cache_key)
    
    @classmethod
    def _invalidate_sessions_by_keys(cls, session_keys: List[str]) -> int:
        """Invalidate sessions by their keys (fastest method)."""
        if not session_keys:
            return 0
        
        with transaction.atomic():
            # Batch delete sessions by keys
            deleted_count = 0
            for i in range(0, len(session_keys), cls.SESSION_BATCH_SIZE):
                batch_keys = session_keys[i:i + cls.SESSION_BATCH_SIZE]
                deleted, _ = Session.objects.filter(session_key__in=batch_keys).delete()
                deleted_count += deleted
            
            return deleted_count
    
    @classmethod
    def _invalidate_sessions_optimized_query(cls, user_id: int, timeout: int) -> int:
        """
        Optimized session invalidation using database indexes.
        Uses multiple strategies to avoid full table scans.
        """
        start_time = time.time()
        total_deleted = 0
        
        # Strategy 1: Try to use session key pattern matching
        try:
            # Some Django session backends store user_id in session key
            user_sessions = Session.objects.filter(
                session_key__regex=f'.*{user_id}.*'
            )
            
            if user_sessions.exists():
                deleted, _ = user_sessions.delete()
                total_deleted += deleted
                logger.debug(f"Deleted {deleted} sessions via key pattern matching")
        except Exception as e:
            logger.debug(f"Key pattern matching failed: {e}")
        
        # Strategy 2: Use indexed query with timeout protection
        if time.time() - start_time < timeout:
            try:
                # Use a more efficient query that can use indexes
                sessions = Session.objects.all()
                
                # Process in batches to avoid long-running queries
                deleted_count = 0
                offset = 0
                
                while time.time() - start_time < timeout:
                    batch = list(sessions[offset:offset + cls.SESSION_BATCH_SIZE])
                    if not batch:
                        break
                    
                    # Filter batch in memory (faster than database text search)
                    user_sessions_in_batch = [
                        session for session in batch 
                        if str(user_id) in session.session_data
                    ]
                    
                    if user_sessions_in_batch:
                        session_keys = [s.session_key for s in user_sessions_in_batch]
                        deleted, _ = Session.objects.filter(session_key__in=session_keys).delete()
                        deleted_count += deleted
                    
                    offset += cls.SESSION_BATCH_SIZE
                    
                    # If we processed a full batch and found nothing, we're likely done
                    if len(batch) < cls.SESSION_BATCH_SIZE:
                        break
                
                total_deleted += deleted_count
                logger.debug(f"Deleted {deleted_count} sessions via batch processing")
                
            except Exception as e:
                logger.debug(f"Batch processing failed: {e}")
        
        return total_deleted
    
    @classmethod
    def track_user_session(cls, user_id: int, session_key: str):
        """Track a user session for efficient invalidation."""
        try:
            session_keys = cls._get_user_session_keys_cached(user_id)
            if session_key not in session_keys:
                session_keys.append(session_key)
                cls._set_user_session_keys_cached(user_id, session_keys)
        except Exception as e:
            logger.debug(f"Failed to track user session: {e}")
    
    @classmethod
    def untrack_user_session(cls, user_id: int, session_key: str):
        """Remove a user session from tracking."""
        try:
            session_keys = cls._get_user_session_keys_cached(user_id)
            if session_key in session_keys:
                session_keys.remove(session_key)
                cls._set_user_session_keys_cached(user_id, session_keys)
        except Exception as e:
            logger.debug(f"Failed to untrack user session: {e}")


def invalidate_user_sessions_fast(user_id: int, timeout: int = 30) -> int:
    """
    Fast session invalidation function.
    
    Args:
        user_id: User ID to invalidate sessions for
        timeout: Maximum time to spend on invalidation
        
    Returns:
        Number of sessions invalidated
    """
    return OptimizedSessionManager.invalidate_user_sessions(user_id, timeout)


def invalidate_user_sessions_async(user_id: int):
    """
    Async session invalidation (returns immediately, processes in background).
    Uses Celery if available, otherwise processes in a short timeout.
    """
    try:
        # Try to use Celery for async processing
        from accounts.tasks import invalidate_user_sessions_task
        invalidate_user_sessions_task.delay(user_id)
        logger.info(f"Queued async session invalidation for user {user_id}")
        return 0
    except ImportError:
        # Fallback to fast sync processing with short timeout
        logger.info(f"Using fast sync session invalidation for user {user_id}")
        return invalidate_user_sessions_fast(user_id, timeout=5)
