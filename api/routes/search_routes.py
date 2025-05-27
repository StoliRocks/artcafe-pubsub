from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

from auth.dependencies import get_current_user, verify_tenant_access
from api.services.search_service import search_service

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=Dict[str, Any])
async def search(
    q: str = Query(..., min_length=1, max_length=200),
    resource_type: Optional[str] = Query(None, regex="^(agent|channel|activity)$"),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(20, ge=1, le=100)
):
    """
    Search across agents, channels, and activities
    
    Args:
        q: Search query
        resource_type: Filter by resource type (agent, channel, activity)
        limit: Maximum results per category
        
    Returns:
        Search results grouped by type
    """
    try:
        filters = {}
        if resource_type:
            filters["resource_type"] = resource_type
        
        results = await search_service.search(
            tenant_id=tenant_id,
            query=q,
            filters=filters,
            limit=limit
        )
        
        return results
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error searching: {str(e)}"
        )


@router.get("/suggestions", response_model=List[str])
async def get_search_suggestions(
    prefix: str = Query(..., min_length=1, max_length=50),
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(verify_tenant_access),
    limit: int = Query(5, ge=1, le=10)
):
    """
    Get search suggestions based on prefix
    
    Args:
        prefix: Search prefix
        limit: Maximum suggestions
        
    Returns:
        List of suggested search terms
    """
    try:
        suggestions = await search_service.get_search_suggestions(
            tenant_id=tenant_id,
            prefix=prefix,
            limit=limit
        )
        
        return suggestions
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting suggestions: {str(e)}"
        )


@router.get("/popular", response_model=List[Dict[str, Any]])
async def get_popular_searches(
    user: dict = Depends(get_current_user),
    tenant_id: str = Depends(verify_tenant_access),
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(10, ge=1, le=20)
):
    """
    Get popular search queries
    
    Args:
        days: Number of days to analyze
        limit: Maximum results
        
    Returns:
        List of popular searches with counts
    """
    try:
        popular = await search_service.get_popular_searches(
            tenant_id=tenant_id,
            days=days,
            limit=limit
        )
        
        return popular
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting popular searches: {str(e)}"
        )