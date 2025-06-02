from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from auth.dependencies import get_current_tenant_id
from api.services import limits_service, tenant_service, usage_service
from models import TenantLimits, TenantUsage, SUBSCRIPTION_PLANS

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/usage-summary")
async def get_usage_summary(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get current usage summary for the tenant
    
    Returns:
        Usage metrics compared to limits
    """
    try:
        summary = await limits_service.get_usage_summary(tenant_id)
        return summary
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/info")
async def get_billing_info(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get billing information for the tenant
    
    Returns:
        Current plan, billing cycle, etc.
    """
    try:
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Get current plan details
        plan = SUBSCRIPTION_PLANS.get(tenant.subscription_plan, SUBSCRIPTION_PLANS["free"])
        
        return {
            "tenant_id": tenant_id,
            "plan": tenant.subscription_plan,
            "plan_details": {
                "name": plan.name,
                "price_monthly": plan.price_monthly,
                "price_yearly": plan.price_yearly,
                "description": plan.description
            },
            "billing_cycle": "monthly" if plan.price_monthly > 0 else "free",
            "next_billing_date": None,  # Free plans don't have billing dates
            "amount": plan.price_monthly,
            "currency": "USD",
            "payment_method": "credit_card" if tenant.stripe_customer_id else None,
            "status": tenant.payment_status,
            "stripe_customer_id": tenant.stripe_customer_id,
            "stripe_subscription_id": tenant.stripe_subscription_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/plans")
async def get_subscription_plans():
    """
    Get available subscription plans
    
    Returns:
        List of available plans with details
    """
    plans = []
    
    for tier, plan in SUBSCRIPTION_PLANS.items():
        plans.append({
            "id": tier,
            "name": plan.name,
            "tier": plan.tier,
            "price_monthly": plan.price_monthly,
            "price_yearly": plan.price_yearly,
            "description": plan.description,
            "limits": plan.limits.dict(),
            "features": {
                "custom_domains": plan.limits.custom_domains_enabled,
                "advanced_analytics": plan.limits.advanced_analytics_enabled,
                "priority_support": plan.limits.priority_support
            }
        })
    
    return {"plans": plans}


@router.post("/upgrade")
async def upgrade_subscription(
    plan_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Upgrade subscription to a new plan
    
    Args:
        plan_id: Target plan ID
        
    Returns:
        Upgrade confirmation
    """
    try:
        # Validate plan exists
        if plan_id not in SUBSCRIPTION_PLANS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid plan: {plan_id}"
            )
        
        # Get tenant
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Check if already on this plan
        if tenant.subscription_plan == plan_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Already on this plan"
            )
        
        # Update tenant plan (in production, this would integrate with Stripe)
        new_plan = SUBSCRIPTION_PLANS[plan_id]
        
        await tenant_service.update_tenant(tenant_id, {
            "subscription_plan": plan_id,
            "limits": new_plan.limits.dict(),
            "payment_status": "active"
        })
        
        return {
            "status": "success",
            "message": f"Upgraded to {new_plan.name} plan",
            "plan": plan_id,
            "new_limits": new_plan.limits.dict()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )