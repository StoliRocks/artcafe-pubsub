import os
import asyncio
import json
import logging
import argparse
from datetime import datetime

import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default API endpoint
DEFAULT_API_ENDPOINT = "http://localhost:8000/api/v1"

class PubSubApiClient:
    """
    Client for testing the ArtCafe.ai PubSub API.
    """
    
    def __init__(self, api_endpoint=None, token=None, tenant_id=None):
        """
        Initialize the client.
        
        Args:
            api_endpoint: API endpoint URL
            token: JWT token
            tenant_id: Tenant ID
        """
        self.api_endpoint = api_endpoint or os.getenv("API_ENDPOINT", DEFAULT_API_ENDPOINT)
        self.token = token or os.getenv("JWT_TOKEN")
        self.tenant_id = tenant_id or os.getenv("TENANT_ID")
        
        # HTTP session
        self.session = None
    
    async def __aenter__(self):
        """Enter async context manager."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        """Exit async context manager."""
        if self.session:
            await self.session.close()
    
    def _headers(self):
        """Get HTTP headers."""
        headers = {
            "Content-Type": "application/json"
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        if self.tenant_id:
            headers["x-tenant-id"] = self.tenant_id
        
        return headers
    
    async def create_tenant(self, name, admin_email):
        """Create a new tenant."""
        url = f"{self.api_endpoint}/tenants"
        
        data = {
            "name": name,
            "admin_email": admin_email,
            "subscription_tier": "basic",
            "metadata": {
                "created_by": "test_client",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        async with self.session.post(url, json=data, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to create tenant: {response_data}")
                return None
            
            self.tenant_id = response_data["tenant_id"]
            return response_data
    
    async def list_agents(self, status=None, type=None):
        """List agents."""
        url = f"{self.api_endpoint}/agents"
        
        params = {}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        
        async with self.session.get(url, params=params, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to list agents: {response_data}")
                return None
            
            return response_data
    
    async def register_agent(self, name, agent_type):
        """Register a new agent."""
        url = f"{self.api_endpoint}/agents"
        
        data = {
            "name": name,
            "type": agent_type,
            "capabilities": [
                {
                    "name": "process_data",
                    "description": "Process and transform data",
                    "parameters": {
                        "formats": ["json", "csv", "xml"],
                        "max_size_mb": 100
                    },
                    "version": "1.0.0"
                }
            ],
            "metadata": {
                "created_by": "test_client",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        async with self.session.post(url, json=data, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to register agent: {response_data}")
                return None
            
            return response_data
    
    async def get_agent(self, agent_id):
        """Get agent details."""
        url = f"{self.api_endpoint}/agents/{agent_id}"
        
        async with self.session.get(url, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to get agent: {response_data}")
                return None
            
            return response_data
    
    async def update_agent_status(self, agent_id, status):
        """Update agent status."""
        url = f"{self.api_endpoint}/agents/{agent_id}/status"
        
        data = {
            "status": status
        }
        
        async with self.session.put(url, json=data, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to update agent status: {response_data}")
                return None
            
            return response_data
    
    async def list_ssh_keys(self, agent_id=None):
        """List SSH keys."""
        url = f"{self.api_endpoint}/ssh-keys"
        
        params = {}
        if agent_id:
            params["agent_id"] = agent_id
        
        async with self.session.get(url, params=params, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to list SSH keys: {response_data}")
                return None
            
            return response_data
    
    async def add_ssh_key(self, name, public_key, agent_id=None):
        """Add a new SSH key."""
        url = f"{self.api_endpoint}/ssh-keys"
        
        data = {
            "name": name,
            "public_key": public_key,
            "metadata": {
                "created_by": "test_client",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        if agent_id:
            data["agent_id"] = agent_id
        
        async with self.session.post(url, json=data, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to add SSH key: {response_data}")
                return None
            
            return response_data
    
    async def delete_ssh_key(self, key_id):
        """Delete an SSH key."""
        url = f"{self.api_endpoint}/ssh-keys/{key_id}"
        
        async with self.session.delete(url, headers=self._headers()) as response:
            if response.status == 204:
                return {"success": True}
            
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to delete SSH key: {response_data}")
                return None
            
            return response_data
    
    async def list_channels(self, status=None, type=None):
        """List channels."""
        url = f"{self.api_endpoint}/channels"
        
        params = {}
        if status:
            params["status"] = status
        if type:
            params["type"] = type
        
        async with self.session.get(url, params=params, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to list channels: {response_data}")
                return None
            
            return response_data
    
    async def create_channel(self, name, description=None, channel_type=None):
        """Create a new channel."""
        url = f"{self.api_endpoint}/channels"
        
        data = {
            "name": name,
            "metadata": {
                "created_by": "test_client",
                "timestamp": datetime.utcnow().isoformat()
            }
        }
        
        if description:
            data["description"] = description
        
        if channel_type:
            data["type"] = channel_type
        
        async with self.session.post(url, json=data, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to create channel: {response_data}")
                return None
            
            return response_data
    
    async def get_channel(self, channel_id):
        """Get channel details."""
        url = f"{self.api_endpoint}/channels/{channel_id}"
        
        async with self.session.get(url, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to get channel: {response_data}")
                return None
            
            return response_data
    
    async def get_usage_metrics(self, start_date=None, end_date=None):
        """Get usage metrics."""
        url = f"{self.api_endpoint}/usage-metrics"
        
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        async with self.session.get(url, params=params, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to get usage metrics: {response_data}")
                return None
            
            return response_data
    
    async def get_billing_info(self):
        """Get billing information."""
        url = f"{self.api_endpoint}/billing"
        
        async with self.session.get(url, headers=self._headers()) as response:
            response_data = await response.json()
            
            if response.status != 200:
                logger.error(f"Failed to get billing info: {response_data}")
                return None
            
            return response_data


async def run_demo(api_endpoint, token, tenant_id):
    """Run a demo of the API client."""
    async with PubSubApiClient(api_endpoint, token, tenant_id) as client:
        # Create tenant if needed
        if not client.tenant_id:
            logger.info("Creating tenant...")
            tenant = await client.create_tenant("Demo Organization", "admin@example.com")
            if tenant:
                logger.info(f"Created tenant: {tenant['tenant_id']}")
                client.tenant_id = tenant['tenant_id']
                logger.info(f"API Key: {tenant['api_key']}")
                logger.info(f"Admin Token: {tenant['admin_token']}")
            else:
                logger.error("Failed to create tenant")
                return
        
        # Register an agent
        logger.info("Registering agent...")
        agent = await client.register_agent("Demo Agent", "worker")
        if agent:
            logger.info(f"Registered agent: {agent['agent_id']}")
            agent_id = agent['agent_id']
        else:
            logger.error("Failed to register agent")
            return
        
        # List agents
        logger.info("Listing agents...")
        agents = await client.list_agents()
        if agents:
            logger.info(f"Found {len(agents['agents'])} agents")
        else:
            logger.error("Failed to list agents")
        
        # Get agent details
        logger.info(f"Getting agent {agent_id}...")
        agent_details = await client.get_agent(agent_id)
        if agent_details:
            logger.info(f"Agent status: {agent_details['status']}")
        else:
            logger.error("Failed to get agent details")
        
        # Update agent status
        logger.info(f"Updating agent {agent_id} status to 'online'...")
        updated_agent = await client.update_agent_status(agent_id, "online")
        if updated_agent:
            logger.info(f"Updated agent status: {updated_agent['status']}")
        else:
            logger.error("Failed to update agent status")
        
        # Add an SSH key
        logger.info("Adding SSH key...")
        ssh_key = await client.add_ssh_key(
            "Demo Key",
            "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC0pA7JzLOJ5Ir3EzpKkfN5TJmC2zKM7y+KFsJQiqMHYVZ6hLcQgoT02W3GfQ9kNW0NFxb4KhdOoIAM+i3MyZ5LirhQwYC9eiKjRGxkjqM/NJxo+Dj0GQMzKK5O/bxxmpa6NKnwUc3revqZQ7OEFWbYxJfmXB5Obz2L3p/URS7TdPQgKM+4FpP5K8wMKxuJOO/5nSQl67D7mUjID+R1/UTv2GkjGVQtgHKdGJ2PEY9LEKGIlmJv3r/F8mTvLQqGY6hIg4bOwZbMwJgPdbixTLsNBJ9fIgcszfz/eeEPIGMukaThNQkjWNnHsujRzpKkJ+9eAm6m3YXFuZHnbGcX demo@example.com",
            agent_id=agent_id
        )
        if ssh_key:
            logger.info(f"Added SSH key: {ssh_key['key_id']}")
            key_id = ssh_key['key_id']
        else:
            logger.error("Failed to add SSH key")
            return
        
        # List SSH keys
        logger.info("Listing SSH keys...")
        ssh_keys = await client.list_ssh_keys()
        if ssh_keys:
            logger.info(f"Found {len(ssh_keys['ssh_keys'])} SSH keys")
        else:
            logger.error("Failed to list SSH keys")
        
        # Create a channel
        logger.info("Creating channel...")
        channel = await client.create_channel("Demo Channel", "Demo channel for testing", "command")
        if channel:
            logger.info(f"Created channel: {channel['id']}")
            channel_id = channel['id']
        else:
            logger.error("Failed to create channel")
            return
        
        # List channels
        logger.info("Listing channels...")
        channels = await client.list_channels()
        if channels:
            logger.info(f"Found {len(channels['channels'])} channels")
        else:
            logger.error("Failed to list channels")
        
        # Get channel details
        logger.info(f"Getting channel {channel_id}...")
        channel_details = await client.get_channel(channel_id)
        if channel_details:
            logger.info(f"Channel name: {channel_details['name']}")
        else:
            logger.error("Failed to get channel details")
        
        # Get usage metrics
        logger.info("Getting usage metrics...")
        metrics = await client.get_usage_metrics()
        if metrics:
            logger.info(f"Total messages: {metrics['totals']['messages']}")
        else:
            logger.error("Failed to get usage metrics")
        
        # Get billing info
        logger.info("Getting billing info...")
        billing = await client.get_billing_info()
        if billing:
            logger.info(f"Billing plan: {billing['plan']}")
        else:
            logger.error("Failed to get billing info")
        
        # Delete SSH key
        logger.info(f"Deleting SSH key {key_id}...")
        deleted = await client.delete_ssh_key(key_id)
        if deleted and deleted.get("success"):
            logger.info("Deleted SSH key")
        else:
            logger.error("Failed to delete SSH key")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="ArtCafe.ai PubSub API Test Client")
    
    parser.add_argument("--api-endpoint", dest="api_endpoint", default=DEFAULT_API_ENDPOINT,
                      help=f"API endpoint URL (default: {DEFAULT_API_ENDPOINT})")
    parser.add_argument("--token", dest="token", help="JWT token")
    parser.add_argument("--tenant-id", dest="tenant_id", help="Tenant ID")
    
    return parser.parse_args()


if __name__ == "__main__":
    # Parse command line arguments
    args = parse_args()
    
    # Run the demo
    asyncio.run(run_demo(args.api_endpoint, args.token, args.tenant_id))