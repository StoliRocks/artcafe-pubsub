from typing import Optional
from fastapi import APIRouter, Depends, Query

from auth import get_current_tenant_id
from models import UsageMetricsResponse
from api.services import usage_service

router = APIRouter(prefix="/usage-metrics", tags=["usage-metrics"])


@router.get("", response_model=UsageMetricsResponse)
async def get_usage_metrics(
    tenant_id: str = Depends(get_current_tenant_id),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)")
):
    """
    Get usage metrics for a tenant
    
    Args:
        tenant_id: Tenant ID
        start_date: Optional start date (ISO format)
        end_date: Optional end date (ISO format)
        
    Returns:
        Usage metrics
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get usage metrics
    metrics = await usage_service.get_usage_metrics(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return UsageMetricsResponse(metrics=metrics)