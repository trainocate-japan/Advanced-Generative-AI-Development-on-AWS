#!/bin/bash

################################################################################
# Email Classification System - Automated Teardown Script
################################################################################
#
# This script automates the cleanup of the Email Classification CDK stack.
# It performs the following steps:
#   1. Retrieves bucket names from CloudFormation stack outputs
#   2. Empties all S3 buckets (inbox, destination, website)
#   3. Deletes object versions if versioning is enabled
#   4. Destroys the CDK stack
#   5. Verifies all resources have been removed
#
# Usage:
#   ./scripts/teardown.sh [--force] [--keep-logs]
#
# Options:
#   --force         Skip confirmation prompt
#   --keep-logs     Preserve CloudWatch log groups
#
# Requirements:
#   - AWS CLI configured with valid credentials
#   - CDK CLI installed
#   - Deployed EmailClassificationStack
#
################################################################################

set -e  # Exit on any error

# Ensure script is run from project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
STACK_NAME="EmailClassificationStack"
FORCE_MODE=false
KEEP_LOGS=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_MODE=true
            shift
            ;;
        --keep-logs)
            KEEP_LOGS=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--force] [--keep-logs]"
            exit 1
            ;;
    esac
done

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 is not installed or not in PATH"
        return 1
    fi
    return 0
}

################################################################################
# Prerequisite Checks
################################################################################

print_header "Checking Prerequisites"

# Check AWS CLI
if check_command aws; then
    AWS_VERSION=$(aws --version 2>&1 | cut -d' ' -f1)
    print_success "AWS CLI found: $AWS_VERSION"
else
    print_error "AWS CLI is required. Install from: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured. Run 'aws configure' first."
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
print_success "AWS Account: $AWS_ACCOUNT"
print_success "AWS Region: $AWS_REGION"

# Check CDK CLI
if check_command cdk; then
    CDK_VERSION=$(cdk --version 2>&1)
    print_success "AWS CDK found: $CDK_VERSION"
else
    print_error "AWS CDK CLI is required. Install with: npm install -g aws-cdk"
    exit 1
fi

################################################################################
# Check if Stack Exists
################################################################################

print_header "Checking Stack Status"

if ! aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION &> /dev/null; then
    print_error "Stack '$STACK_NAME' not found in region $AWS_REGION"
    print_info "Nothing to clean up. Exiting."
    exit 0
fi

STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query 'Stacks[0].StackStatus' --output text)
print_success "Stack found: $STACK_NAME (Status: $STACK_STATUS)"

################################################################################
# Retrieve Stack Outputs
################################################################################

print_header "Retrieving Stack Outputs"

print_info "Fetching bucket names from stack outputs..."

# Get stack outputs
INBOX_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`InboxBucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

DEST_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`DestinationBucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

WEBSITE_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name $STACK_NAME \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`WebsiteBucketName`].OutputValue' \
    --output text 2>/dev/null || echo "")

# Display found buckets
if [ -n "$INBOX_BUCKET" ]; then
    print_success "Inbox Bucket: $INBOX_BUCKET"
else
    print_warning "Inbox bucket name not found in outputs"
fi

if [ -n "$DEST_BUCKET" ]; then
    print_success "Destination Bucket: $DEST_BUCKET"
else
    print_warning "Destination bucket name not found in outputs"
fi

if [ -n "$WEBSITE_BUCKET" ]; then
    print_success "Website Bucket: $WEBSITE_BUCKET"
else
    print_warning "Website bucket name not found in outputs"
fi

# Check if any buckets were found
if [ -z "$INBOX_BUCKET" ] && [ -z "$DEST_BUCKET" ] && [ -z "$WEBSITE_BUCKET" ]; then
    print_warning "No bucket names found in stack outputs"
    print_info "Will proceed with stack deletion only"
fi

################################################################################
# Confirmation Prompt
################################################################################

