/**
 * GenAI Model Selection Demo - Frontend Application
 * Educational demonstration of provider-agnostic GenAI architecture
 * 
 * This application showcases:
 * - Provider-agnostic API interactions
 * - Real-time metrics and monitoring
 * - Session history and analytics
 * - Educational transparency in system behavior
 */

class GenAIDemo {
    constructor() {
        // Configuration
        this.config = {
            apiBaseUrl: 'https://ts3ji30co1.execute-api.us-east-1.amazonaws.com/Prod', // Will be configured for API Gateway
            sessionId: this.generateSessionId(),
            maxRetries: 3,
            retryDelay: 1000
        };

        // State management
        this.state = {
            isLoading: false,
            sessionMetrics: {
                totalQueries: 0,
                totalTokens: 0,
                averageLatency: 0,
                providerDistribution: {
                    anthropic: 0,
                    openai: 0,
                    nova: 0
                }
            },
            queryHistory: [],
            providerStatus: {
                anthropic: { status: 'unknown', latency: 0, successRate: 0 },
                openai: { status: 'unknown', latency: 0, successRate: 0 },
                nova: { status: 'unknown', latency: 0, successRate: 0 }
            },
            failureSimulations: {
                anthropic: false,
                openai: false,
                nova: false
            }
        };

        // Initialize the application
        this.init();
    }

    /**
     * Initialize the application
     */
    init() {
        console.log('GenAI Model Selection Demo - Initializing...');
        
        this.bindEventListeners();
        this.initializeUI();
        this.initializeEducationalFeatures();
        this.checkProviderHealth();
        
        // Set up periodic health checks
        setInterval(() => this.checkProviderHealth(), 30000); // Every 30 seconds
        
        console.log('GenAI Model Selection Demo - Ready');
        this.showToast('🎓 Educational demo ready! Hover over ℹ️ icons for learning tips', 'info', 6000);
    }

