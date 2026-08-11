"""
Email Processor Lambda Function

This Lambda function processes incoming emails from S3, extracts PDF attachments,
and invokes Amazon Bedrock Data Automation (BDA) for document processing.

Workflow:
1. Triggered by S3 ObjectCreated event on inbox bucket (incoming/ prefix)
2. Parses EML file and extracts metadata (sender, subject, body)
3. Identifies PDF attachments that are likely invoices
4. Uploads attachments to S3 with meaningful naming
5. Invokes BDA for document text extraction
6. Starts Step Functions state machine for orchestration
7. Stores BDA job metadata for tracking

Requirements: 4.1, 4.2, 4.3, 4.7, 11.1, 11.4
"""

from email import policy
import json
import boto3
import os
import email
import uuid
import logging
from datetime import datetime, timezone
import traceback
import re
import unicodedata

# Get region from environment variable or default to current session region
AWS_REGION = os.environ.get('AWS_REGION', boto3.session.Session().region_name)

# Initialize AWS clients outside of handler function to improve performance
# This reduces cold start time and reuses connections across invocations
s3 = boto3.client("s3")
bedrock_data_automation = boto3.client("bedrock-data-automation-runtime", region_name=AWS_REGION)
bda_client = boto3.client("bedrock-data-automation", region_name=AWS_REGION)
stepfunctions_client = boto3.client("stepfunctions", region_name=AWS_REGION)
cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Keywords used to identify invoice-related emails
# These are checked against email subject and body content
INVOICE_KEYWORDS = [keyword.lower() for keyword in [
    "Invoice",
    "Bill",
    "Statement",
    "Account",
    "Receipt"
]]

# S3 folder where BDA will write extracted document data
OUTPUT_FOLDER_NAME = "bda-output"

# BDA profile for document processing
# This profile defines the extraction capabilities and models to use
BDA_PROFILE_ID = "us.data-automation-v1"

# Retrieve BDA project ID at module initialization
# This is done once per Lambda container to avoid repeated API calls
try:
    response = bda_client.list_data_automation_projects()
    BDA_PROJECT_ID = None
    
    # Find the invoice-processing project by name
    for project in response["projects"]:
        if project["projectName"] == "invoice-processing":
            project_arn = project["projectArn"]
            # Extract project ID from ARN format: arn:aws:bedrock:region:account:data-automation-project/PROJECT_ID
            BDA_PROJECT_ID = re.search(r'data-automation-project/(.+)', project_arn).group(1)
            logger.info(f"Found BDA project 'invoice-processing' with ID: {BDA_PROJECT_ID}")
            break
    
    if not BDA_PROJECT_ID:
        logger.warning("BDA project 'invoice-processing' not found, will use fallback")
        BDA_PROJECT_ID = "fallback-project-id"
except Exception as e:
    logger.warning(f"Could not retrieve BDA project ID: {str(e)}")
    BDA_PROJECT_ID = "fallback-project-id"


