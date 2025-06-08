"""
Client routes (formerly agent routes)
Handles client management with NKey authentication
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import List, Optional
import nkeys
from datetime import datetime, timezone
from ulid import ULID
import os
import base64

from models.client import Client, ClientPermissions
from auth.dependencies import get_current_user, get_current_tenant_id
from api.services.client_service import ClientService
from pydantic import BaseModel

router = APIRouter(prefix="/clients", tags=["clients"])
client_service = ClientService()


class CreateClientRequest(BaseModel):
    """Request body for creating a client"""
    name: str
    permissions: Optional[ClientPermissions] = None
    metadata: Optional[dict] = None


def generate_nkey_seed():
    """
    Generate a new NKey seed for a user/client.
    
    The nkeys library doesn't have create_user_seed(), so we need to:
    1. Generate random bytes for the seed
    2. Create the proper seed format with the correct prefix
    
    NKey seeds follow this format:
    - First byte is the prefix (S for seed)
    - Second byte is the role (U for user, A for account, etc.)
    - Remaining bytes are random data
    """
    # NKey seed prefixes
    PREFIX_BYTE_SEED = 18 << 3  # 'S' prefix
    ROLE_USER = 20 << 3  # 'U' for user
    
    # Generate 32 random bytes for the key material
    random_bytes = os.urandom(32)
    
    # Construct the seed bytes: prefix + role + random data
    seed_bytes = bytes([PREFIX_BYTE_SEED | (ROLE_USER >> 5)]) + bytes([ROLE_USER & 0x1F]) + random_bytes[2:]
    
    # Encode using base32 (NKeys use a custom base32 alphabet)
    # The nkeys library handles the encoding when we create from the seed
    # For now, let's use the KeyPair.generate() method if available
    try:
        # Try the recommended approach - generate a new keypair
        kp = nkeys.KeyPair.generate()
        return kp
    except AttributeError:
        # If KeyPair.generate() doesn't exist, try another approach
        # Generate a valid seed string manually
        import secrets
        
        # NKey seeds are base32 encoded with a specific alphabet
        # They start with 'S' for seed, then 'U' for user
        nkey_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        
        # Generate random seed (56 characters after 'SU' prefix)
        seed_suffix = ''.join(secrets.choice(nkey_alphabet) for _ in range(56))
        seed_string = f"SU{seed_suffix}"
        
        # Create keypair from this seed
        kp = nkeys.from_seed(seed_string.encode())
        return kp


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
    request: CreateClientRequest,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """Create a new client with NKey"""
    try:
        # Generate client NKey
        kp = generate_nkey_seed()
        nkey_public = kp.public_key.decode('utf-8')
        nkey_seed = kp.seed.decode('utf-8')
    except Exception as e:
        # Fallback: Import the correct function from nkeys if available
        try:
            # Some versions might have it in a different location
            from nkeys import create_user_seed
            kp = nkeys.from_seed(create_user_seed())
            nkey_public = kp.public_key.decode('utf-8')
            nkey_seed = kp.seed.decode('utf-8')
        except ImportError:
            # Final fallback: generate a simple user seed
            # This follows the NATS nkey format
            import secrets
            nkey_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
            seed_string = "SU" + ''.join(secrets.choice(nkey_alphabet) for _ in range(56))
            kp = nkeys.from_seed(seed_string.encode())
            nkey_public = kp.public_key.decode('utf-8')
            nkey_seed = seed_string
    
    # Generate unique client ID
    client_ulid = str(ULID())
    
    # Default permissions if not provided
    if not request.permissions:
        permissions = ClientPermissions(
            publish=[f"{tenant_id}.*"],  # Can publish to any subject under tenant
            subscribe=[f"{tenant_id}.>"]  # Can subscribe to all tenant subjects
        )
    else:
        permissions = request.permissions
    
    # Create client
    client = Client(
        name=request.name,
        tenant_id=tenant_id,
        nkey_public=nkey_public,
        permissions=permissions,
        metadata=request.metadata or {}
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
    try:
        kp = generate_nkey_seed()
        new_nkey_public = kp.public_key.decode('utf-8')
        new_nkey_seed = kp.seed.decode('utf-8')
    except Exception:
        # Fallback to simple generation
        import secrets
        nkey_alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
        seed_string = "SU" + ''.join(secrets.choice(nkey_alphabet) for _ in range(56))
        kp = nkeys.from_seed(seed_string.encode())
        new_nkey_public = kp.public_key.decode('utf-8')
        new_nkey_seed = seed_string
    
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