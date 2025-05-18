"""
Usage metrics service.

This module provides a service for tracking and reporting usage metrics.
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, date, timedelta

from ..db import dynamodb
from config.settings import settings
from models.usage import UsageMetrics, UsageTotals
from infrastructure.metrics_service import metrics_service

logger = logging.getLogger(__name__)


class UsageService:
    """Service for usage metrics"""

    def __init__(self):
        """Initialize usage service"""
        pass

        async def get_usage_metrics(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[UsageMetrics]:
        """
        Get usage metrics for a tenant.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)

        Returns:
            List of UsageMetrics objects
        """
        try:
            # If no date range specified, use today
            if not start_date:
                start_date = date.today().isoformat()
            if not end_date:
                end_date = date.today().isoformat()
                
            # Fetch current counts from database
            agents = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Agents",
                key_conditions={"tenant_id": tenant_id}
            )
            
            channels = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Channels",
                key_conditions={"tenant_id": tenant_id}
            )
            
            # Count active agents (status == 'online')
            total_agents = len(agents) if agents else 0
            active_agents = sum(1 for agent in (agents or []) if agent.get('status') == 'online')
            
            # Count active channels
            total_channels = len(channels) if channels else 0
            active_channels = sum(1 for channel in (channels or []) if channel.get('status') == 'active')
            
            # Get message count from usage stats
            usage_table = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"
            today_key = f"{tenant_id}#daily#{date.today().isoformat()}"
            
            daily_stats = await dynamodb.get_item(
                table_name=usage_table,
                key={"pk": today_key, "sk": "stats"}
            )
            
            messages_count = 0
            api_calls_count = 0
            
            if daily_stats:
                messages_count = daily_stats.get('messages_count', 0)
                api_calls_count = daily_stats.get('api_calls_count', 0)
            
            # Create metric for today
            metric = UsageMetrics(
                date=date.today().isoformat(),
                tenant_id=tenant_id,
                agents_count=total_agents,
                active_agents_count=active_agents,
                channels_count=total_channels,
                active_channels_count=active_channels,
                messages_count=messages_count,
                api_calls_count=api_calls_count,
                created_at=datetime.utcnow().isoformat()
            )

            return [metric]

        except Exception as e:
            logger.error(f"Error getting usage metrics: {e}")
            # Return empty metrics on error
            return [UsageMetrics(
                date=date.today().isoformat(),
                tenant_id=tenant_id,
                agents_count=0,
                active_agents_count=0,
                channels_count=0,
                active_channels_count=0,
                messages_count=0,
                api_calls_count=0,
                created_at=datetime.utcnow().isoformat()
            )]


# Singleton instance
usage_service = UsageService()