def lambda_handler(event, context):
    """
    Main handler for processing incoming email files from S3.
    
    This function is triggered by S3 ObjectCreated events when EML files
    are uploaded to the inbox bucket's incoming/ prefix.
    
    Args:
        event: S3 event containing bucket and object key information
        context: Lambda context with runtime information
        
    Returns:
        dict: Response with statusCode and body containing processing results
        
    Raises:
        Exception: Logs errors but returns 500 status instead of raising
    """
    # Log the actual bucket names being used for debugging
    inbox_bucket = os.environ.get('INBOX_BUCKET')
    destination_bucket = os.environ.get('DESTINATION_BUCKET')
    logger.info(f"Using bucket names - Inbox: {inbox_bucket}, Destination: {destination_bucket}")
    
    logger.info(f"Starting to process new email...")
    
    try:
        # Extract S3 bucket and object key from the event
        # Event structure: Records[0].s3.bucket.name and Records[0].s3.object.key
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]

        logger.info(f"Processing email from bucket: {bucket}, key: {key}")
        
        # Verify we're using the correct bucket (defensive check)
        if bucket != inbox_bucket:
            logger.warning(f"Event bucket ({bucket}) doesn't match configured inbox bucket ({inbox_bucket})")
        
        # Retrieve the email file from S3
        response = s3.get_object(Bucket=bucket, Key=key)
        raw_email = response["Body"].read()
        
        # Parse the email using Python's email library with default policy
        # policy.default handles modern email formats including MIME and Unicode
        msg = email.message_from_bytes(raw_email, policy=policy.default)

        # Extract email metadata
        subject = msg["Subject"] or "No Subject"
        sender = msg["From"] or "Unknown Sender"

        logger.info(f"Email from {sender} with subject: {subject}")

        # Extract email body and check if it's likely an invoice
        email_body = extract_email_body(msg)
        is_invoice = is_likely_invoice(email_body, subject)
        logger.info(f"Is likely invoice: {is_invoice}")
                                              
        # Get all attachments from the email
        attachments = list(msg.iter_attachments())
        logger.info(f"Found {len(attachments)} attachments")

        # Skip processing if no attachments found
        if not attachments:
            logger.info("No attachments found - ignoring")
            return {
                'statusCode': 200,
                'body': json.dumps("No attachments found - ignoring")
            }

        # Setup BDA ARNs using Lambda context
        # Extract AWS account ID from the Lambda function ARN
        aws_account_id = context.invoked_function_arn.split(":")[4]
        bda_project_arn = f"arn:aws:bedrock:{AWS_REGION}:{aws_account_id}:data-automation-project/{BDA_PROJECT_ID}"
        bda_profile_arn = f"arn:aws:bedrock:{AWS_REGION}:{aws_account_id}:data-automation-profile/{BDA_PROFILE_ID}"

        logger.info(f"Using BDA Project ARN: {bda_project_arn}")

        # Record start time for processing time metric
        start_time = datetime.now(timezone.utc)
        
        # Process each attachment
        processed_count = 0
        for part in attachments:
            filename = part.get_filename()
            if not filename:
                continue
                
            filename = filename.lower()
            logger.info(f"Processing attachment: {filename}")

            # Check if filename contains invoice keywords (secondary check)
            filename_contains_keyword = False
            if not is_invoice:
                filename_contains_keyword = any(keyword in filename for keyword in INVOICE_KEYWORDS)

            # Only process PDFs that are likely invoices
            # This filters out non-invoice attachments to reduce processing costs
            if filename.endswith(".pdf") and (is_invoice or filename_contains_keyword):
                # Create meaningful and unique filename with timestamp
                # Format: attachments/YYYY-MM-DDTHH:MM:SS-sender-filename.pdf
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                sanitized_sender = sanitize_for_s3(sender.split('@')[0])
                sanitized_filename = sanitize_for_s3(filename, allow_dot=True)
                attachment_key = f"attachments/{timestamp}-{sanitized_sender}-{sanitized_filename}"

                # Create metadata for tracking
                metadata = {
                    "email_key": key,
                    "filename": filename,
                    "attachment_key": attachment_key,
                    "sender": sender,
                    "subject": subject
                }

                # Extract PDF binary data
                file_data = part.get_payload(decode=True)

                # Upload PDF attachment to S3
                s3.put_object(
                    Bucket=bucket,
                    Key=attachment_key,
                    Body=file_data,
                    Metadata=metadata,
                    ContentType="application/pdf"
                )

                # Create extended metadata including email body and timestamp
                metadata_with_body = {
                    **metadata,
                    "email_body": email_body,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                # Store metadata as JSON file alongside the attachment
                json_data = json.dumps(metadata_with_body, ensure_ascii=False).encode('utf-8')

                s3.put_object(
                    Bucket=bucket,
                    Key=f"{attachment_key}/metadata.json",
                    Body=json_data,
                    ContentType="application/json"
                )

                logger.info(f"Uploaded attachment to S3: {attachment_key}")

                # Get S3 URI for the attachment (required by BDA)
                s3_uri = f"s3://{bucket}/{attachment_key}"

                try:
                    # Invoke Bedrock Data Automation asynchronously
                    # BDA will extract text and structured data from the PDF
                    response = bedrock_data_automation.invoke_data_automation_async(
                        clientToken=str(uuid.uuid4()),  # Unique token for idempotency
                        inputConfiguration={
                            's3Uri': s3_uri  # Input PDF location
                        },
                        outputConfiguration={
                            's3Uri': f"s3://{bucket}/{OUTPUT_FOLDER_NAME}"  # Where BDA writes results
                        },
                        dataAutomationConfiguration={
                            'dataAutomationProjectArn': bda_project_arn,
                            'stage': 'LIVE'  # Use LIVE stage for production processing
                        },
                        dataAutomationProfileArn=bda_profile_arn,
                        notificationConfiguration={
                            'eventBridgeConfiguration': {
                                'eventBridgeEnabled': True  # Enable EventBridge notifications
                            }
                        }
                    )

                    # Extract invocation ID from the response ARN
                    invocation_id = response["invocationArn"].split('/')[-1]
                    logger.info(f"Successfully invoked BDA IDP (job_id: {invocation_id})")
                    
                    # Store BDA job information for tracking and debugging
                    invocation_data = {
                        "invocationId": invocation_id,
                        "invocationArn": response["invocationArn"],
                        "attachmentKey": attachment_key,
                        "emailMetadata": metadata_with_body,
                        "s3OutputUri": f"s3://{bucket}/{OUTPUT_FOLDER_NAME}",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Store job metadata in S3 for audit trail
                    s3.put_object(
                        Bucket=bucket,
                        Key=f"bda-jobs/{invocation_id}.json",
                        Body=json.dumps(invocation_data),
                        ContentType="application/json"
                    )
                    
                    # Start Step Functions execution to orchestrate classification workflow
                    # Step Functions will wait for BDA completion and then invoke the classifier
                    state_machine_arn = os.environ.get('STATE_MACHINE_ARN')
                    if state_machine_arn:
                        execution_input = {
                            "bucket": bucket,
                            "invocationId": invocation_id,
                            "emailMetadata": metadata_with_body,
                            "classifierFunctionName": os.environ.get('CLASSIFIER_FUNCTION_NAME')
                        }
                        
                        stepfunctions_client.start_execution(
                            stateMachineArn=state_machine_arn,
                            name=f"invoice-processing-{invocation_id}",
                            input=json.dumps(execution_input)
                        )
                        
                        logger.info(f"Started Step Functions execution for invocation {invocation_id}")
                    else:
                        logger.warning("STATE_MACHINE_ARN not configured, skipping Step Functions execution")
                    
                    processed_count += 1
                        
                except Exception as bda_error:
                    logger.error(f"BDA invocation failed: {str(bda_error)}")
                    logger.error(f"Stack trace: {traceback.format_exc()}")
                    # Continue processing other attachments even if BDA fails
                    # This ensures partial success rather than complete failure
                    continue

        # Publish custom metrics to CloudWatch
        try:
            # Calculate processing time
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            
            # Publish EmailsProcessed metric
            cloudwatch.put_metric_data(
                Namespace='EmailClassification',
                MetricData=[
                    {
                        'MetricName': 'EmailsProcessed',
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': end_time
                    },
                    {
                        'MetricName': 'ProcessingTime',
                        'Value': processing_time,
                        'Unit': 'Seconds',
                        'Timestamp': end_time
                    }
                ]
            )
            logger.info(f"Published metrics: EmailsProcessed=1, ProcessingTime={processing_time}s")
        except Exception as metric_error:
            logger.warning(f"Failed to publish metrics: {str(metric_error)}")
            # Don't fail the function if metrics fail

        return {
            "statusCode": 200,
            "body": json.dumps(f"Successfully processed {processed_count} attachments from email {key}.")
        }
        
    except Exception as e:
        stack_trace = traceback.format_exc()
        logger.error(f"Error processing email: {str(e)}")
        logger.error(f"Stack trace: {stack_trace}")
        
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "stack_trace": stack_trace,
                "message": "Error processing email"
            })
        }


