/**
 * Password Management JavaScript Module
 * 
 * Provides comprehensive password management functionality including:
 * - Password generation
 * - Password strength checking
 * - Password visibility toggle
 * - Password validation
 * - Real-time feedback
 */

class PasswordManager {
    constructor(options = {}) {
        this.options = {
            minLength: 8,
            maxLength: 128,
            requireLowercase: true,
            requireUppercase: true,
            requireDigits: true,
            requireSpecial: true,
            specialChars: '!@#$%^&*()_+-=[]{}|;:,.<>?',
            autoHideDelay: 10000, // 10 seconds
            ...options
        };
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.setupPasswordFields();
    }
    
    bindEvents() {
        // Password visibility toggle
        document.addEventListener('click', (e) => {
            if (e.target.closest('.password-toggle-btn')) {
                this.handlePasswordToggle(e.target.closest('.password-toggle-btn'));
            }
        });
        
        // Password generation
        document.addEventListener('click', (e) => {
            if (e.target.closest('.generate-password-btn')) {
                this.handlePasswordGeneration(e.target.closest('.generate-password-btn'));
            }
        });
        
        // Password strength checking
        document.addEventListener('input', (e) => {
            if (e.target.matches('input[data-password-strength="true"]')) {
                this.updatePasswordStrength(e.target);
            }
        });
        
        // Password confirmation validation
        document.addEventListener('input', (e) => {
            if (e.target.matches('input[data-password-confirm="true"]')) {
                this.validatePasswordConfirmation(e.target);
            }
        });
    }
    
    setupPasswordFields() {
        // Find all password fields and add strength indicators
        document.querySelectorAll('input[type="password"]').forEach(field => {
            this.addStrengthIndicator(field);
        });
    }
    
    /**
     * Generate a secure random password
     */
    generateSecurePassword(length = 12) {
        if (length < this.options.minLength) {
            length = this.options.minLength;
        }
        if (length > this.options.maxLength) {
            length = this.options.maxLength;
        }
        
        const lowercase = 'abcdefghijklmnopqrstuvwxyz';
        const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const digits = '0123456789';
        const special = this.options.specialChars;
        
        let password = [];
        
        // Ensure at least one character from each required set
        if (this.options.requireLowercase) {
            password.push(lowercase[Math.floor(Math.random() * lowercase.length)]);
        }
        if (this.options.requireUppercase) {
            password.push(uppercase[Math.floor(Math.random() * uppercase.length)]);
        }
        if (this.options.requireDigits) {
            password.push(digits[Math.floor(Math.random() * digits.length)]);
        }
        if (this.options.requireSpecial) {
            password.push(special[Math.floor(Math.random() * special.length)]);
        }
        
        // Fill the rest with random characters from all sets
        const allChars = lowercase + uppercase + digits + special;
        const remainingLength = length - password.length;
        
        for (let i = 0; i < remainingLength; i++) {
            password.push(allChars[Math.floor(Math.random() * allChars.length)]);
        }
        
        // Shuffle the password to avoid predictable patterns
        for (let i = password.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [password[i], password[j]] = [password[j], password[i]];
        }
        
        return password.join('');
    }
    
    /**
     * Handle password toggle button click
     */
    handlePasswordToggle(button) {
        const targetId = button.dataset.target;
        const targetField = document.getElementById(targetId) || 
                           document.querySelector(`input[name="${targetId}"]`) ||
                           button.closest('.input-group').querySelector('input');
        
        if (!targetField) return;
        
        const isHidden = targetField.type === 'password';
        targetField.type = isHidden ? 'text' : 'password';
        
        // Update button icon
        const icon = button.querySelector('i');
        if (icon) {
            icon.className = isHidden ? 'fas fa-eye-slash' : 'fas fa-eye';
        }
        
        // Update button text
        const textNode = button.childNodes[0];
        if (textNode && textNode.nodeType === Node.TEXT_NODE) {
            textNode.textContent = isHidden ? ' Hide' : ' Show';
        }
        
        // Auto-hide after delay if showing
        if (isHidden) {
            setTimeout(() => {
                if (targetField.type === 'text') {
                    targetField.type = 'password';
                    if (icon) icon.className = 'fas fa-eye';
                    if (textNode && textNode.nodeType === Node.TEXT_NODE) {
                        textNode.textContent = ' Show';
                    }
                }
            }, this.options.autoHideDelay);
        }
    }
    
