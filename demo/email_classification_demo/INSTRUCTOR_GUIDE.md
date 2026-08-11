# Instructor Guide - Email Classification Demo

## Quick Start for Instructors

This guide helps you deploy and demonstrate the Email Classification system to students.

### Prerequisites Checklist

Before class, ensure you have:
- [ ] AWS account with admin access
- [ ] AWS CLI configured (`aws configure`)
- [ ] Node.js 18+ installed (`node --version`)
- [ ] Python 3.12+ installed (`python3 --version`)
- [ ] AWS CDK installed (`npm install -g aws-cdk`)
- [ ] Bedrock model access enabled (Amazon Nova Lite)

### Pre-Class Setup (15 minutes)

```bash
# 1. Clone and install
git clone <your-repo-url>
cd email-classification-cdk-migration
pip3 install -r requirements.txt

# 2. Bootstrap CDK (first time only)
cdk bootstrap

# 3. Deploy the stack
chmod +x scripts/setup.sh
./scripts/setup.sh

# 4. Save the CloudFront URL for class
```

### Demo Flow (30-45 minutes)

#### Part 1: Architecture Overview (10 min)
- Open the CloudFront URL in browser
- Show the interactive architecture diagram
- Explain event-driven serverless pattern
- Highlight AI/ML integration with Bedrock

#### Part 2: Live Upload Demo (10 min)
- Drag and drop `incoming/email_01_finance.eml`
- Watch real-time processing status
- Show classification result
- Click "Finance" tab to view organized email

#### Part 3: Behind the Scenes - AWS Console Deep Dive (20 min)

**A. Bedrock Data Automation (BDA) - The Star of the Show (8 min)**

This is the key learning moment - show students how BDA extracts structured data from PDFs:

1. **Navigate to Bedrock Console**
   - AWS Console → Amazon Bedrock
   - Left sidebar → "Data Automation" (under Orchestration)
   - Show the BDA project: `invoice-processing`

2. **Explain BDA Concepts**
   - "BDA is purpose-built for document processing - invoices, forms, receipts"
   - "It extracts text, tables, key-value pairs automatically"
   - "No ML training required - it just works out of the box"

3. **Show a BDA Job Execution**
   - Click on "Data automation projects"
   - Select `invoice-processing` project
   - Click "Jobs" tab to see recent invocations
   - Select the most recent job (from your demo upload)
   - Show job details:
     - Input document (PDF from S3)
     - Processing status (COMPLETED)
     - Output location in S3
     - Processing time (~30-60 seconds)

4. **View BDA Output in S3**
   - Navigate to S3 Console
   - Open inbox bucket → `bda-output/` folder
   - Find the output JSON file (named by invocation ID)
   - Download and open in text editor
   - **Key teaching point:** Show the structured JSON with:
     - Extracted text from PDF
     - Document metadata
     - Confidence scores
     - Bounding boxes (where text was found)

5. **Explain the Architecture Decision**
   - "We use EventBridge to detect BDA completion"
   - "Step Functions polls for the output file"
   - **Production Note:** "In a real production system, you'd use SQS instead of polling"
   - "SQS provides better decoupling and handles high volumes efficiently"
   - "For this demo, Step Functions polling is simpler to understand"

**B. Step Functions Orchestration (5 min)**
- Open AWS Console → Step Functions
- Show the state machine: `EmailClassificationWorkflow`
- Click on a recent execution
- Walk through the visual workflow:
  - Wait state (30 seconds)
  - Check for BDA output
  - Loop if not ready (max 10 attempts)
  - Invoke classifier when ready
- Highlight: "This is event-driven orchestration - no servers waiting"

**C. Lambda Functions and Logs (4 min)**
- Open CloudWatch Logs
- Show Email Processor logs in real-time
- Point out structured logging (JSON format)
- Show Classifier logs with Bedrock API calls
- Demonstrate log filtering for errors

**D. S3 Organization (3 min)**
- Navigate to S3 buckets to show file organization
- Show the three-bucket architecture:
  - Inbox: Raw uploads and processing artifacts
  - Destination: Organized by department
  - Website: Static hosting
- Open a department folder to show classified emails

#### Part 4: Code Walkthrough (10 min)
- Open `email_classification_stack.py` - show CDK infrastructure
- Open `lambda_functions/invoice_classifier.py` - show Bedrock integration
- Highlight error handling and fallback logic
- Discuss security best practices (IAM, encryption)

### Teaching Points

**Key Concepts to Emphasize:**
1. **Bedrock Data Automation (BDA)** - Purpose-built for document processing, no ML training needed
2. **Event-Driven Architecture** - EventBridge detects BDA completion, triggers next step
3. **Infrastructure as Code** - CDK eliminates manual console clicking, ensures reproducibility
4. **Managed Services** - No servers to manage, automatic scaling
5. **Production Patterns** - Demo uses polling for simplicity, production would use SQS for better decoupling
6. **Observability** - CloudWatch logs and metrics built-in from day one

**Common Student Questions:**

Q: "What exactly does BDA do that I couldn't do with regular OCR?"
A: BDA understands document structure - it extracts tables, key-value pairs, and relationships. Regular OCR just gives you raw text. BDA knows an invoice total is different from a line item.

Q: "Why use Step Functions to poll instead of waiting in Lambda?"
A: Lambda has a 15-minute timeout. BDA can take 30-60 seconds. Step Functions can wait hours if needed without consuming resources. In production, you'd use SQS with EventBridge for true event-driven processing.

Q: "How would SQS improve this architecture?"
A: Instead of polling, BDA completion would send a message to SQS. A Lambda would process the queue. This decouples components, handles backpressure, and scales better under load. For this demo, Step Functions polling is simpler to understand.

Q: "Why use CDK instead of CloudFormation?"
A: Type safety catches errors before deployment, reusable constructs reduce boilerplate, and Python is more familiar than YAML/JSON.

Q: "How much does this cost to run?"
A: ~$1 for 100 test emails. BDA charges per document (~$0.01), Bedrock Nova Lite is cheap (~$0.0008 per 1K tokens). Lambda and S3 are negligible.

Q: "Can I use a different AI model?"
A: Yes, change `BEDROCK_MODEL_ID` in the stack (Nova Pro, Claude, etc.). Nova Lite is fast and cheap for demos.

Q: "What if Bedrock is down?"
A: The classifier has fallback logic using keyword matching (see `invoice_classifier.py`). Always build fallbacks for AI services.

Q: "Can BDA process other document types?"
A: Yes! BDA handles invoices, receipts, forms, contracts, medical records, etc. It's trained on diverse document types.

### Post-Class Cleanup

```bash
# Remove all resources to avoid charges
./scripts/teardown.sh
```

### AWS Console Navigation Guide

**Finding Bedrock Data Automation:**
1. AWS Console → Search "Bedrock" in top search bar
2. Click "Amazon Bedrock"
3. Left sidebar → Scroll to "Orchestration" section
4. Click "Data Automation"
5. You'll see "Data automation projects" - click to view projects
6. Select `invoice-processing` project
7. Click "Jobs" tab to see all BDA invocations

**What to Show Students in BDA Console:**
- Project configuration (input/output S3 locations)
- Job history with timestamps
- Individual job details (input document, status, duration)
- Output S3 path for each job
- Error logs if any jobs failed

**Comparing BDA Output to Input:**
1. Download the original PDF from S3 (`attachments/` folder)
2. Download the BDA output JSON from S3 (`bda-output/` folder)
3. Open both side-by-side
4. Show how BDA extracted text, tables, and structure
5. Point out confidence scores and bounding boxes

**Production Architecture Discussion:**
- Current: EventBridge → Step Functions (polling) → Lambda
- Production: EventBridge → SQS → Lambda (event-driven)
- Why SQS? Decoupling, backpressure handling, dead-letter queues, better scaling
- When to use polling? Simple demos, low volume, learning purposes
- When to use SQS? Production, high volume, need for retry logic

### Troubleshooting During Class

**Issue: Upload fails**
- Check API Gateway URL in browser console
- Verify CORS is enabled (should be automatic)

**Issue: Classification stuck**
- Check Step Functions execution in AWS Console
- Verify Bedrock model access is granted

**Issue: CloudFront URL not working**
- Wait 10-15 minutes for distribution to deploy
- Check distribution status in CloudFront console

### Customization Ideas for Assignments

1. **Add a new department**: Edit `config/department_config.json`
2. **Change classification logic**: Modify `invoice_classifier.py`
3. **Add email validation**: Enhance `upload_handler.py`
4. **Create custom metrics**: Add CloudWatch metrics to Lambdas
5. **Implement user authentication**: Add Cognito to API Gateway
6. **Replace Step Functions polling with SQS**: Refactor to use EventBridge → SQS → Lambda pattern (production-ready)
7. **Add BDA output analysis**: Parse BDA JSON to extract specific invoice fields (total, vendor, date)
8. **Multi-document support**: Handle emails with multiple PDF attachments

