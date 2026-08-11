#!/bin/bash

################################################################################
# Email Classification System - Automated Setup Script
################################################################################
#
# This script automates the deployment of the Email Classification CDK stack.
# It performs the following steps:
#   1. Validates prerequisites (AWS CLI, CDK, Python)
#   2. Bootstraps CDK environment (if needed)
#   3. Deploys the CDK stack
#   4. Uploads department configuration to S3
#   5. Verifies deployment and displays access URLs
#
# Usage:
#   ./scripts/setup.sh [--skip-bootstrap]
#
# Options:
#   --skip-bootstrap    Skip CDK bootstrap step (use if already bootstrapped)
#
# Requirements:
#   - AWS CLI configured with valid credentials
#   - Node.js 18+ and AWS CDK CLI installed
#   - Python 3.11+ with pip
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
CONFIG_FILE="config/department_config.json"
SKIP_BOOTSTRAP=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-bootstrap)
            SKIP_BOOTSTRAP=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--skip-bootstrap]"
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

# Check Node.js
if check_command node; then
    NODE_VERSION=$(node --version)
    print_success "Node.js found: $NODE_VERSION"
else
    print_error "Node.js is required. Install from: https://nodejs.org/"
    exit 1
fi

# Check CDK CLI
if check_command cdk; then
    CDK_VERSION=$(cdk --version 2>&1)
    print_success "AWS CDK found: $CDK_VERSION"
else
    print_error "AWS CDK CLI is required. Install with: npm install -g aws-cdk"
    exit 1
fi

# Check Python
if check_command python3; then
    PYTHON_VERSION=$(python3 --version)
    print_success "Python found: $PYTHON_VERSION"
else
    print_error "Python 3.11+ is required"
    exit 1
fi

# Check pip
if check_command pip3; then
    print_success "pip3 found"
else
    print_error "pip3 is required"
    exit 1
fi

# Check if department config exists
if [ ! -f "$CONFIG_FILE" ]; then
    print_error "Department configuration file not found: $CONFIG_FILE"
    exit 1
fi
print_success "Department configuration file found"

################################################################################
# Install Python Dependencies
################################################################################

print_header "Installing Python Dependencies"

if [ -f "requirements.txt" ]; then
    print_info "Installing dependencies from requirements.txt..."
    pip3 install -r requirements.txt --quiet
    print_success "Python dependencies installed"
else
    print_warning "requirements.txt not found, skipping dependency installation"
fi

################################################################################
# CDK Bootstrap
################################################################################

if [ "$SKIP_BOOTSTRAP" = false ]; then
    print_header "Bootstrapping CDK Environment"
    
    print_info "Checking if CDK is already bootstrapped..."
    
    # Check if bootstrap stack exists
    if aws cloudformation describe-stacks --stack-name CDKToolkit --region $AWS_REGION &> /dev/null; then
        print_success "CDK already bootstrapped in this region"
    else
        print_info "Bootstrapping CDK for account $AWS_ACCOUNT in region $AWS_REGION..."
        if cdk bootstrap aws://$AWS_ACCOUNT/$AWS_REGION; then
            print_success "CDK bootstrap completed"
        else
            print_error "CDK bootstrap failed"
            exit 1
        fi
    fi
else
    print_warning "Skipping CDK bootstrap (--skip-bootstrap flag provided)"
fi

################################################################################
# CDK Synthesis
################################################################################

print_header "Synthesizing CDK Stack"

print_info "Generating CloudFormation template..."
if cdk synth > /dev/null; then
    print_success "CDK synthesis completed"
else
    print_error "CDK synthesis failed"
    print_info "Check your CDK code for errors"
    exit 1
fi

################################################################################
# CDK Deployment
################################################################################

print_header "Deploying CDK Stack"

print_info "Deploying $STACK_NAME..."
print_warning "This may take 5-10 minutes..."

if cdk deploy --require-approval never --outputs-file outputs.json; then
    print_success "CDK deployment completed"
else
    print_error "CDK deployment failed"
    print_info ""
    print_info "Rollback instructions:"
    print_info "  1. Check CloudFormation console for error details"
    print_info "  2. Run 'cdk destroy' to clean up partial deployment"
    print_info "  3. Fix the issue and run this script again"
    exit 1
fi

################################################################################
# Verify Stack Outputs
################################################################################

print_header "Verifying Stack Outputs"

if [ ! -f "outputs.json" ]; then
    print_error "outputs.json not found. Stack may not have deployed correctly."
    exit 1
fi

# Extract outputs using jq if available, otherwise use grep/sed
if command -v jq &> /dev/null; then
    INBOX_BUCKET=$(jq -r ".$STACK_NAME.InboxBucketName // empty" outputs.json)
    DEST_BUCKET=$(jq -r ".$STACK_NAME.DestinationBucketName // empty" outputs.json)
    WEBSITE_BUCKET=$(jq -r ".$STACK_NAME.WebsiteBucketName // empty" outputs.json)
    API_URL=$(jq -r ".$STACK_NAME.ApiGatewayUrl // empty" outputs.json)
    CLOUDFRONT_URL=$(jq -r ".$STACK_NAME.CloudFrontUrl // empty" outputs.json)