def is_likely_invoice(email_body: str, email_subject: str) -> bool:
    """
    Check if email content suggests it contains an invoice.
    
    This function performs keyword matching against the email body and subject
    to determine if the email is likely to contain invoice-related content.
    
    Args:
        email_body: The text content of the email body
        email_subject: The email subject line
        
    Returns:
        bool: True if invoice keywords are found, False otherwise
    """
    if not email_body:
        email_body = ""
    if not email_subject:
        email_subject = ""
        
    email_body = email_body.lower()
    email_subject = email_subject.lower()
    
    # Check if any invoice keyword appears in body or subject
    return any(
        keyword in email_body or 
        keyword in email_subject 
        for keyword in INVOICE_KEYWORDS
    )


def extract_email_body(msg) -> str:
    """
    Extract email body using the preferred content type.
    
    This function attempts to extract the email body, preferring plain text
    over HTML format. It handles various email formats and encodings.
    
    Args:
        msg: Email message object from email.message_from_bytes()
        
    Returns:
        str: The email body text, or empty string if extraction fails
    """
    try:
        # Get body with preference for plain text, fallback to HTML
        # This ensures we get readable content regardless of email format
        body_part = msg.get_body(preferencelist=("plain", "html"))
        if body_part is not None:
            content = body_part.get_payload(decode=True)
            if content:
                # Decode bytes to string, ignoring invalid UTF-8 characters
                return content.decode('utf-8', errors='ignore')
        return ""
    except Exception as e:
        logger.error(f"Failed to extract email body: {e}")
        return ""

    
def sanitize_for_s3(value: str, allow_dot=False) -> str:
    """
    Sanitizes a string to be safe for use in S3 object keys.
    
    S3 object keys have specific requirements and best practices:
    - Avoid special characters that need URL encoding
    - Keep keys readable and meaningful
    - Prevent issues with different operating systems
    
    Args:
        value: The string to sanitize
        allow_dot: If True, preserve dots (useful for file extensions)
        
    Returns:
        str: Sanitized string safe for S3 keys, max 100 characters
    """
    if not value:
        return "unknown"

    # Normalize unicode characters to ASCII equivalents
    # Example: "café" becomes "cafe"
    try:
        value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    except:
        pass

    # Convert to lowercase for consistency
    value = value.lower()

    # Replace problematic characters with dashes
    # @ and spaces are common in email addresses and names
    value = re.sub(r"[@\s]+", "-", value)
    
    # Remove all non-alphanumeric characters except dash (and dot if allowed)
    if allow_dot:
        value = re.sub(r"[^\w.-]", "-", value)
    else:
        value = re.sub(r"[^\w-]", "-", value)

    # Collapse multiple consecutive dashes into single dash
    value = re.sub(r"-{2,}", "-", value)

    # Strip leading/trailing dashes
    value = value.strip("-")

    # Truncate to safe length (S3 allows 1024 chars, but keep it reasonable)
    return value[:100]