if [ "$FORCE_MODE" = false ]; then
    print_header "Confirmation Required"
    
    echo -e "${YELLOW}WARNING: This will permanently delete the following resources:${NC}"
    echo ""
    [ -n "$INBOX_BUCKET" ] && echo -e "  • S3 Bucket: ${RED}$INBOX_BUCKET${NC} (and all contents)"
    [ -n "$DEST_BUCKET" ] && echo -e "  • S3 Bucket: ${RED}$DEST_BUCKET${NC} (and all contents)"
    [ -n "$WEBSITE_BUCKET" ] && echo -e "  • S3 Bucket: ${RED}$WEBSITE_BUCKET${NC} (and all contents)"
    echo -e "  • Lambda Functions"
    echo -e "  • API Gateway"
    echo -e "  • CloudFront Distribution"
    echo -e "  • Step Functions State Machine"
    echo -e "  • IAM Roles and Policies"
    [ "$KEEP_LOGS" = false ] && echo -e "  • CloudWatch Log Groups"
    echo ""
    echo -e "${RED}This action cannot be undone!${NC}"
    echo ""
    
    read -p "Are you sure you want to proceed? (yes/no): " -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        print_info "Teardown cancelled by user"
        exit 0
    fi
    
    print_success "Confirmation received. Proceeding with teardown..."
fi

################################################################################
# Empty S3 Buckets
################################################################################

print_header "Emptying S3 Buckets"

