#!/usr/bin/env python3
import os
import aws_cdk as cdk
from prompt_caching.prompt_caching_stack import PromptCachingStack

app = cdk.App()

# Create the main stack for the prompt caching demonstration system
# This stack provisions all AWS resources needed for the demo
PromptCachingStack(
    app, 
    "PromptCachingStack",
    description="Prompt Caching Demo with Amazon Bedrock - Educational demonstration of prompt caching best practices",
    # Uncomment to specify AWS account and region
    # env=cdk.Environment(
    #     account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    #     region=os.getenv('CDK_DEFAULT_REGION')
    # ),
)

app.synth()