    /**
     * Generate a unique session ID
     */
    generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Bind event listeners to UI elements
     */
    bindEventListeners() {
        // Query submission
        const submitBtn = document.getElementById('submitQuery');
        const queryInput = document.getElementById('queryInput');
        
        submitBtn.addEventListener('click', () => this.submitQuery());
        queryInput.addEventListener('input', () => this.validateInput());
        queryInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                this.submitQuery();
            }
        });

        // History management
        const clearHistoryBtn = document.getElementById('clearHistory');
        clearHistoryBtn.addEventListener('click', () => this.clearHistory());

        // Admin panel toggle
        const adminToggle = document.getElementById('toggleAdminPanel');
        adminToggle.addEventListener('click', () => this.toggleAdminPanel());

        // Failure simulation controls
        const anthropicToggle = document.getElementById('simulateAnthropicFailure');
        const openaiToggle = document.getElementById('simulateOpenAIFailure');
        const novaToggle = document.getElementById('simulateNovaFailure');
        const resetSimBtn = document.getElementById('resetSimulations');

        anthropicToggle.addEventListener('change', (e) => this.toggleProviderSimulation('anthropic', e.target.checked));
        openaiToggle.addEventListener('change', (e) => this.toggleProviderSimulation('openai', e.target.checked));
        novaToggle.addEventListener('change', (e) => this.toggleProviderSimulation('nova', e.target.checked));
        resetSimBtn.addEventListener('click', () => this.resetSimulations());
    }

    /**
     * Initialize UI state
     */
    initializeUI() {
        this.updateMetricsDisplay();
        this.validateInput();
        
        // Add helpful placeholder text
        const queryInput = document.getElementById('queryInput');
        queryInput.placeholder = 'Enter your query here... (e.g., "Explain the benefits of cloud computing" or "Write a Python function to sort a list")';
    }

    /**
     * Initialize educational features and interactions
     */
    initializeEducationalFeatures() {
        // Add educational callouts dynamically
        this.addEducationalCallouts();
        
        // Set up educational highlighting
        this.setupEducationalHighlighting();
        
        // Add sample queries for demonstration
        this.addSampleQueries();
        
        // Initialize architecture diagram interactions
        this.initializeArchitectureDiagram();
        
        console.log('Educational features initialized');
    }

    /**
     * Initialize architecture diagram interactions
     */
    initializeArchitectureDiagram() {
        // Add click handlers for architecture components
        const componentBoxes = document.querySelectorAll('.component-box, .provider-box');
        componentBoxes.forEach(box => {
            box.addEventListener('click', (e) => {
                this.handleArchitectureComponentClick(e.target);
            });
        });
        
        // Add educational demonstration mode
        this.addArchitectureDemoMode();
        
        console.log('Architecture diagram interactions initialized');
    }

    /**
     * Handle clicks on architecture diagram components
     */
    handleArchitectureComponentClick(element) {
        // Get the parent group to identify the component
        const parentGroup = element.closest('g');
        if (!parentGroup) return;
        
        const componentId = parentGroup.id;
        let componentInfo = '';
        
        switch (componentId) {
            case 'client-layer':
                componentInfo = 'Web Frontend: The user interface layer that provides a consistent experience regardless of which AI provider processes requests. Built with HTML, CSS, and JavaScript.';
                break;
            case 'cloudfront-layer':
                componentInfo = 'CloudFront: AWS Content Delivery Network that distributes the web application globally for fast loading times and improved user experience.';
                break;
            case 'api-gateway-layer':
                componentInfo = 'API Gateway: Manages all API requests with authentication, rate limiting, and request validation. Provides a single, secure entry point.';
                break;
            case 'lambda-router-layer':
                componentInfo = 'Lambda Router Engine: The core intelligence implementing health monitoring, circuit breakers, and intelligent routing to optimal providers.';
                break;
            case 'bedrock-layer':
                componentInfo = 'AWS Bedrock Converse API: The abstraction layer that provides a unified interface for all AI providers, eliminating provider-specific integration complexity.';
                break;
            case 'anthropic-provider':
                componentInfo = 'Anthropic Claude: Advanced reasoning and analysis capabilities with models optimized for different use cases and performance requirements.';
                break;
            case 'openai-provider':
                componentInfo = 'OpenAI GPT: GPT OSS 120B model provides strong performance across reasoning, coding, and creative tasks with excellent reliability.';
                break;
            case 'nova-provider':
                componentInfo = 'AWS Nova: Cost-effective models optimized for AWS integration with multiple performance and cost options.';
                break;
            case 'monitoring-layer':
                componentInfo = 'CloudWatch: Comprehensive monitoring and logging service providing real-time visibility into system performance and behavior.';
                break;
            default:
                componentInfo = 'Click on different components to learn about their role in the provider-agnostic architecture.';
        }
        
        this.showToast(`🏗️ ${componentInfo}`, 'info', 8000);
        
        // Highlight the clicked component
        element.classList.add('active');
        setTimeout(() => {
            element.classList.remove('active');
        }, 3000);
    }

    /**
     * Add architecture demonstration mode
     */
    addArchitectureDemoMode() {
        // Add demo control button
        const architectureSection = document.querySelector('.architecture-section');
        const demoButton = document.createElement('button');
        demoButton.className = 'demo-flow-btn';
        demoButton.textContent = '▶️ Demonstrate Data Flow';
        demoButton.style.cssText = `
            margin: 15px 0;
            padding: 10px 20px;
            background: var(--info-color);
            color: white;
            border: none;
            border-radius: var(--border-radius);
            font-weight: 600;
            cursor: pointer;
            transition: var(--transition);
        `;
        
        demoButton.addEventListener('click', () => {
            this.demonstrateArchitectureFlow();
        });
        
        demoButton.addEventListener('mouseover', () => {
            demoButton.style.background = '#1976D2';
            demoButton.style.transform = 'translateY(-1px)';
        });
        
        demoButton.addEventListener('mouseout', () => {
            demoButton.style.background = 'var(--info-color)';
            demoButton.style.transform = 'translateY(0)';
        });
        
        architectureSection.querySelector('.section-header').appendChild(demoButton);
    }

    /**
     * Demonstrate complete architecture flow
     */
    demonstrateArchitectureFlow() {
        this.showToast('🎬 Demonstrating complete request flow through provider-agnostic architecture...', 'info', 3000);
        
        const steps = [
            { selector: '#client-layer .component-box', message: '1️⃣ User submits query through web interface' },
            { selector: '#cloudfront-layer .component-box', message: '2️⃣ CloudFront delivers optimized content globally' },
            { selector: '#api-gateway-layer .component-box', message: '3️⃣ API Gateway validates and routes request' },
            { selector: '#lambda-router-layer .component-box', message: '4️⃣ Router analyzes request and selects optimal provider' },
            { selector: '#bedrock-layer .component-box', message: '5️⃣ Bedrock Converse API abstracts provider differences' },
            { selector: '#anthropic-provider .provider-box, #openai-provider .provider-box, #nova-provider .provider-box', message: '6️⃣ AI provider processes request (Anthropic, OpenAI, or Nova)' },
            { selector: '#monitoring-layer .component-box', message: '📊 CloudWatch monitors entire flow for observability' }
        ];
        
        steps.forEach((step, index) => {
            setTimeout(() => {
                // Highlight components
                const elements = document.querySelectorAll(step.selector);
                elements.forEach(el => el.classList.add('active'));
                
                // Show step message
                this.showToast(step.message, 'info', 2500);
                
                // Remove highlight after delay
                setTimeout(() => {
                    elements.forEach(el => el.classList.remove('active'));
                }, 2000);
                
            }, index * 1500);
        });
        
        // Final message
        setTimeout(() => {
            this.showToast('✨ Complete! This demonstrates how provider-agnostic architecture maintains consistent behavior regardless of which AI service processes the request.', 'success', 6000);
        }, steps.length * 1500);
    }

    /**
     * Add educational callout boxes to sections
     */
    addEducationalCallouts() {
        // Add callout to query section
        const querySection = document.querySelector('.query-section');
        const queryCallout = document.createElement('div');
        queryCallout.className = 'educational-callout';
        queryCallout.innerHTML = `
            <h4>🔍 What to Watch For</h4>
            <p>Notice how the same interface works regardless of which provider processes your request. This demonstrates the power of abstraction in system design!</p>
        `;
        querySection.appendChild(queryCallout);

        // Add callout to provider status section
        const providerSection = document.querySelector('.provider-status-section');
        const providerCallout = document.createElement('div');
        providerCallout.className = 'educational-callout';
        providerCallout.innerHTML = `
            <h4>⚡ Intelligent Routing</h4>
            <p>The system continuously monitors provider health and automatically routes requests to the best available option. Watch the status indicators change in real-time!</p>
        `;
        providerSection.appendChild(providerCallout);

        // Add callout to metrics section
        const metricsSection = document.querySelector('.metrics-section');
        const metricsCallout = document.createElement('div');
        metricsCallout.className = 'educational-callout';
        metricsCallout.innerHTML = `
            <h4>📈 Load Balancing in Action</h4>
            <p>Observe how queries are distributed across providers. The system balances load while considering factors like performance, cost, and availability.</p>
        `;
        metricsSection.appendChild(metricsCallout);
    }

    /**
     * Set up educational highlighting effects
     */
    setupEducationalHighlighting() {
        // Highlight provider cards when they're selected
        this.originalHighlightActiveProvider = this.highlightActiveProvider;
        this.highlightActiveProvider = (provider) => {
            this.originalHighlightActiveProvider(provider);
            
            // Add educational highlighting
            const providerCard = document.querySelector(`[data-provider="${provider.toLowerCase()}"]`);
            if (providerCard) {
                providerCard.classList.add('educational-highlight');
                
                // Show educational toast
                this.showToast(`🎯 Routing Decision: ${provider} selected based on health and performance metrics`, 'info', 5000);
                
                // Remove highlight after animation
                setTimeout(() => {
                    providerCard.classList.remove('educational-highlight');
                }, 4000);
            }
        };
    }

    /**
     * Add sample queries for educational demonstration
     */
    addSampleQueries() {
        const sampleQueries = [
            "Explain AWS Bedrock's LLM-as-Judge evaluation methodology and its advantages",
            "How do RPS, tokens per second, and concurrent users relate to throughput analysis?",
            "Describe how serverless architecture with Lambda and API Gateway enables automatic fallback",
            "What metrics are important for foundation model throughput analysis in enterprise deployments?",
            "How does AWS Bedrock's evaluation framework assess response quality, accuracy, and bias?"
        ];

        // Add sample query buttons
        const querySection = document.querySelector('.query-input-container');
        const sampleContainer = document.createElement('div');
        sampleContainer.className = 'sample-queries';
        sampleContainer.innerHTML = `
            <div class="sample-header">
                <span>💡 Try these sample queries:</span>
            </div>
            <div class="sample-buttons">
                ${sampleQueries.map(query => 
                    `<button class="sample-btn" data-query="${query}">${query}</button>`
                ).join('')}
            </div>
        `;

        querySection.appendChild(sampleContainer);

        // Add event listeners for sample queries
        sampleContainer.addEventListener('click', (e) => {
            if (e.target.classList.contains('sample-btn')) {
                const query = e.target.getAttribute('data-query');
                document.getElementById('queryInput').value = query;
                this.validateInput();
                this.showToast('Sample query loaded - click Submit to see provider-agnostic routing in action!', 'info');
            }
        });
    }

    /**
     * Validate input and enable/disable submit button
     */
    validateInput() {
        const queryInput = document.getElementById('queryInput');
        const submitBtn = document.getElementById('submitQuery');
        
        const isValid = queryInput.value.trim().length > 0 && !this.state.isLoading;
        submitBtn.disabled = !isValid;
        
        // Update character count (optional enhancement)
        const charCount = queryInput.value.length;
        if (charCount > 1800) {
            queryInput.style.borderColor = 'var(--warning-color)';
        } else {
            queryInput.style.borderColor = '';
        }
    }

    /**
     * Submit a query to the GenAI system
     */
    async submitQuery() {
        if (this.state.isLoading) return;

        const queryInput = document.getElementById('queryInput');
        const query = queryInput.value.trim();
        
        if (!query) {
            this.showToast('Please enter a query', 'warning');
            return;
        }

        this.setLoadingState(true);
        
        try {
            const requestData = {
                query: query,
                sessionId: this.config.sessionId,
                maxTokens: parseInt(document.getElementById('maxTokens').value),
                temperature: parseFloat(document.getElementById('temperature').value),
                timestamp: new Date().toISOString()
            };

            console.log('Submitting query:', requestData);
            
            const startTime = Date.now();
            const response = await this.makeAPIRequest('/query', 'POST', requestData);
            const endTime = Date.now();
            
            // Calculate actual latency (including network time)
            const totalLatency = endTime - startTime;
            
            // Process the response
            this.handleQueryResponse(response, query, totalLatency);
            
            // Clear the input
            queryInput.value = '';
            this.validateInput();
            
        } catch (error) {
            console.error('Query submission failed:', error);
            this.handleQueryError(error, query);
        } finally {
            this.setLoadingState(false);
        }
    }

    /**
     * Handle successful query response
     */
    handleQueryResponse(response, originalQuery, totalLatency) {
        console.log('Query response received:', response);
        
        // Update response display
        this.displayResponse(response);
        
        // Update session metrics
        this.updateSessionMetrics(response, totalLatency);
        
        // Add to history
        this.addToHistory(originalQuery, response, totalLatency);
        
        // Highlight active provider
        this.highlightActiveProvider(response.metadata.provider);
        
        this.showToast(`Query processed by ${response.metadata.provider}`, 'success');
    }

    /**
     * Handle query errors
     */
    handleQueryError(error, originalQuery) {
        console.error('Query error:', error);
        
        let errorMessage = 'An error occurred while processing your query';
        
        if (error.message) {
            errorMessage = error.message;
        } else if (error.error && error.error.message) {
            errorMessage = error.error.message;
        }
        
        // Display error in response section
        this.displayError(errorMessage);
        
        // Add error to history
        this.addErrorToHistory(originalQuery, errorMessage);
        
        this.showToast(errorMessage, 'error');
    }

    /**
     * Display query response in the UI
     */
    displayResponse(response) {
        const responseSection = document.querySelector('.response-section');
        responseSection.style.display = 'block';
        
        // Update metadata
        document.getElementById('responseProvider').textContent = response.metadata.provider;
        document.getElementById('responseModel').textContent = response.metadata.model;
        document.getElementById('responseTokens').textContent = response.metadata.tokensUsed;
        document.getElementById('responseLatency').textContent = response.metadata.latencyMs + 'ms';
        document.getElementById('responseTimestamp').textContent = new Date(response.metadata.timestamp).toLocaleString();
        
        // Update response text
        document.getElementById('responseText').textContent = response.response;
        
        // Scroll to response
        responseSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * Display error in the response section
     */
    displayError(errorMessage) {
        const responseSection = document.querySelector('.response-section');
        responseSection.style.display = 'block';
        
        // Clear metadata
        document.getElementById('responseProvider').textContent = 'Error';
        document.getElementById('responseModel').textContent = '--';
        document.getElementById('responseTokens').textContent = '--';
        document.getElementById('responseLatency').textContent = '--';
        document.getElementById('responseTimestamp').textContent = new Date().toLocaleString();
        
        // Display error message
        document.getElementById('responseText').textContent = `Error: ${errorMessage}`;
        document.getElementById('responseText').style.color = 'var(--error-color)';
        
        // Scroll to response
        responseSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    /**
     * Update session metrics
     */
    updateSessionMetrics(response, totalLatency) {
        const metrics = this.state.sessionMetrics;
        
        metrics.totalQueries++;
        metrics.totalTokens += response.metadata.tokensUsed;
        
        // Update average latency
        const currentAvg = metrics.averageLatency;
        metrics.averageLatency = Math.round(
            (currentAvg * (metrics.totalQueries - 1) + response.metadata.latencyMs) / metrics.totalQueries
        );
        
        // Update provider distribution
        const provider = response.metadata.provider.toLowerCase();
        if (metrics.providerDistribution[provider] !== undefined) {
            metrics.providerDistribution[provider]++;
        }
        
        this.updateMetricsDisplay();
    }

    /**
     * Update metrics display in the UI
     */
    updateMetricsDisplay() {
        const metrics = this.state.sessionMetrics;
        
        document.getElementById('totalQueries').textContent = metrics.totalQueries;
        document.getElementById('avgLatency').textContent = metrics.averageLatency > 0 ? 
            metrics.averageLatency + 'ms' : '--ms';
        document.getElementById('totalTokens').textContent = metrics.totalTokens;
        
        // Update provider distribution
        const distributionItems = document.querySelectorAll('.distribution-item .provider-count');
        distributionItems[0].textContent = metrics.providerDistribution.anthropic;
        distributionItems[1].textContent = metrics.providerDistribution.openai;
        distributionItems[2].textContent = metrics.providerDistribution.nova;
    }

    /**
     * Add query to session history
     */
    addToHistory(query, response, totalLatency) {
        const historyItem = {
            id: Date.now(),
            timestamp: new Date(),
            query: query,
            response: response.response,
            provider: response.metadata.provider,
            model: response.metadata.model,
            tokens: response.metadata.tokensUsed,
            latency: response.metadata.latencyMs,
            totalLatency: totalLatency
        };
        
        this.state.queryHistory.unshift(historyItem); // Add to beginning
        
        // Limit history to 50 items
        if (this.state.queryHistory.length > 50) {
            this.state.queryHistory = this.state.queryHistory.slice(0, 50);
        }
        
        this.updateHistoryDisplay();
    }

    /**
     * Add error to session history
     */
    addErrorToHistory(query, errorMessage) {
        const historyItem = {
            id: Date.now(),
            timestamp: new Date(),
            query: query,
            error: errorMessage,
            provider: 'Error',
            model: '--',
            tokens: 0,
            latency: 0,
            totalLatency: 0
        };
        
        this.state.queryHistory.unshift(historyItem);
        this.updateHistoryDisplay();
    }

    /**
     * Update history display in the UI
     */
    updateHistoryDisplay() {
        const historyList = document.getElementById('historyList');
        
        if (this.state.queryHistory.length === 0) {
            historyList.innerHTML = `
                <div class="history-empty">
                    <p>No queries submitted yet. Start by entering a query above.</p>
                </div>
            `;
            return;
        }
        
        historyList.innerHTML = this.state.queryHistory.map(item => `
            <div class="history-item">
                <div class="history-header">
                    <span class="history-timestamp">${item.timestamp.toLocaleString()}</span>
                    <span class="history-provider ${item.error ? 'error' : ''}">${item.provider}</span>
                </div>
                <div class="history-query">"${this.truncateText(item.query, 100)}"</div>
                ${item.error ? 
                    `<div class="history-error" style="color: var(--error-color); font-size: 0.9rem;">Error: ${item.error}</div>` :
                    `<div class="history-metrics">
                        <span>Model: ${item.model}</span>
                        <span>Tokens: ${item.tokens}</span>
                        <span>Latency: ${item.latency}ms</span>
                        <span>Total: ${item.totalLatency}ms</span>
                    </div>`
                }
            </div>
        `).join('');
    }

    /**
     * Clear session history
     */
    clearHistory() {
        if (this.state.queryHistory.length === 0) {
            this.showToast('History is already empty', 'info');
            return;
        }
        
        if (confirm('Are you sure you want to clear the session history?')) {
            this.state.queryHistory = [];
            this.updateHistoryDisplay();
            this.showToast('Session history cleared', 'success');
        }
    }

    /**
     * Highlight the active provider during query processing
     */
    highlightActiveProvider(provider) {
        // Remove previous highlights
        document.querySelectorAll('.provider-card').forEach(card => {
            card.classList.remove('active');
        });
        
        // Highlight current provider card
        const providerCard = document.querySelector(`[data-provider="${provider.toLowerCase()}"]`);
        if (providerCard) {
            providerCard.classList.add('active');
            
            // Remove highlight after 3 seconds
            setTimeout(() => {
                providerCard.classList.remove('active');
            }, 3000);
        }
        
        // Highlight in architecture diagram
        this.highlightArchitectureFlow(provider);
    }

    /**
     * Highlight data flow in architecture diagram
     */
    highlightArchitectureFlow(provider) {
        // Remove previous highlights
        document.querySelectorAll('.component-box, .provider-box, .flow-line, .provider-line').forEach(element => {
            element.classList.remove('active');
        });
        
        // Highlight the complete flow
        const flowElements = [
            '#client-layer .component-box',
            '#cloudfront-layer .component-box', 
            '#api-gateway-layer .component-box',
            '#lambda-router-layer .component-box',
            '#bedrock-layer .component-box'
        ];
        
        flowElements.forEach((selector, index) => {
            setTimeout(() => {
                const element = document.querySelector(selector);
                if (element) {
                    element.classList.add('active');
                }
            }, index * 200); // Stagger the highlights
        });
        
        // Highlight request flow arrows
        setTimeout(() => {
            document.querySelectorAll('#request-flow .flow-line').forEach(line => {
                line.classList.add('active');
            });
        }, 1000);
        
        // Highlight specific provider
        setTimeout(() => {
            const providerBox = document.querySelector(`#${provider.toLowerCase()}-provider .provider-box`);
            const providerLine = document.querySelector(`#${provider.toLowerCase()}-line`);
            
            if (providerBox) {
                providerBox.classList.add('active');
            }
            if (providerLine) {
                providerLine.classList.add('active');
            }
        }, 1200);
        
        // Clear all highlights after animation
        setTimeout(() => {
            document.querySelectorAll('.component-box, .provider-box, .flow-line, .provider-line').forEach(element => {
                element.classList.remove('active');
            });
        }, 4000);
    }

    /**
     * Check provider health status
     */
    async checkProviderHealth() {
        try {
            console.log('Checking provider health...');
            const healthData = await this.makeAPIRequest('/health', 'GET');
            
            if (healthData && healthData.providers) {
                this.updateProviderStatus(healthData.providers);
            }
        } catch (error) {
            console.error('Health check failed:', error);
            // Set all providers to unknown status
            Object.keys(this.state.providerStatus).forEach(provider => {
                this.state.providerStatus[provider] = {
                    status: 'unknown',
                    latency: 0,
                    successRate: 0
                };
            });
            this.updateProviderStatusDisplay();
        }
    }

    /**
     * Update provider status from health check
     */
    updateProviderStatus(providers) {
        Object.keys(providers).forEach(provider => {
            if (this.state.providerStatus[provider]) {
                this.state.providerStatus[provider] = {
                    status: providers[provider].status,
                    latency: providers[provider].latency || 0,
                    successRate: providers[provider].successRate || 0
                };
            }
        });
        
        this.updateProviderStatusDisplay();
    }

    /**
     * Update provider status display in the UI
     */
    updateProviderStatusDisplay() {
        Object.keys(this.state.providerStatus).forEach(provider => {
            const card = document.querySelector(`[data-provider="${provider}"]`);
            if (!card) return;
            
            const status = this.state.providerStatus[provider];
            const statusIndicator = card.querySelector('.status-indicator');
            const statusText = card.querySelector('.status-text');
            const metrics = card.querySelectorAll('.metric-value');
            
            // Update status indicator
            statusIndicator.setAttribute('data-status', status.status);
            
            // Update status text
            const statusTexts = {
                healthy: 'Healthy',
                degraded: 'Degraded',
                unavailable: 'Unavailable',
                unknown: 'Checking...'
            };
            statusText.textContent = statusTexts[status.status] || 'Unknown';
            
            // Update metrics
            if (metrics.length >= 2) {
                metrics[0].textContent = status.latency > 0 ? status.latency + 'ms' : '--ms';
                metrics[1].textContent = status.successRate > 0 ? Math.round(status.successRate) + '%' : '--%';
            }
        });
        
        // Update architecture diagram
        this.updateArchitectureDiagramStatus();
    }

    /**
     * Update architecture diagram based on provider status
     */
    updateArchitectureDiagramStatus() {
        Object.keys(this.state.providerStatus).forEach(provider => {
            const providerBox = document.querySelector(`#${provider}-provider .provider-box`);
            if (!providerBox) return;
            
            // Remove all status classes
            providerBox.classList.remove('healthy', 'degraded', 'unavailable', 'simulated-failure');
            
            // Check if this provider has simulated failure
            if (this.state.failureSimulations[provider]) {
                providerBox.classList.add('simulated-failure');
            } else {
                // Add status class based on actual health
                const status = this.state.providerStatus[provider].status;
                if (status && status !== 'unknown') {
                    providerBox.classList.add(status);
                }
            }
        });
    }

    /**
     * Toggle admin panel visibility
     */
    toggleAdminPanel() {
        const adminSection = document.querySelector('.admin-section');
        const toggleBtn = document.getElementById('toggleAdminPanel');
        
        if (adminSection.style.display === 'none' || !adminSection.style.display) {
            adminSection.style.display = 'block';
            toggleBtn.textContent = 'Hide Instructor Controls';
            
            // Add educational context
            this.showToast('🎓 Instructor Controls: Use these toggles to simulate provider failures and demonstrate system resilience', 'info', 7000);
            
            // Add educational callout to admin section
            this.addAdminEducationalContent();
            
        } else {
            adminSection.style.display = 'none';
            toggleBtn.textContent = 'Show Instructor Controls';
            
            // Show current simulation status if any are active
            const simStatus = this.getSimulationStatus();
            if (simStatus.hasActiveSimulations) {
                this.showToast(`⚠️ ${simStatus.count} provider simulation(s) still active: ${simStatus.activeProviders.join(', ')}`, 'warning');
            }
        }
    }

    /**
     * Add educational content to admin section
     */
    addAdminEducationalContent() {
        const adminSection = document.querySelector('.admin-section');
        let educationalContent = adminSection.querySelector('.admin-educational-content');
        
        if (!educationalContent) {
            educationalContent = document.createElement('div');
            educationalContent.className = 'admin-educational-content';
            educationalContent.innerHTML = `
                <div class="educational-callout">
                    <h4>🎯 Teaching Objectives</h4>
                    <p><strong>Demonstrate Fault Tolerance:</strong> Toggle provider failures to show how the system automatically routes to healthy providers.</p>
                    <p><strong>Show Circuit Breaker Pattern:</strong> Observe how the system prevents requests to failed providers and recovers when they're restored.</p>
                    <p><strong>Illustrate Graceful Degradation:</strong> Even with multiple provider failures, the system continues to function with available resources.</p>
                </div>
                <div class="simulation-status">
                    <h4>📊 Current Simulation Status</h4>
                    <div id="simulationStatusDisplay">
                        <p>All providers operating normally</p>
                    </div>
                </div>
            `;
            
            adminSection.insertBefore(educationalContent, adminSection.querySelector('.admin-controls'));
        }
        
        this.updateSimulationStatusDisplay();
    }

    /**
     * Update simulation status display
     */
    updateSimulationStatusDisplay() {
        const statusDisplay = document.getElementById('simulationStatusDisplay');
        if (!statusDisplay) return;
        
        const simStatus = this.getSimulationStatus();
        
        if (simStatus.hasActiveSimulations) {
            statusDisplay.innerHTML = `
                <div class="active-simulations">
                    <p style="color: var(--error-color); font-weight: 600;">
                        🚨 Active Simulations: ${simStatus.activeProviders.join(', ')}
                    </p>
                    <p style="font-size: 0.9rem; color: var(--text-secondary);">
                        These providers are artificially marked as unavailable for educational demonstration.
                    </p>
                </div>
            `;
        } else {
            statusDisplay.innerHTML = `
                <p style="color: var(--success-color); font-weight: 600;">
                    ✅ All providers operating normally
                </p>
            `;
        }
    }

    /**
     * Toggle provider failure simulation
     */
    async toggleProviderSimulation(provider, enabled) {
        console.log(`${enabled ? 'Enabling' : 'Disabling'} failure simulation for ${provider}`);
        
        try {
            // Update local state
            this.state.failureSimulations[provider] = enabled;
            
            // Make API call to enable/disable simulation
            const endpoint = `/admin/simulate-failure`;
            const requestData = {
                provider: provider,
                enabled: enabled,
                sessionId: this.config.sessionId
            };
            
            await this.makeAPIRequest(endpoint, 'POST', requestData);
            
            // Update UI to reflect simulation state
            this.updateSimulationDisplay(provider, enabled);
            
            // Show educational toast
            if (enabled) {
                this.showToast(`🚨 Educational Demo: ${provider} failure simulation enabled. Watch how the system routes to other providers!`, 'warning', 6000);
            } else {
                this.showToast(`✅ ${provider} failure simulation disabled. Provider restored to normal operation.`, 'success');
            }
            
            // Trigger immediate health check to show the change
            setTimeout(() => this.checkProviderHealth(), 1000);
            
        } catch (error) {
            console.error(`Failed to toggle simulation for ${provider}:`, error);
            
            // Revert the toggle if API call failed
            const toggle = document.getElementById(`simulate${provider.charAt(0).toUpperCase() + provider.slice(1)}Failure`);
            if (toggle) {
                toggle.checked = !enabled;
            }
            this.state.failureSimulations[provider] = !enabled;
            
            this.showToast(`Failed to ${enabled ? 'enable' : 'disable'} ${provider} simulation: ${error.message}`, 'error');
        }
    }

    /**
     * Update simulation display in the UI
     */
    updateSimulationDisplay(provider, enabled) {
        const providerCard = document.querySelector(`[data-provider="${provider}"]`);
        if (!providerCard) return;
        
        // Add/remove simulation indicator
        let simulationBadge = providerCard.querySelector('.simulation-badge');
        
        if (enabled) {
            if (!simulationBadge) {
                simulationBadge = document.createElement('div');
                simulationBadge.className = 'simulation-badge';
                simulationBadge.textContent = 'SIMULATED FAILURE';
                providerCard.querySelector('.provider-header').appendChild(simulationBadge);
            }
            
            // Add visual styling for simulated failure
            providerCard.classList.add('simulated-failure');
            
            // Update status to unavailable
            const statusIndicator = providerCard.querySelector('.status-indicator');
            statusIndicator.setAttribute('data-status', 'unavailable');
            statusIndicator.querySelector('.status-text').textContent = 'Simulated Failure';
            
        } else {
            if (simulationBadge) {
                simulationBadge.remove();
            }
            
            // Remove visual styling
            providerCard.classList.remove('simulated-failure');
        }
    }

    /**
     * Reset all failure simulations
     */
    async resetSimulations() {
        console.log('Resetting all failure simulations...');
        
        try {
            // Reset all toggles
            const toggles = [
                document.getElementById('simulateAnthropicFailure'),
                document.getElementById('simulateOpenAIFailure'),
                document.getElementById('simulateNovaFailure')
            ];
            
            // Disable all simulations
            const resetPromises = [];
            Object.keys(this.state.failureSimulations).forEach(provider => {
                if (this.state.failureSimulations[provider]) {
                    resetPromises.push(this.toggleProviderSimulation(provider, false));
                }
            });
            
            // Wait for all resets to complete
            await Promise.all(resetPromises);
            
            // Reset toggle switches
            toggles.forEach(toggle => {
                if (toggle) toggle.checked = false;
            });
            
            // Clear all simulation displays
            Object.keys(this.state.failureSimulations).forEach(provider => {
                this.updateSimulationDisplay(provider, false);
                this.state.failureSimulations[provider] = false;
            });
            
            this.showToast('🔄 All failure simulations reset. System restored to normal operation.', 'success');
            
            // Trigger health check to refresh status
            setTimeout(() => this.checkProviderHealth(), 1000);
            
        } catch (error) {
            console.error('Failed to reset simulations:', error);
            this.showToast('Failed to reset some simulations. Please try individual toggles.', 'error');
        }
    }

    /**
     * Get current simulation status for educational display
     */
    getSimulationStatus() {
        const activeSimulations = Object.keys(this.state.failureSimulations)
            .filter(provider => this.state.failureSimulations[provider]);
        
        return {
            hasActiveSimulations: activeSimulations.length > 0,
            activeProviders: activeSimulations,
            count: activeSimulations.length
        };
    }

    /**
     * Set loading state
     */
    setLoadingState(isLoading) {
        this.state.isLoading = isLoading;
        
        const submitBtn = document.getElementById('submitQuery');
        const btnText = submitBtn.querySelector('.btn-text');
        const spinner = submitBtn.querySelector('.loading-spinner');
        
        if (isLoading) {
            btnText.textContent = 'Processing...';
            spinner.style.display = 'block';
            submitBtn.disabled = true;
        } else {
            btnText.textContent = 'Submit Query';
            spinner.style.display = 'none';
            this.validateInput(); // Re-enable if input is valid
        }
    }

    /**
     * Make API request with error handling and retries
     */
    async makeAPIRequest(endpoint, method = 'GET', data = null, retryCount = 0) {
        const url = this.config.apiBaseUrl + endpoint;
        
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json',
                'X-Session-ID': this.config.sessionId
            }
        };
        
        if (data) {
            options.body = JSON.stringify(data);
        }
        
        try {
            console.log(`Making ${method} request to ${url}`, data);
            
            const response = await fetch(url, options);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.message || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const responseData = await response.json();
            console.log('API response:', responseData);
            
            return responseData;
            
        } catch (error) {
            console.error(`API request failed (attempt ${retryCount + 1}):`, error);
            
            // Retry logic for network errors
            if (retryCount < this.config.maxRetries && 
                (error.name === 'TypeError' || error.message.includes('fetch'))) {
                
                console.log(`Retrying in ${this.config.retryDelay}ms...`);
                await this.delay(this.config.retryDelay);
                return this.makeAPIRequest(endpoint, method, data, retryCount + 1);
            }
            
            throw error;
        }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toastContainer');
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        
        container.appendChild(toast);
        
        // Auto-remove after duration
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, duration);
    }

    /**
     * Utility function to truncate text
     */
    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    }

    /**
     * Utility function for delays
     */
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Code samples for educational display
const CODE_SAMPLES = {
    'query-interface': {
        title: 'Query Interface - Provider-Agnostic API Call',
        code: `// Frontend makes identical API calls regardless of provider
async function submitQuery(query) {
    const response = await fetch(API_URL + '/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query: query,
            sessionId: generateSessionId()
        })
    });
    
    const result = await response.json();
    
    // Response format is identical for ALL providers
    console.log('Provider:', result.metadata.provider);  // anthropic, openai, or nova
    console.log('Response:', result.response);
    console.log('Tokens:', result.metadata.tokensUsed);
    
    // Your application code never changes!
    return result;
}
`
    },
    'provider-status': {
        title: 'Health Monitoring - Real-time Provider Status',
        code: `def check_provider_health(provider):
    """
    Continuous health monitoring for intelligent routing
    """
    try:
        # Test provider with lightweight query
        start_time = time.time()
        response = bedrock.converse(
            modelId=get_test_model(provider),
            messages=[{"role": "user", "content": "test"}]
        )
        latency = (time.time() - start_time) * 1000
        
        # Update health metrics
        health_status[provider] = {
            'status': 'healthy',
            'latency': latency,
            'successRate': calculate_success_rate(provider),
            'lastCheck': time.time()
        }
        
        return health_status[provider]
        
    except Exception as e:
        # Mark provider as unhealthy
        health_status[provider] = {
            'status': 'unavailable',
            'error': str(e)
        }
        logger.warning(f"Provider {provider} health check failed")
`
    },
    'lambda-router': {
        title: 'Lambda Router Engine - Intelligent Model Selection',
        code: `"""
Lambda Router Engine - Core Intelligence

This module implements intelligent model selection and routing across
multiple GenAI providers (Anthropic Claude, OpenAI GPT, AWS Nova).

Key Features:
- Health-based routing with circuit breakers
- Load balancing across providers
- Performance-optimized model selection
- Comprehensive error handling
"""

def route_to_optimal_model(query, health_status):
    """
    Select the best model based on:
    1. Provider health and availability
    2. Query characteristics (length, complexity)
    3. Current load distribution
    4. Performance history
    """
    
    # Step 1: Filter healthy models
    healthy_models = [
        model for model in available_models
        if health_status[model.provider] == 'healthy'
    ]
    
    # Step 2: Score each model
    scores = {}
    for model in healthy_models:
        score = calculate_model_score(
            model=model,
            query_length=len(query),
            current_load=get_load(model),
            avg_latency=get_avg_latency(model)
        )
        scores[model] = score
    
    # Step 3: Select best model
    best_model = max(scores, key=scores.get)
    
    logger.info(f"Selected {best_model.name} with score {scores[best_model]}")
    
    return best_model


def calculate_model_score(model, query_length, current_load, avg_latency):
    """
    Calculate model suitability score based on multiple factors
    """
    # Base score from model capabilities
    capability_score = model.max_tokens / 1000
    
    # Adjust for current load (prefer less loaded models)
    load_penalty = current_load * 0.1
    
    # Adjust for performance (prefer faster models)
    latency_penalty = avg_latency / 1000
    
    # Query complexity matching
    if query_length > 1000:
        complexity_bonus = 0.2 if model.tier == 'advanced' else 0
    else:
        complexity_bonus = 0.2 if model.tier == 'fast' else 0
    
    final_score = capability_score - load_penalty - latency_penalty + complexity_bonus
    
    return final_score
`
    },
    'bedrock-adapter': {
        title: 'AWS Bedrock Converse API - Provider Abstraction',
        code: `"""
Bedrock Converse API Adapter - Unified Provider Interface

This adapter provides a single, consistent interface for all GenAI providers
through AWS Bedrock's Converse API, eliminating provider-specific code.

Supported Providers:
- Anthropic Claude (Claude 3 Sonnet)
- OpenAI GPT (GPT OSS 120B)
- AWS Nova (Pro, Lite, Micro)
"""

class BedrockConverseAdapter:
    """
    Unified adapter for all GenAI providers via Bedrock Converse API
    """
    
    def __init__(self, region_name='us-east-1'):
        self.bedrock = boto3.client('bedrock-runtime', region_name=region_name)
        self.models = self._initialize_models()
    
    def invoke_model(self, model_id, messages, max_tokens=1000, temperature=0.7):
        """
        Invoke any model using the unified Converse API
        
        This single method works identically for ALL providers!
        """
        try:
            # Unified API call - same for Anthropic, Meta, and Nova
            response = self.bedrock.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={
                    'maxTokens': max_tokens,
                    'temperature': temperature
                }
            )
            
            # Extract response - same format for all providers
            content = response['output']['message']['content'][0]['text']
            tokens_used = response['usage']['totalTokens']
            
            return ModelResponse(
                content=content,
                tokens_used=tokens_used,
                model_id=model_id,
                provider=self._get_provider(model_id)
            )
            
        except Exception as e:
            logger.error(f"Model invocation failed: {e}")
            raise
    
    def _get_provider(self, model_id):
        """Determine provider from model ID"""
        if 'anthropic' in model_id:
            return 'anthropic'
        elif 'openai' in model_id:
            return 'openai'
        elif 'nova' in model_id:
            return 'nova'
        return 'unknown'


# Example Usage - Same code works for ANY provider!
adapter = BedrockConverseAdapter()

# Works with Anthropic
response = adapter.invoke_model(
    model_id='anthropic.claude-3-haiku-20240307-v1:0',
    messages=[{'role': 'user', 'content': 'Hello!'}]
)

# Works with OpenAI (same code!)
response = adapter.invoke_model(
    model_id='openai.gpt-oss-120b-v1:0',
    messages=[{'role': 'user', 'content': 'Hello!'}]
)

# Works with Nova (same code!)
response = adapter.invoke_model(
    model_id='amazon.nova-pro-v1:0',
    messages=[{'role': 'user', 'content': 'Hello!'}]
)
`
    }
};

