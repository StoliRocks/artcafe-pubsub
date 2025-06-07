"""
Client routes (formerly agent routes)
Handles client management with NKey authentication
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List, Optional
import nkeys
from datetime import datetime, timezone
from ulid import ULID

from models.client import Client, ClientPermissions
from auth.dependencies import get_current_user, get_current_tenant_id
from api.services.client_service import ClientService

router = APIRouter(prefix="/clients", tags=["clients"])
client_service = ClientService()


@router.get("/", response_model=List[Client])
async def list_clients(
    tenant_id: str = Depends(get_current_tenant_id),
    status: Optional[str] = None,
    limit: int = 100
):
    """List clients for the current tenant"""
    return await client_service.list_clients(
        tenant_id=tenant_id,
        status=status,
        limit=limit
    )


@router.get("/{client_id}", response_model=Client)
async def get_client(
    client_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get client details"""
    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Verify client belongs to tenant
    if client.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return client


@router.post("/", response_model=dict)
async def create_client(
    name: str,
    permissions: Optional[ClientPermissions] = None,
    metadata: Optional[dict] = None,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Create a new client with NKey"""
    # Generate client NKey
    kp = nkeys.from_seed(nkeys.create_user_seed())
    nkey_public = kp.public_key.decode('utf-8')
    nkey_seed = kp.seed.decode('utf-8')
    
    # Default permissions if not provided
    if not permissions:
        permissions = ClientPermissions(
            publish=[f"{tenant_id}.clients.{str(ULID())}.evt"],
            subscribe=[f"{tenant_id}.clients.{str(ULID())}.cmd", f"{tenant_id}._sys.*"]
        )
    
    # Create client
    client = Client(
        name=name,
        tenant_id=tenant_id,
        nkey_public=nkey_public,
        permissions=permissions,
        metadata=metadata or {}
    )
    
    # Save to database
    created = await client_service.create_client(client)
    
    # Return client with seed (only shown once!)
    return {
        "client": created.dict(),
        "nkey_seed": nkey_seed,
        "connection_example": {
            "nats_url": "nats://nats.artcafe.ai:4222",
            "subject_prefix": tenant_id,
            "auth_method": "nkey"
        },
        "warning": "Save this seed securely! It will not be shown again."
    }


@router.put("/{client_id}", response_model=Client)
async def update_client(
    client_id: str,
    updates: dict,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Update client settings"""
    # Get existing client
    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Verify ownership
    if client.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Don't allow updating certain fields
    protected_fields = ["client_id", "tenant_id", "nkey_public", "created_at"]
    for field in protected_fields:
        updates.pop(field, None)
    
    updated = await client_service.update_client(client_id, updates)
    return updated


@router.delete("/{client_id}")
async def delete_client(
    client_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Delete a client"""
    # Get existing client
    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Verify ownership
    if client.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    success = await client_service.delete_client(client_id)
    return {"status": "deleted", "client_id": client_id}


@router.post("/{client_id}/regenerate-nkey", response_model=dict)
async def regenerate_client_nkey(
    client_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Regenerate client NKey (invalidates old one)"""
    # Get existing client
    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Verify ownership
    if client.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Generate new NKey
    kp = nkeys.from_seed(nkeys.create_user_seed())
    new_nkey_public = kp.public_key.decode('utf-8')
    new_nkey_seed = kp.seed.decode('utf-8')
    
    # Update client
    await client_service.update_client(client_id, {
        "nkey_public": new_nkey_public,
        "status": "offline",  # Force reconnection
        "updated_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "client_id": client_id,
        "new_nkey_seed": new_nkey_seed,
        "warning": "Old NKey is now invalid. Update your client configuration."
    }


@router.get("/{client_id}/status")
async def get_client_status(
    client_id: str,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Get real-time client status"""
    client = await client_service.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Verify ownership
    if client.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get connection status
    connection = await client_service.get_client_connection(client_id)
    
    return {
        "client_id": client_id,
        "name": client.name,
        "status": client.status,
        "last_seen": client.last_seen,
        "connection": {
            "connected": connection is not None,
            "server": connection.get("server_id") if connection else None,
            "since": connection.get("connected_at") if connection else None
        }
    }