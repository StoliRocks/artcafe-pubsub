import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from ..db import dynamodb
from config.settings import settings
from models import UsageMetrics, UsageTotal, UsageLimits, DailyUsage

logger = logging.getLogger(__name__)


class UsageService:
    """Service for usage metrics"""
    
    async def get_usage_metrics(self, tenant_id: str, 
                              start_date: Optional[str] = None,
                              end_date: Optional[str] = None) -> UsageMetrics:
        """
        Get usage metrics for a tenant
        
        Args:
            tenant_id: Tenant ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            
        Returns:
            Usage metrics
        """
        try:
            # If no dates provided, use last 7 days
            if not start_date:
                start_date = (datetime.utcnow() - timedelta(days=7)).date().isoformat()
            if not end_date:
                end_date = datetime.utcnow().date().isoformat()
                
            # Query usage metrics from DynamoDB
            filter_expression = "tenant_id = :tenant_id AND #date BETWEEN :start_date AND :end_date"
            expression_values = {
                ":tenant_id": tenant_id,
                ":start_date": start_date,
                ":end_date": end_date
            }
            
            result = await dynamodb.scan_items(
                table_name=settings.USAGE_METRICS_TABLE_NAME,
                filter_expression=filter_expression,
                expression_values=expression_values
            )
            
            # Convert to DailyUsage models
            daily_metrics = []
            total_messages = 0
            total_api_calls = 0
            total_storage_mb = 0
            
            for item in result["items"]:
                daily = DailyUsage(
                    date=item["date"],
                    messages=item.get("messages", 0),
                    api_calls=item.get("api_calls", 0),
                    storage_mb=item.get("storage_mb", 0)
                )
                daily_metrics.append(daily)
                
                # Update totals
                total_messages += daily.messages
                total_api_calls += daily.api_calls
                total_storage_mb = max(total_storage_mb, daily.storage_mb)
            
            # Sort by date
            daily_metrics.sort(key=lambda x: x.date)
            
            # Create totals and limits
            totals = UsageTotal(
                messages=total_messages,
                api_calls=total_api_calls,
                storage_mb=total_storage_mb
            )
            
            limits = UsageLimits(
                max_messages_per_day=50000,
                max_api_calls_per_day=10000,
                max_storage_mb=1000
            )
            
            # Create usage metrics
            return UsageMetrics(
                totals=totals,
                limits=limits,
                daily=daily_metrics
            )
        except Exception as e:
            logger.error(f"Error getting usage metrics for tenant {tenant_id}: {e}")
            raise
            
    async def increment_api_calls(self, tenant_id: str, count: int = 1) -> None:
        """
        Increment API calls count
        
        Args:
            tenant_id: Tenant ID
            count: Number of API calls to add
        """
        await self._increment_usage(tenant_id, "api_calls", count)
            
    async def increment_messages(self, tenant_id: str, count: int = 1) -> None:
        """
        Increment messages count
        
        Args:
            tenant_id: Tenant ID
            count: Number of messages to add
        """
        await self._increment_usage(tenant_id, "messages", count)
            
    async def update_storage(self, tenant_id: str, storage_mb: int) -> None:
        """
        Update storage usage
        
        Args:
            tenant_id: Tenant ID
            storage_mb: Storage usage in MB
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
        Increment usage field
        
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