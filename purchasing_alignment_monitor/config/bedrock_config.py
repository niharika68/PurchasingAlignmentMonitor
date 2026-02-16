"""
Bedrock Configuration Module
Handles AWS Bedrock Knowledge Base connections and settings.
"""

import os
import boto3
from dotenv import load_dotenv

load_dotenv()


class BedrockConfig:
    """Configuration for AWS Bedrock and Knowledge Base integration."""

    def __init__(self):
        """Initialize Bedrock configuration from environment variables."""
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.knowledge_base_id = os.getenv("KNOWLEDGE_BASE_ID")
        self.model_arn = os.getenv("MODEL_ARN")
        
    def get_bedrock_agent_runtime(self):
        """Create and return Bedrock Agent Runtime client."""
        return boto3.client(
            service_name="bedrock-agent-runtime",
            region_name=self.aws_region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def get_bedrock_client(self):
        """Create and return Bedrock client."""
        return boto3.client(
            service_name="bedrock",
            region_name=self.aws_region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )

    def validate_config(self) -> bool:
        """Validate that required configuration is present."""
        required_fields = [
            self.aws_region,
            self.aws_access_key_id,
            self.aws_secret_access_key,
            self.knowledge_base_id,
            self.model_arn,
        ]
        return all(required_fields)


# Global config instance
bedrock_config = BedrockConfig()
