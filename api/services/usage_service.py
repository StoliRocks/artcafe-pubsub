import logging
from typing import List, Optional
from datetime import datetime, date, timedelta

from models.usage import UsageMetrics, UsageTotals
from models.channel import ChannelType
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