from django.conf import settings

def debug_context(request):
    """
    Add debug variable to all template contexts for CSS loading.
    This fixes the issue where dashboard.min.css is loaded but dashboard.css
    is only loaded conditionally based on the debug variable.
    """
    return {
        'debug': settings.DEBUG,
    }
