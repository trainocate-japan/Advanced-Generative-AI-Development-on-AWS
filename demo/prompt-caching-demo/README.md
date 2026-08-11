# Amazon Bedrock Prompt Caching Demo

An educational demonstration system that teaches Amazon Bedrock prompt caching best practices through interactive, real-time demonstrations. This project provides instructors with an automated deployment solution featuring a web-based interface for students to learn about prompt caching optimization techniques.

## Overview

This demonstration showcases how Amazon Bedrock's prompt caching feature can reduce costs by up to 90% and improve latency by caching frequently used prompt prefixes. Students can interact with a web interface to observe cache behavior, token reduction, and performance improvements in real-time.

### Key Features

- **Interactive Web Interface**: Browser-based UI for submitting questions and observing cache behavior
- **Real-Time Demonstrations**: See baseline vs cached performance side-by-side
- **Educational Content**: Built-in explanations of prompt caching concepts and best practices
- **Architecture Visualization**: Interactive diagram showing system components and data flow
- **Automated Deployment**: One-command setup and teardown scripts
- **Production-Quality Code**: Uses real AWS Bedrock API with proper security practices
- **Cost-Effective**: Serverless architecture with automatic cleanup

## Architecture

The system uses AWS serverless services:

- **Amazon S3**: Stores documents and hosts the static website
- **AWS Lambda**: Processes queries and invokes the prompt caching script
- **Amazon API Gateway**: Provides REST API endpoints for the web interface
- **Amazon CloudFront**: Delivers the website globally with HTTPS
- **Amazon Bedrock**: Provides AI inference with prompt caching capabilities
- **AWS CDK**: Infrastructure as code for automated deployment

## Prerequisites

Before deploying this demonstration, ensure you have the following installed and configured:

### Required Software

1. **AWS CLI** (version 2.x or higher)
   - Installation: https://aws.amazon.com/cli/
   - Verify: `aws --version`

2. **AWS CDK** (version 2.x or higher)
   - Installation: `npm install -g aws-cdk`
   - Verify: `cdk --version`

3. **Python** (version 3.12 or higher)
   - Installation: https://www.python.org/downloads/
   - Verify: `python3 --version`

4. **Node.js** (version 18 or higher)
   - Installation: https://nodejs.org/
   - Verify: `node --version`

### AWS Configuration

1. **AWS Account**: Active AWS account with appropriate permissions
2. **AWS Credentials**: Configured via `aws configure`
3. **AWS Region**: Region where Amazon Bedrock is available (e.g., us-east-1)
4. **Bedrock Access**: Ensure you have access to Amazon Bedrock models
   - Navigate to Amazon Bedrock console
   - Request model access for supported models (e.g., Amazon Nova Lite)

### Permissions Required

Your AWS credentials need permissions for:
- S3 (create buckets, upload objects)
- Lambda (create functions, update code)
- API Gateway (create APIs, deploy stages)
- CloudFront (create distributions)
- IAM (create roles and policies)
- CloudFormation (create and manage stacks)
- Bedrock (invoke models)

## Setup Instructions

### Step 1: Clone or Navigate to the Project

```bash
cd prompt-caching-demo
```

### Step 2: Run the Setup Script

The setup script automates the entire deployment process:

```bash
./scripts/setup.sh
```

The script will:
1. ✅ Validate all prerequisites
2. ✅ Check AWS credentials and display account information
3. ✅ Bootstrap CDK environment (if needed)
4. ✅ Install Python dependencies
5. ✅ Deploy AWS infrastructure via CDK
6. ✅ Upload the AWS CAF for AI document to S3
7. ✅ Generate and deploy the web interface
8. ✅ Verify all components are working
9. ✅ Display the CloudFront URL for accessing the demo

### Step 3: Access the Demo

Once deployment completes, the script will display:

```
✅ Deployment successful!

CloudFront URL: https://d1234567890abc.cloudfront.net
API Gateway URL: https://abcdef1234.execute-api.us-east-1.amazonaws.com/prod

Next steps:
1. Open the CloudFront URL in your browser
2. Submit a question to see prompt caching in action
3. Observe the token reduction and latency improvements
```

