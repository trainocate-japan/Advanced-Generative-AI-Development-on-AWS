#!/bin/bash

################################################################################
# Prompt Caching Demo - Automated Teardown Script
################################################################################
#
# This script automates the removal of the Prompt Caching Demo CDK stack.
# It performs the following steps:
#   1. Checks if CloudFormation stack exists
#   2. Retrieves bucket names from stack outputs
#   3. Empties all S3 buckets (including versioned objects)
#   4. Prompts for confirmation (unless --force flag is used)
#   5. Destroys the CDK stack
#   6. Verifies all resources have been removed
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
#   - AWS CDK CLI installed
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
STACK_NAME="PromptCachingStack"
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
    print_error "AWS CLI is required but not installed"
    print_info ""
    print_info "Installation instructions:"
    print_info "  macOS:   brew install awscli"
    print_info "  Linux:   https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    print_info "  Windows: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    print_info ""
    print_info "Official download: https://aws.amazon.com/cli/"
    exit 1
fi

# Check AWS credentials
print_info "Verifying AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    print_error "AWS credentials not configured or invalid"
    print_info ""
    print_info "Please configure your AWS credentials:"
    print_info "  Run: ${YELLOW}aws configure${NC}"
    print_info ""
    print_info "You will need:"
    print_info "  - AWS Access Key ID"
    print_info "  - AWS Secret Access Key"
    print_info "  - Default region (e.g., us-east-1)"
    print_info ""
    print_info "For more information:"
    print_info "  https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html"
    exit 1
fi

AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
if [ -z "$AWS_REGION" ]; then
    AWS_REGION="us-east-1"
    print_warning "No default region configured, using us-east-1"
fi
print_success "AWS Account: $AWS_ACCOUNT"
print_success "AWS Region: $AWS_REGION"

# Check CDK CLI
if check_command cdk; then
    CDK_VERSION=$(cdk --version 2>&1)
    print_success "AWS CDK found: $CDK_VERSION"
else
    print_error "AWS CDK CLI is required but not installed"
    print_info ""
    print_info "Installation instructions:"
    print_info "  Run: ${YELLOW}npm install -g aws-cdk${NC}"
    print_info ""
    print_info "For more information:"
    print_info "  https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html"
    exit 1
fi

################################################################################
# Check Stack Status
################################################################################

print_header "Checking Stack Status"

print_info "Checking if CloudFormation stack exists..."

# Check if stack exists
if ! aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION &> /dev/null; then
    print_warning "Stack '$STACK_NAME' not found in region $AWS_REGION"
    print_info ""
    print_info "The stack may have already been deleted or never existed."
    print_info "Nothing to clean up."
    print_info ""
    exit 0
fi

# Get stack status
STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus" --output text)
print_success "Stack found: $STACK_NAME"
print_info "Stack status: $STACK_STATUS"

# Check if stack is in a deletable state
case $STACK_STATUS in
    *_IN_PROGRESS)
        print_error "Stack is currently in progress: $STACK_STATUS"
        print_info "Please wait for the current operation to complete before running teardown."
        exit 1
        ;;
    DELETE_COMPLETE)
        print_warning "Stack is already deleted"
        print_info "Nothing to clean up."
        exit 0
        ;;
esac

################################################################################
# Retrieve Bucket Names
################################################################################

print_header "Retrieving Resource Information"

print_info "Retrieving bucket names from stack outputs..."

# Try to get outputs from stack
DOCUMENT_BUCKET=""
WEBSITE_BUCKET=""
CLOUDFRONT_ID=""

if command -v jq &> /dev/null; then
    # Use jq if available
    STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].Outputs" --output json)
    DOCUMENT_BUCKET=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="DocumentBucketName") | .OutputValue // empty')
    WEBSITE_BUCKET=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="WebsiteBucketName") | .OutputValue // empty')
    CLOUDFRONT_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="CloudFrontDistributionId") | .OutputValue // empty')
else
    # Fallback to basic parsing
    print_warning "jq not found, using basic parsing (install jq for better output)"
    STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].Outputs" --output text)
    DOCUMENT_BUCKET=$(echo "$STACK_OUTPUTS" | grep "DocumentBucketName" | awk '{print $NF}')
    WEBSITE_BUCKET=$(echo "$STACK_OUTPUTS" | grep "WebsiteBucketName" | awk '{print $NF}')
    CLOUDFRONT_ID=$(echo "$STACK_OUTPUTS" | grep "CloudFrontDistributionId" | awk '{print $NF}')
fi

# Display found resources
if [ -n "$DOCUMENT_BUCKET" ]; then
    print_success "Document bucket: $DOCUMENT_BUCKET"
else
    print_warning "Document bucket name not found in stack outputs"
fi

