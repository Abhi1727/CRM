"""
Custom caching utilities for CRM performance optimization.
Provides multi-level caching with smart invalidation strategies.
"""

from django.core.cache import cache
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers, vary_on_cookie
from functools import wraps
import hashlib
import json
import logging
from typing import Any, Optional, Dict, Callable

logger = logging.getLogger(__name__)


class CacheManager:
    """Centralized cache management with smart invalidation"""
    
    CACHE_TIMEOUTS = {
        'user_hierarchy': 900,      # 15 minutes
        'dashboard_stats': 600,     # 10 minutes
        'lead_filters': 300,         # 5 minutes
        'query_results': 900,        # 15 minutes
        'template_fragments': 1800,  # 30 minutes
        'user_permissions': 600,     # 10 minutes
    }
    
    @classmethod
    def get_cache_key(cls, prefix: str, *args, **kwargs) -> str:
        """Generate consistent cache key with parameters"""
        def serialize_value(value):
            """Convert non-serializable objects to serializable representations"""
            if hasattr(value, '__dict__'):
                # For objects with attributes, use class name and id
                if hasattr(value, 'id'):
                    return f"{value.__class__.__name__}_{value.id}"
                else:
                    return f"{value.__class__.__name__}_{hash(str(value))}"
            elif hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
                # For iterables (except strings), convert to list of serializable items
                try:
                    return [serialize_value(item) for item in value]
                except:
                    return str(value)
            else:
                # For primitive types, return as is
                try:
                    json.dumps(value)  # Test if serializable
                    return value
                except:
                    return str(value)
        
        # Filter and serialize args
        serializable_args = []
        for arg in args:
            serializable_args.append(serialize_value(arg))
        
        # Filter and serialize kwargs
        serializable_kwargs = {}
        for key, value in kwargs.items():
            serializable_kwargs[key] = serialize_value(value)
        
        key_data = {
            'args': serializable_args,
            'kwargs': sorted(serializable_kwargs.items())
        }
        key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
        return f"{prefix}:{key_hash}"
    
    @classmethod
    def get_cached(cls, key: str, timeout: Optional[int] = None) -> Any:
        """Get cached value with error handling"""
        try:
            return cache.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    @classmethod
    def set_cached(cls, key: str, value: Any, timeout: Optional[int] = None) -> bool:
        """Set cached value with error handling"""
        try:
            if timeout is None:
                timeout = cls.CACHE_TIMEOUTS.get('query_results', 900)
            return cache.set(key, value, timeout)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    @classmethod
    def delete_cached(cls, key: str) -> bool:
        """Delete cached value with error handling"""
        try:
            return cache.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    @classmethod
    def clear_pattern(cls, pattern: str) -> int:
        """Clear all cache keys matching pattern"""
        try:
            # This requires cache backend that supports keys() method
            if hasattr(cache, 'keys'):
                keys_to_delete = cache.keys(f"*{pattern}*")
                deleted_count = 0
                for key in keys_to_delete:
                    if cache.delete(key):
                        deleted_count += 1
                return deleted_count
            else:
                logger.warning("Cache backend doesn't support pattern clearing")
                return 0
        except Exception as e:
            logger.error(f"Cache pattern clear error for {pattern}: {e}")
            return 0
    
    @classmethod
    def invalidate_user_cache(cls, user_id: int, company_id: int):
        """Invalidate all cache entries for a specific user"""
        patterns = [
            f"accessible_users_{user_id}_{company_id}",
            f"accessible_leads_{user_id}_{company_id}",
            f"dashboard_stats_{user_id}_{company_id}",
            f"user_permissions_{user_id}",
        ]
        
        for pattern in patterns:
            cls.clear_pattern(pattern)
    
    @classmethod
    def invalidate_company_cache(cls, company_id: int):
        """Invalidate all cache entries for a company"""
        patterns = [
            f"company_{company_id}_",
            f"dashboard_stats_*_{company_id}",
        ]
        
        for pattern in patterns:
            cls.clear_pattern(pattern)


