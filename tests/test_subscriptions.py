import pytest
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

from models.channel_subscription import (
    ChannelSubscription,
    ChannelSubscriptionCreate,
    ChannelSubscriptionUpdate,
    SubscriptionRole
)
from api.services.channel_subscription_service import ChannelSubscriptionService


class TestChannelSubscriptionService:
    
    @pytest.fixture
    def service(self):
        return ChannelSubscriptionService()
    
    @pytest.fixture
    def mock_dynamodb(self):
        with patch('api.services.channel_subscription_service.dynamodb') as mock:
            yield mock
    
    @pytest.mark.asyncio
    async def test_create_subscription(self, service, mock_dynamodb):
        # Setup mock data
        tenant_id = "test-tenant"
        subscription_data = ChannelSubscriptionCreate(
            agent_id="agent-123",
            channel_id="channel-456",
            role=SubscriptionRole.SUBSCRIBER
        )
        
        # Mock DynamoDB responses
        mock_dynamodb.put_item = AsyncMock(return_value=None)
        mock_dynamodb.update_item = AsyncMock(return_value=None)
        
        # Execute
        result = await service.create_subscription(tenant_id, subscription_data)
        
        # Verify
        assert result.agent_id == "agent-123"
        assert result.channel_id == "channel-456"
        assert result.tenant_id == tenant_id
        assert result.role == SubscriptionRole.SUBSCRIBER
        assert result.status == "active"
        assert mock_dynamodb.put_item.called
        
    @pytest.mark.asyncio
    async def test_get_subscription(self, service, mock_dynamodb):
        # Setup mock data
        subscription_data = {
            "id": "sub-123",
            "tenant_id": "test-tenant",
            "agent_id": "agent-123",
            "channel_id": "channel-456",
            "role": SubscriptionRole.SUBSCRIBER,
            "status": "active",
            "subscribed_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Mock DynamoDB response
        mock_dynamodb.get_item = AsyncMock(return_value=subscription_data)
        
        # Execute
        result = await service.get_subscription("channel-456", "agent-123")
        
        # Verify
        assert result.id == "sub-123"
        assert result.agent_id == "agent-123"
        assert result.channel_id == "channel-456"
        assert result.role == SubscriptionRole.SUBSCRIBER
        
    @pytest.mark.asyncio
    async def test_update_subscription(self, service, mock_dynamodb):
        # Setup mock data
        existing_subscription = {
            "id": "sub-123",
            "tenant_id": "test-tenant",
            "agent_id": "agent-123",
            "channel_id": "channel-456",
            "role": SubscriptionRole.SUBSCRIBER,
            "status": "active",
            "subscribed_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        update_data = ChannelSubscriptionUpdate(
            role=SubscriptionRole.PUBLISHER,
            permissions={"read": True, "write": True, "publish": True}
        )
        
        # Mock DynamoDB responses
        mock_dynamodb.get_item = AsyncMock(
            side_effect=[
                existing_subscription,  # First call for get_subscription
                {**existing_subscription, **update_data.dict()}  # Second call after update
            ]
        )
        mock_dynamodb.update_item = AsyncMock(return_value=None)
        
        # Execute
        result = await service.update_subscription("channel-456", "agent-123", update_data)
        
        # Verify
        assert result.role == SubscriptionRole.PUBLISHER
        assert mock_dynamodb.update_item.called
        
    @pytest.mark.asyncio
    async def test_delete_subscription(self, service, mock_dynamodb):
        # Setup mock data
        existing_subscription = {
            "id": "sub-123",
            "tenant_id": "test-tenant",
            "agent_id": "agent-123",
            "channel_id": "channel-456",
            "role": SubscriptionRole.SUBSCRIBER,
            "status": "active"
        }
        
        # Mock DynamoDB responses
        mock_dynamodb.get_item = AsyncMock(return_value=existing_subscription)
        mock_dynamodb.delete_item = AsyncMock(return_value=None)
        mock_dynamodb.update_item = AsyncMock(return_value=None)
        
        # Execute
        result = await service.delete_subscription("test-tenant", "channel-456", "agent-123")
        
        # Verify
        assert result is True
        assert mock_dynamodb.delete_item.called
        
    @pytest.mark.asyncio
    async def test_list_channel_subscriptions(self, service, mock_dynamodb):
        # Setup mock data
        subscription_items = [{
            "id": f"sub-{i}",
            "tenant_id": "test-tenant",
            "agent_id": f"agent-{i}",
            "channel_id": "channel-456",
            "role": SubscriptionRole.SUBSCRIBER,
            "status": "active",
            "subscribed_at": datetime.utcnow().isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        } for i in range(3)]
        
        # Mock DynamoDB response
        mock_dynamodb.query = AsyncMock(return_value={
            "Items": subscription_items,
            "LastEvaluatedKey": None
        })
        
        # Execute
        result = await service.list_channel_subscriptions("channel-456")
        
        # Verify
        assert len(result["subscriptions"]) == 3
        assert result["next_token"] is None
        assert all(sub.channel_id == "channel-456" for sub in result["subscriptions"])
        
    @pytest.mark.asyncio
    async def test_update_last_activity(self, service, mock_dynamodb):
        # Mock DynamoDB response
        mock_dynamodb.update_item = AsyncMock(return_value=None)
        
        # Execute
        await service.update_last_activity("channel-456", "agent-123", "message_sent")
        
        # Verify
        assert mock_dynamodb.update_item.called
        
    @pytest.mark.asyncio
    async def test_update_connection_status(self, service, mock_dynamodb):
        # Mock DynamoDB response  
        mock_dynamodb.update_item = AsyncMock(return_value=None)
        
        # Execute - test connected
        await service.update_connection_status(
            "channel-456", 
            "agent-123",
            connected=True,
            connection_id="ws-conn-123"
        )
        
        # Verify
        assert mock_dynamodb.update_item.called
        
        # Execute - test disconnected
        await service.update_connection_status(
            "channel-456",
            "agent-123", 
            connected=False
        )
        
        # Verify
        assert mock_dynamodb.update_item.call_count == 2