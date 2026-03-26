from django import template
from urllib.parse import urlencode

register = template.Library()

@register.tag
def generate_page_numbers(parser, token):
    """
    Generate page numbers with smart ellipsis display
    Usage: {% generate_page_numbers page_obj request.GET %}
    """
    try:
        tag_name, page_obj_var, get_params = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError(
            f"{token.contents.split_contents()[0]} tag requires exactly two arguments"
        )
    
    return PageNumbersNode(page_obj_var, get_params)

class PageNumbersNode(template.Node):
    def __init__(self, page_obj_var, get_params):
        self.page_obj_var = template.Variable(page_obj_var)
        self.get_params_var = template.Variable(get_params)
    
    def render(self, context):
        try:
            page_obj = self.page_obj_var.resolve(context)
            get_params = self.get_params_var.resolve(context)
        except template.VariableDoesNotExist:
            return ''
        
        current_page = page_obj.number
        total_pages = page_obj.paginator.num_pages
        
        if total_pages <= 1:
            return ''
        
        # Build query parameters for each page
        query_dict = {}
        for key, value in get_params.items():
            if key != 'page':
                query_dict[key] = value
        
        # Generate page numbers with smart ellipsis
        page_numbers = []
        
        # Always show first page
        if current_page > 3:
            page_numbers.append(1)
            if current_page > 4:
                page_numbers.append('ellipsis')
        
        # Show pages around current page
        start_page = max(1, current_page - 2)
        end_page = min(total_pages, current_page + 2)
        
        for page_num in range(start_page, end_page + 1):
            page_numbers.append(page_num)
        
        # Always show last page
        if current_page < total_pages - 2:
            if current_page < total_pages - 3:
                page_numbers.append('ellipsis')
            page_numbers.append(total_pages)
        
        # Generate HTML
        html_parts = []
        
        for page_num in page_numbers:
            if page_num == 'ellipsis':
                html_parts.append('<span class="page-btn ellipsis">...</span>')
            else:
                query_dict['page'] = page_num
                query_string = urlencode(query_dict)
                
                css_classes = ['page-btn']
                if page_num == current_page:
                    css_classes.append('current')
                
                html_parts.append(
                    f'<a href="?{query_string}" class="{" ".join(css_classes)}">{page_num}</a>'
                )
        
        return ''.join(html_parts)

@register.simple_tag
def build_url_with_params(base_url, **kwargs):
    """
    Build URL with parameters, preserving existing ones
    """
    query_dict = {}
    
    # Add existing parameters from kwargs
    for key, value in kwargs.items():
        if value:
            query_dict[key] = value
    
    return f"{base_url}?{urlencode(query_dict)}"