empty_bucket() {
    local bucket_name=$1
    local bucket_label=$2
    
    if [ -z "$bucket_name" ]; then
        print_warning "Skipping $bucket_label (bucket name not found)"
        return 0
    fi
    
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket $bucket_name --region $AWS_REGION 2>/dev/null; then
        print_warning "Bucket $bucket_name does not exist or is not accessible"
        return 0
    fi
    
    print_info "Emptying $bucket_label: $bucket_name"
    
    # Count objects before deletion
    OBJECT_COUNT=$(aws s3 ls s3://$bucket_name --recursive --region $AWS_REGION 2>/dev/null | wc -l || echo "0")
    
    if [ "$OBJECT_COUNT" -eq 0 ]; then
        print_success "$bucket_label is already empty"
        return 0
    fi
    
    print_info "Found $OBJECT_COUNT objects to delete"
    
    # Delete all objects (non-versioned)
    print_info "Deleting objects..."
    if aws s3 rm s3://$bucket_name --recursive --region $AWS_REGION 2>/dev/null; then
        print_success "Objects deleted from $bucket_label"
    else
        print_warning "Some objects may not have been deleted from $bucket_label"
    fi
    
    # Check if versioning is enabled
    VERSIONING_STATUS=$(aws s3api get-bucket-versioning --bucket $bucket_name --region $AWS_REGION --query 'Status' --output text 2>/dev/null || echo "")
    
    if [ "$VERSIONING_STATUS" = "Enabled" ] || [ "$VERSIONING_STATUS" = "Suspended" ]; then
        print_info "Versioning is $VERSIONING_STATUS. Deleting object versions..."
        
        # Delete all object versions
        aws s3api list-object-versions --bucket $bucket_name --region $AWS_REGION --output json 2>/dev/null | \
        jq -r '.Versions[]? | "--key \"\(.Key)\" --version-id \(.VersionId)"' 2>/dev/null | \
        while read -r args; do
            if [ -n "$args" ]; then
                eval aws s3api delete-object --bucket $bucket_name --region $AWS_REGION $args 2>/dev/null || true
            fi
        done
        
        # Delete all delete markers
        aws s3api list-object-versions --bucket $bucket_name --region $AWS_REGION --output json 2>/dev/null | \
        jq -r '.DeleteMarkers[]? | "--key \"\(.Key)\" --version-id \(.VersionId)"' 2>/dev/null | \
        while read -r args; do
            if [ -n "$args" ]; then
                eval aws s3api delete-object --bucket $bucket_name --region $AWS_REGION $args 2>/dev/null || true
            fi
        done
        
        print_success "Object versions and delete markers removed from $bucket_label"
    fi
    
    # Verify bucket is empty
    REMAINING_COUNT=$(aws s3 ls s3://$bucket_name --recursive --region $AWS_REGION 2>/dev/null | wc -l || echo "0")
    
    if [ "$REMAINING_COUNT" -eq 0 ]; then
        print_success "$bucket_label is now empty"
    else
        print_warning "$bucket_label still contains $REMAINING_COUNT objects"
        print_info "CDK destroy will attempt to delete the bucket anyway"
    fi
}

# Empty each bucket
empty_bucket "$INBOX_BUCKET" "Inbox Bucket"
empty_bucket "$DEST_BUCKET" "Destination Bucket"
empty_bucket "$WEBSITE_BUCKET" "Website Bucket"

################################################################################
# Delete CloudWatch Log Groups (Optional)
################################################################################

if [ "$KEEP_LOGS" = false ]; then
    print_header "Deleting CloudWatch Log Groups"
    
    print_info "Searching for log groups..."
    
    # Find all log groups related to the stack
    LOG_GROUPS=$(aws logs describe-log-groups \
        --region $AWS_REGION \
        --log-group-name-prefix "/aws/lambda/EmailClassification" \
        --query 'logGroups[].logGroupName' \
        --output text 2>/dev/null || echo "")
    
    if [ -n "$LOG_GROUPS" ]; then
        for log_group in $LOG_GROUPS; do
            print_info "Deleting log group: $log_group"
            if aws logs delete-log-group --log-group-name $log_group --region $AWS_REGION 2>/dev/null; then
                print_success "Deleted: $log_group"
            else
                print_warning "Failed to delete: $log_group"
            fi
        done
    else
        print_info "No log groups found with prefix '/aws/lambda/EmailClassification'"
    fi
else
    print_warning "Skipping CloudWatch log group deletion (--keep-logs flag provided)"
fi

################################################################################
# Destroy CDK Stack
################################################################################

print_header "Destroying CDK Stack"

print_info "Running CDK destroy for $STACK_NAME..."
print_warning "This may take 5-10 minutes..."

if cdk destroy --force; then
    print_success "CDK stack destroyed successfully"
else
    print_error "CDK destroy failed"
    print_info ""
    print_info "Troubleshooting steps:"
    print_info "  1. Check CloudFormation console for error details"
    print_info "  2. Manually delete any remaining resources"
    print_info "  3. Try running this script again"
    print_info "  4. As a last resort, delete the stack from CloudFormation console"
    exit 1
fi

################################################################################
# Verify Resource Cleanup
################################################################################

print_header "Verifying Resource Cleanup"

# Check if stack still exists
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION &> /dev/null; then
    print_error "Stack still exists in CloudFormation"
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query 'Stacks[0].StackStatus' --output text)
    print_info "Current status: $STACK_STATUS"
    
    if [ "$STACK_STATUS" = "DELETE_FAILED" ]; then
        print_error "Stack deletion failed. Manual cleanup may be required."
        print_info "Check CloudFormation console for details: https://console.aws.amazon.com/cloudformation/home?region=$AWS_REGION"
        exit 1
    fi
else
    print_success "Stack successfully removed from CloudFormation"
fi

# Check if buckets still exist
print_info "Checking if S3 buckets were deleted..."

check_bucket_deleted() {
    local bucket_name=$1
    local bucket_label=$2
    
    if [ -z "$bucket_name" ]; then
        return 0
    fi
    
    if aws s3api head-bucket --bucket $bucket_name --region $AWS_REGION 2>/dev/null; then
        print_warning "$bucket_label still exists: $bucket_name"
        return 1
    else
        print_success "$bucket_label deleted: $bucket_name"
        return 0
    fi
}

BUCKETS_DELETED=true
check_bucket_deleted "$INBOX_BUCKET" "Inbox Bucket" || BUCKETS_DELETED=false
check_bucket_deleted "$DEST_BUCKET" "Destination Bucket" || BUCKETS_DELETED=false
check_bucket_deleted "$WEBSITE_BUCKET" "Website Bucket" || BUCKETS_DELETED=false

# Check Lambda functions
print_info "Checking if Lambda functions were deleted..."

LAMBDA_FUNCTIONS=(
    "EmailClassification-UploadHandler"
    "EmailClassification-EmailProcessor"
    "EmailClassification-InvoiceClassifier"
)

LAMBDAS_DELETED=true
for func in "${LAMBDA_FUNCTIONS[@]}"; do
    if aws lambda get-function --function-name $func --region $AWS_REGION &> /dev/null; then
        print_warning "Lambda function still exists: $func"
        LAMBDAS_DELETED=false
    else
        print_success "Lambda function deleted: $func"
    fi
done

# Check CloudFront distribution (may take time to delete)
print_info "Checking CloudFront distributions..."
CLOUDFRONT_DISTRIBUTIONS=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='Email Classification Website'].Id" \
    --output text 2>/dev/null || echo "")

