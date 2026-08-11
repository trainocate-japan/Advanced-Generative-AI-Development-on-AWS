#!/bin/bash

# Create distribution package for instructors
# This script packages the prompt-caching-demo for easy sharing with timestamp

set -e

echo "📦 Creating distribution package for Prompt Caching Demo..."
echo ""

# Get project name and version with timestamp
PROJECT_NAME="prompt-caching-demo"
VERSION=$(date +%Y%m%d-%H%M%S)
DIST_NAME="${PROJECT_NAME}-${VERSION}"
DIST_DIR="distribution"

# Create distribution directory
mkdir -p "$DIST_DIR"

# Create a temporary staging directory
STAGING_DIR=$(mktemp -d)
STAGING_PROJECT="$STAGING_DIR/$PROJECT_NAME"
mkdir -p "$STAGING_PROJECT"

echo "📋 Preparing files for distribution..."

# Copy essential files and directories
cp app.py "$STAGING_PROJECT/"
cp cdk.json "$STAGING_PROJECT/"
cp requirements.txt "$STAGING_PROJECT/"
cp pytest.ini "$STAGING_PROJECT/"
cp .python-version "$STAGING_PROJECT/" 2>/dev/null || true

# Copy documentation
cp README.md "$STAGING_PROJECT/" 2>/dev/null || true
cp INSTRUCTOR_GUIDE.md "$STAGING_PROJECT/" 2>/dev/null || true
cp ARCHITECTURE.md "$STAGING_PROJECT/" 2>/dev/null || true
cp QUICK_START_UPLOAD.md "$STAGING_PROJECT/" 2>/dev/null || true
cp DOCUMENT_UPLOAD_FEATURE.md "$STAGING_PROJECT/" 2>/dev/null || true

# Copy directories (only if they exist)
[ -d lambda_functions ] && cp -r lambda_functions "$STAGING_PROJECT/"
[ -d prompt_caching ] && cp -r prompt_caching "$STAGING_PROJECT/"
[ -d website ] && cp -r website "$STAGING_PROJECT/"
[ -d scripts ] && cp -r scripts "$STAGING_PROJECT/"
[ -d sample-documents ] && cp -r sample-documents "$STAGING_PROJECT/"
[ -d tests ] && cp -r tests "$STAGING_PROJECT/"
[ -d data ] && cp -r data "$STAGING_PROJECT/"

# Clean up Python cache files and build artifacts
echo "🧹 Cleaning build artifacts..."
find "$STAGING_PROJECT" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_PROJECT" -type f -name "*.pyc" -delete 2>/dev/null || true
find "$STAGING_PROJECT" -type f -name "*.pyo" -delete 2>/dev/null || true
find "$STAGING_PROJECT" -type f -name ".DS_Store" -delete 2>/dev/null || true
find "$STAGING_PROJECT" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_PROJECT" -type d -name ".hypothesis" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_PROJECT" -type d -name "cdk.out" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_PROJECT" -type d -name "node_modules" -exec rm -rf {} + 2>/dev/null || true

# Remove deployment-specific files
rm -f "$STAGING_PROJECT/outputs.json" 2>/dev/null || true
rm -f "$STAGING_PROJECT/setup_output.log" 2>/dev/null || true
rm -f "$STAGING_PROJECT/DEPLOYMENT_SUCCESS.md" 2>/dev/null || true
rm -f "$STAGING_PROJECT/FILES_CHANGED.md" 2>/dev/null || true
rm -f "$STAGING_PROJECT/CHANGELOG.md" 2>/dev/null || true
rm -f "$STAGING_PROJECT/LATENCY_FIX.md" 2>/dev/null || true

# Create DISTRIBUTION_README.md with setup instructions
cat > "$STAGING_PROJECT/DISTRIBUTION_README.md" << 'EOF'
# Prompt Caching Demo - Distribution Package

This is a ready-to-deploy distribution of the Amazon Bedrock Prompt Caching demonstration.

## 📦 Package Contents

- ✅ Complete CDK infrastructure code
- ✅ Lambda functions with security features
- ✅ Interactive web interface with document upload
- ✅ Sample documents for testing
- ✅ Comprehensive test suite
- ✅ Deployment and teardown scripts
- ✅ Complete documentation including instructor guide

## 🚀 Quick Start

### Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **Python 3.10+** installed
4. **Node.js 18+** and npm installed
5. **AWS CDK** installed globally: `npm install -g aws-cdk`

### Installation Steps

1. **Extract the package**:
   ```bash
   unzip prompt-caching-demo-*.zip
   cd prompt-caching-demo
   ```

2. **Review the README**:
   ```bash
   cat README.md
   ```

3. **Deploy the demo**:
   ```bash
   ./scripts/setup.sh
   ```

4. **Access the demo**:
   - The setup script will output a CloudFront URL
   - Share this URL with students
   - Test with sample queries

5. **After your session, clean up**:
   ```bash
   ./scripts/teardown.sh
   ```

## 📚 Documentation

