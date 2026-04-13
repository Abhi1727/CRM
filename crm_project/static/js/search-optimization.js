/**
 * Search optimization utilities for CRM
 * Implements debouncing, throttling, and efficient search handling
 */

class CRMSearchOptimizer {
    constructor() {
        this.searchTimeout = null;
        this.searchDelay = 300; // 300ms debounce delay
        this.minSearchLength = 2;
        this.searchCache = new Map();
        this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
        this.init();
    }

    init() {
        this.setupSearchListeners();
        this.setupKeyboardShortcuts();
    }

    setupSearchListeners() {
        // Find all search inputs
        const searchInputs = document.querySelectorAll('input[type="search"], input[name="search"], .search-input');
        
        searchInputs.forEach(input => {
            // Add instant search for leads list
            if (input.id === 'search-input' && this.isLeadsPage()) {
                input.addEventListener('input', (e) => {
                    this.instantSearchLeads(e.target);
                });
            } else {
                // Add debounced search for other inputs
                input.addEventListener('input', (e) => {
                    this.debounceSearch(e.target);
                });
            }

            // Add loading indicator
            input.addEventListener('focus', (e) => {
                this.showSearchLoading(e.target);
            });

            // Clear cache on Escape
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    e.target.value = '';
                    this.clearSearchResults(e.target);
                    if (this.isLeadsPage()) {
                        this.resetLeadsDisplay();
                    }
                }
            });
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K for quick search
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                const searchInput = document.querySelector('input[type="search"], input[name="search"], .search-input');
                if (searchInput) {
                    searchInput.focus();
                    searchInput.select();
                }
            }
        });
    }

    debounceSearch(input) {
        const query = input.value.trim();
        
        // Clear previous timeout
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        // Clear results if query is too short
        if (query.length < this.minSearchLength) {
            this.clearSearchResults(input);
            return;
        }

        // Show loading state
        this.showSearchLoading(input);

        // Debounce the search
        this.searchTimeout = setTimeout(() => {
            this.performSearch(input, query);
        }, this.searchDelay);
    }

    async performSearch(input, query) {
        try {
            // Check cache first
            const cacheKey = this.getCacheKey(query, input.dataset.searchContext || 'default');
            const cachedResult = this.searchCache.get(cacheKey);
            
            if (cachedResult && (Date.now() - cachedResult.timestamp) < this.cacheTimeout) {
                this.displaySearchResults(input, cachedResult.data);
                return;
            }

            // Perform actual search
            const searchUrl = this.getSearchUrl(input, query);
            const response = await fetch(searchUrl, {
                method: 'GET',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`Search failed: ${response.status}`);
            }

            const data = await response.json();
            
            // Cache the result
            this.searchCache.set(cacheKey, {
                data: data,
                timestamp: Date.now()
            });

            // Display results
            this.displaySearchResults(input, data);

        } catch (error) {
            console.error('Search error:', error);
            this.showSearchError(input, error.message);
        } finally {
            this.hideSearchLoading(input);
        }
    }

    getSearchUrl(input, query) {
        const form = input.closest('form');
        const baseUrl = form ? form.action : window.location.pathname;
        const params = new URLSearchParams();
        
        params.set('search', query);
        params.set('ajax', '1');
        
        // Add other form fields
        if (form) {
            const formData = new FormData(form);
            for (let [key, value] of formData.entries()) {
                if (key !== 'search' && value) {
                    params.set(key, value);
                }
            }
        }

        return `${baseUrl}?${params.toString()}`;
    }

    getCacheKey(query, context) {
        return `${context}:${query.toLowerCase()}`;
    }

    displaySearchResults(input, data) {
        const resultsContainer = this.getResultsContainer(input);
        
        if (!resultsContainer) {
            // If no results container, trigger page reload
            this.updatePageWithResults(data);
            return;
        }

        // Clear previous results
        resultsContainer.innerHTML = '';

        if (data.results && data.results.length > 0) {
            // Render results
            const resultsHtml = data.results.map(item => this.renderSearchResult(item)).join('');
            resultsContainer.innerHTML = resultsHtml;
            resultsContainer.style.display = 'block';
            
            // Add result click handlers
            resultsContainer.querySelectorAll('.search-result-item').forEach(item => {
                item.addEventListener('click', () => {
                    this.handleResultClick(item.dataset.url);
                });
            });
        } else {
            // Show no results message
            resultsContainer.innerHTML = `
                <div class="search-no-results">
                    <i class="fas fa-search"></i>
                    <p>No results found for "${input.value}"</p>
                </div>
            `;
            resultsContainer.style.display = 'block';
        }
    }

    renderSearchResult(item) {
        return `
            <div class="search-result-item" data-url="${item.url}">
                <div class="search-result-icon">
                    <i class="fas ${item.icon || 'fa-file'}"></i>
                </div>
                <div class="search-result-content">
                    <div class="search-result-title">${item.title}</div>
                    <div class="search-result-description">${item.description || ''}</div>
                </div>
            </div>
        `;
    }

    getResultsContainer(input) {
        // Look for a results container near the input
        let container = input.parentNode.querySelector('.search-results');
        
        if (!container) {
            // Create one if it doesn't exist
            container = document.createElement('div');
            container.className = 'search-results';
            input.parentNode.style.position = 'relative';
            input.parentNode.appendChild(container);
        }
        
        return container;
    }

    clearSearchResults(input) {
        const container = this.getResultsContainer(input);
        if (container) {
            container.style.display = 'none';
            container.innerHTML = '';
        }
    }

    showSearchLoading(input) {
        const container = this.getResultsContainer(input);
        if (container) {
            container.innerHTML = `
                <div class="search-loading">
                    <i class="fas fa-spinner fa-spin"></i>
                    <span>Searching...</span>
                </div>
            `;
            container.style.display = 'block';
        }
        
        // Add loading class to input
        input.classList.add('search-loading');
    }

    hideSearchLoading(input) {
        input.classList.remove('search-loading');
    }

    showSearchError(input, message) {
        const container = this.getResultsContainer(input);
        if (container) {
            container.innerHTML = `
                <div class="search-error">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Search error: ${message}</span>
                </div>
            `;
            container.style.display = 'block';
        }
    }

    updatePageWithResults(data) {
        // Update page content without full reload
        if (data.html) {
            const contentContainer = document.querySelector('.main-content, .page-content, #content');
            if (contentContainer) {
                contentContainer.innerHTML = data.html;
                this.reinitializeComponents();
            }
        } else {
            // Fallback to page reload
            window.location.reload();
        }
    }

    handleResultClick(url) {
        window.location.href = url;
    }

    reinitializeComponents() {
        // Reinitialize any JavaScript components that might be needed
        if (window.crmPerformanceMonitor) {
            window.crmPerformanceMonitor.setupLazyLoading();
        }
        
        // Reinitialize search optimizer for new content
        this.setupSearchListeners();
    }

    // Utility methods
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }

    clearCache() {
        this.searchCache.clear();
    }

    instantSearchLeads(input) {
        const query = input.value.trim().toLowerCase();
        
        // Get all lead rows
        const leadRows = document.querySelectorAll('.leads-table tbody tr');
        let visibleCount = 0;
        let totalCount = 0;

        leadRows.forEach(row => {
            // Skip empty state row
            if (row.classList.contains('empty-state')) {
                return;
            }
            
            totalCount++;
            
            // Get searchable text from the row
            const searchableText = this.getSearchableText(row);
            
            if (query === '' || searchableText.includes(query)) {
                row.style.display = '';
                row.classList.remove('search-filtered');
                visibleCount++;
            } else {
                row.style.display = 'none';
                row.classList.add('search-filtered');
            }
        });

        // Update search results count
        this.updateSearchResultsCount(visibleCount, totalCount, query);
        
        // Show/hide "no results" message
        this.toggleNoResultsMessage(visibleCount, totalCount, query);
    }

    getSearchableText(row) {
        const searchableFields = [];
        
        // Get text from editable fields
        const editableFields = row.querySelectorAll('.editable-field');
        editableFields.forEach(field => {
            const text = field.textContent.trim();
            if (text && text !== '-') {
                searchableFields.push(text.toLowerCase());
            }
        });
        
        // Get text from other columns
        const cells = row.querySelectorAll('td');
        cells.forEach(cell => {
            if (!cell.classList.contains('editable-field')) {
                const text = cell.textContent.trim();
                if (text && text !== '-') {
                    searchableFields.push(text.toLowerCase());
                }
            }
        });
        
        return searchableFields.join(' ');
    }

    updateSearchResultsCount(visibleCount, totalCount, query) {
        // Update or create results count element
        let countElement = document.querySelector('.search-results-count');
        if (!countElement) {
            countElement = document.createElement('div');
            countElement.className = 'search-results-count';
            
            // Insert after the search box
            const searchBox = document.querySelector('.search-box');
            if (searchBox) {
                searchBox.parentNode.insertBefore(countElement, searchBox.nextSibling);
            }
        }

        if (query) {
            countElement.innerHTML = `
                <span class="count-highlight">${visibleCount}</span> of ${totalCount} leads match "${query}"
            `;
            countElement.style.display = 'block';
        } else {
            countElement.style.display = 'none';
        }
    }

    toggleNoResultsMessage(visibleCount, totalCount, query) {
        let noResultsElement = document.querySelector('.search-no-results-message');
        
        if (query && visibleCount === 0) {
            if (!noResultsElement) {
                noResultsElement = document.createElement('div');
                noResultsElement.className = 'search-no-results-message';
                
                // Insert after the table
                const table = document.querySelector('.leads-table');
                if (table) {
                    table.parentNode.insertBefore(noResultsElement, table.nextSibling);
                }
            }
            
            noResultsElement.innerHTML = `
                <div class="no-results-content">
                    <i class="fas fa-search"></i>
                    <h3>No leads found</h3>
                    <p>No leads match your search for "${query}"</p>
                    <button type="button" class="btn btn-outline" onclick="this.closest('.search-no-results-message').remove(); document.getElementById('search-input').value = ''; crmSearchOptimizer.resetLeadsDisplay();">
                        Clear Search
                    </button>
                </div>
            `;
            noResultsElement.style.display = 'block';
        } else {
            if (noResultsElement) {
                noResultsElement.style.display = 'none';
            }
        }
    }

    resetLeadsDisplay() {
        const leadRows = document.querySelectorAll('.leads-table tbody tr');
        leadRows.forEach(row => {
            row.style.display = '';
            row.classList.remove('search-filtered');
        });

        // Hide search results count
        const countElement = document.querySelector('.search-results-count');
        if (countElement) {
            countElement.style.display = 'none';
        }

        // Hide no results message
        const noResultsElement = document.querySelector('.search-no-results-message');
        if (noResultsElement) {
            noResultsElement.style.display = 'none';
        }
    }

    isLeadsPage() {
        // Check if we're on a leads list page
        return window.location.pathname.includes('/dashboard/leads') || 
               document.querySelector('.leads-table') !== null;
    }

    getCacheStats() {
        const now = Date.now();
        let validEntries = 0;
        let expiredEntries = 0;

        for (const [key, value] of this.searchCache.entries()) {
            if ((now - value.timestamp) < this.cacheTimeout) {
                validEntries++;
            } else {
                expiredEntries++;
            }
        }

        return {
            total: this.searchCache.size,
            valid: validEntries,
            expired: expiredEntries
        };
    }
}

