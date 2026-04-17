/**
 * Inline Editing for Agent Efficiency Improvements
 * Provides double-click inline editing for lead fields with auto-save functionality
 */

class InlineEditor {
    constructor() {
        this.currentEdit = null;
        this.validationRules = {};
        this.init();
    }

    async init() {
        // Load validation rules
        await this.loadValidationRules();
        
        // Add double-click listeners to editable fields
        this.attachEventListeners();
        
        console.log('Inline Editor initialized');
    }

    async loadValidationRules() {
        try {
            const response = await fetch('/dashboard/ajax/field-validation-rules/');
            const data = await response.json();
            if (data.success) {
                this.validationRules = data.validation_rules;
            }
        } catch (error) {
            console.error('Failed to load validation rules:', error);
        }
    }

    attachEventListeners() {
        document.addEventListener('dblclick', (e) => {
            const editableField = e.target.closest('.editable-field');
            if (editableField && !editableField.classList.contains('editing')) {
                this.startEdit(editableField);
            }
        });

        // Close edit on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.currentEdit) {
                this.cancelEdit();
            }
        });

        // Close edit when clicking outside
        document.addEventListener('click', (e) => {
            if (this.currentEdit && !this.currentEdit.element.contains(e.target)) {
                this.saveEdit();
            }
        });
    }

    startEdit(fieldElement) {
        // Cancel any existing edit
        if (this.currentEdit) {
            this.cancelEdit();
        }

        const fieldName = fieldElement.dataset.field;
        const leadId = fieldElement.dataset.leadId;
        const fieldContent = fieldElement.querySelector('.field-content');
        
        if (!fieldContent) return;

        const currentValue = this.getCurrentValue(fieldElement, fieldName);
        
        // Create input element
        const inputElement = this.createInputElement(fieldName, currentValue);
        
        // Replace content with input
        fieldContent.innerHTML = '';
        fieldContent.appendChild(inputElement);
        
        // Add editing state
        fieldElement.classList.add('editing');
        
        // Store current edit context
        this.currentEdit = {
            element: fieldElement,
            fieldName: fieldName,
            leadId: leadId,
            inputElement: inputElement,
            originalValue: currentValue
        };

        // Focus and select input
        inputElement.focus();
        if (inputElement.select) {
            inputElement.select();
        }

        // Add input-specific event listeners
        this.attachInputListeners(inputElement);
    }

    createInputElement(fieldName, currentValue) {
        const input = document.createElement('input');
        input.type = this.getInputType(fieldName);
        input.className = 'inline-input';
        input.value = currentValue || '';
        
        // Add field-specific attributes
        if (fieldName === 'followup_datetime') {
            input.placeholder = 'YYYY-MM-DD HH:MM';
            input.title = 'Format: YYYY-MM-DD HH:MM';
        } else if (fieldName === 'email') {
            input.type = 'email';
            input.placeholder = 'email@example.com';
        } else if (fieldName === 'mobile') {
            input.placeholder = '+1 (555) 123-4567';
        } else if (fieldName === 'name') {
            input.placeholder = 'Lead Name';
        }

        return input;
    }

    getInputType(fieldName) {
        switch (fieldName) {
            case 'email':
                return 'email';
            case 'followup_datetime':
                return 'datetime-local';
            case 'mobile':
                return 'tel';
            default:
                return 'text';
        }
    }

    getCurrentValue(fieldElement, fieldName) {
        const textContent = fieldElement.textContent.trim();
        
        // Handle special cases
        if (fieldName === 'followup_datetime') {
            // Convert display format back to input format
            if (textContent === '-') return '';
            // Try to parse various date formats
            const dateMatch = textContent.match(/(\w{3}\s+\d{1,2},\s+\d{4})/);
            if (dateMatch) {
                return dateMatch[1]; // Return in the same format for now
            }
        }
        
        return textContent === '-' ? '' : textContent;
    }

    attachInputListeners(inputElement) {
        // Save on Enter key
        inputElement.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.saveEdit();
            } else if (e.key === 'Escape') {
                e.preventDefault();
                this.cancelEdit();
            }
        });

        // Validate on input
        inputElement.addEventListener('input', () => {
            this.validateInput(inputElement);
        });

        // Save on blur (but allow click events to propagate first)
        setTimeout(() => {
            inputElement.addEventListener('blur', () => {
                if (this.currentEdit && this.currentEdit.inputElement === inputElement) {
                    setTimeout(() => this.saveEdit(), 100);
                }
            });
        }, 100);
    }

    validateInput(inputElement) {
        if (!this.currentEdit) return;

        const fieldName = this.currentEdit.fieldName;
        const value = inputElement.value;
        const rules = this.validationRules[fieldName];

        if (!rules) return true;

        let isValid = true;
        let errorMessage = '';

        // Required field validation
        if (rules.required && (!value || value.trim() === '')) {
            isValid = false;
            errorMessage = `${fieldName} is required`;
        }

        // Length validation
        if (isValid && value && rules.min_length && value.length < rules.min_length) {
            isValid = false;
            errorMessage = rules.message || `Minimum ${rules.min_length} characters required`;
        }

        if (isValid && value && rules.max_length && value.length > rules.max_length) {
            isValid = false;
            errorMessage = rules.message || `Maximum ${rules.max_length} characters allowed`;
        }

        // Pattern validation
        if (isValid && value && rules.pattern) {
            const pattern = new RegExp(rules.pattern);
            if (!pattern.test(value)) {
                isValid = false;
                errorMessage = rules.message || 'Invalid format';
            }
        }

        // Special validation for dates
        if (isValid && fieldName === 'followup_datetime' && value) {
            const inputDate = new Date(value);
            const now = new Date();
            if (inputDate < now) {
                isValid = false;
                errorMessage = 'Follow-up date cannot be in the past';
            }
        }

        // Update input styling
        this.updateInputValidation(inputElement, isValid, errorMessage);

        return isValid;
    }

    updateInputValidation(inputElement, isValid, errorMessage) {
        // Remove existing validation message
        const existingMessage = inputElement.parentNode.querySelector('.validation-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        // Update input classes
        inputElement.classList.remove('error', 'success');
        
        if (!isValid) {
            inputElement.classList.add('error');
            
            // Add validation message
            const messageDiv = document.createElement('div');
            messageDiv.className = 'validation-message';
            messageDiv.textContent = errorMessage;
            inputElement.parentNode.appendChild(messageDiv);
        }
    }

    async saveEdit() {
        if (!this.currentEdit) return;

        const { element, fieldName, leadId, inputElement, originalValue } = this.currentEdit;
        
        // Validate before saving
        if (!this.validateInput(inputElement)) {
            return;
        }

        const newValue = inputElement.value.trim();
        
        // Check if value actually changed
        if (newValue === originalValue) {
            this.cancelEdit();
            return;
        }

        // Show loading state
        element.classList.add('loading');

        try {
            const response = await fetch('/dashboard/ajax/inline-field-update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    lead_id: leadId,
                    field_name: fieldName,
                    new_value: newValue
                })
            });

            const data = await response.json();

            if (data.success) {
                // Update the display with new value
                this.updateFieldDisplay(element, fieldName, data.display_value || newValue);
                
                // Show success feedback
                this.showFeedback(element, data.message, 'success');
            } else {
                // Show error feedback
                this.showFeedback(element, data.error, 'error');
                inputElement.classList.add('error');
            }
        } catch (error) {
            console.error('Error saving field:', error);
            this.showFeedback(element, 'Error saving field. Please try again.', 'error');
        } finally {
            // Clean up
            element.classList.remove('loading');
            this.cleanupEdit();
        }
    }

    cancelEdit() {
        if (!this.currentEdit) return;

        const { element, originalValue } = this.currentEdit;
        
        // Restore original display
        this.updateFieldDisplay(element, this.currentEdit.fieldName, originalValue);
        
        // Clean up
        this.cleanupEdit();
    }

    updateFieldDisplay(element, fieldName, value) {
        const fieldContent = element.querySelector('.field-content');
        if (!fieldContent) return;

        let displayHtml = '';
        
        switch (fieldName) {
            case 'name':
                displayHtml = `<strong><a href="/dashboard/leads/${element.dataset.leadId}/" class="lead-name-link">${value || '-'}</a></strong>`;
                // Add badges if this is the name field
                const badges = element.querySelector('.lead-type-badge');
                if (badges) {
                    displayHtml += ' ' + badges.outerHTML;
                }
                break;
            case 'mobile':
            case 'email':
                displayHtml = value || '-';
                break;
            case 'followup_datetime':
                displayHtml = value ? this.formatDate(value) : '-';
                break;
            default:
                displayHtml = value || '-';
        }

        // Add edit icon back
        displayHtml += '<i class="fas fa-edit edit-icon" title="Double-click to edit"></i>';
        
        fieldContent.innerHTML = displayHtml;
    }

    formatDate(dateString) {
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric', 
                year: 'numeric' 
            });
        } catch (error) {
            return dateString;
        }
    }

    showFeedback(element, message, type) {
        // Remove existing feedback
        const existingFeedback = element.querySelector('.validation-message');
        if (existingFeedback) {
            existingFeedback.remove();
        }

        // Create feedback message
        const feedbackDiv = document.createElement('div');
        feedbackDiv.className = `validation-message ${type}`;
        feedbackDiv.textContent = message;
        
        // Position it
        const fieldContent = element.querySelector('.field-content');
        fieldContent.appendChild(feedbackDiv);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (feedbackDiv.parentNode) {
                feedbackDiv.remove();
            }
        }, 3000);
    }

    cleanupEdit() {
        if (this.currentEdit) {
            this.currentEdit.element.classList.remove('editing');
            this.currentEdit = null;
        }
    }

    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(cookie => cookie.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }
}

