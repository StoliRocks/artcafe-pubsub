from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from .base import BaseSchema


class SubscriptionTier:
    """Subscription tier enumeration"""
    FREE = "Free"
    STARTER = "Starter"
    GROWTH = "Growth"
    SCALE = "Scale"
    ENTERPRISE = "Enterprise"


class SubscriptionStatus:
    """Subscription status enumeration"""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"


class Subscription(BaseSchema):
    """Subscription model for tenant billing"""
    tenant_id: str = Field(..., description="Tenant ID")
    user_id: str = Field(..., description="User ID who owns the subscription")
    subscription_id: Optional[str] = Field(None, description="External subscription ID (e.g., PayPal)")
    plan_id: Optional[str] = Field(None, description="External plan ID")
    
    tier_name: str = Field(default=SubscriptionTier.STARTER, description="Subscription tier name")
    billing_cycle: str = Field(default="monthly", description="Billing cycle: monthly or annually")
    status: str = Field(default=SubscriptionStatus.ACTIVE, description="Subscription status")
    
    # Dates
    start_date: Optional[datetime] = Field(default_factory=datetime.utcnow)
    end_date: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    
    # Pricing
    amount: float = Field(default=0.0, description="Subscription amount")
    currency: str = Field(default="USD", description="Currency code")
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "subscription_id": "SUB-123456789",
                "plan_id": "P-2MX74475V9687691NNAWRYIA",
                "tier_name": "Basic",
                "billing_cycle": "monthly",
                "status": "active",
                "amount": 9.99,
                "currency": "USD"
            }
        }


class SubscriptionCreate(BaseModel):
    """Create subscription request"""
    subscription_id: str = Field(..., description="External subscription ID")
    plan_id: str = Field(..., description="External plan ID")
    tier_name: str = Field(..., description="Subscription tier name")
    billing_cycle: str = Field(..., description="Billing cycle")
    user_id: Optional[str] = Field(None, description="User ID")


class SubscriptionResponse(BaseModel):
    """Subscription response model"""
    id: str
    tenant_id: str
    user_id: str
    subscription_id: Optional[str]
    plan_id: Optional[str]
    tier_name: str
    billing_cycle: str
    status: str
    start_date: datetime
    end_date: Optional[datetime]
    amount: float
    currency: str
    created_at: datetime
    updated_at: datetime