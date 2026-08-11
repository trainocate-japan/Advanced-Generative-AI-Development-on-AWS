"""
Upload Handler Lambda Function

This function receives EML files from API Gateway, validates them, and stores them in S3.

Workflow:
1. Receive multipart/form-data from API Gateway (base64 encoded)
2. Parse the multipart data to extract the EML file
3. Validate file format and size
4. Generate unique S3 key with timestamp
5. Upload to S3 inbox bucket with metadata
6. Return success response with tracking information

Environment Variables:
- INBOX_BUCKET_NAME: Name of the S3 bucket for storing uploaded files
"""

import json
import base64
import email
import os
import uuid
from datetime import datetime
from io import BytesIO
from email import policy
import boto3
import logging

# Configure structured logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')

# Get environment variables
INBOX_BUCKET_NAME = os.environ.get('INBOX_BUCKET_NAME')

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes


def parse_multipart_form_data(body, content_type):
    """
    Parse multipart/form-data from API Gateway
    
    API Gateway sends the body as base64-encoded string when binary media types
    are configured. We need to decode it and parse the multipart data.
    
    Args:
        body: Base64-encoded multipart form data
        content_type: Content-Type header with boundary parameter
        
    Returns:
        dict: Parsed form data with file information
        
    Raises:
        ValueError: If parsing fails or file is missing
    """
    try:
        # Decode base64 body
        decoded_body = base64.b64decode(body)
        
        # Extract boundary from content-type header
        # Format: multipart/form-data; boundary=----WebKitFormBoundary...
        boundary = None
        if 'boundary=' in content_type:
            boundary = content_type.split('boundary=')[1].strip()
        
        if not boundary:
            raise ValueError("No boundary found in Content-Type header")
        
        # Parse multipart data manually
        # Split by boundary to get parts
        boundary_bytes = f'--{boundary}'.encode()
        parts = decoded_body.split(boundary_bytes)
        
        file_data = None
        filename = None
        
        # Process each part
        for part in parts:
            if not part or part == b'--\r\n' or part == b'--':
                continue
                
            # Split headers from content
            if b'\r\n\r\n' in part:
                headers_section, content = part.split(b'\r\n\r\n', 1)
                headers_text = headers_section.decode('utf-8', errors='ignore')
                
                # Check if this is a file upload part
                if 'Content-Disposition' in headers_text and 'filename=' in headers_text:
                    # Extract filename
                    for line in headers_text.split('\r\n'):
                        if 'filename=' in line:
                            # Parse filename from: filename="example.eml"
                            filename_start = line.find('filename="') + 10
                            filename_end = line.find('"', filename_start)
                            if filename_end > filename_start:
                                filename = line[filename_start:filename_end]
                    
                    # Remove trailing boundary markers from content
                    file_data = content.rstrip(b'\r\n--')
        
        if not file_data or not filename:
            raise ValueError("No file found in multipart data")
        
        return {
            'filename': filename,
            'content': file_data,
            'size': len(file_data)
        }
        
    except Exception as e:
        logger.error(f"Failed to parse multipart data: {str(e)}")
        raise ValueError(f"Invalid multipart data: {str(e)}")


def validate_eml_file(file_data, filename):
    """
    Validate that the uploaded file is a valid EML format
    
    Checks:
    1. File extension is .eml
    2. File size is within limits
    3. Content can be parsed as an email message
    
    Args:
        file_data: Raw file content as bytes
        filename: Original filename
        
    Returns:
        dict: Validation result with email metadata
        
    Raises:
        ValueError: If validation fails
    """
    # Check file extension
    if not filename.lower().endswith('.eml'):
        raise ValueError("File must have .eml extension")
    
    # Check file size
    file_size = len(file_data)
    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File size ({file_size} bytes) exceeds maximum allowed size ({MAX_FILE_SIZE} bytes)")
    
    if file_size == 0:
        raise ValueError("File is empty")
    
    # Try to parse as email to validate format
    try:
        msg = email.message_from_bytes(file_data, policy=policy.default)
        
        # Extract basic metadata for validation
        subject = msg.get('Subject', 'No Subject')
        sender = msg.get('From', 'Unknown Sender')
        date = msg.get('Date', 'Unknown Date')
        
        # Count attachments
        attachment_count = 0
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_disposition() == 'attachment':
                    attachment_count += 1
        
        logger.info(f"Valid EML file: {filename}, Subject: {subject}, From: {sender}, Attachments: {attachment_count}")
        
        return {
            'valid': True,
            'subject': subject,
            'sender': sender,
            'date': date,
            'attachment_count': attachment_count,
            'size': file_size
        }
        
    except Exception as e:
        logger.error(f"Failed to parse EML file: {str(e)}")
        raise ValueError(f"Invalid EML file format: {str(e)}")


