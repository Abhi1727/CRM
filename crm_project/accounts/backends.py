from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
import logging

User = get_user_model()
logger = logging.getLogger(__name__)

class EmailOrUsernameBackend(BaseBackend):
    """
    Custom authentication backend that allows users to login with either username or email.
    
    This backend maintains backward compatibility with the existing username-based authentication
    while adding email-based authentication support.
    """
    
    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user using either username or email.
        
        Args:
            request: The HTTP request object
            username: Can be either username or email address
            password: User's password
            **kwargs: Additional keyword arguments
            
        Returns:
            User object if authentication successful, None otherwise
        """
        if username is None or password is None:
            return None
            
        # Try to find user by username first (for backward compatibility)
        try:
            user = User.objects.get(username=username)
            logger.debug(f"Found user by username: {username}")
        except User.DoesNotExist:
            # If not found by username, try email
            try:
                user = User.objects.get(email__iexact=username)  # Case-insensitive email matching
                logger.debug(f"Found user by email: {username}")
            except User.DoesNotExist:
                logger.debug(f"No user found with username or email: {username}")
                return None
            except User.MultipleObjectsReturned:
                # This should not happen with unique email constraint, but handle gracefully
                logger.error(f"Multiple users found with email: {username}")
                return None
        
        # Verify the password
        if user.check_password(password):
            logger.debug(f"Authentication successful for: {user.username}")
            return user
        else:
            logger.debug(f"Password verification failed for: {user.username}")
            return None
    
    def get_user(self, user_id):
        """
        Retrieve user by primary key.
        
        Args:
            user_id: The user's primary key
            
        Returns:
            User object if found, None otherwise
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
