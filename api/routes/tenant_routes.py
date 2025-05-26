from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Optional, Dict

from models import TenantCreate, TenantResponse, Tenant, TenantUpdate
from models.user_tenant import UserWithTenants, UserRole
from api.services import tenant_service
from api.services.user_tenant_service import user_tenant_service
from auth.dependencies import get_current_user, get_current_user_with_tenants, verify_tenant_access
from config.settings import settings

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    user: Dict = Depends(get_current_user),
    request: Request = None
):
    """
    Create a new tenant
    
    Args:
        tenant_data: Tenant data
        user: Current authenticated user
        
    Returns:
        Created tenant info with API key and admin token
    """
    try:
        # Add user ID to metadata
        if not tenant_data.metadata:
            tenant_data.metadata = {}
        tenant_data.metadata["user_id"] = user["user_id"]
        
        # Add terms acceptance data if available
        if request and hasattr(request, "state") and hasattr(request.state, "terms_data"):
            tenant_data.terms_acceptance = request.state.terms_data
        
        # Create tenant
        result = await tenant_service.create_tenant(tenant_data)
        
        return TenantResponse(
            tenant_id=result["tenant_id"],
            api_key=result["api_key"],
            admin_token=result["admin_token"],
            success=True
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating tenant: {str(e)}"
        )


@router.get("", response_model=List[Tenant])
async def list_tenants(
    user: Dict = Depends(get_current_user),
    limit: int = 100
):
    """
    List tenants accessible by the current user
    
    Args:
        user: Current authenticated user
        limit: Maximum number of tenants to return
        
    Returns:
        List of tenants
    """
    try:
        # Get tenants for the user
        tenants = await tenant_service.get_user_tenants(user["user_id"])
        
        # Apply limit
        if limit and len(tenants) > limit:
            tenants = tenants[:limit]
        
        return tenants
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing tenants: {str(e)}"
        )


@router.get("/{tenant_id}", response_model=Tenant)
async def get_tenant(
    tenant_id: str,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Get a specific tenant by ID
    
    Args:
        tenant_id: Tenant ID
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        Tenant details
    """
    try:
        # Get tenant
        tenant = await tenant_service.get_tenant(tenant_id)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tenant {tenant_id} not found"
            )
        
        return tenant
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting tenant: {str(e)}"
        )


@router.put("/{tenant_id}", response_model=Tenant)
async def update_tenant(
    tenant_id: str,
    update_data: TenantUpdate,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Update a tenant
    
    Args:
        tenant_id: Tenant ID
        update_data: Fields to update
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        Updated tenant
    """
    try:
        # Check if user has admin or owner role
        user_tenant = await user_tenant_service.get_user_tenant_mapping(
            user.user_id, tenant_id
        )
        
        if not user_tenant or not user_tenant.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can update tenant settings"
            )
        
        # Convert update_data to dict, excluding None values
        update_dict = update_data.dict(exclude_none=True)
        
        if not update_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        # Update tenant
        from ..db import dynamodb
        await dynamodb.update_item(
            table_name=settings.TENANT_TABLE_NAME,
            key={"id": tenant_id},
            updates=update_dict
        )
        
        # Get updated tenant
        updated_tenant = await tenant_service.get_tenant(tenant_id)
        return updated_tenant
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating tenant: {str(e)}"
        )


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Delete a tenant
    
    Args:
        tenant_id: Tenant ID
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        No content on success
    """
    try:
        # Check if user is owner
        user_tenant = await user_tenant_service.get_user_tenant_mapping(
            user.user_id, tenant_id
        )
        
        if not user_tenant or not user_tenant.is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only owners can delete tenants"
            )
        
        # Delete tenant
        from ..db import dynamodb
        await dynamodb.delete_item(
            table_name=settings.TENANT_TABLE_NAME,
            key={"id": tenant_id}
        )
        
        # Remove all user-tenant mappings for this tenant
        tenant_users = await user_tenant_service.get_tenant_users(tenant_id)
        for mapping in tenant_users:
            await user_tenant_service.remove_user_from_tenant(
                mapping.user_id, tenant_id
            )
        
        # TODO: Also delete related resources (agents, channels, etc.)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting tenant: {str(e)}"
        )


# Organization member management endpoints
@router.get("/{tenant_id}/members", response_model=List[Dict])
async def get_tenant_members(
    tenant_id: str,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Get all members of a tenant
    
    Args:
        tenant_id: Tenant ID
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        List of tenant members
    """
    try:
        members = await user_tenant_service.get_tenant_users(tenant_id)
        
        # Convert to response format
        return [
            {
                "user_id": member.user_id,
                "email": member.user_email,
                "role": member.role,
                "joined_date": member.created_at,
                "active": member.active
            }
            for member in members
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting tenant members: {str(e)}"
        )


