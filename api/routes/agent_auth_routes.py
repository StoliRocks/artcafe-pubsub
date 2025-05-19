"""
Agent Authentication Routes

Provides endpoints for agent authentication
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from auth.ssh_auth import SSHKeyManager
from auth.jwt_handler import create_access_token
from api.services.agent_service import agent_service
from api.db import dynamodb
from config.settings import settings
from datetime import timedelta
import base64
import logging

router = APIRouter(
    prefix="/api/v1/auth/agent",
    tags=["Agent Authentication"]
)

logger = logging.getLogger(__name__)
ssh_key_manager = SSHKeyManager()


class SSHAuthRequest(BaseModel):
    agent_id: str
    tenant_id: str
    signature: str  # Base64 encoded signature
    challenge: str  # The challenge that was signed


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    agent_id: str
    tenant_id: str


@router.post("/ssh", response_model=AuthResponse)
async def authenticate_with_ssh(request: SSHAuthRequest):
    """
    Authenticate an agent using SSH key
    
    This endpoint accepts a signed challenge and verifies it against
    the agent's public key stored in the database.
    """
    try:
        # Get the agent
        agent = await agent_service.get_agent(request.tenant_id, request.agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agent not found"
            )
        
        if not agent.public_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Agent has no public key configured"
            )
        
        # Get the challenge from the challenge store
        from infrastructure.challenge_store import challenge_store
        challenge_data = await challenge_store.get_challenge(request.challenge)
        
        if not challenge_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired challenge"
            )
        
        # Verify the challenge belongs to this tenant/agent
        if challenge_data.get("tenant_id") != request.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Challenge mismatch"
            )
        
        # Decode the signature
        try:
            signature_bytes = base64.b64decode(request.signature)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature format"
            )
        
        # Verify the signature
        challenge_bytes = request.challenge.encode('utf-8')
        if not ssh_key_manager.verify_signature(
            agent.public_key,
            challenge_bytes,
            signature_bytes
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
        
        # Create JWT token for the agent
        token_data = {
            "sub": agent.agent_id,
            "tenant_id": agent.tenant_id,
            "agent_id": agent.agent_id,
            "scopes": "agent:pubsub",
            "token_type": "agent"
        }
        
        # Create JWT token with 24 hour expiration
        token = create_access_token(
            data=token_data,
            expires_delta=timedelta(hours=24)
        )
        
        # Clean up the used challenge
        await challenge_store.delete_challenge(request.challenge)
        
        return AuthResponse(
            access_token=token,
            agent_id=agent.agent_id,
            tenant_id=agent.tenant_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error authenticating agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )