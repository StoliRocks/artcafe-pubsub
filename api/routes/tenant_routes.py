from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from models import TenantCreate, TenantResponse
from api.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(tenant_data: TenantCreate):
    """
    Create a new tenant
    
    Args:
        tenant_data: Tenant data
        
    Returns:
        Created tenant info with API key and admin token
    """
    try:
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