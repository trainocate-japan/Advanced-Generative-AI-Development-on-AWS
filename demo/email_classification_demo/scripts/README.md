# Deployment Scripts

This directory contains automated scripts for deploying and managing the Email Classification System.

## Setup Script

### Purpose
The `setup.sh` script automates the complete deployment process, including:
- Prerequisite validation
- CDK environment bootstrapping
- Stack deployment
- Configuration upload
- Deployment verification

### Usage

```bash
# Standard deployment (includes bootstrap)
./scripts/setup.sh

# Skip bootstrap if already done
./scripts/setup.sh --skip-bootstrap
```

### Prerequisites

Before running the setup script, ensure you have:

1. **AWS CLI** configured with valid credentials
   ```bash
   aws configure
   ```

2. **Node.js 18+** and **AWS CDK CLI**
   ```bash
   npm install -g aws-cdk
   ```

3. **Python 3.11+** with pip
   ```bash
   python3 --version
   ```

4. **Department configuration** file at `config/department_config.json`

### What the Script Does

1. **Validates Prerequisites**
   - Checks for AWS CLI, Node.js, CDK CLI, Python
   - Verifies AWS credentials are configured
   - Confirms department configuration file exists

2. **Installs Dependencies**
   - Installs Python packages from `requirements.txt`

3. **Bootstraps CDK** (unless `--skip-bootstrap` is used)
   - Prepares AWS environment for CDK deployments
   - Creates necessary S3 buckets and IAM roles
   - Only needs to be done once per account/region

4. **Synthesizes CDK Stack**
   - Generates CloudFormation template
   - Validates CDK code

5. **Deploys Stack**
   - Creates all AWS resources (S3, Lambda, API Gateway, CloudFront, etc.)
   - Typically takes 5-10 minutes
   - Saves outputs to `outputs.json`

6. **Uploads Configuration**
   - Uploads `department_config.json` to S3 inbox bucket

7. **Verifies Deployment**
   - Checks stack outputs
   - Verifies Lambda functions exist
   - Tests S3 bucket accessibility

8. **Displays Success Message**
   - Shows CloudFront URL for accessing the application
   - Provides links to monitoring resources
   - Lists next steps

### Output

The script provides color-coded output:
- 🟢 **Green**: Success messages
- 🔵 **Blue**: Informational messages
- 🟡 **Yellow**: Warnings
- 🔴 **Red**: Errors

### Error Handling

If deployment fails, the script will:
1. Display the error message
2. Provide rollback instructions
3. Exit with a non-zero status code

**Rollback Steps:**
```bash
# Clean up partial deployment
cdk destroy

# Fix the issue in your code
# Then run setup again
./scripts/setup.sh
```

### Outputs File

The script creates `outputs.json` containing:
- Inbox bucket name
- Destination bucket name
- Website bucket name
- API Gateway URL
- CloudFront URL

This file is used by other scripts and can be referenced for manual operations.

## Teardown Script

See `teardown.sh` for cleanup instructions (Task 18).

## Tips

- **First-time deployment**: Use the standard command without flags
- **Subsequent deployments**: Use `--skip-bootstrap` to save time
- **Check logs**: If deployment fails, check CloudFormation console for details
- **Monitor progress**: Watch the CloudFormation console during deployment
- **Verify outputs**: Always check that `outputs.json` was created successfully

## Troubleshooting

### "AWS credentials not configured"
```bash
aws configure
# Enter your AWS Access Key ID, Secret Access Key, and default region
```

### "CDK bootstrap failed"
- Ensure you have sufficient IAM permissions
- Check that your AWS account is valid
- Verify the region is correct

### "CDK deployment failed"
- Check CloudFormation console for specific error
- Review CDK code for syntax errors
- Ensure all Lambda function code is valid
- Verify IAM permissions are correct

### "Failed to upload department configuration"
- Check S3 bucket permissions
- Verify the bucket was created successfully
- Try manual upload:
  ```bash
  aws s3 cp config/department_config.json s3://YOUR-INBOX-BUCKET/
  ```

## Support

For issues or questions:
1. Check CloudWatch logs for Lambda function errors
2. Review CloudFormation events in AWS Console
3. Verify all prerequisites are met
4. Check the main README.md for architecture details
