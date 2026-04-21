// Universal Copy/Paste Fix - Override any global blockers
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing universal copy/paste fix...');
    
    // Override any global contextmenu blockers
    function enableCopyPaste() {
        // Remove any existing contextmenu event listeners that prevent copying
        const originalPreventDefault = Event.prototype.preventDefault;
        Event.prototype.preventDefault = function() {
            // Allow contextmenu, copy, cut, paste, and selectstart events
            if (this.type === 'contextmenu' || 
                this.type === 'copy' || 
                this.type === 'cut' || 
                this.type === 'paste' || 
                this.type === 'selectstart' ||
                this.type === 'mousedown' ||
                this.type === 'mouseup') {
                // Check if the target is text content
                const target = this.target;
                if (target && (
                    target.tagName === 'TEXTAREA' ||
                    target.tagName === 'INPUT' ||
                    target.tagName === 'TD' ||
                    target.tagName === 'TH' ||
                    target.tagName === 'P' ||
                    target.tagName === 'SPAN' ||
                    target.tagName === 'DIV' ||
                    target.tagName === 'A' ||
                    target.tagName === 'LI' ||
                    target.tagName === 'H1' ||
                    target.tagName === 'H2' ||
                    target.tagName === 'H3' ||
                    target.tagName === 'H4' ||
                    target.tagName === 'H5' ||
                    target.tagName === 'H6'
                )) {
                    console.log('Allowing', this.type, 'on', target.tagName);
                    return; // Don't prevent default for text elements
                }
            }
            return originalPreventDefault.call(this);
        };
        
        // Add global event listeners to ensure copy/paste works
        document.addEventListener('contextmenu', function(e) {
            console.log('Global contextmenu event on:', e.target.tagName);
            // Allow context menu everywhere
            return true;
        }, true);
        
        document.addEventListener('copy', function(e) {
            console.log('Global copy event on:', e.target.tagName);
            // Allow copy everywhere
            return true;
        }, true);
        
        document.addEventListener('cut', function(e) {
            console.log('Global cut event on:', e.target.tagName);
            // Allow cut everywhere
            return true;
        }, true);
        
        document.addEventListener('paste', function(e) {
            console.log('Global paste event on:', e.target.tagName);
            // Allow paste on input elements
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
                return true;
            }
        }, true);
        
        document.addEventListener('selectstart', function(e) {
            console.log('Global selectstart event on:', e.target.tagName);
            // Allow text selection everywhere
            return true;
        }, true);
        
        // Remove any global oncontextmenu handlers
        if (document.oncontextmenu) {
            document.oncontextmenu = null;
            console.log('Removed document.oncontextmenu');
        }
        
        // Remove any global onselectstart handlers
        if (document.onselectstart) {
            document.onselectstart = null;
            console.log('Removed document.onselectstart');
        }
        
        // Remove any global oncopy handlers
        if (document.oncopy) {
            document.oncopy = null;
            console.log('Removed document.oncopy');
        }
        
        // Remove any global oncut handlers
        if (document.oncut) {
            document.oncut = null;
            console.log('Removed document.oncut');
        }
        
        console.log('Universal copy/paste fix applied');
    }
    
    // Apply the fix immediately
    enableCopyPaste();
    
    // Also apply after a short delay to catch any late-loading scripts
    setTimeout(enableCopyPaste, 1000);
    
    // Apply again after window load to catch any remaining blockers
    window.addEventListener('load', enableCopyPaste);
});

// Also ensure the fix runs in case this script loads after DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
        console.log('DOM not ready, adding copy fix listener');
    });
} else {
    console.log('DOM already ready, applying copy fix immediately');
    // Apply the fix immediately if DOM is already loaded
    (function() {
        // Remove any existing contextmenu event listeners that prevent copying
        const originalPreventDefault = Event.prototype.preventDefault;
        Event.prototype.preventDefault = function() {
            // Allow contextmenu, copy, cut, paste, and selectstart events
            if (this.type === 'contextmenu' || 
                this.type === 'copy' || 
                this.type === 'cut' || 
                this.type === 'paste' || 
                this.type === 'selectstart' ||
                this.type === 'mousedown' ||
                this.type === 'mouseup') {
                // Check if the target is text content
                const target = this.target;
                if (target && (
                    target.tagName === 'TEXTAREA' ||
                    target.tagName === 'INPUT' ||
                    target.tagName === 'TD' ||
                    target.tagName === 'TH' ||
                    target.tagName === 'P' ||
                    target.tagName === 'SPAN' ||
                    target.tagName === 'DIV' ||
                    target.tagName === 'A' ||
                    target.tagName === 'LI' ||
                    target.tagName === 'H1' ||
                    target.tagName === 'H2' ||
                    target.tagName === 'H3' ||
                    target.tagName === 'H4' ||
                    target.tagName === 'H5' ||
                    target.tagName === 'H6'
                )) {
                    console.log('Allowing', this.type, 'on', target.tagName);
                    return; // Don't prevent default for text elements
                }
            }
            return originalPreventDefault.call(this);
        };
        
        console.log('Immediate copy fix applied');
    })();
}