// Initialize search optimizer
let crmSearchOptimizer;

document.addEventListener('DOMContentLoaded', () => {
    crmSearchOptimizer = new CRMSearchOptimizer();
    
    // Make it globally available
    window.CRMSearchOptimizer = CRMSearchOptimizer;
    window.crmSearchOptimizer = crmSearchOptimizer;
});

// Add CSS for search optimization
const searchStyles = `
<style>
.search-results {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--card-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    box-shadow: var(--card-shadow);
    max-height: 400px;
    overflow-y: auto;
    z-index: 1000;
    margin-top: 5px;
}

.search-result-item {
    display: flex;
    align-items: center;
    padding: 12px 15px;
    cursor: pointer;
    transition: background 0.2s ease;
    border-bottom: 1px solid var(--border-color);
}

.search-result-item:last-child {
    border-bottom: none;
}

.search-result-item:hover {
    background: var(--hover-bg);
}

.search-result-icon {
    width: 40px;
    height: 40px;
    border-radius: 6px;
    background: var(--accent-color);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 12px;
    font-size: 14px;
}

.search-result-content {
    flex: 1;
}

.search-result-title {
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 4px;
}

.search-result-description {
    font-size: 0.85rem;
    color: var(--text-secondary);
}

.search-loading, .search-error, .search-no-results {
    padding: 20px;
    text-align: center;
    color: var(--text-secondary);
}

.search-loading i, .search-error i, .search-no-results i {
    font-size: 1.5rem;
    margin-bottom: 10px;
    display: block;
}

.search-error {
    color: var(--danger-color);
}

.search-loading.search-loading {
    border-color: var(--accent-color);
}

input.search-loading {
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20' viewBox='0 0 24 24'%3E%3Cstyle%3E%40keyframes spin%7B0%25%7Btransform:rotate(0deg)%7D100%25%7Btransform:rotate(360deg)%7D%7D%3C/style%3E%3Cpath d='M12,1A11,11,0,1,0,23,12,11,11,0,0,0,12,1Zm0,19a8,8,0,1,1,8-8A8,8,0,0,1,12,20Z' opacity='.25'/%3E%3Cpath d='M10.14,1.16a11,11,0,0,0-9,8.92A1.59,1.59,0,0,0,2.46,12,1.52,1.52,0,0,0,4.11,10.7a8,8,0,0,1,6.56-6.56A1.52,1.52,0,0,0,10.14,1.16Z' fill='%23667eea' style='animation:spin 1s linear infinite'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 10px center;
    background-size: 20px;
    padding-right: 40px;
}
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', searchStyles);
