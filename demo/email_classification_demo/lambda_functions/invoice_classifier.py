"""
Invoice Classifier Lambda Function

This Lambda function classifies invoices using Amazon Bedrock and organizes emails
into department-specific folders in S3.

Workflow:
1. Triggered by Step Functions after BDA completes document extraction
2. Retrieves BDA output from S3 (extracted text from PDF invoices)
3. Reads department configuration from S3
4. Classifies invoice using Amazon Bedrock Converse API
5. Falls back to keyword-based classification if Bedrock fails
6. Copies email to destination bucket under department prefix
7. Creates metadata JSON file for tracking and display

Requirements: 4.5, 4.6, 5.1, 5.2, 9.2, 9.3, 11.1, 11.4
"""

import json
import boto3
import os
import logging
import datetime
import re

# Configure structured logging
# Logs are sent to CloudWatch for monitoring and debugging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get AWS region from environment variable or default to current session region
AWS_REGION = os.environ.get('AWS_REGION', boto3.session.Session().region_name)

# Initialize AWS clients outside of handler function to improve performance
# This reduces cold start time and reuses connections across Lambda invocations
s3 = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=AWS_REGION)
cloudwatch = boto3.client('cloudwatch', region_name=AWS_REGION)

# Constants for BDA output location
OUTPUT_FOLDER_NAME = "bda-output"


def lambda_handler(event, context):
    """
    Main handler for invoice classification and email organization.
    
    This function is invoked by Step Functions after BDA completes document processing.
    It classifies the invoice and organizes the email into the appropriate department folder.
    
    Args:
        event: Step Functions event containing:
            - stepFunctionTrigger: Boolean indicating Step Functions invocation
            - bucket: S3 bucket name containing the email and BDA output
            - invocationId: BDA invocation ID for retrieving extracted content
            - bdaOutputPrefix: S3 prefix where BDA writes output (default: bda-output/)
            - emailMetadata: Original email information (sender, subject, key, etc.)
        context: Lambda context with runtime information
        
    Returns:
        dict: Response with statusCode and processing results
        
    Raises:
        Exception: Logs errors and re-raises for Step Functions retry logic
    """
    logger.info("Invoice classifier Lambda triggered")
    logger.info(f"Event: {json.dumps(event, default=str)}")
    
    # Log the actual bucket names being used for debugging
    inbox_bucket = os.environ.get('INBOX_BUCKET')
    destination_bucket = os.environ.get('DESTINATION_BUCKET')
    logger.info(f"Using bucket names - Inbox: {inbox_bucket}, Destination: {destination_bucket}")
    
    # Handle test events for Lambda function verification
    if event.get('test'):
        logger.info("Test event received - Lambda is working!")
        return {
            'statusCode': 200,
            'body': json.dumps('Test successful - Lambda function is working')
        }
    
    try:
        # Process the classification and organization
        result = process_classification(event)
        
        # Publish custom metrics to CloudWatch
        try:
            department = result.get('department', 'Unknown')
            
            # Publish ClassificationSuccess and DepartmentDistribution metrics
            cloudwatch.put_metric_data(
                Namespace='EmailClassification',
                MetricData=[
                    {
                        'MetricName': 'ClassificationSuccess',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': datetime.datetime.now(datetime.timezone.utc)
                    },
                    {
                        'MetricName': 'DepartmentDistribution',
                        'Value': 1,
                        'Unit': 'Count',
                        'Dimensions': [
                            {
                                'Name': 'Department',
                                'Value': department
                            }
                        ],
                        'Timestamp': datetime.datetime.now(datetime.timezone.utc)
                    }
                ]
            )
            logger.info(f"Published metrics: ClassificationSuccess=1, DepartmentDistribution[{department}]=1")
        except Exception as metric_error:
            logger.warning(f"Failed to publish metrics: {str(metric_error)}")
            # Don't fail the function if metrics fail
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Classification processing completed',
                'department': result.get('department'),
                'targetKey': result.get('targetKey')
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing classification: {str(e)}")
        
        # Publish ClassificationFailure metric
        try:
            cloudwatch.put_metric_data(
                Namespace='EmailClassification',
                MetricData=[
                    {
                        'MetricName': 'ClassificationFailure',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': datetime.datetime.now(datetime.timezone.utc)
                    }
                ]
            )
            logger.info("Published metric: ClassificationFailure=1")
        except Exception as metric_error:
            logger.warning(f"Failed to publish failure metric: {str(metric_error)}")
        
        # Re-raise exception so Step Functions can retry if configured
        raise


