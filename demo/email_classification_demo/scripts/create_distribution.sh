#!/bin/bash

# Create distribution package for instructors
# This script packages the project for easy sharing with timestamp

set -e

echo "📦 Creating distribution package..."

# Get project name and version with timestamp
PROJECT_NAME="email-classification-demo"
VERSION=$(date +%Y%m%d-%H%M%S)
DIST_NAME="${PROJECT_NAME}-${VERSION}"
DIST_DIR="distribution"

# Create distribution directory
mkdir -p "$DIST_DIR"

# Create archive excluding unnecessary files
echo "🗜️  Creating ZIP archive..."
zip -r "${DIST_DIR}/${DIST_NAME}.zip" \
  app.py \
  cdk.json \
  requirements.txt \
  README.md \
  INSTRUCTOR_GUIDE.md \
  QUICK_REFERENCE.md \
  email_classification/ \
  lambda_functions/ \
  website/ \
  config/ \
  incoming/ \
  scripts/ \
  -x "*.pyc" "*.pyo" "*__pycache__*" "*cdk.out*" "*.DS_Store" "*node_modules*" 2>&1 | tail -20

# Create checksum
cd "$DIST_DIR"
shasum -a 256 "${DIST_NAME}.zip" > "${DIST_NAME}.sha256"
cd ..

# Display results
echo ""
echo "✅ Distribution package created!"
echo ""
echo "📁 Location: ${DIST_DIR}/${DIST_NAME}.zip"
echo "🔐 Checksum: ${DIST_DIR}/${DIST_NAME}.sha256"
echo ""
echo "📊 Package details:"
ls -lh "${DIST_DIR}/${DIST_NAME}.zip" | awk '{print "   Size: " $5}'
unzip -l "${DIST_DIR}/${DIST_NAME}.zip" | tail -1 | awk '{print "   Files: " $2}'
echo ""
echo "📝 Package includes:"
echo "   ✓ CDK infrastructure code"
echo "   ✓ Lambda functions (4 functions)"
echo "   ✓ Website with educational panel"
echo "   ✓ Kiro badge and icon"
echo "   ✓ Deployment scripts"
echo "   ✓ Sample EML test files (10 files)"
echo "   ✓ Complete documentation"
echo ""
echo "📤 Next steps:"
echo "   1. Test the package in a clean environment"
echo "   2. Upload to cloud storage or repository"
echo "   3. Share with instructors and students"
echo ""
echo "📝 Recipients should run:"
echo "   unzip ${DIST_NAME}.zip"
echo "   cd ${PROJECT_NAME}"
echo "   cat README.md"
echo "   ./scripts/setup.sh"
