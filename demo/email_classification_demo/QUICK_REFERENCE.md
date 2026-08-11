# Quick Reference Card

## One-Page Cheat Sheet for Instructors

### Deploy (First Time)
```bash
cdk bootstrap                    # One-time AWS setup
./scripts/setup.sh              # Deploy everything
```

### Deploy (Subsequent)
```bash
cdk deploy                      # Update existing stack
```

### Cleanup
```bash
./scripts/teardown.sh           # Remove all resources
```

### Test Upload
```bash
python3 test_api_upload.py      # Test API endpoint
```

### View Logs
```bash
# Email Processor
aws logs tail /aws/lambda/EmailClassification-EmailProcessor --follow

# Classifier
aws logs tail /aws/lambda/EmailClassification-InvoiceClassifier --follow
```

### Check Stack Status
```bash
aws cloudformation describe-stacks --stack-name EmailClassificationStack
```

### Get CloudFront URL
```bash
aws cloudformation describe-stacks \
  --stack-name EmailClassificationStack \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontURL`].OutputValue' \
  --output text
```

### Common Issues

| Problem | Solution |
|---------|----------|
| Upload fails | Check API Gateway CORS, verify URL in config.js |
| Bedrock access denied | Enable Nova Lite in Bedrock console |
| Classification stuck | Check Step Functions execution, verify BDA output |
| CloudFront 403 | Wait 15 min for distribution, check OAI |

### Sample EML Files

| File | Department | Use Case |
|------|-----------|----------|
| email_01_finance.eml | Finance | Basic demo |
| email_02_it.eml | IT | Software invoice |
| email_03_marketing.eml | Marketing | Campaign invoice |
| email_06_unknown.eml | Finance (fallback) | Ambiguous content |

### Architecture Components

```
User → CloudFront → S3 (Website)
User → API Gateway → Lambda (Upload) → S3 (Inbox)
S3 → Lambda (Processor) → Bedrock BDA
BDA → EventBridge → Step Functions → Lambda (Classifier) → S3 (Dest)
```

### Key Files

| File | Purpose |
|------|---------|
| `app.py` | CDK entry point |
| `email_classification_stack.py` | Infrastructure definition |
| `lambda_functions/invoice_classifier.py` | Bedrock integration |
| `config/department_config.json` | Department definitions |
| `website/index.html` | Upload interface |

### Cost Estimate

- 100 emails: < $1
- Per student/month: < $1
- Idle cost: ~$0 (serverless)

### Prerequisites

- AWS account with admin access
- AWS CLI configured
- Node.js 18+
- Python 3.12+
- CDK CLI: `npm install -g aws-cdk`

### Support Resources

- Full README: `README.md`
- Instructor guide: `INSTRUCTOR_GUIDE.md`
- AWS CDK docs: https://docs.aws.amazon.com/cdk/
- Bedrock docs: https://docs.aws.amazon.com/bedrock/
