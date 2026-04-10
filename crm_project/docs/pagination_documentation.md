# Duplicate Detection Pagination Documentation

## Overview

This document describes the pagination functionality implemented for the duplicate detection system in the CRM. The pagination system has been optimized for performance and user experience, handling large datasets efficiently.

## Features

### Database-Level Pagination
- **Efficient Querying**: Uses Django ORM aggregation and pagination at the database level
- **Memory Optimization**: Only loads the current page of data into memory
- **Performance**: Handles thousands of duplicate groups efficiently

### User Experience Enhancements
- **Configurable Page Sizes**: Users can choose from 5, 10, 20, 25, 50, 100, 200, or 500 items per page
- **Persistent Preferences**: Page size preference is saved in localStorage
- **Smart Navigation**: Pagination controls with ellipsis for large page counts
- **Keyboard Shortcuts**: Ctrl/Cmd + Arrow keys for page navigation
- **State Preservation**: Expanded duplicate groups are preserved across page navigation

### Role-Based Access
- **Owner**: Can see all duplicate groups in the company
- **Manager**: Can see duplicate groups for their team members
- **Team Lead**: Can see duplicate groups for their agents
- **Agent**: Can only see duplicate groups for their own leads

## API Parameters

### URL Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | Integer | 1 | Current page number (1-based) |
| `page_size` | Integer | 20 | Number of items per page (5, 10, 20, 25, 50, 100, 200, 500) |
| `status` | String | 'pending' | Filter by resolution status ('pending', 'resolved', 'ignored', 'merged') |
| `type` | String | '' | Filter by duplicate type ('exact_duplicate', 'potential_duplicate') |

### Example URLs

```
# Basic pagination
/duplicates/?page=2&page_size=20

# With filters
/duplicates/?page=1&page_size=10&status=pending&type=exact_duplicate

# Team duplicates with pagination
/team-duplicates/?page=3&page_size=25

# My duplicates with large page size
/my-duplicates/?page=1&page_size=100
```

## Backend Implementation

### Views

#### `leads_duplicates`
Main duplicate leads list view with pagination support.

**Parameters:**
- `page`: Current page number
- `page_size`: Items per page
- `status`: Resolution status filter
- `type`: Duplicate type filter

**Returns:**
- Paginated duplicate groups
- Statistics
- Pagination metadata

#### `team_duplicate_leads`
Team-specific duplicate leads with role-based pagination.

**Additional Parameters:**
- Role-based filtering based on `request.user.role`

#### `my_duplicate_leads`
User-specific duplicate leads.

**Additional Parameters:**
- Filters to show only user's assigned leads

### Service Methods

#### `find_duplicate_groups_paginated()`

**Signature:**
```python
def find_duplicate_groups_paginated(
    self, 
    status: str = None, 
    duplicate_type: str = None,
    page: int = 1, 
    page_size: int = 20, 
    user_role: str = None, 
    user=None
) -> Dict
```

**Parameters:**
- `status`: Filter by resolution status
- `duplicate_type`: Filter by duplicate type
- `page`: Page number (1-based)
- `page_size`: Items per page
- `user_role`: User role for access control
- `user`: User object for access control

**Returns:**
```python
{
    'page_obj': PaginatorPage,
    'groups': List[Dict],
    'total_count': int,
    'has_next': bool,
    'has_previous': bool,
    'num_pages': int,
    'current_page': int,
    'start_index': int,
    'end_index': int
}
```

## Frontend Implementation

### JavaScript Functions

#### `changePageSize(pageSize)`
Updates the page size and navigates to the first page.

#### `jumpToPage(pageNum)`
Navigates to a specific page number.

#### `preserveGroupExpansion()`
Saves and restores expanded duplicate group states across pagination.

#### `filterDuplicates()`
Applies filters and resets pagination to page 1.

#### `performBulkAction(action)`
Performs bulk actions while preserving pagination state.

#### Keyboard Shortcuts
- `Ctrl/Cmd + ←`: Previous page
- `Ctrl/Cmd + →`: Next page

### Session Storage

