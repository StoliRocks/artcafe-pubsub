from datetime import datetime, timedelta
import logging
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config.settings import settings
from api.services.tenant_service import get_tenant
from auth.jwt_handler import decode_token, validate_cognito_token
from auth.jwt_auth import JWTAuth

logger = logging.getLogger(__name__)

# Security scheme for tenant authentication
security = HTTPBearer()

async def get_tenant_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract tenant ID from the request headers or JWT token.
    
    Args:
        request: The incoming request
        credentials: Bearer token credentials
        
    Returns:
        Tenant ID as a string
        
    Raises:
        HTTPException: If tenant ID is not found or invalid
    """
    # Enhanced logging for tenant extraction
    logger.debug(f"Extracting tenant ID from request")
    
    # Check if tenant_id exists in the request
    # First try to get tenant ID from headers
    tenant_id = request.headers.get(settings.TENANT_ID_HEADER_NAME)
    
    # If not in headers, try to extract from JWT token
    if not tenant_id and credentials:
        try:
            payload = decode_token(credentials.credentials)
            
            # Check different places where tenant_id might be in the JWT
            tenant_id = payload.get("tenant_id")  # Direct tenant_id claim
            
            if not tenant_id and "custom:tenant_id" in payload:
                tenant_id = payload.get("custom:tenant_id")  # AWS Cognito custom attribute
                
            if not tenant_id and "user_metadata" in payload and isinstance(payload["user_metadata"], dict):
                tenant_id = payload["user_metadata"].get("tenant_id")  # User metadata (Auth0 style)
                
            if not tenant_id and "organizations" in payload and isinstance(payload["organizations"], list) and len(payload["organizations"]) > 0:
                # Use the first organization ID as tenant ID (for multi-org users)
                tenant_id = payload["organizations"][0]
        except Exception as e:
            # Log the error but continue with flow - tenant_id might still be found elsewhere
            import logging
            logging.getLogger("auth.tenant_auth").warning(f"Error extracting tenant_id from JWT: {str(e)}")
    
    # If still not found, use the default tenant (for development only)
    if not tenant_id and settings.DEBUG:
        tenant_id = settings.DEFAULT_TENANT_ID
    
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant ID not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.debug(f"Extracted tenant ID: {tenant_id}")
    return tenant_id


async def validate_tenant(
    tenant_id: str = Depends(get_tenant_id)
) -> dict:
    """
    Validate that the tenant exists and has an active subscription.
    
    Args:
        tenant_id: The tenant ID to validate
        
    Returns:
        Tenant object if valid
        
    Raises:
        HTTPException: If tenant is not found or subscription is invalid
    """
    try:
        logger.debug(f"Validating tenant: {tenant_id}")
        # Get tenant from database
        tenant = await get_tenant(tenant_id)
        
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tenant not found"
            )
        
        # Check tenant status
        if tenant.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Tenant is not active. Current status: {tenant.status}"
            )
        
        # Check payment status - only check if completely inactive
        if tenant.payment_status == "inactive":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription is inactive"
            )
        
        # For free plan, we enforce limits instead of expiration
        # Limit checking is handled separately in check_tenant_limits
        
        logger.debug(f"Tenant validation successful: {tenant.id}")
        return tenant
    except Exception as e:
        logger.error(f"Tenant validation error for {tenant_id}: {e}")
        raise


async def check_tenant_limits(
    request_type: str,
    tenant: dict = Depends(validate_tenant)
) -> dict:
    """
    Check if the tenant has reached its usage limits.
    
    Args:
        request_type: The type of request being made
        tenant: The tenant to check
        
    Returns:
        Tenant object if limits are not exceeded
        
    Raises:
        HTTPException: If tenant has exceeded usage limits
    """
    # Skip limit checks in debug mode or if tenant is a superuser
    if settings.DEBUG or tenant.get("is_superuser", False):
        return tenant
    
    # Check tenant limits based on request type
    if request_type == "agent":
        # Check if tenant has reached agent limit
        if tenant.limits.max_agents > 0 and tenant.usage.total_agents >= tenant.limits.max_agents:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent limit reached: {tenant.usage.total_agents}/{tenant.limits.max_agents}"
            )
    
    elif request_type == "channel":
        # Check if tenant has reached channel limit
        if tenant.limits.max_channels > 0 and tenant.usage.total_channels >= tenant.limits.max_channels:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Channel limit reached: {tenant.usage.total_channels}/{tenant.limits.max_channels}"
            )
    
    elif request_type == "ssh_key":
        # Check if tenant has reached SSH key limit
        if tenant.limits.max_ssh_keys > 0 and tenant.usage.total_ssh_keys >= tenant.limits.max_ssh_keys:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"SSH key limit reached: {tenant.usage.total_ssh_keys}/{tenant.limits.max_ssh_keys}"
            )
    
    # Add other limit checks as needed
    
    return tenant