    /**
     * Handle password generation button click
     */
    handlePasswordGeneration(button) {
        const targetId = button.dataset.target;
        const targetField = document.getElementById(targetId) || 
                           document.querySelector(`input[name="${targetId}"]`) ||
                           button.closest('.form-group').querySelector('input[type="password"], input[data-password-strength="true"]');
        
        if (!targetField) return;
        
        const password = this.generateSecurePassword();
        targetField.value = password;
        
        // Trigger input event to update strength indicator
        targetField.dispatchEvent(new Event('input', { bubbles: true }));
        
        // Fill confirm field if exists
        const confirmField = document.getElementById('id_confirm_password') || 
                            document.querySelector('input[name="confirm_password"]') ||
                            targetField.closest('.form-section').querySelector('input[data-password-confirm="true"]');
        
        if (confirmField) {
            confirmField.value = password;
        }
        
        // Show password temporarily
        targetField.type = 'text';
        setTimeout(() => {
            targetField.type = 'password';
        }, this.options.autoHideDelay);
        
        // Select the password for easy copying
        targetField.select();
        
        // Show notification
        this.showNotification('Secure password generated!', 'success');
        
        // Update any strength indicators
        this.updatePasswordStrength(targetField);
    }
    
    /**
     * Add strength indicator to a password field
     */
    addStrengthIndicator(field) {
        const container = field.closest('.form-group');
        if (!container) return;
        
        // Check if indicator already exists
        if (container.querySelector('.password-strength-indicator')) {
            return;
        }
        
        const indicator = document.createElement('div');
        indicator.className = 'password-strength-indicator';
        indicator.innerHTML = `
            <div class="strength-label">Password Strength:</div>
            <div class="strength-bar">
                <div class="strength-fill" id="strength-${field.id || field.name}"></div>
            </div>
            <div class="strength-text" id="strength-text-${field.id || field.name}">Enter a password</div>
        `;
        
        container.appendChild(indicator);
        field.dataset.passwordStrength = 'true';
    }
    
    /**
     * Update password strength indicator
     */
    updatePasswordStrength(field) {
        const password = field.value;
        const strengthFillId = `strength-${field.id || field.name}`;
        const strengthTextId = `strength-text-${field.id || field.name}`;
        
        const strengthFill = document.getElementById(strengthFillId);
        const strengthText = document.getElementById(strengthTextId);
        
        if (!strengthFill || !strengthText) return;
        
        const strength = this.calculatePasswordStrength(password);
        const strengthInfo = this.getStrengthInfo(strength);
        
        strengthFill.style.width = `${strength}%`;
        strengthFill.className = `strength-fill ${strengthInfo.class}`;
        strengthText.textContent = strengthInfo.text;
    }
    
    /**
     * Calculate password strength score (0-100)
     */
    calculatePasswordStrength(password) {
        if (!password) return 0;
        
        let strength = 0;
        
        // Length check
        if (password.length >= this.options.minLength) strength += 20;
        if (password.length >= 12) strength += 10;
        if (password.length >= 16) strength += 10;
        
        // Character variety
        if (this.options.requireLowercase && /[a-z]/.test(password)) strength += 15;
        if (this.options.requireUppercase && /[A-Z]/.test(password)) strength += 15;
        if (this.options.requireDigits && /[0-9]/.test(password)) strength += 15;
        if (this.options.requireSpecial && new RegExp(`[${this.escapeRegex(this.options.specialChars)}]`).test(password)) strength += 15;
        
        // Bonus points for entropy
        const uniqueChars = new Set(password).size;
        if (uniqueChars >= password.length * 0.7) strength += 10;
        
        return Math.min(strength, 100);
    }
    
