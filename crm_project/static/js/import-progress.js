/**
 * Import Progress Tracking System
 * Provides real-time progress monitoring for lead import operations
 */

class ImportProgressTracker {
    constructor(options = {}) {
        this.sessionId = options.sessionId;
        this.updateInterval = options.updateInterval || 2000; // 2 seconds
        this.autoStart = options.autoStart !== false;
        this.onProgress = options.onProgress || (() => {});
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        this.onCancel = options.onCancel || (() => {});
        
        this.intervalId = null;
        this.isRunning = false;
        this.lastUpdate = null;
        
        // Create modal if needed
        this.modal = this.createModal();
        
        if (this.autoStart && this.sessionId) {
            this.start();
        }
    }
    
    createModal() {
        // Check if modal already exists
        const existingModal = document.getElementById('importProgressModal');
        if (existingModal) {
            return existingModal;
        }
        
        const modalHtml = `
            <div class="modal fade" id="importProgressModal" tabindex="-1" data-bs-backdrop="static" data-bs-keyboard="false">
                <div class="modal-dialog modal-lg">
                    <div class="modal-content">
                        <div class="modal-header bg-primary text-white">
                            <h5 class="modal-title">
                                <i class="fas fa-upload me-2"></i>
                                Import Progress
                            </h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <div class="row mb-3">
                                <div class="col-md-8">
                                    <h6 class="mb-2">Current Stage: <span id="currentStage" class="text-primary">Starting...</span></h6>
                                    <div class="progress mb-3" style="height: 25px;">
                                        <div id="progressBar" class="progress-bar progress-bar-striped progress-bar-animated bg-success" 
                                             role="progressbar" style="width: 0%">0%</div>
                                    </div>
                                </div>
                                <div class="col-md-4 text-end">
                                    <div id="recordsPerSecond" class="text-muted small">0 records/sec</div>
                                    <div id="estimatedTime" class="text-muted small">ETA: --</div>
                                </div>
                            </div>
                            
                            <div class="row text-center mb-3">
                                <div class="col">
                                    <div class="card bg-light">
                                        <div class="card-body p-2">
                                            <div class="h5 mb-0 text-primary" id="totalRecords">0</div>
                                            <div class="small text-muted">Total Records</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col">
                                    <div class="card bg-light">
                                        <div class="card-body p-2">
                                            <div class="h5 mb-0 text-success" id="processedRecords">0</div>
                                            <div class="small text-muted">Processed</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col">
                                    <div class="card bg-light">
                                        <div class="card-body p-2">
                                            <div class="h5 mb-0 text-info" id="importedRecords">0</div>
                                            <div class="small text-muted">Imported</div>
                                        </div>
                                    </div>
                                </div>
                                <div class="col">
                                    <div class="card bg-light">
                                        <div class="card-body p-2">
                                            <div class="h5 mb-0 text-warning" id="failedRecords">0</div>
                                            <div class="small text-muted">Failed</div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            
                            <div id="errorSection" class="alert alert-danger d-none">
                                <h6><i class="fas fa-exclamation-triangle me-2"></i>Errors Detected</h6>
                                <div id="errorList" class="small"></div>
                            </div>
                            
                            <div class="d-flex justify-content-between">
                                <button id="cancelImportBtn" class="btn btn-outline-danger" style="display: none;">
                                    <i class="fas fa-stop me-2"></i>Cancel Import
                                </button>
                                <div id="statusBadge" class="badge bg-secondary">Pending</div>
                            </div>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        return document.getElementById('importProgressModal');
    }
    
    start(sessionId = null) {
        if (sessionId) {
            this.sessionId = sessionId;
        }
        
        if (!this.sessionId) {
            console.error('ImportProgressTracker: No session ID provided');
            return;
        }
        
        this.isRunning = true;
        this.showModal();
        this.fetchProgress();
        
        // Start polling
        this.intervalId = setInterval(() => {
            this.fetchProgress();
        }, this.updateInterval);
    }
    
    stop() {
        this.isRunning = false;
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
    
    showModal() {
        const modal = new bootstrap.Modal(this.modal);
        modal.show();
    }
    
    hideModal() {
        const modal = bootstrap.Modal.getInstance(this.modal);
        if (modal) {
            modal.hide();
        }
    }
    
    async fetchProgress() {
        if (!this.sessionId || !this.isRunning) return;
        
        try {
            const response = await fetch(`/dashboard/api/import-progress/?session_id=${this.sessionId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.updateUI(data);
            this.onProgress(data);
            
            // Check if import is complete
            if (data.status === 'completed') {
                this.stop();
                this.onComplete(data);
                this.showCompletionMessage(data);
            } else if (data.status === 'failed') {
                this.stop();
                this.onError(data);
                this.showErrorMessage(data);
            } else if (data.status === 'cancelled') {
                this.stop();
                this.onCancel(data);
                this.showCancelMessage(data);
            }
            
        } catch (error) {
            console.error('Error fetching import progress:', error);
            this.stop();
            this.onError({ error: error.message });
        }
    }
    
