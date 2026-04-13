/**
 * Bulk Operations Progress Tracking
 * Handles real-time progress tracking for bulk operations
 */

class BulkOperationProgress {
    constructor() {
        this.activeOperations = new Map();
        this.progressIntervals = new Map();
        this.updateInterval = 2000; // 2 seconds
        this.init();
    }

    init() {
        // Initialize progress tracking for any existing operations
        this.initializeExistingOperations();
        
        // Set up event listeners for bulk operation forms
        this.setupBulkOperationListeners();
        
        // Start polling for running operations
        this.startProgressPolling();
    }

    initializeExistingOperations() {
        // Check for any running operations on page load
        const operationElements = document.querySelectorAll('[data-operation-id]');
        operationElements.forEach(element => {
            const operationId = element.dataset.operationId;
            if (element.dataset.status === 'running') {
                this.startProgressTracking(operationId);
            }
        });
    }

    setupBulkOperationListeners() {
        // Listen for bulk operation form submissions
        const bulkForms = document.querySelectorAll('[data-bulk-operation]');
        bulkForms.forEach(form => {
            form.addEventListener('submit', (e) => {
                this.handleBulkOperationSubmit(e, form);
            });
        });

        // Listen for bulk action buttons
        const bulkButtons = document.querySelectorAll('[data-bulk-action]');
        bulkButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                this.handleBulkActionButton(e, button);
            });
        });
    }

    handleBulkOperationSubmit(event, form) {
        const operationType = form.dataset.bulkOperation;
        const submitButton = form.querySelector('button[type="submit"]');
        
        if (!submitButton) return;

        // Disable submit button and show loading state
        submitButton.disabled = true;
        const originalText = submitButton.innerHTML;
        submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

        // Store original button state for potential restoration
        submitButton.dataset.originalText = originalText;
    }

    handleBulkActionButton(event, button) {
        const action = button.dataset.bulkAction;
        const confirmMessage = button.dataset.confirmMessage;
        
        if (confirmMessage && !confirm(confirmMessage)) {
            event.preventDefault();
            return;
        }

        // Disable button and show loading state
        button.disabled = true;
        const originalText = button.innerHTML;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
        button.dataset.originalText = originalText;
    }

    startProgressTracking(operationId) {
        if (this.activeOperations.has(operationId)) {
            return; // Already tracking
        }

        this.activeOperations.set(operationId, {
            id: operationId,
            status: 'running',
            startTime: Date.now()
        });

        // Create progress modal if it doesn't exist
        this.createProgressModal(operationId);

        // Start polling for this operation
        const interval = setInterval(() => {
            this.updateOperationProgress(operationId);
        }, this.updateInterval);

        this.progressIntervals.set(operationId, interval);
    }

    createProgressModal(operationId) {
        // Check if modal already exists
        if (document.getElementById(`progress-modal-${operationId}`)) {
            return;
        }

        const modalHtml = `
            <div id="progress-modal-${operationId}" class="modal fade" tabindex="-1">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">
                                <i class="fas fa-tasks"></i> Bulk Operation Progress
                            </h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="operation-info mb-3">
                                <div class="row">
                                    <div class="col-md-6">
                                        <strong>Operation ID:</strong> <span id="operation-id-${operationId}">${operationId}</span>
                                    </div>
                                    <div class="col-md-6">
                                        <strong>Type:</strong> <span id="operation-type-${operationId}">Loading...</span>
                                    </div>
                                </div>
                            </div>

                            <div class="progress-section">
                                <div class="d-flex justify-content-between mb-2">
                                    <span>Progress</span>
                                    <span id="progress-percentage-${operationId}">0%</span>
                                </div>
                                <div class="progress mb-3">
                                    <div id="progress-bar-${operationId}" class="progress-bar progress-bar-striped progress-bar-animated" 
                                         role="progressbar" style="width: 0%"></div>
                                </div>

                                <div class="row text-center">
                                    <div class="col-md-3">
                                        <div class="stat-box">
                                            <div class="stat-number" id="processed-items-${operationId}">0</div>
                                            <div class="stat-label">Processed</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stat-box">
                                            <div class="stat-number text-success" id="success-items-${operationId}">0</div>
                                            <div class="stat-label">Success</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stat-box">
                                            <div class="stat-number text-danger" id="failed-items-${operationId}">0</div>
                                            <div class="stat-label">Failed</div>
                                        </div>
                                    </div>
                                    <div class="col-md-3">
                                        <div class="stat-box">
                                            <div class="stat-number text-info" id="eta-${operationId}">--</div>
                                            <div class="stat-label">ETA</div>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div class="performance-section mt-3">
                                <h6>Performance</h6>
                                <div class="row">
                                    <div class="col-md-6">
                                        <small class="text-muted">Processing Rate: <span id="processing-rate-${operationId}">0</span> items/sec</small>
                                    </div>
                                    <div class="col-md-6">
                                        <small class="text-muted">Elapsed Time: <span id="elapsed-time-${operationId}">0s</span></small>
                                    </div>
                                </div>
                            </div>

                            <div class="error-section mt-3" id="error-section-${operationId}" style="display: none;">
                                <h6>Recent Errors</h6>
                                <div id="error-list-${operationId}" class="error-list"></div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                            <button type="button" class="btn btn-warning" id="cancel-operation-${operationId}" 
                                    onclick="bulkProgress.cancelOperation('${operationId}')">
                                <i class="fas fa-stop"></i> Cancel
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById(`progress-modal-${operationId}`));
        modal.show();

        // Auto-show modal when operation starts
        modal.show();
    }

    async updateOperationProgress(operationId) {
        try {
            const response = await fetch(`/dashboard/api/bulk-operation-progress/${operationId}/`);
            const data = await response.json();

            if (response.ok) {
                this.updateProgressUI(operationId, data);
                
                // Check if operation is complete
                if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
                    this.completeOperation(operationId, data);
                }
            } else {
                console.error('Failed to fetch operation progress:', data);
                this.handleOperationError(operationId, data.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Error fetching operation progress:', error);
            this.handleOperationError(operationId, 'Network error');
        }
    }

    updateProgressUI(operationId, data) {
        // Update basic info
        const typeElement = document.getElementById(`operation-type-${operationId}`);
        if (typeElement) {
            typeElement.textContent = this.getOperationTypeDisplay(data.operation_type);
        }

        // Update progress bar
        const progressBar = document.getElementById(`progress-bar-${operationId}`);
        const progressPercentage = document.getElementById(`progress-percentage-${operationId}`);
        if (progressBar && progressPercentage) {
            const percentage = Math.round(data.progress_percentage || 0);
            progressBar.style.width = `${percentage}%`;
            progressPercentage.textContent = `${percentage}%`;

            // Update progress bar color based on status
            progressBar.className = 'progress-bar';
            if (data.status === 'completed') {
                progressBar.classList.add('bg-success');
            } else if (data.status === 'failed') {
                progressBar.classList.add('bg-danger');
            } else if (data.status === 'cancelled') {
                progressBar.classList.add('bg-warning');
            } else {
                progressBar.classList.add('progress-bar-striped', 'progress-bar-animated', 'bg-primary');
            }
        }

        // Update statistics
        this.updateElement(`processed-items-${operationId}`, data.processed_items || 0);
        this.updateElement(`success-items-${operationId}`, data.success_items || 0);
        this.updateElement(`failed-items-${operationId}`, data.failed_items || 0);
        this.updateElement(`eta-${operationId}`, data.eta_display || '--');

        // Update performance metrics
        this.updateElement(`processing-rate-${operationId}`, (data.items_per_second || 0).toFixed(1));
        this.updateElement(`elapsed-time-${operationId}`, this.formatDuration(data.elapsed_seconds || 0));

        // Update errors if any
        if (data.error_samples && data.error_samples.length > 0) {
            this.updateErrorDisplay(operationId, data.error_samples);
        }
    }

    updateElement(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            element.textContent = value;
        }
    }

    updateErrorDisplay(operationId, errors) {
        const errorSection = document.getElementById(`error-section-${operationId}`);
        const errorList = document.getElementById(`error-list-${operationId}`);
        
        if (errorSection && errorList) {
            errorSection.style.display = 'block';
            errorList.innerHTML = errors.slice(0, 5).map(error => `
                <div class="alert alert-sm alert-danger">
                    <strong>Error:</strong> ${error.error || 'Unknown error'}
                    ${error.lead_name ? `<br><small>Lead: ${error.lead_name}</small>` : ''}
                    ${error.lead_id ? `<br><small>ID: ${error.lead_id}</small>` : ''}
                </div>
            `).join('');
        }
    }

    completeOperation(operationId, data) {
        // Stop polling
        const interval = this.progressIntervals.get(operationId);
        if (interval) {
            clearInterval(interval);
            this.progressIntervals.delete(operationId);
        }

        // Update UI to show completion
        this.updateProgressUI(operationId, data);

        // Update cancel button
        const cancelButton = document.getElementById(`cancel-operation-${operationId}`);
        if (cancelButton) {
            cancelButton.disabled = true;
            cancelButton.style.display = 'none';
        }

        // Show completion message
        const modalBody = document.querySelector(`#progress-modal-${operationId} .modal-body`);
        if (modalBody) {
            const alertClass = data.status === 'completed' ? 'success' : 
                              data.status === 'failed' ? 'danger' : 'warning';
            
            const alertHtml = `
                <div class="alert alert-${alertClass} alert-dismissible fade show" role="alert">
                    <strong>Operation ${data.status}!</strong>
                    ${data.error_message || ''}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `;
            
            // Insert alert at the top of modal body
            modalBody.insertAdjacentHTML('afterbegin', alertHtml);
        }

        // Remove from active operations
        this.activeOperations.delete(operationId);

        // Auto-hide modal after 5 seconds if successful
        if (data.status === 'completed') {
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById(`progress-modal-${operationId}`));
                if (modal) {
                    modal.hide();
                }
            }, 5000);
        }
    }

    handleOperationError(operationId, error) {
        console.error(`Operation ${operationId} error:`, error);
        
        // Show error in modal
        const modalBody = document.querySelector(`#progress-modal-${operationId} .modal-body`);
        if (modalBody) {
            const errorHtml = `
                <div class="alert alert-danger">
                    <strong>Error:</strong> ${error}
                    <br><small>Please refresh the page and try again.</small>
                </div>
            `;
            modalBody.insertAdjacentHTML('afterbegin', errorHtml);
        }

        // Stop polling
        const interval = this.progressIntervals.get(operationId);
        if (interval) {
            clearInterval(interval);
            this.progressIntervals.delete(operationId);
        }
    }

    async cancelOperation(operationId) {
        if (!confirm('Are you sure you want to cancel this operation?')) {
            return;
        }

        try {
            const response = await fetch(`/dashboard/api/bulk-operation-cancel/${operationId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            
            if (response.ok) {
                // Update UI to show cancellation
                this.completeOperation(operationId, { ...data, status: 'cancelled' });
            } else {
                alert('Failed to cancel operation: ' + (data.error || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error cancelling operation:', error);
            alert('Error cancelling operation. Please try again.');
        }
    }

    startProgressPolling() {
        // Poll for any running operations periodically
        setInterval(() => {
            this.checkForRunningOperations();
        }, 10000); // Check every 10 seconds
    }

    async checkForRunningOperations() {
        try {
            const response = await fetch('/dashboard/api/running-operations/');
            const data = await response.json();

            if (response.ok && data.running_operations) {
                data.running_operations.forEach(operationId => {
                    if (!this.activeOperations.has(operationId)) {
                        this.startProgressTracking(operationId);
                    }
                });
            }
        } catch (error) {
            console.error('Error checking for running operations:', error);
        }
    }

    getOperationTypeDisplay(operationType) {
        const types = {
            'bulk_assign': 'Bulk Assignment',
            'bulk_delete': 'Bulk Deletion',
            'bulk_reassign_duplicates': 'Duplicate Reassignment',
            'user_deletion_reassign': 'User Deletion Reassignment',
            'bulk_import': 'Bulk Import',
            'bulk_export': 'Bulk Export'
        };
        return types[operationType] || operationType;
    }

    formatDuration(seconds) {
        if (seconds < 60) {
            return `${Math.round(seconds)}s`;
        } else if (seconds < 3600) {
            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = Math.round(seconds % 60);
            return `${minutes}m ${remainingSeconds}s`;
        } else {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            return `${hours}h ${minutes}m`;
        }
    }

    getCSRFToken() {
        const cookie = document.cookie.match(/csrftoken=([^;]+)/);
        return cookie ? cookie[1] : '';
    }

    // Public method to manually start tracking an operation
    startTracking(operationId) {
        this.startProgressTracking(operationId);
    }

    // Public method to stop tracking an operation
    stopTracking(operationId) {
        const interval = this.progressIntervals.get(operationId);
        if (interval) {
            clearInterval(interval);
            this.progressIntervals.delete(operationId);
        }
        this.activeOperations.delete(operationId);
    }
}

// Initialize the bulk operations progress tracker
const bulkProgress = new BulkOperationProgress();

// Export for use in other scripts
window.bulkProgress = bulkProgress;