def cache_result(timeout: int = 900, key_prefix: str = None, vary_on: list = None):
    """
    Decorator for caching function results with smart invalidation
    
    Args:
        timeout: Cache timeout in seconds
        key_prefix: Prefix for cache key
        vary_on: List of parameter names to vary cache on
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            prefix = key_prefix or f"{func.__module__}.{func.__name__}"
            
            # Filter kwargs based on vary_on parameter
            if vary_on:
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in vary_on}
            else:
                filtered_kwargs = kwargs
            
            cache_key = CacheManager.get_cache_key(prefix, *args, **filtered_kwargs)
            
            # Try to get cached result
            cached_result = CacheManager.get_cached(cache_key, timeout)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            CacheManager.set_cached(cache_key, result, timeout)
            
            return result
        
        # Add cache invalidation method
        wrapper.invalidate_cache = lambda *args, **kwargs: (
            CacheManager.delete_cached(
                CacheManager.get_cache_key(
                    key_prefix or f"{func.__module__}.{func.__name__}",
                    *args,
                    **(filtered_kwargs if vary_on else kwargs)
                )
            )
        )
        
        return wrapper
    return decorator


def cache_queryset(timeout: int = 900, key_prefix: str = None):
    """
    Decorator specifically for caching Django querysets
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            prefix = key_prefix or f"qs_{func.__module__}.{func.__name__}"
            cache_key = CacheManager.get_cache_key(prefix, *args, **kwargs)
            
            # Try to get cached queryset IDs
            cached_ids = CacheManager.get_cached(cache_key, timeout)
            if cached_ids is not None:
                # Reconstruct queryset from cached IDs
                from dashboard.models import Lead
                return Lead.objects.filter(id_lead__in=cached_ids)
            
            # Execute function and cache queryset IDs
            queryset = func(*args, **kwargs)
            if queryset.exists():
                ids = list(queryset.values_list('id_lead', flat=True))
                CacheManager.set_cached(cache_key, ids, timeout)
            
            return queryset
        
        wrapper.invalidate_cache = lambda *args, **kwargs: (
            CacheManager.delete_cached(
                CacheManager.get_cache_key(
                    key_prefix or f"qs_{func.__module__}.{func.__name__}",
                    *args,
                    **kwargs
                )
            )
        )
        
        return wrapper
    return decorator


class TemplateFragmentCache:
    """Enhanced template fragment caching with smart invalidation"""
    
    @staticmethod
    def get_fragment_key(template_name: str, fragment_name: str, user_id: int = None, **kwargs) -> str:
        """Generate cache key for template fragment"""
        key_data = {
            'template': template_name,
            'fragment': fragment_name,
            'user_id': user_id,
            'kwargs': sorted(kwargs.items())
        }
        key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
        return f"template_fragment:{key_hash}"
    
    @staticmethod
    def cache_fragment(key: str, content: str, timeout: int = 1800):
        """Cache template fragment content"""
        return CacheManager.set_cached(key, content, timeout)
    
    @staticmethod
    def get_cached_fragment(key: str) -> str:
        """Get cached template fragment"""
        return CacheManager.get_cached(key)
    
    @staticmethod
    def invalidate_fragment(template_name: str, fragment_name: str = None):
        """Invalidate template fragments"""
        if fragment_name:
            pattern = f"template_fragment:*{template_name}*{fragment_name}*"
        else:
            pattern = f"template_fragment:*{template_name}*"
        CacheManager.clear_pattern(pattern)


class QueryResultCache:
    """Specialized caching for database query results"""
    
    @staticmethod
    def get_query_cache_key(query_type: str, user_id: int, company_id: int, **filters) -> str:
        """Generate cache key for query results"""
        filter_data = {k: v for k, v in filters.items() if v is not None}
        key_data = {
            'type': query_type,
            'user_id': user_id,
            'company_id': company_id,
            'filters': sorted(filter_data.items())
        }
        key_hash = hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
        return f"query_result:{key_hash}"
    
    @staticmethod
    def cache_query_result(key: str, result: Any, timeout: int = 900):
        """Cache query result"""
        return CacheManager.set_cached(key, result, timeout)
    
    @staticmethod
    def get_cached_query_result(key: str) -> Any:
        """Get cached query result"""
        return CacheManager.get_cached(key)
    
    @staticmethod
    def invalidate_query_cache(query_type: str = None, user_id: int = None, company_id: int = None):
        """Invalidate query results based on parameters"""
        if query_type and user_id and company_id:
            pattern = f"query_result:*type*{query_type}*user_id*{user_id}*company_id*{company_id}*"
        elif company_id:
            pattern = f"query_result:*company_id*{company_id}*"
        elif user_id:
            pattern = f"query_result:*user_id*{user_id}*"
        else:
            pattern = "query_result:*"
        CacheManager.clear_pattern(pattern)


# Performance monitoring for cache operations
class CacheMetrics:
    """Track cache performance metrics"""
    
    @staticmethod
    def log_cache_hit(key: str, hit: bool):
        """Log cache hit/miss for monitoring"""
        status = "HIT" if hit else "MISS"
        logger.debug(f"CACHE {status}: {key}")
    
    @staticmethod
    def log_cache_operation(operation: str, key: str, success: bool):
        """Log cache operations for monitoring"""
        status = "SUCCESS" if success else "ERROR"
        logger.info(f"CACHE {operation} {status}: {key}")


# Decorators for views
def cached_view(timeout: int = 600, vary_on_headers: list = None, vary_on_cookie: bool = False):
    """
    Combined view caching with varying parameters
    """
    def decorator(view_func: Callable) -> Callable:
        decorators = [cache_page(timeout)]
        
        if vary_on_headers:
            decorators.append(vary_on_headers(*vary_on_headers))
        
        if vary_on_cookie:
            decorators.append(vary_on_cookie)
        
        # Apply decorators in reverse order
        for decorator in reversed(decorators):
            view_func = decorator(view_func)
        
        return view_func
    return decorator