else
    print_warning "jq not found, using basic parsing (install jq for better output)"
    INBOX_BUCKET=$(grep -o '"InboxBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    DEST_BUCKET=$(grep -o '"DestinationBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    WEBSITE_BUCKET=$(grep -o '"WebsiteBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    API_URL=$(grep -o '"ApiGatewayUrl"[^,]*' outputs.json | cut -d'"' -f4)
    CLOUDFRONT_URL=$(grep -o '"CloudFrontUrl"[^,]*' outputs.json | cut -d'"' -f4)
fi

# Verify critical outputs exist
if [ -z "$INBOX_BUCKET" ] || [ -z "$DEST_BUCKET" ] || [ -z "$CLOUDFRONT_URL" ]; then
    print_error "Failed to retrieve stack outputs"
    print_info "Check outputs.json for details"
    exit 1
fi

print_success "Inbox Bucket: $INBOX_BUCKET"
print_success "Destination Bucket: $DEST_BUCKET"
print_success "Website Bucket: $WEBSITE_BUCKET"
print_success "API Gateway URL: $API_URL"
print_success "CloudFront URL: $CLOUDFRONT_URL"

################################################################################
# Upload Department Configuration
################################################################################

print_header "Uploading Department Configuration"

print_info "Uploading $CONFIG_FILE to S3..."

if aws s3 cp $CONFIG_FILE s3://$INBOX_BUCKET/department_config.json; then
    print_success "Department configuration uploaded successfully"
else
    print_error "Failed to upload department configuration"
    print_warning "You can manually upload it later with:"
    print_warning "  aws s3 cp $CONFIG_FILE s3://$INBOX_BUCKET/department_config.json"
fi

################################################################################
# Deploy Website Files
################################################################################

print_header "Deploying Website Files"

# Update config.js with correct API Gateway URL
print_info "Generating config.js with API Gateway URL..."
cat > website/config.js << EOF
// API Configuration - Auto-generated
// This file is created during deployment and should not be edited manually
window.API_GATEWAY_URL = '${API_URL}';
console.log('API Gateway URL configured:', window.API_GATEWAY_URL);
EOF

print_success "config.js generated"

# Upload all website files to S3
print_info "Uploading website files to S3..."
if aws s3 sync website/ s3://$WEBSITE_BUCKET/ \
    --exclude "*.md" \
    --exclude ".DS_Store" \
    --cache-control "public, max-age=300"; then
    print_success "Website files uploaded successfully"
else
    print_error "Failed to upload website files"
    print_warning "You can manually upload them later with:"
    print_warning "  aws s3 sync website/ s3://$WEBSITE_BUCKET/"
fi

# Invalidate CloudFront cache
if command -v jq &> /dev/null; then
    CLOUDFRONT_ID=$(jq -r ".$STACK_NAME.CloudFrontDistributionId // empty" outputs.json)
else
    CLOUDFRONT_ID=$(grep -o '"CloudFrontDistributionId"[^,]*' outputs.json | cut -d'"' -f4)
fi

if [ -n "$CLOUDFRONT_ID" ]; then
    print_info "Invalidating CloudFront cache..."
    if aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_ID --paths "/*" > /dev/null 2>&1; then
        print_success "CloudFront cache invalidated"
    else
        print_warning "Failed to invalidate CloudFront cache (may need to wait a few minutes)"
    fi
else
    print_warning "CloudFront distribution ID not found, skipping cache invalidation"
fi

################################################################################
# Final Verification
################################################################################

print_header "Final Verification"

# Check if Lambda functions exist
print_info "Verifying Lambda functions..."
LAMBDA_FUNCTIONS=(
    "EmailClassification-UploadHandler"
    "EmailClassification-EmailProcessor"
    "EmailClassification-InvoiceClassifier"
)

for func in "${LAMBDA_FUNCTIONS[@]}"; do
    if aws lambda get-function --function-name $func --region $AWS_REGION &> /dev/null; then
        print_success "Lambda function exists: $func"
    else
        print_warning "Lambda function not found: $func (may have different name)"
    fi
done

# Check if S3 buckets are accessible
print_info "Verifying S3 buckets..."
if aws s3 ls s3://$INBOX_BUCKET &> /dev/null; then
    print_success "Inbox bucket is accessible"
else
    print_warning "Cannot access inbox bucket (may need time to propagate)"
fi

if aws s3 ls s3://$DEST_BUCKET &> /dev/null; then
    print_success "Destination bucket is accessible"
else
    print_warning "Cannot access destination bucket (may need time to propagate)"
fi

################################################################################
# Success Message
################################################################################

print_header "Deployment Complete! 🎉"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  Email Classification System Successfully Deployed!           ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${BLUE}Access Your Application:${NC}"
echo -e "  ${GREEN}CloudFront URL:${NC} $CLOUDFRONT_URL"
echo -e "  ${GREEN}API Gateway:${NC} $API_URL"

echo -e "\n${BLUE}S3 Buckets:${NC}"
echo -e "  ${GREEN}Inbox:${NC} $INBOX_BUCKET"
echo -e "  ${GREEN}Destination:${NC} $DEST_BUCKET"
echo -e "  ${GREEN}Website:${NC} $WEBSITE_BUCKET"

echo -e "\n${BLUE}Next Steps:${NC}"
echo -e "  1. Open the CloudFront URL in your browser"
echo -e "  2. Upload a sample EML file from the ${YELLOW}incoming/${NC} directory"
echo -e "     ${BLUE}→${NC} Test files location: ${YELLOW}$PROJECT_ROOT/incoming/${NC}"
echo -e "     ${BLUE}→${NC} Available files: email_01_finance.eml through email_10_operations.eml"
echo -e "  3. Watch the classification process in action"
echo -e "  4. Check CloudWatch logs for detailed processing information"
echo -e "  5. View classified emails in the destination bucket"

echo -e "\n${BLUE}Monitoring:${NC}"
echo -e "  CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups"
echo -e "  CloudWatch Dashboard: https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#dashboards:"

echo -e "\n${BLUE}Cleanup:${NC}"
echo -e "  To remove all resources, run: ${YELLOW}./scripts/teardown.sh${NC}"

echo -e "\n${GREEN}Happy testing! 🚀${NC}\n"
