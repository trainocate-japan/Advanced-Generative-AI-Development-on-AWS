#!/usr/bin/env python3
"""
Query Handler Lambda Function

Processes student questions and demonstrates prompt caching by invoking
the Python script three times: baseline (no cache), cache write, and cache hit.
"""

import json
import logging
import os
import re
import time
import base64
from collections import defaultdict
from datetime import datetime, timedelta
import boto3
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime')

# Rate limiting configuration
# Store request timestamps per IP address (in-memory, resets on cold start)
# Format: {ip_address: [timestamp1, timestamp2, ...]}
rate_limit_store: Dict[str, list] = defaultdict(list)
RATE_LIMIT_REQUESTS = 10  # Maximum requests per time window
RATE_LIMIT_WINDOW_SECONDS = 60  # Time window in seconds (1 minute)

# Supported models with caching
SUPPORTED_MODELS = {
    'anthropic.claude-3-5-haiku-20241022-v1:0': {'min_tokens': 2048, 'name': 'Claude 3.5 Haiku'},
    'anthropic.claude-3-5-sonnet-20241022-v2:0': {'min_tokens': 1024, 'name': 'Claude 3.5 Sonnet v2'},
    'amazon.nova-micro-v1:0': {'min_tokens': 1024, 'name': 'Amazon Nova Micro'},
    'amazon.nova-lite-v1:0': {'min_tokens': 1024, 'name': 'Amazon Nova Lite'},
    'amazon.nova-pro-v1:0': {'min_tokens': 1024, 'name': 'Amazon Nova Pro'}
}


def validate_question(question: str) -> Optional[str]:
    """
    Validate and sanitize question input.
    
    Args:
        question: User-provided question string
        
    Returns:
        Error message if validation fails, None if valid
    """
    if not question or not isinstance(question, str):
        return "Question is required and must be a string"
    
    # Strip whitespace
    question = question.strip()
    
    # Check length
    if len(question) < 1:
        return "Question must be at least 1 character"
    
    if len(question) > 500:
        return "Question must not exceed 500 characters"
    
    return None


def sanitize_input(text: str) -> str:
    """
    Sanitize user input to prevent SQL injection and XSS attacks.
    
    Args:
        text: User input text
        
    Returns:
        Sanitized text
    """
    if not isinstance(text, str):
        return ""
    
    # Remove potential SQL injection patterns
    sql_patterns = [
        r"(\bUNION\b|\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b|\bDROP\b|\bCREATE\b|\bALTER\b)",
        r"(--|;|\/\*|\*\/)",
        r"(\bOR\b\s+\d+\s*=\s*\d+|\bAND\b\s+\d+\s*=\s*\d+)"
    ]
    
    sanitized = text
    for pattern in sql_patterns:
        sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
    
    # Remove HTML/script tags for XSS prevention
    sanitized = re.sub(r'<script[^>]*>.*?</script>', '', sanitized, flags=re.IGNORECASE | re.DOTALL)
    sanitized = re.sub(r'<[^>]+>', '', sanitized)
    
    # Remove potentially dangerous characters
    sanitized = sanitized.replace('\x00', '')
    
    return sanitized.strip()


def validate_model_id(model_id: str) -> bool:
    """
    Validate model ID against supported models.
    
    Args:
        model_id: Model identifier to validate
        
    Returns:
        True if model is supported, False otherwise
    """
    return model_id in SUPPORTED_MODELS


def sanitize_error_message(error_msg: str) -> str:
    """
    Sanitize error messages to prevent information disclosure.
    
    Args:
        error_msg: Raw error message
        
    Returns:
        Sanitized error message
    """
    if not isinstance(error_msg, str):
        error_msg = str(error_msg)
    
    # Remove file paths
    sanitized = re.sub(r'/[^\s]+', '[path]', error_msg)
    
    # Remove potential credentials or tokens
    sanitized = re.sub(r'(key|token|password|secret)[=:]\s*\S+', r'\1=[REDACTED]', sanitized, flags=re.IGNORECASE)
    
    # Remove IP addresses
    sanitized = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', sanitized)
    
    # Truncate if too long
    if len(sanitized) > 200:
        sanitized = sanitized[:200] + '...'
    
    return sanitized


def check_rate_limit(ip_address: str) -> tuple[bool, int]:
    """
    Check if the request from the given IP address exceeds rate limits.
    
    Implements a sliding window rate limiter that allows RATE_LIMIT_REQUESTS
    requests per RATE_LIMIT_WINDOW_SECONDS.
    
    Args:
        ip_address: IP address of the requester
        
    Returns:
        Tuple of (is_allowed, retry_after_seconds)
        - is_allowed: True if request is within rate limit, False otherwise
        - retry_after_seconds: Number of seconds to wait before retrying (0 if allowed)
    """
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)
    
    # Get request timestamps for this IP
    timestamps = rate_limit_store[ip_address]
    
    # Remove timestamps outside the current window
    timestamps[:] = [ts for ts in timestamps if ts > cutoff_time]
    
    # Check if rate limit is exceeded
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        # Calculate retry-after time (time until oldest request expires)
        oldest_timestamp = timestamps[0]
        retry_after = int((oldest_timestamp + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS) - current_time).total_seconds()) + 1
        logger.warning(f"Rate limit exceeded for IP {ip_address}: {len(timestamps)} requests in window")
        return False, retry_after
    
    # Add current request timestamp
    timestamps.append(current_time)
    
    logger.info(f"Rate limit check passed for IP {ip_address}: {len(timestamps)}/{RATE_LIMIT_REQUESTS} requests")
    return True, 0


