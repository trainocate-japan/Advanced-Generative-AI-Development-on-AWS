/**
 * Email Classification Demo - Frontend Application
 * Educational demonstration of serverless email classification with Amazon Bedrock
 * 
 * This application showcases:
 * - File upload with drag-and-drop functionality
 * - Real-time upload progress tracking
 * - Department-based email organization
 * - Interactive architecture visualization
 * - Session history management
 */

class EmailClassificationDemo {
    constructor() {
        // Configuration - API Gateway URL will be injected at deployment
        this.config = {
            apiBaseUrl: window.API_GATEWAY_URL || 'https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/prod',
            maxFileSize: 10 * 1024 * 1024, // 10MB
            allowedExtensions: ['.eml'],
            maxRetries: 3,
            retryDelay: 1000
        };

        // State management
        this.state = {
            isUploading: false,
            selectedFile: null,
            currentDepartment: 'finance',
            departmentEmails: {
                finance: [],
                it: [],
                hr: [],
                operations: [],
                marketing: []
            },
            uploadHistory: [],
            emailCounts: {
                finance: 0,
                it: 0,
                hr: 0,
                operations: 0,
                marketing: 0
            }
        };

        // Initialize the application
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        console.log('Email Classification Demo - Initializing...');
        
        this.bindEventListeners();
        this.initializeUI();
        this.loadHistoryFromStorage();
        this.loadDepartmentEmails();
        
        console.log('Email Classification Demo - Ready');
        this.showToast('📧 Email Classification Demo ready! Upload an EML file to get started', 'info', 5000);
    }

