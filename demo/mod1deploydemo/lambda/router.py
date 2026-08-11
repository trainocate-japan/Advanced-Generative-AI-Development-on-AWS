"""
Intelligent Model Selection and Routing Logic

This module implements sophisticated routing algorithms for GenAI model selection
across Anthropic Claude, Meta Llama, and AWS Nova models. The router provides
intelligent load balancing, failover logic, and comprehensive logging for
educational demonstration purposes.

The routing system demonstrates key architectural patterns:
1. Strategy pattern for different selection algorithms
2. Load balancing across multiple providers
3. Intelligent failover with health-aware routing
4. Comprehensive logging for educational analysis
5. Provider-agnostic abstraction through unified interfaces

This implementation showcases how complex routing decisions can be made
transparent and educational while maintaining production-grade reliability.
"""

import time
import json
import logging
import random
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque
import hashlib

# Import from our unified adapter and health monitoring
from bedrock_adapter import (
    BedrockConverseAdapter, ModelProvider, ModelType, ModelResponse,
    ConversationMessage, create_user_message
)
from health_monitor import ModelHealthMonitor, HealthStatus, HealthCheckResult

# Configure logging for educational demonstration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """
    Routing strategies for intelligent model selection.
    
    Each strategy represents a different approach to model selection,
    demonstrating various optimization criteria and decision-making patterns.
    """
    PERFORMANCE_OPTIMIZED = "performance"    # Fastest response time
    COST_OPTIMIZED = "cost"                 # Lowest cost per token
    CAPABILITY_OPTIMIZED = "capability"     # Best model for complex tasks
    BALANCED = "balanced"                   # Balance of performance, cost, capability
    ROUND_ROBIN = "round_robin"            # Equal distribution across models
    WEIGHTED_ROUND_ROBIN = "weighted_rr"   # Weighted distribution based on capacity
    LEAST_CONNECTIONS = "least_connections" # Route to least busy model
    HEALTH_AWARE = "health_aware"          # Prioritize healthy models
    PROVIDER_SPECIFIC = "provider_specific" # Route to specific provider
    ADAPTIVE = "adaptive"                  # Learn and adapt based on performance


@dataclass
class QueryCharacteristics:
    """
    Analysis of query characteristics for intelligent routing decisions.
    
    This dataclass captures various aspects of a query that inform
    routing decisions, demonstrating how different query types can
    be optimally matched to appropriate models.
    """
    query_text: str
    length: int
    complexity_score: float  # 0.0 (simple) to 1.0 (complex)
    estimated_tokens: int
    requires_reasoning: bool
    requires_creativity: bool
    requires_code: bool
    requires_analysis: bool
    language: str = "en"
    priority: str = "normal"  # low, normal, high, critical
    
    def __post_init__(self):
        """Calculate derived characteristics"""
        if self.length == 0:
            self.length = len(self.query_text)
        
        if self.estimated_tokens == 0:
            # Rough estimation: ~4 characters per token
            self.estimated_tokens = max(self.length // 4, 1)


@dataclass
class ModelCapabilities:
    """
    Comprehensive model capability profile for routing decisions.
    
    This dataclass defines the strengths and characteristics of each model,
    enabling intelligent matching between query requirements and model capabilities.
    """
    model_id: str
    provider: ModelProvider
    
    # Performance characteristics
    avg_response_time_ms: int
    max_tokens: int
    tokens_per_second: float
    
    # Cost characteristics (relative scores 0.0-1.0, lower is cheaper)
    cost_per_input_token: float
    cost_per_output_token: float
    cost_score: float  # Overall cost ranking
    
    # Capability scores (0.0-1.0, higher is better)
    reasoning_capability: float
    creativity_capability: float
    code_capability: float
    analysis_capability: float
    general_capability: float
    
    # Operational characteristics
    reliability_score: float  # Historical reliability
    capacity_weight: float    # Relative capacity for load balancing
    timeout_minutes: int      # Maximum allowed timeout
    
    def get_capability_score(self, query_chars: QueryCharacteristics) -> float:
        """
        Calculate capability match score for a specific query.
        
        This method demonstrates how query characteristics can be matched
        against model capabilities to find the optimal routing decision.
        
        Args:
            query_chars: Query characteristics to match against
            
        Returns:
            Capability match score (0.0-1.0, higher is better match)
        """
        score = self.general_capability * 0.3  # Base capability
        
        # Add specific capability bonuses based on query requirements
        if query_chars.requires_reasoning:
            score += self.reasoning_capability * 0.3
        
        if query_chars.requires_creativity:
            score += self.creativity_capability * 0.2
        
        if query_chars.requires_code:
            score += self.code_capability * 0.3
        
        if query_chars.requires_analysis:
            score += self.analysis_capability * 0.2
        
        # Adjust for query complexity
        complexity_bonus = query_chars.complexity_score * 0.1
        score += complexity_bonus
        
        return min(score, 1.0)  # Cap at 1.0


@dataclass
class RoutingDecision:
    """
    Comprehensive routing decision with detailed reasoning for educational purposes.
    
    This dataclass captures not just the routing decision but also the complete
    reasoning process, making the system's decision-making transparent for
    educational demonstration.
    """
    selected_model_id: str
    selected_provider: ModelProvider
    strategy_used: RoutingStrategy
    decision_timestamp: float = field(default_factory=time.time)
    
    # Decision reasoning (for educational logging)
    query_characteristics: Optional[QueryCharacteristics] = None
    considered_models: List[str] = field(default_factory=list)
    model_scores: Dict[str, float] = field(default_factory=dict)
    health_factors: Dict[str, str] = field(default_factory=dict)
    load_factors: Dict[str, float] = field(default_factory=dict)
    decision_reasoning: List[str] = field(default_factory=list)
    
    # Performance predictions
    estimated_response_time_ms: int = 0
    estimated_cost_score: float = 0.0
    confidence_score: float = 0.0
    
    def add_reasoning(self, reason: str):
        """Add reasoning step for educational logging"""
        self.decision_reasoning.append(reason)
        logger.debug(f"Routing reasoning: {reason}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'selected_model_id': self.selected_model_id,
            'selected_provider': self.selected_provider.value,
            'strategy_used': self.strategy_used.value,
            'decision_timestamp': self.decision_timestamp,
            'query_length': self.query_characteristics.length if self.query_characteristics else 0,
            'query_complexity': self.query_characteristics.complexity_score if self.query_characteristics else 0,
            'considered_models': self.considered_models,
            'model_scores': self.model_scores,
            'health_factors': self.health_factors,
            'load_factors': self.load_factors,
            'decision_reasoning': self.decision_reasoning,
            'estimated_response_time_ms': self.estimated_response_time_ms,
            'estimated_cost_score': self.estimated_cost_score,
            'confidence_score': self.confidence_score
        }


class LoadBalancer:
    """
    Sophisticated load balancing implementation for GenAI model routing.
    
    This class implements multiple load balancing algorithms with comprehensive
    tracking and educational logging. It demonstrates how traffic can be
    distributed across multiple models while considering health, capacity,
    and performance characteristics.
    """
    
    def __init__(self):
        """Initialize load balancer with tracking structures"""
        self.request_counts: Dict[str, int] = defaultdict(int)
        self.active_connections: Dict[str, int] = defaultdict(int)
        self.response_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.last_selected: Dict[RoutingStrategy, str] = {}
        self.weighted_counters: Dict[str, float] = defaultdict(float)
        
        logger.info("Initialized LoadBalancer with comprehensive tracking")
    
    def round_robin_select(self, available_models: List[str], 
                          strategy: RoutingStrategy) -> str:
        """
        Simple round-robin selection across available models.
        
        This method demonstrates the simplest load balancing approach,
        providing equal distribution across all available models.
        
        Args:
            available_models: List of available model IDs
            strategy: Routing strategy (for tracking)
            
        Returns:
            Selected model ID
        """
        if not available_models:
            raise ValueError("No available models for round-robin selection")
        
        # Get last selected model for this strategy
        last_selected = self.last_selected.get(strategy)
        
        if last_selected and last_selected in available_models:
            # Find next model in rotation
            current_index = available_models.index(last_selected)
            next_index = (current_index + 1) % len(available_models)
            selected = available_models[next_index]
        else:
            # Start with first available model
            selected = available_models[0]
        
        # Update tracking
        self.last_selected[strategy] = selected
        self.request_counts[selected] += 1
        
        logger.debug(f"Round-robin selected {selected} "
                    f"(request #{self.request_counts[selected]})")
        
        return selected
    
    def weighted_round_robin_select(self, model_capabilities: Dict[str, ModelCapabilities],
                                   available_models: List[str]) -> str:
        """
        Weighted round-robin selection based on model capacity.
        
        This method demonstrates advanced load balancing where models
        with higher capacity receive proportionally more traffic.
        
        Args:
            model_capabilities: Model capability profiles
            available_models: List of available model IDs
            
        Returns:
            Selected model ID
        """
        if not available_models:
            raise ValueError("No available models for weighted round-robin")
        
        # Calculate total weight and find model with highest weighted counter
        total_weight = sum(
            model_capabilities[model_id].capacity_weight 
            for model_id in available_models
        )
        
        # Find model with lowest weighted counter relative to its weight
        best_model = None
        best_ratio = float('inf')
        
        for model_id in available_models:
            capability = model_capabilities[model_id]
            current_counter = self.weighted_counters[model_id]
            weight_ratio = current_counter / capability.capacity_weight
            
            if weight_ratio < best_ratio:
                best_ratio = weight_ratio
                best_model = model_id
        
        # Update weighted counter
        selected = best_model
        capability = model_capabilities[selected]
        self.weighted_counters[selected] += 1.0 / capability.capacity_weight
        self.request_counts[selected] += 1
        
        logger.debug(f"Weighted round-robin selected {selected} "
                    f"(weight: {capability.capacity_weight}, "
                    f"counter: {self.weighted_counters[selected]:.2f})")
        
        return selected
    
    def least_connections_select(self, available_models: List[str]) -> str:
        """
        Select model with fewest active connections.
        
        This method demonstrates connection-based load balancing,
        routing new requests to the least busy models.
        
        Args:
            available_models: List of available model IDs
            
        Returns:
            Selected model ID
        """
        if not available_models:
            raise ValueError("No available models for least connections")
        
        # Find model with minimum active connections
        selected = min(available_models, 
                      key=lambda model_id: self.active_connections[model_id])
        
        # Update tracking
        self.active_connections[selected] += 1
        self.request_counts[selected] += 1
        
        logger.debug(f"Least connections selected {selected} "
                    f"({self.active_connections[selected]} active connections)")
        
        return selected
    
    def record_request_start(self, model_id: str):
        """Record the start of a request for connection tracking"""
        self.active_connections[model_id] += 1
        logger.debug(f"Request started for {model_id} "
                    f"({self.active_connections[model_id]} active)")
    
    def record_request_complete(self, model_id: str, response_time_ms: int):
        """Record the completion of a request with performance metrics"""
        self.active_connections[model_id] = max(0, self.active_connections[model_id] - 1)
        self.response_times[model_id].append(response_time_ms)
        
        logger.debug(f"Request completed for {model_id} "
                    f"({response_time_ms}ms, {self.active_connections[model_id]} active)")
    
    def get_load_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get comprehensive load balancing statistics for monitoring.
        
        Returns:
            Dictionary with detailed load balancing metrics
        """
        stats = {}
        
        for model_id in self.request_counts.keys():
            response_times_list = list(self.response_times[model_id])
            avg_response_time = (sum(response_times_list) / len(response_times_list) 
                               if response_times_list else 0)
            
            stats[model_id] = {
                'total_requests': self.request_counts[model_id],
                'active_connections': self.active_connections[model_id],
                'avg_response_time_ms': int(avg_response_time),
                'weighted_counter': self.weighted_counters[model_id],
                'recent_response_times': response_times_list[-10:]  # Last 10 requests
            }
        
        return stats