def invoke_bedrock_directly(question: str, model_id: str, document_content: str, 
                           use_cache: bool = False, max_retries: int = 3) -> Dict[str, Any]:
    """
    Invoke Bedrock directly with retry logic and exponential backoff.
    
    Args:
        question: User question
        model_id: Bedrock model ID
        document_content: Document content
        use_cache: Whether to use cache checkpoint
        max_retries: Maximum number of retry attempts
        
    Returns:
        Dictionary with success, content, response_time, and usage metrics
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Invoking Bedrock (attempt {attempt + 1}/{max_retries}): use_cache={use_cache}")
            
            start_time = time.time()
            
            # Build messages based on cache usage
            if use_cache:
                # Use cache checkpoint syntax
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": document_content
                            },
                            {
                                "cachePoint": {
                                    "type": "default"
                                }
                            },
                            {
                                "text": f"\n\nBased on the document above, {question}"
                            }
                        ]
                    }
                ]
            else:
                # Regular message without cache checkpoint
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "text": f"{document_content}\n\nBased on the document above, {question}"
                            }
                        ]
                    }
                ]
            
            # Invoke Bedrock
            response = bedrock_runtime.converse(
                modelId=model_id,
                messages=messages,
                inferenceConfig={
                    "maxTokens": 1000,
                    "temperature": 0.7
                }
            )
            
            end_time = time.time()
            response_time = end_time - start_time
            
            # Extract response content and usage
            content = response['output']['message']['content'][0]['text']
            usage = response.get('usage', {})
            
            cache_read_tokens = usage.get('cacheReadInputTokens', 0)
            cache_write_tokens = usage.get('cacheWriteInputTokens', 0)
            
            logger.info(f"Bedrock response received: {response_time:.2f}s")
            logger.info(f"Tokens - input: {usage.get('inputTokens', 0)}, output: {usage.get('outputTokens', 0)}, "
                       f"cache_read: {cache_read_tokens}, cache_write: {cache_write_tokens}")
            
            return {
                'success': True,
                'content': content,
                'response_time': response_time,
                'usage': usage,
                'cache_read_tokens': cache_read_tokens,
                'cache_write_tokens': cache_write_tokens
            }
            
        except Exception as e:
            error_msg = sanitize_error_message(str(e))
            logger.error(f"Bedrock invocation failed: {error_msg}")
            last_error = error_msg
            
            # Check if error is retryable (throttling, temporary service issues)
            if 'throttl' in str(e).lower() or 'rate' in str(e).lower():
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    logger.info(f"Retrying after {wait_time}s due to throttling...")
                    time.sleep(wait_time)
                    continue
            
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 1
                logger.info(f"Retrying after {wait_time}s...")
                time.sleep(wait_time)
                continue
            
            return {
                'success': False,
                'error': f'Bedrock invocation failed: {error_msg}',
                'response_time': 0
            }
    
    # If we exhausted all retries
    return {
        'success': False,
        'error': f'Failed after {max_retries} attempts: {last_error}',
        'response_time': 0
    }


def invoke_python_script(question: str, model_id: str, document_content: str, use_cache: bool = False) -> Dict[str, Any]:
    """
    Invoke Bedrock directly (replaces subprocess approach).
    
    This is a wrapper around invoke_bedrock_directly for backward compatibility.
    
    Args:
        question: User question
        model_id: Bedrock model ID
        document_content: Document content
        use_cache: Whether to use cache checkpoint
        
    Returns:
        Dictionary with success, content, response_time, and usage metrics
    """
    return invoke_bedrock_directly(question, model_id, document_content, use_cache)


def extract_uploaded_document(body: Dict[str, Any]) -> Optional[str]:
    """
    Extract uploaded document content from request body.
    
    Args:
        body: Parsed request body
        
    Returns:
        Document content if uploaded, None otherwise
    """
    uploaded_doc = body.get('document')
    if not uploaded_doc:
        return None
    
    # Handle base64 encoded content
    if isinstance(uploaded_doc, str):
        try:
            # Try to decode if it's base64
            if uploaded_doc.startswith('data:'):
                # Remove data URL prefix (e.g., "data:text/plain;base64,")
                uploaded_doc = uploaded_doc.split(',', 1)[1]
            decoded = base64.b64decode(uploaded_doc).decode('utf-8')
            return decoded
        except Exception as e:
            logger.warning(f"Failed to decode uploaded document: {str(e)}")
            # If not base64, treat as plain text
            return uploaded_doc
    
    return None


def validate_document_content(content: str) -> Optional[str]:
    """
    Validate uploaded document content.
    
    Args:
        content: Document content to validate
        
    Returns:
        Error message if validation fails, None if valid
    """
    if not content or not isinstance(content, str):
        return "Document content is required and must be text"
    
    # Check length (max 100KB)
    if len(content) > 100000:
        return "Document must not exceed 100KB"
    
    # Check minimum length (at least 100 characters for meaningful content)
    if len(content) < 100:
        return "Document must be at least 100 characters"
    
    return None


def load_document_from_s3(bucket_name: str, document_key: str = 'Shareholderletter97.txt') -> Dict[str, Any]:
    """
    Load 1997 Amazon shareholder letter from S3 with fallback content.
    
    Args:
        bucket_name: S3 bucket name containing the document
        document_key: S3 object key for the document
        
    Returns:
        Dictionary containing:
            - content: Document text
            - source: 'file' or 'fallback'
            - word_count: Number of words
            - estimated_tokens: Estimated token count (word_count * 1.3)
            - meets_minimum: Whether document meets 1024 token minimum
    """
    try:
        # Try to load document from S3
        logger.info(f"Loading document from s3://{bucket_name}/{document_key}")
        response = s3_client.get_object(Bucket=bucket_name, Key=document_key)
        content = response['Body'].read().decode('utf-8')
        
        word_count = len(content.split())
        estimated_tokens = int(word_count * 1.3)
        
        logger.info(f"Document loaded: {word_count} words, ~{estimated_tokens} tokens")
        
        return {
            'content': content,
            'source': 'file',
            'word_count': word_count,
            'estimated_tokens': estimated_tokens,
            'meets_minimum': estimated_tokens >= 1024
        }
        
    except Exception as e:
        logger.warning(f"Failed to load document from S3: {str(e)}")
        logger.info("Using fallback content")
        
        # Substantial fallback content that meets token requirements (must be >= 1024 tokens)
        # Using excerpts from the 1997 Amazon shareholder letter
        fallback_content = """To our shareholders:

