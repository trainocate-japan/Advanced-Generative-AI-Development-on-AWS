"""
List Emails Lambda Function

This Lambda function provides an API endpoint to list classified emails from the destination
S3 bucket organized by department. It retrieves email metadata and returns a JSON response
with email details for display in the frontend department view.

Workflow:
1. Validate department parameter from API Gateway path
2. List S3 objects in the department-specific prefix
3. Extract metadata from S3 object metadata
4. Format and return JSON response with email array and count

Requirements:
- 1.1: Retrieve email counts for all departments
- 2.1: Retrieve list of emails for selected department
- 2.2: Display email metadata (sender, subject, timestamp, attachment count)
- 2.3: Return email metadata including S3 key
- 3.1: REST API endpoint at /departments/{department}/emails
- 3.2: Validate department parameter
- 3.3: Return email metadata in JSON format
- 3.5: Return HTTP 400 for invalid department
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Any
import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize S3 client
s3_client = boto3.client('s3')

# Valid departments
VALID_DEPARTMENTS = ['finance', 'it', 'hr', 'operations', 'marketing']

# Environment variables
DESTINATION_BUCKET_NAME = os.environ.get('DESTINATION_BUCKET_NAME')

# Default and maximum limits
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for listing classified emails by department.
    
    Args:
        event: API Gateway proxy event containing path parameters
        context: Lambda context object
        
    Returns:
        API Gateway proxy response with email list and count
        
    Raises:
        No exceptions raised - all errors returned as HTTP responses
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Validate environment variables
    if not DESTINATION_BUCKET_NAME:
        logger.error("DESTINATION_BUCKET_NAME environment variable not set")
        return create_error_response(500, "Server configuration error")
    
    try:
        # Extract and validate department parameter
        path_parameters = event.get('pathParameters', {})
        department = path_parameters.get('department', '').lower()
        
        if not department:
            logger.warning("Missing department parameter")
            return create_error_response(400, "Department parameter is required")
        
        if department not in VALID_DEPARTMENTS:
            logger.warning(f"Invalid department: {department}")
            return create_error_response(
                400,
                f"Invalid department. Must be one of: {', '.join(VALID_DEPARTMENTS)}"
            )
        
        # Extract and validate limit parameter
        query_parameters = event.get('queryStringParameters') or {}
        limit = int(query_parameters.get('limit', DEFAULT_LIMIT))
        limit = min(limit, MAX_LIMIT)  # Cap at maximum
        
        logger.info(f"Listing emails for department: {department}, limit: {limit}")
        
        # List emails from S3
        emails = list_department_emails(department, limit)
        
        # Create response
        response_body = {
            'department': department,
            'count': len(emails),
            'emails': emails
        }
        
        logger.info(f"Successfully retrieved {len(emails)} emails for {department}")
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps(response_body)
        }
        
    except ValueError as e:
        logger.error(f"Invalid parameter: {str(e)}")
        return create_error_response(400, f"Invalid parameter: {str(e)}")
    
    except ClientError as e:
        logger.error(f"S3 error: {str(e)}")
        return create_error_response(500, "Failed to retrieve emails")
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error")


def list_department_emails(department: str, limit: int) -> List[Dict[str, Any]]:
    """
    List emails from S3 for a specific department.
    
    Args:
        department: Department name (finance, it, hr, operations, marketing)
        limit: Maximum number of emails to return
        
    Returns:
        List of email metadata dictionaries
        
    Raises:
        ClientError: If S3 operations fail
    """
    # Construct S3 prefix for department
    prefix = f"departments/{department}/"
    
    logger.info(f"Listing objects in bucket: {DESTINATION_BUCKET_NAME}, prefix: {prefix}")
    
    emails = []
    
    try:
        # List objects in S3 with prefix filter
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=DESTINATION_BUCKET_NAME,
            Prefix=prefix
        )
        
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                s3_key = obj['Key']
                
                # Skip metadata folder and non-EML files
                if '/metadata/' in s3_key or not s3_key.endswith('.eml'):
                    continue
                
                # Extract email metadata
                email_metadata = extract_email_metadata(s3_key, obj)
                
                if email_metadata:
                    emails.append(email_metadata)
                
                # Stop if we've reached the limit
                if len(emails) >= limit:
                    break
            
            if len(emails) >= limit:
                break
        
        # Sort by timestamp (newest first)
        emails.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return emails[:limit]
    
    except ClientError as e:
        logger.error(f"Failed to list objects: {str(e)}")
        raise


def extract_email_metadata(s3_key: str, s3_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract email metadata from S3 object.
    
    Args:
        s3_key: S3 object key
        s3_object: S3 object metadata from list_objects_v2
        
    Returns:
        Dictionary containing email metadata, or None if extraction fails
    """
    try:
        # Get object metadata
        response = s3_client.head_object(
            Bucket=DESTINATION_BUCKET_NAME,
            Key=s3_key
        )
        
        metadata = response.get('Metadata', {})
        
        # Extract filename from S3 key
        filename = s3_key.split('/')[-1]
        
        # Extract metadata fields (set by invoice_classifier.py)
        sender = metadata.get('sender', 'Unknown')
        subject = metadata.get('subject', 'No Subject')
        attachment_count = int(metadata.get('attachment-count', '0'))
        
        # Get timestamp from metadata or use LastModified from S3 object
        timestamp_str = metadata.get('upload-timestamp') or metadata.get('classification-timestamp')
        
        if timestamp_str:
            timestamp = timestamp_str
        else:
            # Fallback to S3 LastModified
            last_modified = s3_object.get('LastModified')
            if last_modified:
                timestamp = last_modified.isoformat()
            else:
                timestamp = datetime.utcnow().isoformat()
        
        return {
            'sender': sender,
            'subject': subject,
            'timestamp': timestamp,
            'attachmentCount': attachment_count,
            's3Key': s3_key,
            'fileName': filename
        }
    
    except ClientError as e:
        logger.warning(f"Failed to get metadata for {s3_key}: {str(e)}")
        return None
    
    except Exception as e:
        logger.warning(f"Error extracting metadata for {s3_key}: {str(e)}")
        return None


def get_cors_headers() -> Dict[str, str]:
    """
    Get CORS headers for API response.
    
    Returns:
        Dictionary of CORS headers
    """
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    }


def create_error_response(status_code: int, message: str) -> Dict[str, Any]:
    """
    Create an error response for API Gateway.
    
    Args:
        status_code: HTTP status code
        message: Error message
        
    Returns:
        API Gateway proxy response
    """
    return {
        'statusCode': status_code,
        'headers': get_cors_headers(),
        'body': json.dumps({
            'error': message
        })
    }
