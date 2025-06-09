"""
Scalable Multi-tenant Heartbeat Service
Handles agent heartbeats efficiently using Redis for in-memory state
and periodic DynamoDB persistence.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Set, Optional, List
from collections import defaultdict

import redis.asyncio as redis
from boto3.dynamodb.conditions import Key

from core.nats_client import nats_manager
from api.db.dynamodb import DynamoDBService
from config.settings import settings

logger = logging.getLogger(__name__)


class HeartbeatService:
    """
    Efficient heartbeat processing for multi-tenant agents.
    
    Architecture:
    - Agents publish lightweight heartbeats to _heartbeat.{tenant_id}.{agent_id}
    - Service maintains in-memory state in Redis with TTL
    - Periodic batch writes to DynamoDB for persistence
    - Fast status queries from Redis for dashboard
    """
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.dynamodb = DynamoDBService()
        self.running = False
        
        # Configuration
        self.heartbeat_ttl = 90  # seconds (3x heartbeat interval)
        self.persist_interval = 60  # seconds between DynamoDB writes
        self.cleanup_interval = 300  # seconds between cleanup runs
        
        # In-memory cache for ultra-fast queries
        self.agent_cache: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._subscription = None
        
    async def start(self):
        """Start the heartbeat service"""
        try:
            logger.info("Starting Heartbeat Service")
            
            # Connect to Redis
            self.redis_client = await redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis for heartbeat tracking")
            
            # Subscribe to heartbeat messages
            self._subscription = await nats_manager.subscribe(
                "_heartbeat.>",
                cb=self._handle_heartbeat
            )
            logger.info("Subscribed to NATS heartbeat messages")
            
            # Start background tasks
            self.running = True
            asyncio.create_task(self._persist_loop())
            asyncio.create_task(self._cleanup_loop())
            
            logger.info("Heartbeat Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Heartbeat Service: {e}")
            raise
    
    async def stop(self):
        """Stop the heartbeat service"""
        logger.info("Stopping Heartbeat Service")
        self.running = False
        
        if self._subscription:
            await self._subscription.unsubscribe()
            
        if self.redis_client:
            await self.redis_client.close()
            
        logger.info("Heartbeat Service stopped")
    
    async def _handle_heartbeat(self, msg):
        """
        Handle incoming heartbeat messages.
        Expected subject format: _heartbeat.{tenant_id}.{agent_id}
        """
        try:
            # Parse subject
            parts = msg.subject.split('.')
            if len(parts) != 3 or parts[0] != '_heartbeat':
                logger.warning(f"Invalid heartbeat subject: {msg.subject}")
                return
                
            tenant_id = parts[1]
            agent_id = parts[2]
            
            # Update Redis with TTL
            redis_key = f"agent:status:{tenant_id}:{agent_id}"
            await self.redis_client.setex(
                redis_key,
                self.heartbeat_ttl,
                json.dumps({
                    "status": "online",
                    "last_seen": time.time(),
                    "last_heartbeat": datetime.now(timezone.utc).isoformat()
                })
            )
            
            # Update in-memory cache for ultra-fast queries
            self.agent_cache[tenant_id][agent_id] = time.time()
            
            # Track tenant activity
            tenant_key = f"tenant:active:{tenant_id}"
            await self.redis_client.setex(tenant_key, self.heartbeat_ttl, "1")
            
            logger.debug(f"Heartbeat from {tenant_id}/{agent_id}")
            
        except Exception as e:
            logger.error(f"Error handling heartbeat: {e}")
    
    async def get_agent_status(self, tenant_id: str, agent_id: str) -> Dict:
        """Get status for a specific agent"""
        try:
            redis_key = f"agent:status:{tenant_id}:{agent_id}"
            data = await self.redis_client.get(redis_key)
            
            if data:
                return json.loads(data)
            else:
                return {"status": "offline", "last_seen": None}
                
        except Exception as e:
            logger.error(f"Error getting agent status: {e}")
            return {"status": "unknown", "error": str(e)}
    
    async def get_tenant_agents_status(self, tenant_id: str) -> List[Dict]:
        """Get status for all agents in a tenant"""
        try:
            # Use Redis SCAN for efficient pattern matching
            pattern = f"agent:status:{tenant_id}:*"
            agent_statuses = []
            
            async for key in self.redis_client.scan_iter(match=pattern):
                # Extract agent_id from key
                agent_id = key.split(':')[-1]
                data = await self.redis_client.get(key)
                
                if data:
                    status_data = json.loads(data)
                    status_data['agent_id'] = agent_id
                    agent_statuses.append(status_data)
            
            return agent_statuses
            
        except Exception as e:
            logger.error(f"Error getting tenant agents status: {e}")
            return []
    
    async def get_online_agents_count(self, tenant_id: str) -> int:
        """Get count of online agents for a tenant (ultra-fast)"""
        # Use in-memory cache for instant response
        return len(self.agent_cache.get(tenant_id, {}))
    
    async def _persist_loop(self):
        """Periodically persist agent status to DynamoDB"""
        while self.running:
            try:
                await asyncio.sleep(self.persist_interval)
                await self._persist_to_dynamodb()
            except Exception as e:
                logger.error(f"Error in persist loop: {e}")
                await asyncio.sleep(10)
    
    async def _persist_to_dynamodb(self):
        """Batch write agent statuses to DynamoDB"""
        try:
            logger.info("Persisting agent statuses to DynamoDB")
            
            # Get all active tenants
            tenant_pattern = "tenant:active:*"
            active_tenants = set()
            
            async for key in self.redis_client.scan_iter(match=tenant_pattern):
                tenant_id = key.split(':')[-1]
                active_tenants.add(tenant_id)
            
            # Process each tenant
            for tenant_id in active_tenants:
                agents_status = await self.get_tenant_agents_status(tenant_id)
                
                if agents_status:
                    # Batch update in DynamoDB
                    for status in agents_status:
                        try:
                            # Update agent record with last_seen
                            await self.dynamodb.update_item(
                                table_name="artcafe-agents-nkey",
                                key={"agent_id": status['agent_id']},
                                update_expression="SET #status = :status, last_seen = :last_seen",
                                expression_attribute_names={"#status": "status"},
                                expression_attribute_values={
                                    ":status": "online",
                                    ":last_seen": status['last_heartbeat']
                                }
                            )
                        except Exception as e:
                            logger.error(f"Error updating agent {status['agent_id']}: {e}")
            
            logger.info(f"Persisted status for {len(active_tenants)} tenants")
            
        except Exception as e:
            logger.error(f"Error persisting to DynamoDB: {e}")
    
    async def _cleanup_loop(self):
        """Periodically clean up stale data"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_offline_agents()
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(30)
    
    async def _cleanup_offline_agents(self):
        """Mark agents as offline in DynamoDB if no recent heartbeat"""
        try:
            logger.info("Running offline agents cleanup")
            
            # Clean up in-memory cache
            current_time = time.time()
            for tenant_id in list(self.agent_cache.keys()):
                for agent_id in list(self.agent_cache[tenant_id].keys()):
                    if current_time - self.agent_cache[tenant_id][agent_id] > self.heartbeat_ttl:
                        del self.agent_cache[tenant_id][agent_id]
                        
                        # Mark as offline in DynamoDB
                        try:
                            await self.dynamodb.update_item(
                                table_name="artcafe-agents-nkey",
                                key={"agent_id": agent_id},
                                update_expression="SET #status = :status",
                                expression_attribute_names={"#status": "status"},
                                expression_attribute_values={":status": "offline"}
                            )
                        except Exception as e:
                            logger.error(f"Error marking agent {agent_id} offline: {e}")
                
                # Clean up empty tenant entries
                if not self.agent_cache[tenant_id]:
                    del self.agent_cache[tenant_id]
            
            logger.info("Cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in cleanup: {e}")


# Global instance
heartbeat_service = HeartbeatService()