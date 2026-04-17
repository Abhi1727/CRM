// CSRF Token Helper Function
function getCSRFToken() {
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
    if (!csrfToken) {
        console.warn('CSRF token not found in meta tag');
        return null;
    }
    return csrfToken;
}

// Setup CSRF headers for all AJAX requests
function setupCSRF() {
    const csrfToken = getCSRFToken();
    if (csrfToken) {
        // Set up for fetch API
        const originalFetch = window.fetch;
        window.fetch = function(...args) {
            if (args[1] && typeof args[1] === 'object') {
                args[1].headers = {
                    ...args[1].headers,
                    'X-CSRFToken': csrfToken,
                };
            }
            return originalFetch.apply(this, args);
        };
        
        // Set up for XMLHttpRequest
        const originalXHROpen = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url) {
            originalXHROpen.call(this, method, url);
            this.setRequestHeader('X-CSRFToken', csrfToken);
        };
    }
}

// Sidebar Toggle
document.addEventListener('DOMContentLoaded', function() {
    // Setup CSRF for AJAX requests
    setupCSRF();
    const sidebar = document.getElementById('sidebar');
    const mobileToggle = document.getElementById('mobileToggle');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarThemeToggle = document.getElementById('sidebarThemeToggle');
    const sidebarThemeIcon = document.getElementById('sidebarThemeIcon');
    const topBar = document.querySelector('.top-bar');
    
    // SIMPLIFIED THEME TOGGLE - DIRECT APPROACH
    console.log('Initializing theme toggle...');
    
    // Find theme toggle button
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    
    console.log('Theme toggle element:', themeToggle);
    console.log('Theme icon element:', themeIcon);
    
    // Direct theme toggle function
    function toggleTheme() {
        console.log('Toggle theme called');
        
        const html = document.documentElement;
        const isDark = html.hasAttribute('data-theme');
        
        console.log('Current state - isDark:', isDark);
        
        if (isDark) {
            // Switch to light
            html.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
            if (themeIcon) themeIcon.className = 'fas fa-moon';
            if (sidebarThemeIcon) sidebarThemeIcon.className = 'fas fa-moon';
            console.log('Switched to light mode');
            
            // Apply light styles immediately
            document.body.style.backgroundColor = '#ffffff';
            document.body.style.color = '#212529';
            
        } else {
            // Switch to dark
            html.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            if (themeIcon) themeIcon.className = 'fas fa-sun';
            if (sidebarThemeIcon) sidebarThemeIcon.className = 'fas fa-sun';
            console.log('Switched to dark mode');
            
            // Apply dark styles immediately
            document.body.style.backgroundColor = '#1a0f1f';
            document.body.style.color = '#f0e6ff';
        }
    }
    
    // Add click listener for top-bar theme toggle
    if (themeToggle) {
        themeToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('Theme toggle clicked!');
            toggleTheme();
        });
        
        // Also try double click in case
        themeToggle.addEventListener('dblclick', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('Theme toggle double clicked!');
            toggleTheme();
        });
        
        console.log('Theme toggle listener added successfully');
    } else {
        console.log('Top-bar theme toggle not found (expected on leads pages)');
    }
    
    // Add click listener for sidebar theme toggle
    if (sidebarThemeToggle) {
        sidebarThemeToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            console.log('Sidebar theme toggle clicked!');
            toggleTheme();
        });
        
        console.log('Sidebar theme toggle listener added successfully');
    }
    
    // Show sidebar theme toggle if no top-bar
    if (!topBar && sidebarThemeToggle) {
        sidebarThemeToggle.style.display = 'flex';
        console.log('Showing sidebar theme toggle (no top-bar found)');
    }
    
    // Try to find any fallback theme toggle elements
    const fallbackToggles = document.querySelectorAll('.theme-toggle');
    fallbackToggles.forEach(fallback => {
        if (fallback !== themeToggle && fallback !== sidebarThemeToggle) {
            console.log('Found fallback theme toggle:', fallback);
            fallback.addEventListener('click', toggleTheme);
        }
    });
    
    // Initialize theme on load
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
        if (sidebarThemeIcon) sidebarThemeIcon.className = 'fas fa-sun';
        document.body.style.backgroundColor = '#1a0f1f';
        document.body.style.color = '#f0e6ff';
    }
    
    // Make function globally available
    window.toggleTheme = toggleTheme;
    window.forceDarkMode = function() {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
        if (sidebarThemeIcon) sidebarThemeIcon.className = 'fas fa-sun';
        document.body.style.backgroundColor = '#1a0f1f';
        document.body.style.color = '#f0e6ff';
        console.log('Force dark mode applied');
    };
    
    window.forceLightMode = function() {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
        if (themeIcon) themeIcon.className = 'fas fa-moon';
        if (sidebarThemeIcon) sidebarThemeIcon.className = 'fas fa-moon';
        document.body.style.backgroundColor = '#ffffff';
        document.body.style.color = '#212529';
        console.log('Force light mode applied');
    };
    
    console.log('Theme toggle ready! Use: toggleTheme(), forceDarkMode(), or forceLightMode()');
    
    // Mobile toggle (only if top-bar exists)
    if (mobileToggle) {
        mobileToggle.addEventListener('click', function() {
            sidebar.classList.toggle('active');
        });
    } else {
        console.log('Mobile toggle not found (expected on leads pages without top-bar)');
        
        // If no mobile toggle, ensure sidebar toggle works for mobile
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', function() {
                sidebar.classList.toggle('active');
                sidebar.classList.toggle('collapsed');
            });
        }
    }
    
    // Sidebar toggle
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            sidebar.classList.toggle('collapsed');
        });
    }
    
    // Submenu toggle
    const submenuToggles = document.querySelectorAll('.submenu-toggle');
    submenuToggles.forEach(toggle => {
        toggle.addEventListener('click', function(e) {
            e.preventDefault();
            const parent = this.parentElement;
            parent.classList.toggle('open');
        });
    });
    
    // Auto-open submenu if current page is in submenu
    const currentPath = window.location.pathname;
    const allLinks = document.querySelectorAll('.sidebar-nav a');
    allLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
            // If it's in a submenu, open the parent
            const submenu = link.closest('.submenu');
            if (submenu) {
                submenu.parentElement.classList.add('open');
            }
        }
    });
    
    // Close alert messages
    const closeButtons = document.querySelectorAll('.close-alert');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            this.parentElement.style.display = 'none';
        });
    });
    
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => {
                alert.style.display = 'none';
            }, 300);
        }, 5000);
    });
    
    // Duplicate Management Pagination Enhancements
    initDuplicatePagination();
});

