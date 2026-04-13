/**
 * Performance monitoring and optimization utilities for CRM
 * Tracks page load times, user interactions, and provides performance insights
 */

class CRMPerformanceMonitor {
    constructor() {
        this.startTime = performance.now();
        this.metrics = {
            pageLoad: {},
            interactions: [],
            domOperations: 0,
            cacheHits: 0,
            cacheMisses: 0
        };
        this.observers = [];
        this.init();
    }

    init() {
        // Track page load performance
        this.trackPageLoad();
        
        // Track DOM mutations
        this.trackDOMOperations();
        
        // Track user interactions
        this.trackUserInteractions();
        
        // Track long tasks
        this.trackLongTasks();
        
        // Setup performance observer if available
        this.setupPerformanceObserver();
        
        // Send metrics to server periodically
        setInterval(() => this.sendMetrics(), 30000); // Every 30 seconds
    }

    trackPageLoad() {
        window.addEventListener('load', () => {
            const navigation = performance.getEntriesByType('navigation')[0];
            
            this.metrics.pageLoad = {
                domContentLoaded: navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart,
                loadComplete: navigation.loadEventEnd - navigation.loadEventStart,
                firstPaint: this.getFirstPaint(),
                firstContentfulPaint: this.getFirstContentfulPaint(),
                totalLoadTime: performance.now() - this.startTime,
                resourceCount: performance.getEntriesByType('resource').length
            };

            // Log slow page loads
            if (this.metrics.pageLoad.totalLoadTime > 3000) {
                console.warn(`Slow page load detected: ${this.metrics.pageLoad.totalLoadTime}ms`);
                this.reportSlowLoad();
            }
        });
    }

    getFirstPaint() {
        const paintEntries = performance.getEntriesByType('paint');
        const firstPaint = paintEntries.find(entry => entry.name === 'first-paint');
        return firstPaint ? Math.round(firstPaint.startTime) : 0;
    }

    getFirstContentfulPaint() {
        const paintEntries = performance.getEntriesByType('paint');
        const fcp = paintEntries.find(entry => entry.name === 'first-contentful-paint');
        return fcp ? Math.round(fcp.startTime) : 0;
    }

