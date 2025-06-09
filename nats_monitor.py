#!/usr/bin/env python3
"""
NATS Monitor Service - Tracks client heartbeats and messages
Runs as a separate service alongside the main API
"""

import asyncio
import json
import redis
import boto3
import logging
from datetime import datetime, timezone
import nats
import os
import sys

# Add the project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
NATS_URL = os.getenv("NATS_URL", "nats://10.0.1.241:4222")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


class NATSMonitor:
    def __init__(self):
        self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        self.dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        self.agents_table = self.dynamodb.Table('artcafe-agents')
        self.nc = None
        self.running = True
        
    async def connect(self):
        """Connect to NATS"""
        logger.info(f"Connecting to NATS at {NATS_URL}")
        self.nc = await nats.connect(NATS_URL)
        logger.info("Connected to NATS")
        
    async def monitor_heartbeats(self):
        """Update client status based on heartbeats"""
        async def handler(msg):
            try:
                # Parse _PRESENCE.tenant.{tenant_id}.client.{client_id}
                parts = msg.subject.split('.')
                if len(parts) >= 5 and parts[0] == '_PRESENCE':
                    tenant_id = parts[2]
                    client_id = parts[4]
                    data = json.loads(msg.data.decode())
                    msg_type = data.get('type', 'heartbeat')
                    
                    if msg_type in ['connect', 'heartbeat']:
                        # Update Redis for quick status checks
                        self.redis.setex(f"client:online:{client_id}", 90, "1")
                        self.redis.hset(f"client:info:{client_id}", mapping={
                            "tenant_id": tenant_id,
                            "last_seen": datetime.now(timezone.utc).isoformat(),
                            "name": data.get('metadata', {}).get('name', 'Unknown')
                        })
                        
                        # Update DynamoDB periodically (every 10th heartbeat)
                        count = self.redis.incr(f"client:hb:count:{client_id}")
                        if count % 10 == 0:
                            self.agents_table.update_item(
                                Key={'id': client_id},
                                UpdateExpression='SET last_heartbeat = :ts, #s = :status',
                                ExpressionAttributeNames={'#s': 'status'},
                                ExpressionAttributeValues={
                                    ':ts': datetime.now(timezone.utc).isoformat(),
                                    ':status': 'online'
                                }
                            )
                            logger.info(f"Updated DynamoDB status for agent {client_id}")
                            
                        if msg_type == 'connect':
                            logger.info(f"Client {client_id} connected")
                            
                    elif msg_type == 'disconnect':
                        # Remove from Redis
                        self.redis.delete(f"client:online:{client_id}")
                        # Update DynamoDB
                        self.agents_table.update_item(
                            Key={'id': client_id},
                            UpdateExpression='SET #s = :status',
                            ExpressionAttributeNames={'#s': 'status'},
                            ExpressionAttributeValues={':status': 'offline'}
                        )
                        logger.info(f"Agent {client_id} disconnected")
                        
            except Exception as e:
                logger.error(f"Error handling heartbeat: {e}")
                
        await self.nc.subscribe("_PRESENCE.>", cb=handler)
        logger.info("Subscribed to _PRESENCE.>")
        
    async def monitor_messages(self):
        """Count messages for metrics"""
        async def handler(msg):
            try:
                # Extract tenant ID from subject
                parts = msg.subject.split('.')
                tenant_id = None
                
                # Skip internal messages
                if parts[0].startswith('_'):
                    return
                
                if parts[0] == 'tenant' and len(parts) > 1:
                    tenant_id = parts[1]
                elif len(parts[0]) == 36 and '-' in parts[0]:  # UUID
                    tenant_id = parts[0]
                    
                if tenant_id:
                    # Update Redis counters (same keys as WebSocket used)
                    now = datetime.now(timezone.utc)
                    hour_key = now.strftime("%Y%m%d:%H")
                    day_key = now.strftime("%Y%m%d")
                    
                    # Hourly stats
                    self.redis.hincrby(f"stats:h:{hour_key}:{tenant_id}", "message_count", 1)
                    self.redis.hincrby(f"stats:h:{hour_key}:{tenant_id}", "bytes", len(msg.data))
                    self.redis.hincrby(f"stats:h:{hour_key}:{tenant_id}", msg.subject, 1)
                    
                    # Daily stats
                    self.redis.hincrby(f"stats:d:{day_key}:{tenant_id}", "message_count", 1)
                    self.redis.hincrby(f"stats:d:{day_key}:{tenant_id}", "bytes", len(msg.data))
                    self.redis.hincrby(f"stats:d:{day_key}:{tenant_id}", msg.subject, 1)
                    
                    # Set expiry
                    self.redis.expire(f"stats:h:{hour_key}:{tenant_id}", 86400)  # 24 hours
                    self.redis.expire(f"stats:d:{day_key}:{tenant_id}", 2592000)  # 30 days
                    
                    # Log every 100th message
                    count = int(self.redis.hget(f"stats:d:{day_key}:{tenant_id}", "message_count") or 0)
                    if count % 100 == 0:
                        logger.info(f"Tenant {tenant_id}: {count} messages today")
                    
            except Exception as e:
                logger.error(f"Error tracking message: {e}")
                
        # Subscribe to multiple patterns
        await self.nc.subscribe("*.>", cb=handler)
        await self.nc.subscribe("tenant.*.>", cb=handler)
        logger.info("Subscribed to message patterns")
        
    async def cleanup_offline_clients(self):
        """Mark clients offline if no heartbeat"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Get all agents from DynamoDB
                response = self.agents_table.scan(
                    FilterExpression='attribute_exists(id)'
                )
                
                offline_count = 0
                for item in response.get('Items', []):
                    agent_id = item['id']
                    
                    # Check Redis for recent heartbeat
                    if not self.redis.exists(f"client:online:{agent_id}"):
                        # Only update if currently marked as online
                        if item.get('status') == 'online':
                            self.agents_table.update_item(
                                Key={'id': agent_id},
                                UpdateExpression='SET #s = :status',
                                ExpressionAttributeNames={'#s': 'status'},
                                ExpressionAttributeValues={':status': 'offline'}
                            )
                            offline_count += 1
                            
                if offline_count > 0:
                    logger.info(f"Marked {offline_count} agents as offline")
                    
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                
    async def log_stats(self):
        """Periodically log statistics"""
        while self.running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                
                # Count online agents
                online_agents = len(self.redis.keys("client:online:*"))
                
                # Get today's message count
                day_key = datetime.now(timezone.utc).strftime("%Y%m%d")
                total_messages = 0
                
                for key in self.redis.keys(f"stats:d:{day_key}:*"):
                    count = self.redis.hget(key, "message_count")
                    if count:
                        total_messages += int(count)
                
                logger.info(f"Stats - Online agents: {online_agents}, Messages today: {total_messages}")
                
            except Exception as e:
                logger.error(f"Error logging stats: {e}")
                
    async def run(self):
        """Main run loop"""
        try:
            await self.connect()
            
            # Start monitoring
            await self.monitor_heartbeats()
            await self.monitor_messages()
            
            # Start background tasks
            cleanup_task = asyncio.create_task(self.cleanup_offline_clients())
            stats_task = asyncio.create_task(self.log_stats())
            
            logger.info("NATS Monitor running...")
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise
        finally:
            if self.nc:
                await self.nc.close()
            logger.info("NATS Monitor stopped")


if __name__ == "__main__":
    monitor = NATSMonitor()
    asyncio.run(monitor.run())