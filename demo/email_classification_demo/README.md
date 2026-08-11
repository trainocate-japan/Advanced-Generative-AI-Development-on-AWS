# Email Classification System with Amazon Bedrock Data Automation

An educational demonstration of serverless email classification using AWS CDK, Amazon Bedrock, and Bedrock Data Automation (BDA). This system automatically processes uploaded email files (.eml), extracts invoice attachments, classifies them by department using AI, and organizes them in S3 for easy access through a web interface.

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Configuration](#configuration)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Educational Learning Objectives](#educational-learning-objectives)
- [Cleanup](#cleanup)

## Overview

### What This System Does

1. **Upload**: Users upload email files (.eml format) through a web interface
2. **Extract**: System extracts PDF invoice attachments from emails
3. **Process**: Amazon Bedrock Data Automation extracts text and structured data from PDFs
4. **Classify**: Amazon Bedrock Converse API classifies invoices into departments (Finance, IT, HR, Operations, Marketing)
5. **Organize**: Emails are automatically stored in department-specific S3 folders
6. **Display**: Web interface shows classified emails organized by department

### Key Features

- **Serverless Architecture**: No servers to manage, scales automatically
- **AI-Powered Classification**: Uses Amazon Bedrock for intelligent document understanding
- **Event-Driven Processing**: Asynchronous pipeline with S3 events and Step Functions
- **Web-Based Interface**: Modern, responsive UI with drag-and-drop upload
- **Infrastructure as Code**: Complete AWS CDK deployment for reproducibility
- **Educational Focus**: Extensively documented code for learning AWS patterns

## Architecture

### High-Level Data Flow

```
User → CloudFront → Web Interface
         ↓
    API Gateway → Upload Handler Lambda → S3 Inbox Bucket
                                            ↓
                                    Email Processor Lambda
                                            ↓
                                  Bedrock Data Automation
                                            ↓
                                    Step Functions
                                            ↓
                                  Classifier Lambda
                                            ↓
                              S3 Destination Bucket (by department)
                                            ↓
                                    Web Interface (Department View)
```

### AWS Services Used

- **Compute**: AWS Lambda (Python 3.12)
- **Storage**: Amazon S3 (3 buckets: inbox, destination, website)
- **API**: Amazon API Gateway (REST API)
- **CDN**: Amazon CloudFront
- **AI/ML**: Amazon Bedrock (Nova Lite model), Bedrock Data Automation
- **Orchestration**: AWS Step Functions
- **Monitoring**: Amazon CloudWatch (logs, metrics, dashboards, alarms)
- **IAM**: Least-privilege roles for each Lambda function

### Component Descriptions

#### 1. Upload Handler Lambda
- Receives EML files from API Gateway
- Validates file format and size (max 10MB)
- Stores files in S3 inbox bucket with unique keys

#### 2. Email Processor Lambda
- Triggered by S3 ObjectCreated events
- Parses EML files and extracts PDF attachments
- Invokes Bedrock Data Automation for text extraction
- Starts Step Functions workflow

#### 3. Step Functions State Machine
- Orchestrates the classification workflow
- Waits for BDA completion (30-second intervals)
- Checks for BDA output in S3
- Invokes Classifier Lambda when ready

#### 4. Invoice Classifier Lambda
- Retrieves BDA extraction results
- Calls Bedrock Converse API for classification
- Falls back to keyword-based classification if Bedrock fails
- Copies emails to department folders
- Creates metadata JSON files

#### 5. Web Frontend
- Static HTML/CSS/JavaScript hosted on S3
- Served via CloudFront for global distribution
- Drag-and-drop file upload
- Interactive architecture diagram with tooltips
- Department view showing classified emails

## Prerequisites

### Required Software

- **AWS Account**: With permissions to create IAM roles, Lambda functions, S3 buckets, etc.
- **AWS CLI**: Version 2.x configured with credentials
  ```bash
  aws configure
  ```
- **Node.js**: Version 18.x or later (for AWS CDK)
  ```bash
  node --version  # Should be 18.x or higher
  ```
- **Python**: Version 3.12 or later
  ```bash
  python3 --version  # Should be 3.12 or higher
  ```
- **AWS CDK CLI**: Version 2.120.0 or later
  ```bash
  npm install -g aws-cdk
  cdk --version
  ```

### AWS Service Access

Ensure your AWS account has access to:
- Amazon Bedrock (enable in AWS Console if not already)
- Bedrock Data Automation (BDA) - may require service quota increase
- All standard services (Lambda, S3, API Gateway, CloudFront, Step Functions)

### Bedrock Model Access

1. Navigate to Amazon Bedrock in AWS Console
2. Go to "Model access" in the left sidebar
3. Request access to **Amazon Nova Lite** model
4. Wait for approval (usually instant for Nova models)

## Quick Start

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd email-classification-cdk-migration

# Install Python dependencies
pip3 install -r requirements.txt
```

### 2. Bootstrap CDK (First Time Only)

```bash
# Bootstrap your AWS environment for CDK
cdk bootstrap

# This creates an S3 bucket and IAM roles for CDK deployments
```

### 3. Deploy Using Setup Script

```bash
# Make the setup script executable
chmod +x scripts/setup.sh

# Run the automated setup
./scripts/setup.sh
```

The setup script will:
- Deploy the CDK stack (takes 5-10 minutes)
- Upload department configuration to S3
- Display the CloudFront URL for accessing the web interface
- Show stack outputs (bucket names, API endpoint)

### 4. Access the Web Interface

After deployment completes, the script outputs the CloudFront URL:

```
✅ Deployment successful!
🌐 Web Interface: https://d1234567890abc.cloudfront.net
```

Open this URL in your browser to access the email classification system.

### 5. Upload a Test Email

1. Navigate to the `incoming/` directory
2. Select any sample EML file (e.g., `email_01_finance.eml`)
3. Drag and drop it onto the upload zone in the web interface
4. Watch the processing status update in real-time
5. View the classified email in the department view

## Project Structure

```
.
├── app.py                              # CDK app entry point
├── cdk.json                            # CDK configuration
├── requirements.txt                    # Python dependencies
├── email_classification/               # Main CDK package
│   ├── __init__.py
│   └── email_classification_stack.py  # Complete stack definition (2000+ lines)
├── lambda_functions/                   # Lambda function code
│   ├── upload_handler.py              # Handles API Gateway uploads
│   ├── email_processor.py             # Processes emails and invokes BDA
│   └── invoice_classifier.py          # Classifies and organizes emails
├── website/                            # Frontend assets
│   ├── index.html                     # Main upload interface
│   ├── styles.css                     # Responsive styling
│   ├── app.js                         # Upload and department view logic
│   └── architecture-diagram.svg       # Interactive system diagram
├── config/                             # Configuration files
│   └── department_config.json         # Department definitions
├── scripts/                            # Automation scripts
│   ├── setup.sh                       # Automated deployment
│   └── teardown.sh                    # Automated cleanup
├── incoming/                           # Sample EML files for testing
│   ├── email_01_finance.eml
│   ├── email_02_it.eml
│   ├── email_03_marketing.eml
│   ├── email_04_operations.eml
│   └── email_05_hr.eml
└── README.md                           # This file
```

### S3 Bucket Organization

#### Inbox Bucket (`email-classification-inbox-{account}-{region}`)
```
incoming/                   # Uploaded EML files
attachments/                # Extracted PDF invoices
bda-output/                 # BDA extraction results
bda-jobs/                   # BDA job metadata
department_config.json      # Department configuration
```

#### Destination Bucket (`email-classification-dest-{account}-{region}`)
```
departments/
  ├── finance/              # Finance department emails
  │   ├── metadata/         # JSON metadata files
  │   └── *.eml             # Classified emails
  ├── it/
  ├── hr/
  ├── operations/
  └── marketing/
```

#### Website Bucket (`email-classification-web-{account}-{region}`)
```
index.html                  # Main page
styles.css                  # Styling
app.js                      # Frontend logic
architecture-diagram.svg    # Interactive diagram
config.js                   # API Gateway URL (auto-generated)
```

## Configuration

### Department Configuration

The system uses `config/department_config.json` to define available departments:

```json
{
  "departments": [
    {
      "name": "Finance",
      "prefixPath": "departments/finance"
    },
    {
      "name": "IT",
      "prefixPath": "departments/it"
    },
    {
      "name": "HR",
      "prefixPath": "departments/hr"
    },
    {
      "name": "Operations",
      "prefixPath": "departments/operations"
    },
    {
      "name": "Marketing",
      "prefixPath": "departments/marketing"
    }
  ]
}
```

**To add or modify departments:**

1. Edit `config/department_config.json`
2. Upload to S3:
   ```bash
   aws s3 cp config/department_config.json s3://<inbox-bucket-name>/department_config.json
   ```
3. No Lambda redeployment needed - changes take effect immediately

### Environment Variables

Lambda functions use these environment variables (automatically set by CDK):

- `INBOX_BUCKET_NAME`: Source bucket for emails
- `DESTINATION_BUCKET`: Target bucket for classified emails
- `CONFIG_BUCKET_NAME`: Bucket containing department config
- `STATE_MACHINE_ARN`: Step Functions state machine ARN
- `CLASSIFIER_FUNCTION_NAME`: Classifier Lambda function name
- `BEDROCK_MODEL_ID`: Bedrock model (default: `amazon.nova-lite-v1:0`)

### Bedrock Model Configuration

To use a different Bedrock model, update the environment variable in `email_classification_stack.py`:

```python
classifier_function = _lambda.Function(
    self, "InvoiceClassifierFunction",
    environment={
        "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",  # Change here
        # ... other env vars
    }
)
```

Then redeploy:
```bash
cdk deploy
```

## Testing

### Using Sample EML Files

The `incoming/` directory contains 10 sample EML files covering all departments:

| File | Expected Department | Description |
|------|-------------------|-------------|
| `email_01_finance.eml` | Finance | Vendor invoice |
| `email_02_it.eml` | IT | Software license invoice |
| `email_03_marketing.eml` | Marketing | Advertising campaign invoice |
| `email_04_operations.eml` | Operations | Equipment purchase invoice |
| `email_05_hr.eml` | HR | Training services invoice |
| `email_06_unknown.eml` | Finance (fallback) | Ambiguous content |
| `email_07_finance.eml` | Finance | Tax services invoice |
| `email_08_it.eml` | IT | Hardware purchase invoice |
| `email_09_marketing.eml` | Marketing | Media buy invoice |
| `email_10_operations.eml` | Operations | Facility maintenance invoice |

### Manual Testing Steps

1. **Upload via Web Interface**
   - Open CloudFront URL in browser
   - Drag and drop an EML file from `incoming/`
   - Verify upload progress displays
   - Confirm classification result appears

2. **Verify S3 Storage**
   ```bash
   # Check inbox bucket
   aws s3 ls s3://<inbox-bucket-name>/incoming/
   
   # Check destination bucket
   aws s3 ls s3://<destination-bucket-name>/departments/finance/
   ```

3. **Check CloudWatch Logs**
   ```bash
   # View Email Processor logs
   aws logs tail /aws/lambda/EmailClassification-EmailProcessor --follow
   
   # View Classifier logs
   aws logs tail /aws/lambda/EmailClassification-InvoiceClassifier --follow
   ```

4. **View Department in Web Interface**
   - Click on a department tab (e.g., "Finance")
   - Verify emails appear in the list
   - Check metadata displays correctly

### Automated Testing Scripts

#### Test API Upload Endpoint
```bash
python3 test_api_upload.py
```

This script:
- Uploads a sample EML file to API Gateway
- Verifies successful upload response
- Checks file appears in S3 inbox bucket

#### Test S3 Trigger
```bash
python3 test_s3_trigger.py
```

This script:
- Directly uploads an EML file to S3
- Verifies Email Processor Lambda triggers
- Checks BDA invocation occurs

### Expected Processing Time

- **Upload to S3**: < 1 second
- **Email Processor**: 2-5 seconds
- **BDA Processing**: 30-60 seconds
- **Classification**: 2-5 seconds
- **Total**: ~40-70 seconds per email

## Troubleshooting

### Common Issues and Solutions

#### 1. CDK Bootstrap Fails

**Error**: `Need to perform AWS calls for account XXX, but no credentials found`

**Solution**:
```bash
# Configure AWS credentials
aws configure

# Verify credentials work
aws sts get-caller-identity

# Try bootstrap again
cdk bootstrap
```

#### 2. Bedrock Model Access Denied

**Error**: `AccessDeniedException: You don't have access to the model`

**Solution**:
1. Go to AWS Console → Amazon Bedrock
2. Click "Model access" in left sidebar
3. Click "Manage model access"
4. Enable "Amazon Nova Lite"
5. Wait for status to show "Access granted"
6. Redeploy: `cdk deploy`

#### 3. BDA Service Not Available

**Error**: `ServiceQuotaExceededException` or `BDA project not found`

**Solution**:
1. Ensure BDA is available in your region (us-east-1, us-west-2)
2. Request service quota increase if needed
3. Verify BDA project exists:
   ```bash
   aws bedrock-data-automation list-data-automation-projects
   ```

#### 4. Upload Fails with CORS Error

**Error**: `Access to fetch blocked by CORS policy`

**Solution**:
- This shouldn't happen with proper deployment
- Verify API Gateway CORS is configured (automatic in CDK)
- Check browser console for actual error
- Try clearing browser cache

#### 5. Classification Takes Too Long

**Issue**: Processing stuck at "Classifying invoice..."

**Solution**:
1. Check Step Functions execution:
   ```bash
   aws stepfunctions list-executions --state-machine-arn <arn>
   ```
2. View execution details in AWS Console
3. Check if BDA output exists:
   ```bash
   aws s3 ls s3://<inbox-bucket>/bda-output/
   ```
4. Review CloudWatch logs for errors

#### 6. Emails Not Appearing in Department View

**Issue**: Upload succeeds but emails don't show in department tabs

**Solution**:
1. Check destination bucket:
   ```bash
   aws s3 ls s3://<destination-bucket>/departments/ --recursive
   ```
2. Verify metadata files exist:
   ```bash
   aws s3 ls s3://<destination-bucket>/departments/finance/metadata/
   ```
3. Check browser console for JavaScript errors
4. Verify API Gateway URL in `config.js` is correct

#### 7. CloudFront Distribution Not Working

**Error**: `AccessDenied` when accessing CloudFront URL

**Solution**:
- Wait 10-15 minutes for CloudFront distribution to fully deploy
- Check distribution status in AWS Console
- Verify Origin Access Identity (OAI) is configured
- Try invalidating CloudFront cache:
  ```bash
  aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
  ```

#### 8. Lambda Function Timeout

**Error**: `Task timed out after 30.00 seconds`

**Solution**:
- This is normal for BDA processing (handled by Step Functions)
- For other functions, check CloudWatch logs for bottlenecks
- Increase timeout if needed (edit CDK stack)

### Debugging Tips

#### View All Stack Outputs
```bash
aws cloudformation describe-stacks --stack-name EmailClassificationStack \
  --query 'Stacks[0].Outputs' --output table
```

#### Monitor Lambda Invocations
```bash
# Real-time log streaming
aws logs tail /aws/lambda/EmailClassification-EmailProcessor --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/EmailClassification-InvoiceClassifier \
  --filter-pattern "ERROR"
```

#### Check Step Functions Execution
```bash
# List recent executions
aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --max-results 10

# Get execution details
aws stepfunctions describe-execution --execution-arn <execution-arn>
```

#### Verify S3 Event Notifications
```bash
aws s3api get-bucket-notification-configuration \
  --bucket <inbox-bucket-name>
```

## Educational Learning Objectives

This project is designed to teach the following AWS and software engineering concepts:

### 1. Infrastructure as Code (IaC)
- **AWS CDK**: Define cloud resources using Python code
- **Declarative Infrastructure**: Resources defined once, deployed consistently
- **Version Control**: Infrastructure changes tracked in Git
- **Reproducibility**: Deploy identical environments across accounts/regions

**Key Takeaways**:
- CDK constructs abstract CloudFormation complexity
- Type safety catches errors before deployment
- Stack outputs enable cross-stack references
- Custom resources handle deployment-time operations

### 2. Serverless Architecture Patterns
- **Event-Driven Design**: S3 events trigger Lambda functions
- **Asynchronous Processing**: Step Functions orchestrate long-running workflows
- **Stateless Functions**: Lambda functions scale automatically
- **Managed Services**: No servers to patch or maintain

**Key Takeaways**:
- Pay only for actual usage (no idle costs)
- Automatic scaling handles traffic spikes
- Focus on business logic, not infrastructure
- Resilience through managed service SLAs

### 3. AI/ML Integration with Amazon Bedrock
- **Bedrock Data Automation**: Extract structured data from documents
- **Converse API**: Natural language classification
- **Prompt Engineering**: Craft effective prompts for accurate results
- **Fallback Strategies**: Handle AI service failures gracefully

**Key Takeaways**:
- BDA simplifies document processing pipelines
- Bedrock provides enterprise-grade AI without ML expertise
- Always implement fallback logic for production systems
- Monitor AI service costs and usage

### 4. Security Best Practices
- **Least Privilege IAM**: Each Lambda has minimal required permissions
- **Encryption**: S3 buckets encrypted at rest
- **HTTPS Only**: CloudFront enforces secure connections
- **No Public Access**: S3 buckets not publicly accessible

**Key Takeaways**:
- Never use wildcard (*) permissions in production
- Resource-level IAM policies limit blast radius
- Origin Access Identity (OAI) secures S3 website hosting
- CloudWatch logs help audit access patterns

### 5. Observability and Monitoring
- **Structured Logging**: JSON logs for easy parsing
- **Custom Metrics**: Track business-specific KPIs
- **CloudWatch Dashboards**: Visualize system health
- **Alarms**: Proactive alerting on errors

**Key Takeaways**:
- Log context (request IDs, user IDs) for debugging
- Emit metrics at key processing stages
- Set alarms on error rates, not just counts
- Use log insights for complex queries

### 6. API Design
- **REST API**: Standard HTTP methods and status codes
- **CORS Configuration**: Enable cross-origin requests
- **Request Validation**: Validate input before processing
- **Error Responses**: Return meaningful error messages

**Key Takeaways**:
- API Gateway handles authentication, throttling, caching
- Binary media types support file uploads
- Lambda proxy integration simplifies request/response handling
- API versioning enables backward compatibility

### 7. Frontend Development
- **Vanilla JavaScript**: No framework dependencies
- **Fetch API**: Modern HTTP client
- **Progressive Enhancement**: Works without JavaScript (basic upload)
- **Responsive Design**: Mobile-first CSS

**Key Takeaways**:
- FormData handles multipart file uploads
- Async/await simplifies promise handling
- CSS Grid and Flexbox enable responsive layouts
- SVG provides scalable, interactive diagrams

### 8. DevOps Practices
- **Automated Deployment**: Scripts handle setup and teardown
- **Idempotent Operations**: Safe to run multiple times
- **Rollback Strategy**: CDK tracks previous versions
- **Documentation**: README guides new developers

**Key Takeaways**:
- Automation reduces human error
- Scripts should check prerequisites before running
- Always provide cleanup instructions
- Document expected outcomes for each step

## Cleanup

### Automated Teardown

The easiest way to remove all resources:

```bash
# Make teardown script executable
chmod +x scripts/teardown.sh

# Run automated cleanup
./scripts/teardown.sh
```

The teardown script will:
1. Empty all S3 buckets (including object versions)
2. Destroy the CDK stack
3. Verify all resources are removed
4. Report any remaining resources

### Manual Cleanup

If the automated script fails, manually clean up:

```bash
# 1. Empty S3 buckets
aws s3 rm s3://<inbox-bucket-name> --recursive
aws s3 rm s3://<destination-bucket-name> --recursive
aws s3 rm s3://<website-bucket-name> --recursive

# 2. Delete object versions (if versioning enabled)
aws s3api list-object-versions --bucket <bucket-name> \
  --query 'Versions[].{Key:Key,VersionId:VersionId}' \
  --output json | jq -r '.[] | "--key \(.Key) --version-id \(.VersionId)"' | \
  xargs -I {} aws s3api delete-object --bucket <bucket-name> {}

# 3. Destroy CDK stack
cdk destroy --force

# 4. Verify cleanup
aws cloudformation describe-stacks --stack-name EmailClassificationStack
# Should return: "Stack with id EmailClassificationStack does not exist"
```

### Cost Considerations

This demo incurs minimal costs:
- **S3**: ~$0.023/GB/month (negligible for demo)
- **Lambda**: Free tier covers 1M requests/month
- **API Gateway**: Free tier covers 1M requests/month
- **CloudFront**: Free tier covers 1TB/month
- **Bedrock**: Pay per request (~$0.0008 per 1K input tokens for Nova Lite)
- **BDA**: Pay per document processed

**Estimated cost for 100 test emails**: < $1.00

**To minimize costs**:
- Run teardown script after demos
- Use lifecycle policies (already configured)
- Monitor usage in AWS Cost Explorer

## Useful CDK Commands

```bash
# List all stacks
cdk ls

# Synthesize CloudFormation template
cdk synth

# Show differences between deployed and local
cdk diff

# Deploy stack
cdk deploy

# Deploy without confirmation prompts
cdk deploy --require-approval never

# Destroy stack
cdk destroy

# View stack outputs
cdk deploy --outputs-file outputs.json
```

## Additional Resources

### AWS Documentation
- [AWS CDK Developer Guide](https://docs.aws.amazon.com/cdk/latest/guide/)
- [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- [Bedrock Data Automation](https://docs.aws.amazon.com/bedrock/latest/userguide/data-automation.html)
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/)
- [Step Functions Developer Guide](https://docs.aws.amazon.com/step-functions/latest/dg/)

### Related Projects
- [AWS CDK Examples](https://github.com/aws-samples/aws-cdk-examples)
- [Serverless Patterns Collection](https://serverlessland.com/patterns)
- [Amazon Bedrock Samples](https://github.com/aws-samples/amazon-bedrock-samples)

## Support and Contributions

This is an educational demo project. For questions or issues:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review CloudWatch logs for error details
3. Consult AWS documentation for service-specific issues
4. Open an issue in the repository (if applicable)

## License

This project is provided as-is for educational purposes.