function initDuplicatePagination() {
    // Enhanced page size change for duplicate views
    const pageSizeSelect = document.getElementById('page-size');
    if (pageSizeSelect) {
        pageSizeSelect.addEventListener('change', function() {
            changePageSize(this.value);
        });
    }
    
    // Auto-refresh pagination on filter changes
    const filterSelects = document.querySelectorAll('select[name="status"], select[name="type"]');
    filterSelects.forEach(select => {
        select.addEventListener('change', function() {
            // Reset to first page when filters change
            const urlParams = new URLSearchParams(window.location.search);
            urlParams.set('page', '1');
            urlParams.set(this.name, this.value);
            window.location.href = window.location.pathname + '?' + urlParams.toString();
        });
    });
    
    // Preserve expanded groups across pagination
    preserveGroupExpansion();
}

function preserveGroupExpansion() {
    // Store expanded group IDs in sessionStorage
    const expandedGroups = JSON.parse(sessionStorage.getItem('expandedDuplicateGroups') || '[]');
    
    // Re-expand groups that were previously expanded
    expandedGroups.forEach(groupId => {
        const detailsRow = document.getElementById('group-' + groupId);
        const expandBtn = document.querySelector('[data-group-id="' + groupId + '"] .expand-btn i');
        
        if (detailsRow && expandBtn) {
            detailsRow.style.display = 'table-row';
            expandBtn.className = 'fas fa-chevron-up';
        }
    });
    
    // Update toggleGroup function to save state
    const originalToggleGroup = window.toggleGroup;
    window.toggleGroup = function(groupId) {
        if (originalToggleGroup) {
            originalToggleGroup(groupId);
        }
        
        // Save expanded state
        const detailsRow = document.getElementById('group-' + groupId);
        const isExpanded = detailsRow && detailsRow.style.display !== 'none';
        
        let expandedGroups = JSON.parse(sessionStorage.getItem('expandedDuplicateGroups') || '[]');
        
        if (isExpanded) {
            if (!expandedGroups.includes(groupId)) {
                expandedGroups.push(groupId);
            }
        } else {
            expandedGroups = expandedGroups.filter(id => id !== groupId);
        }
        
        sessionStorage.setItem('expandedDuplicateGroups', JSON.stringify(expandedGroups));
    };
}

