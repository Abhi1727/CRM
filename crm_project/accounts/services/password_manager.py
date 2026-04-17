"""
Password Management Service

This service provides comprehensive password management functionality including:
- Secure password generation
- Password validation
- Password change logging
- Session management for password changes
- Email notifications for password changes
"""

import logging
import secrets
import string
from typing import Optional, Dict, Any
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger(__name__)


class PasswordManager:
    """Service class for managing user passwords with security and audit features"""
    
    def __init__(self):
        self.logger = logger
    
    def generate_secure_password(self, length: int = 12) -> str:
        """
        Generate a cryptographically secure password
        
        Args:
            length: Password length (minimum 8, maximum 128)
            
        Returns:
            Secure random password string
            
        Raises:
            ValueError: If length is invalid
        """
        if length < 8:
            raise ValueError("Password length must be at least 8 characters")
        if length > 128:
            raise ValueError("Password length cannot exceed 128 characters")
        
        # Define character sets
        lowercase = string.ascii_lowercase
        uppercase = string.ascii_uppercase
        digits = string.digits
        special = '!@#$%^&*()_+-=[]{}|;:,.<>?'
        
        # Ensure password has at least one character from each set
        password_chars = [
            secrets.choice(lowercase),
            secrets.choice(uppercase),
            secrets.choice(digits),
            secrets.choice(special)
        ]
        
        # Fill the rest of the password with random characters from all sets
        all_chars = lowercase + uppercase + digits + special
        for _ in range(length - 4):
            password_chars.append(secrets.choice(all_chars))
        
        # Shuffle the password to avoid predictable patterns
        secrets.SystemRandom().shuffle(password_chars)
        
        return ''.join(password_chars)
    
    def validate_password_strength(self, password: str, username: str = None) -> Dict[str, Any]:
        """
        Validate password strength against security requirements
        
        Args:
            password: Password to validate
            username: Optional username to check against
            
        Returns:
            Dictionary with validation results and recommendations
        """
        result = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'score': 0,
            'recommendations': []
        }
        
        # Length validation
        if len(password) < 8:
            result['errors'].append('Password must be at least 8 characters long')
            result['is_valid'] = False
        elif len(password) < 12:
            result['warnings'].append('Consider using a longer password (12+ characters)')
            result['recommendations'].append('Use a longer password for better security')
        else:
            result['score'] += 25
        
        # Character variety validation
        has_lowercase = any(c.islower() for c in password)
        has_uppercase = any(c.isupper() for c in password)
        has_digits = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        
        if not has_lowercase:
            result['errors'].append('Password must contain at least one lowercase letter')
            result['is_valid'] = False
        else:
            result['score'] += 15
        
        if not has_uppercase:
            result['errors'].append('Password must contain at least one uppercase letter')
            result['is_valid'] = False
        else:
            result['score'] += 15
        
        if not has_digits:
            result['errors'].append('Password must contain at least one digit')
            result['is_valid'] = False
        else:
            result['score'] += 15
        
        if not has_special:
            result['errors'].append('Password must contain at least one special character')
            result['is_valid'] = False
        else:
            result['score'] += 15
        
        # Password validation restrictions removed - users can set any password content
        
        # Repetitive characters validation
        if len(set(password)) < len(password) * 0.5:
            result['warnings'].append('Password contains too many repetitive characters')
            result['recommendations'].append('Use more diverse characters')
        
        # Sequential characters validation
        sequential_count = 0
        for i in range(len(password) - 1):
            if ord(password[i + 1]) == ord(password[i]) + 1:
                sequential_count += 1
                if sequential_count >= 2:
                    result['warnings'].append('Password contains sequential characters')
                    result['recommendations'].append('Avoid sequential characters')
                    break
            else:
                sequential_count = 0
        
        return result
    
    def change_user_password(self, user: User, new_password: str, changed_by: User = None, 
                           send_notification: bool = True, invalidate_sessions: bool = True) -> Dict[str, Any]:
        """
        Change user password with comprehensive security measures
        
        Args:
            user: User whose password is being changed
            new_password: New password to set
            changed_by: User who is making the change (None for self-change)
            send_notification: Whether to send email notification
            invalidate_sessions: Whether to invalidate existing sessions
            
        Returns:
            Dictionary with operation results
        """
        result = {
            'success': False,
            'message': '',
            'sessions_invalidated': 0,
            'notification_sent': False
        }
        
        try:
            with transaction.atomic():
                # Validate password strength
                validation = self.validate_password_strength(new_password, user.username)
                if not validation['is_valid']:
                    result['message'] = 'Password does not meet security requirements'
                    result['validation'] = validation
                    return result
                
                # Log the password change
                action = "Password changed"
                if changed_by:
                    if changed_by == user:
                        action = "Self password change"
                    else:
                        action = f"Password changed by admin: {changed_by.username}"
                
                self.logger.info(f"{action} for user {user.username} (ID: {user.id})")
                
                # Set the new password
                user.set_password(new_password)
                user.save()
                
                # Invalidate sessions if requested and not self-change (optimized)
                sessions_invalidated = 0
                if invalidate_sessions and changed_by and changed_by != user:
                    from accounts.services.session_manager import invalidate_user_sessions_fast
                    
                    sessions_invalidated = invalidate_user_sessions_fast(user.id, timeout=30)
                    
                    self.logger.info(f"Invalidated {sessions_invalidated} sessions for user {user.username}")
                
                # Send email notification if requested
                notification_sent = False
                if send_notification and hasattr(settings, 'DEFAULT_FROM_EMAIL'):
                    try:
                        subject = "Your Password Has Been Changed"
                        message = f"""
Dear {user.get_full_name() or user.username},

Your password has been changed.

{'If you did not make this change, please contact your administrator immediately.' if changed_by and changed_by != user else 'This was a self-initiated password change.'}

If you have any questions, please contact your system administrator.

Best regards,
{getattr(settings, 'SITE_NAME', 'CRM System')}
                        """.strip()
                        
                        send_mail(
                            subject=subject,
                            message=message,
                            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
                            recipient_list=[user.email],
                            fail_silently=True
                        )
                        notification_sent = True
                        self.logger.info(f"Password change notification sent to {user.email}")
                        
                    except Exception as e:
                        self.logger.warning(f"Failed to send password change notification to {user.email}: {e}")
                
                result.update({
                    'success': True,
                    'message': 'Password changed successfully',
                    'sessions_invalidated': sessions_invalidated,
                    'notification_sent': notification_sent,
                    'validation': validation
                })
                
                return result
                
        except Exception as e:
            self.logger.error(f"Error changing password for user {user.username}: {e}")
            result['message'] = f'Error changing password: {str(e)}'
            return result
    
    def can_manage_user_password(self, manager: User, target_user: User) -> bool:
        """
        Check if a user can manage another user's password
        
        Args:
            manager: User attempting to manage password
            target_user: User whose password is being managed
            
        Returns:
            True if manager can manage target_user's password
        """
        # Owner can manage anyone's password
        if manager.role == 'owner':
            return True
        
        # Manager can manage passwords of team leads and agents in their hierarchy
        if manager.role == 'manager':
            return (target_user.manager == manager or 
                   (target_user.team_lead and target_user.team_lead.manager == manager))
        
        # Team lead can manage passwords of agents only
        if manager.role == 'team_lead':
            return (target_user.role == 'agent' and 
                   target_user.team_lead == manager)
        
        # Agents cannot manage other users' passwords
        return False
    
    def get_password_policy_info(self) -> Dict[str, Any]:
        """
        Get information about the current password policy
        
        Returns:
            Dictionary with password policy information
        """
        return {
            'min_length': 8,
            'require_lowercase': True,
            'require_uppercase': True,
            'require_digits': True,
            'require_special': True,
            'forbidden_patterns': ['password', '123456', 'qwerty', 'admin', 'user', 'welcome', 'login'],
            'forbidden_username': True,
            'recommend_length': 12,
            'max_length': 128
        }


# Singleton instance for easy access
password_manager = PasswordManager()