    trackDOMOperations() {
        const observer = new MutationObserver((mutations) => {
            this.metrics.domOperations += mutations.length;
            
            // Track excessive DOM manipulation
            if (this.metrics.domOperations > 1000) {
                console.warn('Excessive DOM manipulation detected');
                this.optimizeDOMOperations();
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeOldValue: true
        });

        this.observers.push(observer);
    }

    trackUserInteractions() {
        const events = ['click', 'scroll', 'keydown', 'input'];
        
        events.forEach(eventType => {
            document.addEventListener(eventType, (event) => {
                const startTime = performance.now();
                
                requestAnimationFrame(() => {
                    const responseTime = performance.now() - startTime;
                    
                    this.metrics.interactions.push({
                        type: eventType,
                        responseTime: responseTime,
                        timestamp: Date.now(),
                        target: event.target.tagName + (event.target.className ? '.' + event.target.className : '')
                    });

                    // Keep only last 100 interactions
                    if (this.metrics.interactions.length > 100) {
                        this.metrics.interactions = this.metrics.interactions.slice(-100);
                    }

                    // Log slow interactions
                    if (responseTime > 200) {
                        console.warn(`Slow ${eventType} interaction: ${responseTime}ms`);
                    }
                });
            });
        });
    }

    trackLongTasks() {
        if ('PerformanceObserver' in window) {
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.duration > 50) { // Tasks longer than 50ms
                        console.warn(`Long task detected: ${entry.duration}ms`);
                        this.reportLongTask(entry);
                    }
                }
            });

            try {
                observer.observe({ entryTypes: ['longtask'] });
                this.observers.push(observer);
            } catch (e) {
                // Long task API not supported
                console.log('Long task monitoring not supported');
            }
        }
    }

    setupPerformanceObserver() {
        if ('PerformanceObserver' in window) {
            // Monitor resource loading
            const resourceObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.duration > 1000) { // Slow resources
                        console.warn(`Slow resource: ${entry.name} took ${entry.duration}ms`);
                    }
                }
            });

            try {
                resourceObserver.observe({ entryTypes: ['resource'] });
                this.observers.push(resourceObserver);
            } catch (e) {
                console.log('Resource monitoring not supported');
            }
        }
    }

    // Debounce function for optimizing frequent operations
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    // Throttle function for rate limiting
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

    // Optimize DOM operations by batching
    batchDOMUpdates(updates) {
        return new Promise(resolve => {
            requestAnimationFrame(() => {
                const fragment = document.createDocumentFragment();
                
                updates.forEach(update => {
                    if (update.type === 'add') {
                        fragment.appendChild(update.element);
                    }
                });
                
                if (fragment.children.length > 0) {
                    document.body.appendChild(fragment);
                }
                
                resolve();
            });
        });
    }

    // Lazy loading for images and content
    setupLazyLoading() {
        const images = document.querySelectorAll('img[data-src]');
        
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.classList.remove('lazy');
                        observer.unobserve(img);
                    }
                });
            });

            images.forEach(img => imageObserver.observe(img));
        } else {
            // Fallback for older browsers
            images.forEach(img => {
                img.src = img.dataset.src;
                img.classList.remove('lazy');
            });
        }
    }

    // Virtual scrolling for large lists
    setupVirtualScrolling(container, itemHeight, renderItem) {
        const containerHeight = container.clientHeight;
        const visibleItems = Math.ceil(containerHeight / itemHeight) + 2;
        let scrollTop = 0;
        let allItems = [];

        const render = () => {
            const startIndex = Math.floor(scrollTop / itemHeight);
            const endIndex = Math.min(startIndex + visibleItems, allItems.length);
            
            // Clear container
            container.innerHTML = '';
            
            // Create spacer for items above viewport
            const topSpacer = document.createElement('div');
            topSpacer.style.height = `${startIndex * itemHeight}px`;
            container.appendChild(topSpacer);
            
            // Render visible items
            for (let i = startIndex; i < endIndex; i++) {
                const item = renderItem(allItems[i], i);
                item.style.height = `${itemHeight}px`;
                container.appendChild(item);
            }
            
            // Create spacer for items below viewport
            const bottomSpacer = document.createElement('div');
            bottomSpacer.style.height = `${(allItems.length - endIndex) * itemHeight}px`;
            container.appendChild(bottomSpacer);
        };

        const throttledScroll = this.throttle(() => {
            scrollTop = container.scrollTop;
            render();
        }, 16); // ~60fps

        container.addEventListener('scroll', throttledScroll);

        return {
            setItems: (items) => {
                allItems = items;
                render();
            },
            refresh: render
        };
    }

    // Cache management
    cacheData(key, data, ttl = 300000) { // 5 minutes default TTL
        try {
            const item = {
                data: data,
                timestamp: Date.now(),
                ttl: ttl
            };
            localStorage.setItem(`crm_cache_${key}`, JSON.stringify(item));
            this.metrics.cacheHits++;
        } catch (e) {
            console.warn('Cache write failed:', e);
            this.metrics.cacheMisses++;
        }
    }

    getCachedData(key) {
        try {
            const item = JSON.parse(localStorage.getItem(`crm_cache_${key}`));
            if (item && (Date.now() - item.timestamp) < item.ttl) {
                this.metrics.cacheHits++;
                return item.data;
            }
            this.metrics.cacheMisses++;
            return null;
        } catch (e) {
            console.warn('Cache read failed:', e);
            this.metrics.cacheMisses++;
            return null;
        }
    }

    clearExpiredCache() {
        const keys = Object.keys(localStorage);
        keys.forEach(key => {
            if (key.startsWith('crm_cache_')) {
                try {
                    const item = JSON.parse(localStorage.getItem(key));
                    if (item && (Date.now() - item.timestamp) >= item.ttl) {
                        localStorage.removeItem(key);
                    }
                } catch (e) {
                    localStorage.removeItem(key); // Remove corrupted items
                }
            }
        });
    }

    // Performance optimization suggestions
    getOptimizationSuggestions() {
        const suggestions = [];
        
        if (this.metrics.pageLoad.totalLoadTime > 3000) {
            suggestions.push('Consider optimizing images and reducing resource size');
        }
        
        if (this.metrics.domOperations > 500) {
            suggestions.push('Reduce DOM manipulations, consider virtual scrolling');
        }
        
        const avgInteractionTime = this.metrics.interactions.reduce((sum, i) => sum + i.responseTime, 0) / this.metrics.interactions.length;
        if (avgInteractionTime > 100) {
            suggestions.push('Optimize event handlers and use debouncing');
        }
        
        const cacheHitRate = this.metrics.cacheHits / (this.metrics.cacheHits + this.metrics.cacheMisses);
        if (cacheHitRate < 0.5) {
            suggestions.push('Implement better caching strategy');
        }
        
        return suggestions;
    }

    // Report performance issues
    reportSlowLoad() {
        this.sendToServer('/api/performance/slow-load', {
            loadTime: this.metrics.pageLoad.totalLoadTime,
            url: window.location.href,
            userAgent: navigator.userAgent
        });
    }

    reportLongTask(entry) {
        this.sendToServer('/api/performance/long-task', {
            duration: entry.duration,
            startTime: entry.startTime,
            url: window.location.href
        });
    }

    // Send metrics to server
    sendMetrics() {
        const metrics = {
            ...this.metrics,
            url: window.location.href,
            timestamp: Date.now(),
            userAgent: navigator.userAgent,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            }
        };

        this.sendToServer('/api/performance/metrics', metrics);
    }

    sendToServer(endpoint, data) {
        if (navigator.sendBeacon) {
            navigator.sendBeacon(endpoint, JSON.stringify(data));
        } else {
            // Fallback for older browsers
            fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            }).catch(e => console.warn('Failed to send performance data:', e));
        }
    }

    // Cleanup
    destroy() {
        this.observers.forEach(observer => observer.disconnect());
        this.observers = [];
    }
}