Amazon.com passed many milestones in 1997: by year-end, we had served more than 1.5 million customers, yielding 838% revenue growth to $147.8 million, and extended our market leadership despite aggressive competitive entry.

But this is Day 1 for the Internet and, if we execute well, for Amazon.com. Today, online commerce saves customers money and precious time. Tomorrow, through personalization, online commerce will accelerate the very process of discovery. Amazon.com uses the Internet to create real value for its customers and, by doing so, hopes to create an enduring franchise, even in established and large markets.

We have a window of opportunity as larger players marshal the resources to pursue the online opportunity and as customers, new to purchasing online, are receptive to forming new relationships. The competitive landscape has continued to evolve at a fast pace. Many large players have moved online with credible offerings and have devoted substantial energy and resources to building awareness, traffic, and sales. Our goal is to move quickly to solidify and extend our current position while we begin to pursue the online commerce opportunities in other areas. We see substantial opportunity in the large markets we are targeting. This strategy is not without risk: it requires serious investment and crisp execution against established franchise leaders.

It's All About the Long Term

We believe that a fundamental measure of our success will be the shareholder value we create over the long term. This value will be a direct result of our ability to extend and solidify our current market leadership position. The stronger our market leadership, the more powerful our economic model. Market leadership can translate directly to higher revenue, higher profitability, greater capital velocity, and correspondingly stronger returns on invested capital.

Our decisions have consistently reflected this focus. We first measure ourselves in terms of the metrics most indicative of our market leadership: customer and revenue growth, the degree to which our customers continue to purchase from us on a repeat basis, and the strength of our brand. We have invested and will continue to invest aggressively to expand and leverage our customer base, brand, and infrastructure as we move to establish an enduring franchise.

Because of our emphasis on the long term, we may make decisions and weigh tradeoffs differently than some companies. Accordingly, we want to share with you our fundamental management and decision-making approach so that you, our shareholders, may confirm that it is consistent with your investment philosophy:

We will continue to focus relentlessly on our customers.

We will continue to make investment decisions in light of long-term market leadership considerations rather than short-term profitability considerations or short-term Wall Street reactions.

We will continue to measure our programs and the effectiveness of our investments analytically, to jettison those that do not provide acceptable returns, and to step up our investment in those that work best. We will continue to learn from both our successes and our failures.

We will make bold rather than timid investment decisions where we see a sufficient probability of gaining market leadership advantages. Some of these investments will pay off, others will not, and we will have learned another valuable lesson in either case.

When forced to choose between optimizing the appearance of our GAAP accounting and maximizing the present value of future cash flows, we'll take the cash flows.

We will share our strategic thought processes with you when we make bold choices (to the extent competitive pressures allow), so that you may evaluate for yourselves whether we are making rational long-term leadership investments.

We will work hard to spend wisely and maintain our lean culture. We understand the importance of continually reinforcing a cost-conscious culture, particularly in a business incurring net losses.

We will balance our focus on growth with emphasis on long-term profitability and capital management. At this stage, we choose to prioritize growth because we believe that scale is central to achieving the potential of our business model.

We will continue to focus on hiring and retaining versatile and talented employees, and continue to weight their compensation to stock options rather than cash. We know our success will be largely affected by our ability to attract and retain a motivated employee base, each of whom must think like, and therefore must actually be, an owner.