    /**
     * Bind event listeners to UI elements
     */
    bindEventListeners() {
        // File upload elements
        const dropZone = document.getElementById('dropZone');
        const fileInput = document.getElementById('fileInput');
        const browseBtn = document.getElementById('browseBtn');
        const uploadBtn = document.getElementById('uploadBtn');
        const removeFileBtn = document.getElementById('removeFile');

        // Browse button
        browseBtn.addEventListener('click', () => fileInput.click());
        
        // File input change
        fileInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                this.handleFileSelect(e.target.files[0]);
            }
        });

        // Drag and drop
        dropZone.addEventListener('click', (e) => {
            if (e.target === dropZone || e.target.closest('.drop-zone-content')) {
                fileInput.click();
            }
        });

        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('drag-over');
        });

        dropZone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('drag-over');
            
            if (e.dataTransfer.files.length > 0) {
                this.handleFileSelect(e.dataTransfer.files[0]);
            }
        });

        // Upload button
        uploadBtn.addEventListener('click', () => this.uploadFile());

        // Remove file button
        removeFileBtn.addEventListener('click', () => this.clearFileSelection());

        // Department tabs
        const departmentTabs = document.querySelectorAll('.department-tab');
        departmentTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const department = tab.getAttribute('data-department');
                this.selectDepartment(department);
            });
        });

        // Clear history button
        const clearHistoryBtn = document.getElementById('clearHistory');
        clearHistoryBtn.addEventListener('click', () => this.clearHistory());
    }

    /**
     * Initialize UI state
     */
    initializeUI() {
        this.updateDepartmentCounts();
        this.updateHistoryDisplay();
        this.selectDepartment('finance');
    }

    /**
     * Handle file selection
     */
    handleFileSelect(file) {
        console.log('File selected:', file.name);

        // Validate file
        const validation = this.validateFile(file);
        if (!validation.valid) {
            this.showToast(validation.error, 'error');
            return;
        }

        // Store selected file
        this.state.selectedFile = file;

        // Parse EML file to extract metadata
        this.parseEMLFile(file);

        // Show file preview
        this.showFilePreview(file);

        // Enable upload button
        document.getElementById('uploadBtn').disabled = false;
    }

    /**
     * Validate file
     */
    validateFile(file) {
        // Check file extension
        const fileName = file.name.toLowerCase();
        const hasValidExtension = this.config.allowedExtensions.some(ext => fileName.endsWith(ext));
        
        if (!hasValidExtension) {
            return {
                valid: false,
                error: 'Invalid file format. Please upload an EML file.'
            };
        }

        // Check file size
        if (file.size > this.config.maxFileSize) {
            return {
                valid: false,
                error: `File size exceeds ${this.config.maxFileSize / (1024 * 1024)}MB limit.`
            };
        }

        return { valid: true };
    }

    /**
     * Parse EML file to extract metadata
     */
    async parseEMLFile(file) {
        try {
            const text = await file.text();
            
            // Extract sender
            const senderMatch = text.match(/From:\s*(.+)/i);
            const sender = senderMatch ? senderMatch[1].trim() : 'Unknown';
            
            // Extract subject
            const subjectMatch = text.match(/Subject:\s*(.+)/i);
            const subject = subjectMatch ? subjectMatch[1].trim() : 'No Subject';
            
            // Count attachments (look for Content-Disposition: attachment)
            const attachmentMatches = text.match(/Content-Disposition:\s*attachment/gi);
            const attachmentCount = attachmentMatches ? attachmentMatches.length : 0;

            // Update file preview with metadata
            document.getElementById('fileSender').textContent = `From: ${sender}`;
            document.getElementById('fileSubject').textContent = `Subject: ${subject}`;
            
        } catch (error) {
            console.error('Error parsing EML file:', error);
        }
    }

    /**
     * Show file preview
     */
    showFilePreview(file) {
        const dropZone = document.getElementById('dropZone');
        const filePreview = document.getElementById('filePreview');
        
        // Hide drop zone content
        dropZone.querySelector('.drop-zone-content').style.display = 'none';
        
        // Show file preview
        filePreview.style.display = 'block';
        
        // Update file info
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = this.formatFileSize(file.size);
    }

    /**
     * Clear file selection
     */
    clearFileSelection() {
        this.state.selectedFile = null;
        
        const dropZone = document.getElementById('dropZone');
        const filePreview = document.getElementById('filePreview');
        const fileInput = document.getElementById('fileInput');
        
        // Reset file input
        fileInput.value = '';
        
        // Show drop zone content
        dropZone.querySelector('.drop-zone-content').style.display = 'flex';
        
        // Hide file preview
        filePreview.style.display = 'none';
        
        // Disable upload button
        document.getElementById('uploadBtn').disabled = true;
    }

    /**
     * Upload file to API
     */
    async uploadFile() {
        if (!this.state.selectedFile || this.state.isUploading) {
            return;
        }

        this.setUploadingState(true);
        this.showUploadProgress(0, 'Preparing upload...');

        try {
            const startTime = Date.now();

            // Create FormData for multipart upload
            const formData = new FormData();
            formData.append('file', this.state.selectedFile);

            // Upload file with progress tracking
            const response = await this.uploadWithProgress(formData);
            
            const endTime = Date.now();
            const processingTime = ((endTime - startTime) / 1000).toFixed(2);

            console.log('Upload response:', response);

            // Show success
            this.showUploadProgress(100, 'Upload complete!');
            
            // Display result
            this.displayUploadResult(response, processingTime);

            // Add to history
            this.addToHistory(this.state.selectedFile.name, response, processingTime);

            // Clear file selection
            setTimeout(() => {
                this.clearFileSelection();
                this.hideUploadProgress();
            }, 2000);

            // Refresh department emails after 3 seconds
            setTimeout(() => {
                console.log('Auto-refreshing department emails after upload...');
                this.loadDepartmentEmails();
            }, 3000);

            this.showToast('✅ Email uploaded and queued for classification!', 'success');

        } catch (error) {
            console.error('Upload failed:', error);
            this.handleUploadError(error);
        } finally {
            this.setUploadingState(false);
        }
    }

    /**
     * Upload with progress tracking
     */
    uploadWithProgress(formData) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();

            // Progress tracking
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percentComplete = (e.loaded / e.total) * 100;
                    this.showUploadProgress(percentComplete, 'Uploading...');
                }
            });

            // Load event
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (error) {
                        reject(new Error('Invalid response format'));
                    }
                } else {
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        reject(new Error(errorData.message || `HTTP ${xhr.status}`));
                    } catch {
                        reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                    }
                }
            });

            // Error event
            xhr.addEventListener('error', (e) => {
                console.error('XHR Error Event:', e);
                console.error('XHR Status:', xhr.status);
                console.error('XHR Ready State:', xhr.readyState);
                console.error('XHR Response:', xhr.responseText);
                reject(new Error('Network error occurred'));
            });

            // Timeout event
            xhr.addEventListener('timeout', () => {
                console.error('XHR Timeout');
                reject(new Error('Upload timeout'));
            });

            // Load start event for debugging
            xhr.addEventListener('loadstart', () => {
                console.log('Upload started to:', this.config.apiBaseUrl + '/upload');
            });

            // Open and send
            xhr.open('POST', this.config.apiBaseUrl + '/upload');
            xhr.timeout = 60000; // 60 second timeout
            
            // Log the request details
            console.log('Sending POST request to:', this.config.apiBaseUrl + '/upload');
            console.log('FormData:', formData);
            
            xhr.send(formData);
        });
    }

    /**
     * Show upload progress
     */
    showUploadProgress(percent, status) {
        const progressContainer = document.getElementById('uploadProgress');
        const progressFill = document.getElementById('progressFill');
        const progressStatus = document.getElementById('progressStatus');

        progressContainer.style.display = 'block';
        progressFill.style.width = percent + '%';
        progressStatus.textContent = status;
    }

    /**
     * Hide upload progress
     */
    hideUploadProgress() {
        const progressContainer = document.getElementById('uploadProgress');
        progressContainer.style.display = 'none';
    }

    /**
     * Display upload result
     */
    displayUploadResult(response, processingTime) {
        const resultsSection = document.getElementById('resultsSection');
        resultsSection.style.display = 'block';

        // Update result metadata
        document.getElementById('resultDepartment').textContent = response.department || 'Processing...';
        document.getElementById('resultProcessingTime').textContent = processingTime + 's';
        document.getElementById('resultTimestamp').textContent = new Date().toLocaleString();
        document.getElementById('resultUploadId').textContent = response.uploadId || response.s3Key || 'N/A';

        // Update result message
        const message = response.message || 'Your email has been uploaded and is being processed for classification.';
        document.getElementById('resultMessage').textContent = message;

        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * Handle upload error
     */
    handleUploadError(error) {
        console.error('Upload error:', error);
        
        this.hideUploadProgress();
        
        const errorMessage = error.message || 'An error occurred during upload';
        this.showToast('❌ ' + errorMessage, 'error', 6000);

        // Display error in results section
        const resultsSection = document.getElementById('resultsSection');
        resultsSection.style.display = 'block';

        document.getElementById('resultDepartment').textContent = 'Error';
        document.getElementById('resultProcessingTime').textContent = '--';
        document.getElementById('resultTimestamp').textContent = new Date().toLocaleString();
        document.getElementById('resultUploadId').textContent = '--';
        document.getElementById('resultMessage').textContent = errorMessage;
    }

    /**
     * Set uploading state
     */
    setUploadingState(isUploading) {
        this.state.isUploading = isUploading;

        const uploadBtn = document.getElementById('uploadBtn');
        const btnText = uploadBtn.querySelector('.btn-text');
        const spinner = uploadBtn.querySelector('.loading-spinner');

        if (isUploading) {
            btnText.textContent = 'Uploading...';
            spinner.style.display = 'block';
            uploadBtn.disabled = true;
        } else {
            btnText.textContent = 'Upload & Classify';
            spinner.style.display = 'none';
            uploadBtn.disabled = !this.state.selectedFile;
        }
    }

    /**
     * Select department tab
     */
    selectDepartment(department) {
        this.state.currentDepartment = department;

        // Update tab active state
        document.querySelectorAll('.department-tab').forEach(tab => {
            if (tab.getAttribute('data-department') === department) {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });

        // Load emails for selected department
        this.displayDepartmentEmails(department);
    }

    /**
     * Load department emails from API
     */
    async loadDepartmentEmails() {
        console.log('Loading department emails...');

        // Show loading indicator
        const emailList = document.getElementById('emailList');
        const originalContent = emailList.innerHTML;
        emailList.innerHTML = `
            <div class="email-list-empty">
                <div class="loading-spinner" style="display: inline-block; margin-right: 8px;"></div>
                <p>Loading department emails...</p>
            </div>
        `;

        try {
            // Load emails for all departments
            const departments = ['finance', 'it', 'hr', 'operations', 'marketing'];
            
            for (const dept of departments) {
                const response = await fetch(
                    `${this.config.apiBaseUrl}/departments/${dept}/emails?limit=50`
                );
                
                if (!response.ok) {
                    throw new Error(`Failed to load ${dept} emails: ${response.status}`);
                }
                
                const data = await response.json();
                
                // Update state with email data
                this.state.departmentEmails[dept] = data.emails || [];
                this.state.emailCounts[dept] = data.count || 0;
            }
            
            // Update UI with loaded data
            this.updateDepartmentCounts();
            this.displayDepartmentEmails(this.state.currentDepartment);
            
        } catch (error) {
            console.error('Failed to load department emails:', error);
            this.showToast('Failed to load department emails', 'error');
            // Restore original content on error
            emailList.innerHTML = originalContent;
        }
    }

    /**
     * Display emails for selected department
     */
    displayDepartmentEmails(department) {
        const emailList = document.getElementById('emailList');
        const emails = this.state.departmentEmails[department] || [];

        if (emails.length === 0) {
            emailList.innerHTML = `
                <div class="email-list-empty">
                    <p>No emails in ${this.capitalizeFirst(department)} department yet. Upload an EML file to get started.</p>
                </div>
            `;
            return;
        }

        emailList.innerHTML = emails.map(email => `
            <div class="email-item">
                <div class="email-header">
                    <span class="email-sender">${email.sender}</span>
                    <span class="email-timestamp">${new Date(email.timestamp).toLocaleString()}</span>
                </div>
                <div class="email-subject">${email.subject}</div>
                <div class="email-metadata">
                    <span>📎 ${email.attachmentCount || 0} attachment(s)</span>
                    <span>🏷️ ${this.capitalizeFirst(department)}</span>
                </div>
            </div>
        `).join('');
    }

    /**
     * Update department email counts
     */
    updateDepartmentCounts() {
        Object.keys(this.state.emailCounts).forEach(dept => {
            const count = this.state.departmentEmails[dept]?.length || 0;
            this.state.emailCounts[dept] = count;
            
            const countElement = document.getElementById(dept + 'Count');
            if (countElement) {
                countElement.textContent = count;
            }
        });
    }

    /**
     * Add upload to history
     */
    addToHistory(fileName, response, processingTime) {
        const historyItem = {
            id: Date.now(),
            timestamp: new Date().toISOString(),
            fileName: fileName,
            department: response.department || 'Processing',
            uploadId: response.uploadId || response.s3Key,
            processingTime: processingTime,
            status: 'success'
        };

        this.state.uploadHistory.unshift(historyItem);

        // Limit history to 50 items
        if (this.state.uploadHistory.length > 50) {
            this.state.uploadHistory = this.state.uploadHistory.slice(0, 50);
        }

        this.saveHistoryToStorage();
        this.updateHistoryDisplay();
    }

    /**
     * Update history display
     */
    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');

        if (this.state.uploadHistory.length === 0) {
            historyList.innerHTML = `
                <div class="history-empty">
                    <p>No uploads yet. Start by uploading an EML file above.</p>
                </div>
            `;
            return;
        }

        historyList.innerHTML = this.state.uploadHistory.map(item => `
            <div class="history-item">
                <div class="history-header">
                    <span class="history-timestamp">${new Date(item.timestamp).toLocaleString()}</span>
                    <span class="history-department">${item.department}</span>
                </div>
                <div class="history-filename">${item.fileName}</div>
                <div class="history-details">
                    Processing Time: ${item.processingTime}s | Upload ID: ${this.truncateText(item.uploadId, 30)}
                </div>
            </div>
        `).join('');
    }

    /**
     * Clear history
     */
    clearHistory() {
        if (this.state.uploadHistory.length === 0) {
            this.showToast('History is already empty', 'info');
            return;
        }

        if (confirm('Are you sure you want to clear the upload history?')) {
            this.state.uploadHistory = [];
            this.saveHistoryToStorage();
            this.updateHistoryDisplay();
            this.showToast('Upload history cleared', 'success');
        }
    }

    /**
     * Save history to localStorage
     */
    saveHistoryToStorage() {
        try {
            localStorage.setItem('emailClassificationHistory', JSON.stringify(this.state.uploadHistory));
        } catch (error) {
            console.error('Failed to save history to localStorage:', error);
        }
    }

    /**
     * Load history from localStorage
     */
    loadHistoryFromStorage() {
        try {
            const stored = localStorage.getItem('emailClassificationHistory');
            if (stored) {
                this.state.uploadHistory = JSON.parse(stored);
            }
        } catch (error) {
            console.error('Failed to load history from localStorage:', error);
            this.state.uploadHistory = [];
        }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toastContainer');

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        // Add icon based on type
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        
        const icon = document.createElement('span');
        icon.textContent = icons[type] || 'ℹ';
        icon.style.fontWeight = 'bold';
        icon.style.marginRight = '8px';
        
        const text = document.createElement('span');
        text.textContent = message;
        
        toast.appendChild(icon);
        toast.appendChild(text);

        container.appendChild(toast);

        // Auto-remove after duration
        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, duration);
    }

    /**
     * Format file size
     */
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    /**
     * Truncate text
     */
    truncateText(text, maxLength) {
        if (!text || text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    /**
     * Capitalize first letter
     */
    capitalizeFirst(str) {
        return str.charAt(0).toUpperCase() + str.slice(1);
    }

    /**
     * Utility function for delays
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.emailDemo = new EmailClassificationDemo();
    console.log('Email Classification Demo initialized');
});

// Export for potential testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = EmailClassificationDemo;
}