def process_classification(event):
    """
    Process invoice classification and email organization.
    
    This function orchestrates the entire classification workflow:
    1. Retrieve configuration and BDA output
    2. Classify the invoice using Bedrock
    3. Organize the email into department folders
    4. Create metadata for tracking
    
    Args:
        event: Lambda event containing processing parameters
        
    Returns:
        dict: Processing results including department and target S3 key
        
    Raises:
        Exception: If required data is missing or processing fails
    """
    # Get configuration from environment variables
    config_bucket = os.environ.get('CONFIG_BUCKET_NAME')
    config_key = os.environ.get('CONFIG_FILE_KEY', 'department_config.json')
    inbox_bucket = os.environ.get('INBOX_BUCKET')
    destination_bucket = os.environ.get('DESTINATION_BUCKET')
    
    logger.info(f"Using buckets - Config: {config_bucket}, Inbox: {inbox_bucket}, Destination: {destination_bucket}")
    
    # Read department configuration from S3
    departments_config = get_departments_config(s3, config_bucket, config_key)
    
    # Initialize variables for invoice data and email metadata
    invoice_data = None
    email_metadata = {}
    
    # Handle Step Functions trigger with BDA output
    if 'stepFunctionTrigger' in event and 'invocationId' in event:
        invocation_id = event['invocationId']
        bucket = event['bucket']
        bda_prefix = event.get('bdaOutputPrefix', 'bda-output/')
        logger.info(f"Processing Step Functions trigger for invocation ID: {invocation_id}")
        
        # Retrieve BDA output from S3
        invoice_data = retrieve_bda_output(bucket, bda_prefix, invocation_id)
        
        # Use the email metadata from Step Functions
        email_metadata = event.get('emailMetadata', {})
    else:
        # Handle test events or direct invocation
        logger.info("No Step Functions trigger found, using test data")
        invoice_data = "Test invoice data for IT department classification"
        email_metadata = {
            'email_key': 'test/sample-email.eml',
            'sender': 'test@example.com',
            'subject': 'Test Invoice - IT Equipment'
        }
    
    # Validate that we have invoice data to classify
    if not invoice_data:
        error_msg = "No extracted content found in the event"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    # Convert to string if it's a dict/object
    # BDA output may be structured JSON or plain text
    invoice_text = invoice_data if isinstance(invoice_data, str) else json.dumps(invoice_data)
    
    logger.info(f"Extracted invoice text (first 200 chars): {invoice_text[:200]}...")
    
    # Classify the invoice using Bedrock
    department = classify_invoice(invoice_text, email_metadata, departments_config)
    
    logger.info(f"Classification result: {department}")
    
    # Validate that the department exists in our config
    if department not in departments_config and department != 'Unknown':
        logger.warning(f"Department '{department}' not found in config, using 'Operations' instead")
        department = 'Operations'
    
    # Organize the email into the appropriate department folder
    target_key = organize_email(
        inbox_bucket,
        destination_bucket,
        email_metadata,
        department,
        invoice_text
    )
    
    logger.info(f"Successfully processed classification for department: {department}")
    
    return {
        'department': department,
        'targetKey': target_key
    }


