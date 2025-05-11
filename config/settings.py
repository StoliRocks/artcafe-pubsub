import os
from typing import List, Optional
from pydantic import BaseSettings, Field


class Settings(BaseSettings):
    """Application settings"""
    # App settings
    APP_NAME: str = "ArtCafe PubSub Service"
    API_VERSION: str = "v1"
    DEBUG: bool = Field(default=False)
    
    # JWT Settings
    JWT_SECRET_KEY: str = Field("", env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # NATS Settings
    NATS_SERVERS: List[str] = Field(default=["nats://localhost:4222"])
    NATS_USERNAME: Optional[str] = None
    NATS_PASSWORD: Optional[str] = None
    NATS_TOKEN: Optional[str] = None
    NATS_TLS_ENABLED: bool = False
    NATS_TLS_CERT_PATH: Optional[str] = None
    NATS_TLS_KEY_PATH: Optional[str] = None
    NATS_TLS_CA_PATH: Optional[str] = None

    # AWS Settings
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # DynamoDB Settings
    DYNAMODB_ENDPOINT: Optional[str] = None
    AGENT_TABLE_NAME: str = Field(default="artcafe-agents")
    SSH_KEY_TABLE_NAME: str = Field(default="artcafe-ssh-keys")
    CHANNEL_TABLE_NAME: str = Field(default="artcafe-channels")
    TENANT_TABLE_NAME: str = Field(default="artcafe-tenants")
    USAGE_METRICS_TABLE_NAME: str = Field(default="artcafe-usage-metrics")
    
    # API Key settings
    API_KEY_HEADER_NAME: str = Field(default="x-api-key")
    TENANT_ID_HEADER_NAME: str = Field(default="x-tenant-id")
    
    # Default tenant settings
    DEFAULT_TENANT_ID: str = Field(default="tenant-default")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()