class QueryAnalyzer:
    """
    Sophisticated query analysis for intelligent routing decisions.
    
    This class implements advanced natural language processing techniques
    to analyze query characteristics and requirements, enabling optimal
    model selection based on query content and complexity.
    """
    
    def __init__(self):
        """Initialize query analyzer with pattern recognition"""
        # Keywords for different capability requirements
        self.reasoning_keywords = {
            'analyze', 'compare', 'evaluate', 'assess', 'judge', 'reason',
            'logic', 'logical', 'deduce', 'infer', 'conclude', 'prove',
            'argument', 'evidence', 'because', 'therefore', 'thus', 'hence'
        }
        
        self.creativity_keywords = {
            'create', 'generate', 'invent', 'design', 'imagine', 'creative',
            'story', 'poem', 'novel', 'artistic', 'original', 'innovative',
            'brainstorm', 'ideate', 'conceptualize', 'visualize'
        }
        
        self.code_keywords = {
            'code', 'program', 'function', 'algorithm', 'script', 'debug',
            'python', 'javascript', 'java', 'sql', 'html', 'css', 'api',
            'database', 'framework', 'library', 'syntax', 'compile'
        }
        
        self.analysis_keywords = {
            'data', 'statistics', 'trend', 'pattern', 'correlation', 'insight',
            'metrics', 'performance', 'optimization', 'efficiency', 'research',
            'study', 'investigation', 'examination', 'review'
        }
        
        # Complexity indicators
        self.complexity_indicators = {
            'multi_step': {'step by step', 'first then', 'process', 'procedure'},
            'technical': {'technical', 'advanced', 'complex', 'sophisticated'},
            'detailed': {'detailed', 'comprehensive', 'thorough', 'in-depth'},
            'comparative': {'compare', 'contrast', 'versus', 'vs', 'difference'}
        }
        
        logger.info("Initialized QueryAnalyzer with comprehensive pattern recognition")
    
    def analyze_query(self, query_text: str) -> QueryCharacteristics:
        """
        Perform comprehensive analysis of query characteristics.
        
        This method demonstrates advanced query analysis techniques,
        extracting multiple dimensions of query requirements for
        intelligent routing decisions.
        
        Args:
            query_text: The query text to analyze
            
        Returns:
            QueryCharacteristics with detailed analysis results
        """
        query_lower = query_text.lower()
        query_words = set(query_lower.split())
        
        # Basic characteristics
        length = len(query_text)
        estimated_tokens = max(length // 4, 1)  # Rough estimation
        
        # Capability requirements analysis
        requires_reasoning = bool(query_words.intersection(self.reasoning_keywords))
        requires_creativity = bool(query_words.intersection(self.creativity_keywords))
        requires_code = bool(query_words.intersection(self.code_keywords))
        requires_analysis = bool(query_words.intersection(self.analysis_keywords))
        
        # Complexity score calculation
        complexity_factors = {
            'length': min(length / 1000, 1.0) * 0.2,  # Longer queries are more complex
            'reasoning': 0.3 if requires_reasoning else 0.0,
            'creativity': 0.2 if requires_creativity else 0.0,
            'code': 0.25 if requires_code else 0.0,
            'analysis': 0.25 if requires_analysis else 0.0,
        }
        
        # Add complexity indicators
        for indicator_type, keywords in self.complexity_indicators.items():
            if any(keyword in query_lower for keyword in keywords):
                complexity_factors[indicator_type] = 0.15
        
        complexity_score = min(sum(complexity_factors.values()), 1.0)
        
        # Determine priority based on urgency keywords
        priority = "normal"
        if any(word in query_lower for word in ['urgent', 'asap', 'immediately', 'critical']):
            priority = "high"
        elif any(word in query_lower for word in ['when convenient', 'no rush', 'eventually']):
            priority = "low"
        
        characteristics = QueryCharacteristics(
            query_text=query_text,
            length=length,
            complexity_score=complexity_score,
            estimated_tokens=estimated_tokens,
            requires_reasoning=requires_reasoning,
            requires_creativity=requires_creativity,
            requires_code=requires_code,
            requires_analysis=requires_analysis,
            priority=priority
        )
        
        # Log analysis results for educational purposes
        logger.info(f"Query analysis completed:")
        logger.info(f"  Length: {length} chars, ~{estimated_tokens} tokens")
        logger.info(f"  Complexity: {complexity_score:.2f}")
        logger.info(f"  Requirements: reasoning={requires_reasoning}, "
                   f"creativity={requires_creativity}, code={requires_code}, "
                   f"analysis={requires_analysis}")
        logger.info(f"  Priority: {priority}")
        
        return characteristics


class IntelligentModelRouter:
    """
    Comprehensive intelligent routing system for GenAI model selection.
    
    This class implements the complete routing intelligence, combining:
    - Query analysis and characteristic extraction
    - Model capability matching and scoring
    - Health-aware routing with failover logic
    - Multiple load balancing strategies
    - Comprehensive logging for educational demonstration
    - Adaptive learning from routing performance
    
    The router demonstrates enterprise-grade routing patterns while
    maintaining educational transparency in decision-making processes.
    """
    
    def __init__(self, adapter: BedrockConverseAdapter, health_monitor: ModelHealthMonitor):
        """
        Initialize intelligent model router with comprehensive capabilities.
        
        Args:
            adapter: Unified Bedrock adapter for model interactions
            health_monitor: Health monitoring system for availability tracking
        """
        self.adapter = adapter
        self.health_monitor = health_monitor
        self.query_analyzer = QueryAnalyzer()
        self.load_balancer = LoadBalancer()
        
        # Initialize model capability profiles
        self.model_capabilities = self._initialize_model_capabilities()
        
        # Routing history for adaptive learning
        self.routing_history: List[RoutingDecision] = []
        self.performance_history: Dict[str, List[float]] = defaultdict(list)
        
        # Provider preferences for different strategies
        self.provider_preferences = {
            RoutingStrategy.PERFORMANCE_OPTIMIZED: [ModelProvider.OPENAI, ModelProvider.ANTHROPIC, ModelProvider.NOVA],
            RoutingStrategy.COST_OPTIMIZED: [ModelProvider.NOVA, ModelProvider.ANTHROPIC, ModelProvider.OPENAI],
            RoutingStrategy.CAPABILITY_OPTIMIZED: [ModelProvider.ANTHROPIC, ModelProvider.OPENAI, ModelProvider.NOVA]
        }
        
        logger.info(f"Initialized IntelligentModelRouter with {len(self.model_capabilities)} model profiles")
        logger.info("Routing strategies available: " + 
                   ", ".join([strategy.value for strategy in RoutingStrategy]))
    
    def _initialize_model_capabilities(self) -> Dict[str, ModelCapabilities]:
        """
        Initialize comprehensive model capability profiles.
        
        This method defines the characteristics and capabilities of each model,
        providing the foundation for intelligent routing decisions.
        
        Returns:
            Dictionary mapping model IDs to their capability profiles
        """
        capabilities = {}
        
        # Anthropic Claude 3 Sonnet - excellent reasoning and analysis
        capabilities[ModelType.CLAUDE_3_SONNET.value] = ModelCapabilities(
            model_id=ModelType.CLAUDE_3_SONNET.value,
            provider=ModelProvider.ANTHROPIC,
            avg_response_time_ms=2500,
            max_tokens=4096,
            tokens_per_second=15.0,
            cost_per_input_token=0.003,
            cost_per_output_token=0.015,
            cost_score=0.7,
            reasoning_capability=0.90,
            creativity_capability=0.85,
            code_capability=0.85,
            analysis_capability=0.90,
            general_capability=0.88,
            reliability_score=0.95,
            capacity_weight=1.0,
            timeout_minutes=5
        )
        
        # OpenAI GPT OSS model - open source GPT model with strong performance
        capabilities[ModelType.GPT_OSS_120B.value] = ModelCapabilities(
            model_id=ModelType.GPT_OSS_120B.value,
            provider=ModelProvider.OPENAI,
            avg_response_time_ms=2200,
            max_tokens=4096,
            tokens_per_second=18.0,
            cost_per_input_token=0.0018,
            cost_per_output_token=0.009,
            cost_score=0.45,
            reasoning_capability=0.88,
            creativity_capability=0.85,
            code_capability=0.90,
            analysis_capability=0.87,
            general_capability=0.88,
            reliability_score=0.92,
            capacity_weight=1.2,
            timeout_minutes=5
        )
        
        # AWS Nova models - AWS native with extended capabilities
        capabilities[ModelType.NOVA_PRO.value] = ModelCapabilities(
            model_id=ModelType.NOVA_PRO.value,
            provider=ModelProvider.NOVA,
            avg_response_time_ms=3000,
            max_tokens=4096,
            tokens_per_second=12.0,
            cost_per_input_token=0.0008,
            cost_per_output_token=0.0032,
            cost_score=0.5,
            reasoning_capability=0.80,
            creativity_capability=0.75,
            code_capability=0.75,
            analysis_capability=0.85,
            general_capability=0.80,
            reliability_score=0.88,
            capacity_weight=0.8,
            timeout_minutes=60
        )
        
        capabilities[ModelType.NOVA_LITE.value] = ModelCapabilities(
            model_id=ModelType.NOVA_LITE.value,
            provider=ModelProvider.NOVA,
            avg_response_time_ms=1800,
            max_tokens=4096,
            tokens_per_second=20.0,
            cost_per_input_token=0.0002,
            cost_per_output_token=0.0008,
            cost_score=0.4,
            reasoning_capability=0.70,
            creativity_capability=0.65,
            code_capability=0.65,
            analysis_capability=0.70,
            general_capability=0.70,
            reliability_score=0.87,
            capacity_weight=1.3,
            timeout_minutes=60
        )
        
        capabilities[ModelType.NOVA_MICRO.value] = ModelCapabilities(
            model_id=ModelType.NOVA_MICRO.value,
            provider=ModelProvider.NOVA,
            avg_response_time_ms=800,
            max_tokens=2048,
            tokens_per_second=35.0,
            cost_per_input_token=0.000035,
            cost_per_output_token=0.00014,
            cost_score=0.15,
            reasoning_capability=0.50,
            creativity_capability=0.55,
            code_capability=0.50,
            analysis_capability=0.50,
            general_capability=0.50,
            reliability_score=0.85,
            capacity_weight=2.5,
            timeout_minutes=60
        )
        
        return capabilities
    
    def get_healthy_models(self, min_health_status: HealthStatus = HealthStatus.DEGRADED) -> List[str]:
        """
        Get list of models that meet minimum health requirements.
        
        This method demonstrates health-aware routing by filtering
        models based on their current health status.
        
        Args:
            min_health_status: Minimum acceptable health status
            
        Returns:
            List of model IDs that meet health requirements
        """
        health_results = self.health_monitor.check_all_models_health()
        healthy_models = []
        
        for model_id, health_result in health_results.items():
            if health_result.status.value >= min_health_status.value:
                healthy_models.append(model_id)
            else:
                logger.warning(f"Excluding unhealthy model {model_id}: {health_result.status.value}")
        
        logger.info(f"Found {len(healthy_models)} healthy models out of {len(health_results)} total")
        return healthy_models
    
    def calculate_model_scores(self, query_chars: QueryCharacteristics, 
                              strategy: RoutingStrategy,
                              available_models: List[str]) -> Dict[str, float]:
        """
        Calculate routing scores for available models based on strategy and query.
        
        This method demonstrates the core scoring algorithm that evaluates
        each model's suitability for a specific query and routing strategy.
        
        Args:
            query_chars: Query characteristics
            strategy: Routing strategy to apply
            available_models: List of available model IDs
            
        Returns:
            Dictionary mapping model IDs to their routing scores
        """
        scores = {}
        
        for model_id in available_models:
            if model_id not in self.model_capabilities:
                logger.warning(f"No capability profile for {model_id}, skipping")
                continue
            
            capability = self.model_capabilities[model_id]
            score = 0.0
            
            if strategy == RoutingStrategy.PERFORMANCE_OPTIMIZED:
                # Prioritize speed and responsiveness
                speed_score = 1.0 - (capability.avg_response_time_ms / 5000)  # Normalize to 5s max
                throughput_score = capability.tokens_per_second / 40.0  # Normalize to 40 tps max
                score = (speed_score * 0.6 + throughput_score * 0.4) * capability.reliability_score
                
            elif strategy == RoutingStrategy.COST_OPTIMIZED:
                # Prioritize low cost
                cost_score = 1.0 - capability.cost_score  # Invert cost (lower cost = higher score)
                efficiency_score = capability.tokens_per_second / (capability.cost_score + 0.1)
                score = (cost_score * 0.7 + efficiency_score * 0.3) * capability.reliability_score
                
            elif strategy == RoutingStrategy.CAPABILITY_OPTIMIZED:
                # Prioritize model capabilities matching query requirements
                capability_score = capability.get_capability_score(query_chars)
                general_score = capability.general_capability
                score = (capability_score * 0.8 + general_score * 0.2) * capability.reliability_score
                
            elif strategy == RoutingStrategy.BALANCED:
                # Balance performance, cost, and capability
                speed_score = 1.0 - (capability.avg_response_time_ms / 5000)
                cost_score = 1.0 - capability.cost_score
                capability_score = capability.get_capability_score(query_chars)
                score = (speed_score * 0.3 + cost_score * 0.3 + capability_score * 0.4) * capability.reliability_score
                
            elif strategy == RoutingStrategy.HEALTH_AWARE:
                # Prioritize healthy models with good performance
                health_result = self.health_monitor.check_model_health(model_id)
                health_score = 1.0 if health_result.is_healthy() else 0.3
                performance_score = 1.0 - (capability.avg_response_time_ms / 5000)
                score = (health_score * 0.6 + performance_score * 0.4) * capability.reliability_score
                
            else:
                # Default to general capability
                score = capability.general_capability * capability.reliability_score
            
            scores[model_id] = max(score, 0.0)  # Ensure non-negative scores
        
        return scores
    
    def route_query(self, query_text: str, 
                   strategy: RoutingStrategy = RoutingStrategy.BALANCED,
                   preferred_provider: Optional[ModelProvider] = None,
                   exclude_models: Optional[Set[str]] = None) -> RoutingDecision:
        """
        Perform intelligent routing decision for a query.
        
        This method implements the complete routing workflow, demonstrating
        how multiple factors are considered to make optimal routing decisions.
        
        Args:
            query_text: The query to route
            strategy: Routing strategy to apply
            preferred_provider: Optional provider preference
            exclude_models: Optional set of models to exclude
            
        Returns:
            RoutingDecision with complete reasoning and selected model
        """
        start_time = time.time()
        
        # Analyze query characteristics
        query_chars = self.query_analyzer.analyze_query(query_text)
        
        # Initialize routing decision
        decision = RoutingDecision(
            selected_model_id="",
            selected_provider=ModelProvider.ANTHROPIC,  # Will be updated
            strategy_used=strategy,
            query_characteristics=query_chars
        )
        
        decision.add_reasoning(f"Starting routing for {len(query_text)} character query")
        decision.add_reasoning(f"Query complexity: {query_chars.complexity_score:.2f}")
        decision.add_reasoning(f"Strategy: {strategy.value}")
        
        # Get healthy models
        healthy_models = self.get_healthy_models()
        if not healthy_models:
            raise RuntimeError("No healthy models available for routing")
        
        decision.considered_models = healthy_models.copy()
        decision.add_reasoning(f"Found {len(healthy_models)} healthy models")
        
        # Apply provider preference filter
        if preferred_provider:
            provider_models = [
                model_id for model_id in healthy_models
                if self.model_capabilities[model_id].provider == preferred_provider
            ]
            if provider_models:
                healthy_models = provider_models
                decision.add_reasoning(f"Filtered to {len(healthy_models)} models from {preferred_provider.value}")
            else:
                decision.add_reasoning(f"No healthy models from {preferred_provider.value}, using all healthy models")
        
        # Apply exclusion filter
        if exclude_models:
            healthy_models = [model_id for model_id in healthy_models if model_id not in exclude_models]
            decision.add_reasoning(f"Excluded {len(exclude_models)} models, {len(healthy_models)} remaining")
        
        if not healthy_models:
            raise RuntimeError("No models available after filtering")
        
        # Handle load balancing strategies
        if strategy in [RoutingStrategy.ROUND_ROBIN, RoutingStrategy.WEIGHTED_ROUND_ROBIN, 
                       RoutingStrategy.LEAST_CONNECTIONS]:
            
            if strategy == RoutingStrategy.ROUND_ROBIN:
                selected_model = self.load_balancer.round_robin_select(healthy_models, strategy)
                decision.add_reasoning("Used round-robin load balancing")
                
            elif strategy == RoutingStrategy.WEIGHTED_ROUND_ROBIN:
                selected_model = self.load_balancer.weighted_round_robin_select(
                    self.model_capabilities, healthy_models)
                decision.add_reasoning("Used weighted round-robin based on model capacity")
                
            elif strategy == RoutingStrategy.LEAST_CONNECTIONS:
                selected_model = self.load_balancer.least_connections_select(healthy_models)
                decision.add_reasoning("Selected model with least active connections")
        
        else:
            # Score-based selection
            model_scores = self.calculate_model_scores(query_chars, strategy, healthy_models)
            decision.model_scores = model_scores
            
            if not model_scores:
                raise RuntimeError("No models received valid scores")
            
            # Select highest scoring model
            selected_model = max(model_scores.keys(), key=lambda k: model_scores[k])
            best_score = model_scores[selected_model]
            
            decision.add_reasoning(f"Scored {len(model_scores)} models, best score: {best_score:.3f}")
            
            # Log top 3 scoring models for educational purposes
            sorted_scores = sorted(model_scores.items(), key=lambda x: x[1], reverse=True)
            for i, (model_id, score) in enumerate(sorted_scores[:3]):
                provider = self.model_capabilities[model_id].provider.value
                decision.add_reasoning(f"#{i+1}: {model_id} ({provider}) - {score:.3f}")
        
        # Finalize decision
        selected_capability = self.model_capabilities[selected_model]
        decision.selected_model_id = selected_model
        decision.selected_provider = selected_capability.provider
        decision.estimated_response_time_ms = selected_capability.avg_response_time_ms
        decision.estimated_cost_score = selected_capability.cost_score
        
        # Calculate confidence score
        if hasattr(decision, 'model_scores') and decision.model_scores:
            scores = list(decision.model_scores.values())
            if len(scores) > 1:
                best_score = max(scores)
                second_best = sorted(scores, reverse=True)[1]
                decision.confidence_score = (best_score - second_best) / best_score
            else:
                decision.confidence_score = 1.0
        else:
            decision.confidence_score = 0.8  # Default for load balancing strategies
        
        # Record health factors
        for model_id in healthy_models:
            health_result = self.health_monitor.check_model_health(model_id, use_cache=True)
            decision.health_factors[model_id] = health_result.status.value
        
        # Record load factors
        load_stats = self.load_balancer.get_load_statistics()
        for model_id in healthy_models:
            if model_id in load_stats:
                decision.load_factors[model_id] = load_stats[model_id]['active_connections']
        
        # Final logging
        routing_time = (time.time() - start_time) * 1000
        decision.add_reasoning(f"Routing completed in {routing_time:.1f}ms")
        
        logger.info(f"Routing decision: {selected_model} ({selected_capability.provider.value}) "
                   f"using {strategy.value} strategy (confidence: {decision.confidence_score:.2f})")
        
        # Store in history for adaptive learning
        self.routing_history.append(decision)
        if len(self.routing_history) > 1000:  # Keep last 1000 decisions
            self.routing_history = self.routing_history[-1000:]
        
        return decision
    
    def record_routing_performance(self, decision: RoutingDecision, 
                                  actual_response_time_ms: int, success: bool):
        """
        Record actual routing performance for adaptive learning.
        
        This method enables the router to learn from actual performance
        and adapt its decision-making over time.
        
        Args:
            decision: The original routing decision
            actual_response_time_ms: Actual response time observed
            success: Whether the request was successful
        """
        model_id = decision.selected_model_id
        
        # Record performance metrics
        self.performance_history[model_id].append(actual_response_time_ms)
        if len(self.performance_history[model_id]) > 100:
            self.performance_history[model_id] = self.performance_history[model_id][-100:]
        
        # Update load balancer
        self.load_balancer.record_request_complete(model_id, actual_response_time_ms)
        
        # Calculate prediction accuracy
        estimated_time = decision.estimated_response_time_ms
        if estimated_time > 0:
            accuracy = 1.0 - abs(actual_response_time_ms - estimated_time) / estimated_time
            accuracy = max(0.0, min(1.0, accuracy))  # Clamp to [0, 1]
        else:
            accuracy = 0.5  # Default for missing estimates
        
        logger.info(f"Routing performance recorded for {model_id}: "
                   f"actual={actual_response_time_ms}ms, "
                   f"estimated={estimated_time}ms, "
                   f"accuracy={accuracy:.2f}, success={success}")
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive routing statistics for monitoring and analysis.
        
        Returns:
            Dictionary with detailed routing performance metrics
        """
        stats = {
            'total_routing_decisions': len(self.routing_history),
            'strategy_distribution': {},
            'provider_distribution': {},
            'model_distribution': {},
            'average_confidence': 0.0,
            'load_balancer_stats': self.load_balancer.get_load_statistics(),
            'performance_trends': {}
        }
        
        if not self.routing_history:
            return stats
        
        # Analyze routing history
        for decision in self.routing_history:
            # Strategy distribution
            strategy = decision.strategy_used.value
            stats['strategy_distribution'][strategy] = stats['strategy_distribution'].get(strategy, 0) + 1
            
            # Provider distribution
            provider = decision.selected_provider.value
            stats['provider_distribution'][provider] = stats['provider_distribution'].get(provider, 0) + 1
            
            # Model distribution
            model = decision.selected_model_id
            stats['model_distribution'][model] = stats['model_distribution'].get(model, 0) + 1
        
        # Calculate average confidence
        confidences = [d.confidence_score for d in self.routing_history if d.confidence_score > 0]
        stats['average_confidence'] = sum(confidences) / len(confidences) if confidences else 0.0
        
        # Performance trends
        for model_id, times in self.performance_history.items():
            if times:
                stats['performance_trends'][model_id] = {
                    'avg_response_time': sum(times) / len(times),
                    'min_response_time': min(times),
                    'max_response_time': max(times),
                    'sample_count': len(times)
                }
        
        return stats


# Convenience functions for easy integration
def create_intelligent_router(region_name: str = "us-east-1") -> IntelligentModelRouter:
    """
    Create a fully configured intelligent model router.
    
    Args:
        region_name: AWS region for Bedrock service
        
    Returns:
        Configured IntelligentModelRouter instance
    """
    from bedrock_adapter import BedrockConverseAdapter
    from health_monitor import ModelHealthMonitor
    
    adapter = BedrockConverseAdapter(region_name=region_name)
    health_monitor = ModelHealthMonitor(adapter)
    return IntelligentModelRouter(adapter, health_monitor)


def quick_route_query(query_text: str, strategy: RoutingStrategy = RoutingStrategy.BALANCED,
                     region_name: str = "us-east-1") -> RoutingDecision:
    """
    Perform quick query routing with default configuration.
    
    Args:
        query_text: Query to route
        strategy: Routing strategy to use
        region_name: AWS region for Bedrock service
        
    Returns:
        RoutingDecision with selected model and reasoning
    """
    router = create_intelligent_router(region_name)
    return router.route_query(query_text, strategy)


# Example usage and demonstration
if __name__ == "__main__":
    """
    Demonstration of the intelligent model routing system.
    
    This example shows how sophisticated routing decisions are made
    across Claude, GPT, and Nova models with comprehensive logging.
    """
    
    print("=== Intelligent Model Routing System Demo ===")
    print("Demonstrating sophisticated routing across Anthropic, Meta Llama, and Nova models")
    
    try:
        # Initialize router
        print("\n1. Initializing Intelligent Router:")
        router = create_intelligent_router(region_name="us-east-1")
        
        print(f"   Configured {len(router.model_capabilities)} model profiles")
        print(f"   Available strategies: {len(RoutingStrategy)} routing algorithms")
        print(f"   Health monitoring: Integrated with circuit breakers")
        print(f"   Load balancing: Multiple algorithms available")
        
        # Demonstrate different routing strategies
        print("\n2. Routing Strategy Demonstrations:")
        
        test_queries = [
            ("Simple question", "What is the capital of France?", RoutingStrategy.COST_OPTIMIZED),
            ("Complex analysis", "Analyze the economic implications of artificial intelligence "
                               "on employment markets over the next decade", RoutingStrategy.CAPABILITY_OPTIMIZED),
            ("Code request", "Write a Python function to implement binary search with error handling",
             RoutingStrategy.BALANCED),
            ("Creative task", "Write a short story about a robot learning to paint",
             RoutingStrategy.PERFORMANCE_OPTIMIZED)
        ]
        
        for description, query, strategy in test_queries:
            print(f"\n   {description} ({strategy.value}):")
            try:
                decision = router.route_query(query, strategy)
                capability = router.model_capabilities[decision.selected_model_id]
                
                print(f"   → Selected: {decision.selected_model_id}")
                print(f"   → Provider: {decision.selected_provider.value}")
                print(f"   → Confidence: {decision.confidence_score:.2f}")
                print(f"   → Est. time: {decision.estimated_response_time_ms}ms")
                print(f"   → Reasoning steps: {len(decision.decision_reasoning)}")
                
                # Show key reasoning
                if decision.decision_reasoning:
                    print(f"   → Key decision: {decision.decision_reasoning[-1]}")
                
            except Exception as e:
                print(f"   → Error: {e}")
        
        # Demonstrate load balancing
        print("\n3. Load Balancing Demonstration:")
        print("   Round-robin distribution across healthy models:")
        
        for i in range(5):
            try:
                decision = router.route_query("Test query", RoutingStrategy.ROUND_ROBIN)
                print(f"   Request {i+1}: {decision.selected_model_id} "
                      f"({decision.selected_provider.value})")
            except Exception as e:
                print(f"   Request {i+1}: Error - {e}")
        
        # Show routing statistics
        print("\n4. Routing Statistics:")
        stats = router.get_routing_statistics()
        print(f"   Total decisions: {stats['total_routing_decisions']}")
        print(f"   Average confidence: {stats['average_confidence']:.2f}")
        
        if stats['provider_distribution']:
            print("   Provider distribution:")
            for provider, count in stats['provider_distribution'].items():
                percentage = (count / stats['total_routing_decisions']) * 100
                print(f"     {provider}: {count} ({percentage:.1f}%)")
        
        print("\n=== Demo Complete ===")
        print("The intelligent router provides sophisticated decision-making")
        print("with comprehensive logging for educational demonstration.")
        
    except Exception as e:
        print(f"Demo error: {e}")
        print("Note: Full functionality requires valid AWS credentials and Bedrock access")