// Code viewer functionality
function showCodeModal(componentId) {
    const sample = CODE_SAMPLES[componentId];
    if (!sample) return;
    
    const modal = document.getElementById('codeModal');
    const title = document.getElementById('codeModalTitle');
    const code = document.getElementById('codeModalCode').querySelector('code');
    
    title.textContent = sample.title;
    code.textContent = sample.code;
    
    modal.style.display = 'block';
}

// Close modal when clicking outside
window.onclick = function(event) {
    const modal = document.getElementById('codeModal');
    if (event.target === modal) {
        modal.style.display = 'none';
    }
};

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.genaiDemo = new GenAIDemo();
    
    // Add click handlers for architecture diagram components
    setTimeout(() => {
        // Find all tooltip areas and add click handlers to the Lambda and Bedrock ones
        const tooltipAreas = document.querySelectorAll('.tooltip-area');
        
        tooltipAreas.forEach(area => {
            const tooltip = area.getAttribute('data-tooltip');
            
            // Lambda Router Engine
            if (tooltip && tooltip.includes('Lambda Router Engine')) {
                area.style.cursor = 'pointer';
                area.addEventListener('click', (e) => {
                    console.log('Lambda Router clicked!');
                    e.stopPropagation();
                    showCodeModal('lambda-router');
                });
                console.log('Added click handler to Lambda Router');
            }
            
            // AWS Bedrock Converse API
            if (tooltip && tooltip.includes('AWS Bedrock Converse API')) {
                area.style.cursor = 'pointer';
                area.addEventListener('click', (e) => {
                    console.log('Bedrock Layer clicked!');
                    e.stopPropagation();
                    showCodeModal('bedrock-adapter');
                });
                console.log('Added click handler to Bedrock Layer');
            }
        });
    }, 1000); // Wait for SVG to fully render
});

// Export for potential testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GenAIDemo;
}