// Enhanced Status Dropdown with Keyboard Navigation
class StatusDropdownEnhancer {
    constructor() {
        this.currentDropdown = null;
        this.selectedOptionIndex = -1;
        this.init();
    }

    init() {
        document.addEventListener('click', (e) => {
            const toggleButton = e.target.closest('.status-badge.dropdown-toggle');
            if (toggleButton) {
                e.preventDefault();
                this.toggleDropdown(toggleButton);
            } else if (this.currentDropdown && !this.currentDropdown.contains(e.target)) {
                this.closeDropdown();
            }
        });

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (this.currentDropdown) {
                this.handleKeyboardNavigation(e);
            }
        });
    }

    toggleDropdown(button) {
        const dropdownId = button.dataset.leadId;
        const dropdown = document.getElementById(`status-dropdown-${dropdownId}`);
        
        if (this.currentDropdown === dropdown) {
            this.closeDropdown();
            return;
        }

        this.closeDropdown();
        this.currentDropdown = dropdown;
        this.selectedOptionIndex = -1;
        
        // Populate status options if not already populated
        if (dropdown.children.length === 0) {
            this.populateStatusOptions(dropdown, button.dataset.currentStatus);
        }
        
        dropdown.style.display = 'block';
        this.adjustDropdownPosition(dropdown);
    }

    populateStatusOptions(dropdown, currentStatus) {
        const statusOptions = [
            { value: 'lead', label: 'Lead', icon: 'fas fa-user' },
            { value: 'contacted', label: 'Contacted', icon: 'fas fa-phone' },
            { value: 'interested_follow_up', label: 'Interested - Follow Up', icon: 'fas fa-clock' },
            { value: 'not_interested', label: 'Not Interested', icon: 'fas fa-times' },
            { value: 'in_few_months', label: 'Follow Up in Few Months', icon: 'fas fa-calendar' },
            { value: 'sale_done', label: 'Sale Done', icon: 'fas fa-check-circle' }
        ];

        statusOptions.forEach(status => {
            const option = document.createElement('div');
            option.className = 'status-option';
            option.dataset.value = status.value;
            option.dataset.leadId = dropdown.id.replace('status-dropdown-', '');
            
            if (status.value === currentStatus) {
                option.classList.add('selected');
            }

            option.innerHTML = `
                <i class="${status.icon}"></i>
                <span>${status.label}</span>
            `;

            option.addEventListener('click', () => {
                this.selectStatus(option);
            });

            dropdown.appendChild(option);
        });
    }

    handleKeyboardNavigation(e) {
        const options = Array.from(this.currentDropdown.querySelectorAll('.status-option'));
        
        switch (e.key) {
            case 'ArrowDown':
                e.preventDefault();
                this.selectedOptionIndex = Math.min(this.selectedOptionIndex + 1, options.length - 1);
                this.highlightOption(options[this.selectedOptionIndex]);
                break;
            case 'ArrowUp':
                e.preventDefault();
                this.selectedOptionIndex = Math.max(this.selectedOptionIndex - 1, 0);
                this.highlightOption(options[this.selectedOptionIndex]);
                break;
            case 'Enter':
                e.preventDefault();
                if (this.selectedOptionIndex >= 0) {
                    this.selectStatus(options[this.selectedOptionIndex]);
                }
                break;
            case 'Escape':
                e.preventDefault();
                this.closeDropdown();
                break;
        }
    }

    highlightOption(option) {
        // Remove previous highlights
        this.currentDropdown.querySelectorAll('.status-option').forEach(opt => {
            opt.classList.remove('keyboard-selected');
        });
        
        if (option) {
            option.classList.add('keyboard-selected');
            option.scrollIntoView({ block: 'nearest' });
        }
    }

    async selectStatus(option) {
        const leadId = option.dataset.leadId;
        const newStatus = option.dataset.value;
        
        try {
            const response = await fetch('/dashboard/ajax/lead-status-update/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    lead_id: leadId,
                    status: newStatus
                })
            });

            const data = await response.json();
            
            if (data.success) {
                // Update status badge
                this.updateStatusBadge(leadId, newStatus, data.new_status_display);
                this.closeDropdown();
            } else {
                alert('Error updating status: ' + data.error);
            }
        } catch (error) {
            console.error('Error updating status:', error);
            alert('Error updating status. Please try again.');
        }
    }

    updateStatusBadge(leadId, newStatus, displayText) {
        const button = document.querySelector(`[data-lead-id="${leadId}"].status-badge`);
        if (button) {
            // Update status classes
            button.className = `status-badge status-${newStatus} dropdown-toggle`;
            
            // Update text
            const textSpan = button.querySelector('span') || button.firstChild;
            if (textSpan.nodeType === Node.TEXT_NODE) {
                button.textContent = displayText + ' ';
            } else {
                textSpan.textContent = displayText;
            }
            
            // Re-add chevron icon
            const chevron = document.createElement('i');
            chevron.className = 'fas fa-chevron-down';
            button.appendChild(chevron);
        }
    }

    adjustDropdownPosition(dropdown) {
        const rect = dropdown.getBoundingClientRect();
        const viewportHeight = window.innerHeight;
        const viewportWidth = window.innerWidth;
        
        // Adjust vertical position if needed
        if (rect.bottom > viewportHeight) {
            dropdown.style.top = 'auto';
            dropdown.style.bottom = '100%';
            dropdown.style.marginBottom = '8px';
            dropdown.style.marginTop = '0';
        }
        
        // Adjust horizontal position if needed
        if (rect.right > viewportWidth) {
            dropdown.style.left = 'auto';
            dropdown.style.right = '0';
        }
    }

    closeDropdown() {
        if (this.currentDropdown) {
            this.currentDropdown.style.display = 'none';
            this.currentDropdown = null;
            this.selectedOptionIndex = -1;
        }
    }

    getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(cookie => cookie.startsWith('csrftoken='))
            ?.split('=')[1];
        return cookieValue || '';
    }
}

