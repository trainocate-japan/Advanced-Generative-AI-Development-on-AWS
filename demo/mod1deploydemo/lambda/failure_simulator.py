"""
Failure Simulation System for Educational Demonstrations

This module implements a comprehensive failure simulation system that allows
instructors to demonstrate model failover scenarios during classroom presentations.
The system provides controlled failure injection for individual models (Claude, GPT, Nova)
and comprehensive logging to show the decision-making process during failover events.

The failure simulation system demonstrates key reliability patterns:
1. Controlled failure injection for educational purposes
2. Circuit breaker behavior under failure conditions
3. Intelligent failover routing between providers
4. Comprehensive logging of decision-making processes
5. Administrative controls for demonstration management

This implementation showcases how distributed systems handle failures gracefully
while maintaining educational transparency in all operations.
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import random

# Import from our system components
from bedrock_adapter import ModelProvider, ModelType
from health_monitor import ModelHealthMonitor, HealthStatus, HealthCheckResult
from router import IntelligentModelRouter, RoutingStrategy

# Configure logging for educational demonstration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FailureType(Enum):
    """Types of failures that can be simulated for educational purposes"""
    MODEL_UNAVAILABLE = "model_unavailable"      # Model completely unavailable
    HIGH_LATENCY = "high_latency"               # Slow response times
    INTERMITTENT_ERRORS = "intermittent_errors" # Random failures
    RATE_LIMITED = "rate_limited"               # Rate limiting simulation
    TIMEOUT = "timeout"                         # Request timeouts
    CIRCUIT_BREAKER_OPEN = "circuit_breaker"    # Force circuit breaker open


@dataclass
class FailureSimulation:
    """
    Configuration for a specific failure simulation.
    
    This dataclass defines how a particular failure should be simulated,
    including duration, intensity, and educational logging preferences.
    """
    model_id: str
    provider: ModelProvider
    failure_type: FailureType
    start_time: float
    duration_seconds: int
    intensity: float = 1.0  # 0.0 (no effect) to 1.0 (complete failure)
    description: str = ""
    educational_notes: str = ""
    
    def is_active(self) -> bool:
        """Check if the failure simulation is currently active"""
        current_time = time.time()
        return (self.start_time <= current_time <= 
                self.start_time + self.duration_seconds)
    
    def time_remaining(self) -> float:
        """Get remaining time for the simulation in seconds"""
        if not self.is_active():
            return 0.0
        return (self.start_time + self.duration_seconds) - time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'model_id': self.model_id,
            'provider': self.provider.value,
            'failure_type': self.failure_type.value,
            'start_time': self.start_time,
            'duration_seconds': self.duration_seconds,
            'intensity': self.intensity,
            'description': self.description,
            'educational_notes': self.educational_notes,
            'is_active': self.is_active(),
            'time_remaining': self.time_remaining()
        }


class FailureSimulator:
    """
    Comprehensive failure simulation system for educational demonstrations.
    
    This class provides controlled failure injection capabilities that allow
    instructors to demonstrate various failure scenarios and recovery patterns
    during classroom presentations. The system includes:
    
    1. Individual model failure simulation (Claude, GPT, Nova)
    2. Provider-level failure scenarios
    3. Comprehensive logging for educational analysis
    4. Administrative controls for demonstration management
    5. Integration with health monitoring and routing systems
    
    The simulator demonstrates enterprise-grade reliability testing patterns
    while maintaining educational value for understanding distributed systems.
    """
    
    def __init__(self, health_monitor: ModelHealthMonitor, router: IntelligentModelRouter):
        """
        Initialize failure simulation system with system integration.
        
        Args:
            health_monitor: Health monitoring system for integration
            router: Intelligent router for failover demonstration
        """
        self.health_monitor = health_monitor
        self.router = router
        self.active_simulations: Dict[str, FailureSimulation] = {}
        self.simulation_history: List[FailureSimulation] = []
        self.lock = Lock()  # Thread safety for concurrent access
        
        # Educational demonstration scenarios
        self.demo_scenarios = self._initialize_demo_scenarios()
        
        logger.info("Initialized FailureSimulator for educational demonstrations")
        logger.info(f"Available demo scenarios: {len(self.demo_scenarios)}")
    
    def _initialize_demo_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """
        Initialize predefined demonstration scenarios for classroom use.
        
        These scenarios provide instructors with ready-to-use failure
        simulations that demonstrate specific reliability patterns.
        
        Returns:
            Dictionary of demo scenarios with configuration
        """
        scenarios = {
            "claude_outage": {
                "name": "Anthropic Claude Outage",
                "description": "Simulate complete Claude model unavailability",
                "educational_focus": "Demonstrates failover from Claude to GPT/Nova models",
                "models": [ModelType.CLAUDE_3_5_SONNET.value, ModelType.CLAUDE_3_HAIKU.value],
                "failure_type": FailureType.MODEL_UNAVAILABLE,
                "duration": 300,  # 5 minutes
                "intensity": 1.0
            },
            
            "gpt_degraded": {
                "name": "Meta Llama Performance Degradation",
                "description": "Simulate high latency in Llama models",
                "educational_focus": "Shows how routing adapts to performance issues",
                "models": [ModelType.GPT_4O.value, ModelType.GPT_4O_MINI.value],
                "failure_type": FailureType.HIGH_LATENCY,
                "duration": 180,  # 3 minutes
                "intensity": 0.7
            },
            
            "nova_intermittent": {
                "name": "AWS Nova Intermittent Failures",
                "description": "Simulate random failures in Nova models",
                "educational_focus": "Demonstrates circuit breaker pattern activation",
                "models": [ModelType.NOVA_PRO.value, ModelType.NOVA_LITE.value, ModelType.NOVA_MICRO.value],
                "failure_type": FailureType.INTERMITTENT_ERRORS,
                "duration": 240,  # 4 minutes
                "intensity": 0.5
            },
            
            "multi_provider_cascade": {
                "name": "Multi-Provider Cascade Failure",
                "description": "Simulate failures across multiple providers",
                "educational_focus": "Shows system behavior under extreme conditions",
                "models": [
                    ModelType.CLAUDE_3_HAIKU.value,
                    ModelType.GPT_4O_MINI.value,
                    ModelType.NOVA_LITE.value
                ],
                "failure_type": FailureType.MODEL_UNAVAILABLE,
                "duration": 120,  # 2 minutes
                "intensity": 1.0
            },
            
            "rate_limiting_demo": {
                "name": "Rate Limiting Demonstration",
                "description": "Simulate rate limiting across all providers",
                "educational_focus": "Shows load balancing under capacity constraints",
                "models": "all",  # Special case for all models
                "failure_type": FailureType.RATE_LIMITED,
                "duration": 150,  # 2.5 minutes
                "intensity": 0.6
            }
        }
        
        return scenarios
    
    def start_model_failure(self, model_id: str, failure_type: FailureType,
                           duration_seconds: int = 300, intensity: float = 1.0,
                           description: str = "", educational_notes: str = "") -> str:
        """
        Start failure simulation for a specific model.
        
        This method demonstrates controlled failure injection with comprehensive
        logging for educational analysis of system behavior under failure conditions.
        
        Args:
            model_id: Model to simulate failure for
            failure_type: Type of failure to simulate
            duration_seconds: How long the failure should last
            intensity: Failure intensity (0.0 to 1.0)
            description: Human-readable description
            educational_notes: Educational context for the simulation
            
        Returns:
            Simulation ID for tracking and management
            
        Raises:
            ValueError: If model_id is invalid or simulation already active
        """
        # Validate model ID
        if model_id not in self.router.model_capabilities:
            raise ValueError(f"Invalid model ID: {model_id}")
        
        # Check for existing simulation
        with self.lock:
            if model_id in self.active_simulations:
                existing = self.active_simulations[model_id]
                if existing.is_active():
                    raise ValueError(f"Failure simulation already active for {model_id}")
        
        # Get model configuration
        model_config = self.router.model_capabilities[model_id]
        provider = model_config.provider
        
        # Create simulation
        simulation = FailureSimulation(
            model_id=model_id,
            provider=provider,
            failure_type=failure_type,
            start_time=time.time(),
            duration_seconds=duration_seconds,
            intensity=intensity,
            description=description or f"{failure_type.value} simulation for {model_id}",
            educational_notes=educational_notes
        )
        
        # Store simulation
        with self.lock:
            self.active_simulations[model_id] = simulation
            self.simulation_history.append(simulation)
        
        # Log educational information
        logger.info(f"=== FAILURE SIMULATION STARTED ===")
        logger.info(f"Model: {model_id} ({provider.value})")
        logger.info(f"Failure Type: {failure_type.value}")
        logger.info(f"Duration: {duration_seconds} seconds")
        logger.info(f"Intensity: {intensity}")
        logger.info(f"Description: {simulation.description}")
        if educational_notes:
            logger.info(f"Educational Notes: {educational_notes}")
        
        # Apply failure effects immediately
        self._apply_failure_effects(simulation)
        
        simulation_id = f"{model_id}_{int(simulation.start_time)}"
        logger.info(f"Simulation ID: {simulation_id}")
        
        return simulation_id
    
    def start_provider_failure(self, provider: ModelProvider, failure_type: FailureType,
                              duration_seconds: int = 300, intensity: float = 1.0,
                              description: str = "", educational_notes: str = "") -> List[str]:
        """
        Start failure simulation for all models from a specific provider.
        
        This method demonstrates provider-level failure scenarios, showing
        how the system handles complete provider outages.
        
        Args:
            provider: Provider to simulate failure for
            failure_type: Type of failure to simulate
            duration_seconds: How long the failure should last
            intensity: Failure intensity (0.0 to 1.0)
            description: Human-readable description
            educational_notes: Educational context for the simulation
            
        Returns:
            List of simulation IDs for all affected models
        """
        # Get all models for the provider
        provider_models = [
            model_id for model_id, config in self.router.model_capabilities.items()
            if config.provider == provider
        ]
        
        if not provider_models:
            raise ValueError(f"No models found for provider {provider.value}")
        
        logger.info(f"=== PROVIDER FAILURE SIMULATION STARTED ===")
        logger.info(f"Provider: {provider.value}")
        logger.info(f"Affected models: {len(provider_models)}")
        logger.info(f"Models: {', '.join(provider_models)}")
        
        # Start simulation for each model
        simulation_ids = []
        for model_id in provider_models:
            try:
                sim_id = self.start_model_failure(
                    model_id=model_id,
                    failure_type=failure_type,
                    duration_seconds=duration_seconds,
                    intensity=intensity,
                    description=description or f"{provider.value} provider {failure_type.value}",
                    educational_notes=educational_notes
                )
                simulation_ids.append(sim_id)
            except ValueError as e:
                logger.warning(f"Could not start simulation for {model_id}: {e}")
        
        logger.info(f"Started {len(simulation_ids)} model simulations for {provider.value}")
        return simulation_ids
    
    def start_demo_scenario(self, scenario_name: str) -> List[str]:
        """
        Start a predefined demonstration scenario.
        
        This method provides instructors with easy-to-use demonstration
        scenarios that showcase specific reliability patterns.
        
        Args:
            scenario_name: Name of the demo scenario to start
            
        Returns:
            List of simulation IDs for tracking
            
        Raises:
            ValueError: If scenario name is invalid
        """
        if scenario_name not in self.demo_scenarios:
            available = ', '.join(self.demo_scenarios.keys())
            raise ValueError(f"Unknown scenario '{scenario_name}'. Available: {available}")
        
        scenario = self.demo_scenarios[scenario_name]
        
        logger.info(f"=== DEMO SCENARIO STARTED ===")
        logger.info(f"Scenario: {scenario['name']}")
        logger.info(f"Description: {scenario['description']}")
        logger.info(f"Educational Focus: {scenario['educational_focus']}")
        
        simulation_ids = []
        
        # Handle special case for "all" models
        if scenario['models'] == "all":
            target_models = list(self.router.model_capabilities.keys())
        else:
            target_models = scenario['models']
        
        # Start simulations for each target model
        for model_id in target_models:
            try:
                sim_id = self.start_model_failure(
                    model_id=model_id,
                    failure_type=scenario['failure_type'],
                    duration_seconds=scenario['duration'],
                    intensity=scenario['intensity'],
                    description=f"{scenario['name']} - {model_id}",
                    educational_notes=scenario['educational_focus']
                )
                simulation_ids.append(sim_id)
            except ValueError as e:
                logger.warning(f"Could not start scenario simulation for {model_id}: {e}")
        
        logger.info(f"Demo scenario '{scenario_name}' started with {len(simulation_ids)} simulations")
        return simulation_ids
    
    def _apply_failure_effects(self, simulation: FailureSimulation):
        """
        Apply the effects of a failure simulation to the system.
        
        This method demonstrates how different failure types affect
        system behavior and routing decisions.
        
        Args:
            simulation: The failure simulation to apply
        """
        model_id = simulation.model_id
        failure_type = simulation.failure_type
        intensity = simulation.intensity
        
        logger.info(f"Applying {failure_type.value} effects to {model_id} (intensity: {intensity})")
        
        if failure_type == FailureType.MODEL_UNAVAILABLE:
            # Force circuit breaker open for complete unavailability
            if model_id in self.health_monitor.circuit_breakers:
                breaker = self.health_monitor.circuit_breakers[model_id]
                breaker.failure_count = breaker.config.failure_threshold
                breaker.record_failure()
                logger.info(f"Forced circuit breaker OPEN for {model_id}")
        
        elif failure_type == FailureType.CIRCUIT_BREAKER_OPEN:
            # Directly open the circuit breaker
            if model_id in self.health_monitor.circuit_breakers:
                breaker = self.health_monitor.circuit_breakers[model_id]
                breaker.state = breaker.state.OPEN
                breaker.last_failure_time = time.time()
                logger.info(f"Circuit breaker manually opened for {model_id}")
        
        # Invalidate health cache to force fresh checks
        self.health_monitor.health_cache.invalidate(model_id)
        
        logger.info(f"Failure effects applied for {model_id}")
    
    def stop_simulation(self, model_id: str) -> bool:
        """
        Stop an active failure simulation for a specific model.
        
        This method allows instructors to manually end simulations
        during demonstrations for educational control.
        
        Args:
            model_id: Model to stop simulation for
            
        Returns:
            True if simulation was stopped, False if none was active
        """
        with self.lock:
            if model_id not in self.active_simulations:
                logger.warning(f"No active simulation found for {model_id}")
                return False
            
            simulation = self.active_simulations[model_id]
            
            # Remove from active simulations
            del self.active_simulations[model_id]
            
            # Reset circuit breaker if it was affected
            if model_id in self.health_monitor.circuit_breakers:
                self.health_monitor.reset_circuit_breaker(model_id)
            
            # Invalidate health cache to allow recovery
            self.health_monitor.health_cache.invalidate(model_id)
            
            logger.info(f"=== FAILURE SIMULATION STOPPED ===")
            logger.info(f"Model: {model_id}")
            logger.info(f"Simulation type: {simulation.failure_type.value}")
            logger.info(f"Duration: {time.time() - simulation.start_time:.1f} seconds")
            
            return True
    
    def stop_all_simulations(self) -> int:
        """
        Stop all active failure simulations.
        
        This method provides a quick way to reset the system to normal
        operation during demonstrations.
        
        Returns:
            Number of simulations that were stopped
        """
        with self.lock:
            active_models = list(self.active_simulations.keys())
        
        stopped_count = 0
        for model_id in active_models:
            if self.stop_simulation(model_id):
                stopped_count += 1
        
        logger.info(f"Stopped {stopped_count} active failure simulations")
        return stopped_count
    
    def cleanup_expired_simulations(self) -> int:
        """
        Clean up expired simulations and restore normal operation.
        
        This method automatically handles simulation expiration,
        demonstrating how systems recover from temporary failures.
        
        Returns:
            Number of expired simulations cleaned up
        """
        expired_models = []
        
        with self.lock:
            for model_id, simulation in self.active_simulations.items():
                if not simulation.is_active():
                    expired_models.append(model_id)
        
        cleaned_count = 0
        for model_id in expired_models:
            if self.stop_simulation(model_id):
                cleaned_count += 1
                logger.info(f"Cleaned up expired simulation for {model_id}")
        
        if cleaned_count > 0:
            logger.info(f"Cleaned up {cleaned_count} expired failure simulations")
        
        return cleaned_count
    
    def is_model_simulated_failure(self, model_id: str) -> Optional[FailureSimulation]:
        """
        Check if a model is currently under failure simulation.
        
        This method allows other system components to check for
        active simulations and adjust behavior accordingly.
        
        Args:
            model_id: Model to check
            
        Returns:
            FailureSimulation if active, None otherwise
        """
        with self.lock:
            simulation = self.active_simulations.get(model_id)
            if simulation and simulation.is_active():
                return simulation
            return None
    
    def simulate_failure_effect(self, model_id: str, operation: str) -> bool:
        """
        Simulate the effect of a failure on a specific operation.
        
        This method determines whether an operation should fail based on
        active failure simulations, demonstrating probabilistic failure patterns.
        
        Args:
            model_id: Model being used for the operation
            operation: Type of operation (e.g., 'health_check', 'query')
            
        Returns:
            True if the operation should fail, False if it should succeed
        """
        simulation = self.is_model_simulated_failure(model_id)
        if not simulation:
            return False  # No simulation active, operation succeeds
        
        failure_type = simulation.failure_type
        intensity = simulation.intensity
        
        # Log simulation effect for educational purposes
        logger.debug(f"Evaluating {failure_type.value} simulation for {model_id} "
                    f"operation '{operation}' (intensity: {intensity})")
        
        if failure_type == FailureType.MODEL_UNAVAILABLE:
            # Complete failure based on intensity
            should_fail = random.random() < intensity
            if should_fail:
                logger.info(f"SIMULATION: {model_id} unavailable for {operation}")
            return should_fail
        
        elif failure_type == FailureType.INTERMITTENT_ERRORS:
            # Random failures based on intensity
            should_fail = random.random() < (intensity * 0.3)  # 30% max failure rate
            if should_fail:
                logger.info(f"SIMULATION: {model_id} intermittent error for {operation}")
            return should_fail
        
        elif failure_type == FailureType.RATE_LIMITED:
            # Simulate rate limiting
            should_fail = random.random() < (intensity * 0.4)  # 40% max rate limit
            if should_fail:
                logger.info(f"SIMULATION: {model_id} rate limited for {operation}")
            return should_fail
        
        elif failure_type == FailureType.CIRCUIT_BREAKER_OPEN:
            # Circuit breaker is open, all requests fail
            logger.info(f"SIMULATION: {model_id} circuit breaker open for {operation}")
            return True
        
        # For other failure types (HIGH_LATENCY, TIMEOUT), don't fail the operation
        # but log the simulation effect
        if failure_type in [FailureType.HIGH_LATENCY, FailureType.TIMEOUT]:
            logger.info(f"SIMULATION: {model_id} experiencing {failure_type.value} for {operation}")
        
        return False
    
    def get_active_simulations(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all active failure simulations.
        
        Returns:
            Dictionary mapping model IDs to simulation information
        """
        # Clean up expired simulations first
        self.cleanup_expired_simulations()
        
        with self.lock:
            return {
                model_id: simulation.to_dict()
                for model_id, simulation in self.active_simulations.items()
                if simulation.is_active()
            }
    
    def get_simulation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history of failure simulations for analysis.
        
        Args:
            limit: Maximum number of historical simulations to return
            
        Returns:
            List of simulation dictionaries
        """
        with self.lock:
            recent_simulations = self.simulation_history[-limit:]
            return [sim.to_dict() for sim in recent_simulations]
    
    def get_demo_scenarios(self) -> Dict[str, Dict[str, Any]]:
        """
        Get available demonstration scenarios for instructor use.
        
        Returns:
            Dictionary of available demo scenarios
        """
        return self.demo_scenarios.copy()
    
    def get_simulation_status(self) -> Dict[str, Any]:
        """
        Get comprehensive status of the failure simulation system.
        
        Returns:
            Dictionary with simulation system status and statistics
        """
        active_sims = self.get_active_simulations()
        
        # Count simulations by type and provider
        type_counts = {}
        provider_counts = {}
        
        for sim_info in active_sims.values():
            failure_type = sim_info['failure_type']
            provider = sim_info['provider']
            
            type_counts[failure_type] = type_counts.get(failure_type, 0) + 1
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
        
        return {
            'timestamp': time.time(),
            'active_simulations': len(active_sims),
            'total_simulations_run': len(self.simulation_history),
            'simulations_by_type': type_counts,
            'simulations_by_provider': provider_counts,
            'available_scenarios': list(self.demo_scenarios.keys()),
            'active_simulation_details': active_sims
        }


# Integration with health monitoring
class SimulationAwareHealthMonitor(ModelHealthMonitor):
    """
    Health monitor that integrates with failure simulation system.
    
    This class extends the base health monitor to be aware of active
    failure simulations, providing realistic failure behavior during
    educational demonstrations.
    """
    
    def __init__(self, adapter, cache_ttl_seconds: int = 300):
        """Initialize with failure simulation integration"""
        super().__init__(adapter, cache_ttl_seconds)
        self.failure_simulator: Optional[FailureSimulator] = None
    
    def set_failure_simulator(self, simulator: FailureSimulator):
        """Set the failure simulator for integration"""
        self.failure_simulator = simulator
        logger.info("Health monitor integrated with failure simulator")
    
    def check_model_health(self, model_id: str, use_cache: bool = True, 
                          force_check: bool = False) -> HealthCheckResult:
        """
        Enhanced health check that considers active failure simulations.
        
        This method demonstrates how failure simulations affect health
        monitoring results during educational demonstrations.
        """
        # Check for active failure simulation
        if self.failure_simulator:
            simulation = self.failure_simulator.is_model_simulated_failure(model_id)
            if simulation:
                # Simulate failure effect on health check
                should_fail = self.failure_simulator.simulate_failure_effect(model_id, 'health_check')
                
                if should_fail:
                    # Return simulated failure result
                    config = self.adapter.get_model_config(model_id)
                    logger.info(f"SIMULATION: Health check failed for {model_id} "
                               f"({simulation.failure_type.value})")
                    
                    return HealthCheckResult(
                        model_id=model_id,
                        provider=config.provider if config else ModelProvider.ANTHROPIC,
                        status=HealthStatus.UNHEALTHY,
                        response_time_ms=0,
                        error_message=f"Simulated {simulation.failure_type.value} failure",
                        test_query="simulated_failure",
                        tokens_used=0
                    )
        
        # Proceed with normal health check
        return super().check_model_health(model_id, use_cache, force_check)


# Convenience functions for easy integration
def create_failure_simulator(health_monitor: ModelHealthMonitor, 
                           router: IntelligentModelRouter) -> FailureSimulator:
    """
    Create a configured failure simulator with system integration.
    
    Args:
        health_monitor: Health monitoring system
        router: Intelligent router system
        
    Returns:
        Configured FailureSimulator instance
    """
    simulator = FailureSimulator(health_monitor, router)
    
    # If using simulation-aware health monitor, set up integration
    if isinstance(health_monitor, SimulationAwareHealthMonitor):
        health_monitor.set_failure_simulator(simulator)
    
    return simulator


# Example usage and demonstration
if __name__ == "__main__":
    """
    Demonstration of the failure simulation system.
    
    This example shows how instructors can use the failure simulator
    to demonstrate various reliability patterns during classroom presentations.
    """
    
    print("=== Failure Simulation System Demo ===")
    print("Demonstrating controlled failure injection for educational purposes")
    
    try:
        # This would normally be integrated with the full system
        print("\n1. Available Demo Scenarios:")
        
        # Create a mock simulator to show scenarios
        from bedrock_adapter import BedrockConverseAdapter
        from health_monitor import ModelHealthMonitor
        from router import IntelligentModelRouter
        
        adapter = BedrockConverseAdapter()
        health_monitor = ModelHealthMonitor(adapter)
        router = IntelligentModelRouter(adapter, health_monitor)
        simulator = FailureSimulator(health_monitor, router)
        
        scenarios = simulator.get_demo_scenarios()
        for name, scenario in scenarios.items():
            print(f"   {name}:")
            print(f"     Description: {scenario['description']}")
            print(f"     Educational Focus: {scenario['educational_focus']}")
            print(f"     Duration: {scenario['duration']} seconds")
        
        print("\n2. Failure Types Available:")
        for failure_type in FailureType:
            print(f"   - {failure_type.value}: {failure_type.name}")
        
        print("\n3. Educational Benefits:")
        print("   - Demonstrates circuit breaker patterns")
        print("   - Shows intelligent failover routing")
        print("   - Illustrates system recovery behavior")
        print("   - Provides controlled failure scenarios")
        print("   - Enables hands-on reliability education")
        
        print("\n4. Integration Features:")
        print("   - Health monitoring integration")
        print("   - Router failover demonstration")
        print("   - Comprehensive educational logging")
        print("   - Administrative control interface")
        print("   - Automatic cleanup and recovery")
        
        print("\n=== Demo Complete ===")
        print("The failure simulator provides controlled failure injection")
        print("for comprehensive reliability education and demonstration.")
        
    except Exception as e:
        print(f"Demo error: {e}")
        print("Note: Full functionality requires integrated system components")