Open the CloudFront URL in your web browser to access the demonstration.

### Optional: Skip CDK Bootstrap

If you've already bootstrapped CDK in your account and region:

```bash
./scripts/setup.sh --skip-bootstrap
```

## Usage Instructions

### Using the Web Interface

1. **Access the Demo**: Open the CloudFront URL provided after deployment

2. **Read Educational Content**: Review the learning objectives and prompt caching concepts

3. **Submit a Question**: 
   - Enter a question in the text input (e.g., "What are the key principles of AWS CAF for AI?")
   - **(Optional) Upload Your Own Document**: Click "Choose Document" to upload a custom document (.txt or .md files, max 100KB) to demonstrate caching with your own content
     - Sample documents are provided in the `sample-documents/` folder for testing:
       - `prompt-caching-guide.txt`: Comprehensive guide to Amazon Bedrock prompt caching (~10,000 tokens)
       - `sample-tech-doc.txt`: Cloud computing best practices (~3,000 tokens)
       - `sample-product-guide.txt`: Product development lifecycle (~4,000 tokens)
   - Select a model (defaults to Amazon Nova Lite for cost-effectiveness)
   - Click "Submit Query"

4. **Observe Results**:
   - **Baseline Metrics**: First request without caching
   - **Cache Write Metrics**: Tokens written to cache
   - **Cache Hit Metrics**: Second request using cached content
   - **Token Reduction**: Percentage of tokens saved through caching
   - **Latency Improvement**: Response time improvement

5. **Explore the Architecture**: Hover over components in the architecture diagram to see tooltips

6. **View History**: See all previous queries and their cache performance

### Understanding the Results

The demo performs three requests to demonstrate caching:

1. **Baseline Request**: Processes the full document without caching to establish a baseline
2. **Cache Write Request**: Includes a cache checkpoint to write the document to cache
3. **Cache Hit Request**: Reuses the cached document, showing reduced token counts

**Key Metrics**:
- **Input Tokens**: Tokens processed from the prompt
- **Output Tokens**: Tokens generated in the response
- **Cache Write Tokens**: Tokens written to cache (premium pricing, varies by model)
- **Cache Read Tokens**: Tokens read from cache (reduced pricing, varies by model)
- **Token Reduction %**: Percentage of tokens saved through caching
- **Latency Improvement %**: Response time improvement

### Supported Models

The following Amazon Bedrock models support prompt caching:

- **Amazon Nova Lite** (amazon.nova-lite-v1:0) - Cost-effective, 1024 token minimum
- **Amazon Nova Pro** (amazon.nova-pro-v1:0) - Balanced performance, 1024 token minimum
- **Claude 3.5 Sonnet** (anthropic.claude-3-5-sonnet-20241022-v2:0) - High performance, 1024 token minimum
- **Claude 3 Haiku** (anthropic.claude-3-haiku-20240307-v1:0) - Fast responses, 1024 token minimum

**Note**: Documents must contain at least 1024 tokens to be eligible for caching.

## Teardown Instructions

When you're finished with the demonstration, remove all AWS resources to avoid ongoing charges:

### Step 1: Run the Teardown Script

```bash
./scripts/teardown.sh
```

The script will:
1. Display all resources to be deleted
2. Ask for confirmation
3. Empty all S3 buckets
4. Destroy the CDK stack
5. Verify all resources are removed

### Step 2: Confirm Deletion

When prompted, type `yes` to confirm:

```
The following resources will be deleted:
- S3 Buckets: 2
- Lambda Functions: 1
- API Gateway: 1
- CloudFront Distribution: 1

Are you sure you want to proceed? (yes/no): yes
```

### Optional: Force Teardown

To skip the confirmation prompt:

```bash
./scripts/teardown.sh --force
```

### Optional: Keep Logs

To preserve CloudWatch logs:

```bash
./scripts/teardown.sh --keep-logs
```

### Verification

