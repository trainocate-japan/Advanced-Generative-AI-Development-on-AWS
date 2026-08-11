"""
Monitoring utilities for GenAI Model Selection Demo

This module provides utilities for custom metrics collection, CloudWatch integration,
and educational monitoring features for classroom demonstration.
"""

import json
import time
import boto3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class CustomMetricsCollector:
    """
    Collects and publishes custom metrics for educational demonstration.
    
    This class provides methods to track provider usage, failover events,
    performance metrics, and other educational indicators that help students
    understand system behavior.
    """
    
    def __init__(self, namespace: str = "GenAIDemo"):
        """
        Initialize the metrics collector.
        
        Args:
            namespace: CloudWatch namespace for custom metrics
        """
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
        self.metrics_buffer = []
        
    def record_provider_selection(self, provider: str, query_type: str = "general"):
        """
        Record when a provider is selected for a query.
        
        Args:
            provider: Name of the selected provider (anthropic, openai, nova)
            query_type: Type of query for categorization
        """
        metric_data = {
            'MetricName': 'ProviderSelection',
            'Dimensions': [
                {'Name': 'Provider', 'Value': provider},
                {'Name': 'QueryType', 'Value': query_type}
            ],
            'Value': 1,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.info(f"Provider selected: {provider} for {query_type} query")
        
    def record_failover_event(self, from_provider: str, to_provider: str, reason: str):
        """
        Record a provider failover event.
        
        Args:
            from_provider: Provider that failed
            to_provider: Provider that took over
            reason: Reason for failover
        """
        metric_data = {
            'MetricName': 'FailoverEvent',
            'Dimensions': [
                {'Name': 'FromProvider', 'Value': from_provider},
                {'Name': 'ToProvider', 'Value': to_provider},
                {'Name': 'Reason', 'Value': reason}
            ],
            'Value': 1,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.warning(f"Provider failover: {from_provider} -> {to_provider} (reason: {reason})")
        
    def record_circuit_breaker_event(self, provider: str, action: str):
        """
        Record circuit breaker state changes.
        
        Args:
            provider: Provider affected by circuit breaker
            action: Action taken (opened, closed, half_open)
        """
        metric_data = {
            'MetricName': 'CircuitBreakerEvent',
            'Dimensions': [
                {'Name': 'Provider', 'Value': provider},
                {'Name': 'Action', 'Value': action}
            ],
            'Value': 1,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.error(f"Circuit breaker {action}: {provider}")
        
    def record_token_usage(self, provider: str, tokens_used: int, query_type: str = "general"):
        """
        Record token usage for cost and performance tracking.
        
        Args:
            provider: Provider that processed the request
            tokens_used: Number of tokens consumed
            query_type: Type of query for categorization
        """
        metric_data = {
            'MetricName': 'TokenUsage',
            'Dimensions': [
                {'Name': 'Provider', 'Value': provider},
                {'Name': 'QueryType', 'Value': query_type}
            ],
            'Value': tokens_used,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.info(f"Token usage: {tokens_used} tokens used by {provider}")
        
    def record_response_time(self, provider: str, response_time_ms: float, query_type: str = "general"):
        """
        Record response time for performance analysis.
        
        Args:
            provider: Provider that processed the request
            response_time_ms: Response time in milliseconds
            query_type: Type of query for categorization
        """
        metric_data = {
            'MetricName': 'ResponseTime',
            'Dimensions': [
                {'Name': 'Provider', 'Value': provider},
                {'Name': 'QueryType', 'Value': query_type}
            ],
            'Value': response_time_ms,
            'Unit': 'Milliseconds',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.info(f"Response time: {response_time_ms:.2f} ms from {provider}")
        
    def record_error_event(self, provider: str, error_type: str, error_message: str):
        """
        Record error events for reliability analysis.
        
        Args:
            provider: Provider where error occurred
            error_type: Type of error (timeout, auth, rate_limit, etc.)
            error_message: Error message for debugging
        """
        metric_data = {
            'MetricName': 'ErrorEvent',
            'Dimensions': [
                {'Name': 'Provider', 'Value': provider},
                {'Name': 'ErrorType', 'Value': error_type}
            ],
            'Value': 1,
            'Unit': 'Count',
            'Timestamp': datetime.utcnow()
        }
        
        self.metrics_buffer.append(metric_data)
        
        # Log for educational transparency
        logger.error(f"Error event: {error_type} from {provider} - {error_message}")
        
    def flush_metrics(self):
        """
        Publish all buffered metrics to CloudWatch.
        
        This method should be called at the end of request processing to ensure
        all metrics are published.
        """
        if not self.metrics_buffer:
            return
            
        try:
            # CloudWatch allows up to 20 metrics per put_metric_data call
            batch_size = 20
            for i in range(0, len(self.metrics_buffer), batch_size):
                batch = self.metrics_buffer[i:i + batch_size]
                
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=batch
                )
                
            logger.info(f"Published {len(self.metrics_buffer)} custom metrics to CloudWatch")
            self.metrics_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to publish metrics to CloudWatch: {str(e)}")
            # Don't raise exception to avoid breaking main functionality


class HealthMetricsCollector:
    """
    Collects health and availability metrics for provider monitoring.
    
    This class tracks provider health status, response times, and availability
    for educational demonstration of system reliability patterns.
    """
    
    def __init__(self, namespace: str = "GenAIDemo/Health"):
        self.cloudwatch = boto3.client('cloudwatch')
        self.namespace = namespace
        
    def record_health_check(self, provider: str, is_healthy: bool, response_time_ms: float):
        """
        Record the result of a provider health check.
        
        Args:
            provider: Provider being checked
            is_healthy: Whether the provider is healthy
            response_time_ms: Time taken for health check
        """
        try:
            metrics = [
                {
                    'MetricName': 'ProviderHealth',
                    'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                    'Value': 1 if is_healthy else 0,
                    'Unit': 'None',
                    'Timestamp': datetime.utcnow()
                },
                {
                    'MetricName': 'HealthCheckResponseTime',
                    'Dimensions': [{'Name': 'Provider', 'Value': provider}],
                    'Value': response_time_ms,
                    'Unit': 'Milliseconds',
                    'Timestamp': datetime.utcnow()
                }
            ]
            
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=metrics
            )
            
            status = "healthy" if is_healthy else "unhealthy"
            logger.info(f"Health check: {provider} is {status} (response time: {response_time_ms:.2f}ms)")
            
        except Exception as e:
            logger.error(f"Failed to record health check metrics: {str(e)}")


class DashboardManager:
    """
    Manages CloudWatch dashboards for educational demonstration.
    
    This class provides methods to create and update dashboards that show
    real-time system behavior for classroom demonstration.
    """
    
    def __init__(self, project_name: str = "genai-model-selection-demo"):
        self.cloudwatch = boto3.client('cloudwatch')
        self.project_name = project_name
        
    def create_educational_dashboard(self, lambda_function_name: str, api_gateway_name: str):
        """
        Create a comprehensive dashboard for educational demonstration.
        
        Args:
            lambda_function_name: Name of the Lambda function to monitor
            api_gateway_name: Name of the API Gateway to monitor
        """
        dashboard_body = {
            "widgets": [
                {
                    "type": "metric",
                    "x": 0, "y": 0, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["GenAIDemo", "ProviderSelection", "Provider", "anthropic"],
                            [".", ".", ".", "openai"],
                            [".", ".", ".", "nova"]
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": boto3.Session().region_name,
                        "title": "Provider Selection Distribution",
                        "period": 300,
                        "stat": "Sum"
                    }
                },
                {
                    "type": "metric",
                    "x": 12, "y": 0, "width": 12, "height": 6,
                    "properties": {
                        "metrics": [
                            ["GenAIDemo", "ResponseTime", "Provider", "anthropic"],
                            [".", ".", ".", "openai"],
                            [".", ".", ".", "nova"]
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": boto3.Session().region_name,
                        "title": "Response Time by Provider",
                        "period": 300,
                        "stat": "Average"
                    }
                },
                {
                    "type": "metric",
                    "x": 0, "y": 6, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [
                            ["GenAIDemo", "FailoverEvent"],
                            [".", "CircuitBreakerEvent"]
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": boto3.Session().region_name,
                        "title": "Reliability Events",
                        "period": 300,
                        "stat": "Sum"
                    }
                },
                {
                    "type": "metric",
                    "x": 8, "y": 6, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [
                            ["GenAIDemo", "TokenUsage", "Provider", "anthropic"],
                            [".", ".", ".", "openai"],
                            [".", ".", ".", "nova"]
                        ],
                        "view": "timeSeries",
                        "stacked": True,
                        "region": boto3.Session().region_name,
                        "title": "Token Usage by Provider",
                        "period": 300,
                        "stat": "Sum"
                    }
                },
                {
                    "type": "metric",
                    "x": 16, "y": 6, "width": 8, "height": 6,
                    "properties": {
                        "metrics": [
                            ["GenAIDemo/Health", "ProviderHealth", "Provider", "anthropic"],
                            [".", ".", ".", "openai"],
                            [".", ".", ".", "nova"]
                        ],
                        "view": "timeSeries",
                        "stacked": False,
                        "region": boto3.Session().region_name,
                        "title": "Provider Health Status",
                        "period": 300,
                        "stat": "Average"
                    }
                }
            ]
        }
        
        try:
            self.cloudwatch.put_dashboard(
                DashboardName=f"{self.project_name}-educational",
                DashboardBody=json.dumps(dashboard_body)
            )
            
            logger.info(f"Created educational dashboard: {self.project_name}-educational")
            
        except Exception as e:
            logger.error(f"Failed to create dashboard: {str(e)}")


class AlertManager:
    """
    Manages CloudWatch alarms for educational demonstration.
    
    This class creates and manages alarms that demonstrate monitoring
    and alerting best practices for GenAI systems.
    """
    
    def __init__(self, project_name: str = "genai-model-selection-demo"):
        self.cloudwatch = boto3.client('cloudwatch')
        self.project_name = project_name
        
    def create_educational_alarms(self, sns_topic_arn: Optional[str] = None):
        """
        Create alarms for educational demonstration.
        
        Args:
            sns_topic_arn: Optional SNS topic for alarm notifications
        """
        alarms = [
            {
                'AlarmName': f"{self.project_name}-high-failover-rate",
                'AlarmDescription': "Too many provider failover events",
                'MetricName': 'FailoverEvent',
                'Namespace': 'GenAIDemo',
                'Statistic': 'Sum',
                'Period': 300,
                'EvaluationPeriods': 1,
                'Threshold': 3,
                'ComparisonOperator': 'GreaterThanThreshold'
            },
            {
                'AlarmName': f"{self.project_name}-circuit-breaker-triggered",
                'AlarmDescription': "Circuit breaker has been triggered",
                'MetricName': 'CircuitBreakerEvent',
                'Namespace': 'GenAIDemo',
                'Statistic': 'Sum',
                'Period': 300,
                'EvaluationPeriods': 1,
                'Threshold': 1,
                'ComparisonOperator': 'GreaterThanOrEqualToThreshold'
            },
            {
                'AlarmName': f"{self.project_name}-high-response-time",
                'AlarmDescription': "Average response time is too high",
                'MetricName': 'ResponseTime',
                'Namespace': 'GenAIDemo',
                'Statistic': 'Average',
                'Period': 300,
                'EvaluationPeriods': 2,
                'Threshold': 10000,
                'ComparisonOperator': 'GreaterThanThreshold'
            }
        ]
        
        for alarm_config in alarms:
            try:
                alarm_params = {
                    **alarm_config,
                    'ActionsEnabled': True,
                    'TreatMissingData': 'notBreaching'
                }
                
                if sns_topic_arn:
                    alarm_params['AlarmActions'] = [sns_topic_arn]
                    
                self.cloudwatch.put_metric_alarm(**alarm_params)
                logger.info(f"Created alarm: {alarm_config['AlarmName']}")
                
            except Exception as e:
                logger.error(f"Failed to create alarm {alarm_config['AlarmName']}: {str(e)}")


# Global metrics collector instance
metrics_collector = CustomMetricsCollector()
health_metrics_collector = HealthMetricsCollector()


def get_metrics_collector() -> CustomMetricsCollector:
    """Get the global metrics collector instance."""
    return metrics_collector


def get_health_metrics_collector() -> HealthMetricsCollector:
    """Get the global health metrics collector instance."""
    return health_metrics_collector


# Utility functions for easy integration
def record_provider_usage(provider: str, tokens: int, response_time_ms: float):
    """
    Convenience function to record provider usage metrics.
    
    Args:
        provider: Provider name
        tokens: Tokens used
        response_time_ms: Response time in milliseconds
    """
    collector = get_metrics_collector()
    collector.record_provider_selection(provider)
    collector.record_token_usage(provider, tokens)
    collector.record_response_time(provider, response_time_ms)


def record_failover(from_provider: str, to_provider: str, reason: str = "health_check_failed"):
    """
    Convenience function to record failover events.
    
    Args:
        from_provider: Provider that failed
        to_provider: Provider that took over
        reason: Reason for failover
    """
    collector = get_metrics_collector()
    collector.record_failover_event(from_provider, to_provider, reason)


def flush_all_metrics():
    """Flush all buffered metrics to CloudWatch."""
    get_metrics_collector().flush_metrics()


if __name__ == "__main__":
    # Test the monitoring utilities
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    print("Testing monitoring utilities...")
    
    # Test metrics collection
    collector = CustomMetricsCollector("TestNamespace")
    collector.record_provider_selection("anthropic", "general")
    collector.record_token_usage("anthropic", 150, "general")
    collector.record_response_time("anthropic", 1250.5, "general")
    collector.record_failover_event("anthropic", "openai", "timeout")
    
    print("Metrics recorded successfully")
    
    # In a real deployment, you would call flush_metrics() to publish to CloudWatch
    # collector.flush_metrics()
    
    print("Monitoring utilities test completed")