// Quick Actions Context Menu
class QuickActionsMenu {
    constructor() {
        this.currentMenu = null;
        this.currentLeadId = null;
        this.init();
    }

    init() {
        document.addEventListener('contextmenu', (e) => {
            const leadRow = e.target.closest('tbody tr');
            if (leadRow && !leadRow.classList.contains('empty-state')) {
                // Only prevent context menu if clicking on interactive elements, not text content
                const isInteractiveElement = e.target.closest('.lead-checkbox, .status-badge, .editable-field, .action-buttons, .quick-actions-trigger');
                const isTextContent = e.target.closest('.field-content, .lead-name-link, td');
                
                // Allow native context menu for text selection and copying
                if (isTextContent && !isInteractiveElement) {
                    return; // Allow default context menu for text copying
                }
                
                // Prevent context menu for interactive elements
                e.preventDefault();
                this.showMenu(e, leadRow);
            }
        });

        document.addEventListener('click', () => {
            this.hideMenu();
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.hideMenu();
            }
        });
    }

    showMenu(event, leadRow) {
        this.hideMenu();

        const leadId = this.getLeadId(leadRow);
        this.currentLeadId = leadId;

        const menu = this.createMenu(leadId);
        document.body.appendChild(menu);

        // Position menu
        const x = event.clientX;
        const y = event.clientY;
        
        // Adjust position if menu would go off-screen
        const rect = menu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        let finalX = x;
        let finalY = y;

        if (x + rect.width > viewportWidth) {
            finalX = viewportWidth - rect.width - 10;
        }

        if (y + rect.height > viewportHeight) {
            finalY = viewportHeight - rect.height - 10;
        }

        menu.style.left = finalX + 'px';
        menu.style.top = finalY + 'px';
        menu.style.display = 'block';

        this.currentMenu = menu;
    }

    hideMenu() {
        if (this.currentMenu) {
            this.currentMenu.remove();
            this.currentMenu = null;
            this.currentLeadId = null;
        }
    }

    getLeadId(leadRow) {
        // Try to get lead ID from various sources
        const checkbox = leadRow.querySelector('.lead-checkbox');
        if (checkbox && checkbox.dataset.leadId) {
            return checkbox.dataset.leadId;
        }

        const editableField = leadRow.querySelector('.editable-field');
        if (editableField && editableField.dataset.leadId) {
            return editableField.dataset.leadId;
        }

        const nameLink = leadRow.querySelector('.lead-name-link');
        if (nameLink && nameLink.href) {
            const match = nameLink.href.match(/\/leads\/(\d+)\//);
            if (match) return match[1];
        }

        return null;
    }

    createMenu(leadId) {
        const menu = document.createElement('div');
        menu.className = 'quick-actions-menu';
        menu.innerHTML = `
            <div class="quick-actions-header">
                <i class="fas fa-bolt"></i>
                <span>Quick Actions</span>
            </div>
            <div class="quick-actions-list">
                <div class="quick-action-item" data-action="call" data-lead-id="${leadId}">
                    <i class="fas fa-phone"></i>
                    <span>Call Lead</span>
                    <kbd>Ctrl+C</kbd>
                </div>
                <div class="quick-action-item" data-action="email" data-lead-id="${leadId}">
                    <i class="fas fa-envelope"></i>
                    <span>Send Email</span>
                    <kbd>Ctrl+E</kbd>
                </div>
                <div class="quick-action-item" data-action="schedule-followup" data-lead-id="${leadId}">
                    <i class="fas fa-calendar-plus"></i>
                    <span>Schedule Follow-up</span>
                    <kbd>Ctrl+F</kbd>
                </div>
                <div class="quick-action-item" data-action="view-details" data-lead-id="${leadId}">
                    <i class="fas fa-eye"></i>
                    <span>View Details</span>
                    <kbd>Ctrl+D</kbd>
                </div>
                <div class="quick-action-item" data-action="edit-lead" data-lead-id="${leadId}">
                    <i class="fas fa-edit"></i>
                    <span>Edit Lead</span>
                    <kbd>Ctrl+Enter</kbd>
                </div>
            </div>
        `;

        // Add click handlers
        menu.querySelectorAll('.quick-action-item').forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = item.dataset.action;
                const leadId = item.dataset.leadId;
                this.executeAction(action, leadId);
            });
        });

        return menu;
    }

    executeAction(action, leadId) {
        switch (action) {
            case 'call':
                this.initiateCall(leadId);
                break;
            case 'email':
                this.composeEmail(leadId);
                break;
            case 'schedule-followup':
                this.scheduleFollowUp(leadId);
                break;
            case 'view-details':
                this.viewLeadDetails(leadId);
                break;
            case 'edit-lead':
                this.editLead(leadId);
                break;
        }
        
        this.hideMenu();
    }

    initiateCall(leadId) {
        // Get lead phone number
        const leadRow = document.querySelector(`[data-lead-id="${leadId}"]`).closest('tr');
        const mobileField = leadRow.querySelector('[data-field="mobile"]');
        const phoneNumber = mobileField ? mobileField.textContent.trim() : '';
        
        if (phoneNumber && phoneNumber !== '-') {
            // Open phone dialer or copy to clipboard
            if (navigator.userAgent.includes('Mobile')) {
                window.location.href = `tel:${phoneNumber}`;
            } else {
                navigator.clipboard.writeText(phoneNumber).then(() => {
                    this.showNotification('Phone number copied to clipboard', 'success');
                }).catch(() => {
                    this.showNotification('Failed to copy phone number', 'error');
                });
            }
        } else {
            this.showNotification('No phone number available for this lead', 'warning');
        }
    }

    composeEmail(leadId) {
        // Get lead email
        const leadRow = document.querySelector(`[data-lead-id="${leadId}"]`).closest('tr');
        const emailField = leadRow.querySelector('[data-field="email"]');
        const email = emailField ? emailField.textContent.trim() : '';
        
        if (email && email !== '-') {
            window.location.href = `mailto:${email}`;
        } else {
            this.showNotification('No email address available for this lead', 'warning');
        }
    }

    scheduleFollowUp(leadId) {
        // Navigate to lead detail page with follow-up focus
        window.location.href = `/dashboard/leads/${leadId}/#followup`;
    }

    viewLeadDetails(leadId) {
        window.location.href = `/dashboard/leads/${leadId}/`;
    }

    editLead(leadId) {
        window.location.href = `/dashboard/leads/${leadId}/edit/`;
    }

    showNotification(message, type = 'info') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `quick-action-notification ${type}`;
        notification.innerHTML = `
            <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
            <span>${message}</span>
        `;

        // Position at top-right
        notification.style.position = 'fixed';
        notification.style.top = '20px';
        notification.style.right = '20px';
        notification.style.zIndex = '10000';
        notification.style.padding = '12px 20px';
        notification.style.borderRadius = '8px';
        notification.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.15)';
        notification.style.display = 'flex';
        notification.style.alignItems = 'center';
        notification.style.gap = '10px';
        notification.style.fontSize = '14px';
        notification.style.fontWeight = '500';

        // Style based on type
        if (type === 'success') {
            notification.style.background = 'var(--success-color)';
            notification.style.color = 'white';
        } else if (type === 'error') {
            notification.style.background = 'var(--danger-color)';
            notification.style.color = 'white';
        } else {
            notification.style.background = 'var(--info-color)';
            notification.style.color = 'white';
        }

        document.body.appendChild(notification);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            if (notification.parentNode) {
                notification.remove();
            }
        }, 3000);
    }
}

