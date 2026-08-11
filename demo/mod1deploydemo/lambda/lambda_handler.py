"""
Main Lambda Handler for GenAI Model Selection Demo

This module implements the main AWS Lambda handler that orchestrates the complete
GenAI model selection and routing process. It serves as the central entry point
for the demonstration system, integrating all components including:

1. Unified Bedrock Converse API adapter
2. Intelligent model selection and routing
3. Health monitoring and circuit breaker patterns
4. Comprehensive error handling and logging
5. Educational demonstration features

The handler demonstrates enterprise-grade serverless architecture patterns
while maintaining educational transparency in all operations for classroom
demonstration purposes.

Key educational concepts demonstrated:
- Serverless request/response patterns
- Provider-agnostic API design
- Comprehensive error handling strategies
- Structured logging for observability
- Performance monitoring and metrics collection
"""

import json
import time
import logging
import traceback
from typing import Dict, Any, Optional, List
from dataclasses import asdict
import boto3
from botocore.exceptions import ClientError

# Import our unified components
from bedrock_adapter import (
    BedrockConverseAdapter, ModelProvider, ModelType, ModelResponse,
    ConversationMessage, create_user_message
)
from health_monitor import ModelHealthMonitor, HealthStatus
from router import IntelligentModelRouter, RoutingStrategy, RoutingDecision

# Configure comprehensive logging for educational demonstration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global components (initialized once per Lambda container)
_adapter: Optional[BedrockConverseAdapter] = None
_health_monitor: Optional[ModelHealthMonitor] = None
_router: Optional[IntelligentModelRouter] = None

# Global failure simulation state (persists across invocations in same container)
_simulated_failures: Dict[str, bool] = {
    'anthropic': False,
    'openai': False,
    'nova': False
}


def initialize_components(region_name: str = "us-east-1") -> tuple:
    """
    Initialize all system components with comprehensive error handling.
    
    This function demonstrates the initialization pattern for serverless
    applications, including proper error handling and logging for
    educational purposes.
    
    Args:
        region_name: AWS region for Bedrock service
        
    Returns:
        Tuple of (adapter, health_monitor, router)
        
    Raises:
        RuntimeError: If initialization fails
    """
    global _adapter, _health_monitor, _router
    
    try:
        logger.info("Initializing GenAI model selection system components")
        start_time = time.time()
        
        # Initialize unified Bedrock adapter
        logger.info("Initializing unified Bedrock Converse API adapter")
        _adapter = BedrockConverseAdapter(region_name=region_name)
        
        # Get available models for logging
        available_models = _adapter.get_available_models()
        total_models = sum(len(models) for models in available_models.values())
        logger.info(f"Configured {total_models} models across {len(available_models)} providers:")
        
        for provider, models in available_models.items():
            logger.info(f"  {provider.value}: {len(models)} models")
        
        # Initialize health monitoring system
        logger.info("Initializing health monitoring with circuit breakers")
        _health_monitor = ModelHealthMonitor(_adapter, cache_ttl_seconds=300)
        
        # Initialize intelligent router
        logger.info("Initializing intelligent model router")
        _router = IntelligentModelRouter(_adapter, _health_monitor)
        
        # Log available routing strategies
        strategies = [strategy.value for strategy in RoutingStrategy]
        logger.info(f"Available routing strategies: {', '.join(strategies)}")
        
        initialization_time = (time.time() - start_time) * 1000
        logger.info(f"System initialization completed in {initialization_time:.1f}ms")
        
        return _adapter, _health_monitor, _router
        
    except Exception as e:
        logger.error(f"Failed to initialize system components: {str(e)}")
        logger.error(f"Initialization error traceback: {traceback.format_exc()}")
        raise RuntimeError(f"System initialization failed: {str(e)}")


def get_components() -> tuple:
    """
    Get initialized components, initializing if necessary.
    
    This function implements the lazy initialization pattern common
    in serverless applications, ensuring components are ready when needed.
    
    Returns:
        Tuple of (adapter, health_monitor, router)
    """
    global _adapter, _health_monitor, _router
    
    if not all([_adapter, _health_monitor, _router]):
        logger.info("Components not initialized, performing initialization")
        return initialize_components()
    
    return _adapter, _health_monitor, _router


def parse_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse and validate incoming request body with comprehensive error handling.
    
    This function demonstrates robust request parsing patterns for
    serverless applications, including proper validation and error handling.
    
    Args:
        event: Lambda event dictionary
        
    Returns:
        Parsed request body dictionary
        
    Raises:
        ValueError: If request body is invalid
    """
    try:
        # Handle different event sources (API Gateway, direct invocation, etc.)
        if 'body' in event:
            # API Gateway event
            body = event['body']
            if isinstance(body, str):
                request_data = json.loads(body)
            else:
                request_data = body
        else:
            # Direct invocation
            request_data = event
        
        # Log request for educational purposes (sanitized)
        sanitized_request = {k: v for k, v in request_data.items() if k != 'query'}
        sanitized_request['query_length'] = len(request_data.get('query', ''))
        logger.info(f"Parsed request: {json.dumps(sanitized_request)}")
        
        return request_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        raise ValueError(f"Invalid JSON format: {str(e)}")
    except Exception as e:
        logger.error(f"Request parsing error: {str(e)}")
        raise ValueError(f"Request parsing failed: {str(e)}")


def validate_request_parameters(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate and normalize request parameters with educational logging.
    
    This function demonstrates comprehensive parameter validation patterns,
    including default value handling and constraint checking.
    
    Args:
        request_data: Raw request data dictionary
        
    Returns:
        Validated and normalized parameters dictionary
        
    Raises:
        ValueError: If required parameters are missing or invalid
    """
    # Required parameters
    if 'query' not in request_data or not request_data['query'].strip():
        raise ValueError("Missing required parameter: 'query'")
    
    query = request_data['query'].strip()
    
    # Validate query length
    if len(query) > 10000:  # Reasonable limit for demo
        raise ValueError("Query too long (maximum 10,000 characters)")
    
    if len(query) < 1:
        raise ValueError("Query cannot be empty")
    
    # Optional parameters with defaults and validation
    params = {
        'query': query,
        'strategy': request_data.get('strategy', 'balanced'),
        'preferred_provider': request_data.get('preferred_provider'),
        'max_tokens': request_data.get('max_tokens', 1000),
        'temperature': request_data.get('temperature', 0.7),
        'system_prompt': request_data.get('system_prompt'),
        'session_id': request_data.get('session_id', f"session_{int(time.time())}")
    }
    
    # Validate strategy
    valid_strategies = [s.value for s in RoutingStrategy]
    if params['strategy'] not in valid_strategies:
        logger.warning(f"Invalid strategy '{params['strategy']}', using 'balanced'")
        params['strategy'] = 'balanced'
    
    # Validate preferred_provider
    if params['preferred_provider']:
        valid_providers = [p.value for p in ModelProvider]
        if params['preferred_provider'] not in valid_providers:
            logger.warning(f"Invalid provider '{params['preferred_provider']}', ignoring")
            params['preferred_provider'] = None
    
    # Validate max_tokens
    if not isinstance(params['max_tokens'], int) or params['max_tokens'] < 1 or params['max_tokens'] > 4096:
        logger.warning(f"Invalid max_tokens {params['max_tokens']}, using 1000")
        params['max_tokens'] = 1000
    
    # Validate temperature
    if not isinstance(params['temperature'], (int, float)) or params['temperature'] < 0 or params['temperature'] > 2:
        logger.warning(f"Invalid temperature {params['temperature']}, using 0.7")
        params['temperature'] = 0.7
    
    # Log validated parameters for educational purposes
    log_params = params.copy()
    log_params['query'] = f"[{len(query)} characters]"  # Don't log actual query content
    logger.info(f"Validated parameters: {json.dumps(log_params)}")
    
    return params


def create_cors_headers() -> Dict[str, str]:
    """
    Create CORS headers for web frontend compatibility.
    
    Returns:
        Dictionary of CORS headers
    """
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token,X-Session-ID',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        'Content-Type': 'application/json'
    }


