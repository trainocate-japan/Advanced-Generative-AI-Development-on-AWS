"""
Model Health Monitoring System

This module implements comprehensive health monitoring for GenAI models through
the unified Bedrock Converse API. It provides real-time availability checking,
circuit breaker patterns, and health status caching for Anthropic Claude,
Meta Llama, and AWS Nova models.

The health monitoring system demonstrates provider-agnostic architecture by
using the same health check patterns across all three model providers,
abstracting away provider-specific differences through the Converse API.

Key educational concepts demonstrated:
1. Circuit breaker pattern for fault tolerance
2. Health status caching with TTL for performance
3. Unified monitoring across multiple providers
4. Comprehensive logging for demonstration purposes
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import boto3
from botocore.exceptions import ClientError

# Import from our unified adapter
from bedrock_adapter import (
    BedrockConverseAdapter, ModelProvider, ModelType, 
    ConversationMessage, create_user_message
)

# Configure logging for educational demonstration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration for models and providers"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitState(Enum):
    """Circuit breaker states for fault tolerance"""
    CLOSED = "closed"      # Normal operation, requests allowed
    OPEN = "open"          # Failure threshold exceeded, requests blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


@dataclass
class HealthCheckResult:
    """
    Comprehensive health check result for a specific model.
    
    This dataclass captures all relevant health information including
    performance metrics, error details, and timestamp data for
    educational analysis and demonstration purposes.
    """
    model_id: str
    provider: ModelProvider
    status: HealthStatus
    response_time_ms: int
    error_message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    test_query: str = ""
    tokens_used: int = 0
    
    def is_healthy(self) -> bool:
        """Check if the model is considered healthy"""
        return self.status == HealthStatus.HEALTHY
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'model_id': self.model_id,
            'provider': self.provider.value,
            'status': self.status.value,
            'response_time_ms': self.response_time_ms,
            'error_message': self.error_message,
            'timestamp': self.timestamp,
            'test_query': self.test_query,
            'tokens_used': self.tokens_used,
            'is_healthy': self.is_healthy()
        }


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 5      # Number of failures before opening circuit
    recovery_timeout: int = 60      # Seconds before attempting recovery
    success_threshold: int = 2      # Successful calls needed to close circuit
    timeout_seconds: int = 30       # Request timeout for health checks


@dataclass
class CircuitBreakerState:
    """
    Circuit breaker state tracking for individual models.
    
    The circuit breaker pattern prevents cascading failures by temporarily
    disabling requests to unhealthy models, allowing them time to recover
    while routing traffic to healthy alternatives.
    """
    model_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    
    def should_allow_request(self) -> bool:
        """
        Determine if requests should be allowed based on circuit breaker state.
        
        This method implements the core circuit breaker logic with detailed
        logging for educational demonstration of fault tolerance patterns.
        """
        current_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            # Normal operation - allow all requests
            logger.debug(f"Circuit breaker for {self.model_id}: CLOSED - allowing request")
            return True
            
        elif self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            time_since_failure = current_time - self.last_failure_time
            
            if time_since_failure >= self.config.recovery_timeout:
                # Transition to half-open for testing
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker for {self.model_id}: OPEN → HALF_OPEN "
                           f"(recovery timeout {self.config.recovery_timeout}s elapsed)")
                return True
            else:
                # Still in failure state - block requests
                remaining_time = self.config.recovery_timeout - time_since_failure
                logger.warning(f"Circuit breaker for {self.model_id}: OPEN - blocking request "
                             f"({remaining_time:.1f}s until recovery attempt)")
                return False
                
        elif self.state == CircuitState.HALF_OPEN:
            # Testing phase - allow limited requests
            logger.info(f"Circuit breaker for {self.model_id}: HALF_OPEN - allowing test request")
            return True
            
        return False
    
    def record_success(self):
        """
        Record a successful request and update circuit breaker state.
        
        This method demonstrates how successful requests can close an open
        circuit breaker, restoring normal operation.
        """
        self.last_success_time = time.time()
        self.failure_count = 0  # Reset failure count on success
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(f"Circuit breaker for {self.model_id}: Success in HALF_OPEN "
                       f"({self.success_count}/{self.config.success_threshold})")
            
            if self.success_count >= self.config.success_threshold:
                # Sufficient successes - close the circuit
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info(f"Circuit breaker for {self.model_id}: HALF_OPEN → CLOSED "
                           f"(recovery successful)")
        
        elif self.state == CircuitState.CLOSED:
            logger.debug(f"Circuit breaker for {self.model_id}: Success recorded in CLOSED state")
    
    def record_failure(self):
        """
        Record a failed request and update circuit breaker state.
        
        This method shows how accumulated failures can open a circuit breaker,
        protecting the system from cascading failures.
        """
        self.last_failure_time = time.time()
        self.failure_count += 1
        
        logger.warning(f"Circuit breaker for {self.model_id}: Failure recorded "
                      f"({self.failure_count}/{self.config.failure_threshold})")
        
        if self.failure_count >= self.config.failure_threshold:
            if self.state != CircuitState.OPEN:
                previous_state = self.state.value
                self.state = CircuitState.OPEN
                logger.error(f"Circuit breaker for {self.model_id}: {previous_state.upper()} → OPEN "
                           f"(failure threshold {self.config.failure_threshold} exceeded)")
        
        elif self.state == CircuitState.HALF_OPEN:
            # Failure during testing - reopen circuit
            self.state = CircuitState.OPEN
            self.success_count = 0
            logger.warning(f"Circuit breaker for {self.model_id}: HALF_OPEN → OPEN "
                          f"(test request failed)")


class HealthCache:
    """
    Thread-safe health status cache with TTL (Time To Live) functionality.
    
    This cache improves performance by avoiding redundant health checks
    while ensuring data freshness through configurable TTL values.
    The cache demonstrates efficient resource management in distributed systems.
    """
    
    def __init__(self, default_ttl_seconds: int = 300):  # 5 minutes default TTL
        """
        Initialize health cache with configurable TTL.
        
        Args:
            default_ttl_seconds: Default cache TTL in seconds
        """
        self.default_ttl = default_ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()  # Thread safety for concurrent access
        
        logger.info(f"Initialized HealthCache with {default_ttl_seconds}s default TTL")
    
    def get(self, model_id: str) -> Optional[HealthCheckResult]:
        """
        Retrieve cached health result if still valid.
        
        Args:
            model_id: Model identifier to look up
            
        Returns:
            Cached HealthCheckResult if valid, None if expired or missing
        """
        with self.lock:
            if model_id not in self.cache:
                logger.debug(f"Cache miss for {model_id}: not found")
                return None
            
            cache_entry = self.cache[model_id]
            current_time = time.time()
            
            # Check if cache entry has expired
            if current_time > cache_entry['expires_at']:
                # Remove expired entry
                del self.cache[model_id]
                logger.debug(f"Cache miss for {model_id}: expired "
                           f"({current_time - cache_entry['expires_at']:.1f}s ago)")
                return None
            
            # Return valid cached result
            logger.debug(f"Cache hit for {model_id}: "
                        f"{cache_entry['expires_at'] - current_time:.1f}s remaining")
            return cache_entry['result']
    
    def put(self, model_id: str, result: HealthCheckResult, ttl_seconds: Optional[int] = None):
        """
        Store health check result in cache with TTL.
        
        Args:
            model_id: Model identifier
            result: Health check result to cache
            ttl_seconds: Custom TTL, uses default if None
        """
        ttl = ttl_seconds or self.default_ttl
        expires_at = time.time() + ttl
        
        with self.lock:
            self.cache[model_id] = {
                'result': result,
                'expires_at': expires_at,
                'cached_at': time.time()
            }
            
            logger.debug(f"Cached health result for {model_id}: "
                        f"TTL={ttl}s, expires at {expires_at}")
    
    def invalidate(self, model_id: str):
        """Remove specific model from cache"""
        with self.lock:
            if model_id in self.cache:
                del self.cache[model_id]
                logger.debug(f"Invalidated cache for {model_id}")
    
    def clear(self):
        """Clear entire cache"""
        with self.lock:
            cache_size = len(self.cache)
            self.cache.clear()
            logger.info(f"Cleared health cache ({cache_size} entries)")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring"""
        with self.lock:
            current_time = time.time()
            valid_entries = 0
            expired_entries = 0
            
            for entry in self.cache.values():
                if current_time <= entry['expires_at']:
                    valid_entries += 1
                else:
                    expired_entries += 1
            
            return {
                'total_entries': len(self.cache),
                'valid_entries': valid_entries,
                'expired_entries': expired_entries,
                'cache_hit_potential': valid_entries / len(self.cache) if self.cache else 0
            }


