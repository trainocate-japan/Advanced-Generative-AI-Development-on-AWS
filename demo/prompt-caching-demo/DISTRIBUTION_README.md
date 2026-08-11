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