def create_success_response(data: Dict[str, Any], status_code: int = 200) -> Dict[str, Any]:
    """
    Create standardized success response with CORS headers.
    
    Args:
        data: Response data dictionary
        status_code: HTTP status code
        
    Returns:
        Lambda response dictionary
    """
    return {
        'statusCode': status_code,
        'headers': create_cors_headers(),
        'body': json.dumps(data, default=str, indent=2)
    }


def create_error_response(error_message: str, status_code: int = 400, 
                         error_code: str = "REQUEST_ERROR") -> Dict[str, Any]:
    """
    Create standardized error response with comprehensive error information.
    
    This function demonstrates proper error response patterns for APIs,
    including structured error information for client handling.
    
    Args:
        error_message: Human-readable error message
        status_code: HTTP status code
        error_code: Machine-readable error code
        
    Returns:
        Lambda error response dictionary
    """
    error_response = {
        'error': {
            'code': error_code,
            'message': error_message,
            'timestamp': time.time()
        }
    }
    
    logger.error(f"Error response: {error_code} - {error_message}")
    
    return {
        'statusCode': status_code,
        'headers': create_cors_headers(),
        'body': json.dumps(error_response, indent=2)
    }


def handle_query_request(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle GenAI query request with comprehensive processing and logging.
    
    This function implements the complete query processing workflow,
    demonstrating enterprise-grade request handling with educational
    transparency in all operations.
    
    Args:
        params: Validated request parameters
        
    Returns:
        Response data dictionary
        
    Raises:
        RuntimeError: If query processing fails
    """
    start_time = time.time()
    
    # Get system components
    adapter, health_monitor, router = get_components()
    
    # Convert strategy string to enum
    strategy = RoutingStrategy(params['strategy'])
    
    # Convert provider string to enum if specified
    preferred_provider = None
    if params['preferred_provider']:
        preferred_provider = ModelProvider(params['preferred_provider'])
    
    logger.info(f"Processing query request:")
    logger.info(f"  Query length: {len(params['query'])} characters")
    logger.info(f"  Strategy: {strategy.value}")
    logger.info(f"  Preferred provider: {preferred_provider.value if preferred_provider else 'none'}")
    logger.info(f"  Session ID: {params['session_id']}")
    
    try:
        # Step 1: Perform intelligent routing
        logger.info("Step 1: Performing intelligent model routing")
        
        # Check for simulated failures
        global _simulated_failures
        active_failures = {k: v for k, v in _simulated_failures.items() if v}
        if active_failures:
            logger.warning(f"🎓 EDUCATIONAL DEMO: Active failure simulations: {active_failures}")
        
        routing_start = time.time()
        
        routing_decision = router.route_query(
            query_text=params['query'],
            strategy=strategy,
            preferred_provider=preferred_provider
        )
        
        # Check if selected provider is simulated as failed
        selected_provider = routing_decision.selected_provider.value
        if _simulated_failures.get(selected_provider, False):
            logger.warning(f"🎓 EDUCATIONAL DEMO: {selected_provider} is simulated as FAILED - forcing failover")
            
            # Force selection of a different provider
            # Try providers in order: anthropic, openai, nova (excluding the failed one)
            available_providers = ['anthropic', 'openai', 'nova']
            healthy_providers = [p for p in available_providers if not _simulated_failures.get(p, False)]
            
            if healthy_providers:
                # Re-route to a healthy provider
                logger.info(f"🎓 Failing over to healthy providers: {healthy_providers}")
                
                # Convert string to ModelProvider enum
                provider_map = {
                    'anthropic': ModelProvider.ANTHROPIC,
                    'openai': ModelProvider.OPENAI,
                    'nova': ModelProvider.NOVA
                }
                fallback_provider = provider_map.get(healthy_providers[0])
                
                # Re-route with the healthy provider
                routing_decision = router.route_query(
                    query_text=params['query'],
                    strategy=strategy,
                    preferred_provider=fallback_provider
                )
                logger.info(f"🎓 Failover complete - now using {routing_decision.selected_provider.value}")
                
                # Verify the new provider is not also simulated as failed
                new_provider = routing_decision.selected_provider.value
                if _simulated_failures.get(new_provider, False):
                    logger.error(f"🎓 Failover provider {new_provider} is also simulated as failed!")
                    # Try the next healthy provider
                    for next_provider_str in healthy_providers[1:]:
                        next_provider = provider_map.get(next_provider_str)
                        if next_provider:
                            routing_decision = router.route_query(
                                query_text=params['query'],
                                strategy=strategy,
                                preferred_provider=next_provider
                            )
                            if not _simulated_failures.get(routing_decision.selected_provider.value, False):
                                logger.info(f"🎓 Successfully failed over to {routing_decision.selected_provider.value}")
                                break
                    else:
                        raise RuntimeError("All healthy providers failed during failover - no available providers")
            else:
                raise RuntimeError("All providers are simulated as failed - no healthy providers available")
        
        routing_time = (time.time() - routing_start) * 1000
        logger.info(f"Routing completed in {routing_time:.1f}ms:")
        logger.info(f"  Selected model: {routing_decision.selected_model_id}")
        logger.info(f"  Selected provider: {routing_decision.selected_provider.value}")
        logger.info(f"  Confidence: {routing_decision.confidence_score:.2f}")
        logger.info(f"  Reasoning steps: {len(routing_decision.decision_reasoning)}")
        
        # Log key routing reasoning for educational purposes
        if routing_decision.decision_reasoning:
            logger.info("Key routing decisions:")
            for i, reason in enumerate(routing_decision.decision_reasoning[-3:], 1):
                logger.info(f"  {i}. {reason}")
        
        # Step 2: Execute query with selected model
        logger.info("Step 2: Executing query with selected model")
        execution_start = time.time()
        
        # Create conversation messages
        messages = [create_user_message(params['query'])]
        
        # Record request start for load balancing
        router.load_balancer.record_request_start(routing_decision.selected_model_id)
        
        try:
            # Execute the query
            response = adapter.converse(
                model_id=routing_decision.selected_model_id,
                messages=messages,
                max_tokens=params['max_tokens'],
                temperature=params['temperature'],
                system_prompt=params['system_prompt']
            )
            
            execution_time = (time.time() - execution_start) * 1000
            
            # Record successful execution
            router.record_routing_performance(
                routing_decision, 
                response.latency_ms, 
                success=True
            )
            
            logger.info(f"Query execution completed successfully:")
            logger.info(f"  Execution time: {execution_time:.1f}ms")
            logger.info(f"  Model response time: {response.latency_ms}ms")
            logger.info(f"  Tokens used: {response.tokens_used}")
            logger.info(f"  Finish reason: {response.finish_reason}")
            
        except Exception as e:
            # Record failed execution
            execution_time = (time.time() - execution_start) * 1000
            router.record_routing_performance(
                routing_decision,
                int(execution_time),
                success=False
            )
            
            logger.error(f"Query execution failed after {execution_time:.1f}ms: {str(e)}")
            raise
        
        # Step 3: Build comprehensive response
        total_time = (time.time() - start_time) * 1000
        
        response_data = {
            'response': response.content,
            'metadata': {
                'model': response.model_id,
                'provider': response.provider.value,
                'tokensUsed': response.tokens_used,
                'inputTokens': response.metadata.get('input_tokens', 0),
                'outputTokens': response.metadata.get('output_tokens', 0),
                'latencyMs': response.latency_ms,
                'finishReason': response.finish_reason
            },
            'routing_info': {
                'strategy_used': routing_decision.strategy_used.value,
                'routing_time_ms': int(routing_time),
                'confidence_score': routing_decision.confidence_score,
                'considered_models': routing_decision.considered_models,
                'decision_reasoning': routing_decision.decision_reasoning[-5:]  # Last 5 steps
            },
            'performance_metrics': {
                'total_request_time_ms': int(total_time),
                'routing_time_ms': int(routing_time),
                'execution_time_ms': int(execution_time),
                'model_response_time_ms': response.latency_ms
            },
            'session_info': {
                'session_id': params['session_id'],
                'timestamp': time.time(),
                'request_id': response.metadata.get('request_id', 'unknown')
            }
        }
        
        logger.info(f"Request completed successfully in {total_time:.1f}ms")
        logger.info(f"Response length: {len(response.content)} characters")
        
        return response_data
        
    except Exception as e:
        logger.error(f"Query processing failed: {str(e)}")
        logger.error(f"Error traceback: {traceback.format_exc()}")
        raise RuntimeError(f"Query processing failed: {str(e)}")


def handle_health_check() -> Dict[str, Any]:
    """
    Handle system health check request with comprehensive status information.
    
    This function demonstrates health check patterns for serverless applications,
    providing detailed system status for monitoring and educational purposes.
    
    Returns:
        Health check response data dictionary
    """
    logger.info("Processing health check request")
    start_time = time.time()
    
    try:
        # Get system components
        adapter, health_monitor, router = get_components()
        
        # Get comprehensive system health overview
        health_overview = health_monitor.get_system_health_overview()
        
        # Get routing statistics
        routing_stats = router.get_routing_statistics()
        
        # Build health check response
        health_data = {
            'status': 'healthy',
            'timestamp': time.time(),
            'system_health': health_overview['system_health'],
            'providers': {
                provider.value: {
                    'status': info['overall_status'],
                    'latency': info['avg_response_time_ms'],
                    'successRate': (info['healthy_models'] / info['total_models'] * 100) if info['total_models'] > 0 else 0,
                    'healthyModels': info['healthy_models'],
                    'totalModels': info['total_models']
                }
                for provider, info in health_overview['provider_health'].items()
            },
            'provider_health': {
                provider.value: {
                    'status': info['overall_status'],
                    'healthy_models': info['healthy_models'],
                    'total_models': info['total_models'],
                    'avg_response_time_ms': info['avg_response_time_ms']
                }
                for provider, info in health_overview['provider_health'].items()
            },
            'circuit_breakers': {
                'total_breakers': health_overview['circuit_breakers']['total_breakers'],
                'open_breakers': health_overview['circuit_breakers']['open_breakers'],
                'half_open_breakers': health_overview['circuit_breakers']['half_open_breakers']
            },
            'routing_statistics': {
                'total_decisions': routing_stats['total_routing_decisions'],
                'average_confidence': routing_stats['average_confidence'],
                'provider_distribution': routing_stats['provider_distribution']
            },
            'cache_performance': health_overview['cache_performance']
        }
        
        # Determine overall system status
        system_health = health_overview['system_health']
        if system_health['overall_status'] == 'unhealthy':
            health_data['status'] = 'unhealthy'
        elif system_health['overall_status'] == 'degraded':
            health_data['status'] = 'degraded'
        
        check_time = (time.time() - start_time) * 1000
        health_data['check_time_ms'] = int(check_time)
        
        logger.info(f"Health check completed in {check_time:.1f}ms:")
        logger.info(f"  System status: {health_data['status']}")
        logger.info(f"  Healthy models: {system_health['healthy_models']}/{system_health['total_models']}")
        logger.info(f"  Open circuit breakers: {health_data['circuit_breakers']['open_breakers']}")
        
        return health_data
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            'status': 'error',
            'timestamp': time.time(),
            'error': str(e),
            'check_time_ms': int((time.time() - start_time) * 1000)
        }


def handle_failure_simulation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle failure simulation requests for educational demonstrations.
    
    Args:
        event: Lambda event containing simulation parameters
        
    Returns:
        Simulation status response
    """
    global _simulated_failures
    
    logger.info("Processing failure simulation request")
    
    try:
        # Parse request body
        body = event.get('body', '{}')
        if isinstance(body, str):
            import json
            params = json.loads(body)
        else:
            params = body
            
        provider = params.get('provider', '').lower()
        enabled = params.get('enabled', False)
        
        logger.info(f"🎓 EDUCATIONAL DEMO: Failure simulation {provider}={enabled}")
        
        # Update global failure simulation state
        if provider in _simulated_failures:
            _simulated_failures[provider] = enabled
            message = f"Failure simulation {'enabled' if enabled else 'disabled'} for {provider}"
            logger.info(f"✅ {message}")
            logger.info(f"Current simulated failures: {_simulated_failures}")
        else:
            message = f"Unknown provider: {provider}"
            logger.warning(message)
        
        return {
            'success': True,
            'message': message,
            'provider': provider,
            'enabled': enabled,
            'active_simulations': {k: v for k, v in _simulated_failures.items() if v}
        }
        
    except Exception as e:
        logger.error(f"Failure simulation error: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'success': False,
            'message': f"Error: {str(e)}",
            'provider': provider if 'provider' in locals() else 'unknown',
            'enabled': False
        }


def handle_metrics_request() -> Dict[str, Any]:
    """
    Handle metrics request with comprehensive system performance data.
    
    This function provides detailed metrics for monitoring dashboards
    and educational analysis of system performance.
    
    Returns:
        Metrics response data dictionary
    """
    logger.info("Processing metrics request")
    start_time = time.time()
    
    try:
        # Get system components
        adapter, health_monitor, router = get_components()
        
        # Get comprehensive metrics
        routing_stats = router.get_routing_statistics()
        health_overview = health_monitor.get_system_health_overview()
        load_stats = router.load_balancer.get_load_statistics()
        
        metrics_data = {
            'timestamp': time.time(),
            'routing_metrics': routing_stats,
            'health_metrics': {
                'system_health_rate': health_overview['system_health']['health_rate'],
                'provider_health': health_overview['provider_health'],
                'circuit_breaker_status': health_overview['circuit_breakers']
            },
            'load_balancing_metrics': load_stats,
            'model_capabilities': {
                model_id: {
                    'provider': capability.provider.value,
                    'avg_response_time_ms': capability.avg_response_time_ms,
                    'cost_score': capability.cost_score,
                    'general_capability': capability.general_capability,
                    'reliability_score': capability.reliability_score
                }
                for model_id, capability in router.model_capabilities.items()
            }
        }
        
        metrics_time = (time.time() - start_time) * 1000
        metrics_data['collection_time_ms'] = int(metrics_time)
        
        logger.info(f"Metrics collection completed in {metrics_time:.1f}ms")
        
        return metrics_data
        
    except Exception as e:
        logger.error(f"Metrics collection failed: {str(e)}")
        return {
            'error': str(e),
            'timestamp': time.time(),
            'collection_time_ms': int((time.time() - start_time) * 1000)
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main AWS Lambda handler function for GenAI model selection demo.
    
    This function serves as the central entry point for the demonstration system,
    orchestrating all components and providing comprehensive error handling and
    logging for educational purposes.
    
    The handler demonstrates enterprise-grade serverless patterns including:
    - Comprehensive request validation and error handling
    - Structured logging for observability
    - Performance monitoring and metrics collection
    - CORS support for web frontend integration
    - Educational transparency in all operations
    
    Args:
        event: Lambda event dictionary (from API Gateway or direct invocation)
        context: Lambda context object
        
    Returns:
        Lambda response dictionary with proper HTTP formatting
    """
    # Log request start with context information
    request_id = context.aws_request_id if context else 'unknown'
    logger.info(f"=== Lambda Request Started ===")
    logger.info(f"Request ID: {request_id}")
    logger.info(f"Function name: {context.function_name if context else 'unknown'}")
    logger.info(f"Remaining time: {context.get_remaining_time_in_millis() if context else 'unknown'}ms")
    
    start_time = time.time()
    
    try:
        # Handle CORS preflight requests
        if event.get('httpMethod') == 'OPTIONS':
            logger.info("Handling CORS preflight request")
            return {
                'statusCode': 200,
                'headers': create_cors_headers(),
                'body': ''
            }
        
        # Determine request type based on path or event structure
        path = event.get('path', '/')
        http_method = event.get('httpMethod', 'POST')
        
        logger.info(f"Processing {http_method} request to {path}")
        
        # Route to appropriate handler based on path
        if path == '/health' or event.get('action') == 'health_check':
            logger.info("Routing to health check handler")
            response_data = handle_health_check()
            return create_success_response(response_data)
            
        elif path == '/metrics' or event.get('action') == 'metrics':
            logger.info("Routing to metrics handler")
            response_data = handle_metrics_request()
            return create_success_response(response_data)
            
        elif path == '/admin/simulate-failure':
            logger.info("Routing to failure simulation handler")
            response_data = handle_failure_simulation(event)
            return create_success_response(response_data)
            
        else:
            # Default to query processing
            logger.info("Routing to query processing handler")
            
            # Parse and validate request
            try:
                request_data = parse_request_body(event)
                params = validate_request_parameters(request_data)
            except ValueError as e:
                return create_error_response(str(e), 400, "VALIDATION_ERROR")
            
            # Process the query
            try:
                response_data = handle_query_request(params)
                return create_success_response(response_data)
            except RuntimeError as e:
                return create_error_response(str(e), 500, "PROCESSING_ERROR")
    
    except Exception as e:
        # Handle unexpected errors
        logger.error(f"Unexpected error in Lambda handler: {str(e)}")
        logger.error(f"Error traceback: {traceback.format_exc()}")
        
        return create_error_response(
            "Internal server error occurred",
            500,
            "INTERNAL_ERROR"
        )
    
    finally:
        # Log request completion
        total_time = (time.time() - start_time) * 1000
        logger.info(f"=== Lambda Request Completed ===")
        logger.info(f"Request ID: {request_id}")
        logger.info(f"Total execution time: {total_time:.1f}ms")
        
        # Log remaining time for educational purposes
        if context:
            remaining_time = context.get_remaining_time_in_millis()
            logger.info(f"Remaining Lambda time: {remaining_time}ms")


# Utility functions for testing and development
def test_handler_locally():
    """
    Test the Lambda handler locally with sample requests.
    
    This function provides a way to test the handler functionality
    without deploying to AWS, useful for development and debugging.
    """
    print("=== Local Lambda Handler Testing ===")
    
    # Mock Lambda context
    class MockContext:
        def __init__(self):
            self.aws_request_id = "test-request-123"
            self.function_name = "genai-model-selection-demo"
            self.remaining_time = 30000
        
        def get_remaining_time_in_millis(self):
            return self.remaining_time
    
    context = MockContext()
    
    # Test health check
    print("\n1. Testing Health Check:")
    health_event = {
        'httpMethod': 'GET',
        'path': '/health'
    }
    
    try:
        response = lambda_handler(health_event, context)
        print(f"   Status: {response['statusCode']}")
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            print(f"   System status: {body.get('status', 'unknown')}")
        else:
            print(f"   Error: {response['body']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test metrics
    print("\n2. Testing Metrics:")
    metrics_event = {
        'httpMethod': 'GET',
        'path': '/metrics'
    }
    
    try:
        response = lambda_handler(metrics_event, context)
        print(f"   Status: {response['statusCode']}")
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            print(f"   Metrics collected: {len(body)} categories")
        else:
            print(f"   Error: {response['body']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test query processing
    print("\n3. Testing Query Processing:")
    query_event = {
        'httpMethod': 'POST',
        'path': '/query',
        'body': json.dumps({
            'query': 'What is artificial intelligence?',
            'strategy': 'balanced',
            'max_tokens': 100
        })
    }
    
    try:
        response = lambda_handler(query_event, context)
        print(f"   Status: {response['statusCode']}")
        if response['statusCode'] == 200:
            body = json.loads(response['body'])
            print(f"   Selected model: {body.get('metadata', {}).get('model_id', 'unknown')}")
            print(f"   Response length: {len(body.get('response', ''))} characters")
        else:
            print(f"   Error: {response['body']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n=== Local Testing Complete ===")
    print("Note: Full functionality requires valid AWS credentials and Bedrock access")


# Example usage and testing
if __name__ == "__main__":
    """
    Local testing and demonstration of the Lambda handler.
    
    This section provides examples of how the handler works and can be
    tested locally during development.
    """
    
    print("=== GenAI Model Selection Lambda Handler Demo ===")
    print("Demonstrating serverless GenAI routing with comprehensive logging")
    
    # Run local tests
    test_handler_locally()
    
    print("\nThe Lambda handler provides:")
    print("- Unified GenAI model routing across Claude, GPT, and Nova")
    print("- Intelligent model selection with multiple strategies")
    print("- Health monitoring with circuit breaker patterns")
    print("- Comprehensive error handling and logging")
    print("- Educational transparency in all operations")
    print("- CORS support for web frontend integration")