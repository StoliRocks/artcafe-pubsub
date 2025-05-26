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
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRIAL = "trial"
    EXPIRED = "expired"


class TenantBase(BaseModel):
    """Base tenant model"""
    name: str
    admin_email: EmailStr
    subscription_tier: str = SubscriptionTier.BASIC
    
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
    trial_days: int = 14  # Default trial period in days
    # Terms acceptance data
    terms_acceptance: Optional[Dict] = None  # Include IP, timestamp, versions, etc.


class Tenant(TenantBase, BaseSchema):
    """Tenant model"""
    tenant_id: str = Field(..., alias="id")
    metadata: Optional[Dict] = None
    status: str = "active"

    # Payment fields
    payment_status: str = PaymentStatus.TRIAL
    subscription_expires_at: Optional[datetime] = None
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
        allowed_statuses = [PaymentStatus.ACTIVE, PaymentStatus.INACTIVE,
                           PaymentStatus.TRIAL, PaymentStatus.EXPIRED]
        if v not in allowed_statuses:
            raise ValueError(f"Payment status must be one of: {', '.join(allowed_statuses)}")
        return v

    @validator('subscription_expires_at', pre=True, always=True)
    def set_expiry_date(cls, v, values):
        """Set subscription expiry date if not provided"""
        if v:
            return v

        # If new tenant (no ID) or in trial, set expiry based on creation date
        is_new = 'id' not in values or not values['id']
        is_trial = 'payment_status' in values and values['payment_status'] == PaymentStatus.TRIAL

        if is_new or is_trial:
            # Default 14-day trial
            return datetime.utcnow() + timedelta(days=14)

        return datetime.utcnow() + timedelta(days=30)  # Default 30-day subscription

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