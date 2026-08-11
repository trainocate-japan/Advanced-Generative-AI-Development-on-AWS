#!/bin/bash

################################################################################
# Prompt Caching Demo - Automated Setup Script
################################################################################
#
# This script automates the deployment of the Prompt Caching Demo CDK stack.
# It performs the following steps:
#   1. Validates prerequisites (AWS CLI, CDK, Python 3.12+, Node.js 18+)
#   2. Bootstraps CDK environment (if needed)
#   3. Deploys the CDK stack
#   4. Uploads AWS CAF for AI document to S3
#   5. Deploys website files with generated configuration
#   6. Verifies deployment and displays access URLs
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
#   - Python 3.12+ with pip
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
DOCUMENT_FILE="data/aws-caf-for-ai.txt"
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

check_python_version() {
    local version=$1
    local required_major=3
    local required_minor=12
    
    if [[ $version =~ Python[[:space:]]([0-9]+)\.([0-9]+) ]]; then
        local major="${BASH_REMATCH[1]}"
        local minor="${BASH_REMATCH[2]}"
        
        if [ "$major" -gt "$required_major" ] || \
           ([ "$major" -eq "$required_major" ] && [ "$minor" -ge "$required_minor" ]); then
            return 0
        fi
    fi
    return 1
}

check_node_version() {
    local version=$1
    local required_major=18
    
    if [[ $version =~ v([0-9]+) ]]; then
        local major="${BASH_REMATCH[1]}"
        
        if [ "$major" -ge "$required_major" ]; then
            return 0
        fi
    fi
    return 1
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

# Check Node.js
if check_command node; then
    NODE_VERSION=$(node --version)
    if check_node_version "$NODE_VERSION"; then
        print_success "Node.js found: $NODE_VERSION"
    else
        print_error "Node.js 18+ is required, found: $NODE_VERSION"
        print_info ""
        print_info "Installation instructions:"
        print_info "  macOS:   brew install node@18"
        print_info "  Linux:   https://nodejs.org/en/download/package-manager"
        print_info "  Windows: https://nodejs.org/en/download"
        print_info ""
        print_info "Official download: https://nodejs.org/"
        exit 1
    fi
else
    print_error "Node.js is required but not installed"
    print_info ""
    print_info "Installation instructions:"
    print_info "  macOS:   brew install node"
    print_info "  Linux:   https://nodejs.org/en/download/package-manager"
    print_info "  Windows: https://nodejs.org/en/download"
    print_info ""
    print_info "Official download: https://nodejs.org/"
    exit 1
fi

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

# Check Python
if check_command python3; then
    PYTHON_VERSION=$(python3 --version)
    if check_python_version "$PYTHON_VERSION"; then
        print_success "Python found: $PYTHON_VERSION"
    else
        print_error "Python 3.12+ is required, found: $PYTHON_VERSION"
        print_info ""
        print_info "Installation instructions:"
        print_info "  macOS:   brew install python@3.12"
        print_info "  Linux:   https://www.python.org/downloads/"
        print_info "  Windows: https://www.python.org/downloads/"
        print_info ""
        print_info "Official download: https://www.python.org/downloads/"
        exit 1
    fi
else
    print_error "Python 3.12+ is required but not installed"
    print_info ""
    print_info "Installation instructions:"
    print_info "  macOS:   brew install python@3.12"
    print_info "  Linux:   https://www.python.org/downloads/"
    print_info "  Windows: https://www.python.org/downloads/"
    print_info ""
    print_info "Official download: https://www.python.org/downloads/"
    exit 1
fi

# Check pip
if check_command pip3; then
    print_success "pip3 found"
else
    print_error "pip3 is required but not installed"
    print_info ""
    print_info "pip3 should be included with Python 3.12+"
    print_info "If missing, reinstall Python or install pip separately"
    exit 1
fi

# Check if document file exists
if [ ! -f "$DOCUMENT_FILE" ]; then
    print_error "AWS CAF for AI document not found: $DOCUMENT_FILE"
    print_info ""
    print_info "Expected location: $PROJECT_ROOT/$DOCUMENT_FILE"
    print_info "Please ensure the document file exists before running setup"
    exit 1
fi
print_success "AWS CAF for AI document found"

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
            print_info ""
            print_info "Troubleshooting:"
            print_info "  - Verify your AWS credentials have sufficient permissions"
            print_info "  - Check that CloudFormation service is available in your region"
            print_info "  - Review error messages above for specific issues"
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
    print_info ""
    print_info "Troubleshooting:"
    print_info "  - Check your CDK code for syntax errors"
    print_info "  - Verify all required CDK dependencies are installed"
    print_info "  - Review error messages above for specific issues"
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
    print_info "  1. Check CloudFormation console for error details:"
    print_info "     https://console.aws.amazon.com/cloudformation/home?region=$AWS_REGION"
    print_info "  2. Run '${YELLOW}cdk destroy${NC}' to clean up partial deployment"
    print_info "  3. Fix the issue and run this script again"
    print_info ""
    print_info "Common issues:"
    print_info "  - Insufficient IAM permissions"
    print_info "  - Service quotas exceeded"
    print_info "  - Resource naming conflicts"
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
    DOCUMENT_BUCKET=$(jq -r ".$STACK_NAME.DocumentBucketName // empty" outputs.json)
    WEBSITE_BUCKET=$(jq -r ".$STACK_NAME.WebsiteBucketName // empty" outputs.json)
    API_URL=$(jq -r ".$STACK_NAME.ApiGatewayURL // empty" outputs.json)
    CLOUDFRONT_URL=$(jq -r ".$STACK_NAME.CloudFrontURL // empty" outputs.json)
    CLOUDFRONT_ID=$(jq -r ".$STACK_NAME.CloudFrontDistributionId // empty" outputs.json)
else
    print_warning "jq not found, using basic parsing (install jq for better output)"
    DOCUMENT_BUCKET=$(grep -o '"DocumentBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    WEBSITE_BUCKET=$(grep -o '"WebsiteBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    API_URL=$(grep -o '"ApiGatewayURL"[^,]*' outputs.json | cut -d'"' -f4)
    CLOUDFRONT_URL=$(grep -o '"CloudFrontURL"[^,]*' outputs.json | cut -d'"' -f4)
    CLOUDFRONT_ID=$(grep -o '"CloudFrontDistributionId"[^,]*' outputs.json | cut -d'"' -f4)
fi

# Verify critical outputs exist
if [ -z "$DOCUMENT_BUCKET" ] || [ -z "$WEBSITE_BUCKET" ] || [ -z "$CLOUDFRONT_URL" ]; then
    print_error "Failed to retrieve stack outputs"
    print_info "Check outputs.json for details"
    exit 1
fi

print_success "Document Bucket: $DOCUMENT_BUCKET"
print_success "Website Bucket: $WEBSITE_BUCKET"
print_success "API Gateway URL: $API_URL"
print_success "CloudFront URL: $CLOUDFRONT_URL"
print_success "CloudFront Distribution ID: $CLOUDFRONT_ID"

################################################################################
# Upload Document to S3
################################################################################

print_header "Uploading AWS CAF for AI Document"

print_info "Uploading document to S3..."

if aws s3 cp $DOCUMENT_FILE s3://$DOCUMENT_BUCKET/aws-caf-for-ai.txt; then
    print_success "Document uploaded successfully"
    
    # Verify upload
    if aws s3 ls s3://$DOCUMENT_BUCKET/aws-caf-for-ai.txt &> /dev/null; then
        print_success "Document upload verified"
    else
        print_warning "Document upload verification failed (may need time to propagate)"
    fi
else
    print_error "Failed to upload document"
    print_warning "You can manually upload it later with:"
    print_warning "  aws s3 cp $DOCUMENT_FILE s3://$DOCUMENT_BUCKET/aws-caf-for-ai.txt"
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
    --exclude ".gitkeep" \
    --cache-control "public, max-age=300"; then
    print_success "Website files uploaded successfully"
else
    print_error "Failed to upload website files"
    print_warning "You can manually upload them later with:"
    print_warning "  aws s3 sync website/ s3://$WEBSITE_BUCKET/"
fi

# Invalidate CloudFront cache
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
if aws lambda get-function --function-name PromptCachingStack-QueryHandler* --region $AWS_REGION &> /dev/null 2>&1; then
    print_success "Query handler Lambda function is accessible"
else
    # Try to find the function by listing all functions
    LAMBDA_COUNT=$(aws lambda list-functions --region $AWS_REGION --query "Functions[?contains(FunctionName, 'QueryHandler')].FunctionName" --output text | wc -w)
    if [ "$LAMBDA_COUNT" -gt 0 ]; then
        print_success "Query handler Lambda function is accessible"
    else
        print_warning "Lambda function verification inconclusive (may have different naming)"
    fi
fi

# Check if S3 buckets are accessible and contain files
print_info "Verifying S3 buckets..."
if aws s3 ls s3://$DOCUMENT_BUCKET &> /dev/null; then
    print_success "Document bucket is accessible"
    
    # Check if document exists
    if aws s3 ls s3://$DOCUMENT_BUCKET/aws-caf-for-ai.txt &> /dev/null; then
        print_success "Document file exists in bucket"
    else
        print_warning "Document file not found in bucket"
    fi
else
    print_warning "Cannot access document bucket (may need time to propagate)"
fi

if aws s3 ls s3://$WEBSITE_BUCKET &> /dev/null; then
    print_success "Website bucket is accessible"
    
    # Check if website files exist
    FILE_COUNT=$(aws s3 ls s3://$WEBSITE_BUCKET/ | wc -l)
    if [ "$FILE_COUNT" -gt 0 ]; then
        print_success "Website files exist in bucket ($FILE_COUNT files)"
    else
        print_warning "No website files found in bucket"
    fi
else
    print_warning "Cannot access website bucket (may need time to propagate)"
fi

# Check API Gateway health endpoint
print_info "Verifying API Gateway..."
if curl -s -o /dev/null -w "%{http_code}" "${API_URL}health" | grep -q "200"; then
    print_success "API Gateway health check passed"
else
    print_warning "API Gateway health check failed (may need time to propagate)"
fi

# Check CloudFront distribution status
print_info "Verifying CloudFront distribution..."
if [ -n "$CLOUDFRONT_ID" ]; then
    CF_STATUS=$(aws cloudfront get-distribution --id $CLOUDFRONT_ID --query "Distribution.Status" --output text 2>/dev/null || echo "Unknown")
    if [ "$CF_STATUS" = "Deployed" ]; then
        print_success "CloudFront distribution is active"
    else
        print_warning "CloudFront distribution status: $CF_STATUS (may take 10-15 minutes to fully deploy)"
    fi
else
    print_warning "CloudFront distribution ID not available for verification"
fi

# Verify document meets token requirements
print_info "Verifying document token requirements..."
if [ -f "$DOCUMENT_FILE" ]; then
    WORD_COUNT=$(wc -w < "$DOCUMENT_FILE")
    ESTIMATED_TOKENS=$(echo "$WORD_COUNT * 1.3" | bc | cut -d'.' -f1)
    
    if [ "$ESTIMATED_TOKENS" -ge 1024 ]; then
        print_success "Document meets minimum token requirements (estimated: $ESTIMATED_TOKENS tokens)"
    else
        print_warning "Document may not meet minimum token requirements (estimated: $ESTIMATED_TOKENS tokens, minimum: 1024)"
    fi
else
    print_warning "Cannot verify document token requirements (file not found)"
fi

################################################################################
# Success Message
################################################################################

print_header "Deployment Complete! 🎉"

echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║  Prompt Caching Demo Successfully Deployed!                   ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${BLUE}Access Your Application:${NC}"
echo -e "  ${GREEN}CloudFront URL:${NC} $CLOUDFRONT_URL"
echo -e "  ${GREEN}API Gateway:${NC} $API_URL"

echo -e "\n${BLUE}S3 Buckets:${NC}"
echo -e "  ${GREEN}Document:${NC} $DOCUMENT_BUCKET"
echo -e "  ${GREEN}Website:${NC} $WEBSITE_BUCKET"

echo -e "\n${BLUE}Next Steps:${NC}"
echo -e "  1. Open the CloudFront URL in your browser"
echo -e "     ${BLUE}→${NC} ${YELLOW}$CLOUDFRONT_URL${NC}"
echo -e "  2. Wait 2-3 minutes for CloudFront distribution to fully activate"
echo -e "  3. Submit a question about AWS CAF for AI"
echo -e "  4. Observe the prompt caching demonstration:"
echo -e "     ${BLUE}→${NC} Baseline request (no cache)"
echo -e "     ${BLUE}→${NC} Cache write request (creates cache)"
echo -e "     ${BLUE}→${NC} Cache hit request (uses cache)"
echo -e "  5. Review token reduction and latency improvements"

echo -e "\n${BLUE}Educational Features:${NC}"
echo -e "  • Interactive architecture diagram with tooltips"
echo -e "  • Side-by-side comparison of cached vs non-cached performance"
echo -e "  • Real-time metrics showing token reduction percentage"
echo -e "  • Query history with cache performance tracking"

echo -e "\n${BLUE}Monitoring:${NC}"
echo -e "  CloudWatch Logs: https://console.aws.amazon.com/cloudwatch/home?region=$AWS_REGION#logsV2:log-groups"
echo -e "  Lambda Functions: https://console.aws.amazon.com/lambda/home?region=$AWS_REGION#/functions"
echo -e "  S3 Buckets: https://s3.console.aws.amazon.com/s3/home?region=$AWS_REGION"

echo -e "\n${BLUE}Cleanup:${NC}"
echo -e "  To remove all resources, run: ${YELLOW}./scripts/teardown.sh${NC}"

echo -e "\n${GREEN}Happy learning! 🚀${NC}\n"
