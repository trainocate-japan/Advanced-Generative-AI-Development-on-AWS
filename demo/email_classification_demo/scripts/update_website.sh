#!/bin/bash

################################################################################
# Update Website Files - Upload website files to S3 and invalidate CloudFront
################################################################################

set -e

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Check if outputs.json exists
if [ ! -f "outputs.json" ]; then
    print_error "outputs.json not found. Run './scripts/setup.sh' first."
    exit 1
fi

# Extract values from outputs.json
if command -v jq &> /dev/null; then
    WEBSITE_BUCKET=$(jq -r '.EmailClassificationStack.WebsiteBucketName // empty' outputs.json)
    API_URL=$(jq -r '.EmailClassificationStack.ApiGatewayUrl // empty' outputs.json)
    CLOUDFRONT_ID=$(jq -r '.EmailClassificationStack.CloudFrontDistributionId // empty' outputs.json)
else
    WEBSITE_BUCKET=$(grep -o '"WebsiteBucketName"[^,]*' outputs.json | cut -d'"' -f4)
    API_URL=$(grep -o '"ApiGatewayUrl"[^,]*' outputs.json | cut -d'"' -f4)
    CLOUDFRONT_ID=$(grep -o '"CloudFrontDistributionId"[^,]*' outputs.json | cut -d'"' -f4)
fi

if [ -z "$WEBSITE_BUCKET" ] || [ -z "$API_URL" ]; then
    print_error "Failed to extract stack outputs"
    exit 1
fi

print_info "Website Bucket: $WEBSITE_BUCKET"
print_info "API Gateway URL: $API_URL"
print_info "CloudFront Distribution: $CLOUDFRONT_ID"

# Update config.js with correct API Gateway URL
print_info "Updating config.js with API Gateway URL..."
cat > website/config.js << EOF
// API Configuration - Auto-generated
// This file is created during deployment and should not be edited manually
window.API_GATEWAY_URL = '${API_URL}';
console.log('API Gateway URL configured:', window.API_GATEWAY_URL);
EOF

print_success "config.js updated"

# Upload all website files to S3
print_info "Uploading website files to S3..."
aws s3 sync website/ s3://${WEBSITE_BUCKET}/ \
    --exclude "*.md" \
    --exclude ".DS_Store" \
    --cache-control "public, max-age=300"

print_success "Website files uploaded"

# Invalidate CloudFront cache
if [ -n "$CLOUDFRONT_ID" ]; then
    print_info "Invalidating CloudFront cache..."
    aws cloudfront create-invalidation \
        --distribution-id $CLOUDFRONT_ID \
        --paths "/*" > /dev/null
    print_success "CloudFront cache invalidated"
else
    print_error "CloudFront distribution ID not found, skipping cache invalidation"
fi

print_success "Website update complete!"
