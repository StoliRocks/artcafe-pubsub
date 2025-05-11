from typing import Dict, List, Optional
from datetime import date
from pydantic import BaseModel


class UsageTotal(BaseModel):
    """Usage totals"""
    messages: int
    api_calls: int
    storage_mb: int


class UsageLimits(BaseModel):
    """Usage limits"""
    max_messages_per_day: int
    max_api_calls_per_day: int
    max_storage_mb: int


class DailyUsage(BaseModel):
    """Daily usage metrics"""
    date: str  # ISO format date
    messages: int
    api_calls: int
    storage_mb: int


class UsageMetrics(BaseModel):
    """Usage metrics model"""
    totals: UsageTotal
    limits: UsageLimits
    daily: List[DailyUsage]


class UsageMetricsResponse(BaseModel):
    """Usage metrics response model"""
    metrics: UsageMetrics
    success: bool = True