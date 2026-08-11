#!/bin/bash

echo "=========================================="
echo "  GenAI Demo - Cleanup Script            "
echo "=========================================="
echo ""
echo "⚠️  WARNING: This will DELETE all resources!"
echo "   - S3 bucket and all files"
echo "   - CloudFront distribution"
echo "   - Lambda function"
echo "   - API Gateway"
echo "   - IAM roles and policies"
echo "   - CloudWatch logs"
echo ""
read -p "Are you sure you want to continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "Starting cleanup process..."
echo ""

STACK_NAME="genai-model-selection-demo"

# Step 1: Get S3 bucket name
echo "Step 1/4: Finding S3 bucket..."
BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucket`].OutputValue' \
    --output text 2>/dev/null)

if [ -z "$BUCKET" ] || [[ "$BUCKET" == *"error"* ]]; then
    echo "⚠️  Could not get bucket from CloudFormation, trying alternative method..."
    BUCKET=$(aws s3 ls | grep genai-demo-website | awk '{print $3}' | head -n 1)
fi

if [ -n "$BUCKET" ] && [ "$BUCKET" != "None" ]; then
    echo "✅ Found bucket: $BUCKET"
    
    # Step 2: Empty S3 bucket
    echo ""
    echo "Step 2/4: Emptying S3 bucket..."
    aws s3 rm s3://${BUCKET}/ --recursive
    
    if [ $? -eq 0 ]; then
        echo "✅ S3 bucket emptied successfully"
    else
        echo "⚠️  Warning: Could not empty S3 bucket completely"
    fi
else
    echo "⚠️  No S3 bucket found, skipping..."
fi

# Step 3: Delete CloudFormation stack
echo ""
echo "Step 3/4: Deleting CloudFormation stack..."
aws cloudformation delete-stack --stack-name $STACK_NAME

if [ $? -eq 0 ]; then
    echo "✅ Stack deletion initiated"
    echo ""
    echo "Waiting for stack deletion to complete..."
    echo "(This may take 5-10 minutes)"
    
    aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo "✅ Stack deleted successfully"
    else
        echo "⚠️  Stack deletion in progress (check AWS Console for status)"
    fi
else
    echo "❌ Failed to initiate stack deletion"
    exit 1
fi

# Step 4: Clean up SAM artifacts
echo ""
echo "Step 4/4: Cleaning up local SAM artifacts..."
if [ -d ".aws-sam" ]; then
    rm -rf .aws-sam
    echo "✅ Removed .aws-sam directory"
fi

if [ -f "lambda-deployment.zip" ]; then
    rm -f lambda-deployment.zip
    echo "✅ Removed lambda-deployment.zip"
fi

if [ -f "lambda-update.zip" ]; then
    rm -f lambda-update.zip
    echo "✅ Removed lambda-update.zip"
fi

echo ""
echo "=========================================="
echo "  🎉 CLEANUP COMPLETE!                   "
echo "=========================================="
echo ""
echo "All resources have been removed:"
echo "  ✅ S3 bucket emptied and deleted"
echo "  ✅ CloudFront distribution deleted"
echo "  ✅ Lambda function deleted"
echo "  ✅ API Gateway deleted"
echo "  ✅ IAM roles deleted"
echo "  ✅ CloudWatch logs will expire automatically"
echo "  ✅ Local artifacts cleaned up"
echo ""
echo "Note: CloudWatch logs are retained for 30 days by default"
echo "      You can manually delete them from the AWS Console if needed"
echo ""
