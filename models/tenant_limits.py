from typing import Dict, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from .base import BaseSchema


class TenantLimits(BaseModel):
    """Tenant usage limits"""
    max_agents: int = Field(default=10, description="Maximum number of agents")
    max_messages_per_month: int = Field(default=100000, description="Maximum messages per month")
    max_storage_gb: float = Field(default=10.0, description="Maximum storage in GB")
    max_concurrent_connections: int = Field(default=50, description="Maximum concurrent WebSocket connections")
    max_api_calls_per_minute: int = Field(default=1000, description="Maximum API calls per minute")
    max_channels: int = Field(default=100, description="Maximum number of channels")
    max_ssh_keys: int = Field(default=50, description="Maximum number of SSH keys")
    
    # Feature flags
    custom_domains_enabled: bool = Field(default=False)
    advanced_analytics_enabled: bool = Field(default=False)
    priority_support: bool = Field(default=False)


class TenantUsage(BaseModel):
    """Current tenant usage metrics"""
    agent_count: int = Field(default=0)
    messages_this_month: int = Field(default=0)
    storage_used_gb: float = Field(default=0.0)
    concurrent_connections: int = Field(default=0)
    api_calls_this_minute: int = Field(default=0)
    channel_count: int = Field(default=0)
    ssh_key_count: int = Field(default=0)
    
    last_month_reset: datetime = Field(default_factory=datetime.utcnow)
    last_api_call: datetime = Field(default_factory=datetime.utcnow)


class SubscriptionPlan(BaseModel):
    """Subscription plan definition"""
    name: str
    tier: str  # beta, free, basic, pro, enterprise
    price_monthly: float
    price_yearly: float
    limits: TenantLimits
    description: Optional[str] = None
    features: Dict[str, bool] = Field(default_factory=dict)


# Predefined subscription plans - matching frontend pricing exactly
SUBSCRIPTION_PLANS = {
    
    "starter": SubscriptionPlan(
        name="Starter",
        tier="starter", 
        price_monthly=0.0,
        price_yearly=0.0,
        limits=TenantLimits(
            max_agents=3,
            max_messages_per_month=10000,
            max_storage_gb=1.0,
            max_concurrent_connections=5,
            max_api_calls_per_minute=100,
            max_channels=10,
            max_ssh_keys=5,
            custom_domains_enabled=False,
            advanced_analytics_enabled=False,
            priority_support=False
        ),
        description="Perfect for testing your AI agents and validating ideas."
    ),
    
    "growth": SubscriptionPlan(
        name="Growth",
        tier="growth",
        price_monthly=29.00,
        price_yearly=290.00,
        limits=TenantLimits(
            max_agents=10,
            max_messages_per_month=100000,
            max_storage_gb=10.0,
            max_concurrent_connections=20,
            max_api_calls_per_minute=500,
            max_channels=100,
            max_ssh_keys=20,
            custom_domains_enabled=False,
            advanced_analytics_enabled=True,
            priority_support=False
        ),
        description="Build your first production-ready agent ecosystem."
    ),
    
    "scale": SubscriptionPlan(
        name="Scale",
        tier="scale",
        price_monthly=99.00,
        price_yearly=990.00,
        limits=TenantLimits(
            max_agents=50,
            max_messages_per_month=500000,
            max_storage_gb=50.0,
            max_concurrent_connections=100,
            max_api_calls_per_minute=2000,
            max_channels=500,
            max_ssh_keys=100,
            custom_domains_enabled=True,
            advanced_analytics_enabled=True,
            priority_support=True
        ),
        description="Scale your agent ecosystem with advanced features."
    ),
    
    "enterprise": SubscriptionPlan(
        name="Enterprise",
        tier="enterprise",
        price_monthly=0.0,  # Custom pricing
        price_yearly=0.0,
        limits=TenantLimits(
            max_agents=999999,  # Unlimited
            max_messages_per_month=999999999,
            max_storage_gb=999999.0,
            max_concurrent_connections=999999,
            max_api_calls_per_minute=999999,
            max_channels=999999,
            max_ssh_keys=999999,
            custom_domains_enabled=True,
            advanced_analytics_enabled=True,
            priority_support=True
        ),
        description="Custom solutions for large-scale deployments."
    ),
    
    # Legacy mappings for backward compatibility
    "free": SubscriptionPlan(
        name="Starter",
        tier="starter",
        price_monthly=0.0,
        price_yearly=0.0,
        limits=TenantLimits(
            max_agents=3,
            max_messages_per_month=10000,
            max_storage_gb=1.0,
            max_concurrent_connections=5,
            max_api_calls_per_minute=100,
            max_channels=10,
            max_ssh_keys=5,
            custom_domains_enabled=False,
            advanced_analytics_enabled=False,
            priority_support=False
        ),
        description="Perfect for testing your AI agents and validating ideas."
    ),
    
    "basic": SubscriptionPlan(
        name="Growth",
        tier="growth",
        price_monthly=29.00,
        price_yearly=290.00,
        limits=TenantLimits(
            max_agents=10,
            max_messages_per_month=100000,
            max_storage_gb=10.0,
            max_concurrent_connections=20,
            max_api_calls_per_minute=500,
            max_channels=100,
            max_ssh_keys=20,
            custom_domains_enabled=False,
            advanced_analytics_enabled=True,
            priority_support=False
        ),
        description="Build your first production-ready agent ecosystem."
    ),
    
    "pro": SubscriptionPlan(
        name="Scale",
        tier="scale",
        price_monthly=99.00,
        price_yearly=990.00,
        limits=TenantLimits(
            max_agents=50,
            max_messages_per_month=500000,
            max_storage_gb=50.0,
            max_concurrent_connections=100,
            max_api_calls_per_minute=2000,
            max_channels=500,
            max_ssh_keys=100,
            custom_domains_enabled=True,
            advanced_analytics_enabled=True,
            priority_support=True
        ),
        description="Scale your agent ecosystem with advanced features."
    )
}