    /**
     * Get strength information based on score
     */
    getStrengthInfo(score) {
        if (score < 30) {
            return { class: 'weak', text: 'Weak' };
        } else if (score < 50) {
            return { class: 'fair', text: 'Fair' };
        } else if (score < 70) {
            return { class: 'good', text: 'Good' };
        } else {
            return { class: 'strong', text: 'Strong' };
        }
    }
    
    /**
     * Validate password confirmation
     */
    validatePasswordConfirmation(confirmField) {
        const formGroup = confirmField.closest('.form-group');
        if (!formGroup) return;
        
        // Find the original password field
        const passwordField = document.querySelector('input[name="password"]') ||
                            document.querySelector('input[data-password-strength="true"]') ||
                            confirmField.closest('form').querySelector('input[type="password"]');
        
        if (!passwordField) return;
        
        const password = passwordField.value;
        const confirmPassword = confirmField.value;
        
        // Remove previous validation message
        const existingError = formGroup.querySelector('.password-match-error');
        if (existingError) {
            existingError.remove();
        }
        
        // Add validation error if passwords don't match
        if (confirmPassword && password !== confirmPassword) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message password-match-error';
            errorDiv.innerHTML = '<span>Passwords do not match</span>';
            formGroup.appendChild(errorDiv);
        }
    }
    
    /**
     * Show notification message
     */
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `password-notification password-notification-${type}`;
        
        const icon = type === 'success' ? 'fa-check-circle' : 
                    type === 'error' ? 'fa-exclamation-circle' : 
                    'fa-info-circle';
        
        notification.innerHTML = `
            <div class="notification-content">
                <i class="fas ${icon}"></i>
                <span>${message}</span>
            </div>
        `;
        
        // Add styles
        const colors = {
            success: 'linear-gradient(135deg, #28a745, #20c997)',
            error: 'linear-gradient(135deg, #dc3545, #c82333)',
            info: 'linear-gradient(135deg, #667eea, #764ba2)'
        };
        
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${colors[type]};
            color: white;
            padding: 15px 20px;
            border-radius: 8px;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.3);
            z-index: 1000;
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 600;
            transform: translateX(100%);
            transition: transform 0.3s ease;
            max-width: 350px;
        `;
        
        document.body.appendChild(notification);
        
        // Animate in
        requestAnimationFrame(() => {
            notification.style.transform = 'translateX(0)';
        });
        
        // Remove after delay
        setTimeout(() => {
            notification.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    /**
     * Escape special characters for regex
     */
    escapeRegex(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    /**
     * Validate password against requirements
     */
    validatePassword(password) {
        const errors = [];
        
        if (!password) {
            errors.push('Password is required');
            return { valid: false, errors };
        }
        
        if (password.length < this.options.minLength) {
            errors.push(`Password must be at least ${this.options.minLength} characters long`);
        }
        
        if (password.length > this.options.maxLength) {
            errors.push(`Password cannot exceed ${this.options.maxLength} characters`);
        }
        
        if (this.options.requireLowercase && !/[a-z]/.test(password)) {
            errors.push('Password must contain at least one lowercase letter');
        }
        
        if (this.options.requireUppercase && !/[A-Z]/.test(password)) {
            errors.push('Password must contain at least one uppercase letter');
        }
        
        if (this.options.requireDigits && !/[0-9]/.test(password)) {
            errors.push('Password must contain at least one digit');
        }
        
        if (this.options.requireSpecial && !new RegExp(`[${this.escapeRegex(this.options.specialChars)}]`).test(password)) {
            errors.push('Password must contain at least one special character');
        }
        
        return {
            valid: errors.length === 0,
            errors,
            strength: this.calculatePasswordStrength(password)
        };
    }
}

// Initialize password manager when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Auto-initialize if no other instance is created
    if (!window.passwordManager) {
        window.passwordManager = new PasswordManager();
    }
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PasswordManager;
}
