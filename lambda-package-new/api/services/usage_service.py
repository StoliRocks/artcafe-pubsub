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
            # Get metrics from the metrics service
            metrics_data = await metrics_service.get_metrics(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date
            )

            # Convert to UsageMetrics objects
            metrics = []
            for data in metrics_data:
                # Extract metrics
                agents_count = data.get("agents", {}).get("count", 0)
                active_agents_count = data.get("agents", {}).get("active", 0)
                channels_count = data.get("channels", {}).get("count", 0)
                active_channels_count = data.get("channels", {}).get("active", 0)
                messages_in_count = data.get("messages", {}).get("in", 0)
                messages_out_count = data.get("messages", {}).get("out", 0)
                api_calls_count = data.get("api", {}).get("calls", 0)

                # Create UsageMetrics object
                metric = UsageMetrics(
                    tenant_id=tenant_id,
                    date=data.get("date"),
                    agents_count=agents_count,
                    active_agents_count=active_agents_count,
                    channels_count=channels_count,
                    active_channels_count=active_channels_count,
                    messages_count=messages_in_count + messages_out_count,
                    api_calls_count=api_calls_count,
                    created_at=data.get("timestamp", datetime.utcnow().isoformat())
                )

                metrics.append(metric)

            # If no metrics were found, create a default one
            if not metrics:
                # Get current date in ISO format
                current_date = date.today().isoformat()

                # Create a default UsageMetrics object
                metric = UsageMetrics(
                    tenant_id=tenant_id,
                    date=current_date,
                    agents_count=0,
                    active_agents_count=0,
                    channels_count=0,
                    active_channels_count=0,
                    messages_count=0,
                    api_calls_count=0,
                    created_at=datetime.utcnow().isoformat()
                )

                metrics.append(metric)

            # Return metrics sorted by date
            return sorted(metrics, key=lambda m: m.date)

        except Exception as e:
            logger.error(f"Error getting usage metrics: {e}")

            # Return an empty list on error
            return []

    async def get_usage_totals(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> UsageTotals:
        """
        Get usage totals for a tenant.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)

        Returns:
            UsageTotals object
        """
        try:
            # Get usage totals from the metrics service
            return await metrics_service.get_usage_totals(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date
            )

        except Exception as e:
            logger.error(f"Error getting usage totals: {e}")

            # Return default usage totals on error
            return UsageTotals(
                tenant_id=tenant_id,
                start_date=start_date or date.today().isoformat(),
                end_date=end_date or date.today().isoformat(),
                agents_total=0,
                active_agents_total=0,
                channels_total=0,
                active_channels_total=0,
                messages_in_total=0,
                messages_out_total=0,
                timestamp=datetime.utcnow().isoformat()
            )

    async def increment_api_calls(self, tenant_id: str, count: int = 1):
        """
        Increment API calls count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of API calls to increment by (default: 1)
        """
        # Increment API calls metric
        metrics_service.increment_metric(tenant_id, "api", "calls", count)

        # Also update in DynamoDB for backward compatibility
        await self._increment_usage(tenant_id, "api_calls", count)

    async def increment_messages(self, tenant_id: str, count: int = 1):
        """
        Increment message count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of messages to increment by (default: 1)
        """
        # Increment message count metric
        metrics_service.increment_metric(tenant_id, "messages", "in", count)

        # Also update in DynamoDB for backward compatibility
        await self._increment_usage(tenant_id, "messages", count)

    async def set_agent_count(self, tenant_id: str, count: int):
        """
        Set agent count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of agents
        """
        # Set agent count metric
        metrics_service.set_metric(tenant_id, "agents", "count", count)

    async def set_channel_count(self, tenant_id: str, count: int):
        """
        Set channel count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of channels
        """
        # Set channel count metric
        metrics_service.set_metric(tenant_id, "channels", "count", count)

    async def update_storage(self, tenant_id: str, storage_mb: int) -> None:
        """
        Update storage usage

        Args:
            tenant_id: Tenant ID
            storage_mb: Storage usage in MB
        """
        # Set storage metric
        metrics_service.set_metric(tenant_id, "storage", "mb", storage_mb)

        try:
            today = datetime.utcnow().date().isoformat()

            # Get current usage
            item = await dynamodb.get_item(
                table_name=settings.USAGE_METRICS_TABLE_NAME,
                key={"tenant_id": tenant_id, "date": today}
            )

            if not item:
                # Create new usage record
                await dynamodb.put_item(
                    table_name=settings.USAGE_METRICS_TABLE_NAME,
                    item={
                        "tenant_id": tenant_id,
                        "date": today,
                        "messages": 0,
                        "api_calls": 0,
                        "storage_mb": storage_mb
                    }
                )
            else:
                # Update storage
                await dynamodb.update_item(
                    table_name=settings.USAGE_METRICS_TABLE_NAME,
                    key={"tenant_id": tenant_id, "date": today},
                    updates={"storage_mb": storage_mb}
                )
        except Exception as e:
            logger.error(f"Error updating storage for tenant {tenant_id}: {e}")

    async def _increment_usage(self, tenant_id: str, field: str, count: int) -> None:
        """
        Increment usage field in the legacy DynamoDB table.

        Args:
            tenant_id: Tenant ID
            field: Field to increment
            count: Increment amount
        """
        try:
            today = datetime.utcnow().date().isoformat()

            # Get current usage
            item = await dynamodb.get_item(
                table_name=settings.USAGE_METRICS_TABLE_NAME,
                key={"tenant_id": tenant_id, "date": today}
            )

            if not item:
                # Create new usage record
                new_item = {
                    "tenant_id": tenant_id,
                    "date": today,
                    "messages": 0,
                    "api_calls": 0,
                    "storage_mb": 0
                }
                new_item[field] = count

                await dynamodb.put_item(
                    table_name=settings.USAGE_METRICS_TABLE_NAME,
                    item=new_item
                )
            else:
                # Increment field
                current_value = item.get(field, 0)
                new_value = current_value + count

                await dynamodb.update_item(
                    table_name=settings.USAGE_METRICS_TABLE_NAME,
                    key={"tenant_id": tenant_id, "date": today},
                    updates={field: new_value}
                )
        except Exception as e:
            logger.error(f"Error incrementing {field} for tenant {tenant_id}: {e}")


# Singleton instance
usage_service = UsageService()