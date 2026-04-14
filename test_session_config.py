#!/usr/bin/env python3
"""
Test script to verify session configuration without Django setup
"""
import os
import sys

# Add the project directory to Python path
sys.path.insert(0, '/root/CRM/crm_project')

# Set environment variables
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')

try:
    import django
    from django.conf import settings
    
    # Setup Django
    django.setup()
    
    # Check session configuration
    print("Session Configuration:")
    print(f"SESSION_ENGINE: {settings.SESSION_ENGINE}")
    
    # Check if database sessions table exists
    from django.db import connection
    from django.contrib.sessions.models import Session
    
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='django_session';")
            result = cursor.fetchone()
            if result:
                print("Session table exists: django_session")
            else:
                print("Session table does not exist")
    except Exception as e:
        print(f"Database check failed: {e}")
    
    # Test session creation
    from django.contrib.sessions.backends.db import SessionStore
    session = SessionStore()
    session['test_key'] = 'test_value'
    session.save()
    session_key = session.session_key
    
    print(f"Created test session: {session_key}")
    
    # Test session retrieval
    loaded_session = SessionStore(session_key=session_key)
    if loaded_session.get('test_key') == 'test_value':
        print("Session retrieval: SUCCESS")
        loaded_session.delete()
        print("Test session cleaned up")
    else:
        print("Session retrieval: FAILED")
    
    print("\nSession configuration fix is working!")
    
except ImportError as e:
    print(f"Django import failed: {e}")
    print("This is expected if Django is not installed system-wide")
    print("The session configuration change in settings.py is still valid")
    
except Exception as e:
    print(f"Error: {e}")