if [ -n "$WEBSITE_BUCKET" ]; then
    print_success "Website bucket: $WEBSITE_BUCKET"
else
    print_warning "Website bucket name not found in stack outputs"
fi

if [ -n "$CLOUDFRONT_ID" ]; then
    print_success "CloudFront distribution: $CLOUDFRONT_ID"
else
    print_warning "CloudFront distribution ID not found in stack outputs"
fi

# Get Lambda functions
print_info "Retrieving Lambda functions..."
LAMBDA_FUNCTIONS=$(aws lambda list-functions --region $AWS_REGION --query "Functions[?contains(FunctionName, '$STACK_NAME')].FunctionName" --output text)
if [ -n "$LAMBDA_FUNCTIONS" ]; then
    LAMBDA_COUNT=$(echo "$LAMBDA_FUNCTIONS" | wc -w | tr -d ' ')
    print_success "Found $LAMBDA_COUNT Lambda function(s)"
else
    print_warning "No Lambda functions found for this stack"
fi

# Get API Gateway
print_info "Retrieving API Gateway..."
API_GATEWAYS=$(aws apigateway get-rest-apis --region $AWS_REGION --query "items[?contains(name, '$STACK_NAME')].name" --output text)
if [ -n "$API_GATEWAYS" ]; then
    API_COUNT=$(echo "$API_GATEWAYS" | wc -w | tr -d ' ')
    print_success "Found $API_COUNT API Gateway(s)"
else
    print_warning "No API Gateways found for this stack"
fi

################################################################################
# Confirmation Prompt
################################################################################

if [ "$FORCE_MODE" = false ]; then
    print_header "Confirmation Required"
    
    echo -e "${YELLOW}The following resources will be PERMANENTLY DELETED:${NC}"
    echo ""
    echo -e "  ${RED}CloudFormation Stack:${NC} $STACK_NAME"
    
    if [ -n "$DOCUMENT_BUCKET" ]; then
        echo -e "  ${RED}S3 Bucket:${NC} $DOCUMENT_BUCKET (and all contents)"
    fi
    
    if [ -n "$WEBSITE_BUCKET" ]; then
        echo -e "  ${RED}S3 Bucket:${NC} $WEBSITE_BUCKET (and all contents)"
    fi
    
    if [ -n "$CLOUDFRONT_ID" ]; then
        echo -e "  ${RED}CloudFront Distribution:${NC} $CLOUDFRONT_ID"
    fi
    
    if [ -n "$LAMBDA_FUNCTIONS" ]; then
        echo -e "  ${RED}Lambda Functions:${NC} $LAMBDA_COUNT function(s)"
    fi
    
    if [ -n "$API_GATEWAYS" ]; then
        echo -e "  ${RED}API Gateway:${NC} $API_COUNT API(s)"
    fi
    
    if [ "$KEEP_LOGS" = false ]; then
        echo -e "  ${RED}CloudWatch Log Groups:${NC} All logs for this stack"
    fi
    
    echo ""
    echo -e "${YELLOW}This action CANNOT be undone!${NC}"
    echo ""
    
    read -p "Are you sure you want to proceed? (yes/no): " CONFIRMATION
    
    if [ "$CONFIRMATION" != "yes" ]; then
        print_info "Teardown cancelled by user"
        exit 0
    fi
    
    print_success "Confirmation received, proceeding with teardown..."
fi

################################################################################
# Empty S3 Buckets
################################################################################

print_header "Emptying S3 Buckets"

