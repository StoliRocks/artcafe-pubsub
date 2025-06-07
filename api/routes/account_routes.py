"""
Account routes (maps to tenant for backward compatibility)
Handles organization/account management with optional NKey support
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict
import nkeys
from datetime import datetime, timezone

from models.tenant import Tenant, TenantCreate, TenantUpdate
from auth.dependencies import get_current_user, get_current_tenant_id
from api.services.tenant_service import tenant_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("/", response_model=List[Dict])
async def list_accounts(
    current_user: dict = Depends(get_current_user),
    limit: int = 100
):
    """List all accounts (maps to tenants)"""
    # Get user's tenants
    from api.services.user_tenant_service import user_tenant_service
    user_tenants = await user_tenant_service.get_user_tenants(current_user["user_id"])
    
    accounts = []
    for ut in user_tenants:
        tenant = await tenant_service.get_tenant(ut.tenant_id)
        if tenant:
            # Map tenant to account format
            accounts.append({
                "account_id": tenant.tenant_id,
                "name": tenant.name,
                "nkey_public": tenant.nkey_public,
                "subscription_tier": tenant.subscription_tier,
                "created_at": tenant.created_at,
                "updated_at": tenant.updated_at
            })
    
    return accounts


@router.get("/{account_id}", response_model=Dict)
async def get_account(
    account_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get account details (maps to tenant)"""
    # Verify user has access to this tenant
    from api.services.user_tenant_service import user_tenant_service
    if not await user_tenant_service.check_user_access(current_user["user_id"], account_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    tenant = await tenant_service.get_tenant(account_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Map tenant to account format
    return {
        "account_id": tenant.tenant_id,
        "name": tenant.name,
        "nkey_public": tenant.nkey_public,
        "subscription_tier": tenant.subscription_tier,
        "description": tenant.description,
        "website": tenant.website,
        "logo_url": tenant.logo_url,
        "created_at": tenant.created_at,
        "updated_at": tenant.updated_at
    }


@router.post("/generate-nkey/{account_id}", response_model=dict)
async def generate_account_nkey(
    account_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Generate NKey for existing account/tenant"""
    # Verify user has access
    from api.services.user_tenant_service import user_tenant_service
    if not await user_tenant_service.check_user_access(current_user["user_id"], account_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    tenant = await tenant_service.get_tenant(account_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Check if NKey already exists
    if tenant.nkey_public:
        raise HTTPException(status_code=400, detail="Account already has an NKey")
    
    # Generate account NKey
    kp = nkeys.from_seed(nkeys.create_account_seed())
    nkey_public = kp.public_key.decode('utf-8')
    nkey_seed = kp.seed.decode('utf-8')
    
    # Update tenant with NKey
    await tenant_service.update_tenant(account_id, {
        "nkey_public": nkey_public
    })
    
    # Return with seed (only shown once!)
    return {
        "account_id": account_id,
        "nkey_public": nkey_public,
        "nkey_seed": nkey_seed,
        "warning": "Save this seed securely! It will not be shown again."
    }


@router.put("/{account_id}", response_model=Dict)
async def update_account(
    account_id: str,
    updates: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update account settings (maps to tenant)"""
    # Verify user has access
    from api.services.user_tenant_service import user_tenant_service
    if not await user_tenant_service.check_user_access(current_user["user_id"], account_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Don't allow updating certain fields
    protected_fields = ["tenant_id", "id", "nkey_public", "issuer_key", "created_at"]
    for field in protected_fields:
        updates.pop(field, None)
    
    updated = await tenant_service.update_tenant(account_id, updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Account not found")
    
    # Return in account format
    return {
        "account_id": updated.tenant_id,
        "name": updated.name,
        "nkey_public": updated.nkey_public,
        "subscription_tier": updated.subscription_tier,
        "description": updated.description,
        "website": updated.website,
        "logo_url": updated.logo_url,
        "updated_at": updated.updated_at
    }