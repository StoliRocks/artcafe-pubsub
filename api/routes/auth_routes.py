from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime, timedelta

from auth.tenant_auth import get_tenant_id, validate_tenant
from auth.ssh_auth import ssh_key_manager
from api.services.ssh_key_service import ssh_key_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


class ChallengeRequest(BaseModel):
    """Challenge request model"""
    agent_id: Optional[str] = None
    tenant_id: Optional[str] = None  # For unauthenticated agent challenge


class ChallengeResponse(BaseModel):
    """Challenge response model"""
    challenge: str
    expires_at: str
    tenant_id: str
    agent_id: Optional[str] = None


class VerifyRequest(BaseModel):
    """Verification request model"""
    tenant_id: str
    key_id: str
    challenge: str
    response: str
    agent_id: Optional[str] = None


class VerifyResponse(BaseModel):
    """Verification response model"""
    valid: bool
    message: str
    token: Optional[str] = None


@router.post("/challenge", response_model=ChallengeResponse)
async def create_challenge(
    request: ChallengeRequest,
    tenant_id: str = Depends(get_tenant_id),
    tenant: Dict = Depends(validate_tenant)
):
    """
    Generate an authentication challenge for SSH key verification.
    
    This endpoint generates a random challenge string that the client must sign
    with their private key. The signature is then verified using the public key
    stored in the system.
    """
    # Generate challenge
    challenge_data = await ssh_key_manager.generate_challenge(
        tenant_id=tenant_id,
        agent_id=request.agent_id
    )
    
    return ChallengeResponse(**challenge_data)


@router.post("/agent/challenge", response_model=ChallengeResponse)
async def create_agent_challenge(
    request: ChallengeRequest
):
    """
    Generate an authentication challenge for SSH key verification (agent auth).
    
    This is an unauthenticated endpoint specifically for agent initial authentication.
    The tenant_id must be provided in the request body.
    """
    if not request.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tenant_id is required in request body"
        )
    
    # Validate tenant exists
    tenant = await validate_tenant(request.tenant_id)
    
    # Generate challenge
    challenge_data = await ssh_key_manager.generate_challenge(
        tenant_id=request.tenant_id,
        agent_id=request.agent_id
    )
    
    return ChallengeResponse(**challenge_data)


@router.post("/verify", response_model=VerifyResponse)
async def verify_challenge(request: VerifyRequest):
    """
    Verify a signed challenge response.

    This endpoint verifies that the signature provided by the client matches the
    expected signature for the challenge, using the public key associated with the
    provided key_id.
    """
    # Validate tenant
    tenant = await validate_tenant(request.tenant_id)

    # Verify challenge response
    valid = await ssh_key_manager.verify_challenge_response(
        tenant_id=request.tenant_id,
        key_id=request.key_id,
        challenge=request.challenge,
        response=request.response,
        agent_id=request.agent_id
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )

    # Get SSH key details for additional context
    from auth.jwt_handler import create_access_token
    from datetime import timedelta

    # Get the SSH key
    ssh_key = await ssh_key_service.get_ssh_key(
        tenant_id=request.tenant_id,
        key_id=request.key_id
    )

    # Create token payload
    token_data = {
        "sub": request.key_id,
        "tenant_id": request.tenant_id,
        "key_type": ssh_key.key_type,
        "agent_id": request.agent_id or ssh_key.agent_id,
        "iat": datetime.utcnow().timestamp()
    }

    # Generate JWT token with 1 hour expiry
    token = create_access_token(
        data=token_data,
        expires_delta=timedelta(hours=1)
    )

    return VerifyResponse(
        valid=True,
        message="Authentication successful",
        token=token
    )