The system uses `sessionStorage` to persist:
- Expanded duplicate group IDs (`expandedDuplicateGroups`)
- Preferred page size (`preferred_page_size`)

## Performance Optimizations

### Database Level
1. **Aggregation**: Uses `values()` and `annotate()` for efficient grouping
2. **Selective Loading**: Only loads necessary fields with `only()`
3. **Related Objects**: Uses `select_related()` to reduce query count
4. **Indexing**: Optimized queries with proper database indexes

### Memory Management
1. **Page-by-Page Loading**: Only current page data in memory
2. **Efficient Data Structures**: Uses sets for ID comparisons
3. **Garbage Collection**: Proper cleanup of unused objects

### Frontend Optimization
1. **Lazy Loading**: Pagination controls load on demand
2. **Event Delegation**: Efficient event handling for large lists
3. **Debouncing**: Prevents excessive API calls

## Testing

### Test Coverage

1. **Basic Pagination**: Page navigation, page size changes
2. **Edge Cases**: Invalid pages, empty results, single page
3. **Filters**: Combined filters with pagination
4. **Role-Based Access**: Different user roles
5. **Performance**: Large datasets, response times
6. **Integration**: End-to-end user flows

### Running Tests

```bash
# Run comprehensive pagination tests
python test_pagination_fix.py

# Run Django test suite
python manage.py test tests.test_duplicate_pagination
```

## Troubleshooting

### Common Issues

#### Slow Pagination Performance
**Symptoms**: Page loads take > 2 seconds
**Solutions**:
- Check database indexes on `duplicate_group_id` and `company_id`
- Reduce page size
- Add caching for frequently accessed data

#### Inconsistent Page Counts
**Symptoms**: Page count changes between requests
**Solutions**:
- Ensure data consistency in duplicate groups
- Check for concurrent modifications
- Validate filter parameters

#### Lost Expanded Groups
**Symptoms**: Groups collapse when navigating pages
**Solutions**:
- Check sessionStorage availability
- Verify JavaScript error console
- Ensure proper group ID formatting

### Debug Mode

Enable debug mode by adding to URL:
```
/duplicates/?debug=1&page=1&page_size=20
```

This will add:
- Query execution times
- Memory usage statistics
- Pagination metadata

## Migration Guide

### From Old Pagination System

1. **Update Views**: Replace old pagination with new `find_duplicate_groups_paginated()`
2. **Update Templates**: Use new pagination template with enhanced features
3. **Update JavaScript**: Add new pagination functions
4. **Database Migration**: Ensure proper indexes exist

### Configuration

Add to settings.py (optional):
```python
# Pagination defaults
DUPLICATE_DEFAULT_PAGE_SIZE = 20
DUPLICATE_MAX_PAGE_SIZE = 500
DUPLICATE_PAGE_SIZE_CHOICES = [5, 10, 20, 25, 50, 100, 200, 500]

# Performance settings
DUPLICATE_CACHE_TIMEOUT = 300  # 5 minutes
DUPLICATE_QUERY_TIMEOUT = 2.0  # 2 seconds
```

## Future Enhancements

### Planned Features
1. **Infinite Scroll**: Alternative to traditional pagination
2. **AJAX Loading**: Dynamic content loading without page refresh
3. **Export Functionality**: Export current page or all filtered results
4. **Advanced Filtering**: Date ranges, multiple status selection
5. **Bulk Operations**: Enhanced bulk actions with pagination awareness

### Performance Improvements
1. **Caching Layer**: Redis/Memcached for frequent queries
2. **Database Optimization**: Materialized views for complex aggregations
3. **CDN Integration**: Static asset optimization
4. **Progressive Loading**: Load essential data first, then enhance

## Support

For issues or questions about the pagination system:
1. Check the troubleshooting section
2. Run the test suite to identify problems
3. Check browser console for JavaScript errors
4. Review Django logs for backend issues

## Version History

### v2.0.0 (Current)
- Complete pagination rewrite
- Database-level optimization
- Enhanced user experience
- Comprehensive testing

### v1.0.0 (Previous)
- Basic in-memory pagination
- Limited filtering support
- Performance issues with large datasets