# Function to empty a bucket including versioned objects
empty_bucket() {
    local bucket=$1
    
    if [ -z "$bucket" ]; then
        return 0
    fi
    
    print_info "Emptying bucket: $bucket..."
    
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket "$bucket" --region $AWS_REGION 2>/dev/null; then
        print_warning "Bucket $bucket does not exist or is not accessible"
        return 0
    fi
    
    # Check if versioning is enabled
    VERSIONING=$(aws s3api get-bucket-versioning --bucket "$bucket" --region $AWS_REGION --query "Status" --output text 2>/dev/null || echo "Disabled")
    
    if [ "$VERSIONING" = "Enabled" ]; then
        print_info "Versioning is enabled, deleting all versions and delete markers..."
        
        # Delete all object versions
        aws s3api list-object-versions --bucket "$bucket" --region $AWS_REGION --output json | \
        jq -r '.Versions[]? | "--key \"\(.Key)\" --version-id \"\(.VersionId)\""' | \
        while read -r args; do
            if [ -n "$args" ]; then
                eval aws s3api delete-object --bucket "$bucket" --region $AWS_REGION $args > /dev/null 2>&1 || true
            fi
        done
        
        # Delete all delete markers
        aws s3api list-object-versions --bucket "$bucket" --region $AWS_REGION --output json | \
        jq -r '.DeleteMarkers[]? | "--key \"\(.Key)\" --version-id \"\(.VersionId)\""' | \
        while read -r args; do
            if [ -n "$args" ]; then
                eval aws s3api delete-object --bucket "$bucket" --region $AWS_REGION $args > /dev/null 2>&1 || true
            fi
        done
    fi
    
    # Delete all current objects (works for both versioned and non-versioned buckets)
    aws s3 rm s3://$bucket --recursive --region $AWS_REGION > /dev/null 2>&1 || true
    
    # Verify bucket is empty
    OBJECT_COUNT=$(aws s3 ls s3://$bucket --region $AWS_REGION 2>/dev/null | wc -l | tr -d ' ')
    if [ "$OBJECT_COUNT" -eq 0 ]; then
        print_success "Bucket $bucket emptied successfully"
    else
        print_warning "Bucket $bucket may still contain objects (found $OBJECT_COUNT)"
    fi
}

# Empty document bucket
if [ -n "$DOCUMENT_BUCKET" ]; then
    empty_bucket "$DOCUMENT_BUCKET"
else
    print_warning "Document bucket name not available, skipping"
fi

# Empty website bucket
if [ -n "$WEBSITE_BUCKET" ]; then
    empty_bucket "$WEBSITE_BUCKET"
else
    print_warning "Website bucket name not available, skipping"
fi

################################################################################
# Delete CloudWatch Log Groups (Optional)
################################################################################

if [ "$KEEP_LOGS" = false ]; then
    print_header "Deleting CloudWatch Log Groups"
    
    print_info "Finding log groups for stack..."
    LOG_GROUPS=$(aws logs describe-log-groups --region $AWS_REGION --query "logGroups[?contains(logGroupName, '$STACK_NAME')].logGroupName" --output text)
    
    if [ -n "$LOG_GROUPS" ]; then
        LOG_COUNT=$(echo "$LOG_GROUPS" | wc -w | tr -d ' ')
        print_info "Found $LOG_COUNT log group(s)"
        
        for LOG_GROUP in $LOG_GROUPS; do
            print_info "Deleting log group: $LOG_GROUP"
            aws logs delete-log-group --log-group-name "$LOG_GROUP" --region $AWS_REGION 2>/dev/null || true
        done
        
        print_success "Log groups deleted"
    else
        print_info "No log groups found for this stack"
    fi
else
    print_warning "Keeping CloudWatch log groups (--keep-logs flag provided)"
fi

################################################################################
# Destroy CDK Stack
################################################################################

print_header "Destroying CDK Stack"

print_info "Running cdk destroy..."
print_warning "This may take 5-10 minutes..."

if cdk destroy --force; then
    print_success "CDK stack destroyed successfully"
else
    print_error "CDK destroy failed"
    print_info ""
    print_info "Troubleshooting:"
    print_info "  1. Check CloudFormation console for error details:"
    print_info "     https://console.aws.amazon.com/cloudformation/home?region=$AWS_REGION"
    print_info "  2. Manually delete any remaining resources blocking deletion"
    print_info "  3. Try running this script again"
    print_info ""
    print_info "Common issues:"
    print_info "  - S3 buckets not empty (script should have emptied them)"
    print_info "  - Resources created outside of CDK"
    print_info "  - Insufficient IAM permissions"
    exit 1
fi

################################################################################
# Verify Stack Deletion
################################################################################

print_header "Verifying Stack Deletion"

print_info "Checking if stack was deleted..."

# Wait a moment for deletion to propagate
sleep 2

if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION &> /dev/null; then
    STACK_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus" --output text)
    
    if [ "$STACK_STATUS" = "DELETE_IN_PROGRESS" ]; then
        print_warning "Stack deletion in progress"
        print_info "This may take several minutes to complete"
    elif [ "$STACK_STATUS" = "DELETE_COMPLETE" ]; then
        print_success "Stack deleted successfully"
    else
        print_warning "Stack status: $STACK_STATUS"
    fi
else
    print_success "CloudFormation stack deleted"
fi

################################################################################
# Verify Resource Cleanup
################################################################################

print_header "Verifying Resource Cleanup"

# Check S3 buckets
print_info "Verifying S3 buckets deleted..."
REMAINING_BUCKETS=0

if [ -n "$DOCUMENT_BUCKET" ]; then
    if aws s3api head-bucket --bucket "$DOCUMENT_BUCKET" --region $AWS_REGION 2>/dev/null; then
        print_warning "Document bucket still exists: $DOCUMENT_BUCKET"
        REMAINING_BUCKETS=$((REMAINING_BUCKETS + 1))
    else
        print_success "Document bucket deleted"
    fi
fi

if [ -n "$WEBSITE_BUCKET" ]; then
    if aws s3api head-bucket --bucket "$WEBSITE_BUCKET" --region $AWS_REGION 2>/dev/null; then
        print_warning "Website bucket still exists: $WEBSITE_BUCKET"
        REMAINING_BUCKETS=$((REMAINING_BUCKETS + 1))
    else
        print_success "Website bucket deleted"
    fi
fi

if [ $REMAINING_BUCKETS -eq 0 ]; then
    print_success "All S3 buckets deleted"
fi

# Check Lambda functions
print_info "Verifying Lambda functions deleted..."
REMAINING_LAMBDAS=$(aws lambda list-functions --region $AWS_REGION --query "Functions[?contains(FunctionName, '$STACK_NAME')].FunctionName" --output text)

if [ -z "$REMAINING_LAMBDAS" ]; then
    print_success "All Lambda functions deleted"
else
    LAMBDA_COUNT=$(echo "$REMAINING_LAMBDAS" | wc -w | tr -d ' ')
    print_warning "$LAMBDA_COUNT Lambda function(s) still exist"
fi

# Check API Gateway
print_info "Verifying API Gateway deleted..."
REMAINING_APIS=$(aws apigateway get-rest-apis --region $AWS_REGION --query "items[?contains(name, '$STACK_NAME')].name" --output text)

if [ -z "$REMAINING_APIS" ]; then
    print_success "API Gateway deleted"
else
    API_COUNT=$(echo "$REMAINING_APIS" | wc -w | tr -d ' ')
    print_warning "$API_COUNT API Gateway(s) still exist"
fi

# Check CloudFormation stack
print_info "Verifying CloudFormation stack deleted..."
if aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION &> /dev/null; then
    FINAL_STATUS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --region $AWS_REGION --query "Stacks[0].StackStatus" --output text)
    
    if [ "$FINAL_STATUS" = "DELETE_COMPLETE" ] || [ "$FINAL_STATUS" = "DELETE_IN_PROGRESS" ]; then
        print_success "CloudFormation stack deletion confirmed"
    else
        print_warning "CloudFormation stack still exists with status: $FINAL_STATUS"
    fi
