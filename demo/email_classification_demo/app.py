#!/usr/bin/env python3
import os
import aws_cdk as cdk
from email_classification.email_classification_stack import EmailClassificationStack

app = cdk.App()

# Create the main stack for the email classification system
# This stack provisions all AWS resources needed for the demo
EmailClassificationStack(
    app, 
    "EmailClassificationStack",
    description="Email Classification Demo with Amazon Bedrock Data Automation",
    # Uncomment to specify AWS account and region
    # env=cdk.Environment(
    #     account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    #     region=os.getenv('CDK_DEFAULT_REGION')
    # ),
)

app.synth()
