/**
 * Prompt Caching Demo - Frontend Application
 * Educational demonstration of Amazon Bedrock prompt caching optimization
 * 
 * This application showcases:
 * - Real-time prompt caching demonstrations
 * - Token reduction and latency improvements
 * - Interactive architecture visualization
 * - Query history management with cache metrics
 */

class PromptCachingDemo {
    constructor() {
        // Configuration - API Gateway URL will be injected at deployment
        this.config = {
            apiBaseUrl: window.API_GATEWAY_URL || 'https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/prod',
            maxQuestionLength: 500,
            defaultModel: 'amazon.nova-lite-v1:0'
        };

        // State management
        this.state = {
            isProcessing: false,
            currentQuestion: '',
            currentModel: this.config.defaultModel,
            uploadedDocument: null,
            uploadedFileName: null,
            lastResponse: null,
            queryHistory: []
        };

        // Initialize the application
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        console.log('Prompt Caching Demo - Initializing...');
        
        this.bindEventListeners();
        this.initializeUI();
        this.loadHistoryFromStorage();
        
        console.log('Prompt Caching Demo - Ready');
        this.showToast('💾 Prompt Caching Demo ready! Submit a question to see caching in action', 'info', 5000);
    }

    /**
     * Bind event listeners to UI elements
     */
    bindEventListeners() {
        // Question input
        const questionInput = document.getElementById('questionInput');
        questionInput.addEventListener('input', (e) => {
            this.updateCharCounter(e.target.value.length);
            this.state.currentQuestion = e.target.value;
        });

        // Model selector
        const modelSelect = document.getElementById('modelSelect');
        modelSelect.addEventListener('change', (e) => {
            this.state.currentModel = e.target.value;
        });

        // Submit button
        const submitBtn = document.getElementById('submitBtn');
        submitBtn.addEventListener('click', () => this.submitQuery());

        // Enter key in textarea
        questionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.submitQuery();
            }
        });

        // Clear history button
        const clearHistoryBtn = document.getElementById('clearHistory');
        clearHistoryBtn.addEventListener('click', () => this.clearHistory());

        // File upload button
        const uploadBtn = document.getElementById('uploadBtn');
        const documentUpload = document.getElementById('documentUpload');
        uploadBtn.addEventListener('click', () => documentUpload.click());

        // File input change
        documentUpload.addEventListener('change', (e) => this.handleFileUpload(e));

        // Clear file button
        const clearFileBtn = document.getElementById('clearFileBtn');
        clearFileBtn.addEventListener('click', () => this.clearUploadedFile());

        // Copy response button
        const copyResponseBtn = document.getElementById('copyResponseBtn');
        copyResponseBtn.addEventListener('click', () => this.copyResponseToClipboard());
    }

    /**
     * Initialize UI state
     */
    initializeUI() {
        this.updateCharCounter(0);
        this.updateHistoryDisplay();
    }

    /**
     * Update character counter
     */
    updateCharCounter(count) {
        const charCount = document.getElementById('charCount');
        charCount.textContent = count;
        
        if (count > this.config.maxQuestionLength) {
            charCount.style.color = 'var(--error-color)';
        } else if (count > this.config.maxQuestionLength * 0.9) {
            charCount.style.color = 'var(--warning-color)';
        } else {
            charCount.style.color = 'var(--text-secondary)';
        }
    }

    /**
     * Handle file upload
     */
    async handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Validate file size (max 100KB)
        const maxSize = 100 * 1024; // 100KB
        if (file.size > maxSize) {
            this.showToast('File size exceeds 100KB limit', 'error');
            event.target.value = '';
            return;
        }

        // Validate file type
        const allowedTypes = ['text/plain', 'text/markdown', 'application/pdf', 
                             'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
        const allowedExtensions = ['.txt', '.md', '.pdf', '.doc', '.docx'];
        const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
        
        if (!allowedExtensions.includes(fileExtension)) {
            this.showToast('Please upload a .txt, .md, .pdf, .doc, or .docx file', 'error');
            event.target.value = '';
            return;
        }

        try {
            // Read file content
            const content = await this.readFileContent(file);
            
            // Validate content length
            if (content.length < 100) {
                this.showToast('Document must be at least 100 characters', 'error');
                event.target.value = '';
                return;
            }

            // Store document
            this.state.uploadedDocument = content;
            this.state.uploadedFileName = file.name;

            // Update UI
            const fileName = document.getElementById('fileName');
            fileName.textContent = file.name;
            fileName.classList.add('has-file');

            const clearFileBtn = document.getElementById('clearFileBtn');
            clearFileBtn.style.display = 'inline-block';

            this.showToast(`✓ Document uploaded: ${file.name}`, 'success');

        } catch (error) {
            console.error('File upload error:', error);
            this.showToast('Failed to read file: ' + error.message, 'error');
            event.target.value = '';
        }
    }

    /**
     * Read file content
     */
    readFileContent(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            
            reader.onload = (e) => {
                try {
                    let content = e.target.result;
                    
                    // For PDF and DOC files, we'll just send the base64
                    // The backend would need additional processing for these
                    if (file.type === 'application/pdf' || 
                        file.type === 'application/msword' || 
                        file.type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
                        this.showToast('Note: PDF and DOC files require text extraction. Please use .txt or .md for best results.', 'warning', 6000);
                        reject(new Error('PDF and DOC files not yet supported. Please use .txt or .md files.'));
                        return;
                    }
                    
                    resolve(content);
                } catch (error) {
                    reject(error);
                }
            };
            
            reader.onerror = () => {
                reject(new Error('Failed to read file'));
            };
            
            // Read as text for text files
            if (file.type.startsWith('text/') || file.name.endsWith('.md') || file.name.endsWith('.txt')) {
                reader.readAsText(file);
            } else {
                // For other files, read as data URL (base64)
                reader.readAsDataURL(file);
            }
        });
    }

    /**
     * Clear uploaded file
     */
    clearUploadedFile() {
        this.state.uploadedDocument = null;
        this.state.uploadedFileName = null;

        const documentUpload = document.getElementById('documentUpload');
        documentUpload.value = '';

        const fileName = document.getElementById('fileName');
        fileName.textContent = 'No file selected (using default 1997 Amazon shareholder letter)';
        fileName.classList.remove('has-file');

        const clearFileBtn = document.getElementById('clearFileBtn');
        clearFileBtn.style.display = 'none';

        this.showToast('Uploaded document cleared', 'info');
    }

    /**
     * Submit query to API
     */
    async submitQuery() {
        const question = this.state.currentQuestion.trim();
        const model = this.state.currentModel;

        // Validate input
        if (!question) {
            this.showToast('Please enter a question', 'warning');
            return;
        }

        if (question.length > this.config.maxQuestionLength) {
            this.showToast(`Question exceeds ${this.config.maxQuestionLength} characters`, 'error');
            return;
        }

        if (this.state.isProcessing) {
            return;
        }

        this.setProcessingState(true);
        this.showProcessingStatus();

        try {
            const startTime = Date.now();

            // Send request to API
            const response = await this.sendQueryRequest(question, model);
            
            const endTime = Date.now();
            const totalTime = ((endTime - startTime) / 1000).toFixed(2);

            console.log('Query response:', response);

            // Hide processing status
            this.hideProcessingStatus();

            // Display results
            this.displayResults(response);

            // Add to history
            this.addToHistory(question, model, response, totalTime);

            this.showToast('✅ Query completed successfully!', 'success');

        } catch (error) {
            console.error('Query failed:', error);
            this.hideProcessingStatus();
            this.handleQueryError(error);
        } finally {
            this.setProcessingState(false);
        }
    }

    /**
     * Send query request to API
     */
    async sendQueryRequest(question, model) {
        const requestBody = {
            question: question,
            model: model
        };

        // Include uploaded document if available
        if (this.state.uploadedDocument) {
            requestBody.document = this.state.uploadedDocument;
        }

        const response = await fetch(`${this.config.apiBaseUrl}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}: ${response.statusText}`);
        }

        return await response.json();
    }

    /**
     * Set processing state
     */
    setProcessingState(isProcessing) {
        this.state.isProcessing = isProcessing;

        const submitBtn = document.getElementById('submitBtn');
        const btnText = submitBtn.querySelector('.btn-text');
        const spinner = submitBtn.querySelector('.loading-spinner');
        const questionInput = document.getElementById('questionInput');
        const modelSelect = document.getElementById('modelSelect');

        if (isProcessing) {
            btnText.textContent = 'Processing...';
            spinner.style.display = 'block';
            submitBtn.disabled = true;
            questionInput.disabled = true;
            modelSelect.disabled = true;
        } else {
            btnText.textContent = 'Submit Query';
            spinner.style.display = 'none';
            submitBtn.disabled = false;
            questionInput.disabled = false;
            modelSelect.disabled = false;
        }
    }

    /**
     * Show processing status
     */
    showProcessingStatus() {
        const statusContainer = document.getElementById('processingStatus');
        statusContainer.style.display = 'block';
    }

    /**
     * Hide processing status
     */
    hideProcessingStatus() {
        const statusContainer = document.getElementById('processingStatus');
        statusContainer.style.display = 'none';
    }

    /**
     * Display query results
     */
    displayResults(response) {
        const resultsSection = document.getElementById('resultsSection');
        resultsSection.style.display = 'block';

        // Store response
        this.state.lastResponse = response;

        // Hide previous warnings/indicators
        const eligibilityContainer = document.getElementById('documentEligibility');
        const cacheMissContainer = document.getElementById('cacheMissWarning');
        if (eligibilityContainer) eligibilityContainer.style.display = 'none';
        if (cacheMissContainer) cacheMissContainer.style.display = 'none';

        // Display document eligibility info
        if (response.document_info) {
            this.displayDocumentEligibility(response.document_info);
        }

        // Display cache miss warning if applicable
        if (response.cache_hit && response.cache_hit.cache_read_tokens === 0) {
            this.displayCacheMissWarning();
        }

        // Display metrics summary
        this.displayMetricsSummary(response.metrics);

        // Display detailed comparison
        this.displayComparison(response);

        // Display AI response
        this.displayAIResponse(response.cache_hit.content || response.baseline.content);

        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * Display document eligibility information
     */
    displayDocumentEligibility(documentInfo) {
        const eligibilityContainer = document.getElementById('documentEligibility');
        if (!eligibilityContainer) return;

        const { estimated_tokens, meets_minimum, minimum_required, source } = documentInfo;

        const sourceLabel = source === 'uploaded' ? '📄 Uploaded Document' : 
                           source === 'fallback' ? '📋 Fallback Content' : 
                           '📁 Default 1997 Amazon Shareholder Letter';

        if (meets_minimum) {
            eligibilityContainer.innerHTML = `
                <div class="eligibility-indicator success">
                    <span class="indicator-icon">✓</span>
                    <div class="indicator-content">
                        <strong>Document Eligible for Caching</strong>
                        <p>Document has ~${estimated_tokens.toLocaleString()} tokens (minimum: ${minimum_required.toLocaleString()})</p>
                        <p class="source-note">${sourceLabel}</p>
                    </div>
                </div>
            `;
        } else {
            eligibilityContainer.innerHTML = `
                <div class="eligibility-indicator warning">
                    <span class="indicator-icon">⚠</span>
                    <div class="indicator-content">
                        <strong>Document Below Minimum Token Requirement</strong>
                        <p>Document has ~${estimated_tokens.toLocaleString()} tokens, but needs ${minimum_required.toLocaleString()} tokens for effective caching.</p>
                        <p class="warning-note">Caching may not be effective with documents below the minimum token requirement.</p>
                        <p class="source-note">${sourceLabel}</p>
                    </div>
                </div>
            `;
        }

        eligibilityContainer.style.display = 'block';
    }

    /**
     * Display cache miss warning
     */
    displayCacheMissWarning() {
        const cacheMissContainer = document.getElementById('cacheMissWarning');
        if (!cacheMissContainer) return;

        cacheMissContainer.innerHTML = `
            <div class="cache-miss-warning">
                <span class="warning-icon">ℹ</span>
                <div class="warning-content">
                    <strong>Cache Miss Detected</strong>
                    <p>The cache hit request did not read from cache (cache_read_tokens = 0).</p>
                    <p><strong>Possible reasons:</strong></p>
                    <ul>
                        <li>Cache expired (5-minute TTL from last use)</li>
                        <li>Document content changed between requests</li>
                        <li>Model doesn't support caching for this content</li>
                        <li>Cache checkpoint not properly configured</li>
                    </ul>
                </div>
            </div>
        `;

        cacheMissContainer.style.display = 'block';
    }

    /**
     * Display metrics summary
     */
    displayMetricsSummary(metrics) {
        document.getElementById('tokenReduction').textContent = 
            metrics.token_reduction_percent.toFixed(1) + '%';
        
        document.getElementById('latencyImprovement').textContent = 
            metrics.latency_improvement_percent.toFixed(1) + '%';
        
        document.getElementById('cacheHitRatio').textContent = 
            metrics.cache_hit_ratio.toFixed(1) + '%';
    }

    /**
     * Display detailed comparison
     */
    displayComparison(response) {
        // Baseline metrics
        document.getElementById('baselineInputTokens').textContent = 
            response.baseline.input_tokens.toLocaleString();
        document.getElementById('baselineOutputTokens').textContent = 
            response.baseline.output_tokens.toLocaleString();
        document.getElementById('baselineResponseTime').textContent = 
            response.baseline.response_time.toFixed(2) + 's';

        // Cache write metrics
        document.getElementById('cacheWriteInputTokens').textContent = 
            response.cache_write.input_tokens.toLocaleString();
        document.getElementById('cacheWriteTokens').textContent = 
            response.cache_write.cache_write_tokens.toLocaleString();
        document.getElementById('cacheWriteResponseTime').textContent = 
            response.cache_write.response_time.toFixed(2) + 's';

        // Cache hit metrics
        document.getElementById('cacheHitInputTokens').textContent = 
            response.cache_hit.input_tokens.toLocaleString();
        document.getElementById('cacheReadTokens').textContent = 
            response.cache_hit.cache_read_tokens.toLocaleString();
        document.getElementById('cacheHitResponseTime').textContent = 
            response.cache_hit.response_time.toFixed(2) + 's';
    }

    /**
     * Display AI response content with formatting
     */
    displayAIResponse(content) {
        const responseContent = document.getElementById('aiResponseContent');
        
        // Store raw content for copying
        this.state.lastResponseContent = content;
        
        // Format the content with better typography
        const formattedContent = this.formatResponseContent(content);
        responseContent.innerHTML = formattedContent;
        
        // Show copy button
        const copyBtn = document.getElementById('copyResponseBtn');
        if (copyBtn) {
            copyBtn.style.display = 'flex';
        }
    }

    /**
     * Copy response to clipboard
     */
    async copyResponseToClipboard() {
        const content = this.state.lastResponseContent;
        if (!content) {
            this.showToast('No response to copy', 'warning');
            return;
        }

        try {
            await navigator.clipboard.writeText(content);
            this.showToast('✓ Response copied to clipboard!', 'success');
        } catch (error) {
            console.error('Failed to copy:', error);
            this.showToast('Failed to copy response', 'error');
        }
    }

    /**
     * Format response content with markdown-like styling
     */
    formatResponseContent(text) {
        if (!text) return '';
        
        // Escape HTML to prevent XSS
        let formatted = this.escapeHtml(text);
        
        // Convert markdown-style bold (**text** or __text__)
        formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/__(.+?)__/g, '<strong>$1</strong>');
        
        // Convert markdown-style italic (*text* or _text_)
        formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/_(.+?)_/g, '<em>$1</em>');
        
        // Convert code blocks (```code```)
        formatted = formatted.replace(/```([\s\S]+?)```/g, '<pre><code>$1</code></pre>');
        
        // Convert inline code (`code`)
        formatted = formatted.replace(/`(.+?)`/g, '<code>$1</code>');
        
        // Convert bullet points (lines starting with - or * or •)
        formatted = formatted.replace(/^[\-\*•]\s+(.+)$/gm, '<li>$1</li>');
        
        // Wrap consecutive list items in <ul>
        formatted = formatted.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
            return '<ul>' + match + '</ul>';
        });
        
        // Convert numbered lists (lines starting with 1. 2. etc.)
        formatted = formatted.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
        
        // Wrap consecutive numbered list items in <ol>
        formatted = formatted.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
            // Check if already wrapped in ul
            if (!match.includes('<ul>')) {
                return '<ol>' + match + '</ol>';
            }
            return match;
        });
        
        // Convert headers (## Header or ### Header)
        formatted = formatted.replace(/^###\s+(.+)$/gm, '<h4>$1</h4>');
        formatted = formatted.replace(/^##\s+(.+)$/gm, '<h3>$1</h3>');
        formatted = formatted.replace(/^#\s+(.+)$/gm, '<h3>$1</h3>');
        
        // Convert double line breaks to paragraphs
        const paragraphs = formatted.split(/\n\n+/);
        formatted = paragraphs.map(para => {
            para = para.trim();
            // Don't wrap if already has block-level tags
            if (para.match(/^<(h[1-6]|ul|ol|pre|div)/)) {
                return para;
            }
            // Replace single line breaks with <br> within paragraphs
            para = para.replace(/\n/g, '<br>');
            return para ? `<p>${para}</p>` : '';
        }).join('\n');
        
        return formatted;
    }

    /**
     * Handle query error
     */
    handleQueryError(error) {
        console.error('Query error:', error);
        
        const errorMessage = error.message || 'An error occurred while processing your query';
        this.showToast('❌ ' + errorMessage, 'error', 6000);

        // Display error in results section if visible
        const resultsSection = document.getElementById('resultsSection');
        if (resultsSection.style.display === 'block') {
            const responseContent = document.getElementById('aiResponseContent');
            responseContent.innerHTML = `<div style="color: var(--error-color); padding: 15px; background: #FFEBEE; border-radius: 6px;">
                <strong>Error:</strong> ${errorMessage}
            </div>`;
        }
    }

    /**
     * Add query to history
     */
    addToHistory(question, model, response, totalTime) {
        const historyItem = {
            id: Date.now(),
            timestamp: new Date().toISOString(),
            question: question,
            model: model,
            tokenReduction: response.metrics.token_reduction_percent,
            latencyImprovement: response.metrics.latency_improvement_percent,
            cacheHitRatio: response.metrics.cache_hit_ratio,
            totalTime: totalTime
        };

        this.state.queryHistory.unshift(historyItem);

        // Limit history to 50 items
        if (this.state.queryHistory.length > 50) {
            this.state.queryHistory = this.state.queryHistory.slice(0, 50);
        }

        this.saveHistoryToStorage();
        this.updateHistoryDisplay();
    }

    /**
     * Update history display
     */
    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');

        if (this.state.queryHistory.length === 0) {
            historyList.innerHTML = `
                <div class="history-empty">
                    <p>No queries yet. Submit a question above to get started.</p>
                </div>
            `;
            return;
        }

        historyList.innerHTML = this.state.queryHistory.map(item => `
            <div class="history-item">
                <div class="history-header">
                    <span class="history-timestamp">${new Date(item.timestamp).toLocaleString()}</span>
                </div>
                <div class="history-question">${this.escapeHtml(item.question)}</div>
                <div class="history-metrics">
                    <span class="history-metric highlight">📉 ${item.tokenReduction.toFixed(1)}% token reduction</span>
                    <span class="history-metric">⚡ ${item.latencyImprovement.toFixed(1)}% faster</span>
                    <span class="history-metric">🎯 ${item.cacheHitRatio.toFixed(1)}% cache hit</span>
                    <span class="history-metric">⏱️ ${item.totalTime}s total</span>
                </div>
            </div>
        `).join('');
    }

    /**
     * Clear history
     */
    clearHistory() {
        if (this.state.queryHistory.length === 0) {
            this.showToast('History is already empty', 'info');
            return;
        }

        if (confirm('Are you sure you want to clear the query history?')) {
            this.state.queryHistory = [];
            this.saveHistoryToStorage();
            this.updateHistoryDisplay();
            this.showToast('Query history cleared', 'success');
        }
    }

    /**
     * Save history to localStorage
     */
    saveHistoryToStorage() {
        try {
            localStorage.setItem('promptCachingHistory', JSON.stringify(this.state.queryHistory));
        } catch (error) {
            console.error('Failed to save history to localStorage:', error);
        }
    }

    /**
     * Load history from localStorage
     */
    loadHistoryFromStorage() {
        try {
            const stored = localStorage.getItem('promptCachingHistory');
            if (stored) {
                this.state.queryHistory = JSON.parse(stored);
            }
        } catch (error) {
            console.error('Failed to load history from localStorage:', error);
            this.state.queryHistory = [];
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
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
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
    window.promptCachingDemo = new PromptCachingDemo();
    console.log('Prompt Caching Demo initialized');
});

// Export for potential testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PromptCachingDemo;
}