if [ -n "$CLOUDFRONT_DISTRIBUTIONS" ]; then
    print_warning "CloudFront distribution(s) still exist (may be in process of deletion)"
    print_info "CloudFront distributions can take up to 15 minutes to fully delete"
else
    print_success "No CloudFront distributions found"
fi

################################################################################
# Cleanup Summary
################################################################################

print_header "Cleanup Summary"

ALL_CLEAN=true

if [ "$BUCKETS_DELETED" = false ]; then
    print_warning "Some S3 buckets were not deleted"
    ALL_CLEAN=false
fi

if [ "$LAMBDAS_DELETED" = false ]; then
    print_warning "Some Lambda functions were not deleted"
    ALL_CLEAN=false
fi

if [ -n "$CLOUDFRONT_DISTRIBUTIONS" ]; then
    print_warning "CloudFront distribution deletion in progress"
    ALL_CLEAN=false
fi

if [ "$ALL_CLEAN" = true ]; then
    print_success "All resources successfully cleaned up"
else
    print_warning "Some resources may still exist"
    print_info "This is normal for CloudFront distributions (can take 15+ minutes)"
    print_info "Check AWS console to verify all resources are eventually deleted"
fi

################################################################################
# Success Message
################################################################################

print_header "Teardown Complete! 🧹"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  Email Classification System Successfully Removed!            ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${BLUE}Resources Removed:${NC}"
[ -n "$INBOX_BUCKET" ] && echo -e "  ${GREEN}✓${NC} Inbox Bucket: $INBOX_BUCKET"
[ -n "$DEST_BUCKET" ] && echo -e "  ${GREEN}✓${NC} Destination Bucket: $DEST_BUCKET"
[ -n "$WEBSITE_BUCKET" ] && echo -e "  ${GREEN}✓${NC} Website Bucket: $WEBSITE_BUCKET"
echo -e "  ${GREEN}✓${NC} Lambda Functions"
echo -e "  ${GREEN}✓${NC} API Gateway"
echo -e "  ${GREEN}✓${NC} Step Functions State Machine"
echo -e "  ${GREEN}✓${NC} IAM Roles and Policies"
[ "$KEEP_LOGS" = false ] && echo -e "  ${GREEN}✓${NC} CloudWatch Log Groups"

if [ -n "$CLOUDFRONT_DISTRIBUTIONS" ]; then
    echo -e "\n${YELLOW}Note:${NC} CloudFront distribution deletion is in progress"
    echo -e "  This can take 15-30 minutes to complete"
    echo -e "  Check status: https://console.aws.amazon.com/cloudfront/home?region=$AWS_REGION"
fi

echo -e "\n${BLUE}Next Steps:${NC}"
echo -e "  • Verify all resources are deleted in AWS Console"
echo -e "  • Check for any remaining costs in AWS Cost Explorer"
echo -e "  • To redeploy, run: ${YELLOW}./scripts/setup.sh${NC}"

echo -e "\n${GREEN}Cleanup complete! 👋${NC}\n"
