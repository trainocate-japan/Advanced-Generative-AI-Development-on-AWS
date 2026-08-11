# Cleanup Guide - GenAI Model Selection Demo

## Overview

This guide explains how to safely remove all AWS resources created by the GenAI Model Selection Demo deployment.

## Quick Cleanup

### Using the Automated Script (Recommended)

```bash
./cleanup-deployment.sh
```

The script will prompt for confirmation before proceeding. Type `yes` to continue.

## What Gets Deleted

The cleanup process removes:

### AWS Resources
- ✅ **S3 Bucket** - Website bucket and all files
- ✅ **CloudFront Distribution** - CDN distribution
- ✅ **Lambda Function** - Router function and code
- ✅ **API Gateway** - REST API and endpoints
- ✅ **IAM Roles** - Lambda execution role and policies
- ✅ **CloudWatch Log Groups** - Function logs (retained 30 days by default)

### Local Artifacts
- ✅ `.aws-sam/` directory
- ✅ `lambda-deployment.zip`
- ✅ `lambda-update.zip`

## Cleanup Process Details

### Step 1: Find S3 Bucket
The script automatically identifies the S3 bucket from CloudFormation outputs.

### Step 2: Empty S3 Bucket
**Critical:** S3 buckets must be empty before CloudFormation can delete them.
The script removes all files recursively.

### Step 3: Delete CloudFormation Stack
Initiates stack deletion and waits for completion (5-10 minutes).

### Step 4: Clean Local Artifacts
Removes SAM build artifacts and deployment packages.

## Manual Cleanup (Alternative)

If you prefer manual cleanup or the script fails:

### 1. Empty S3 Bucket

```bash
# Get bucket name
BUCKET=$(aws cloudformation describe-stacks \
    --stack-name genai-model-selection-demo \
    --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucket`].OutputValue' \
    --output text)

# Empty bucket
aws s3 rm s3://${BUCKET}/ --recursive
```

### 2. Delete CloudFormation Stack

```bash
# Delete stack
aws cloudformation delete-stack --stack-name genai-model-selection-demo

# Wait for completion
aws cloudformation wait stack-delete-complete --stack-name genai-model-selection-demo
```

### 3. Verify Deletion

```bash
# Check stack status
aws cloudformation describe-stacks --stack-name genai-model-selection-demo
# Should return: "Stack with id genai-model-selection-demo does not exist"

# Verify S3 bucket is gone
aws s3 ls | grep genai-demo-website
# Should return nothing
```

### 4. Clean Local Files

```bash
rm -rf .aws-sam
rm -f lambda-deployment.zip lambda-update.zip
```

## Troubleshooting

### Issue: "Bucket not empty" Error

**Cause:** CloudFormation cannot delete non-empty S3 buckets.

**Solution:**
```bash
# Force empty the bucket
aws s3 rb s3://YOUR-BUCKET-NAME --force
```

### Issue: Stack Deletion Stuck

**Cause:** CloudFront distributions take time to delete (15-30 minutes).

**Solution:**
- Wait patiently - CloudFront deletion is slow
- Check AWS Console for detailed status
- Stack will eventually complete

### Issue: "Stack does not exist" but Resources Remain

**Cause:** Manual resource deletion or partial cleanup.

**Solution:**
```bash
# Find and delete orphaned resources manually
aws s3 ls | grep genai-demo
aws cloudfront list-distributions
aws lambda list-functions | grep genai
```

## Cost Considerations

### Resources That Incur Costs
- **S3 Storage** - Charged per GB stored
- **CloudFront** - Charged per request and data transfer
- **Lambda** - Charged per invocation and duration
- **API Gateway** - Charged per request

### After Cleanup
All charges stop immediately after resources are deleted.

**Note:** CloudWatch logs are retained for 30 days but incur minimal storage costs.

## Partial Cleanup

If you want to keep some resources:

### Keep Logs Only
```bash
# Delete everything except logs
# (Logs will auto-expire based on retention policy)
./cleanup-deployment.sh
```

### Keep S3 Bucket for Backup
```bash
# Download files first
aws s3 sync s3://YOUR-BUCKET-NAME/ ./backup/

# Then run cleanup
./cleanup-deployment.sh
```

## Re-deployment After Cleanup

After cleanup, you can redeploy anytime:

```bash
./deploy-sam.sh
```

This creates fresh resources with new IDs and URLs.

## Safety Features

The cleanup script includes:

1. **Confirmation Prompt** - Requires explicit "yes" to proceed
2. **Error Handling** - Continues even if some steps fail
3. **Status Messages** - Clear feedback at each step
4. **Graceful Degradation** - Handles missing resources

## CloudWatch Logs Retention

By default, CloudWatch logs are retained for 30 days after deletion.

### To Delete Logs Immediately

```bash
# List log groups
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/genai

# Delete specific log group
aws logs delete-log-group --log-group-name /aws/lambda/genai-model-selection-demo-router
```

## Verification Checklist

After cleanup, verify all resources are gone:

- [ ] S3 bucket deleted
- [ ] CloudFormation stack deleted
- [ ] CloudFront distribution deleted
- [ ] Lambda function deleted
- [ ] API Gateway deleted
- [ ] IAM roles deleted
- [ ] Local artifacts removed

## Support

If you encounter issues during cleanup:

1. Check AWS Console for detailed error messages
2. Review CloudFormation Events tab for stack deletion progress
3. Ensure you have proper IAM permissions
4. Try manual cleanup steps if automated script fails

## Important Notes

- **Irreversible:** Cleanup permanently deletes all data
- **No Backup:** Ensure you've backed up any important data
- **Cost Savings:** Cleanup stops all ongoing charges
- **Quick Re-deploy:** Can redeploy anytime with `./deploy-sam.sh`

---

**Last Updated:** November 2025  
**Script Version:** 1.0