After teardown completes, verify in the AWS Console that:
- CloudFormation stack is deleted
- S3 buckets are removed
- Lambda functions are deleted
- API Gateway is removed

**Note**: CloudFront distribution deletion may take 15-30 minutes to complete.

## Cost Estimates

Running this demonstration incurs minimal AWS costs:

### Per Demo Session (10-20 queries)
- **Amazon Bedrock**: $0.05 - $0.20 (depends on model and token counts)
- **Lambda**: $0.01 - $0.02
- **API Gateway**: $0.01
- **S3**: < $0.01
- **CloudFront**: < $0.01

**Estimated Total**: $0.10 - $0.50 per session

### Monthly Costs (if left running)
- **S3 Storage**: ~$0.02 per month
- **CloudFront**: ~$0.01 per month (minimal traffic)
- **Lambda**: Pay per invocation only
- **API Gateway**: Pay per request only

**Important**: Run the teardown script after each session to minimize costs.

## Troubleshooting

### Prerequisites Not Found

**Error**: "AWS CLI not found"

**Solution**: Install AWS CLI from https://aws.amazon.com/cli/

### AWS Credentials Not Configured

**Error**: "Unable to locate credentials"

**Solution**: Run `aws configure` and enter your AWS access key, secret key, and region

### CDK Bootstrap Required

**Error**: "This stack uses assets, so the toolkit stack must be deployed"

**Solution**: The setup script handles this automatically. If you see this error, ensure you're not using `--skip-bootstrap` on first deployment.

### Deployment Fails

**Error**: Various CloudFormation errors

**Solution**: 
1. Check the error message for specific resource failures
2. Verify you have sufficient permissions
3. Check service quotas in your AWS account
4. Run `./scripts/teardown.sh` to clean up partial deployment
5. Try deploying again

### Website Not Loading

**Error**: CloudFront URL returns 403 or 404

**Solution**:
1. Wait 2-3 minutes for CloudFront distribution to fully deploy
2. Verify the distribution status is "Deployed" in AWS Console
3. Check that website files were uploaded to S3
4. Try a hard refresh (Ctrl+F5 or Cmd+Shift+R)

### API Connection Errors

**Error**: "Failed to connect to API"

**Solution**:
1. Check browser console for CORS errors
2. Verify API Gateway URL in config.js matches deployed API
3. Check that Lambda function is accessible
4. Verify IAM permissions for Lambda execution role

### Cache Not Working

**Error**: No token reduction observed

**Solution**:
1. Verify document contains at least 1024 tokens
2. Check that cache checkpoint is included in request
3. Ensure requests use the same document context
4. Note: Cache has 5-minute TTL, may expire between requests

## Additional Resources

- **Amazon Bedrock Documentation**: https://docs.aws.amazon.com/bedrock/
- **Prompt Caching Guide**: https://docs.aws.amazon.com/bedrock/latest/userguide/prompt-caching.html
- **AWS CDK Documentation**: https://docs.aws.amazon.com/cdk/
- **Instructor Guide**: See INSTRUCTOR_GUIDE.md for teaching tips and educational objectives

## Security Considerations

This demonstration implements several security best practices:

- **Input Validation**: All user inputs are validated and sanitized
- **Error Sanitization**: Error messages don't expose sensitive information
- **Least Privilege IAM**: Roles have minimal required permissions
- **Encryption**: All S3 buckets use encryption at rest
- **HTTPS Only**: All traffic uses TLS encryption
- **Rate Limiting**: API requests are throttled to prevent abuse
- **No Public S3 Access**: Buckets block all public access

**Note**: This is a demonstration environment. For production use, implement additional security measures such as authentication, authorization, and network isolation.

## License

This demonstration is provided as educational material. Refer to your organization's licensing terms for usage guidelines.

## Support

For issues or questions:
1. Check the Troubleshooting section above
2. Review CloudWatch logs for detailed error messages
3. Consult the INSTRUCTOR_GUIDE.md for common issues
4. Check AWS service health dashboard for outages

---

**Built with AWS Services** | **Powered by Amazon Bedrock**
