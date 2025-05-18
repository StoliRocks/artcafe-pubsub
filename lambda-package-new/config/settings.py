import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


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
    
    # Cognito Settings
    COGNITO_USER_POOL_ID: str = Field(default="us-east-1_YUMQS3O2J", env="COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID: str = Field(default="34srilubaou3u1hu626tmioodi", env="COGNITO_CLIENT_ID")
    COGNITO_REGION: str = Field(default="us-east-1", env="COGNITO_REGION")
    COGNITO_JWKS_URL: Optional[str] = None  # Will be constructed from pool ID and region
    COGNITO_ISSUER: Optional[str] = None   # Will be constructed from pool ID and region
    
    # Supported JWT algorithms (both HS256 for internal and RS256 for Cognito)
    JWT_ALGORITHMS: List[str] = Field(default=["HS256", "RS256"])

    def __init__(self, **values):
        super().__init__(**values)
        # Construct Cognito URLs from pool ID and region
        if self.COGNITO_USER_POOL_ID and self.COGNITO_REGION:
            self.COGNITO_JWKS_URL = f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/{self.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
            self.COGNITO_ISSUER = f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/{self.COGNITO_USER_POOL_ID}"

    # NATS Settings
    NATS_SERVERS: List[str] = Field(default=["nats://localhost:4222"])
    NATS_USERNAME: Optional[str] = None
    NATS_PASSWORD: Optional[str] = None
    NATS_TOKEN: Optional[str] = None
    NATS_TLS_ENABLED: bool = False
    NATS_TLS_CERT_PATH: Optional[str] = None
    NATS_TLS_KEY_PATH: Optional[str] = None
    NATS_TLS_CA_PATH: Optional[str] = None
    NATS_ENABLED: bool = Field(default=False)  # Disable NATS by default

    # AWS Settings
    AWS_REGION: str = Field(default="us-east-1")
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # DynamoDB Settings
    DYNAMODB_ENDPOINT: Optional[str] = None
    DYNAMODB_TABLE_PREFIX: str = Field(default="artcafe-")
    AGENT_TABLE_NAME: str = Field(default="artcafe-agents")
    SSH_KEY_TABLE_NAME: str = Field(default="artcafe-ssh-keys")
    CHANNEL_TABLE_NAME: str = Field(default="artcafe-channels")
    TENANT_TABLE_NAME: str = Field(default="artcafe-tenants")
    USAGE_METRICS_TABLE_NAME: str = Field(default="artcafe-usage-metrics")
    CHANNEL_SUBSCRIPTIONS_TABLE_NAME: str = Field(default="artcafe-channel-subscriptions")
    TERMS_ACCEPTANCE_TABLE_NAME: str = Field(default="artcafe-terms-acceptance")
    USER_TENANT_TABLE_NAME: str = Field(default="artcafe-user-tenants")
    USER_TENANT_INDEX_TABLE_NAME: str = Field(default="artcafe-user-tenant-index")
    
    # API Key settings
    API_KEY_HEADER_NAME: str = Field(default="x-api-key")
    TENANT_ID_HEADER_NAME: str = Field(default="x-tenant-id")
    
    # Default tenant settings
    DEFAULT_TENANT_ID: str = Field(default="tenant-default")
    
    # CORS settings
    CORS_ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:3001",
            "https://www.artcafe.ai",
            "https://artcafe.ai",
            "https://d1isgvgjiqe68i.cloudfront.net",
            "http://3.229.1.223:3000"
        ],
        env="CORS_ALLOWED_ORIGINS"
    )
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, env="CORS_ALLOW_CREDENTIALS")
    CORS_ALLOW_ALL_ORIGINS: bool = Field(default=False, env="CORS_ALLOW_ALL_ORIGINS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def __init__(self, **data):
        super().__init__(**data)
        # Construct Cognito URLs from user pool ID and region
        if self.COGNITO_USER_POOL_ID and self.COGNITO_REGION:
            self.COGNITO_JWKS_URL = f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/{self.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
            self.COGNITO_ISSUER = f"https://cognito-idp.{self.COGNITO_REGION}.amazonaws.com/{self.COGNITO_USER_POOL_ID}"


# Create settings instance
settings = Settings()