    updateUI(data) {
        // Update progress bar
        const progressBar = document.getElementById('progressBar');
        const percentage = Math.round(data.progress_percentage || 0);
        progressBar.style.width = `${percentage}%`;
        progressBar.textContent = `${percentage}%`;
        
        // Update status
        const currentStage = document.getElementById('currentStage');
        currentStage.textContent = data.current_stage || 'Processing...';
        
        // Update statistics
        document.getElementById('totalRecords').textContent = data.total_records || 0;
        document.getElementById('processedRecords').textContent = data.processed_records || 0;
        document.getElementById('importedRecords').textContent = data.imported_records || 0;
        document.getElementById('failedRecords').textContent = data.failed_records || 0;
        
        // Update performance metrics
        const recordsPerSecond = document.getElementById('recordsPerSecond');
        recordsPerSecond.textContent = `${(data.records_per_second || 0).toFixed(1)} records/sec`;
        
        const estimatedTime = document.getElementById('estimatedTime');
        if (data.estimated_time_remaining > 0) {
            const minutes = Math.floor(data.estimated_time_remaining / 60);
            const seconds = data.estimated_time_remaining % 60;
            estimatedTime.textContent = `ETA: ${minutes}m ${seconds}s`;
        } else {
            estimatedTime.textContent = 'ETA: --';
        }
        
        // Update status badge
        const statusBadge = document.getElementById('statusBadge');
        statusBadge.className = 'badge';
        
        switch (data.status) {
            case 'pending':
                statusBadge.classList.add('bg-secondary');
                statusBadge.textContent = 'Pending';
                break;
            case 'processing':
            case 'validating':
            case 'duplicate_checking':
            case 'importing':
                statusBadge.classList.add('bg-primary');
                statusBadge.textContent = 'Processing';
                break;
            case 'completed':
                statusBadge.classList.add('bg-success');
                statusBadge.textContent = 'Completed';
                break;
            case 'failed':
                statusBadge.classList.add('bg-danger');
                statusBadge.textContent = 'Failed';
                break;
            case 'cancelled':
                statusBadge.classList.add('bg-warning');
                statusBadge.textContent = 'Cancelled';
                break;
        }
        
        // Show/hide cancel button
        const cancelBtn = document.getElementById('cancelImportBtn');
        if (['pending', 'processing', 'validating', 'duplicate_checking', 'importing'].includes(data.status)) {
            cancelBtn.style.display = 'inline-block';
        } else {
            cancelBtn.style.display = 'none';
        }
        
        // Update error section
        if (data.error_count > 0) {
            const errorSection = document.getElementById('errorSection');
            const errorList = document.getElementById('errorList');
            
            errorSection.classList.remove('d-none');
            errorList.innerHTML = `
                <div class="mb-2">
                    <strong>Total Errors:</strong> ${data.error_count}
                </div>
                ${data.last_error ? `<div><strong>Last Error:</strong> ${data.last_error}</div>` : ''}
            `;
        } else {
            const errorSection = document.getElementById('errorSection');
            errorSection.classList.add('d-none');
        }
    }
    
    showCompletionMessage(data) {
        const progressBar = document.getElementById('progressBar');
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-success');
        
        // Show success message
        const alertHtml = `
            <div class="alert alert-success alert-dismissible fade show" role="alert">
                <h6><i class="fas fa-check-circle me-2"></i>Import Completed Successfully!</h6>
                <div class="small">
                    <strong>Summary:</strong><br>
                    Total Records: ${data.total_records}<br>
                    Imported: ${data.imported_records}<br>
                    Failed: ${data.failed_records}<br>
                    Processing Rate: ${(data.records_per_second || 0).toFixed(1)} records/sec
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        this.modal.querySelector('.modal-body').insertAdjacentHTML('afterbegin', alertHtml);
    }
    
    showErrorMessage(data) {
        const progressBar = document.getElementById('progressBar');
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-danger');
        
        const alertHtml = `
            <div class="alert alert-danger alert-dismissible fade show" role="alert">
                <h6><i class="fas fa-exclamation-triangle me-2"></i>Import Failed</h6>
                <div class="small">
                    <strong>Error:</strong> ${data.last_error || 'Unknown error occurred'}<br>
                    <strong>Records Processed:</strong> ${data.processed_records} / ${data.total_records}
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        this.modal.querySelector('.modal-body').insertAdjacentHTML('afterbegin', alertHtml);
    }
    
    showCancelMessage(data) {
        const progressBar = document.getElementById('progressBar');
        progressBar.classList.remove('progress-bar-animated');
        progressBar.classList.add('bg-warning');
        
        const alertHtml = `
            <div class="alert alert-warning alert-dismissible fade show" role="alert">
                <h6><i class="fas fa-stop me-2"></i>Import Cancelled</h6>
                <div class="small">
                    <strong>Records Processed:</strong> ${data.processed_records} / ${data.total_records}
                </div>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        `;
        
        this.modal.querySelector('.modal-body').insertAdjacentHTML('afterbegin', alertHtml);
    }
    
    async cancel() {
        if (!this.sessionId) return;
        
        try {
            const response = await fetch('/dashboard/api/import-cancel/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: `session_id=${this.sessionId}`
            });
            
            const data = await response.json();
            if (data.success) {
                this.stop();
                this.onCancel(data);
            } else {
                console.error('Failed to cancel import:', data.error);
            }
        } catch (error) {
            console.error('Error cancelling import:', error);
        }
    }
    
    getCSRFToken() {
        const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
        return cookie ? cookie.split('=')[1] : '';
    }
}

// Auto-setup cancel button
document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', function(e) {
        if (e.target && e.target.id === 'cancelImportBtn') {
            e.preventDefault();
            // Find the tracker instance and cancel
            if (window.importProgressTracker) {
                window.importProgressTracker.cancel();
            }
        }
    });
});

// Export for global access
window.ImportProgressTracker = ImportProgressTracker;
