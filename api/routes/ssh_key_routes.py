from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from auth.dependencies import get_current_tenant_id
from models import SSHKeyCreate, SSHKeyResponse, SSHKeysResponse
from api.services import ssh_key_service, usage_service

router = APIRouter(prefix="/ssh-keys", tags=["ssh-keys"])


@router.get("", response_model=SSHKeysResponse)
async def list_ssh_keys(
    tenant_id: str = Depends(get_current_tenant_id),
    limit: int = Query(50, description="Maximum number of results"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """
    List SSH keys for a tenant
    
    Returns:
        List of SSH keys
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get SSH keys
    result = await ssh_key_service.list_ssh_keys(
        tenant_id=tenant_id,
        limit=limit,
        next_token=next_token
    )
    
    return SSHKeysResponse(
        keys=result["keys"],
        next_token=result["next_token"]
    )


@router.get("/{key_id}", response_model=SSHKeyResponse)
async def get_ssh_key(
    key_id: str = Path(..., description="SSH key ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get SSH key by ID
    
    Args:
        key_id: SSH key ID
        
    Returns:
        SSH key details
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get SSH key
    key = await ssh_key_service.get_ssh_key(tenant_id, key_id)
    
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSH key {key_id} not found"
        )
        
    return SSHKeyResponse(key=key)


@router.post("", response_model=SSHKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_ssh_key(
    key_data: SSHKeyCreate,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Create a new SSH key
    
    Args:
        key_data: SSH key data
        
    Returns:
        Created SSH key
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Create SSH key
    key = await ssh_key_service.create_ssh_key(tenant_id, key_data)
    
    return SSHKeyResponse(key=key)


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ssh_key(
    key_id: str = Path(..., description="SSH key ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Delete an SSH key
    
    Args:
        key_id: SSH key ID
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Delete SSH key
    result = await ssh_key_service.delete_ssh_key(tenant_id, key_id)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SSH key {key_id} not found"
        )