// Initialize performance monitor
let crmPerformanceMonitor;

document.addEventListener('DOMContentLoaded', () => {
    crmPerformanceMonitor = new CRMPerformanceMonitor();
    
    // Setup lazy loading for images
    crmPerformanceMonitor.setupLazyLoading();
    
    // Clear expired cache periodically
    setInterval(() => {
        crmPerformanceMonitor.clearExpiredCache();
    }, 60000); // Every minute
});

// Export for use in other scripts
window.CRMPerformanceMonitor = CRMPerformanceMonitor;
window.crmPerformanceMonitor = crmPerformanceMonitor;

// Utility functions for common performance optimizations
window.CRMPerformance = {
    // Debounced search
    debounceSearch: function(callback, delay = 300) {
        return crmPerformanceMonitor.debounce(callback, delay);
    },
    
    // Throttled scroll
    throttleScroll: function(callback, limit = 16) {
        return crmPerformanceMonitor.throttle(callback, limit);
    },
    
    // Cache API responses
    cacheResponse: function(key, data, ttl = 300000) {
        return crmPerformanceMonitor.cacheData(key, data, ttl);
    },
    
    // Get cached response
    getCachedResponse: function(key) {
        return crmPerformanceMonitor.getCachedData(key);
    },
    
    // Get performance suggestions
    getSuggestions: function() {
        return crmPerformanceMonitor ? crmPerformanceMonitor.getOptimizationSuggestions() : [];
    }
};