We aren't so bold as to claim that the above is the "right" investment philosophy, but it's ours, and we would be remiss if we weren't clear in the approach we have taken and will continue to take.

Obsess Over Customers

From the beginning, our focus has been on offering our customers compelling value. We realized that the Web was, and still is, the World Wide Wait. Therefore, we set out to offer customers something they simply could not get any other way, and began serving them with books. We brought them much more selection than was possible in a physical store (our store would now occupy 6 football fields), and presented it in a useful, easy-to-search, and easy-to-browse format in a store open 365 days a year, 24 hours a day. We maintained a dogged focus on improving the shopping experience, and in 1997 substantially enhanced our store.

By many measures, Amazon.com came a long way in 1997: Sales grew from $15.7 million in 1996 to $147.8 million -- an 838% increase. Cumulative customer accounts grew from 180,000 to 1,510,000 -- a 738% increase. The percentage of orders from repeat customers grew from over 46% in the fourth quarter of 1996 to over 58% in the same period in 1997.

The past year's success is the product of a talented, smart, hard-working group, and I take great pride in being a part of this team. Setting the bar high in our approach to hiring has been, and will continue to be, the single most important element of Amazon.com's success.

It's not easy to work here (when I interview people I tell them, "You can work long, hard, or smart, but at Amazon.com you can't choose two out of three"), but we are working to build something important, something that matters to our customers, something that we can all tell our grandchildren about. Such things aren't meant to be easy. We are incredibly fortunate to have this group of dedicated employees whose sacrifices and passion build Amazon.com.

We are still in the early stages of learning how to bring new value to our customers through Internet commerce and merchandising. Our goal remains to continue to solidify and extend our brand and customer base. This requires sustained investment in systems and infrastructure to support outstanding customer convenience, selection, and service while we grow.

We now know vastly more about online commerce than when Amazon.com was founded, but we still have so much to learn. Though we are optimistic, we must remain vigilant and maintain a sense of urgency. The challenges and hurdles we will face to make our long-term vision for Amazon.com a reality are several: aggressive, capable, well-funded competition; considerable growth challenges and execution risk; the risks of product and geographic expansion; and the need for large continuing investments to meet an expanding market opportunity.