def retrieve_bda_output(bucket, bda_prefix, invocation_id):
    """
    Retrieve BDA output from S3 with multiple key attempts.
    
    BDA writes output to S3 in a specific structure. This function attempts
    to find and parse the output JSON file, trying multiple possible keys
    for the extracted content.
    
    Args:
        bucket: S3 bucket name containing BDA output
        bda_prefix: S3 prefix where BDA writes output (e.g., bda-output/)
        invocation_id: BDA invocation ID
        
    Returns:
        str or dict: Extracted invoice content from BDA
        
    Raises:
        Exception: If BDA output cannot be found or parsed
    """
    try:
        # List objects under the BDA output prefix for this invocation
        response = s3.list_objects_v2(Bucket=bucket, Prefix=f"{bda_prefix}{invocation_id}")
        
        if 'Contents' not in response or len(response['Contents']) == 0:
            logger.warning(f"No BDA output found for invocation: {invocation_id}")
            return None
        
        # Find the actual JSON output file
        # BDA creates multiple files, we need the main output JSON
        output_key = None
        for obj in response['Contents']:
            # Skip S3 access check files and look for JSON output
            if obj['Key'].endswith('.json') and '.s3_access_check' not in obj['Key']:
                output_key = obj['Key']
                break
        
        if not output_key:
            logger.warning(f"No JSON output file found for invocation: {invocation_id}")
            return None
        
        logger.info(f"Found BDA output at: s3://{bucket}/{output_key}")
        
        # Get the BDA output from S3
        response = s3.get_object(Bucket=bucket, Key=output_key)
        bda_output = json.loads(response['Body'].read().decode('utf-8'))
        
        # Debug: Log the BDA output structure
        logger.info(f"BDA output keys: {list(bda_output.keys())}")
        logger.info(f"BDA output sample: {str(bda_output)[:500]}...")
        
        # Extract the invoice text - try multiple possible keys
        # Different BDA versions and configurations may use different key names
        invoice_data = (
            bda_output.get('extractedContent') or 
            bda_output.get('textExtractionResult') or 
            bda_output.get('documentContent') or
            bda_output.get('content') or
            bda_output.get('text') or
            bda_output.get('result') or
            bda_output.get('output')
        )
        
        # If still no data, try to extract from nested structures
        if not invoice_data and isinstance(bda_output, dict):
            for key, value in bda_output.items():
                if isinstance(value, (str, dict)) and value:
                    invoice_data = value
                    logger.info(f"Using data from key: {key}")
                    break
        
        if invoice_data:
            logger.info(f"Successfully loaded BDA output for invocation: {invocation_id}")
        else:
            logger.warning(f"Could not extract content from BDA output for invocation: {invocation_id}")
        
        return invoice_data
        
    except Exception as e:
        logger.error(f"Error loading BDA output: {str(e)}")
        return None


def get_departments_config(s3_client, bucket, key):
    """
    Read department configuration from S3.
    
    The configuration file defines available departments and their S3 prefix paths.
    If the configuration cannot be read, default departments are used.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name containing the configuration
        key: S3 key for the configuration file (e.g., department_config.json)
        
    Returns:
        dict: Department configuration mapping department names to config objects
              Format: {'Finance': {'name': 'Finance', 'prefixPath': 'departments/finance'}, ...}
    """
    departments_config = {}
    
    try:
        if bucket and key:
            logger.info(f"Reading configuration from s3://{bucket}/{key}")
            response = s3_client.get_object(Bucket=bucket, Key=key)
            config = json.loads(response['Body'].read().decode('utf-8'))
            
            # Convert list of departments to dictionary keyed by name
            departments_config = {dept['name']: dept for dept in config.get('departments', [])}
            logger.info(f"Found {len(departments_config)} departments in configuration")
        else:
            logger.warning("Missing bucket or key for department configuration")
    except Exception as e:
        logger.warning(f"Could not read department configuration: {str(e)}")
        # Use default departments if config can't be read
        # This ensures the system continues to function even without configuration
        departments_config = {
            'Finance': {'name': 'Finance', 'prefixPath': 'departments/finance'},
            'IT': {'name': 'IT', 'prefixPath': 'departments/it'},
            'HR': {'name': 'HR', 'prefixPath': 'departments/hr'},
            'Operations': {'name': 'Operations', 'prefixPath': 'departments/operations'},
            'Marketing': {'name': 'Marketing', 'prefixPath': 'departments/marketing'}
        }
        logger.info("Using default department configuration")
    
    return departments_config