- **README.md** - Main project documentation
- **INSTRUCTOR_GUIDE.md** - Teaching tips, cost estimates, troubleshooting
- **ARCHITECTURE.md** - System architecture and design decisions
- **QUICK_START_UPLOAD.md** - Document upload feature guide
- **DOCUMENT_UPLOAD_FEATURE.md** - Technical details of upload feature

## 🧪 Testing

Run the test suite to verify everything works:

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest tests/

# Run specific test categories
pytest tests/test_infrastructure.py
pytest tests/test_integration.py
```

## 💰 Cost Estimates

- **Per session** (1 hour, 20 students): $1-3
- **Infrastructure** (if left running): ~$0.03/month
- **Always run teardown** after sessions to minimize costs

## 🆘 Troubleshooting

### Common Issues

1. **AWS Credentials**: Run `aws configure` to set up credentials
2. **Bedrock Access**: Enable model access in AWS Bedrock console
3. **Region Support**: Deploy to us-east-1 or us-west-2
4. **CloudFront Delay**: Wait 2-3 minutes for distribution to deploy

### Getting Help

- Check CloudWatch logs for Lambda errors
- Review the INSTRUCTOR_GUIDE.md for detailed troubleshooting
- Verify all prerequisites are installed

## 📝 Package Information

- **Distribution Date**: See filename timestamp
- **Version**: Latest stable release
- **Checksum**: See accompanying .sha256 file

## 🎓 For Instructors

This demo is designed for teaching Amazon Bedrock prompt caching concepts:

- **Duration**: 45-60 minute session
- **Audience**: Students learning AWS AI/ML services
- **Prerequisites**: Basic AWS knowledge helpful but not required
- **Learning Outcomes**: Understanding of prompt caching, cost optimization

See **INSTRUCTOR_GUIDE.md** for:
- Educational objectives
- Teaching flow recommendations
- Interactive activities
- Assessment ideas
- Cost management tips

## 📄 License

See LICENSE file for terms and conditions.

## 🤝 Support

For issues or questions:
1. Check the documentation in this package
2. Review AWS Bedrock documentation
3. Contact your AWS support team

---

**Happy Teaching!** 🎓
EOF

# Make scripts executable
chmod +x "$STAGING_PROJECT/scripts/"*.sh

# Create archive
echo "🗜️  Creating ZIP archive..."
cd "$STAGING_DIR"
zip -r "${DIST_NAME}.zip" "$PROJECT_NAME" -q

# Move to distribution directory (use absolute path)
ORIGINAL_DIR=$(pwd)
cd - > /dev/null
mv "$STAGING_DIR/${DIST_NAME}.zip" "$DIST_DIR/"

# Create checksum
cd "$DIST_DIR"
shasum -a 256 "${DIST_NAME}.zip" > "${DIST_NAME}.sha256"
cd ..

# Clean up staging directory
rm -rf "$STAGING_DIR"

# Display results
echo ""
echo "✅ Distribution package created successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📁 Location: ${DIST_DIR}/${DIST_NAME}.zip"
echo "🔐 Checksum: ${DIST_DIR}/${DIST_NAME}.sha256"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Package details
PACKAGE_SIZE=$(ls -lh "${DIST_DIR}/${DIST_NAME}.zip" | awk '{print $5}')
FILE_COUNT=$(unzip -l "${DIST_DIR}/${DIST_NAME}.zip" | tail -1 | awk '{print $2}')

echo "📊 Package Details:"
echo "   Size: $PACKAGE_SIZE"
echo "   Files: $FILE_COUNT"
echo ""

echo "📝 Package Includes:"
echo "   ✓ CDK infrastructure code (app.py, cdk.json)"
echo "   ✓ Lambda functions with security features"
echo "   ✓ Interactive website with document upload"
echo "   ✓ Sample documents (3 files)"
echo "   ✓ Comprehensive test suite"
echo "   ✓ Deployment scripts (setup.sh, teardown.sh)"
echo "   ✓ Complete documentation (5 guides)"
echo "   ✓ Architecture diagrams and icons"
echo ""

echo "🔍 Quality Checks:"
echo "   ✓ Build artifacts removed"
echo "   ✓ Python cache files cleaned"
echo "   ✓ Deployment outputs excluded"
echo "   ✓ Scripts made executable"
echo "   ✓ Distribution README included"
echo ""

echo "📤 Next Steps:"
echo ""
echo "   1. Verify the package:"
echo "      shasum -c ${DIST_DIR}/${DIST_NAME}.sha256"
echo ""
echo "   2. Test in a clean environment:"
echo "      unzip ${DIST_DIR}/${DIST_NAME}.zip"
echo "      cd ${PROJECT_NAME}"
echo "      cat DISTRIBUTION_README.md"
echo ""
echo "   3. Share with instructors:"
echo "      - Upload to cloud storage (S3, Google Drive, etc.)"
echo "      - Share via email or learning management system"
echo "      - Include the .sha256 file for verification"
echo ""

echo "📝 Recipients Should Run:"
echo "   unzip ${DIST_NAME}.zip"
echo "   cd ${PROJECT_NAME}"
echo "   cat DISTRIBUTION_README.md"
echo "   ./scripts/setup.sh"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Distribution package ready for sharing!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
