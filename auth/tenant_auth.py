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
    
    # Check payment status
    if tenant.payment_status == "expired":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription has expired"
        )
    
    if tenant.payment_status == "inactive":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription is inactive"
        )
    
    # Check if trial or subscription has expired
    now = datetime.utcnow()
    if tenant.subscription_expires_at and tenant.subscription_expires_at < now:
        # Update tenant payment status to expired
        # This should be done in a background task to avoid blocking the request
        # await tenant_service.update_payment_status(tenant_id, "expired")
        
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription has expired"
        )
    
    return tenant


async def check_tenant_limits(
    request_type: str,
    tenant: dict = Depends(validate_tenant)
) -> dict:
    """
    Check if the tenant has reached their usage limits.
    
    Args:
        request_type: The type of request being made (agent, channel, message, api_call, storage, connection)
        tenant: Validated tenant object
        
    Returns:
        Tenant object if within limits
        
    Raises:
        HTTPException: If tenant has exceeded their limits
    """
    # Import here to avoid circular imports
    from api.services.agent_service import agent_service
    from api.services.channel_service import channel_service
    from api.services.usage_service import usage_service
    from infrastructure.metrics_service import metrics_service
    
    tenant_id = tenant.tenant_id
    
    try:
        # Get current usage totals
        usage_totals = await usage_service.get_usage_totals(tenant_id)
        today = datetime.utcnow().date().isoformat()
        
        # Get today's metrics
        daily_metrics = await usage_service.get_usage_metrics(
            tenant_id, 
            start_date=today,
            end_date=today
        )
        
        # If we have metrics for today, use them; otherwise create empty metrics
        daily_metric = daily_metrics[0] if daily_metrics else None
        
        # Usage limits based on subscription tier
        if request_type == "agent":
            # Get current agent count
            if hasattr(agent_service, 'get_agent_count'):
                agent_count = await agent_service.get_agent_count(tenant_id)
            else:
                # Fallback to metrics if agent_service doesn't have the method
                agent_count = usage_totals.agents_total if usage_totals else 0
            
            # Check against limit
            if agent_count >= tenant.max_agents:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Agent limit reached. Maximum allowed: {tenant.max_agents}, Current: {agent_count}",
                    headers={"x-rate-limit-reset": "86400"}  # Reset in 24 hours
                )
        
        elif request_type == "channel":
            # Get current channel count
            if hasattr(channel_service, 'get_channel_count'):
                channel_count = await channel_service.get_channel_count(tenant_id)
            else:
                # Fallback to metrics if channel_service doesn't have the method
                channel_count = usage_totals.channels_total if usage_totals else 0
            
            # Check against limit
            if channel_count >= tenant.max_channels:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Channel limit reached. Maximum allowed: {tenant.max_channels}, Current: {channel_count}",
                    headers={"x-rate-limit-reset": "86400"}  # Reset in 24 hours
                )
        
        elif request_type == "message":
            # Get daily message count
            message_count = 0
            if daily_metric:
                message_count = daily_metric.messages_count
            
            # Pre-check against a percentage of the limit to allow for some buffer
            # (90% of limit as a warning threshold)
            warning_threshold = tenant.max_messages_per_day * 0.9
            if message_count >= warning_threshold:
                logger.warning(
                    f"Tenant {tenant_id} approaching message limit: {message_count}/{tenant.max_messages_per_day}"
                )
            
            # Check against limit
            if message_count >= tenant.max_messages_per_day:
                # Calculate seconds until limit reset (midnight UTC)
                now = datetime.utcnow()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_reset = int((tomorrow - now).total_seconds())
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Daily message limit reached. Maximum allowed: {tenant.max_messages_per_day}, Current: {message_count}",
                    headers={"x-rate-limit-reset": str(seconds_until_reset)}
                )
        
        elif request_type == "api_call":
            # Get daily API call count
            api_call_count = 0
            if daily_metric:
                api_call_count = daily_metric.api_calls_count
            
            # Check against limit (if defined)
            max_api_calls = getattr(tenant, 'max_api_calls_per_day', 10000)  # Default if not defined
            
            # Warning at 90% of limit
            warning_threshold = max_api_calls * 0.9
            if api_call_count >= warning_threshold:
                logger.warning(
                    f"Tenant {tenant_id} approaching API call limit: {api_call_count}/{max_api_calls}"
                )
            
            if api_call_count >= max_api_calls:
                # Calculate seconds until limit reset (midnight UTC)
                now = datetime.utcnow()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_reset = int((tomorrow - now).total_seconds())
                
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Daily API call limit reached. Maximum allowed: {max_api_calls}, Current: {api_call_count}",
                    headers={"x-rate-limit-reset": str(seconds_until_reset)}
                )
        
        elif request_type == "storage":
            # Get current storage usage
            storage_bytes = 0
            if daily_metric and hasattr(daily_metric, 'storage_used_bytes'):
                storage_bytes = daily_metric.storage_used_bytes
            
            # Check against limit (if defined)
            max_storage_bytes = getattr(tenant, 'max_storage_bytes', 1073741824)  # Default 1GB if not defined
            
            if storage_bytes >= max_storage_bytes:
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                    detail=f"Storage limit reached. Maximum allowed: {max_storage_bytes} bytes, Current: {storage_bytes} bytes"
                )
        
        elif request_type == "connection":
            # Get current connection count from metrics service
            connection_count = metrics_service.get_tenant_connection_count(tenant_id)
            
            # Check against limit (if defined)
            max_connections = getattr(tenant, 'concurrent_connections', 50)  # Default if not defined
            
            if connection_count >= max_connections:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Connection limit reached. Maximum allowed: {max_connections}, Current: {connection_count}"
                )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log other exceptions but allow the request to proceed
        logger.error(f"Error checking tenant limits: {e}")
        
    # If no limits exceeded, return the tenant
    return tenant