// Sidebar Toggle
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebar');
    const mobileToggle = document.getElementById('mobileToggle');
    const sidebarToggle = document.getElementById('sidebarToggle');
    
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
            console.log('Switched to light mode');
            
            // Apply light styles immediately
            document.body.style.backgroundColor = '#ffffff';
            document.body.style.color = '#212529';
            
        } else {
            // Switch to dark
            html.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            if (themeIcon) themeIcon.className = 'fas fa-sun';
            console.log('Switched to dark mode');
            
            // Apply dark styles immediately
            document.body.style.backgroundColor = '#1a0f1f';
            document.body.style.color = '#f0e6ff';
        }
    }
    
    // Add click listener
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
        console.error('Theme toggle button NOT found!');
        
        // Try to find any element with theme-toggle class
        const fallback = document.querySelector('.theme-toggle');
        if (fallback) {
            console.log('Found fallback theme toggle:', fallback);
            fallback.addEventListener('click', toggleTheme);
        }
    }
    
    // Initialize theme on load
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
        document.body.style.backgroundColor = '#1a0f1f';
        document.body.style.color = '#f0e6ff';
    }
    
    // Make function globally available
    window.toggleTheme = toggleTheme;
    window.forceDarkMode = function() {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
        document.body.style.backgroundColor = '#1a0f1f';
        document.body.style.color = '#f0e6ff';
        console.log('Force dark mode applied');
    };
    
    window.forceLightMode = function() {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
        if (themeIcon) themeIcon.className = 'fas fa-moon';
        document.body.style.backgroundColor = '#ffffff';
        document.body.style.color = '#212529';
        console.log('Force light mode applied');
    };
    
    console.log('Theme toggle ready! Use: toggleTheme(), forceDarkMode(), or forceLightMode()');
    
    // Mobile toggle
    if (mobileToggle) {
        mobileToggle.addEventListener('click', function() {
            sidebar.classList.toggle('active');
        });
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
});