def generate_s3_key(filename):
    """
    Generate unique S3 key for the uploaded file
    
    Format: incoming/{timestamp}-{uuid}-{filename}
    
    This ensures:
    - Files are organized in the incoming/ prefix
    - Unique keys prevent overwrites
    - Timestamp allows chronological sorting
    - Original filename is preserved for reference
    
    Args:
        filename: Original filename
        
    Returns:
        str: S3 key for the file
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    
    # Sanitize filename (remove path components if any)
    safe_filename = os.path.basename(filename)
    
    s3_key = f"incoming/{timestamp}-{unique_id}-{safe_filename}"
    
    return s3_key


def upload_to_s3(file_data, s3_key, metadata):
    """
    Upload file to S3 with metadata
    
    Args:
        file_data: File content as bytes
        s3_key: S3 key for the object
        metadata: Dictionary of metadata to attach to the object
        
    Returns:
        dict: Upload result with S3 information
        
    Raises:
        Exception: If S3 upload fails
    """
    try:
        # Convert metadata values to strings (S3 requirement)
        s3_metadata = {k: str(v) for k, v in metadata.items()}
        
        # Upload to S3
        s3_client.put_object(
            Bucket=INBOX_BUCKET_NAME,
            Key=s3_key,
            Body=file_data,
            ContentType='message/rfc822',  # MIME type for EML files
            Metadata=s3_metadata
        )
        
        logger.info(f"Successfully uploaded file to s3://{INBOX_BUCKET_NAME}/{s3_key}")
        
        return {
            'bucket': INBOX_BUCKET_NAME,
            'key': s3_key,
            'size': len(file_data)
        }
        
    except Exception as e:
        logger.error(f"Failed to upload to S3: {str(e)}")
        raise Exception(f"S3 upload failed: {str(e)}")


def lambda_handler(event, context):
    """
    Main Lambda handler for processing file uploads from API Gateway
    
    This function is invoked by API Gateway when a POST request is made to /upload.
    API Gateway is configured with Lambda proxy integration, so the event contains
    the full HTTP request details.
    
    Args:
        event: API Gateway proxy event with request details
        context: Lambda context object
        
    Returns:
        dict: API Gateway proxy response with status code and body
    """
    try:
        logger.info(f"Received upload request")
        
        # Validate environment variables
        if not INBOX_BUCKET_NAME:
            logger.error("INBOX_BUCKET_NAME environment variable not set")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',  # CORS for demo purposes
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Server configuration error'
                })
            }
        
        # Get request body and headers
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        headers = event.get('headers', {})
        
        # Get content-type header (case-insensitive)
        content_type = None
        for key, value in headers.items():
            if key.lower() == 'content-type':
                content_type = value
                break
        
        if not content_type or 'multipart/form-data' not in content_type:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Content-Type must be multipart/form-data'
                })
            }
        
        # Parse multipart form data
        try:
            file_info = parse_multipart_form_data(body, content_type)
        except ValueError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS'
                },
                'body': json.dumps({
                    'error': str(e)
                })
            }
        
        # Validate EML file
        try:
            validation_result = validate_eml_file(file_info['content'], file_info['filename'])
        except ValueError as e:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS'
                },
                'body': json.dumps({
                    'error': str(e)
                })
            }
        
        # Generate unique S3 key
        s3_key = generate_s3_key(file_info['filename'])
        
        # Prepare metadata
        metadata = {
            'original-filename': file_info['filename'],
            'upload-timestamp': datetime.utcnow().isoformat(),
            'subject': validation_result['subject'][:1024],  # Limit metadata size
            'sender': validation_result['sender'][:1024],
            'attachment-count': str(validation_result['attachment_count'])
        }
        
        # Upload to S3
        try:
            upload_result = upload_to_s3(file_info['content'], s3_key, metadata)
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type',
                    'Access-Control-Allow-Methods': 'POST, OPTIONS'
                },
                'body': json.dumps({
                    'error': 'Failed to store file'
                })
            }
        
        # Generate tracking ID
        upload_id = str(uuid.uuid4())
        
        # Return success response
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'uploadId': upload_id,
                'message': 'File uploaded successfully',
                's3Key': s3_key,
                'bucket': INBOX_BUCKET_NAME,
                'metadata': {
                    'filename': file_info['filename'],
                    'size': file_info['size'],
                    'subject': validation_result['subject'],
                    'sender': validation_result['sender'],
                    'attachmentCount': validation_result['attachment_count']
                }
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }
