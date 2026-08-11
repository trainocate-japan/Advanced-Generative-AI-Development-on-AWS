# Architecture Documentation

This document provides detailed information about the system architecture, component interactions, design decisions, and security considerations for the Amazon Bedrock Prompt Caching Demo.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Design Decisions](#design-decisions)
6. [Security Considerations](#security-considerations)
7. [Performance Considerations](#performance-considerations)
8. [Scalability](#scalability)
9. [Monitoring and Observability](#monitoring-and-observability)
10. [Disaster Recovery](#disaster-recovery)

## System Overview

The Prompt Caching Demo is a serverless web application built on AWS that demonstrates Amazon Bedrock's prompt caching capabilities. The system follows a three-tier architecture:

1. **Presentation Layer**: Static web interface served via CloudFront and S3
2. **Application Layer**: Lambda functions processing queries and invoking Bedrock
3. **Data Layer**: S3 storage for documents and Bedrock for AI inference

### Key Characteristics

- **Serverless**: No servers to manage, automatic scaling
- **Event-Driven**: Lambda functions triggered by API Gateway requests
- **Stateless**: No session state maintained on backend
- **Cost-Optimized**: Pay-per-use pricing model
- **Globally Distributed**: CloudFront CDN for low-latency access

## Architecture Diagram

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Student Browser                          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   HTML/CSS   │  │  JavaScript  │  │  LocalStorage        │  │
│  │   (Static)   │  │   (app.js)   │  │  (Query History)     │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Amazon CloudFront                           │
│                                                                   │
│  • Global CDN with edge locations                                │
│  • HTTPS/TLS 1.2+ enforcement                                   │
│  • Origin Access Identity (OAI) for S3                          │
│  • Cache policies for static assets                             │
│  • Error page routing for SPA                                   │
└───────────────┬─────────────────────────┬───────────────────────┘
                │                         │
                ▼                         ▼
    ┌───────────────────┐     ┌──────────────────────┐
    │   Amazon S3       │     │  Amazon API Gateway  │
    │  (Website Bucket) │     │    (REST API)        │
    │                   │     │                      │
    │  • index.html     │     │  • POST /query       │
    │  • styles.css     │     │  • GET /health       │
    │  • app.js         │     │  • CORS enabled      │
    │  • config.js      │     │  • Throttling: 100/s │
    │  • *.svg          │     └──────────┬───────────┘
    └───────────────────┘                │
                                         ▼
                              ┌──────────────────────┐
                              │   AWS Lambda         │
                              │  (Query Handler)     │
                              │                      │
                              │  • Python 3.12       │
                              │  • 1024 MB memory    │
                              │  • 60s timeout       │
                              │  • Input validation  │
                              │  • Rate limiting     │
                              └──────┬───────┬───────┘
                                     │       │
                    ┌────────────────┘       └────────────────┐
                    ▼                                         ▼
        ┌───────────────────┐                    ┌──────────────────────┐
        │   Amazon S3       │                    │  Amazon Bedrock      │
        │ (Document Bucket) │                    │  (Converse API)      │
        │                   │                    │                      │
        │  • aws-caf-for-   │                    │  • Nova Lite/Pro     │
        │    ai.txt         │                    │  • Claude models     │
        │  • Fallback       │                    │  • Prompt caching    │
        │    content        │                    │  • Cache checkpoints │
        └───────────────────┘                    └──────────────────────┘
```

### Deployment Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                    Instructor Workstation                         │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  setup.sh    │  │  AWS CDK     │  │  teardown.sh         │   │
│  │  (Deploy)    │  │  (IaC)       │  │  (Cleanup)           │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘   │
└─────────┼──────────────────┼──────────────────────────────────────┘
          │                  │
          │                  ▼
          │         ┌──────────────────┐
          │         │  AWS CDK Toolkit │
          │         │  (CloudFormation)│
          │         └────────┬─────────┘
          │                  │
          │                  ▼
          │    ┌─────────────────────────────────────┐
          │    │   CloudFormation Stack              │
          │    │   (PromptCachingDemoStack)          │
          │    │                                     │
          │    │  Resources:                         │
          │    │  • S3 Buckets (2)                  │
          │    │  • Lambda Functions (1)            │
          │    │  • API Gateway (1)                 │
          │    │  • CloudFront Distribution (1)     │
          │    │  • IAM Roles & Policies (2)        │
          │    │  • CloudWatch Log Groups (1)       │
          │    └─────────────────────────────────────┘
          │
          └──────► Upload documents and website files
```

## Component Details

### 1. Amazon CloudFront Distribution

**Purpose**: Global content delivery network for the web interface

**Configuration**:
- **Origin**: S3 website bucket with Origin Access Identity
- **Default Root Object**: index.html
- **Price Class**: PRICE_CLASS_ALL (global coverage)
- **TLS**: Minimum TLS 1.2
- **Caching**: Optimized for static content (HTML, CSS, JS, images)
- **Error Responses**: 
  - 403 → /index.html (for SPA routing)
  - 404 → /index.html (for SPA routing)

**Why CloudFront?**:
- Low-latency access from anywhere in the world
- HTTPS enforcement for security
- Reduced load on S3 origin
- Built-in DDoS protection

**Interactions**:
- Receives HTTPS requests from student browsers
- Fetches content from S3 website bucket
- Caches static assets at edge locations
- Routes API requests to API Gateway (if configured)

### 2. Amazon S3 Buckets

#### Website Bucket

**Purpose**: Hosts static web interface files

**Configuration**:
- **Encryption**: S3-managed keys (SSE-S3)
- **Public Access**: Blocked (accessed via CloudFront OAI only)
- **Versioning**: Disabled (not needed for demo)
- **Lifecycle**: Delete objects after 30 days
- **Removal Policy**: DESTROY (for easy cleanup)

**Contents**:
- index.html (main page structure)
- styles.css (styling)
- app.js (frontend logic)
- config.js (generated with API Gateway URL)
- architecture-diagram.svg (interactive diagram)
- kiro-icon.svg (branding)

#### Document Bucket

**Purpose**: Stores documents for prompt caching demonstrations

**Configuration**:
- **Encryption**: S3-managed keys (SSE-S3)
- **Public Access**: Blocked
- **Versioning**: Disabled
- **Lifecycle**: Delete objects after 30 days
- **Removal Policy**: DESTROY

**Contents**:
- aws-caf-for-ai.txt (primary document, ~3000 tokens)
- Fallback content (if primary document missing)

**Why S3?**:
- Durable storage (99.999999999% durability)
- Low cost for small files
- Easy integration with Lambda
- Automatic encryption at rest

### 3. Amazon API Gateway

**Purpose**: REST API for web interface to backend communication

**Configuration**:
- **Type**: REST API
- **Endpoints**:
  - `POST /query` - Submit question for processing
  - `GET /health` - Health check endpoint
- **CORS**: Enabled for CloudFront origin
- **Throttling**: 100 requests per second per IP
- **Authorization**: None (public demo)
- **Stage**: prod

**Request/Response Format**:

**POST /query**:
```json
Request:
{
  "question": "What are the key principles of AWS CAF for AI?",
  "model": "amazon.nova-lite-v1:0"
}

Response:
{
  "success": true,
  "baseline": { ... },
  "cache_write": { ... },
  "cache_hit": { ... },
  "metrics": { ... }
}
```

**GET /health**:
```json
Response:
{
  "status": "healthy",
  "timestamp": "2024-11-19T18:00:00Z"
}
```

**Why API Gateway?**:
- Managed service, no servers to maintain
- Built-in throttling and rate limiting
- Request/response transformation
- CloudWatch integration for monitoring
- CORS support for web applications

### 4. AWS Lambda Function (Query Handler)

**Purpose**: Processes student queries and orchestrates prompt caching demonstration

**Configuration**:
- **Runtime**: Python 3.12
- **Memory**: 1024 MB
- **Timeout**: 60 seconds
- **Environment Variables**:
  - `DOCUMENT_BUCKET`: Name of S3 bucket with documents
  - `PYTHON_SCRIPT_PATH`: Path to prompt caching script

**Execution Flow**:
1. Receive request from API Gateway
2. Validate and sanitize input
3. Load document from S3
4. Invoke Python script three times:
   - Baseline (no cache)
   - Cache write (with checkpoint)
   - Cache hit (reuse cache)
5. Parse metrics from each invocation
6. Calculate comparison metrics
7. Return structured response

**IAM Permissions**:
- S3: GetObject on document bucket
- Bedrock: InvokeModel for Converse API
- CloudWatch: CreateLogGroup, CreateLogStream, PutLogEvents

**Why Lambda?**:
- Serverless, automatic scaling
- Pay only for execution time
- Integrates seamlessly with API Gateway
- Built-in CloudWatch logging
- No infrastructure to manage

**Code Structure**:
```python
def lambda_handler(event, context):
    # 1. Parse and validate input
    # 2. Load document from S3
    # 3. Invoke baseline request
    # 4. Invoke cache write request
    # 5. Invoke cache hit request
    # 6. Calculate metrics
    # 7. Return response
```

### 5. Amazon Bedrock

**Purpose**: AI inference with prompt caching capabilities

**Models Supported**:
- Amazon Nova Lite (amazon.nova-lite-v1:0)
- Amazon Nova Pro (amazon.nova-pro-v1:0)
- Claude 3.5 Sonnet (anthropic.claude-3-5-sonnet-20241022-v2:0)
- Claude 3 Haiku (anthropic.claude-3-haiku-20240307-v1:0)

**Cache Behavior**:
- **Cache TTL**: 5 minutes
- **Minimum Tokens**: 1024 tokens (varies by model)
- **Cache Write Cost**: Premium pricing on cache write tokens (model-specific)
- **Cache Read Cost**: Reduced pricing on cache read tokens (model-specific)
- **Pricing Details**: See [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)

**API Calls**:
```python
# Baseline (no cache)
response = bedrock.converse(
    modelId=model_id,
    messages=[{
        "role": "user",
        "content": [{"text": document + "\n\n" + question}]
    }]
)

# Cache write (with checkpoint)
response = bedrock.converse(
    modelId=model_id,
    messages=[{
        "role": "user",
        "content": [
            {"text": document},
            {"cachePoint": {"type": "default"}},
            {"text": question}
        ]
    }]
)
```

**Why Bedrock?**:
- Managed AI service, no model hosting
- Built-in prompt caching support
- Multiple model options
- Pay-per-use pricing
- Enterprise security and compliance

### 6. AWS CloudWatch

**Purpose**: Logging and monitoring

**Configuration**:
- **Log Groups**: One per Lambda function
- **Retention**: 7 days (cost optimization)
- **Metrics**: Lambda invocations, errors, duration
- **Alarms**: (Optional) Can be configured for errors

**Logged Information**:
- Lambda execution logs
- API Gateway access logs
- Error messages and stack traces
- Performance metrics

**Why CloudWatch?**:
- Integrated with all AWS services
- Centralized logging
- Real-time monitoring
- Alerting capabilities

### 7. AWS IAM

**Purpose**: Access control and security

**Roles Created**:

#### Lambda Execution Role
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::document-bucket/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:*:*:model/*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

**Security Principles**:
- Least privilege access
- Resource-level permissions where possible
- No wildcard permissions except where required by service
- Separate roles for different functions

## Data Flow

### Query Processing Flow

```
1. Student submits question via web interface
   ↓
2. Browser sends POST request to API Gateway
   ↓
3. API Gateway validates request and invokes Lambda
   ↓
4. Lambda validates and sanitizes input
   ↓
5. Lambda loads document from S3
   ↓
6. Lambda invokes Python script (baseline)
   ├─→ Python script calls Bedrock API
   ├─→ Bedrock processes full document
   └─→ Returns metrics (input_tokens, output_tokens, response_time)
   ↓
7. Lambda invokes Python script (cache write)
   ├─→ Python script calls Bedrock API with cache checkpoint
   ├─→ Bedrock caches document content
   └─→ Returns metrics (cache_write_tokens)
   ↓
8. Lambda invokes Python script (cache hit)
   ├─→ Python script calls Bedrock API with same document
   ├─→ Bedrock reads from cache
   └─→ Returns metrics (cache_read_tokens, reduced input_tokens)
   ↓
9. Lambda calculates comparison metrics
   ├─→ Token reduction percentage
   ├─→ Latency improvement percentage
   └─→ Cache hit ratio
   ↓
10. Lambda returns structured response to API Gateway
    ↓
11. API Gateway returns response to browser
    ↓
12. Browser displays results with visualizations
    ↓
13. Browser saves query to localStorage history
```

### Deployment Flow

```
1. Instructor runs ./scripts/setup.sh
   ↓
2. Script validates prerequisites
   ├─→ AWS CLI installed
   ├─→ CDK installed
   ├─→ Python 3.12+ installed
   └─→ Node.js 18+ installed
   ↓
3. Script checks AWS credentials
   ├─→ Displays account ID
   └─→ Displays region
   ↓
4. Script bootstraps CDK (if needed)
   ↓
5. Script installs Python dependencies
   ↓
6. CDK synthesizes CloudFormation template
   ↓
7. CDK deploys stack
   ├─→ Creates S3 buckets
   ├─→ Creates Lambda function
   ├─→ Creates API Gateway
   ├─→ Creates CloudFront distribution
   ├─→ Creates IAM roles
   └─→ Creates CloudWatch log groups
   ↓
8. Script uploads document to S3
   ↓
9. Script generates config.js with API URL
   ↓
10. Script uploads website files to S3
    ↓
11. Script invalidates CloudFront cache
    ↓
12. Script verifies deployment
    ├─→ Lambda accessible
    ├─→ S3 buckets contain files
    ├─→ API Gateway health check responds
    ├─→ CloudFront distribution active
    └─→ Document meets token requirements
    ↓
13. Script displays CloudFront URL and resource IDs
```

### Teardown Flow

```
1. Instructor runs ./scripts/teardown.sh
   ↓
2. Script retrieves bucket names from stack outputs
   ↓
3. Script displays resources to be deleted
   ↓
4. Script prompts for confirmation
   ↓
5. User confirms (or --force flag used)
   ↓
6. Script empties S3 buckets
   ├─→ Deletes all objects
   ├─→ Deletes all versions
   └─→ Deletes all delete markers
   ↓
7. Script runs cdk destroy
   ├─→ Deletes CloudFormation stack
   ├─→ Deletes all resources
   └─→ Waits for completion
   ↓
8. Script verifies cleanup
   ├─→ S3 buckets deleted
   ├─→ Lambda functions deleted
   ├─→ API Gateway deleted
   └─→ CloudFormation stack deleted
   ↓
9. Script displays cleanup summary
```

## Design Decisions

### 1. Serverless Architecture

**Decision**: Use serverless services (Lambda, API Gateway, S3) instead of EC2 or containers

**Rationale**:
- No infrastructure to manage
- Automatic scaling
- Pay-per-use pricing (cost-effective for demos)
- Built-in high availability
- Faster deployment and teardown

**Trade-offs**:
- Cold start latency (mitigated with 1024 MB memory)
- Vendor lock-in to AWS
- Limited execution time (60 seconds sufficient for this use case)

### 2. Python Script Integration

**Decision**: Reuse existing Python script instead of rewriting in Lambda

**Rationale**:
- Maintains consistency with existing examples
- Preserves security utilities and best practices
- Reduces development time
- Students learn from production-quality code

**Trade-offs**:
- Subprocess overhead (minimal impact)
- Slightly larger deployment package
- More complex error handling

### 3. Three-Request Demonstration

**Decision**: Perform baseline, cache write, and cache hit requests for each query

**Rationale**:
- Shows complete caching lifecycle
- Demonstrates cost/performance trade-offs
- Provides clear before/after comparison
- Educational value outweighs additional cost

**Trade-offs**:
- Higher cost per query (3x Bedrock calls)
- Longer response time
- More complex implementation

### 4. CloudFront for Website Delivery

**Decision**: Use CloudFront instead of S3 website hosting

**Rationale**:
- HTTPS enforcement (S3 website hosting doesn't support HTTPS)
- Global low-latency access
- Built-in DDoS protection
- Professional appearance

**Trade-offs**:
- Slightly higher cost
- Longer deployment time (distribution creation)
- Cache invalidation needed for updates

### 5. No Authentication

**Decision**: Public demo without authentication

**Rationale**:
- Simplifies deployment and usage
- Appropriate for educational environment
- Rate limiting provides abuse protection
- Reduces complexity for students

**Trade-offs**:
- Anyone with URL can access
- Potential for abuse (mitigated by rate limiting)
- Not suitable for production use

### 6. Automated Deployment Scripts

**Decision**: Provide bash scripts instead of manual instructions

**Rationale**:
- Reduces deployment time from hours to minutes
- Eliminates human error
- Ensures consistency across deployments
- Lowers barrier to entry for instructors

**Trade-offs**:
- Requires bash environment
- Less flexibility for customization
- Hides some AWS concepts from students

### 7. Infrastructure as Code (CDK)

**Decision**: Use AWS CDK instead of manual console configuration

**Rationale**:
- Repeatable deployments
- Version control for infrastructure
- Easier to maintain and update
- Industry best practice

**Trade-offs**:
- Requires CDK knowledge
- Additional dependency
- Longer initial learning curve

### 8. Single Lambda Function

**Decision**: Use one Lambda function instead of multiple microservices

**Rationale**:
- Simpler architecture for demo purposes
- Reduced cold start impact
- Easier to understand for students
- Lower operational complexity

**Trade-offs**:
- Less modular
- Harder to scale individual components
- Larger deployment package

## Security Considerations

### 1. Input Validation and Sanitization

**Implementation**:
- Question length validation (1-500 characters)
- SQL injection prevention
- XSS payload detection and removal
- Model ID validation against whitelist

**Code Example**:
```python
def sanitize_input(question: str) -> str:
    # Remove SQL keywords
    sql_keywords = ['DROP', 'DELETE', 'INSERT', 'UPDATE', 'SELECT']
    for keyword in sql_keywords:
        question = question.replace(keyword, '')
    
    # Escape HTML
    question = html.escape(question)
    
    # Validate length
    if len(question) > 500:
        raise ValueError("Question too long")
    
    return question
```

**Why Important**:
- Prevents injection attacks
- Protects backend systems
- Ensures data integrity

### 2. Error Message Sanitization

**Implementation**:
- Remove file paths from error messages
- Remove credentials and tokens
- Remove internal IP addresses
- Provide generic error messages to users

**Code Example**:
```python
def sanitize_error(error: Exception) -> str:
    error_str = str(error)
    # Remove file paths
    error_str = re.sub(r'/[^\s]+', '[path]', error_str)
    # Remove IPs
    error_str = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '[ip]', error_str)
    return error_str
```

**Why Important**:
- Prevents information disclosure
- Protects system internals
- Reduces attack surface

### 3. Least Privilege IAM

**Implementation**:
- Lambda role has only required permissions
- Resource-level permissions where possible
- No wildcard permissions except where required

**Why Important**:
- Limits blast radius of compromised credentials
- Follows AWS security best practices
- Reduces risk of unauthorized access

### 4. Encryption

**Implementation**:
- S3 buckets use SSE-S3 encryption at rest
- All traffic uses HTTPS/TLS 1.2+
- No unencrypted data transmission

**Why Important**:
- Protects data confidentiality
- Meets compliance requirements
- Industry standard practice

### 5. Rate Limiting

**Implementation**:
- API Gateway: 100 requests per second per IP
- Lambda: 10 requests per minute per IP (application-level)
- Returns 429 Too Many Requests when exceeded

**Why Important**:
- Prevents abuse and DoS attacks
- Controls costs
- Ensures fair usage

### 6. S3 Bucket Security

**Implementation**:
- Block all public access
- Access via CloudFront OAI only
- Encryption at rest
- Lifecycle policies to prevent unbounded storage

**Why Important**:
- Prevents data leaks
- Reduces attack surface
- Controls costs

### 7. CloudWatch Logging

**Implementation**:
- All Lambda executions logged
- API Gateway access logs
- Error tracking and alerting
- 7-day retention (balance between visibility and cost)

**Why Important**:
- Security monitoring
- Incident response
- Debugging and troubleshooting

### 8. No Hardcoded Credentials

**Implementation**:
- All credentials from IAM roles
- Environment variables for configuration
- No secrets in code or version control

**Why Important**:
- Prevents credential leaks
- Follows security best practices
- Enables credential rotation

## Performance Considerations

### 1. Lambda Configuration

**Memory**: 1024 MB
- Provides sufficient CPU for document processing
- Reduces cold start time
- Balances cost and performance

**Timeout**: 60 seconds
- Allows time for three Bedrock API calls
- Prevents runaway executions
- Sufficient for typical queries

### 2. CloudFront Caching

**Static Assets**: Cached at edge locations
- Reduces latency for global users
- Reduces load on S3 origin
- Improves user experience

**Cache Policies**:
- HTML: Short TTL (5 minutes)
- CSS/JS: Longer TTL (1 hour)
- Images: Longest TTL (24 hours)

### 3. Bedrock Model Selection

**Default**: Amazon Nova Lite
- Cost-effective
- Fast response times
- Sufficient for demonstrations

**Alternatives**: Nova Pro, Claude models
- Higher performance
- Better quality responses
- Higher cost

### 4. Document Loading

**Strategy**: Load once per Lambda invocation
- Cached in Lambda memory for warm starts
- Reduces S3 API calls
- Improves response time

### 5. Parallel Processing

**Current**: Sequential Bedrock calls
- Simpler implementation
- Easier to understand for students
- Sufficient for demo purposes

**Future**: Could parallelize baseline and cache write
- Faster response time
- More complex implementation
- May confuse students

## Scalability

### Current Capacity

**Lambda**:
- Concurrent executions: 1000 (default account limit)
- Can handle 1000 simultaneous queries
- Sufficient for 100+ concurrent students

**API Gateway**:
- Throttling: 100 requests per second per IP
- Can handle 6000 requests per minute
- Sufficient for large classes

**Bedrock**:
- Subject to service quotas
- Default: 10 TPS per model
- May need quota increase for large deployments

### Scaling Strategies

**Horizontal Scaling**:
- Lambda auto-scales automatically
- No configuration needed
- Pay only for what you use

**Vertical Scaling**:
- Increase Lambda memory if needed
- Adjust API Gateway throttling limits
- Request Bedrock quota increases

**Geographic Scaling**:
- CloudFront provides global distribution
- Deploy to multiple regions if needed
- Use Route 53 for multi-region routing

### Bottlenecks

**Potential Bottlenecks**:
1. Bedrock API quotas (most likely)
2. Lambda concurrent execution limit
3. API Gateway throttling

**Mitigation**:
- Request quota increases proactively
- Monitor CloudWatch metrics
- Implement queuing if needed

## Monitoring and Observability

### Key Metrics

**Lambda**:
- Invocations
- Errors
- Duration
- Throttles
- Concurrent executions

**API Gateway**:
- Request count
- 4xx errors
- 5xx errors
- Latency

**Bedrock**:
- Model invocations
- Throttles
- Errors
- Token usage

**CloudFront**:
- Requests
- Bytes downloaded
- Cache hit ratio
- Error rate

### Logging

**Lambda Logs**:
- Execution start/end
- Input validation results
- S3 document loading
- Bedrock API calls
- Error messages

**API Gateway Logs**:
- Request/response
- Client IP
- User agent
- Response time

### Alerting

**Recommended Alarms**:
- Lambda error rate > 5%
- API Gateway 5xx errors > 1%
- Bedrock throttling > 0
- CloudFront error rate > 5%

### Dashboards

**CloudWatch Dashboard**:
- Lambda invocations and errors
- API Gateway requests and latency
- Bedrock usage and costs
- CloudFront cache hit ratio

## Disaster Recovery

### Backup Strategy

**S3 Buckets**:
- Versioning disabled (not needed for demo)
- Objects can be re-uploaded from source
- No backup needed

**Lambda Code**:
- Stored in version control (Git)
- Deployment package can be rebuilt
- No backup needed

**Infrastructure**:
- Defined in CDK code
- Can be redeployed from code
- No backup needed

### Recovery Procedures

**Complete Failure**:
1. Run teardown script to clean up
2. Run setup script to redeploy
3. Verify deployment
4. Resume operations

**Partial Failure**:
1. Identify failed component via CloudWatch
2. Fix issue (code, permissions, quotas)
3. Redeploy affected component
4. Verify fix

**Data Loss**:
- Document can be re-uploaded
- Website files can be re-uploaded
- No persistent user data to lose

### RTO and RPO

**Recovery Time Objective (RTO)**: 15 minutes
- Time to run setup script and verify

**Recovery Point Objective (RPO)**: 0 minutes
- No persistent data to lose
- All state in code and configuration

## Conclusion

This architecture provides a robust, scalable, and cost-effective platform for demonstrating Amazon Bedrock prompt caching. The serverless design ensures automatic scaling and minimal operational overhead, while the security measures protect against common threats. The system is designed for educational purposes, balancing simplicity with production-quality practices.

For questions or suggestions about this architecture, please provide feedback through your organization's channels.

---

**Last Updated**: November 2024  
**Version**: 1.0
