"""
Advanced metrics API routes for NATS monitoring
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from datetime import datetime, date, timedelta

from auth.tenant_auth import get_tenant_id
from api.services.tenant_service import tenant_service
from api.services.nats_monitoring_service import nats_monitoring_service, MetricTier
from api.services.local_message_tracker import message_tracker
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/realtime")
async def get_realtime_metrics(
    tenant_id: str = Depends(get_tenant_id),
    include_clients: bool = Query(False, description="Include per-client metrics")
):
    """
    Get real-time metrics for the tenant.
    
    Returns current metrics based on tenant's subscription tier.
    """
    try:
        # Get tenant to check tier
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Map subscription tiers to metric tiers
        tier_mapping = {
            "free": MetricTier.BASIC,
            "starter": MetricTier.BASIC,
            "professional": MetricTier.PROFESSIONAL,
            "enterprise": MetricTier.ENTERPRISE
        }
        
        metric_tier = tier_mapping.get(tenant.subscription_tier.lower(), MetricTier.BASIC)
        
        # Get metrics from monitoring service
        metrics = await nats_monitoring_service.get_tenant_metrics(tenant_id, metric_tier)
        
        # Add client details if requested and tier allows
        if include_clients and metric_tier in [MetricTier.PROFESSIONAL, MetricTier.ENTERPRISE]:
            metrics["clients"] = nats_monitoring_service._get_client_analytics(tenant_id)
        
        return {
            "success": True,
            "data": metrics,
            "tier": metric_tier
        }
        
    except Exception as e:
        logger.error(f"Error getting realtime metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


@router.get("/presence")
async def get_client_presence(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get current client presence information.
    
    Shows which clients are online/offline with last seen times.
    """
    try:
        presence_data = nats_monitoring_service.client_presence.get(tenant_id, {})
        
        clients = []
        for client_id, info in presence_data.items():
            clients.append({
                "client_id": client_id,
                "status": info.get("status", "unknown"),
                "last_seen": info.get("last_seen").isoformat() if info.get("last_seen") else None,
                "last_heartbeat": info.get("last_heartbeat").isoformat() if info.get("last_heartbeat") else None,
                "health_status": info.get("health_status", "unknown"),
                "version": info.get("version", "unknown"),
                "message_count": info.get("message_count", 0),
                "metadata": info.get("metadata", {})
            })
        
        return {
            "success": True,
            "data": {
                "tenant_id": tenant_id,
                "timestamp": datetime.now().isoformat(),
                "total_clients": len(clients),
                "online_clients": len([c for c in clients if c["status"] == "online"]),
                "clients": clients
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting client presence: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve presence data")


@router.get("/analytics")
async def get_analytics(
    tenant_id: str = Depends(get_tenant_id),
    period: str = Query("1h", description="Time period: 1h, 24h, 7d, 30d")
):
    """
    Get analytics for the specified time period.
    
    Professional and Enterprise tiers only.
    """
    try:
        # Get tenant to check tier
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Check if tenant has access to analytics
        if tenant.subscription_tier.lower() not in ["professional", "enterprise"]:
            raise HTTPException(
                status_code=403, 
                detail="Analytics requires Professional or Enterprise tier"
            )
        
        # Parse period
        period_map = {
            "1h": 1,
            "24h": 24,
            "7d": 7 * 24,
            "30d": 30 * 24
        }
        hours = period_map.get(period, 1)
        
        # Get historical data
        if hours <= 24:
            # Get hourly data from Redis
            history = await message_tracker.get_usage_history(tenant_id, days=1)
        else:
            # Get daily data
            days = hours // 24
            history = await message_tracker.get_usage_history(tenant_id, days=days)
        
        # Calculate analytics
        analytics = {
            "tenant_id": tenant_id,
            "period": period,
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_messages": sum(h.get("messages", 0) for h in history),
                "total_bytes": sum(h.get("bytes", 0) for h in history),
                "total_api_calls": sum(h.get("api_calls", 0) for h in history),
                "unique_agents": len(set(h.get("active_agents", 0) for h in history)),
                "unique_channels": len(set(h.get("active_channels", 0) for h in history))
            },
            "trends": {
                "message_growth": _calculate_growth_rate([h.get("messages", 0) for h in history]),
                "throughput_trend": _calculate_trend([h.get("bytes", 0) for h in history])
            },
            "history": history
        }
        
        # Add advanced analytics for enterprise
        if tenant.subscription_tier.lower() == "enterprise":
            analytics["advanced"] = {
                "peak_hour": _find_peak_hour(history),
                "quiet_periods": _find_quiet_periods(history),
                "usage_pattern": _analyze_usage_pattern(history),
                "predictions": nats_monitoring_service._get_predictive_insights(tenant_id)
            }
        
        return {
            "success": True,
            "data": analytics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics")


@router.get("/anomalies")
async def get_anomalies(
    tenant_id: str = Depends(get_tenant_id),
    hours: int = Query(24, description="Look back period in hours")
):
    """
    Get detected anomalies.
    
    Enterprise tier only.
    """
    try:
        # Get tenant to check tier
        tenant = await tenant_service.get_tenant(tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        # Check if tenant has access to anomaly detection
        if tenant.subscription_tier.lower() != "enterprise":
            raise HTTPException(
                status_code=403, 
                detail="Anomaly detection requires Enterprise tier"
            )
        
        # For now, return empty list as anomalies would be stored separately
        anomalies = {
            "tenant_id": tenant_id,
            "period_hours": hours,
            "timestamp": datetime.now().isoformat(),
            "anomalies": [],  # Would query from anomaly storage
            "summary": {
                "total_anomalies": 0,
                "by_type": {},
                "severity_distribution": {
                    "low": 0,
                    "medium": 0,
                    "high": 0,
                    "critical": 0
                }
            }
        }
        
        return {
            "success": True,
            "data": anomalies
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting anomalies: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve anomalies")


@router.get("/health-check")
async def get_system_health(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get system health metrics for all clients.
    
    Shows client health status and any issues.
    """
    try:
        presence_data = nats_monitoring_service.client_presence.get(tenant_id, {})
        
        health_summary = {
            "tenant_id": tenant_id,
            "timestamp": datetime.now().isoformat(),
            "overall_health": "healthy",
            "clients": {
                "total": len(presence_data),
                "healthy": 0,
                "degraded": 0,
                "unhealthy": 0,
                "offline": 0,
                "unknown": 0
            },
            "issues": []
        }
        
        # Analyze each client
        for client_id, info in presence_data.items():
            status = info.get("status", "unknown")
            health = info.get("health_status", "unknown")
            
            if status == "offline":
                health_summary["clients"]["offline"] += 1
            elif health == "healthy":
                health_summary["clients"]["healthy"] += 1
            elif health == "degraded":
                health_summary["clients"]["degraded"] += 1
                health_summary["issues"].append({
                    "client_id": client_id,
                    "type": "degraded_performance",
                    "severity": "warning"
                })
            elif health == "unhealthy":
                health_summary["clients"]["unhealthy"] += 1
                health_summary["issues"].append({
                    "client_id": client_id,
                    "type": "unhealthy_client",
                    "severity": "error"
                })
            else:
                health_summary["clients"]["unknown"] += 1
        
        # Determine overall health
        if health_summary["clients"]["unhealthy"] > 0:
            health_summary["overall_health"] = "unhealthy"
        elif health_summary["clients"]["degraded"] > 0:
            health_summary["overall_health"] = "degraded"
        elif health_summary["clients"]["offline"] > health_summary["clients"]["healthy"]:
            health_summary["overall_health"] = "degraded"
        
        return {
            "success": True,
            "data": health_summary
        }
        
    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve health data")


# Helper functions

def _calculate_growth_rate(values: list) -> float:
    """Calculate growth rate from a list of values"""
    if len(values) < 2:
        return 0.0
    
    # Compare first and last non-zero values
    first = next((v for v in values if v > 0), 0)
    last = next((v for v in reversed(values) if v > 0), 0)
    
    if first == 0:
        return 0.0
        
    return ((last - first) / first) * 100


def _calculate_trend(values: list) -> str:
    """Calculate trend direction"""
    if len(values) < 2:
        return "stable"
    
    # Simple trend: compare average of first half vs second half
    mid = len(values) // 2
    first_half = sum(values[:mid]) / mid if mid > 0 else 0
    second_half = sum(values[mid:]) / len(values[mid:]) if len(values[mid:]) > 0 else 0
    
    if second_half > first_half * 1.1:
        return "increasing"
    elif second_half < first_half * 0.9:
        return "decreasing"
    else:
        return "stable"


def _find_peak_hour(history: list) -> Optional[str]:
    """Find the peak usage hour"""
    if not history:
        return None
    
    # Find hour with most messages
    peak = max(history, key=lambda x: x.get("messages", 0))
    return peak.get("date", "unknown")


def _find_quiet_periods(history: list) -> list:
    """Find periods of low activity"""
    quiet = []
    
    if not history:
        return quiet
    
    # Calculate average
    avg = sum(h.get("messages", 0) for h in history) / len(history)
    
    # Find periods below 20% of average
    for h in history:
        if h.get("messages", 0) < avg * 0.2:
            quiet.append(h.get("date", "unknown"))
    
    return quiet


def _analyze_usage_pattern(history: list) -> str:
    """Analyze usage pattern"""
    if not history:
        return "insufficient_data"
    
    # Simple pattern detection
    messages = [h.get("messages", 0) for h in history]
    
    # Check for consistency
    if all(m == messages[0] for m in messages):
        return "constant"
    
    # Check for growth
    if all(messages[i] <= messages[i+1] for i in range(len(messages)-1)):
        return "growing"
    
    # Check for decline
    if all(messages[i] >= messages[i+1] for i in range(len(messages)-1)):
        return "declining"
    
    # Check for periodicity (would need more sophisticated analysis)
    return "variable"