"""
Async tasks for accounts app using Celery.
Provides background processing for session invalidation and other operations.
"""

import logging
from django.utils import timezone
from celery import shared_task
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model
from accounts.services.session_manager import OptimizedSessionManager

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3)
def invalidate_user_sessions_task(self, user_id: int):
    """
    Async task to invalidate user sessions in the background.
    
    Args:
        user_id: User ID to invalidate sessions for
        
    Returns:
        Number of sessions invalidated
    """
    try:
        logger.info(f"Starting async session invalidation for user {user_id}")
        
        # Use the optimized session manager with a longer timeout for async processing
        session_count = OptimizedSessionManager.invalidate_user_sessions(
            user_id, 
            timeout=60  # Longer timeout for async processing
        )
        
        logger.info(f"Completed async session invalidation for user {user_id}: {session_count} sessions")
        return session_count
        
    except Exception as exc:
        logger.error(f"Async session invalidation failed for user {user_id}: {exc}")
        
        # Retry the task if it fails
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying session invalidation for user {user_id} (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (self.request.retries + 1))  # Exponential backoff
        else:
            logger.error(f"Session invalidation failed permanently for user {user_id}")
            return 0


@shared_task
def cleanup_expired_sessions_task():
    """
    Async task to clean up expired sessions.
    Runs periodically to maintain session table performance.
    """
    try:
        logger.info("Starting expired sessions cleanup")
        
        # Delete expired sessions
        deleted_count, _ = Session.objects.filter(expire_date__lt=timezone.now()).delete()
        
        logger.info(f"Cleaned up {deleted_count} expired sessions")
        return deleted_count
        
    except Exception as exc:
        logger.error(f"Session cleanup failed: {exc}")
        return 0


@shared_task(bind=True, max_retries=2)
def bulk_invalidate_sessions_task(self, user_ids: list):
    """
    Async task to invalidate sessions for multiple users.
    Useful for bulk operations like role changes or team updates.
    
    Args:
        user_ids: List of user IDs to invalidate sessions for
        
    Returns:
        Total number of sessions invalidated
    """
    try:
        logger.info(f"Starting bulk session invalidation for {len(user_ids)} users")
        
        total_sessions = 0
        failed_users = []
        
        for user_id in user_ids:
            try:
                session_count = OptimizedSessionManager.invalidate_user_sessions(user_id, timeout=30)
                total_sessions += session_count
            except Exception as e:
                logger.error(f"Failed to invalidate sessions for user {user_id}: {e}")
                failed_users.append(user_id)
        
        logger.info(f"Bulk session invalidation completed: {total_sessions} sessions, {len(failed_users)} failed")
        
        if failed_users:
            # Retry failed users
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying failed users: {failed_users}")
                raise self.retry(args=[failed_users], countdown=60 * (self.request.retries + 1))
        
        return {
            'total_sessions': total_sessions,
            'failed_users': len(failed_users),
            'success_users': len(user_ids) - len(failed_users)
        }
        
    except Exception as exc:
        logger.error(f"Bulk session invalidation failed: {exc}")
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {
            'total_sessions': 0,
            'failed_users': len(user_ids),
            'success_users': 0
        }
