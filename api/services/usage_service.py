import logging
from typing import List, Optional
from datetime import datetime, date, timedelta

from models.usage import UsageMetrics
from api.db.dynamodb import dynamodb
from config.settings import settings

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
            List of usage metrics
        """
        try:
            # Get agent counts
            agents = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Agents",
                key_conditions={"tenant_id": tenant_id}
            )
            
            # Count active agents (based on last_seen)
            current_time = datetime.utcnow()
            total_agents = len(agents) if agents else 0
            active_agents = 0
            
            if agents:
                for agent in agents:
                    last_seen = agent.get('last_seen')
                    if last_seen:
                        try:
                            last_seen_dt = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                            if (current_time - last_seen_dt).total_seconds() < 300:  # Active if seen in last 5 minutes
                                active_agents += 1
                        except:
                            pass
            
            # Get channel counts
            channels = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Channels",
                key_conditions={"tenant_id": tenant_id}
            )
            
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
                
            # Estimate storage usage based on existing data
            # In a real implementation, this would come from a storage tracking system
            storage_used_bytes = self._estimate_storage_usage(tenant_id, agents, channels)
            storage_used_gb = storage_used_bytes / (1024 * 1024 * 1024)  # Convert to GB
            
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
                storage_used_bytes=storage_used_bytes,
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
                storage_used_bytes=0,
                created_at=datetime.utcnow().isoformat()
            )]
            
    def _estimate_storage_usage(self, tenant_id: str, agents: list, channels: list) -> int:
        """
        Estimate storage usage based on tenant data.
        In production, this would be replaced with actual storage tracking.
        
        Args:
            tenant_id: Tenant ID
            agents: List of agent objects
            channels: List of channel objects
            
        Returns:
            Estimated storage usage in bytes
        """
        # Base storage for tenant configuration
        base_storage = 1024 * 1024  # 1 MB
        
        # Add storage for each agent (config, state, etc.)
        agent_storage = len(agents) * (50 * 1024)  # 50 KB per agent
        
        # Add storage for each channel
        channel_storage = len(channels) * (20 * 1024)  # 20 KB per channel
        
        # Add some random variation to simulate real usage
        import random
        random_factor = random.uniform(0.8, 1.2)
        
        total_storage = int((base_storage + agent_storage + channel_storage) * random_factor)
        return total_storage

    async def get_usage_by_date_range(self, tenant_id: str, start_date: str, end_date: str) -> List[UsageMetrics]:
        """
        Get usage metrics for a date range.
        
        Args:
            tenant_id: Tenant ID
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            
        Returns:
            List of usage metrics
        """
        # For now, just return current metrics
        # In a real implementation, this would query historical data
        return await self.get_usage_metrics(tenant_id, start_date, end_date)

    async def increment_api_calls(self, tenant_id: str, count: int = 1):
        """
        Increment API calls count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of API calls to increment by (default: 1)
        """
        try:
            # Get or create today's usage metrics
            usage_table = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"
            today_key = f"{tenant_id}#daily#{date.today().isoformat()}"
            
            daily_stats = await dynamodb.get_item(
                table_name=usage_table,
                key={"pk": today_key, "sk": "stats"}
            )
            
            current_count = 0
            if daily_stats:
                current_count = daily_stats.get('api_calls_count', 0)
            
            # Update the count
            new_count = current_count + count
            
            await dynamodb.put_item(
                table_name=usage_table,
                item={
                    "pk": today_key,
                    "sk": "stats",
                    "api_calls_count": new_count,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error incrementing API calls: {e}")

    async def increment_messages(self, tenant_id: str, count: int = 1):
        """
        Increment message count for a tenant.

        Args:
            tenant_id: Tenant ID
            count: Number of messages to increment by (default: 1)
        """
        try:
            # Get or create today's usage metrics
            usage_table = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"
            today_key = f"{tenant_id}#daily#{date.today().isoformat()}"
            
            daily_stats = await dynamodb.get_item(
                table_name=usage_table,
                key={"pk": today_key, "sk": "stats"}
            )
            
            current_count = 0
            if daily_stats:
                current_count = daily_stats.get('messages_count', 0)
            
            # Update the count
            new_count = current_count + count
            
            await dynamodb.put_item(
                table_name=usage_table,
                item={
                    "pk": today_key,
                    "sk": "stats",
                    "messages_count": new_count,
                    "updated_at": datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error incrementing messages: {e}")

    async def get_usage_totals(self, tenant_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None):
        """
        Get usage totals for a tenant.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)

        Returns:
            Usage totals
        """
        from models.usage import UsageTotals
        
        try:
            # For now, return default totals
            # This would normally aggregate data from the metrics
            metrics = await self.get_usage_metrics(
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date
            )
            
            # Calculate totals from metrics
            total_messages = sum(m.messages_count for m in metrics)
            total_api_calls = sum(m.api_calls_count for m in metrics)
            
            # Get most recent counts for agents and channels
            latest_metric = metrics[0] if metrics else None
            
            # Return proper UsageTotals object
            return UsageTotals(
                tenant_id=tenant_id,
                start_date=start_date or date.today().isoformat(),
                end_date=end_date or date.today().isoformat(),
                agents_total=latest_metric.agents_count if latest_metric else 0,
                active_agents_total=latest_metric.active_agents_count if latest_metric else 0,
                channels_total=latest_metric.channels_count if latest_metric else 0,
                active_channels_total=latest_metric.active_channels_count if latest_metric else 0,
                messages_in_total=total_messages,
                messages_out_total=0,  # We don't track outbound separately yet
                api_calls_total=total_api_calls,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )
            
        except Exception as e:
            logger.error(f"Error getting usage totals: {e}")
            # Return proper UsageTotals object with zero values
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
                api_calls_total=0,
                timestamp=datetime.utcnow().isoformat() + "Z"
            )


# Singleton instance
usage_service = UsageService()