### BDA Demo Script (Detailed Walkthrough)

Use this script when demonstrating BDA in the AWS Console:

**Setup (Before Class):**
```bash
# Upload a test email to trigger BDA
# Use email_01_finance.eml - it has a clear invoice PDF
```

**During Demo:**

1. **"Let's see what happened behind the scenes with Bedrock Data Automation"**
   - Open AWS Console
   - Navigate to Bedrock → Data Automation

2. **"BDA is AWS's managed service for intelligent document processing"**
   - Show the `invoice-processing` project
   - Explain: "This project is configured to process invoice PDFs"
   - Point out: Input bucket, output bucket, profile settings

3. **"Let's look at the job that just processed our invoice"**
   - Click "Jobs" tab
   - Sort by most recent
   - Click on the latest job
   - Show job details:
     - Status: COMPLETED
     - Duration: ~45 seconds
     - Input: S3 path to PDF
     - Output: S3 path to JSON

4. **"Now let's see what BDA extracted from the PDF"**
   - Open S3 in new tab
   - Navigate to inbox bucket → `bda-output/` folder
   - Download the JSON file
   - Open in text editor or JSON viewer
   - **Key points to highlight:**
     - Full text extraction
     - Document structure (headers, body, footer)
     - Confidence scores (how sure BDA is)
     - Bounding boxes (where on the page)
     - Metadata (page count, document type)

5. **"Compare this to the original PDF"**
   - Download PDF from `attachments/` folder
   - Open side-by-side with JSON
   - Show how BDA captured:
     - Vendor name
     - Invoice number
     - Line items
     - Total amount
     - Dates

6. **"This structured data feeds into our classifier"**
   - Explain: "The classifier Lambda reads this JSON"
   - "It sends the extracted text to Bedrock Converse API"
   - "Bedrock determines which department should handle this invoice"

7. **"In production, you'd use SQS instead of polling"**
   - Draw on whiteboard:
     ```
     Current:  BDA → EventBridge → Step Functions (polls S3) → Lambda
     Production: BDA → EventBridge → SQS → Lambda (event-driven)
     ```
   - Explain benefits: "SQS provides better decoupling, handles spikes, supports dead-letter queues"
   - "For this demo, Step Functions is simpler to understand and visualize"

**Questions to Ask Students:**
- "What other document types could BDA process?" (receipts, forms, contracts)
- "Why is structured output better than raw text?" (easier to parse, query, validate)
- "What would happen if BDA fails?" (check error handling in Lambda logs)
- "How would you handle 1000 invoices per hour?" (SQS, parallel processing, batch operations)

### Sample Assignment

**Assignment: Add "Legal" Department**

Students should:
1. Update `config/department_config.json` to add Legal department
2. Upload config to S3
3. Test with a custom EML file containing legal keywords
4. Verify email appears in Legal department view
5. Document the changes in a README

Expected time: 30 minutes
Difficulty: Beginner

**Assignment: Replace Polling with SQS (Advanced)**

Students should:
1. Create an SQS queue in CDK
2. Add EventBridge rule to send BDA completion events to SQS
3. Replace Step Functions with Lambda triggered by SQS
4. Add dead-letter queue for failed messages
5. Test with multiple concurrent uploads
6. Compare performance and reliability to polling approach

Expected time: 2-3 hours
Difficulty: Advanced
Learning outcomes: Production-ready event-driven architecture, SQS patterns, error handling

### Additional Resources for Students

- AWS CDK Workshop: https://cdkworkshop.com/
- Bedrock Documentation: https://docs.aws.amazon.com/bedrock/
- Serverless Patterns: https://serverlessland.com/patterns

### Cost Management

**Per-student costs** (if each deploys their own):
- S3: < $0.10/month
- Lambda: Free tier (1M requests)
- Bedrock: ~$0.50 for 50 test emails
- Total: < $1/student/month

**Recommendation**: Use a single instructor account for demos, have students work with code locally and deploy to a shared sandbox account.

### Support

For issues during class:
1. Check CloudWatch logs first
2. Review the Troubleshooting section in README.md
3. Use `cdk diff` to see what changed
4. Worst case: `cdk destroy` and redeploy

