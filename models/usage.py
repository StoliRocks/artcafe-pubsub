"""
Usage metrics models.

This module defines the models for usage metrics tracking.
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

class UsageMetrics(BaseModel):
    """Usage metrics for a tenant on a specific date."""
    tenant_id: str = Field(..., description="Tenant ID")
    date: str = Field(..., description="Date of the metrics (YYYY-MM-DD)")
    agents_count: int = Field(default=0, description="Number of agents")
    active_agents_count: int = Field(default=0, description="Number of active agents")
    channels_count: int = Field(default=0, description="Number of channels")
    active_channels_count: int = Field(default=0, description="Number of active channels")
    messages_count: int = Field(default=0, description="Number of messages sent")
    api_calls_count: int = Field(default=0, description="Number of API calls made")
    storage_used_bytes: int = Field(default=0, description="Storage used in bytes")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "date": "2023-09-28",
                "agents_count": 10,
                "active_agents_count": 5,
                "channels_count": 8,
                "active_channels_count": 3,
                "messages_count": 1240,
                "api_calls_count": 356,
                "storage_used_bytes": 123456789,
                "created_at": "2023-09-28T14:32:10.123456Z",
                "metadata": {
                    "peak_hour": "14:00",
                    "busiest_channel": "data-processing"
                }
            }
        }

class UsageLimits(BaseModel):
    """Usage limits for a tenant based on subscription tier."""
    max_agents: int = Field(default=10, description="Maximum number of agents")
    max_channels: int = Field(default=20, description="Maximum number of channels")
    max_messages_per_day: int = Field(default=50000, description="Maximum messages per day")
    max_api_calls_per_day: int = Field(default=10000, description="Maximum API calls per day")
    max_storage_bytes: int = Field(default=1073741824, description="Maximum storage in bytes (1GB)")
    concurrent_connections: int = Field(default=50, description="Maximum concurrent WebSocket connections")

    class Config:
        schema_extra = {
            "example": {
                "max_agents": 10,
                "max_channels": 20,
                "max_messages_per_day": 50000,
                "max_api_calls_per_day": 10000,
                "max_storage_bytes": 1073741824,
                "concurrent_connections": 50
            }
        }

class UsageTotals(BaseModel):
    """Aggregated usage metrics across a date range."""
    tenant_id: str = Field(..., description="Tenant ID")
    start_date: str = Field(..., description="Start date of the metrics (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date of the metrics (YYYY-MM-DD)")
    agents_total: int = Field(default=0, description="Total number of agents")
    active_agents_total: int = Field(default=0, description="Total number of active agents")
    channels_total: int = Field(default=0, description="Total number of channels")
    active_channels_total: int = Field(default=0, description="Total number of active channels")
    messages_in_total: int = Field(default=0, description="Total number of inbound messages")
    messages_out_total: int = Field(default=0, description="Total number of outbound messages")
    api_calls_total: int = Field(default=0, description="Total number of API calls")
    timestamp: str = Field(..., description="Timestamp when totals were calculated (ISO format)")

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "start_date": "2023-09-01",
                "end_date": "2023-09-30",
                "agents_total": 10,
                "active_agents_total": 7,
                "channels_total": 15,
                "active_channels_total": 8,
                "messages_in_total": 35678,
                "messages_out_total": 29456,
                "api_calls_total": 12345,
                "timestamp": "2023-09-30T23:59:59.999999Z"
            }
        }

class UsageMetricsResponse(BaseModel):
    """Response with usage metrics."""
    metrics: List[UsageMetrics] = Field(..., description="List of usage metrics")
    totals: Optional[UsageTotals] = Field(None, description="Aggregated totals")
    limits: Optional[UsageLimits] = Field(None, description="Usage limits")
    success: bool = Field(default=True, description="Whether the operation was successful")

    class Config:
        schema_extra = {
            "example": {
                "metrics": [
                    {
                        "tenant_id": "tenant-123",
                        "date": "2023-09-28",
                        "agents_count": 10,
                        "active_agents_count": 5,
                        "channels_count": 8,
                        "active_channels_count": 3,
                        "messages_count": 1240,
                        "api_calls_count": 356,
                        "storage_used_bytes": 123456789,
                        "created_at": "2023-09-28T14:32:10.123456Z"
                    },
                    {
                        "tenant_id": "tenant-123",
                        "date": "2023-09-29",
                        "agents_count": 10,
                        "active_agents_count": 6,
                        "channels_count": 8,
                        "active_channels_count": 4,
                        "messages_count": 1356,
                        "api_calls_count": 412,
                        "storage_used_bytes": 124567890,
                        "created_at": "2023-09-29T14:32:10.123456Z"
                    }
                ],
                "totals": {
                    "tenant_id": "tenant-123",
                    "start_date": "2023-09-28",
                    "end_date": "2023-09-29",
                    "agents_total": 10,
                    "active_agents_total": 6,
                    "channels_total": 8,
                    "active_channels_total": 4,
                    "messages_in_total": 1500,
                    "messages_out_total": 1096,
                    "api_calls_total": 768,
                    "timestamp": "2023-09-30T00:00:00.000000Z"
                },
                "limits": {
                    "max_agents": 10,
                    "max_channels": 20,
                    "max_messages_per_day": 50000,
                    "max_api_calls_per_day": 10000,
                    "max_storage_bytes": 1073741824,
                    "concurrent_connections": 50
                },
                "success": True
            }
        }

class BillingInfo(BaseModel):
    """Billing information for a tenant."""
    tenant_id: str = Field(..., description="Tenant ID")
    plan: str = Field(..., description="Subscription plan/tier")
    billing_cycle: str = Field(..., description="Billing cycle (monthly, annual)")
    next_billing_date: str = Field(..., description="Next billing date (YYYY-MM-DD)")
    amount: float = Field(..., description="Billing amount")
    currency: str = Field(default="USD", description="Currency code")
    payment_method: str = Field(..., description="Payment method")
    status: str = Field(..., description="Billing status")

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "plan": "professional",
                "billing_cycle": "monthly",
                "next_billing_date": "2023-10-01",
                "amount": 49.99,
                "currency": "USD",
                "payment_method": "credit_card",
                "status": "active"
            }
        }