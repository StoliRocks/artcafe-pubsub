from typing import Dict, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field, EmailStr, validator

from .base import BaseSchema
from .tenant_limits import TenantLimits, TenantUsage, SubscriptionPlan, SUBSCRIPTION_PLANS


class SubscriptionTier(str):
    """Subscription tier enum"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PaymentStatus(str):
    """Payment status enum"""
    ACTIVE = "active"  # Active subscription (free or paid)
    INACTIVE = "inactive"  # Subscription cancelled or payment failed
    TRIAL = "trial"  # Legacy - no longer used
    EXPIRED = "expired"  # Legacy - no longer used


class TenantBase(BaseModel):
    """Base tenant model"""
    name: str
    admin_email: EmailStr
    subscription_tier: str = SubscriptionTier.BASIC
    
    # NKey authentication fields
    nkey_public: Optional[str] = None  # Public NKey for tenant authentication
    issuer_key: Optional[str] = None  # For issuing JWT tokens to clients
    
    # Branding and organization info
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = "#0284c7"  # Ocean-600
    secondary_color: Optional[str] = "#0ea5e9"  # Ocean-500

    @validator('subscription_tier')
    def validate_tier(cls, v):
        """Validate subscription tier"""
        allowed_tiers = [SubscriptionTier.FREE, SubscriptionTier.BASIC,
                         SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE]
        if v not in allowed_tiers:
            raise ValueError(f"Subscription tier must be one of: {', '.join(allowed_tiers)}")
        return v


class TenantCreate(TenantBase):
    """Tenant creation model"""
    metadata: Optional[Dict] = None
    # Terms acceptance data
    terms_acceptance: Optional[Dict] = None  # Include IP, timestamp, versions, etc.


class Tenant(TenantBase, BaseSchema):
    """Tenant model"""
    tenant_id: str = Field(..., alias="id")
    metadata: Optional[Dict] = None
    status: str = "active"

    # Payment fields
    payment_status: str = PaymentStatus.ACTIVE  # Default to active for free plans
    subscription_expires_at: Optional[datetime] = None  # Deprecated - kept for backward compatibility
    last_payment_date: Optional[datetime] = None
    payment_reference: Optional[str] = None

    # Subscription details
    subscription_plan: str = Field(default="free", description="Current subscription plan")
    limits: TenantLimits = Field(default_factory=lambda: SUBSCRIPTION_PLANS["free"].limits)
    usage: TenantUsage = Field(default_factory=TenantUsage)
    
    # Stripe/billing integration
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    @validator('payment_status')
    def validate_payment_status(cls, v):
        """Validate payment status"""
        # Only allow ACTIVE and INACTIVE for new tenants
        # TRIAL and EXPIRED are legacy values kept for backward compatibility
        allowed_statuses = [PaymentStatus.ACTIVE, PaymentStatus.INACTIVE,
                           PaymentStatus.TRIAL, PaymentStatus.EXPIRED]
        if v not in allowed_statuses:
            raise ValueError(f"Payment status must be one of: {', '.join(allowed_statuses)}")
        return v

    @validator('subscription_expires_at', pre=True, always=True)
    def set_expiry_date(cls, v, values):
        """Set subscription expiry date if not provided - deprecated field"""
        # This field is deprecated but kept for backward compatibility
        # Free plans don't expire, they just have usage limits
        return v  # Return None for free plans

    class Config:
        allow_population_by_field_name = True


class TenantUpdate(BaseModel):
    """Tenant update model"""
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    secondary_color: Optional[str] = None
    admin_email: Optional[EmailStr] = None
    subscription_tier: Optional[str] = None
    
    @validator('subscription_tier')
    def validate_tier(cls, v):
        """Validate subscription tier if provided"""
        if v is not None:
            allowed_tiers = [SubscriptionTier.FREE, SubscriptionTier.BASIC,
                             SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE]
            if v not in allowed_tiers:
                raise ValueError(f"Subscription tier must be one of: {', '.join(allowed_tiers)}")
        return v


class TenantResponse(BaseModel):
    """Tenant response model"""
    tenant_id: str
    api_key: Optional[str] = None
    admin_token: Optional[str] = None
    success: bool = True