// Keyboard Shortcuts Manager
class KeyboardShortcuts {
    constructor() {
        this.shortcuts = new Map();
        this.init();
    }

    init() {
        this.setupShortcuts();
        this.attachEventListeners();
    }

    setupShortcuts() {
        // Define shortcuts
        this.shortcuts.set('ctrl+c', () => {
            // Only override Ctrl+C if quick actions menu is active and user is not selecting text
            if (window.quickActionsMenu && window.quickActionsMenu.currentLeadId && !this.isTextSelected()) {
                window.quickActionsMenu.executeAction('call', window.quickActionsMenu.currentLeadId);
            }
            // Otherwise, allow native copy behavior by not preventing default
        });

        this.shortcuts.set('ctrl+e', () => {
            if (window.quickActionsMenu && window.quickActionsMenu.currentLeadId) {
                window.quickActionsMenu.executeAction('email', window.quickActionsMenu.currentLeadId);
            }
        });

        this.shortcuts.set('ctrl+f', () => {
            if (window.quickActionsMenu && window.quickActionsMenu.currentLeadId) {
                window.quickActionsMenu.executeAction('schedule-followup', window.quickActionsMenu.currentLeadId);
            }
        });

        this.shortcuts.set('ctrl+d', () => {
            if (window.quickActionsMenu && window.quickActionsMenu.currentLeadId) {
                window.quickActionsMenu.executeAction('view-details', window.quickActionsMenu.currentLeadId);
            }
        });

        this.shortcuts.set('ctrl+shift+a', () => {
            this.selectAllLeads();
        });

        this.shortcuts.set('ctrl+shift+n', () => {
            this.createNewLead();
        });

        this.shortcuts.set('ctrl+/', () => {
            this.focusSearch();
        });
    }

