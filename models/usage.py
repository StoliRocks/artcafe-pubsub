from datetime import datetime, date
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import uuid

class UsageMetrics(BaseModel):
    """Usage metrics for a tenant."""
    tenant_id: str = Field(..., description="Tenant ID")
    timestamp_date: str = Field(..., description="Date of the metrics (YYYY-MM-DD)")
    messages: int = Field(default=0, description="Number of messages sent")
    api_calls: int = Field(default=0, description="Number of API calls made")
    storage_mb: float = Field(default=0.0, description="Storage used in MB")
    active_agents: int = Field(default=0, description="Number of active agents")
    active_channels: int = Field(default=0, description="Number of active channels")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "timestamp_date": "2023-09-28",
                "messages": 1240,
                "api_calls": 356,
                "storage_mb": 120.5,
                "active_agents": 5,
                "active_channels": 3,
                "metadata": {
                    "peak_hour": "14:00",
                    "busiest_channel": "data-processing"
                }
            }
        }

class UsageLimits(BaseModel):
    """Limits for a tenant's usage."""
    max_messages_per_day: int = Field(default=50000, description="Maximum messages per day")
    max_api_calls_per_day: int = Field(default=10000, description="Maximum API calls per day")
    max_storage_mb: int = Field(default=1000, description="Maximum storage in MB")
    max_agents: int = Field(default=20, description="Maximum number of agents")
    max_channels: int = Field(default=50, description="Maximum number of channels")

class UsageTotals(BaseModel):
    """Aggregated usage metrics."""
    messages: int = Field(default=0, description="Total number of messages")
    api_calls: int = Field(default=0, description="Total number of API calls")
    storage_mb: float = Field(default=0.0, description="Total storage used in MB")

class UsageResponse(BaseModel):
    """Response with usage metrics."""
    totals: UsageTotals
    limits: UsageLimits
    daily: List[Dict[str, Any]] = Field(default_factory=list, description="Daily usage breakdown")
    
    class Config:
        schema_extra = {
            "example": {
                "totals": {
                    "messages": 12456,
                    "api_calls": 3789,
                    "storage_mb": 156
                },
                "limits": {
                    "max_messages_per_day": 50000,
                    "max_api_calls_per_day": 10000,
                    "max_storage_mb": 1000,
                    "max_agents": 20,
                    "max_channels": 50
                },
                "daily": [
                    {"date": "2023-05-01", "messages": 1240, "api_calls": 356, "storage_mb": 120},
                    {"date": "2023-05-02", "messages": 1352, "api_calls": 412, "storage_mb": 122},
                    {"date": "2023-05-03", "messages": 1102, "api_calls": 298, "storage_mb": 126},
                    {"date": "2023-05-04", "messages": 1425, "api_calls": 387, "storage_mb": 130},
                    {"date": "2023-05-05", "messages": 986, "api_calls": 276, "storage_mb": 132},
                    {"date": "2023-05-06", "messages": 765, "api_calls": 203, "storage_mb": 135},
                    {"date": "2023-05-07", "messages": 890, "api_calls": 245, "storage_mb": 138}
                ]
            }
        }

class BillingInfo(BaseModel):
    """Billing information for a tenant."""
    tenant_id: str = Field(..., description="Tenant ID")
    plan: str = Field(..., description="Billing plan")
    billing_cycle: str = Field(..., description="Billing cycle (monthly, annual)")
    next_billing_date: str = Field(..., description="Next billing date")
    amount: float = Field(..., description="Billing amount")
    currency: str = Field(default="USD", description="Currency")
    payment_method: str = Field(..., description="Payment method")
    status: str = Field(..., description="Billing status")
    
    class Config:
        schema_extra = {
            "example": {
                "tenant_id": "tenant-123",
                "plan": "standard",
                "billing_cycle": "monthly",
                "next_billing_date": "2023-10-01",
                "amount": 49.99,
                "currency": "USD",
                "payment_method": "credit_card",
                "status": "active"
            }
        }