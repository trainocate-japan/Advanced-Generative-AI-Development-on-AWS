from aws_cdk import (
    Stack,
    aws_s3 as s3,
    aws_lambda as lambda_,
    aws_apigateway as apigateway,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
    aws_logs as logs,
    CfnOutput,
    RemovalPolicy,
    Duration,
)
from constructs import Construct


class PromptCachingStack(Stack):
    """
    CDK Stack for Prompt Caching Demo
    
    This stack creates all AWS infrastructure needed for the educational
    prompt caching demonstration including:
    - S3 buckets for document storage and website hosting
    - Lambda functions for query processing
    - API Gateway for HTTP endpoints
    - CloudFront distribution for global content delivery
    - IAM roles with least-privilege permissions
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ===================================================================
        # S3 Buckets (Task 2.1)
        # ===================================================================
        
        # Document bucket for AWS CAF content
        self.document_bucket = s3.Bucket(
            self,
            "DocumentBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30),
                    enabled=True
                )
            ],
            versioned=False,
        )
        
        # Website bucket for static files
        self.website_bucket = s3.Bucket(
            self,
            "WebsiteBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(30),
                    enabled=True
                )
            ],
            versioned=False,
        )
        
        # ===================================================================
        # CloudFront Origin Access Identity (Task 2.2)
        # ===================================================================
        
        # Create Origin Access Identity for CloudFront to access S3
        origin_access_identity = cloudfront.OriginAccessIdentity(
            self,
            "WebsiteOAI",
            comment="OAI for Prompt Caching Demo website"
        )
        
        # Grant CloudFront OAI read access to website bucket
        self.website_bucket.grant_read(origin_access_identity)
        
        # CloudFront distribution for website
        self.distribution = cloudfront.Distribution(
            self,
            "WebsiteDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_identity(
                    self.website_bucket,
                    origin_access_identity=origin_access_identity
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                compress=True,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5)
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.minutes(5)
                )
            ],
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            price_class=cloudfront.PriceClass.PRICE_CLASS_ALL,
        )
        
        # ===================================================================
        # Lambda Execution Role (Task 2.3)
        # ===================================================================
        
        # Create IAM role for query handler Lambda with least-privilege permissions
        self.lambda_role = iam.Role(
            self,
            "QueryHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for prompt caching query handler Lambda",
        )
        
        # Grant S3 read permissions for document bucket
        self.document_bucket.grant_read(self.lambda_role)
        
        # Grant Bedrock invoke permissions for Converse API
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/*"
                ]
            )
        )
        
        # Grant CloudWatch Logs permissions
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/lambda/*"
                ]
            )
        )
        
        # ===================================================================
        # Lambda Function (Task 2.4)
        # ===================================================================
        
        # Create query handler Lambda function
        self.query_handler = lambda_.Function(
            self,
            "QueryHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="query_handler.lambda_handler",
            code=lambda_.Code.from_asset("lambda_functions"),
            role=self.lambda_role,
            memory_size=1024,
            timeout=Duration.seconds(60),
            environment={
                "DOCUMENT_BUCKET": self.document_bucket.bucket_name,
                "PYTHON_SCRIPT_PATH": "/var/task/05_prompt_caching.py"
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        
        # ===================================================================
        # API Gateway (Task 2.5)
        # ===================================================================
        
        # Create REST API
        self.api = apigateway.RestApi(
            self,
            "PromptCachingApi",
            rest_api_name="Prompt Caching Demo API",
            description="API for prompt caching demonstration",
            deploy_options=apigateway.StageOptions(
                throttling_rate_limit=100,
                throttling_burst_limit=200,
                logging_level=apigateway.MethodLoggingLevel.INFO,
            ),
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                    "X-Amz-Security-Token"
                ],
                allow_credentials=False,
            ),
        )
        
        # Lambda integration for query endpoint
        query_integration = apigateway.LambdaIntegration(
            self.query_handler,
            proxy=True,
        )
        
        # POST /query endpoint
        query_resource = self.api.root.add_resource("query")
        query_resource.add_method("POST", query_integration)
        
        # GET /health endpoint
        health_resource = self.api.root.add_resource("health")
        health_resource.add_method(
            "GET",
            apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code="200",
                        response_templates={
                            "application/json": '{"status": "healthy", "service": "prompt-caching-demo"}'
                        }
                    )
                ],
                request_templates={
                    "application/json": '{"statusCode": 200}'
                }
            ),
            method_responses=[
                apigateway.MethodResponse(
                    status_code="200",
                    response_models={
                        "application/json": apigateway.Model.EMPTY_MODEL
                    }
                )
            ]
        )
        
        # ===================================================================
        # CloudFormation Outputs (Task 2.6)
        # ===================================================================
        
        # Output CloudFront URL
        CfnOutput(
            self,
            "CloudFrontURL",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="CloudFront distribution URL for accessing the web interface",
            export_name=f"{self.stack_name}-CloudFrontURL"
        )
        
        # Output API Gateway URL
        CfnOutput(
            self,
            "ApiGatewayURL",
            value=self.api.url,
            description="API Gateway endpoint URL",
            export_name=f"{self.stack_name}-ApiGatewayURL"
        )
        
        # Output document bucket name
        CfnOutput(
            self,
            "DocumentBucketName",
            value=self.document_bucket.bucket_name,
            description="S3 bucket name for document storage",
            export_name=f"{self.stack_name}-DocumentBucket"
        )
        
        # Output website bucket name
        CfnOutput(
            self,
            "WebsiteBucketName",
            value=self.website_bucket.bucket_name,
            description="S3 bucket name for website files",
            export_name=f"{self.stack_name}-WebsiteBucket"
        )
        
        # Output CloudFront distribution ID
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID for cache invalidation",
            export_name=f"{self.stack_name}-CloudFrontDistributionId"
        )