    attachEventListeners() {
        document.addEventListener('keydown', (e) => {
            const key = this.getKeyString(e);
            
            if (this.shortcuts.has(key)) {
                // For Ctrl+C, only prevent default if we're going to handle it
                if (key === 'ctrl+c') {
                    if (window.quickActionsMenu && window.quickActionsMenu.currentLeadId && !this.isTextSelected()) {
                        e.preventDefault();
                        const action = this.shortcuts.get(key);
                        action();
                    }
                    // If text is selected or no quick actions context, don't prevent default
                } else {
                    // For other shortcuts, prevent default as before
                    e.preventDefault();
                    const action = this.shortcuts.get(key);
                    action();
                }
            }
        });
    }

    getKeyString(event) {
        const parts = [];
        
        if (event.ctrlKey || event.metaKey) {
            parts.push('ctrl');
        }
        
        if (event.shiftKey) {
            parts.push('shift');
        }
        
        if (event.altKey) {
            parts.push('alt');
        }
        
        if (event.key && event.key.length === 1) {
            parts.push(event.key.toLowerCase());
        } else if (event.key && event.key.length > 1) {
            parts.push(event.key.toLowerCase());
        }
        
        return parts.join('+');
    }

    selectAllLeads() {
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = true;
            selectAllCheckbox.dispatchEvent(new Event('change'));
        }
    }

    createNewLead() {
        const createButton = document.querySelector('a[href*="lead_create"]');
        if (createButton) {
            window.location.href = createButton.href;
        }
    }

    focusSearch() {
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }

    isTextSelected() {
        const selection = window.getSelection();
        return selection && selection.toString().trim().length > 0;
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.inlineEditor = new InlineEditor();
    window.statusDropdown = new StatusDropdownEnhancer();
    window.quickActionsMenu = new QuickActionsMenu();
    window.keyboardShortcuts = new KeyboardShortcuts();
    
    console.log('Agent Efficiency Improvements loaded');
});
