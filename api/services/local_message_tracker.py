"""
Local Valkey/Redis-based message tracking
Runs on the same instance as the API for simplicity
"""
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import json

logger = logging.getLogger(__name__)

class LocalMessageTracker:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance
    
    def __init__(self):
        if not self.initialized:
            self.redis_client = None
            self.enabled = False
            self.initialized = True
            
    def connect(self):
        """Connect to local Redis/Valkey"""
        try:
            self.redis_client = redis.Redis(
                host='localhost', 
                port=6379, 
                decode_responses=True,
                socket_connect_timeout=1
            )
            self.redis_client.ping()
            self.enabled = True
            logger.info("Connected to local Valkey/Redis for message tracking")
        except Exception as e:
            logger.warning(f"Could not connect to Redis/Valkey: {e}. Message tracking disabled.")
            self.enabled = False
            
    async def track_message(self, tenant_id: str, agent_id: str = None, 
                          channel_id: str = None, message_size: int = 0):
        """Track a message (async wrapper for sync Redis)"""
        if not self.enabled:
            return
            
        try:
            now = datetime.utcnow()
            hour_key = now.strftime('%Y%m%d:%H')
            day_key = now.strftime('%Y%m%d')
            
            pipe = self.redis_client.pipeline()
            
            # Hourly stats
            pipe.hincrby(f"stats:h:{hour_key}:{tenant_id}", "messages", 1)
            pipe.hincrby(f"stats:h:{hour_key}:{tenant_id}", "bytes", message_size)
            
            # Daily stats
            pipe.hincrby(f"stats:d:{day_key}:{tenant_id}", "messages", 1)
            pipe.hincrby(f"stats:d:{day_key}:{tenant_id}", "bytes", message_size)
            
            # Track unique agents/channels
            if agent_id:
                pipe.sadd(f"active:d:{day_key}:{tenant_id}:agents", agent_id)
            if channel_id:
                pipe.sadd(f"active:d:{day_key}:{tenant_id}:channels", channel_id)
                
            # Set expiry
            pipe.expire(f"stats:h:{hour_key}:{tenant_id}", 2592000)  # 30 days
            pipe.expire(f"stats:d:{day_key}:{tenant_id}", 7776000)   # 90 days
            pipe.expire(f"active:d:{day_key}:{tenant_id}:agents", 86400)  # 1 day
            pipe.expire(f"active:d:{day_key}:{tenant_id}:channels", 86400)  # 1 day
            
            pipe.execute()
            
        except Exception as e:
            logger.debug(f"Error tracking message: {e}")
            
    async def track_api_call(self, tenant_id: str):
        """Track API calls"""
        if not self.enabled:
            return
            
        try:
            now = datetime.utcnow()
            day_key = now.strftime('%Y%m%d')
            self.redis_client.hincrby(f"stats:d:{day_key}:{tenant_id}", "api_calls", 1)
        except Exception as e:
            logger.debug(f"Error tracking API call: {e}")
            
    async def get_current_stats(self, tenant_id: str) -> Dict:
        """Get real-time stats for today"""
        if not self.enabled:
            return {
                'messages': 0,
                'bytes': 0,
                'api_calls': 0,
                'active_agents': 0,
                'active_channels': 0
            }
            
        try:
            now = datetime.utcnow()
            day_key = now.strftime('%Y%m%d')
            
            pipe = self.redis_client.pipeline()
            pipe.hgetall(f"stats:d:{day_key}:{tenant_id}")
            pipe.scard(f"active:d:{day_key}:{tenant_id}:agents")
            pipe.scard(f"active:d:{day_key}:{tenant_id}:channels")
            
            day_stats, agent_count, channel_count = pipe.execute()
            
            return {
                'messages': int(day_stats.get('messages', 0)),
                'bytes': int(day_stats.get('bytes', 0)),
                'api_calls': int(day_stats.get('api_calls', 0)),
                'active_agents': agent_count,
                'active_channels': channel_count
            }
        except Exception as e:
            logger.debug(f"Error getting stats: {e}")
            return {
                'messages': 0,
                'bytes': 0,
                'api_calls': 0,
                'active_agents': 0,
                'active_channels': 0
            }
            
    async def get_usage_history(self, tenant_id: str, days: int = 7) -> List[Dict]:
        """Get historical usage data"""
        if not self.enabled:
            return []
            
        try:
            results = []
            end_date = datetime.utcnow()
            
            for i in range(days):
                date = end_date - timedelta(days=i)
                day_key = date.strftime('%Y%m%d')
                
                pipe = self.redis_client.pipeline()
                pipe.hgetall(f"stats:d:{day_key}:{tenant_id}")
                pipe.scard(f"active:d:{day_key}:{tenant_id}:agents")
                pipe.scard(f"active:d:{day_key}:{tenant_id}:channels")
                
                stats, agents, channels = pipe.execute()
                
                if stats:
                    results.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'messages': int(stats.get('messages', 0)),
                        'bytes': int(stats.get('bytes', 0)),
                        'api_calls': int(stats.get('api_calls', 0)),
                        'active_agents': agents,
                        'active_channels': channels
                    })
                    
            return sorted(results, key=lambda x: x['date'], reverse=True)
        except Exception as e:
            logger.debug(f"Error getting history: {e}")
            return []

# Global instance
message_tracker = LocalMessageTracker()