1997 was indeed an incredible year. We at Amazon.com are grateful to our customers for their business and trust, to each other for our hard work, and to our shareholders for their support and encouragement."""
        
        word_count = len(fallback_content.split())
        estimated_tokens = int(word_count * 1.3)
        
        logger.info(f"Fallback content: {word_count} words, ~{estimated_tokens} tokens")
        
        return {
            'content': fallback_content,
            'source': 'fallback',
            'word_count': word_count,
            'estimated_tokens': estimated_tokens,
            'meets_minimum': estimated_tokens >= 1024
        }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for query processing.
    
    Args:
        event: API Gateway event containing the question and optional model ID
        context: Lambda context object
        
    Returns:
        API Gateway response with status code and body
    """
    try:
        logger.info("Query handler invoked")
        
        # Extract source IP address for rate limiting
        source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', 'unknown')
        logger.info(f"Request from IP: {source_ip}")
        
        # Check rate limit
        is_allowed, retry_after = check_rate_limit(source_ip)
        if not is_allowed:
            logger.warning(f"Rate limit exceeded for IP {source_ip}, retry after {retry_after}s")
            return {
                'statusCode': 429,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Retry-After': str(retry_after)
                },
                'body': json.dumps({
                    'success': False,
                    'error': f'Too many requests. Please wait {retry_after} seconds before trying again.'
                })
            }
        
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        question = body.get('question', '')
        model_id = body.get('model', 'amazon.nova-lite-v1:0')
        
        logger.info(f"Processing question with model: {model_id}")
        
        # Check if user uploaded a document
        uploaded_document = extract_uploaded_document(body)
        if uploaded_document:
            logger.info("User uploaded a custom document")
            # Validate uploaded document
            doc_validation_error = validate_document_content(uploaded_document)
            if doc_validation_error:
                logger.warning(f"Document validation failed: {doc_validation_error}")
                return {
                    'statusCode': 400,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': doc_validation_error
                    })
                }
        
        # Validate question
        validation_error = validate_question(question)
        if validation_error:
            logger.warning(f"Question validation failed: {validation_error}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': validation_error
                })
            }
        
        # Sanitize question
        question = sanitize_input(question)
        logger.info(f"Sanitized question: {question[:50]}...")
        
        # Validate model ID
        if not validate_model_id(model_id):
            logger.warning(f"Invalid model ID: {model_id}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': f'Unsupported model. Supported models: {", ".join(SUPPORTED_MODELS.keys())}'
                })
            }
        
        # Load document - either from upload or S3
        # Context persistence: The same document is used for all requests in the session.
        # This ensures cache hits work correctly across multiple queries, as the cached
        # document context remains consistent.
        if uploaded_document:
            # Use uploaded document
            word_count = len(uploaded_document.split())
            estimated_tokens = int(word_count * 1.3)
            document_data = {
                'content': uploaded_document,
                'source': 'uploaded',
                'word_count': word_count,
                'estimated_tokens': estimated_tokens,
                'meets_minimum': estimated_tokens >= SUPPORTED_MODELS.get(model_id, {}).get('min_tokens', 1024)
            }
            logger.info(f"Using uploaded document: {word_count} words, ~{estimated_tokens} tokens")
        else:
            # Load default document from S3
            document_bucket = os.environ.get('DOCUMENT_BUCKET')
            if not document_bucket:
                logger.error("DOCUMENT_BUCKET environment variable not set")
                return {
                    'statusCode': 500,
                    'headers': {
                        'Content-Type': 'application/json',
                        'Access-Control-Allow-Origin': '*'
                    },
                    'body': json.dumps({
                        'success': False,
                        'error': 'Server configuration error'
                    })
                }
            
            document_data = load_document_from_s3(document_bucket)
            logger.info(f"Document loaded from {document_data['source']}: "
                       f"{document_data['estimated_tokens']} tokens, "
                       f"meets minimum: {document_data['meets_minimum']}")
        
        # Use the same document content for all three phases (baseline, cache write, cache hit)
        # to demonstrate proper cache behavior with consistent context
        document_content = document_data['content']
        
        # Phase 1: Baseline request (no cache)
        logger.info("Phase 1: Baseline request (no cache)")
        baseline_result = invoke_python_script(question, model_id, document_content, use_cache=False)
        
        if not baseline_result.get('success'):
            logger.error(f"Baseline request failed: {baseline_result.get('error')}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': baseline_result.get('error', 'Baseline request failed')
                })
            }
        
        # Phase 2: Cache write request (with cache checkpoint)
        logger.info("Phase 2: Cache write request (with cache checkpoint)")
        cache_write_result = invoke_python_script(question, model_id, document_content, use_cache=True)
        
        if not cache_write_result.get('success'):
            logger.error(f"Cache write request failed: {cache_write_result.get('error')}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': cache_write_result.get('error', 'Cache write request failed')
                })
            }
        
        # Phase 3: Cache hit request (same document, should hit cache)
        logger.info("Phase 3: Cache hit request (should hit cache)")
        # Use the same question and document to demonstrate cache hit
        # The cached document context allows for faster processing
        cache_hit_result = invoke_python_script(question, model_id, document_content, use_cache=True)
        
        if not cache_hit_result.get('success'):
            logger.error(f"Cache hit request failed: {cache_hit_result.get('error')}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'success': False,
                    'error': cache_hit_result.get('error', 'Cache hit request failed')
                })
            }
        
        # Verify token reduction occurred
        baseline_input_tokens = baseline_result.get('usage', {}).get('inputTokens', 0)
        cache_hit_input_tokens = cache_hit_result.get('usage', {}).get('inputTokens', 0)
        cache_read_tokens = cache_hit_result.get('cache_read_tokens', 0)
        
        logger.info(f"Token reduction: baseline={baseline_input_tokens}, "
                   f"cache_hit={cache_hit_input_tokens}, "
                   f"cache_read={cache_read_tokens}")
        
        # Calculate metrics
        # Token reduction percentage: ((baseline - cached) / baseline) * 100
        token_reduction_percent = 0.0
        if baseline_input_tokens > 0:
            token_reduction_percent = ((baseline_input_tokens - cache_hit_input_tokens) / baseline_input_tokens) * 100
        
        # Latency improvement percentage
        baseline_time = baseline_result.get('response_time', 0)
        cache_hit_time = cache_hit_result.get('response_time', 0)
        latency_improvement_percent = 0.0
        if baseline_time > 0:
            latency_improvement_percent = ((baseline_time - cache_hit_time) / baseline_time) * 100
        
        # Cache hit ratio: cache_read / (cache_read + input) * 100
        cache_hit_ratio = 0.0
        total_tokens = cache_read_tokens + cache_hit_input_tokens
        if total_tokens > 0:
            cache_hit_ratio = (cache_read_tokens / total_tokens) * 100
        
        logger.info(f"Metrics: token_reduction={token_reduction_percent:.1f}%, "
                   f"latency_improvement={latency_improvement_percent:.1f}%, "
                   f"cache_hit_ratio={cache_hit_ratio:.1f}%")
        
        # Response with all three phases and metrics
        response = {
            'success': True,
            'baseline': {
                'response_time': baseline_result.get('response_time', 0),
                'input_tokens': baseline_input_tokens,
                'output_tokens': baseline_result.get('usage', {}).get('outputTokens', 0),
                'content': baseline_result.get('content', '')
            },
            'cache_write': {
                'response_time': cache_write_result.get('response_time', 0),
                'input_tokens': cache_write_result.get('usage', {}).get('inputTokens', 0),
                'output_tokens': cache_write_result.get('usage', {}).get('outputTokens', 0),
                'cache_write_tokens': cache_write_result.get('cache_write_tokens', 0),
                'content': cache_write_result.get('content', '')
            },
            'cache_hit': {
                'response_time': cache_hit_result.get('response_time', 0),
                'input_tokens': cache_hit_input_tokens,
                'output_tokens': cache_hit_result.get('usage', {}).get('outputTokens', 0),
                'cache_read_tokens': cache_read_tokens,
                'content': cache_hit_result.get('content', '')
            },
            'metrics': {
                'token_reduction_percent': round(token_reduction_percent, 2),
                'latency_improvement_percent': round(latency_improvement_percent, 2),
                'cache_hit_ratio': round(cache_hit_ratio, 2)
            },
            'document_info': {
                'source': document_data['source'],
                'estimated_tokens': document_data['estimated_tokens'],
                'meets_minimum': document_data['meets_minimum'],
                'minimum_required': SUPPORTED_MODELS.get(model_id, {}).get('min_tokens', 1024)
            }
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps(response)
        }
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request body: {str(e)}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': False,
                'error': 'Invalid JSON in request body'
            })
        }
        
    except Exception as e:
        # Sanitize error message before logging and returning
        error_msg = sanitize_error_message(str(e))
        logger.error(f"Unexpected error: {error_msg}", exc_info=True)
        
        # Determine appropriate status code based on error type
        status_code = 500
        if 'throttl' in str(e).lower() or 'rate' in str(e).lower():
            status_code = 429  # Too Many Requests
        elif 'timeout' in str(e).lower():
            status_code = 504  # Gateway Timeout
        
        return {
            'statusCode': status_code,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Retry-After': '60' if status_code == 429 else None
            },
            'body': json.dumps({
                'success': False,
                'error': 'Internal server error' if status_code == 500 else error_msg
            })
        }