def classify_invoice(invoice_text, email_metadata, departments_config):
    """
    Classify invoice using Amazon Bedrock Converse API with fallback logic.
    
    This function attempts to classify the invoice using Bedrock's AI capabilities.
    If Bedrock fails or is unavailable, it falls back to keyword-based classification.
    
    Args:
        invoice_text: Extracted text content from the invoice
        email_metadata: Email information (subject, sender, etc.)
        departments_config: Available departments for classification
        
    Returns:
        str: Department name (e.g., 'Finance', 'IT', 'HR', 'Operations', 'Marketing')
    """
    # Get Bedrock model ID from environment variable
    model_id = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-lite-v1:0')
    
    # Prepare the prompt for classification
    # Build a list of available departments from configuration
    department_list = "\n".join([f"- {dept}" for dept in departments_config.keys()])
    if not department_list:
        # Fallback department list if configuration is empty
        department_list = "- Finance\n- IT\n- HR\n- Operations\n- Marketing"
    
    # Create classification prompt with clear instructions
    # The prompt includes invoice content, email metadata, and available departments
    prompt = f"""You are a document classifier. Classify this invoice to the most appropriate department based on its content. For example, if the content includes "IT" and the available departments include IT, return the result "IT". Return only the department name, do not return anything else.

Available departments:
{department_list}

Invoice content:
{invoice_text[:1000]}

Email subject: {email_metadata.get('subject', 'N/A')}
Sender: {email_metadata.get('sender', 'N/A')}

Department:"""
    
    try:
        # Call Bedrock for classification using Converse API
        # The Converse API provides a standardized interface for text generation
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
        
        # Configure inference parameters
        # Temperature 0 = deterministic output (same input = same output)
        # MaxTokens 100 = limit response length (we only need department name)
        inference_config = {
            "maxTokens": 100,
            "temperature": 0
        }
        
        logger.info(f"Calling Bedrock model: {model_id}")
        response = bedrock_runtime.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig=inference_config
        )
        
        # Extract department name from response
        department = response['output']['message']['content'][0]['text'].strip()
        
        logger.info(f"Bedrock classification result: {department}")
        
        # Extract department name from potentially verbose response
        # Bedrock might return "The department is Finance" instead of just "Finance"
        department_names = list(departments_config.keys())
        for dept in department_names:
            if dept.lower() in department.lower():
                department = dept
                break
        
        return department
        
    except Exception as e:
        logger.error(f"Bedrock classification failed: {str(e)}")
        # Fallback to keyword-based classification
        logger.info("Using fallback keyword-based classification")
        return fallback_classification(invoice_text, email_metadata)


def fallback_classification(invoice_text, email_metadata):
    """
    Fallback keyword-based classification when Bedrock is unavailable.
    
    This function uses simple keyword matching to classify invoices.
    It's less accurate than Bedrock but ensures the system continues to function.
    
    Args:
        invoice_text: Extracted text content from the invoice
        email_metadata: Email information (subject, sender, etc.)
        
    Returns:
        str: Department name based on keyword matching
    """
    # Combine invoice text and email subject for keyword matching
    combined_text = f"{invoice_text.lower()} {email_metadata.get('subject', '').lower()}"
    
    # Define keywords for each department
    # These are common terms that indicate which department should handle the invoice
    keywords = {
        'Finance': ['invoice', 'payment', 'tax', 'accounting', 'finance', 'billing'],
        'IT': ['computer', 'software', 'hardware', 'license', 'it', 'technology', 'server'],
        'HR': ['payroll', 'benefits', 'recruitment', 'training', 'hr', 'employee'],
        'Operations': ['warehouse', 'equipment', 'facility', 'maintenance', 'operations', 'supply'],
        'Marketing': ['campaign', 'advertising', 'promotion', 'media', 'marketing', 'brand']
    }
    
    # Count keyword matches for each department
    department_scores = {}
    for dept, dept_keywords in keywords.items():
        score = sum(1 for keyword in dept_keywords if keyword in combined_text)
        department_scores[dept] = score
    
    # Select department with highest score
    if max(department_scores.values()) > 0:
        department = max(department_scores, key=department_scores.get)
        logger.info(f"Fallback classification result: {department} (score: {department_scores[department]})")
    else:
        # Default to Finance if no keywords match
        department = 'Finance'
        logger.info("No keyword matches found, defaulting to Finance")
    
    return department