else
    print_success "CloudFormation stack fully deleted"
fi

################################################################################
# Success Message
################################################################################

print_header "Teardown Complete! ✓"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  Prompt Caching Demo Successfully Removed!                    ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${BLUE}Resources Removed:${NC}"
if [ -n "$DOCUMENT_BUCKET" ]; then
    echo -e "  ${GREEN}✓${NC} S3 Document Bucket: $DOCUMENT_BUCKET"
fi
if [ -n "$WEBSITE_BUCKET" ]; then
    echo -e "  ${GREEN}✓${NC} S3 Website Bucket: $WEBSITE_BUCKET"
fi
if [ -n "$CLOUDFRONT_ID" ]; then
    echo -e "  ${GREEN}✓${NC} CloudFront Distribution: $CLOUDFRONT_ID"
fi
if [ -n "$LAMBDA_FUNCTIONS" ]; then
    echo -e "  ${GREEN}✓${NC} Lambda Functions: $LAMBDA_COUNT function(s)"
fi
if [ -n "$API_GATEWAYS" ]; then
    echo -e "  ${GREEN}✓${NC} API Gateway: $API_COUNT API(s)"
fi
echo -e "  ${GREEN}✓${NC} CloudFormation Stack: $STACK_NAME"

if [ "$KEEP_LOGS" = false ]; then
    echo -e "  ${GREEN}✓${NC} CloudWatch Log Groups"
fi

echo -e "\n${YELLOW}Important Notes:${NC}"
echo -e "  • CloudFront distribution deletion may take 15-30 minutes to fully complete"
echo -e "  • Some AWS resources may take a few minutes to fully propagate deletion"
echo -e "  • Check CloudFormation console if you need to verify deletion status"

if [ $REMAINING_BUCKETS -gt 0 ] || [ -n "$REMAINING_LAMBDAS" ] || [ -n "$REMAINING_APIS" ]; then
    echo -e "\n${YELLOW}Remaining Resources:${NC}"
    echo -e "  Some resources may still be in the process of deletion."
    echo -e "  Check the AWS console in a few minutes to verify complete removal."
fi

echo -e "\n${BLUE}Verification:${NC}"
echo -e "  CloudFormation: https://console.aws.amazon.com/cloudformation/home?region=$AWS_REGION"
echo -e "  S3 Buckets: https://s3.console.aws.amazon.com/s3/home?region=$AWS_REGION"
echo -e "  Lambda Functions: https://console.aws.amazon.com/lambda/home?region=$AWS_REGION#/functions"

echo -e "\n${BLUE}To Redeploy:${NC}"
echo -e "  Run: ${YELLOW}./scripts/setup.sh${NC}"

echo -e "\n${GREEN}Cleanup complete! 🧹${NC}\n"