// Enhanced duplicate filtering with AJAX (optional enhancement)
function filterDuplicates() {
    const status = document.querySelector('select[name="status"]')?.value || '';
    const type = document.querySelector('select[name="type"]')?.value || '';
    const pageSize = document.getElementById('page-size')?.value || '20';
    
    // Build URL with all parameters
    const urlParams = new URLSearchParams({
        'status': status,
        'type': type,
        'page_size': pageSize,
        'page': 1
    });
    
    // Navigate to filtered results
    window.location.href = window.location.pathname + '?' + urlParams.toString();
}

// Bulk actions with pagination awareness
function performBulkAction(action) {
    const selectedGroups = getSelectedGroups();
    if (selectedGroups.length === 0) {
        alert('Please select at least one group to perform this action.');
        return;
    }
    
    if (!confirm(`Are you sure you want to ${action} ${selectedGroups.length} group(s)?`)) {
        return;
    }
    
    // Include current page and filters in the form submission
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = window.location.pathname;
    
    // Add CSRF token
    const csrfToken = getCSRFToken() || document.querySelector('[name=csrfmiddlewaretoken]')?.value;
    if (csrfToken) {
        const csrfInput = document.createElement('input');
        csrfInput.type = 'hidden';
        csrfInput.name = 'csrfmiddlewaretoken';
        csrfInput.value = csrfToken;
        form.appendChild(csrfInput);
    } else {
        console.error('CSRF token not found for bulk action');
        return;
    }
    
    // Add action
    const actionInput = document.createElement('input');
    actionInput.type = 'hidden';
    actionInput.name = 'action';
    actionInput.value = action;
    form.appendChild(actionInput);
    
    // Add selected groups
    selectedGroups.forEach(groupId => {
        const groupInput = document.createElement('input');
        groupInput.type = 'hidden';
        groupInput.name = 'group_ids';
        groupInput.value = groupId;
        form.appendChild(groupInput);
    });
    
    // Preserve current page and filters
    const urlParams = new URLSearchParams(window.location.search);
    ['page', 'page_size', 'status', 'type'].forEach(param => {
        if (urlParams.has(param)) {
            const paramInput = document.createElement('input');
            paramInput.type = 'hidden';
            paramInput.name = param;
            paramInput.value = urlParams.get(param);
            form.appendChild(paramInput);
        }
    });
    
    document.body.appendChild(form);
    form.submit();
}

function getSelectedGroups() {
    const checkboxes = document.querySelectorAll('input[name="group_ids"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Keyboard shortcuts for pagination
document.addEventListener('keydown', function(e) {
    // Only on duplicate pages
    if (!window.location.pathname.includes('duplicate')) {
        return;
    }
    
    // Ctrl/Cmd + Arrow keys for pagination
    if (e.ctrlKey || e.metaKey) {
        switch(e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                navigateToPage('prev');
                break;
            case 'ArrowRight':
                e.preventDefault();
                navigateToPage('next');
                break;
        }
    }
});

function navigateToPage(direction) {
    const urlParams = new URLSearchParams(window.location.search);
    const currentPage = parseInt(urlParams.get('page') || '1');
    
    let newPage;
    if (direction === 'prev') {
        newPage = Math.max(1, currentPage - 1);
    } else if (direction === 'next') {
        // We need to determine if there's a next page
        const nextPageLink = document.querySelector('.page-btn[title="Next page"]');
        if (nextPageLink) {
            newPage = currentPage + 1;
        } else {
            return; // No next page available
        }
    }
    
    if (newPage && newPage !== currentPage) {
        urlParams.set('page', newPage);
        window.location.href = window.location.pathname + '?' + urlParams.toString();
    }
}
