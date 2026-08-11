# GenAI Model Selection Demo

Educational demonstration of provider-agnostic GenAI architecture for AWS Technical Training.

## Overview

This demo showcases intelligent model selection and routing across multiple GenAI providers (Anthropic Claude, Meta Llama, AWS Nova) through a unified AWS Bedrock Converse API interface.

## Features

- **Provider-Agnostic Architecture**: Single interface works identically across all providers
- **Intelligent Routing**: Automatic model selection based on health, performance, and query characteristics
- **Fault Tolerance**: Circuit breakers and automatic failover when providers fail
- **Real-time Monitoring**: Live provider status and performance metrics
- **Instructor Controls**: Simulate provider failures for educational demonstrations
- **Interactive Code Viewers**: Click architecture diagram components to see actual Lambda code

## Quick Start

### Prerequisites

- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed ([Installation Guide](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html))
- Access to AWS Bedrock models in your account

### Deployment

```bash
# Deploy the entire stack
./deploy-sam.sh
```

That's it! The script will:
1. Build the Lambda function with dependencies
2. Deploy infrastructure using SAM
3. Upload website files to S3
4. Configure CloudFront distribution
5. Display your website URL

### Manual Deployment

```bash
# Build
sam build

# Deploy
sam deploy --resolve-s3 --capabilities CAPABILITY_IAM

# Get outputs
sam list stack-outputs --stack-name genai-model-selection-demo
```

## Architecture

- **Frontend**: Static web app (HTML/CSS/JavaScript) served via CloudFront
- **API**: API Gateway with Lambda integration
- **Compute**: Python Lambda function with intelligent routing logic
- **AI Providers**: AWS Bedrock Converse API (Anthropic, Meta, Nova)
- **Monitoring**: CloudWatch logs and metrics

## Project Structure

```
├── lambda/                 # Lambda function code
│   ├── lambda_handler.py  # Main handler
│   ├── bedrock_adapter.py # Unified Bedrock interface
│   ├── router.py          # Intelligent routing
│   ├── health_monitor.py  # Health checks
│   └── requirements.txt   # Python dependencies
├── web/                   # Frontend files
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── template.yaml          # SAM template
├── samconfig.toml         # SAM configuration
└── deploy-sam.sh          # Deployment script
```

## Usage

1. Open the website URL provided after deployment
2. Submit queries through the interface
3. Watch automatic provider selection and routing
4. Use Instructor Controls to simulate failures
5. Click architecture diagram components to view code

## Educational Value

This demo teaches:
- Provider-agnostic API design patterns
- Intelligent routing algorithms
- Circuit breaker and failover patterns
- Health monitoring and observability
- Serverless architecture on AWS

## Cleanup

### Automated Cleanup (Recommended)

```bash
# Run the cleanup script (handles everything automatically)
./cleanup-deployment.sh
```

The cleanup script will:
1. Empty the S3 bucket (required before deletion)
2. Delete the CloudFormation stack
3. Remove all AWS resources (CloudFront, Lambda, API Gateway, IAM roles)
4. Clean up local SAM artifacts
5. Wait for completion and confirm success

See [CLEANUP-GUIDE.md](CLEANUP-GUIDE.md) for detailed documentation.

### Manual Cleanup

```bash
# Empty S3 bucket first
aws s3 rm s3://genai-demo-website-<account-id>/ --recursive

# Delete the stack
aws cloudformation delete-stack --stack-name genai-model-selection-demo

# Wait for deletion
aws cloudformation wait stack-delete-complete --stack-name genai-model-selection-demo
```

## License

Educational demonstration for AWS Technical Training.