def organize_email(inbox_bucket, destination_bucket, email_metadata, department, invoice_text):
    """
    Organize email into department-specific folder in destination bucket.
    
    This function:
    1. Creates department and metadata prefixes in S3
    2. Copies the email file to the department folder
    3. Creates a metadata JSON file for tracking and display
    
    Args:
        inbox_bucket: Source S3 bucket containing the original email
        destination_bucket: Destination S3 bucket for organized emails
        email_metadata: Email information (key, sender, subject, etc.)
        department: Classified department name
        invoice_text: Extracted invoice content for metadata
        
    Returns:
        str: S3 key of the organized email in destination bucket
        
    Raises:
        Exception: If email organization fails
    """
    # Get source email key
    source_key = email_metadata.get('email_key', email_metadata.get('emailKey'))
    
    if not inbox_bucket or not destination_bucket or not source_key:
        error_msg = "Inbox bucket, destination bucket, or email key not found"
        logger.error(error_msg)
        raise Exception(error_msg)
    
    # Use standard prefix structure: departments/{department_name}/
    prefix_structure = f"departments/{department.lower()}"
    
    # Create department and metadata prefixes in S3
    # S3 doesn't have true folders, but creating objects with trailing slashes
    # creates the appearance of folders in the console and some tools
    try:
        # Create the department prefix
        s3.put_object(
            Bucket=destination_bucket,
            Key=f"{prefix_structure}/",
            Body=''
        )
        
        # Also create the metadata prefix
        s3.put_object(
            Bucket=destination_bucket,
            Key=f"{prefix_structure}/metadata/",
            Body=''
        )
        
        logger.info(f"Created prefixes: {prefix_structure}/ and {prefix_structure}/metadata/")
    except Exception as e:
        logger.warning(f"Could not create prefix {prefix_structure}: {str(e)}")
        # Continue even if prefix creation fails - the copy will still work
    
    # Generate the target key for the email file
    target_key = f"{prefix_structure}/{os.path.basename(source_key)}"
    
    logger.info(f"Moving email from {inbox_bucket}/{source_key} to {destination_bucket}/{target_key}")
    
    # Check if source file exists before copying
    try:
        s3.head_object(Bucket=inbox_bucket, Key=source_key)
        logger.info(f"Source file exists: {inbox_bucket}/{source_key}")
    except Exception as e:
        logger.warning(f"Source file does not exist: {inbox_bucket}/{source_key}. Creating test file for demonstration.")
        # For test events, create a dummy email file
        # This allows the function to work even without a real email file
        test_email_content = f"""From: {email_metadata.get('sender', 'test@example.com')}
To: invoices@company.com
Subject: {email_metadata.get('subject', 'Test Invoice')}
Date: {datetime.datetime.now().strftime('%a, %d %b %Y %H:%M:%S %z')}

This is a test email with a {department} invoice attachment.
Classified as: {department}
"""
        s3.put_object(
            Bucket=inbox_bucket,
            Key=source_key,
            Body=test_email_content,
            ContentType='message/rfc822'
        )
        logger.info(f"Created test email file: {inbox_bucket}/{source_key}")
    
    # Copy the email from inbox to destination bucket
    s3.copy_object(
        Bucket=destination_bucket,
        CopySource={'Bucket': inbox_bucket, 'Key': source_key},
        Key=target_key
    )
    
    logger.info(f"Successfully copied email to: {destination_bucket}/{target_key}")
    
    # Create metadata JSON file for tracking and web display
    # This metadata will be used by the web frontend to display email information
    metadata_content = {
        'department': department,
        'originalKey': source_key,
        'destinationKey': target_key,
        'metadata': {
            'email_key': source_key,
            'sender': email_metadata.get('sender', 'Unknown'),
            'subject': email_metadata.get('subject', 'No Subject'),
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'attachmentCount': email_metadata.get('attachmentCount', 0),
            'classificationTime': email_metadata.get('classificationTime', 0)
        },
        'invoicePreview': invoice_text[:500] if invoice_text else 'No content available'
    }
    
    # Generate metadata file key
    # Use the email filename without extension for the metadata filename
    email_basename = os.path.basename(source_key)
    email_name_without_ext = os.path.splitext(email_basename)[0]
    metadata_key = f"{prefix_structure}/metadata/{email_name_without_ext}.json"
    
    # Upload metadata JSON to S3
    s3.put_object(
        Bucket=destination_bucket,
        Key=metadata_key,
        Body=json.dumps(metadata_content, indent=2),
        ContentType='application/json'
    )
    
    logger.info(f"Created metadata file: {destination_bucket}/{metadata_key}")
    
    return target_key