@router.post("/{tenant_id}/members", response_model=Dict)
async def add_tenant_member(
    tenant_id: str,
    member_data: Dict,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Add a member to a tenant
    
    Args:
        tenant_id: Tenant ID
        member_data: Member data (user_id, email, role)
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        Created member info
    """
    try:
        # Check if user has permission to add members
        user_tenant = await user_tenant_service.get_user_tenant_mapping(
            user.user_id, tenant_id
        )
        
        if not user_tenant or not user_tenant.can_manage_members:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to manage members"
            )
        
        # Create user-tenant mapping
        mapping = await user_tenant_service.create_user_tenant_mapping(
            user_id=member_data["user_id"],
            tenant_id=tenant_id,
            role=member_data.get("role", UserRole.MEMBER),
            invited_by=user.user_id,
            user_email=member_data.get("email")
        )
        
        return {
            "user_id": mapping.user_id,
            "email": mapping.user_email,
            "role": mapping.role,
            "invited_by": mapping.invited_by,
            "invitation_date": mapping.invitation_date,
            "active": mapping.active
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding tenant member: {str(e)}"
        )


@router.put("/{tenant_id}/members/{user_id}", response_model=Dict)
async def update_tenant_member(
    tenant_id: str,
    user_id: str,
    update_data: Dict,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Update a tenant member's role
    
    Args:
        tenant_id: Tenant ID
        user_id: User ID to update
        update_data: Update data (role)
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        Updated member info
    """
    try:
        # Check if user has permission to manage members
        user_tenant = await user_tenant_service.get_user_tenant_mapping(
            user.user_id, tenant_id
        )
        
        if not user_tenant or not user_tenant.can_manage_members:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to manage members"
            )
        
        # Update role
        updated_mapping = await user_tenant_service.update_user_role(
            user_id=user_id,
            tenant_id=tenant_id,
            new_role=update_data["role"]
        )
        
        if not updated_mapping:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )
        
        return {
            "user_id": updated_mapping.user_id,
            "email": updated_mapping.user_email,
            "role": updated_mapping.role,
            "updated_at": updated_mapping.updated_at,
            "active": updated_mapping.active
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating tenant member: {str(e)}"
        )


@router.delete("/{tenant_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_tenant_member(
    tenant_id: str,
    user_id: str,
    user: UserWithTenants = Depends(get_current_user_with_tenants),
    verified_tenant_id: str = Depends(verify_tenant_access)
):
    """
    Remove a member from a tenant
    
    Args:
        tenant_id: Tenant ID
        user_id: User ID to remove
        user: Current user with tenants
        verified_tenant_id: Verified tenant ID
        
    Returns:
        No content on success
    """
    try:
        # Check if user has permission to manage members
        user_tenant = await user_tenant_service.get_user_tenant_mapping(
            user.user_id, tenant_id
        )
        
        if not user_tenant or not user_tenant.can_manage_members:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to manage members"
            )
        
        # Can't remove the owner
        target_mapping = await user_tenant_service.get_user_tenant_mapping(
            user_id, tenant_id
        )
        
        if target_mapping and target_mapping.is_owner:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the organization owner"
            )
        
        # Remove member
        success = await user_tenant_service.remove_user_from_tenant(
            user_id, tenant_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Member not found"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error removing tenant member: {str(e)}"
        )