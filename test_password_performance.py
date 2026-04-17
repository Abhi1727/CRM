#!/usr/bin/env python
"""
Test script to verify password change performance improvements.
Compares old vs new session invalidation methods.
"""

import os
import sys
import django
import time
import logging

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.crm.settings')
sys.path.append('C:/Users/DELL/OneDrive/Desktop/CRM')
sys.path.append('C:/Users/DELL/OneDrive/Desktop/CRM/crm_project')
django.setup()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import Django models after setup
from django.contrib.sessions.models import Session
from django.contrib.auth import get_user_model

User = get_user_model()


def test_old_session_invalidation(user_id: int) -> int:
    """Test the old slow session invalidation method."""
    logger.info(f"Testing old session invalidation for user {user_id}")
    
    start_time = time.time()
    
    # Old method - slow session_data__contains query
    sessions = Session.objects.filter(session_data__contains=str(user_id))
    session_count = sessions.count()
    sessions.delete()
    
    duration = time.time() - start_time
    
    logger.info(f"Old method: {session_count} sessions invalidated in {duration:.3f} seconds")
    return session_count, duration


def test_new_session_invalidation(user_id: int) -> int:
    """Test the new optimized session invalidation method."""
    from accounts.services.session_manager import invalidate_user_sessions_fast
    
    logger.info(f"Testing new session invalidation for user {user_id}")
    
    start_time = time.time()
    session_count = invalidate_user_sessions_fast(user_id, timeout=30)
    duration = time.time() - start_time
    
    logger.info(f"New method: {session_count} sessions invalidated in {duration:.3f} seconds")
    return session_count, duration


def test_async_session_invalidation(user_id: int) -> int:
    """Test the async session invalidation method."""
    from accounts.services.session_manager import invalidate_user_sessions_async
    
    logger.info(f"Testing async session invalidation for user {user_id}")
    
    start_time = time.time()
    session_count = invalidate_user_sessions_async(user_id)
    duration = time.time() - start_time
    
    logger.info(f"Async method: {session_count} sessions invalidated in {duration:.3f} seconds")
    return session_count, duration


def create_test_sessions(user_id: int, count: int = 100):
    """Create test sessions for performance testing."""
    logger.info(f"Creating {count} test sessions for user {user_id}")
    
    from django.contrib.sessions.backends.db import SessionStore
    
    created_count = 0
    for i in range(count):
        try:
            session = SessionStore()
            session['user_id'] = user_id
            session['test_data'] = f'test_session_{i}'
            session.create()
            created_count += 1
        except Exception as e:
            logger.error(f"Failed to create test session {i}: {e}")
    
    logger.info(f"Created {created_count} test sessions")
    return created_count


def run_performance_test():
    """Run comprehensive performance test."""
    logger.info("Starting password change performance test")
    
    # Get a test user
    try:
        user = User.objects.first()
        if not user:
            logger.error("No users found in database")
            return
        
        user_id = user.id
        logger.info(f"Using test user: {user.username} (ID: {user_id})")
    except Exception as e:
        logger.error(f"Failed to get test user: {e}")
        return
    
    # Clean up any existing sessions
    logger.info("Cleaning up existing sessions...")
    Session.objects.all().delete()
    
    # Create test sessions
    test_session_count = 50
    created_sessions = create_test_sessions(user_id, test_session_count)
    
    if created_sessions == 0:
        logger.error("No test sessions created, cannot proceed")
        return
    
    # Test old method
    logger.info("\n" + "="*50)
    logger.info("TESTING OLD METHOD")
    logger.info("="*50)
    
    old_count, old_duration = test_old_session_invalidation(user_id)
    
    # Create new test sessions for new method test
    create_test_sessions(user_id, test_session_count)
    
    # Test new method
    logger.info("\n" + "="*50)
    logger.info("TESTING NEW METHOD")
    logger.info("="*50)
    
    new_count, new_duration = test_new_session_invalidation(user_id)
    
    # Create new test sessions for async method test
    create_test_sessions(user_id, test_session_count)
    
    # Test async method
    logger.info("\n" + "="*50)
    logger.info("TESTING ASYNC METHOD")
    logger.info("="*50)
    
    async_count, async_duration = test_async_session_invalidation(user_id)
    
    # Performance comparison
    logger.info("\n" + "="*50)
    logger.info("PERFORMANCE COMPARISON")
    logger.info("="*50)
    
    logger.info(f"Old method:   {old_duration:.3f}s for {old_count} sessions")
    logger.info(f"New method:   {new_duration:.3f}s for {new_count} sessions")
    logger.info(f"Async method: {async_duration:.3f}s for {async_count} sessions")
    
    if old_duration > 0:
        new_improvement = ((old_duration - new_duration) / old_duration) * 100
        async_improvement = ((old_duration - async_duration) / old_duration) * 100
        
        logger.info(f"New method improvement: {new_improvement:.1f}% faster")
        logger.info(f"Async method improvement: {async_improvement:.1f}% faster")
    
    # Test targets from plan
    logger.info("\n" + "="*50)
    logger.info("PERFORMANCE TARGETS")
    logger.info("="*50)
    
    target_time = 2.0  # 2 seconds target from plan
    
    logger.info(f"Target time: < {target_time}s")
    logger.info(f"Old method:   {'PASS' if old_duration < target_time else 'FAIL'} ({old_duration:.3f}s)")
    logger.info(f"New method:   {'PASS' if new_duration < target_time else 'FAIL'} ({new_duration:.3f}s)")
    logger.info(f"Async method: {'PASS' if async_duration < target_time else 'FAIL'} ({async_duration:.3f}s)")
    
    logger.info("\nPerformance test completed!")


if __name__ == '__main__':
    run_performance_test()
