"""
Client for querying message tracking stats from NATS instance
"""
import httpx
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class RemoteTrackingClient:
    def __init__(self, tracking_api_url: str = "http://10.0.2.139:8001"):
        """
        Initialize tracking client
        Note: Using private IP for internal communication
        """
        self.base_url = tracking_api_url
        self.client = httpx.AsyncClient(timeout=5.0)
        
    async def get_tenant_stats(self, tenant_id: str, days: int = 7) -> Dict:
        """Get usage stats for a tenant from tracking API"""
        try:
            response = await self.client.get(
                f"{self.base_url}/stats/{tenant_id}",
                params={"days": days}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching tenant stats: {e}")
            # Return empty stats on error
            return {
                'tenant_id': tenant_id,
                'period': f'{days} days',
                'stats': []
            }
            
    async def get_current_usage(self, tenant_id: str) -> Dict:
        """Get today's usage stats"""
        try:
            result = await self.get_tenant_stats(tenant_id, days=1)
            if result['stats']:
                return result['stats'][0]
            return {
                'messages': 0,
                'bytes': 0,
                'active_agents': 0,
                'active_channels': 0
            }
        except Exception as e:
            logger.error(f"Error fetching current usage: {e}")
            return {
                'messages': 0,
                'bytes': 0,
                'active_agents': 0,
                'active_channels': 0
            }
            
    async def health_check(self) -> bool:
        """Check if tracking API is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except:
            return False
            
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

# Global instance
tracking_client = RemoteTrackingClient()