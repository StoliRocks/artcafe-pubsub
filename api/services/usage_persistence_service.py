"""
Usage Persistence Service - Syncs Valkey/Redis data to DynamoDB for durability
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from .local_message_tracker import LocalMessageTracker

logger = logging.getLogger(__name__)


class UsagePersistenceService:
    """
    Manages persistent storage of usage metrics in DynamoDB.
    
    Architecture:
    - Valkey/Redis: Hot data for real-time queries (last 30 days)
    - DynamoDB: Cold storage for billing and historical data (90+ days)
    - Sync Strategy: Periodic background sync with reconciliation
    """
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table_name = 'artcafe-usage-metrics-persistent'
        self.table = self.dynamodb.Table(self.table_name)
        self.message_tracker = LocalMessageTracker()
        self.sync_interval = 300  # 5 minutes
        self.sync_task = None
        
    async def start(self):
        """Start the background sync task"""
        self.sync_task = asyncio.create_task(self._sync_loop())
        logger.info("Usage persistence service started")
        
    async def stop(self):
        """Stop the background sync task"""
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
                
    async def _sync_loop(self):
        """Background task that periodically syncs data to DynamoDB"""
        while True:
            try:
                await self._sync_all_data()
                await asyncio.sleep(self.sync_interval)
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                await asyncio.sleep(60)  # Retry after 1 minute on error
                
    async def _sync_all_data(self):
        """Sync all recent data from Redis to DynamoDB"""
        try:
            # Get current date and sync last 2 days of data
            today = datetime.now(timezone.utc)
            
            for days_ago in range(2):  # Today and yesterday
                date = today - timedelta(days=days_ago)
                await self._sync_daily_data(date)
                
            logger.info("Usage data sync completed successfully")
            
        except Exception as e:
            logger.error(f"Error syncing usage data: {e}")
            
    async def _sync_daily_data(self, date: datetime):
        """Sync a specific day's data to DynamoDB"""
        date_str = date.strftime("%Y%m%d")
        
        # Get all tenant IDs that have data for this date
        tenant_pattern = f"stats:d:{date_str}:*"
        tenant_keys = await self._get_redis_keys(tenant_pattern)
        
        for key in tenant_keys:
            try:
                # Extract tenant_id from key
                parts = key.split(':')
                if len(parts) >= 4:
                    tenant_id = parts[3]
                    
                    # Get stats from Redis
                    stats = await self._get_redis_stats(key)
                    
                    if stats:
                        # Get active agents and channels
                        agents = await self._get_redis_set(f"active:d:{date_str}:{tenant_id}:agents")
                        channels = await self._get_redis_set(f"active:d:{date_str}:{tenant_id}:channels")
                        
                        # Store in DynamoDB
                        await self._store_in_dynamodb(
                            tenant_id=tenant_id,
                            date_str=date_str,
                            stats=stats,
                            agents=agents,
                            channels=channels
                        )
                        
            except Exception as e:
                logger.error(f"Error syncing data for key {key}: {e}")
                
    async def _get_redis_keys(self, pattern: str) -> List[str]:
        """Get all Redis keys matching a pattern"""
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.message_tracker.redis_client.keys,
            pattern
        )
        
    async def _get_redis_stats(self, key: str) -> Optional[Dict]:
        """Get stats from Redis hash"""
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            self.message_tracker.redis_client.hgetall,
            key
        )
        
        if data:
            return {
                'messages': int(data.get(b'messages', 0)),
                'bytes': int(data.get(b'bytes', 0)),
                'api_calls': int(data.get(b'api_calls', 0))
            }
        return None
        
    async def _get_redis_set(self, key: str) -> Set[str]:
        """Get members of a Redis set"""
        loop = asyncio.get_event_loop()
        members = await loop.run_in_executor(
            None,
            self.message_tracker.redis_client.smembers,
            key
        )
        return {m.decode('utf-8') for m in members} if members else set()
        
    async def _store_in_dynamodb(
        self,
        tenant_id: str,
        date_str: str,
        stats: Dict,
        agents: Set[str],
        channels: Set[str]
    ):
        """Store usage data in DynamoDB"""
        try:
            # Prepare item
            item = {
                'tenant_id': tenant_id,
                'date': date_str,
                'message_count': stats['messages'],
                'byte_count': stats['bytes'],
                'api_call_count': stats['api_calls'],
                'active_agents': list(agents),
                'active_channels': list(channels),
                'agent_count': len(agents),
                'channel_count': len(channels),
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'ttl': int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp())  # 1 year retention
            }
            
            # Use conditional put to avoid overwriting newer data
            self.table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(tenant_id) OR last_updated < :updated',
                ExpressionAttributeValues={
                    ':updated': item['last_updated']
                }
            )
            
            logger.debug(f"Stored usage data for tenant {tenant_id} on {date_str}")
            
        except ClientError as e:
            if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
                logger.error(f"Error storing data in DynamoDB: {e}")
                
    async def recover_from_dynamodb(self, date: datetime) -> Dict[str, Dict]:
        """Recover data from DynamoDB back to Redis (for disaster recovery)"""
        date_str = date.strftime("%Y%m%d")
        recovered_data = {}
        
        try:
            # Scan DynamoDB for all tenants on this date
            response = self.table.query(
                IndexName='DateIndex',
                KeyConditionExpression=Key('date').eq(date_str)
            )
            
            for item in response.get('Items', []):
                tenant_id = item['tenant_id']
                
                # Restore to Redis
                daily_key = f"stats:d:{date_str}:{tenant_id}"
                
                # Restore stats
                await self._restore_to_redis_hash(daily_key, {
                    'messages': item['message_count'],
                    'bytes': item['byte_count'],
                    'api_calls': item['api_call_count']
                })
                
                # Restore active sets
                if item.get('active_agents'):
                    agents_key = f"active:d:{date_str}:{tenant_id}:agents"
                    await self._restore_to_redis_set(agents_key, item['active_agents'])
                    
                if item.get('active_channels'):
                    channels_key = f"active:d:{date_str}:{tenant_id}:channels"
                    await self._restore_to_redis_set(channels_key, item['active_channels'])
                    
                recovered_data[tenant_id] = {
                    'messages': item['message_count'],
                    'bytes': item['byte_count'],
                    'api_calls': item['api_call_count']
                }
                
            logger.info(f"Recovered data for {len(recovered_data)} tenants on {date_str}")
            return recovered_data
            
        except Exception as e:
            logger.error(f"Error recovering data from DynamoDB: {e}")
            return {}
            
    async def _restore_to_redis_hash(self, key: str, data: Dict):
        """Restore data to Redis hash"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.message_tracker.redis_client.hmset,
            key,
            data
        )
        
    async def _restore_to_redis_set(self, key: str, members: List[str]):
        """Restore data to Redis set"""
        if members:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.message_tracker.redis_client.sadd,
                key,
                *members
            )
            
    async def get_usage_summary(self, tenant_id: str, days: int = 30) -> Dict:
        """
        Get usage summary combining Redis (hot) and DynamoDB (cold) data
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        summary = {
            'tenant_id': tenant_id,
            'period_days': days,
            'total_messages': 0,
            'total_bytes': 0,
            'total_api_calls': 0,
            'daily_breakdown': []
        }
        
        # First try Redis for recent data (last 30 days)
        for i in range(min(days, 30)):
            date = end_date - timedelta(days=i)
            date_str = date.strftime("%Y%m%d")
            
            # Try Redis first
            stats = await self._get_redis_stats(f"stats:d:{date_str}:{tenant_id}")
            
            if stats:
                summary['total_messages'] += stats['messages']
                summary['total_bytes'] += stats['bytes']
                summary['total_api_calls'] += stats['api_calls']
                summary['daily_breakdown'].append({
                    'date': date_str,
                    'messages': stats['messages'],
                    'bytes': stats['bytes'],
                    'api_calls': stats['api_calls'],
                    'source': 'redis'
                })
                
        # For older data, query DynamoDB
        if days > 30:
            older_data = await self._query_dynamodb_range(
                tenant_id,
                start_date,
                end_date - timedelta(days=30)
            )
            
            for item in older_data:
                summary['total_messages'] += item['message_count']
                summary['total_bytes'] += item['byte_count']
                summary['total_api_calls'] += item['api_call_count']
                summary['daily_breakdown'].append({
                    'date': item['date'],
                    'messages': item['message_count'],
                    'bytes': item['byte_count'],
                    'api_calls': item['api_call_count'],
                    'source': 'dynamodb'
                })
                
        return summary
        
    async def _query_dynamodb_range(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict]:
        """Query DynamoDB for a date range"""
        items = []
        
        try:
            # Query each day in the range
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime("%Y%m%d")
                
                response = self.table.get_item(
                    Key={
                        'tenant_id': tenant_id,
                        'date': date_str
                    }
                )
                
                if 'Item' in response:
                    items.append(response['Item'])
                    
                current_date += timedelta(days=1)
                
        except Exception as e:
            logger.error(f"Error querying DynamoDB: {e}")
            
        return items


# Singleton instance
_persistence_service = None


def get_persistence_service() -> UsagePersistenceService:
    """Get the singleton persistence service instance"""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = UsagePersistenceService()
    return _persistence_service