class ModelHealthMonitor:
    """
    Comprehensive health monitoring system for GenAI models through Converse API.
    
    This class implements unified health monitoring across Anthropic Claude,
    Meta Llama, and AWS Nova models, providing:
    
    1. Real-time health status checking through lightweight test queries
    2. Circuit breaker pattern implementation for fault tolerance
    3. Health status caching with TTL for performance optimization
    4. Comprehensive logging for educational demonstration
    5. Provider-agnostic monitoring through Bedrock Converse API
    
    The system demonstrates enterprise-grade reliability patterns while
    maintaining educational value for understanding distributed system concepts.
    """
    
    def __init__(self, adapter: BedrockConverseAdapter, cache_ttl_seconds: int = 300):
        """
        Initialize comprehensive health monitoring system.
        
        Args:
            adapter: Unified Bedrock adapter for health checks
            cache_ttl_seconds: Cache TTL for health results
        """
        self.adapter = adapter
        self.health_cache = HealthCache(cache_ttl_seconds)
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self.lock = Lock()  # Thread safety for circuit breaker operations
        
        # Initialize circuit breakers for all configured models
        for model_id in self.adapter.model_configs.keys():
            self.circuit_breakers[model_id] = CircuitBreakerState(model_id=model_id)
        
        # Lightweight test queries optimized for each provider
        # These queries are designed to be fast and consume minimal tokens
        self.test_queries = {
            ModelProvider.ANTHROPIC: "Hi",
            ModelProvider.OPENAI: "Hello",
            ModelProvider.NOVA: "Test"
        }
        
        logger.info(f"Initialized ModelHealthMonitor for {len(self.circuit_breakers)} models "
                   f"with {cache_ttl_seconds}s cache TTL")
        
        # Log circuit breaker configuration for educational purposes
        sample_config = CircuitBreakerConfig()
        logger.info(f"Circuit breaker configuration: "
                   f"failure_threshold={sample_config.failure_threshold}, "
                   f"recovery_timeout={sample_config.recovery_timeout}s, "
                   f"success_threshold={sample_config.success_threshold}")
    
    def check_model_health(self, model_id: str, use_cache: bool = True, 
                          force_check: bool = False) -> HealthCheckResult:
        """
        Perform comprehensive health check for a specific model.
        
        This method demonstrates the complete health checking workflow:
        1. Cache lookup for performance optimization
        2. Circuit breaker consultation for fault tolerance
        3. Lightweight test query through Converse API
        4. Result caching and circuit breaker state updates
        
        Args:
            model_id: Model to health check
            use_cache: Whether to use cached results
            force_check: Force check even if circuit breaker is open
            
        Returns:
            HealthCheckResult with comprehensive status information
        """
        # Check cache first (unless forced)
        if use_cache and not force_check:
            cached_result = self.health_cache.get(model_id)
            if cached_result:
                logger.debug(f"Using cached health result for {model_id}")
                return cached_result
        
        # Get model configuration
        config = self.adapter.get_model_config(model_id)
        if not config:
            logger.error(f"Model {model_id} not found in configuration")
            return HealthCheckResult(
                model_id=model_id,
                provider=ModelProvider.ANTHROPIC,  # Default fallback
                status=HealthStatus.UNKNOWN,
                response_time_ms=0,
                error_message="Model not configured"
            )
        
        # Check circuit breaker state (unless forced)
        with self.lock:
            circuit_breaker = self.circuit_breakers.get(model_id)
            if circuit_breaker and not force_check:
                if not circuit_breaker.should_allow_request():
                    # Circuit breaker is open - return cached unhealthy status
                    logger.warning(f"Circuit breaker OPEN for {model_id} - skipping health check")
                    return HealthCheckResult(
                        model_id=model_id,
                        provider=config.provider,
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        error_message="Circuit breaker open - model temporarily disabled"
                    )
        
        # Perform actual health check
        logger.info(f"Performing health check for {model_id} ({config.provider.value})")
        start_time = time.time()
        
        # Select appropriate test query for the provider
        test_query = self.test_queries.get(config.provider, "Hello")
        
        try:
            # Create minimal test message for health check
            messages = [create_user_message(test_query)]
            
            # Execute health check with minimal resource usage
            response = self.adapter.converse(
                model_id=model_id,
                messages=messages,
                max_tokens=5,      # Minimal response for health check
                temperature=0.0    # Deterministic response
            )
            
            # Calculate response time
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Validate response quality
            is_healthy = (
                response.content and 
                len(response.content.strip()) > 0 and
                response.finish_reason in ['end_turn', 'stop_sequence', 'max_tokens'] and
                response.tokens_used > 0
            )
            
            # Determine health status based on response time and quality
            if is_healthy:
                if response_time_ms < 5000:  # Under 5 seconds
                    status = HealthStatus.HEALTHY
                elif response_time_ms < 15000:  # Under 15 seconds
                    status = HealthStatus.DEGRADED
                else:
                    status = HealthStatus.UNHEALTHY
                    is_healthy = False
            else:
                status = HealthStatus.UNHEALTHY
            
            # Create health check result
            result = HealthCheckResult(
                model_id=model_id,
                provider=config.provider,
                status=status,
                response_time_ms=response_time_ms,
                error_message=None if is_healthy else "Invalid or slow response",
                test_query=test_query,
                tokens_used=response.tokens_used
            )
            
            # Update circuit breaker state
            with self.lock:
                if circuit_breaker:
                    if is_healthy:
                        circuit_breaker.record_success()
                    else:
                        circuit_breaker.record_failure()
            
            # Log detailed results for educational purposes
            logger.info(f"Health check completed for {model_id}: "
                       f"status={status.value}, "
                       f"response_time={response_time_ms}ms, "
                       f"tokens={response.tokens_used}")
            
            if status == HealthStatus.DEGRADED:
                logger.warning(f"Model {model_id} showing degraded performance: "
                             f"{response_time_ms}ms response time")
            
        except Exception as e:
            # Handle health check failures
            response_time_ms = int((time.time() - start_time) * 1000)
            error_message = str(e)
            
            result = HealthCheckResult(
                model_id=model_id,
                provider=config.provider,
                status=HealthStatus.UNHEALTHY,
                response_time_ms=response_time_ms,
                error_message=error_message,
                test_query=test_query,
                tokens_used=0
            )
            
            # Update circuit breaker for failure
            with self.lock:
                if circuit_breaker:
                    circuit_breaker.record_failure()
            
            logger.error(f"Health check failed for {model_id}: {error_message}")
        
        # Cache the result
        if use_cache:
            # Use shorter TTL for unhealthy models to check recovery more frequently
            cache_ttl = 60 if result.status == HealthStatus.UNHEALTHY else None
            self.health_cache.put(model_id, result, cache_ttl)
        
        return result
    
    def check_all_models_health(self, use_cache: bool = True) -> Dict[str, HealthCheckResult]:
        """
        Perform health checks for all configured models.
        
        This method demonstrates comprehensive system health monitoring
        across all three provider types (Claude, GPT, Nova) using the
        unified Converse API interface.
        
        Args:
            use_cache: Whether to use cached results where available
            
        Returns:
            Dictionary mapping model IDs to their health check results
        """
        logger.info("Starting comprehensive health check for all models")
        start_time = time.time()
        
        results = {}
        healthy_count = 0
        degraded_count = 0
        unhealthy_count = 0
        
        # Check each configured model
        for model_id in self.adapter.model_configs.keys():
            try:
                result = self.check_model_health(model_id, use_cache)
                results[model_id] = result
                
                # Count status distribution
                if result.status == HealthStatus.HEALTHY:
                    healthy_count += 1
                elif result.status == HealthStatus.DEGRADED:
                    degraded_count += 1
                else:
                    unhealthy_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to health check {model_id}: {str(e)}")
                config = self.adapter.get_model_config(model_id)
                results[model_id] = HealthCheckResult(
                    model_id=model_id,
                    provider=config.provider if config else ModelProvider.ANTHROPIC,
                    status=HealthStatus.UNKNOWN,
                    response_time_ms=0,
                    error_message=f"Health check exception: {str(e)}"
                )
                unhealthy_count += 1
        
        # Log comprehensive summary for educational purposes
        total_time = time.time() - start_time
        total_models = len(results)
        
        logger.info(f"Health check summary:")
        logger.info(f"  Total models: {total_models}")
        logger.info(f"  Healthy: {healthy_count} ({healthy_count/total_models*100:.1f}%)")
        logger.info(f"  Degraded: {degraded_count} ({degraded_count/total_models*100:.1f}%)")
        logger.info(f"  Unhealthy: {unhealthy_count} ({unhealthy_count/total_models*100:.1f}%)")
        logger.info(f"  Total time: {total_time:.2f}s")
        logger.info(f"  Average time per model: {total_time/total_models:.2f}s")
        
        return results
    
    def get_provider_health_summary(self) -> Dict[ModelProvider, Dict[str, Any]]:
        """
        Get health summary organized by provider for educational analysis.
        
        This method demonstrates how to aggregate health data across
        providers to understand system-wide health patterns and identify
        provider-specific issues.
        
        Returns:
            Dictionary with provider-level health statistics
        """
        all_results = self.check_all_models_health()
        provider_summary = {}
        
        # Organize results by provider
        for provider in ModelProvider:
            provider_results = [
                result for result in all_results.values() 
                if result.provider == provider
            ]
            
            if not provider_results:
                continue
            
            # Calculate provider-level statistics
            healthy_models = [r for r in provider_results if r.status == HealthStatus.HEALTHY]
            degraded_models = [r for r in provider_results if r.status == HealthStatus.DEGRADED]
            unhealthy_models = [r for r in provider_results if r.status == HealthStatus.UNHEALTHY]
            
            # Calculate average response time for healthy models
            healthy_response_times = [r.response_time_ms for r in healthy_models if r.response_time_ms > 0]
            avg_response_time = (sum(healthy_response_times) / len(healthy_response_times) 
                               if healthy_response_times else 0)
            
            # Determine overall provider status
            if len(healthy_models) == len(provider_results):
                overall_status = HealthStatus.HEALTHY
            elif len(healthy_models) + len(degraded_models) > 0:
                overall_status = HealthStatus.DEGRADED
            else:
                overall_status = HealthStatus.UNHEALTHY
            
            provider_summary[provider] = {
                'overall_status': overall_status.value,
                'total_models': len(provider_results),
                'healthy_models': len(healthy_models),
                'degraded_models': len(degraded_models),
                'unhealthy_models': len(unhealthy_models),
                'health_rate': len(healthy_models) / len(provider_results),
                'avg_response_time_ms': int(avg_response_time),
                'model_details': {
                    result.model_id: {
                        'status': result.status.value,
                        'response_time_ms': result.response_time_ms,
                        'error_message': result.error_message
                    }
                    for result in provider_results
                }
            }
            
            # Log provider summary for educational purposes
            logger.info(f"Provider {provider.value} health summary: "
                       f"{overall_status.value} "
                       f"({len(healthy_models)}/{len(provider_results)} healthy, "
                       f"avg {int(avg_response_time)}ms)")
        
        return provider_summary
    
    def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get current circuit breaker status for all models.
        
        This method provides visibility into the circuit breaker states,
        helping understand fault tolerance behavior during demonstrations.
        
        Returns:
            Dictionary with circuit breaker status for each model
        """
        with self.lock:
            status = {}
            
            for model_id, breaker in self.circuit_breakers.items():
                status[model_id] = {
                    'state': breaker.state.value,
                    'failure_count': breaker.failure_count,
                    'success_count': breaker.success_count,
                    'last_failure_time': breaker.last_failure_time,
                    'last_success_time': breaker.last_success_time,
                    'allows_requests': breaker.should_allow_request(),
                    'config': {
                        'failure_threshold': breaker.config.failure_threshold,
                        'recovery_timeout': breaker.config.recovery_timeout,
                        'success_threshold': breaker.config.success_threshold
                    }
                }
            
            return status
    
    def reset_circuit_breaker(self, model_id: str):
        """
        Reset circuit breaker for a specific model.
        
        This method allows manual recovery during demonstrations,
        showing how circuit breakers can be managed operationally.
        
        Args:
            model_id: Model whose circuit breaker to reset
        """
        with self.lock:
            if model_id in self.circuit_breakers:
                breaker = self.circuit_breakers[model_id]
                old_state = breaker.state.value
                
                breaker.state = CircuitState.CLOSED
                breaker.failure_count = 0
                breaker.success_count = 0
                
                logger.info(f"Reset circuit breaker for {model_id}: {old_state} → CLOSED")
                
                # Invalidate cache to force fresh health check
                self.health_cache.invalidate(model_id)
            else:
                logger.warning(f"No circuit breaker found for model {model_id}")
    
    def get_system_health_overview(self) -> Dict[str, Any]:
        """
        Get comprehensive system health overview for monitoring dashboards.
        
        This method provides a complete picture of system health suitable
        for real-time monitoring and educational demonstration.
        
        Returns:
            Dictionary with system-wide health metrics and status
        """
        # Get current health status for all models
        health_results = self.check_all_models_health()
        provider_summary = self.get_provider_health_summary()
        circuit_breaker_status = self.get_circuit_breaker_status()
        cache_stats = self.health_cache.get_cache_stats()
        
        # Calculate system-wide metrics
        total_models = len(health_results)
        healthy_models = sum(1 for r in health_results.values() if r.status == HealthStatus.HEALTHY)
        degraded_models = sum(1 for r in health_results.values() if r.status == HealthStatus.DEGRADED)
        unhealthy_models = sum(1 for r in health_results.values() if r.status == HealthStatus.UNHEALTHY)
        
        # Determine overall system status
        if healthy_models == total_models:
            system_status = HealthStatus.HEALTHY
        elif healthy_models + degraded_models > total_models * 0.5:
            system_status = HealthStatus.DEGRADED
        else:
            system_status = HealthStatus.UNHEALTHY
        
        # Count circuit breaker states
        open_breakers = sum(1 for status in circuit_breaker_status.values() 
                           if status['state'] == 'open')
        half_open_breakers = sum(1 for status in circuit_breaker_status.values() 
                                if status['state'] == 'half_open')
        
        overview = {
            'timestamp': time.time(),
            'system_health': {
                'overall_status': system_status.value,
                'total_models': total_models,
                'healthy_models': healthy_models,
                'degraded_models': degraded_models,
                'unhealthy_models': unhealthy_models,
                'health_rate': healthy_models / total_models if total_models > 0 else 0
            },
            'provider_health': provider_summary,
            'circuit_breakers': {
                'total_breakers': len(circuit_breaker_status),
                'open_breakers': open_breakers,
                'half_open_breakers': half_open_breakers,
                'closed_breakers': len(circuit_breaker_status) - open_breakers - half_open_breakers,
                'details': circuit_breaker_status
            },
            'cache_performance': cache_stats,
            'model_details': {
                model_id: result.to_dict() 
                for model_id, result in health_results.items()
            }
        }
        
        # Log system overview for educational purposes
        logger.info(f"System health overview: {system_status.value} "
                   f"({healthy_models}/{total_models} healthy models, "
                   f"{open_breakers} open circuit breakers)")
        
        return overview


# Convenience functions for easy integration
def create_health_monitor(region_name: str = "us-east-1", 
                         cache_ttl_seconds: int = 300) -> ModelHealthMonitor:
    """
    Create a configured health monitor with unified Bedrock adapter.
    
    Args:
        region_name: AWS region for Bedrock service
        cache_ttl_seconds: Cache TTL for health results
        
    Returns:
        Configured ModelHealthMonitor instance
    """
    adapter = BedrockConverseAdapter(region_name=region_name)
    return ModelHealthMonitor(adapter, cache_ttl_seconds)


def quick_health_check(model_ids: Optional[List[str]] = None, 
                      region_name: str = "us-east-1") -> Dict[str, HealthCheckResult]:
    """
    Perform quick health check for specified models or all configured models.
    
    Args:
        model_ids: Specific models to check, or None for all models
        region_name: AWS region for Bedrock service
        
    Returns:
        Dictionary mapping model IDs to health check results
    """
    monitor = create_health_monitor(region_name)
    
    if model_ids:
        results = {}
        for model_id in model_ids:
            results[model_id] = monitor.check_model_health(model_id)
        return results
    else:
        return monitor.check_all_models_health()


# Example usage and demonstration
if __name__ == "__main__":
    """
    Demonstration of the comprehensive health monitoring system.
    
    This example shows how the health monitor works across all three
    provider types (Claude, GPT, Nova) with unified monitoring patterns.
    """
    
    print("=== GenAI Model Health Monitoring System Demo ===")
    print("Demonstrating unified health monitoring across Anthropic, Meta Llama, and Nova models")
    
    try:
        # Initialize health monitor
        print("\n1. Initializing Health Monitor:")
        monitor = create_health_monitor(region_name="us-east-1", cache_ttl_seconds=300)
        
        available_models = list(monitor.adapter.model_configs.keys())
        print(f"   Monitoring {len(available_models)} models across 3 providers")
        
        # Display configured models by provider
        for provider in ModelProvider:
            provider_models = [
                model_id for model_id, config in monitor.adapter.model_configs.items()
                if config.provider == provider
            ]
            if provider_models:
                print(f"   {provider.value}: {len(provider_models)} models")
        
        # Demonstrate individual model health check
        print("\n2. Individual Model Health Check:")
        if available_models:
            test_model = available_models[0]
            print(f"   Testing {test_model}...")
            
            # Note: This would require valid AWS credentials in a real environment
            print(f"   Health check would verify:")
            print(f"   - Model availability through Converse API")
            print(f"   - Response time measurement")
            print(f"   - Circuit breaker state management")
            print(f"   - Cache TTL handling")
        
        # Demonstrate system-wide health monitoring
        print("\n3. System-Wide Health Overview:")
        print("   The health monitor provides:")
        print("   - Unified monitoring across all three providers")
        print("   - Circuit breaker fault tolerance")
        print("   - Performance-optimized caching")
        print("   - Comprehensive logging for education")
        
        # Show circuit breaker configuration
        print("\n4. Circuit Breaker Configuration:")
        sample_config = CircuitBreakerConfig()
        print(f"   Failure threshold: {sample_config.failure_threshold} failures")
        print(f"   Recovery timeout: {sample_config.recovery_timeout} seconds")
        print(f"   Success threshold: {sample_config.success_threshold} successes")
        print(f"   Request timeout: {sample_config.timeout_seconds} seconds")
        
        # Demonstrate cache configuration
        print("\n5. Health Cache Configuration:")
        print(f"   Default TTL: {monitor.health_cache.default_ttl} seconds")
        print(f"   Thread-safe concurrent access")
        print(f"   Automatic expiration handling")
        print(f"   Performance statistics tracking")
        
        print("\n=== Demo Complete ===")
        print("The health monitoring system provides enterprise-grade reliability")
        print("with comprehensive observability across all GenAI model providers.")
        
    except Exception as e:
        print(f"Demo error: {e}")
        print("Note: Full functionality requires valid AWS credentials and Bedrock access")