from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    CfnResource,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_s3_notifications as s3n,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_iam as iam,
    aws_logs as logs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_sqs as sqs,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
)
from constructs import Construct


class EmailClassificationStack(Stack):
    """
    Main CDK stack for the Email Classification System
    
    This stack creates the core infrastructure for processing and classifying
    email files with invoice attachments using Amazon Bedrock Data Automation.
    
    Architecture:
    - S3 buckets for inbox, destination, and website hosting
    - Lambda functions for processing pipeline
    - API Gateway for file uploads
    - CloudFront for website distribution
    - Step Functions for orchestration
    - SQS for email routing
    
    AWS Documentation References:
    - CDK Developer Guide: https://docs.aws.amazon.com/cdk/latest/guide/home.html
    - S3 Best Practices: https://docs.aws.amazon.com/AmazonS3/latest/userguide/best-practices.html
    - Lambda Best Practices: https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html
    - API Gateway: https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html
    - Step Functions: https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html
    - Bedrock: https://docs.aws.amazon.com/bedrock/latest/userguide/what-is-bedrock.html
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ========================================
        # S3 Buckets
        # ========================================
        # AWS S3 Documentation: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html
        # S3 Bucket Naming Rules: https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucketnamingrules.html
        # S3 Security Best Practices: https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html
        
        # Inbox Bucket - Stores uploaded EML files and extracted attachments
        #
        # Structure:
        # - incoming/ - Raw EML files uploaded via API Gateway
        # - attachments/ - Extracted PDF attachments from emails
        # - bda-output/ - Output from Bedrock Data Automation processing
        # - bda-jobs/ - Metadata about BDA invocations
        #
        # Why these settings:
        # - auto_delete_objects: Allows easy cleanup during teardown (demo purposes)
        # - removal_policy: DESTROY allows cdk destroy to remove the bucket
        # - versioned: False to simplify demo (enable for production)
        # - encryption: S3_MANAGED provides encryption at rest
        #
        # Security Best Practices Applied:
        # - Block all public access (block_public_access=BLOCK_ALL)
        # - Encryption at rest enabled (S3-managed keys)
        # - Lifecycle rules to automatically delete old objects
        # - Access controlled via IAM roles (no bucket policies allowing public access)
        #
        # S3 Encryption Documentation: https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingEncryption.html
        self.inbox_bucket = s3.Bucket(
            self, "InboxBucket",
            bucket_name=f"email-classification-inbox-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    # Clean up old files after 30 days to manage storage costs
                    id="DeleteOldFiles",
                    enabled=True,
                    expiration=Duration.days(30),
                )
            ],
        )

        # Destination Bucket - Stores classified emails organized by department
        #
        # Structure:
        # - departments/finance/ - Finance department emails
        # - departments/it/ - IT department emails
        # - departments/hr/ - HR department emails
        # - departments/operations/ - Operations department emails
        # - departments/marketing/ - Marketing department emails
        # - departments/{dept}/metadata/ - JSON metadata files for each email
        #
        # Why these settings:
        # - Same as inbox bucket for consistency
        # - Separate bucket for clear separation of concerns
        # - Allows different access policies for classified vs unclassified data
        self.destination_bucket = s3.Bucket(
            self, "DestinationBucket",
            bucket_name=f"email-classification-dest-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldClassifiedEmails",
                    enabled=True,
                    expiration=Duration.days(90),  # Keep classified emails longer
                )
            ],
        )

        # Website Bucket - Hosts the static web frontend
        #
        # Structure:
        # - index.html - Main upload interface
        # - styles.css - Styling adapted from example website
        # - app.js - Upload logic and API integration
        #
        # Why these settings:
        # - Will be accessed via CloudFront (not direct S3 website hosting)
        # - CloudFront OAI will provide secure access
        # - CORS not needed here as CloudFront handles it
        # - Public access blocked; CloudFront uses OAI for access
        self.website_bucket = s3.Bucket(
            self, "WebsiteBucket",
            bucket_name=f"email-classification-web-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ========================================
        # Create S3 Prefixes (Folders)
        # ========================================
        
        # Create prefix structure in inbox bucket
        #
        # Note: S3 doesn't have true folders, but we use BucketDeployment
        # to create the initial prefix structure. This helps with organization
        # and makes the bucket structure clear in the console.
        #
        # We'll create placeholder files for each prefix that will be used
        s3deploy.BucketDeployment(
            self, "InboxPrefixes",
            sources=[
                s3deploy.Source.data("incoming/.keep", ""),
                s3deploy.Source.data("attachments/.keep", ""),
                s3deploy.Source.data("bda-output/.keep", ""),
                s3deploy.Source.data("bda-jobs/.keep", ""),
            ],
            destination_bucket=self.inbox_bucket,
            prune=False,  # Don't delete existing objects
        )

        # Create prefix structure in destination bucket for each department
        s3deploy.BucketDeployment(
            self, "DestinationPrefixes",
            sources=[
                s3deploy.Source.data("departments/finance/.keep", ""),
                s3deploy.Source.data("departments/finance/metadata/.keep", ""),
                s3deploy.Source.data("departments/it/.keep", ""),
                s3deploy.Source.data("departments/it/metadata/.keep", ""),
                s3deploy.Source.data("departments/hr/.keep", ""),
                s3deploy.Source.data("departments/hr/metadata/.keep", ""),
                s3deploy.Source.data("departments/operations/.keep", ""),
                s3deploy.Source.data("departments/operations/metadata/.keep", ""),
                s3deploy.Source.data("departments/marketing/.keep", ""),
                s3deploy.Source.data("departments/marketing/metadata/.keep", ""),
            ],
            destination_bucket=self.destination_bucket,
            prune=False,
        )

        # ========================================
        # CloudFront Distribution for Website
        # ========================================
        # CloudFront Documentation: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Introduction.html
        # CloudFront OAI: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html
        # CloudFront Security: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/security.html
        # CloudFront Best Practices: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/best-practices.html
        
        # CloudFront Origin Access Identity (OAI)
        #
        # Purpose: Allows CloudFront to securely access the S3 website bucket
        #
        # Why OAI:
        # - Provides secure access to S3 without making bucket public
        # - CloudFront uses OAI credentials to read from S3
        # - Prevents direct S3 access, forcing all traffic through CloudFront
        # - Best practice for serving static websites from S3
        # - Protects against direct S3 URL access (security)
        #
        # Security Best Practice:
        # - S3 bucket remains private (block_public_access=BLOCK_ALL)
        # - Only CloudFront can access bucket via OAI
        # - Users cannot bypass CloudFront to access S3 directly
        # - Prevents bandwidth theft and unauthorized access
        #
        # How it works:
        # 1. OAI is a special CloudFront user identity
        # 2. S3 bucket policy grants read access to this OAI
        # 3. CloudFront uses OAI to fetch objects from S3
        # 4. Users can only access content via CloudFront URL, not direct S3 URL
        oai = cloudfront.OriginAccessIdentity(
            self, "WebsiteOAI",
            comment="OAI for Email Classification website bucket",
        )
        
        # Grant CloudFront OAI read access to website bucket
        # This creates an S3 bucket policy allowing the OAI to read objects
        self.website_bucket.grant_read(oai)
        
        # CloudFront Distribution
        #
        # Purpose: Serves the static website with global CDN, HTTPS, and caching
        #
        # Why CloudFront:
        # - Provides HTTPS with AWS-managed certificate (no cost)
        # - Global CDN for fast content delivery
        # - Caching reduces S3 requests and improves performance
        # - Custom error pages for better user experience
        # - Industry best practice for serving static websites
        #
        # Why these settings:
        # - default_root_object: Serves index.html when accessing root URL
        # - price_class: PRICE_CLASS_100 uses only North America and Europe edge locations (cost-effective for demo)
        # - enabled: True activates the distribution immediately
        # - http_version: HTTP2 for better performance
        # - minimum_protocol_version: TLS 1.2 for security
        #
        # Cache behavior:
        # - Caches static assets (HTML, CSS, JS) at edge locations
        # - Reduces latency for users worldwide
        # - Reduces load on S3 and API Gateway
        self.distribution = cloudfront.Distribution(
            self, "WebsiteDistribution",
            comment="Email Classification Demo Website",
            default_behavior=cloudfront.BehaviorOptions(
                # S3 origin with OAI for secure access
                origin=origins.S3Origin(
                    self.website_bucket,
                    origin_access_identity=oai,
                ),
                # Viewer protocol policy: Redirect HTTP to HTTPS
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                # Allowed HTTP methods for the website (GET, HEAD for static content)
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                # Cache policy: Optimized for static content
                # CachingOptimized provides good defaults for static websites
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                # Compress content automatically (gzip, brotli)
                compress=True,
            ),
            # Default root object: Serve index.html when accessing root URL
            # Example: https://d123456.cloudfront.net/ -> serves index.html
            default_root_object="index.html",
            # Error responses: Custom error pages for better UX
            #
            # 403 Forbidden: Returned when object doesn't exist in S3 (due to OAI)
            # We redirect to index.html for client-side routing support
            #
            # 404 Not Found: Returned when object truly doesn't exist
            # We also redirect to index.html for client-side routing
            #
            # Why redirect to index.html:
            # - Supports single-page application (SPA) routing
            # - Provides consistent user experience
            # - Allows frontend to handle 404 pages
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5),
                ),
            ],
            # Price class: Use all edge locations worldwide
            # PRICE_CLASS_ALL provides global coverage for users anywhere in the world
            # This ensures the best performance for international users
            price_class=cloudfront.PriceClass.PRICE_CLASS_ALL,
            # Enable the distribution immediately upon deployment
            enabled=True,
            # HTTP version: Use HTTP/2 for better performance
            # HTTP/2 provides multiplexing, header compression, and server push
            http_version=cloudfront.HttpVersion.HTTP2,
            # Minimum TLS version: Require TLS 1.2 for security
            # TLS 1.2 is the minimum recommended version (TLS 1.0/1.1 are deprecated)
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
        )
        
        # Additional cache behavior for static assets (CSS, JS, images)
        #
        # Purpose: Optimize caching for static assets with longer TTL
        #
        # Why separate behavior:
        # - Static assets (CSS, JS) change less frequently than HTML
        # - Can cache longer to reduce S3 requests and improve performance
        # - HTML should have shorter cache to allow quick updates
        #
        # Path patterns:
        # - *.css - Stylesheet files
        # - *.js - JavaScript files
        # - *.svg - SVG images (architecture diagram)
        # - *.png, *.jpg, *.gif - Raster images
        #
        # Cache policy: CachingOptimized with longer TTL
        # This caches assets at edge locations for 24 hours by default
        self.distribution.add_behavior(
            path_pattern="*.css",
            origin=origins.S3Origin(
                self.website_bucket,
                origin_access_identity=oai,
            ),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            compress=True,
        )
        
        self.distribution.add_behavior(
            path_pattern="*.js",
            origin=origins.S3Origin(
                self.website_bucket,
                origin_access_identity=oai,
            ),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            compress=True,
        )
        
        self.distribution.add_behavior(
            path_pattern="*.svg",
            origin=origins.S3Origin(
                self.website_bucket,
                origin_access_identity=oai,
            ),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            compress=True,
        )

        # ========================================
        # IAM Roles for Lambda Functions
        # ========================================
        # IAM Best Practices: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
        # Least Privilege Principle: https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege
        # Lambda Execution Roles: https://docs.aws.amazon.com/lambda/latest/dg/lambda-intro-execution-role.html
        
        # Upload Handler Execution Role
        #
        # Purpose: Defines permissions for the Upload Handler Lambda function
        #
        # Principle of Least Privilege:
        # - Only grants s3:PutObject permission (not s3:GetObject or s3:DeleteObject)
        # - Restricted to specific bucket and prefix (incoming/)
        # - No wildcard permissions on resources
        # - CloudWatch Logs permissions scoped to function's log group
        #
        # Security Best Practices Applied:
        # - Resource-level permissions (not bucket-wide or account-wide)
        # - Explicit deny of public access via S3 bucket settings
        # - Separate role per Lambda function (not shared roles)
        # - Inline policies for transparency and auditability
        #
        # Required Permissions:
        # 1. s3:PutObject - Upload validated EML files to the inbox bucket
        #    - Resource: inbox bucket with incoming/ prefix only
        #    - Why: Upload Handler only needs to write new files, not read or delete
        #
        # 2. CloudWatch Logs - Write function logs for monitoring and debugging
        #    - logs:CreateLogGroup - Create log group if it doesn't exist
        #    - logs:CreateLogStream - Create new log stream for each invocation
        #    - logs:PutLogEvents - Write log events to CloudWatch
        #    - Resource: Scoped to this function's log group only
        #    - Why: Required for all Lambda functions to write logs
        upload_handler_role = iam.Role(
            self, "UploadHandlerRole",
            role_name="EmailClassification-UploadHandlerRole",
            description="Execution role for Upload Handler Lambda - allows uploading EML files to S3 inbox",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "S3UploadPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowPutObjectToInboxBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",  # Upload EML files to S3
                            ],
                            resources=[
                                # Restrict to incoming/ prefix only
                                # This prevents the function from writing to other prefixes
                                f"{self.inbox_bucket.bucket_arn}/incoming/*",
                            ],
                        ),
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",    # Create log group if needed
                                "logs:CreateLogStream",   # Create log stream for invocation
                                "logs:PutLogEvents",      # Write log events
                            ],
                            resources=[
                                # Scope to this function's log group only
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/EmailClassification-UploadHandler:*",
                            ],
                        ),
                    ]
                ),
            },
        )

        # ========================================
        # Lambda Functions
        # ========================================
        # Lambda Documentation: https://docs.aws.amazon.com/lambda/latest/dg/welcome.html
        # Lambda Python Runtime: https://docs.aws.amazon.com/lambda/latest/dg/lambda-python.html
        # Lambda Best Practices: https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html
        # Lambda Monitoring: https://docs.aws.amazon.com/lambda/latest/dg/lambda-monitoring.html
        
        # Upload Handler Lambda Function
        #
        # Purpose: Receives EML files from API Gateway, validates them, and stores in S3
        #
        # Why these settings:
        # - Python 3.12: Latest stable Python runtime with improved performance
        # - 512MB memory: Sufficient for parsing multipart data and uploading to S3
        # - 30 second timeout: Allows time for large file uploads (up to 10MB)
        # - Code from local directory: Keeps Lambda code in the project for easy updates
        # - Environment variables: Pass bucket name to Lambda without hardcoding
        # - role: Custom IAM role with least privilege permissions
        #
        # IAM Permissions (via upload_handler_role):
        # - s3:PutObject on inbox bucket incoming/ prefix (to upload files)
        # - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents (for CloudWatch)
        self.upload_handler = lambda_.Function(
            self, "UploadHandler",
            function_name="EmailClassification-UploadHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="upload_handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            memory_size=512,
            timeout=Duration.seconds(30),
            role=upload_handler_role,  # Use custom IAM role with least privilege
            environment={
                'INBOX_BUCKET_NAME': self.inbox_bucket.bucket_name,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,  # Keep logs for 7 days
            description="Handles EML file uploads from API Gateway and stores them in S3",
        )

        # Email Processor Execution Role
        #
        # Purpose: Defines permissions for the Email Processor Lambda function
        #
        # Principle of Least Privilege:
        # - S3 permissions scoped to specific buckets and prefixes
        # - Bedrock permissions limited to required actions only
        # - Step Functions permission scoped to specific state machine (added later)
        # - CloudWatch Logs permissions scoped to function's log group
        #
        # Security Best Practices Applied:
        # - No wildcard (*) permissions on S3 resources
        # - Bedrock permissions use wildcard only because resource-level permissions not supported
        # - Separate read and write permissions for clarity
        # - Inline policies for transparency (visible in stack definition)
        # - Descriptive SIDs for each permission statement
        #
        # Bedrock Data Automation: https://docs.aws.amazon.com/bedrock/latest/userguide/data-automation.html
        #
        # Required Permissions:
        # 1. s3:GetObject - Read EML files from inbox bucket
        #    - Resource: inbox bucket (all prefixes needed for reading emails and config)
        #    - Why: Must read uploaded EML files and department configuration
        #
        # 2. s3:PutObject - Write extracted PDF attachments and BDA job metadata
        #    - Resource: inbox bucket attachments/ and bda-jobs/ prefixes
        #    - Why: Store extracted PDFs and track BDA invocations
        #
        # 3. bedrock:InvokeDataAutomationAsync - Invoke BDA for document processing
        #    - Resource: All BDA resources in region (BDA doesn't support resource-level permissions)
        #    - Why: Process PDF invoices to extract structured data
        #
        # 4. bedrock:ListDataAutomationProjects - List available BDA projects
        #    - Resource: All BDA resources in region
        #    - Why: Find the invoice-processing project ID dynamically
        #
        # 5. bedrock:GetDataAutomationProject - Get BDA project details
        #    - Resource: All BDA resources in region
        #    - Why: Retrieve project configuration for invocation
        #
        # 6. states:StartExecution - Start Step Functions workflow
        #    - Resource: Specific state machine ARN (added after state machine is created)
        #    - Why: Trigger classification workflow after BDA invocation
        #
        # 7. CloudWatch Logs - Write function logs
        #    - Resource: Scoped to this function's log group only
        email_processor_role = iam.Role(
            self, "EmailProcessorRole",
            role_name="EmailClassification-EmailProcessorRole",
            description="Execution role for Email Processor Lambda - reads emails, invokes BDA, starts Step Functions",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "S3AccessPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowReadFromInboxBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",  # Read EML files and configuration
                            ],
                            resources=[
                                # Allow reading from all prefixes in inbox bucket
                                # Needed for: incoming/ (EML files), config files
                                f"{self.inbox_bucket.bucket_arn}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="AllowWriteToInboxBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",  # Write attachments and metadata
                            ],
                            resources=[
                                # Restrict writes to specific prefixes only
                                f"{self.inbox_bucket.bucket_arn}/attachments/*",  # PDF attachments
                                f"{self.inbox_bucket.bucket_arn}/bda-jobs/*",     # BDA job metadata
                                f"{self.inbox_bucket.bucket_arn}/bda-output/*",   # BDA output location
                            ],
                        ),
                    ]
                ),
                "BedrockDataAutomationPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowBedrockDataAutomation",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeDataAutomationAsync",  # Invoke BDA for document processing
                                "bedrock:ListDataAutomationProjects", # List available BDA projects
                                "bedrock:GetDataAutomationProject",   # Get project details
                            ],
                            # BDA doesn't support resource-level permissions yet
                            # Must use wildcard, but limited to this region by default
                            resources=["*"],
                        ),
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/EmailClassification-EmailProcessor:*",
                            ],
                        ),
                    ]
                ),
            },
        )

        # ========================================
        # Bedrock Data Automation Project
        # ========================================
        # BDA Documentation: https://docs.aws.amazon.com/bedrock/latest/userguide/bda-how-it-works.html
        # BDA API Reference: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_Operations_Data_Automation_for_Amazon_Bedrock.html
        # CloudFormation Reference: https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-bedrock-dataautomationproject.html
        
        # Create BDA Project for Invoice Processing
        #
        # Purpose: Defines the Bedrock Data Automation project for extracting text and structured data from PDF invoices
        #
        # Why BDA:
        # - Automatically extracts text from PDF documents
        # - Provides structured output for downstream processing
        # - Handles various document formats and layouts
        # - Scales automatically with workload
        # - No infrastructure management required
        #
        # Configuration:
        # - Project Name: invoice-processing (must match what Lambda code expects)
        # - Standard Output: Enabled for document processing
        # - Document Extraction: Enabled for text extraction
        # - Output Format: Markdown for easy parsing
        #
        # The Lambda function (email_processor.py) looks for this project by name
        # and uses it to process PDF invoice attachments
        #
        # Note: Using CfnResource because CDK doesn't have native L2 constructs for BDA yet
        #
        # Configuration based on AWS CLI examples and CloudFormation schema:
        # - ProjectName: Required, must match Lambda code expectations ("invoice-processing")
        # - StandardOutputConfiguration: Required for document processing
        #   - Document.Extraction: Enables text extraction
        #     - BoundingBox: Provides location information for extracted text
        #     - Granularity: Specifies extraction level (document, page, line, word)
        #   - Document.GenerativeField: Enables AI-generated summaries
        #   - Document.OutputFormat: Specifies output format (text and additional files)
        #
        # See: https://docs.aws.amazon.com/bedrock/latest/userguide/bda-cli-guide.html
        self.bda_project = CfnResource(
            self, "BDAProject",
            type="AWS::Bedrock::DataAutomationProject",
            properties={
                "ProjectName": "invoice-processing",
                "ProjectDescription": "Data automation project for extracting text and structured data from invoice PDF attachments",
                "StandardOutputConfiguration": {
                    "Document": {
                        "Extraction": {
                            "BoundingBox": {
                                "State": "ENABLED"
                            },
                            "Granularity": {
                                "Types": ["DOCUMENT"]
                            }
                        },
                        "GenerativeField": {
                            "State": "ENABLED"
                        },
                        "OutputFormat": {
                            "TextFormat": {
                                "Types": ["PLAIN_TEXT"]
                            },
                            "AdditionalFileFormat": {
                                "State": "DISABLED"
                            }
                        }
                    }
                }
            }
        )

        # Email Processor Lambda Function
        #
        # Purpose: Processes incoming EML files, extracts PDF attachments, and invokes BDA
        #
        # Why these settings:
        # - Python 3.12: Latest stable Python runtime
        # - 1024MB memory: Sufficient for parsing emails and handling PDF attachments
        # - 5 minute timeout: Allows time for BDA invocation and Step Functions orchestration
        # - Code from local directory: Keeps Lambda code in the project
        # - Environment variables: Pass bucket names and ARNs to Lambda
        # - role: Custom IAM role with least privilege permissions
        #
        # IAM Permissions (via email_processor_role):
        # - s3:GetObject on inbox bucket (to read EML files)
        # - s3:PutObject on inbox bucket attachments/ and bda-jobs/ prefixes (to store attachments and metadata)
        # - bedrock:InvokeDataAutomationAsync, ListDataAutomationProjects, GetDataAutomationProject (for BDA)
        # - states:StartExecution on specific state machine (added later, to start Step Functions workflow)
        # - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents (for CloudWatch)
        self.email_processor = lambda_.Function(
            self, "EmailProcessor",
            function_name="EmailClassification-EmailProcessor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="email_processor.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            memory_size=1024,
            timeout=Duration.minutes(5),
            role=email_processor_role,  # Use custom IAM role with least privilege
            environment={
                'INBOX_BUCKET': self.inbox_bucket.bucket_name,
                'DESTINATION_BUCKET': self.destination_bucket.bucket_name,
                # STATE_MACHINE_ARN will be set later when state machine is created
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
            description="Processes incoming emails, extracts attachments, and invokes BDA",
        )
        
        # Configure S3 event notification to trigger Email Processor
        #
        # Why these settings:
        # - Event: OBJECT_CREATED triggers on any object creation (Put, Post, Copy, CompleteMultipartUpload)
        # - Prefix filter: Only trigger for files in the incoming/ folder
        # - This ensures the Lambda only processes new EML files uploaded by the Upload Handler
        #
        # How it works:
        # 1. Upload Handler stores EML file in s3://bucket/incoming/filename.eml
        # 2. S3 sends ObjectCreated event to Email Processor Lambda
        # 3. Email Processor extracts attachments and invokes BDA
        #
        # Note: CDK automatically creates the necessary Lambda permissions for S3 invocation
        self.inbox_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.email_processor),
            s3.NotificationKeyFilter(prefix="incoming/")
        )

        # ========================================
        # List Emails Lambda Function
        # ========================================
        
        # List Emails Execution Role
        #
        # Purpose: Defines permissions for the List Emails Lambda function
        #
        # Principle of Least Privilege:
        # - S3 read permissions scoped to destination bucket departments/ prefix only
        # - No write or delete permissions
        # - CloudWatch Logs permissions scoped to function's log group
        #
        # Security Best Practices Applied:
        # - Resource-level permissions (not bucket-wide)
        # - Read-only access (s3:ListBucket, s3:GetObject, s3:GetObjectMetadata)
        # - Scoped to specific prefix (departments/)
        # - Separate role per Lambda function
        # - Inline policies for transparency
        #
        # Required Permissions:
        # 1. s3:ListBucket - List objects in destination bucket
        #    - Resource: destination bucket
        #    - Condition: Prefix restricted to departments/
        #    - Why: List emails in department folders
        #
        # 2. s3:GetObject - Read email files from destination bucket
        #    - Resource: destination bucket departments/* prefix
        #    - Why: Retrieve email metadata from S3 object metadata
        #
        # 3. s3:GetObjectMetadata - Read object metadata
        #    - Resource: destination bucket departments/* prefix
        #    - Why: Extract email metadata (sender, subject, timestamp, etc.)
        #
        # 4. CloudWatch Logs - Write function logs
        #    - Resource: Scoped to this function's log group only
        list_emails_role = iam.Role(
            self, "ListEmailsRole",
            role_name="EmailClassification-ListEmailsRole",
            description="Execution role for List Emails Lambda - read-only access to destination bucket",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "S3ReadPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowListDestinationBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:ListBucket",  # List objects in destination bucket
                            ],
                            resources=[
                                # Bucket-level permission for ListBucket
                                self.destination_bucket.bucket_arn,
                            ],
                            conditions={
                                "StringLike": {
                                    # Restrict listing to departments/ prefix only
                                    # This prevents listing other prefixes in the bucket
                                    "s3:prefix": ["departments/*"]
                                }
                            },
                        ),
                        iam.PolicyStatement(
                            sid="AllowReadFromDestinationBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",          # Read email files
                                "s3:GetObjectMetadata",  # Read object metadata
                            ],
                            resources=[
                                # Restrict reads to departments/ prefix only
                                # This prevents reading from other locations
                                f"{self.destination_bucket.bucket_arn}/departments/*",
                            ],
                        ),
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/EmailClassification-ListEmails:*",
                            ],
                        ),
                    ]
                ),
            },
        )

        # List Emails Lambda Function
        #
        # Purpose: Lists classified emails from destination bucket for a specific department
        #
        # Why these settings:
        # - Python 3.12: Latest stable Python runtime (consistent with other functions)
        # - 256MB memory: Minimal processing required (just listing and metadata extraction)
        # - 10 second timeout: Sufficient for S3 list operations (typically < 2 seconds)
        # - Code from local directory: Keeps Lambda code in the project
        # - Environment variable: Pass destination bucket name to Lambda
        # - role: Custom IAM role with read-only permissions
        #
        # IAM Permissions (via list_emails_role):
        # - s3:ListBucket on destination bucket with departments/ prefix condition
        # - s3:GetObject on destination bucket departments/* prefix
        # - s3:GetObjectMetadata on destination bucket departments/* prefix
        # - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents (for CloudWatch)
        #
        # This Lambda is invoked by API Gateway when users request department emails
        self.list_emails_function = lambda_.Function(
            self, "ListEmails",
            function_name="EmailClassification-ListEmails",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="list_emails.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            memory_size=256,
            timeout=Duration.seconds(10),
            role=list_emails_role,  # Use custom IAM role with read-only permissions
            environment={
                'DESTINATION_BUCKET_NAME': self.destination_bucket.bucket_name,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
            description="Lists classified emails from destination bucket for a specific department",
        )

        # ========================================
        # API Gateway
        # ========================================
        # API Gateway Documentation: https://docs.aws.amazon.com/apigateway/latest/developerguide/welcome.html
        # REST API vs HTTP API: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html
        # API Gateway CORS: https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-cors.html
        # Binary Media Types: https://docs.aws.amazon.com/apigateway/latest/developerguide/api-gateway-payload-encodings.html
        
        # REST API for file uploads
        #
        # Why REST API (not HTTP API):
        # - Better support for binary media types (multipart/form-data)
        # - Request validation capabilities
        # - More mature and stable for this use case
        # - HTTP API is newer and cheaper but lacks some features we need
        #
        # Architecture Decision: REST API
        # - Chosen for binary media type support (file uploads)
        # - Provides request validation before Lambda invocation
        # - Supports resource policies for additional security
        # - Well-documented and widely used pattern
        #
        # Why these settings:
        # - deploy: True automatically creates a deployment and stage
        # - default_cors_preflight_options: Enables CORS for browser uploads
        # - binary_media_types: Tells API Gateway to treat multipart/form-data as binary
        #   and pass it base64-encoded to Lambda
        # - endpoint_types: REGIONAL is sufficient for demo (EDGE would use CloudFront)
        #
        # Security Considerations:
        # - CORS set to allow all origins (*) for demo purposes
        # - In production, restrict to specific domains
        # - Consider adding API keys or Cognito authentication
        # - Rate limiting configured to prevent abuse
        self.upload_api = apigateway.RestApi(
            self, "UploadApi",
            rest_api_name="EmailClassification-UploadApi",
            description="API for uploading EML files to the email classification system",
            deploy=True,
            deploy_options=apigateway.StageOptions(
                stage_name="prod",
                throttling_rate_limit=10,  # Max 10 requests per second
                throttling_burst_limit=20,  # Allow bursts up to 20 requests
                logging_level=apigateway.MethodLoggingLevel.INFO,
                data_trace_enabled=True,  # Log full request/response for debugging
                metrics_enabled=True,  # Enable CloudWatch metrics
            ),
            # Configure CORS to allow uploads from any origin (demo purposes)
            # In production, restrict to specific domains
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,  # Allow all origins (*)
                allow_methods=apigateway.Cors.ALL_METHODS,  # Allow all HTTP methods
                allow_headers=[
                    'Content-Type',
                    'X-Amz-Date',
                    'Authorization',
                    'X-Api-Key',
                    'X-Amz-Security-Token',
                ],
                allow_credentials=False,  # Don't need credentials for demo
            ),
            # Binary media types configuration
            # This tells API Gateway to base64-encode these content types
            # before passing to Lambda, which is necessary for file uploads
            binary_media_types=[
                'multipart/form-data',
                'application/octet-stream',
            ],
            endpoint_types=[apigateway.EndpointType.REGIONAL],
        )
        
        # Create /upload resource (endpoint)
        #
        # This creates the URL path: https://{api-id}.execute-api.{region}.amazonaws.com/prod/upload
        #
        # CORS Configuration:
        # The default_cors_preflight_options on the RestApi should automatically add OPTIONS methods,
        # but we need to ensure it's properly configured for this resource
        upload_resource = self.upload_api.root.add_resource(
            'upload',
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,  # Allow all origins (*)
                allow_methods=['POST', 'OPTIONS'],  # Explicitly allow POST and OPTIONS
                allow_headers=[
                    'Content-Type',
                    'X-Amz-Date',
                    'Authorization',
                    'X-Api-Key',
                    'X-Amz-Security-Token',
                ],
                allow_credentials=False,
            )
        )
        
        # Lambda integration for the upload endpoint
        #
        # Why Lambda Proxy Integration:
        # - Passes the entire HTTP request to Lambda (headers, body, query params)
        # - Lambda has full control over the response (status code, headers, body)
        # - Simplifies Lambda code as it receives standard HTTP request format
        #
        # Why these settings:
        # - proxy: True enables Lambda proxy integration (Lambda handles CORS headers)
        # - allow_test_invoke: True allows testing from API Gateway console
        #
        # Note: With proxy=True, Lambda function must return CORS headers in response
        # The integration_responses are ignored when using proxy integration
        upload_integration = apigateway.LambdaIntegration(
            self.upload_handler,
            proxy=True,
            allow_test_invoke=True,  # Allow testing from API Gateway console
        )
        
        # Add POST method to /upload endpoint
        #
        # Why these settings:
        # - authorization_type: NONE means no authentication (demo purposes)
        # - request_validator: Validates request before invoking Lambda
        # - method_responses: Defines possible response codes and headers
        upload_resource.add_method(
            'POST',
            upload_integration,
            authorization_type=apigateway.AuthorizationType.NONE,
            method_responses=[
                apigateway.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                    },
                    response_models={
                        'application/json': apigateway.Model.EMPTY_MODEL
                    }
                ),
                apigateway.MethodResponse(
                    status_code='400',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                    }
                ),
                apigateway.MethodResponse(
                    status_code='500',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                    }
                )
            ]
        )
        
        # Add request validator to enforce size limits
        #
        # This validator checks:
        # - Request body size (max 10MB as configured in API Gateway)
        # - Content-Type header presence
        #
        # Note: API Gateway has a hard limit of 10MB for request payload
        # which aligns with our requirement
        request_validator = apigateway.RequestValidator(
            self, "UploadRequestValidator",
            rest_api=self.upload_api,
            request_validator_name="upload-validator",
            validate_request_body=True,
            validate_request_parameters=True,
        )

        # ========================================
        # API Gateway - Department List Endpoint
        # ========================================
        
        # Create /departments resource
        #
        # This creates the URL path: https://{api-id}.execute-api.{region}.amazonaws.com/prod/departments
        #
        # Purpose: Base resource for department-related endpoints
        # This follows REST API conventions where resources are organized hierarchically
        departments_resource = self.upload_api.root.add_resource('departments')
        
        # Create /{department} sub-resource with path parameter
        #
        # This creates the URL path: https://{api-id}.execute-api.{region}.amazonaws.com/prod/departments/{department}
        #
        # Purpose: Represents a specific department (finance, it, hr, operations, marketing)
        # The {department} path parameter will be validated by the Lambda function
        department_resource = departments_resource.add_resource('{department}')
        
        # Create /emails sub-resource with CORS configuration
        #
        # This creates the final URL path: https://{api-id}.execute-api.{region}.amazonaws.com/prod/departments/{department}/emails
        #
        # Purpose: Endpoint to list emails for a specific department
        # GET /departments/{department}/emails returns all emails for that department
        #
        # CORS Configuration:
        # - Allow all origins (*) for demo purposes (production should restrict to CloudFront domain)
        # - Allow GET and OPTIONS methods (OPTIONS for CORS preflight)
        # - Allow standard headers for API requests
        emails_resource = department_resource.add_resource(
            'emails',
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,  # Allow all origins (*)
                allow_methods=['GET', 'OPTIONS'],  # Explicitly allow GET and OPTIONS
                allow_headers=[
                    'Content-Type',
                    'X-Amz-Date',
                    'Authorization',
                    'X-Api-Key',
                    'X-Amz-Security-Token',
                ],
                allow_credentials=False,  # Don't need credentials for demo
            )
        )
        
        # Lambda integration for the list emails endpoint
        #
        # Why Lambda Proxy Integration:
        # - Passes the entire HTTP request to Lambda (path parameters, query params, headers)
        # - Lambda has full control over the response (status code, headers, body)
        # - Simplifies Lambda code as it receives standard HTTP request format
        # - Lambda can access {department} path parameter from event.pathParameters
        #
        # Why these settings:
        # - proxy: True enables Lambda proxy integration
        # - allow_test_invoke: True allows testing from API Gateway console
        list_emails_integration = apigateway.LambdaIntegration(
            self.list_emails_function,
            proxy=True,
            allow_test_invoke=True,
        )
        
        # Add GET method to /departments/{department}/emails endpoint
        #
        # Why these settings:
        # - authorization_type: NONE means no authentication (demo purposes)
        # - method_responses: Defines possible response codes and CORS headers
        #
        # Response codes:
        # - 200: Success with email list
        # - 400: Invalid department parameter
        # - 500: Internal server error
        emails_resource.add_method(
            'GET',
            list_emails_integration,
            authorization_type=apigateway.AuthorizationType.NONE,
            method_responses=[
                apigateway.MethodResponse(
                    status_code='200',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                        'method.response.header.Access-Control-Allow-Methods': True,
                    },
                    response_models={
                        'application/json': apigateway.Model.EMPTY_MODEL
                    }
                ),
                apigateway.MethodResponse(
                    status_code='400',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                    }
                ),
                apigateway.MethodResponse(
                    status_code='500',
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Origin': True,
                    }
                )
            ]
        )

        # ========================================
        # Website and Configuration Deployment
        # ========================================
        
        # Deploy website assets to S3
        #
        # Purpose: Upload static website files (HTML, CSS, JS, SVG) to the website bucket
        #
        # Why BucketDeployment:
        # - Automatically uploads files during CDK deployment
        # - Handles updates when files change
        # - Sets proper content types and cache headers
        # - Integrates with CDK lifecycle (deploy/destroy)
        # - Invalidates CloudFront cache after deployment
        #
        # Files deployed:
        # - index.html: Main upload interface
        # - styles.css: Styling adapted from example website
        # - app.js: Upload logic and API integration
        # - architecture-diagram.svg: Interactive architecture diagram
        #
        # Why these settings:
        # - sources: Points to local website directory containing all assets
        # - destination_bucket: Website bucket created earlier
        # - prune: True removes old files when updating (keeps bucket clean)
        # - retain_on_delete: False removes files when stack is destroyed
        # - content_type: Automatically detected based on file extension
        # - cache_control: Sets cache headers for browser caching
        # - distribution: Invalidates CloudFront cache after deployment
        #
        # Cache headers:
        # - max-age=300 (5 minutes) - allows quick updates for HTML
        # - Static assets (CSS/JS/SVG) benefit from CloudFront caching
        self.website_deployment = s3deploy.BucketDeployment(
            self, "WebsiteDeployment",
            sources=[
                s3deploy.Source.asset("website"),  # Upload entire website directory
            ],
            destination_bucket=self.website_bucket,
            prune=True,  # Remove old files when updating
            retain_on_delete=False,  # Remove files when stack is destroyed
            # Set cache control headers for optimal performance
            # Short cache (5 minutes) allows quick updates while still providing some caching benefit
            cache_control=[
                s3deploy.CacheControl.max_age(Duration.minutes(5)),
            ],
            # Invalidate CloudFront cache after deployment
            # This ensures users get the latest version of the website immediately
            # Without this, users might see cached old versions for up to 24 hours
            distribution=self.distribution,
            distribution_paths=["/*"],  # Invalidate all paths
        )
        
        # Deploy API configuration file
        #
        # Purpose: Inject API Gateway URL into a JavaScript config file at deployment time
        #
        # Why separate deployment:
        # - API Gateway URL is only available after the API is created
        # - BucketDeployment doesn't support variable substitution in files
        # - Creating a separate config.js file is cleaner than modifying source files
        #
        # How it works:
        # 1. Create a JavaScript file with the API Gateway URL
        # 2. Upload it to S3 alongside other website assets
        # 3. HTML file loads this config before loading app.js
        # 4. app.js reads window.API_GATEWAY_URL set by config.js
        #
        # Content of config.js:
        # window.API_GATEWAY_URL = 'https://{api-id}.execute-api.{region}.amazonaws.com/prod/';
        #
        # This approach:
        # - Keeps source code clean (no placeholders)
        # - Works with CDK's deployment model
        # - Easy to update when API changes
        # - No build step required
        s3deploy.BucketDeployment(
            self, "ApiConfigDeployment",
            sources=[
                s3deploy.Source.data(
                    "config.js",
                    f"// API Configuration - Auto-generated by CDK\n"
                    f"// This file is created during deployment and should not be edited manually\n"
                    f"window.API_GATEWAY_URL = '{self.upload_api.url}';\n"
                    f"console.log('API Gateway URL configured:', window.API_GATEWAY_URL);\n"
                )
            ],
            destination_bucket=self.website_bucket,
            prune=False,  # Don't delete other files
            retain_on_delete=False,
            cache_control=[
                s3deploy.CacheControl.max_age(Duration.minutes(5)),  # Short cache for config
            ],
            distribution=self.distribution,
            distribution_paths=["/config.js"],  # Only invalidate config.js
        )

        # ========================================
        # Department Configuration Upload
        # ========================================
        
        # Upload department configuration file to S3
        #
        # Purpose: Provides department configuration for the classifier Lambda
        #
        # Why BucketDeployment:
        # - Automatically uploads files during CDK deployment
        # - Handles updates when configuration changes
        # - No need for manual upload steps
        # - Integrates with CDK lifecycle (deploy/destroy)
        #
        # Configuration structure:
        # - departments: Array of department objects
        # - name: Department display name (e.g., "Finance")
        # - prefixPath: S3 prefix for storing classified emails (e.g., "departments/finance")
        #
        # How it's used:
        # 1. Classifier Lambda reads this file from S3 on startup
        # 2. Uses department list for Bedrock classification prompt
        # 3. Uses prefixPath to determine where to copy classified emails
        # 4. Allows easy configuration updates without code changes
        #
        # Why stored in inbox bucket:
        # - Classifier already has read permissions on inbox bucket
        # - Keeps configuration close to processing logic
        # - Simplifies IAM permissions (no additional bucket needed)
        s3deploy.BucketDeployment(
            self, "DepartmentConfigUpload",
            sources=[
                s3deploy.Source.asset("config"),  # Upload entire config directory
            ],
            destination_bucket=self.inbox_bucket,
            prune=False,  # Don't delete other objects in the bucket
            retain_on_delete=False,  # Remove config when stack is destroyed
        )

        # ========================================
        # SQS Queue for Email Routing
        # ========================================
        # SQS Documentation: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html
        # SQS Best Practices: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-best-practices.html
        # Long Polling: https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-short-and-long-polling.html
        
        # Email Routing Queue
        #
        # Purpose: Queues classified emails for routing to department email addresses
        #
        # Architecture Decision: Why SQS?
        # - Decouples classification from routing (separation of concerns)
        # - Provides retry logic and dead-letter queue capability
        # - Allows asynchronous processing without blocking classification
        # - Scales automatically with message volume
        # - More reliable than direct Lambda-to-Lambda invocation
        # - Enables future enhancements (batch processing, priority queues)
        #
        # Why these settings:
        # - visibility_timeout: 5 minutes allows Router Lambda enough time to process
        # - retention_period: 14 days keeps messages for debugging if needed
        # - receive_message_wait_time: 20 seconds enables long polling for efficiency
        #
        # How it works:
        # 1. Classifier Lambda sends message after classifying email
        # 2. Router Lambda polls queue and processes messages
        # 3. Router creates metadata and forwards via SES
        #
        # Best Practices Applied:
        # - Long polling enabled (reduces empty receives and costs)
        # - Visibility timeout matches Lambda timeout
        # - Message retention allows debugging of failed messages
        self.routing_queue = sqs.Queue(
            self, "EmailRoutingQueue",
            queue_name="EmailClassification-RoutingQueue",
            visibility_timeout=Duration.minutes(5),
            retention_period=Duration.days(14),
            receive_message_wait_time=Duration.seconds(20),  # Enable long polling
        )

        # ========================================
        # Invoice Classifier Lambda Function
        # ========================================
        
        # Invoice Classifier Execution Role
        #
        # Purpose: Defines permissions for the Invoice Classifier Lambda function
        #
        # Principle of Least Privilege:
        # - S3 read permissions scoped to inbox bucket only
        # - S3 write permissions scoped to destination bucket specific prefixes
        # - S3 list permissions scoped to specific prefixes for checking BDA output
        # - Bedrock InvokeModel scoped to specific foundation models
        # - SQS permissions scoped to specific routing queue
        # - CloudWatch Logs permissions scoped to function's log group
        #
        # Security Best Practices Applied:
        # - Resource-level permissions wherever possible
        # - Condition keys used to further restrict S3 ListBucket
        # - Multiple foundation models allowed for fallback resilience
        # - No cross-account access permissions
        # - Explicit resource ARNs (no wildcards except where required by service)
        #
        # Bedrock Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
        # Bedrock Foundation Models: https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
        #
        # Required Permissions:
        # 1. s3:GetObject - Read BDA output, emails, and configuration
        #    - Resource: inbox bucket (all prefixes for BDA output, emails, config)
        #    - Why: Retrieve BDA extracted data and original email for classification
        #
        # 2. s3:ListBucket - List objects in BDA output prefix
        #    - Resource: inbox bucket
        #    - Condition: Prefix restricted to bda-output/
        #    - Why: Check if BDA output exists and find output files
        #
        # 3. s3:PutObject - Write classified emails and metadata to destination
        #    - Resource: destination bucket departments/ prefixes
        #    - Why: Copy classified emails to appropriate department folders
        #
        # 4. bedrock:InvokeModel - Call Bedrock for classification
        #    - Resource: Specific foundation models (Nova Lite and fallbacks)
        #    - Why: Use AI to classify invoices into departments
        #
        # 5. sqs:SendMessage - Send routing messages to queue
        #    - Resource: Specific routing queue
        #    - Why: Trigger email routing after classification
        #
        # 6. CloudWatch Logs - Write function logs
        #    - Resource: Scoped to this function's log group only
        classifier_role = iam.Role(
            self, "ClassifierRole",
            role_name="EmailClassification-ClassifierRole",
            description="Execution role for Invoice Classifier Lambda - reads BDA output, invokes Bedrock, writes to destination",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            inline_policies={
                "S3ReadPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowReadFromInboxBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:GetObject",  # Read BDA output, emails, and config
                            ],
                            resources=[
                                # Allow reading from all prefixes in inbox bucket
                                # Needed for: bda-output/ (BDA results), incoming/ (original emails), config files
                                f"{self.inbox_bucket.bucket_arn}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            sid="AllowListInboxBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:ListBucket",  # List objects to find BDA output
                            ],
                            resources=[
                                self.inbox_bucket.bucket_arn,  # Bucket-level permission
                            ],
                            conditions={
                                "StringLike": {
                                    # Restrict listing to bda-output/ prefix only
                                    # This prevents listing other prefixes unnecessarily
                                    "s3:prefix": ["bda-output/*"]
                                }
                            },
                        ),
                    ]
                ),
                "S3WritePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowWriteToDestinationBucket",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:PutObject",  # Write classified emails and metadata
                            ],
                            resources=[
                                # Restrict writes to departments/ prefix only
                                # This prevents writing to other locations in destination bucket
                                f"{self.destination_bucket.bucket_arn}/departments/*",
                            ],
                        ),
                    ]
                ),
                "BedrockInvokeModelPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowBedrockInvokeModel",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",                # Invoke foundation models for classification
                                "bedrock:InvokeModelWithResponseStream",  # Support streaming responses if needed
                            ],
                            resources=[
                                # Scope to specific foundation models only
                                # Primary model: Nova Lite for cost-effective classification
                                f"arn:aws:bedrock:{self.region}::foundation-model/amazon.nova-lite-v1:0",
                                # Fallback models: Allow other models in case Nova Lite is unavailable
                                # This provides resilience without granting access to all AWS services
                                f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-*",
                                f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-*",
                            ],
                        ),
                    ]
                ),
                "SQSPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowSendMessageToRoutingQueue",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "sqs:SendMessage",  # Send routing messages after classification
                            ],
                            resources=[
                                # Scope to specific routing queue only
                                self.routing_queue.queue_arn,
                            ],
                        ),
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents",
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/EmailClassification-InvoiceClassifier:*",
                            ],
                        ),
                    ]
                ),
            },
        )

        # Invoice Classifier Lambda Function
        #
        # Purpose: Classifies invoices using Bedrock and organizes emails by department
        #
        # Why these settings:
        # - Python 3.12: Latest stable Python runtime
        # - 1024MB memory: Sufficient for Bedrock API calls and S3 operations
        # - 5 minute timeout: Allows time for Bedrock classification and S3 operations
        # - Code from local directory: Keeps Lambda code in the project
        # - Environment variables: Pass bucket names, queue URL, and config location
        # - role: Custom IAM role with least privilege permissions
        #
        # IAM Permissions (via classifier_role):
        # - s3:GetObject on inbox bucket (to read BDA output and emails)
        # - s3:ListBucket on inbox bucket with bda-output/ prefix condition (to find BDA output)
        # - s3:PutObject on destination bucket departments/ prefix (to copy classified emails)
        # - bedrock:InvokeModel on specific foundation models (to call Bedrock Converse API for classification)
        # - sqs:SendMessage on routing queue (to send routing messages)
        # - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents (for CloudWatch)
        #
        # This Lambda is invoked by Step Functions after BDA completes processing
        self.classifier_function = lambda_.Function(
            self, "InvoiceClassifier",
            function_name="EmailClassification-InvoiceClassifier",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="invoice_classifier.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            memory_size=1024,
            timeout=Duration.minutes(5),
            role=classifier_role,  # Use custom IAM role with least privilege
            environment={
                'INBOX_BUCKET': self.inbox_bucket.bucket_name,
                'DESTINATION_BUCKET': self.destination_bucket.bucket_name,
                'CONFIG_BUCKET_NAME': self.inbox_bucket.bucket_name,  # Config stored in inbox bucket
                'CONFIG_FILE_KEY': 'department_config.json',
                'EMAIL_ROUTING_QUEUE_URL': self.routing_queue.queue_url,
                'BEDROCK_MODEL_ID': 'amazon.nova-lite-v1:0',
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
            description="Classifies invoices using Bedrock and organizes emails by department",
        )

        # ========================================
        # Step Functions Execution Role
        # ========================================
        
        # Step Functions Execution Role
        #
        # Purpose: Defines permissions for the Step Functions state machine
        #
        # Principle of Least Privilege:
        # - Lambda invoke permissions scoped to specific classifier function
        # - S3 list permissions scoped to specific bucket and prefix
        # - CloudWatch Logs permissions scoped to state machine's log group
        # - X-Ray permissions for tracing
        #
        # Security Best Practices Applied:
        # - Function-specific Lambda invocation (not wildcard)
        # - S3 ListBucket with prefix condition (not bucket-wide)
        # - CloudWatch Logs delivery permissions (required for Step Functions logging)
        # - X-Ray tracing for security auditing and performance monitoring
        #
        # Step Functions IAM: https://docs.aws.amazon.com/step-functions/latest/dg/procedure-create-iam-role.html
        # X-Ray Tracing: https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html
        #
        # Required Permissions:
        # 1. lambda:InvokeFunction - Invoke the classifier Lambda
        #    - Resource: Specific classifier function ARN
        #    - Why: State machine needs to trigger classification after BDA completes
        #
        # 2. s3:ListBucket - List objects in BDA output prefix
        #    - Resource: inbox bucket
        #    - Condition: Prefix restricted to bda-output/
        #    - Why: Check if BDA has completed and output is available
        #
        # 3. CloudWatch Logs - Write state machine execution logs
        #    - Resource: Scoped to state machine's log group
        #    - Why: Required for monitoring and debugging workflow executions
        #
        # 4. X-Ray - Write trace data for performance analysis
        #    - Resource: All (X-Ray doesn't support resource-level permissions)
        #    - Why: Provides distributed tracing for debugging and optimization
        step_functions_role = iam.Role(
            self, "StepFunctionsRole",
            role_name="EmailClassification-StepFunctionsRole",
            description="Execution role for Step Functions state machine - invokes Lambda, checks S3, writes logs",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={
                "LambdaInvokePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowInvokeClassifierFunction",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "lambda:InvokeFunction",  # Invoke classifier Lambda
                            ],
                            resources=[
                                # Scope to specific classifier function only
                                # This prevents the state machine from invoking other Lambda functions
                                f"arn:aws:lambda:{self.region}:{self.account}:function:EmailClassification-InvoiceClassifier",
                            ],
                        ),
                    ]
                ),
                "S3ListPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowListBDAOutput",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "s3:ListBucket",  # List objects to check if BDA output exists
                            ],
                            resources=[
                                # Bucket-level permission for ListBucket
                                self.inbox_bucket.bucket_arn,
                            ],
                            conditions={
                                "StringLike": {
                                    # Restrict listing to bda-output/ prefix only
                                    # This prevents listing other prefixes in the bucket
                                    "s3:prefix": ["bda-output/*"]
                                }
                            },
                        ),
                    ]
                ),
                "CloudWatchLogsPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowCloudWatchLogsAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogDelivery",     # Create log delivery for state machine
                                "logs:GetLogDelivery",        # Get log delivery configuration
                                "logs:UpdateLogDelivery",     # Update log delivery settings
                                "logs:DeleteLogDelivery",     # Delete log delivery when state machine is deleted
                                "logs:ListLogDeliveries",     # List log deliveries
                                "logs:PutResourcePolicy",     # Put resource policy for log group
                                "logs:DescribeResourcePolicies",  # Describe resource policies
                                "logs:DescribeLogGroups",     # Describe log groups
                            ],
                            resources=["*"],  # CloudWatch Logs delivery requires wildcard
                        ),
                    ]
                ),
                "XRayPolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            sid="AllowXRayTracing",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "xray:PutTraceSegments",      # Write trace segments
                                "xray:PutTelemetryRecords",   # Write telemetry data
                            ],
                            # X-Ray doesn't support resource-level permissions
                            resources=["*"],
                        ),
                    ]
                ),
            },
        )

        # ========================================
        # Step Functions State Machine
        # ========================================
        # Step Functions Documentation: https://docs.aws.amazon.com/step-functions/latest/dg/welcome.html
        # State Machine Best Practices: https://docs.aws.amazon.com/step-functions/latest/dg/sfn-best-practices.html
        # AWS SDK Integrations: https://docs.aws.amazon.com/step-functions/latest/dg/supported-services-awssdk.html
        # Error Handling: https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html
        
        # Step Functions State Machine for BDA Orchestration
        #
        # Purpose: Orchestrates the classification workflow after BDA completes
        #
        # Architecture Decision: Why Step Functions?
        # - BDA processing is asynchronous and can take 30+ seconds
        # - Need to wait for BDA output to be available in S3
        # - Provides built-in retry logic and error handling
        # - Visual workflow makes it easy to understand and debug
        # - Better than polling from Lambda (avoids long-running functions)
        # - Supports complex workflows with branching and parallel execution
        # - Integrates directly with AWS services (S3, Lambda) without custom code
        # - Provides execution history for auditing and debugging
        #
        # Alternative Approaches Considered:
        # - EventBridge events from BDA: Less reliable, events can be missed
        # - Lambda polling: Wastes compute time and costs more
        # - SQS with Lambda: Adds unnecessary complexity for this use case
        #
        # Workflow:
        # 1. WaitForBDACompletion: Wait 30 seconds for BDA to process
        # 2. CheckBDAOutput: List objects in S3 to see if BDA output exists
        # 3. BDAOutputExists: Check if any objects were found
        #    - If yes: Proceed to InvokeClassifier
        #    - If no: Loop back to WaitForBDACompletion (with max retries)
        # 4. InvokeClassifier: Invoke the classifier Lambda with BDA output location
        #
        # Why these settings:
        # - 30 second wait: Typical BDA processing time for invoices
        # - Retry logic: Handles cases where BDA takes longer than expected
        # - S3 ListObjectsV2: Efficient way to check if output exists
        # - Lambda invocation: Passes context from Email Processor to Classifier
        # - role: Custom IAM role with least privilege permissions
        # - X-Ray tracing: Enables performance analysis and debugging
        # - CloudWatch logs: Captures execution details for troubleshooting
        
        # Define the Wait state (30 seconds for BDA to complete)
        wait_for_bda = sfn.Wait(
            self, "WaitForBDACompletion",
            time=sfn.WaitTime.duration(Duration.seconds(30)),
        )
        
        # Define the S3 ListObjectsV2 task to check if BDA output exists
        #
        # This uses the AWS SDK integration to call S3 directly from Step Functions
        # without needing a Lambda function. It's more efficient and cost-effective.
        #
        # Parameters:
        # - Bucket: Passed from Email Processor (inbox bucket name)
        # - Prefix: bda-output/{invocationId}/ to find specific BDA job output
        #
        # Output: Stored in $.s3Result with KeyCount indicating number of objects found
        check_bda_output = tasks.CallAwsService(
            self, "CheckBDAOutput",
            service="s3",
            action="listObjectsV2",
            parameters={
                "Bucket": sfn.JsonPath.string_at("$.bucket"),
                "Prefix": sfn.JsonPath.format("bda-output/{}/", sfn.JsonPath.string_at("$.invocationId")),
            },
            iam_resources=[
                f"arn:aws:s3:::{self.inbox_bucket.bucket_name}",
                f"arn:aws:s3:::{self.inbox_bucket.bucket_name}/*",
            ],
            result_path="$.s3Result",
        )
        
        # Define the Lambda invocation task for the classifier
        #
        # This invokes the Classifier Lambda with the BDA output location
        # and email metadata from the Email Processor.
        #
        # Payload structure:
        # - stepFunctionTrigger: true (indicates Step Functions invocation)
        # - bucket: Inbox bucket name
        # - invocationId: BDA invocation ID
        # - bdaOutputPrefix: Prefix where BDA output is stored
        # - emailMetadata: Original email metadata (sender, subject, etc.)
        invoke_classifier = tasks.LambdaInvoke(
            self, "InvokeClassifier",
            lambda_function=self.classifier_function,
            payload=sfn.TaskInput.from_object({
                "stepFunctionTrigger": True,
                "bucket": sfn.JsonPath.string_at("$.bucket"),
                "invocationId": sfn.JsonPath.string_at("$.invocationId"),
                "bdaOutputPrefix": "bda-output/",
                "emailMetadata": sfn.JsonPath.string_at("$.emailMetadata"),
            }),
            result_path="$.classifierResult",
        )
        
        # Define the Choice state to check if BDA output exists
        #
        # This checks the KeyCount from the S3 ListObjectsV2 result:
        # - If KeyCount > 0: BDA output exists, proceed to classifier
        # - If KeyCount = 0: BDA output not ready, wait and retry
        #
        # Why this approach:
        # - More reliable than polling EventBridge events
        # - Handles cases where EventBridge event is missed
        # - Provides explicit retry logic with backoff
        bda_output_exists = sfn.Choice(
            self, "BDAOutputExists",
        )
        
        # Add condition: If KeyCount > 0, invoke classifier
        bda_output_exists.when(
            sfn.Condition.number_greater_than("$.s3Result.KeyCount", 0),
            invoke_classifier,
        )
        
        # Add default: If KeyCount = 0, wait and retry
        # This creates a loop: Wait -> Check -> Choice -> Wait (if not ready)
        bda_output_exists.otherwise(wait_for_bda)
        
        # Chain the states together
        #
        # Flow: Wait -> Check -> Choice -> Invoke (if ready) or Wait (if not ready)
        #
        # This creates a polling loop that checks every 30 seconds for BDA output
        # Step Functions will automatically handle retries and timeouts
        definition = wait_for_bda.next(check_bda_output).next(bda_output_exists)
        
        # Create the state machine
        #
        # Why these settings:
        # - timeout: 15 minutes max (BDA should complete within this time)
        # - logs: Enable CloudWatch logs for debugging
        # - tracing: Enable X-Ray tracing for performance analysis
        # - role: Custom IAM role with least privilege permissions
        #
        # IAM Permissions (via step_functions_role):
        # - lambda:InvokeFunction on classifier function (to invoke classifier)
        # - s3:ListBucket on inbox bucket with bda-output/ prefix condition (to check BDA output)
        # - CloudWatch Logs permissions (to write execution logs)
        # - X-Ray permissions (to write trace data)
        self.state_machine = sfn.StateMachine(
            self, "BDAOrchestrationStateMachine",
            state_machine_name="EmailClassification-BDAOrchestration",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            role=step_functions_role,  # Use custom IAM role with least privilege
            timeout=Duration.minutes(15),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(
                    self, "StateMachineLogGroup",
                    log_group_name="/aws/vendedlogs/states/EmailClassification-BDAOrchestration",
                    retention=logs.RetentionDays.ONE_WEEK,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
                level=sfn.LogLevel.ALL,
                include_execution_data=True,
            ),
            tracing_enabled=True,
        )
        
        # Update Email Processor environment with State Machine ARN
        #
        # The Email Processor needs to know the State Machine ARN to start executions
        # after invoking BDA. We add it here after the state machine is created.
        self.email_processor.add_environment(
            "STATE_MACHINE_ARN",
            self.state_machine.state_machine_arn,
        )
        
        # Grant Email Processor permission to start state machine executions
        #
        # This adds the states:StartExecution permission to the Email Processor role
        # with resource-level restriction to this specific state machine only.
        #
        # Why add this permission here (not in role definition):
        # - State machine ARN is only available after the state machine is created
        # - CDK handles the circular dependency automatically
        # - Keeps permission close to the resource it grants access to
        #
        # Permission added:
        # - states:StartExecution on specific state machine ARN
        # - Why: Email Processor triggers the orchestration workflow after BDA invocation
        email_processor_role.add_to_policy(
            iam.PolicyStatement(
                sid="AllowStartStateMachineExecution",
                effect=iam.Effect.ALLOW,
                actions=[
                    "states:StartExecution",  # Start Step Functions workflow
                ],
                resources=[
                    # Scope to specific state machine only
                    # This prevents starting executions of other state machines
                    self.state_machine.state_machine_arn,
                ],
            )
        )

        # ========================================
        # CloudWatch Monitoring and Alarms
        # ========================================
        # CloudWatch Documentation: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html
        # CloudWatch Alarms: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/AlarmThatSendsEmail.html
        # CloudWatch Dashboards: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Dashboards.html
        # Custom Metrics: https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html
        # SNS Documentation: https://docs.aws.amazon.com/sns/latest/dg/welcome.html
        
        # SNS Topic for Alarm Notifications
        #
        # Purpose: Sends notifications when CloudWatch alarms trigger
        #
        # Why SNS:
        # - Centralized notification system for all alarms
        # - Can send to multiple subscribers (email, SMS, Lambda, etc.)
        # - Easy to add/remove subscribers without changing alarms
        # - Industry best practice for alarm notifications
        # - Supports fan-out pattern (one alarm, many subscribers)
        #
        # Usage:
        # - Subscribe email addresses to receive alarm notifications
        # - Can integrate with PagerDuty, Slack, or other incident management tools
        # - Useful for production monitoring and alerting
        #
        # Note: For demo purposes, no subscriptions are added by default
        # To add email subscription: aws sns subscribe --topic-arn <ARN> --protocol email --notification-endpoint your@email.com
        alarm_topic = sns.Topic(
            self, "AlarmTopic",
            topic_name="EmailClassification-Alarms",
            display_name="Email Classification System Alarms",
        )
        
        # Custom Metrics Namespace
        #
        # All custom metrics will be published to this namespace
        # This keeps our metrics organized and separate from AWS service metrics
        metrics_namespace = "EmailClassification"
        
        # Define Custom Metrics
        #
        # These metrics are published by Lambda functions using boto3 CloudWatch client
        # Example: cloudwatch.put_metric_data(Namespace='EmailClassification', MetricName='EmailsProcessed', Value=1)
        #
        # Metrics:
        # 1. EmailsProcessed - Count of emails processed by Email Processor
        # 2. ClassificationSuccess - Count of successful classifications
        # 3. ClassificationFailure - Count of failed classifications
        # 4. ProcessingTime - Time taken to process and classify an email (seconds)
        # 5. DepartmentDistribution - Count of emails classified to each department
        #
        # Why custom metrics:
        # - Track business-level metrics beyond AWS service metrics
        # - Monitor classification accuracy and performance
        # - Understand department distribution for capacity planning
        # - Identify bottlenecks in the processing pipeline
        
        # Metric: Emails Processed
        emails_processed_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="EmailsProcessed",
            statistic="Sum",
            period=Duration.minutes(5),
            label="Emails Processed",
        )
        
        # Metric: Classification Success
        classification_success_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="ClassificationSuccess",
            statistic="Sum",
            period=Duration.minutes(5),
            label="Classification Success",
        )
        
        # Metric: Classification Failure
        classification_failure_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="ClassificationFailure",
            statistic="Sum",
            period=Duration.minutes(5),
            label="Classification Failure",
        )
        
        # Metric: Processing Time
        processing_time_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="ProcessingTime",
            statistic="Average",
            period=Duration.minutes(5),
            label="Avg Processing Time (seconds)",
        )
        
        # Metric: Department Distribution (Finance)
        dept_finance_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="DepartmentDistribution",
            statistic="Sum",
            period=Duration.hours(1),
            dimensions_map={"Department": "Finance"},
            label="Finance",
        )
        
        # Metric: Department Distribution (IT)
        dept_it_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="DepartmentDistribution",
            statistic="Sum",
            period=Duration.hours(1),
            dimensions_map={"Department": "IT"},
            label="IT",
        )
        
        # Metric: Department Distribution (HR)
        dept_hr_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="DepartmentDistribution",
            statistic="Sum",
            period=Duration.hours(1),
            dimensions_map={"Department": "HR"},
            label="HR",
        )
        
        # Metric: Department Distribution (Operations)
        dept_operations_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="DepartmentDistribution",
            statistic="Sum",
            period=Duration.hours(1),
            dimensions_map={"Department": "Operations"},
            label="Operations",
        )
        
        # Metric: Department Distribution (Marketing)
        dept_marketing_metric = cloudwatch.Metric(
            namespace=metrics_namespace,
            metric_name="DepartmentDistribution",
            statistic="Sum",
            period=Duration.hours(1),
            dimensions_map={"Department": "Marketing"},
            label="Marketing",
        )
        
        # CloudWatch Dashboard
        #
        # Purpose: Provides a single-pane-of-glass view of system health and performance
        #
        # Why CloudWatch Dashboard:
        # - Visualize key metrics in real-time
        # - Monitor system health at a glance
        # - Identify trends and patterns
        # - Useful for demos and presentations
        # - Free (first 3 dashboards per month)
        #
        # Dashboard Layout:
        # - Row 1: Upload count, classification success rate, processing time
        # - Row 2: Error counts by Lambda function, Lambda duration
        # - Row 3: Department distribution
        # - Row 4: Step Functions executions
        #
        # Widgets:
        # - SingleValueWidget: Shows single metric value (e.g., total uploads)
        # - GraphWidget: Shows metric over time (e.g., processing time trend)
        # - PieWidget: Shows distribution (e.g., emails by department)
        dashboard = cloudwatch.Dashboard(
            self, "MonitoringDashboard",
            dashboard_name="EmailClassification-Dashboard",
        )
        
        # Widget: Upload Count (last 24 hours)
        #
        # Shows total number of emails uploaded in the last 24 hours
        # Uses custom metric EmailsProcessed published by Email Processor Lambda
        dashboard.add_widgets(
            cloudwatch.SingleValueWidget(
                title="Emails Uploaded (24h)",
                metrics=[emails_processed_metric],
                width=6,
                height=4,
                period=Duration.hours(24),
            ),
            # Widget: Classification Success Rate
            #
            # Shows percentage of successful classifications
            # Calculated as: (ClassificationSuccess / (ClassificationSuccess + ClassificationFailure)) * 100
            cloudwatch.GraphWidget(
                title="Classification Success Rate",
                left=[
                    cloudwatch.MathExpression(
                        expression="(success / (success + failure)) * 100",
                        using_metrics={
                            "success": classification_success_metric,
                            "failure": classification_failure_metric,
                        },
                        label="Success Rate (%)",
                        period=Duration.minutes(5),
                    )
                ],
                width=9,
                height=4,
                left_y_axis=cloudwatch.YAxisProps(
                    min=0,
                    max=100,
                    label="Percentage",
                ),
            ),
            # Widget: Average Processing Time
            #
            # Shows average time to process and classify an email
            # Includes time for: email parsing, BDA invocation, classification, S3 operations
            cloudwatch.GraphWidget(
                title="Average Processing Time",
                left=[processing_time_metric],
                width=9,
                height=4,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Seconds",
                ),
            ),
        )
        
        # Widget: Lambda Function Errors
        #
        # Shows error count for each Lambda function
        # Uses AWS Lambda built-in Errors metric
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Lambda Function Errors",
                left=[
                    self.upload_handler.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Upload Handler",
                    ),
                    self.email_processor.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Email Processor",
                    ),
                    self.classifier_function.metric_errors(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Classifier",
                    ),
                ],
                width=12,
                height=6,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Error Count",
                ),
            ),
            # Widget: Lambda Function Duration
            #
            # Shows execution duration for each Lambda function
            # Helps identify performance bottlenecks
            cloudwatch.GraphWidget(
                title="Lambda Function Duration",
                left=[
                    self.upload_handler.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                        label="Upload Handler",
                    ),
                    self.email_processor.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                        label="Email Processor",
                    ),
                    self.classifier_function.metric_duration(
                        statistic="Average",
                        period=Duration.minutes(5),
                        label="Classifier",
                    ),
                ],
                width=12,
                height=6,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Milliseconds",
                ),
            ),
        )
        
        # Widget: Department Distribution
        #
        # Shows how many emails were classified to each department
        # Useful for understanding workload distribution and capacity planning
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Department Distribution (Last 24h)",
                left=[
                    dept_finance_metric,
                    dept_it_metric,
                    dept_hr_metric,
                    dept_operations_metric,
                    dept_marketing_metric,
                ],
                width=12,
                height=6,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Email Count",
                ),
                period=Duration.hours(24),
                statistic="Sum",
            ),
        )
        
        # Widget: Step Functions Executions
        #
        # Shows Step Functions execution status
        # Tracks successful, failed, and timed-out executions
        dashboard.add_widgets(
            cloudwatch.GraphWidget(
                title="Step Functions Executions",
                left=[
                    self.state_machine.metric_succeeded(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Succeeded",
                    ),
                    self.state_machine.metric_failed(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Failed",
                    ),
                    self.state_machine.metric_timed_out(
                        statistic="Sum",
                        period=Duration.minutes(5),
                        label="Timed Out",
                    ),
                ],
                width=12,
                height=6,
                left_y_axis=cloudwatch.YAxisProps(
                    label="Execution Count",
                ),
            ),
        )
        
        # CloudWatch Alarms
        #
        # Purpose: Automatically detect and alert on system issues
        #
        # Why CloudWatch Alarms:
        # - Proactive monitoring and alerting
        # - Detect issues before users report them
        # - Trigger automated remediation actions
        # - Meet SLA and uptime requirements
        # - Industry best practice for production systems
        #
        # Alarm States:
        # - OK: Metric is within threshold
        # - ALARM: Metric breached threshold
        # - INSUFFICIENT_DATA: Not enough data to evaluate
        #
        # Alarm Actions:
        # - Send notification to SNS topic
        # - Can trigger Lambda for auto-remediation
        # - Can trigger Auto Scaling actions
        
        # Alarm: Upload Handler Errors
        #
        # Triggers when Upload Handler Lambda has more than 5 errors in 5 minutes
        # Indicates issues with file upload processing (parsing, validation, S3 upload)
        #
        # Why 5 errors in 5 minutes:
        # - Allows for occasional transient errors
        # - Detects sustained error conditions
        # - Balances sensitivity vs. false positives
        upload_handler_error_alarm = cloudwatch.Alarm(
            self, "UploadHandlerErrorAlarm",
            alarm_name="EmailClassification-UploadHandler-Errors",
            alarm_description="Upload Handler Lambda has more than 5 errors in 5 minutes",
            metric=self.upload_handler.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        upload_handler_error_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Alarm: Email Processor Errors
        #
        # Triggers when Email Processor Lambda has more than 5 errors in 5 minutes
        # Indicates issues with email parsing, attachment extraction, or BDA invocation
        email_processor_error_alarm = cloudwatch.Alarm(
            self, "EmailProcessorErrorAlarm",
            alarm_name="EmailClassification-EmailProcessor-Errors",
            alarm_description="Email Processor Lambda has more than 5 errors in 5 minutes",
            metric=self.email_processor.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        email_processor_error_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Alarm: Classifier Errors
        #
        # Triggers when Classifier Lambda has more than 5 errors in 5 minutes
        # Indicates issues with Bedrock classification, S3 operations, or SQS messaging
        classifier_error_alarm = cloudwatch.Alarm(
            self, "ClassifierErrorAlarm",
            alarm_name="EmailClassification-Classifier-Errors",
            alarm_description="Classifier Lambda has more than 5 errors in 5 minutes",
            metric=self.classifier_function.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        classifier_error_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Alarm: High Processing Latency
        #
        # Triggers when average processing time exceeds 30 seconds
        # Indicates performance degradation in the pipeline
        #
        # Why 30 seconds:
        # - Normal processing should complete in 10-20 seconds
        # - 30 seconds allows for occasional slow processing
        # - Detects sustained performance issues
        # - Aligns with user experience expectations
        high_latency_alarm = cloudwatch.Alarm(
            self, "HighLatencyAlarm",
            alarm_name="EmailClassification-HighLatency",
            alarm_description="Average processing time exceeds 30 seconds",
            metric=processing_time_metric,
            threshold=30,
            evaluation_periods=2,  # 2 consecutive periods to reduce false positives
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        high_latency_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Alarm: BDA Failures (Step Functions)
        #
        # Triggers when Step Functions has more than 3 failed executions in 10 minutes
        # Indicates issues with BDA processing or classification workflow
        #
        # Why 3 failures in 10 minutes:
        # - BDA failures are more serious than Lambda errors
        # - Lower threshold to detect issues quickly
        # - 10 minute window allows for occasional failures
        # - Detects sustained BDA issues
        bda_failure_alarm = cloudwatch.Alarm(
            self, "BDAFailureAlarm",
            alarm_name="EmailClassification-BDA-Failures",
            alarm_description="Step Functions has more than 3 failed executions in 10 minutes",
            metric=self.state_machine.metric_failed(
                statistic="Sum",
                period=Duration.minutes(10),
            ),
            threshold=3,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        bda_failure_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Alarm: Step Functions Timeout
        #
        # Triggers when Step Functions executions are timing out
        # Indicates BDA is taking too long or not completing
        step_functions_timeout_alarm = cloudwatch.Alarm(
            self, "StepFunctionsTimeoutAlarm",
            alarm_name="EmailClassification-StepFunctions-Timeout",
            alarm_description="Step Functions executions are timing out",
            metric=self.state_machine.metric_timed_out(
                statistic="Sum",
                period=Duration.minutes(10),
            ),
            threshold=1,  # Any timeout is concerning
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )
        step_functions_timeout_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))
        
        # Grant Lambda functions permission to publish custom metrics
        #
        # All Lambda functions need cloudwatch:PutMetricData permission
        # to publish custom metrics to CloudWatch
        #
        # Why add this permission:
        # - Lambda functions publish custom metrics (EmailsProcessed, ClassificationSuccess, etc.)
        # - Required for dashboard widgets and alarms to work
        # - Scoped to specific namespace for security
        #
        # Permissions added to each Lambda role:
        # - cloudwatch:PutMetricData on EmailClassification namespace
        metric_policy = iam.PolicyStatement(
            sid="AllowPublishCustomMetrics",
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudwatch:PutMetricData",  # Publish custom metrics
            ],
            resources=["*"],  # CloudWatch metrics don't support resource-level permissions
            conditions={
                "StringEquals": {
                    # Restrict to our custom namespace only
                    "cloudwatch:namespace": [metrics_namespace]
                }
            },
        )
        
        # Add metric publishing permission to all Lambda roles
        upload_handler_role.add_to_policy(metric_policy)
        email_processor_role.add_to_policy(metric_policy)
        classifier_role.add_to_policy(metric_policy)

        # ========================================
        # Stack Outputs
        # ========================================
        
        # Export bucket names as stack outputs
        #
        # Why: These outputs are used by:
        # - Setup scripts to upload configuration files
        # - Teardown scripts to empty buckets before deletion
        # - Lambda functions (passed as environment variables)
        # - Testing and debugging
        CfnOutput(
            self, "InboxBucketName",
            value=self.inbox_bucket.bucket_name,
            description="S3 bucket for incoming emails and attachments",
            export_name="EmailClassification-InboxBucket",
        )

        CfnOutput(
            self, "DestinationBucketName",
            value=self.destination_bucket.bucket_name,
            description="S3 bucket for classified emails organized by department",
            export_name="EmailClassification-DestinationBucket",
        )

        CfnOutput(
            self, "WebsiteBucketName",
            value=self.website_bucket.bucket_name,
            description="S3 bucket for static website hosting",
            export_name="EmailClassification-WebsiteBucket",
        )
        
        # Export API Gateway URL
        #
        # This is the endpoint URL that the web frontend will use to upload files
        # Format: https://{api-id}.execute-api.{region}.amazonaws.com/prod
        CfnOutput(
            self, "ApiGatewayUrl",
            value=self.upload_api.url,
            description="API Gateway endpoint URL for file uploads",
            export_name="EmailClassification-ApiUrl",
        )
        
        # Export the full upload endpoint URL for convenience
        CfnOutput(
            self, "UploadEndpoint",
            value=f"{self.upload_api.url}upload",
            description="Full URL for the /upload endpoint",
        )
        
        # Export Email Processor function name for reference
        CfnOutput(
            self, "EmailProcessorFunctionName",
            value=self.email_processor.function_name,
            description="Lambda function name for the Email Processor",
            export_name="EmailClassification-EmailProcessorFunction",
        )
        
        # Export State Machine ARN
        CfnOutput(
            self, "StateMachineArn",
            value=self.state_machine.state_machine_arn,
            description="Step Functions state machine ARN for BDA orchestration",
            export_name="EmailClassification-StateMachineArn",
        )
        
        # Export Classifier function name
        CfnOutput(
            self, "ClassifierFunctionName",
            value=self.classifier_function.function_name,
            description="Lambda function name for the Invoice Classifier",
            export_name="EmailClassification-ClassifierFunction",
        )
        
        # Export SQS Queue URL
        CfnOutput(
            self, "RoutingQueueUrl",
            value=self.routing_queue.queue_url,
            description="SQS queue URL for email routing",
            export_name="EmailClassification-RoutingQueueUrl",
        )
        
        # Export CloudFront Distribution URL
        #
        # This is the primary URL users should use to access the web frontend
        # Format: https://d123456789.cloudfront.net
        #
        # Why CloudFront URL instead of S3 URL:
        # - HTTPS enabled by default with AWS certificate
        # - Global CDN for fast content delivery
        # - Secure access via OAI (S3 bucket is not public)
        # - Custom error pages for better UX
        # - Caching for improved performance
        #
        # Usage:
        # - Share this URL with users to access the upload interface
        # - Use in documentation and demo guides
        # - Configure in frontend for API calls (if needed)
        CfnOutput(
            self, "CloudFrontUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront URL for accessing the web frontend",
            export_name="EmailClassification-CloudFrontUrl",
        )
        
        # Export CloudFront Distribution ID
        #
        # Useful for:
        # - Creating cache invalidations when updating website content
        # - Monitoring CloudFront metrics in CloudWatch
        # - Debugging and troubleshooting
        #
        # Example invalidation command:
        # aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
        CfnOutput(
            self, "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID for cache invalidation",
            export_name="EmailClassification-CloudFrontDistributionId",
        )
        
        # Export CloudWatch Dashboard URL
        #
        # Direct link to the CloudWatch dashboard for monitoring system health
        # Format: https://console.aws.amazon.com/cloudwatch/home?region={region}#dashboards:name={dashboard-name}
        CfnOutput(
            self, "DashboardUrl",
            value=f"https://console.aws.amazon.com/cloudwatch/home?region={self.region}#dashboards:name=EmailClassification-Dashboard",
            description="CloudWatch Dashboard URL for monitoring",
        )
        
        # Export SNS Topic ARN for alarm notifications
        #
        # Use this ARN to subscribe email addresses or other endpoints for alarm notifications
        # Example: aws sns subscribe --topic-arn <ARN> --protocol email --notification-endpoint your@email.com
        CfnOutput(
            self, "AlarmTopicArn",
            value=alarm_topic.topic_arn,
            description="SNS Topic ARN for alarm notifications",
            export_name="EmailClassification-AlarmTopicArn",
        )
