"""
Middleware for tracking user sessions to enable fast session invalidation.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from accounts.services.session_manager import OptimizedSessionManager

logger = logging.getLogger(__name__)


class SessionTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track user sessions for efficient invalidation.
    Stores session keys in cache for fast lookup during password changes.
    """
    
    def process_request(self, request):
        """Track user session when request is processed."""
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                # Track this session for the user
                session_key = request.session.session_key
                if session_key:
                    OptimizedSessionManager.track_user_session(
                        request.user.id, 
                        session_key
                    )
            except Exception as e:
                logger.debug(f"Failed to track user session: {e}")
    
    def process_response(self, request, response):
        """Clean up tracking if needed."""
        return response
