"""
Channel Bridge Service - Bridges NATS messages to WebSocket connections
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

from nats_client import nats_manager
from config.settings import settings

logger = logging.getLogger(__name__)


class ChannelBridgeService:
    """Service that bridges NATS channel messages to WebSocket connections via AWS API Gateway"""
    
    def __init__(self):
        self.nats_manager = nats_manager
        self.apigateway_client = None
        self.lambda_client = None
        self.subscriptions: Dict[str, Any] = {}
        self.running = False
        
        # AWS API Gateway WebSocket endpoint
        self.websocket_api_id = settings.AWS_WEBSOCKET_API_ID or "cxxx228bta"
        self.websocket_stage = settings.AWS_WEBSOCKET_STAGE or "production"
        self.websocket_region = settings.AWS_REGION or "us-east-1"
        
        if self.websocket_api_id and self.websocket_api_id != "your-api-id-here":
            self.websocket_endpoint = f"https://{self.websocket_api_id}.execute-api.{self.websocket_region}.amazonaws.com/{self.websocket_stage}"
            logger.info(f"WebSocket endpoint configured: {self.websocket_endpoint}")
        else:
            logger.warning("AWS WebSocket API ID not configured - channel bridge disabled")
    
    async def start(self):
        """Start the channel bridge service"""
        if not self.websocket_api_id or self.websocket_api_id == "your-api-id-here":
            logger.warning("Channel bridge service not starting - AWS WebSocket API not configured")
            return
            
        try:
            # Initialize AWS clients
            self.apigateway_client = boto3.client(
                'apigatewaymanagementapi',
                endpoint_url=self.websocket_endpoint,
                region_name=self.websocket_region
            )
            
            self.lambda_client = boto3.client(
                'lambda',
                region_name=self.websocket_region
            )
            
            # Connect to NATS
            if not self.nats_manager.is_connected:
                await self.nats_manager.connect()
            
            self.running = True
            logger.info("Channel bridge service started")
            
            # Subscribe to all tenant channels (in production, this would be more selective)
            # For now, we'll rely on individual channel subscriptions
            
        except Exception as e:
            logger.error(f"Failed to start channel bridge service: {e}")
            self.running = False
    
    async def stop(self):
        """Stop the channel bridge service"""
        self.running = False
        
        # Unsubscribe from all channels
        for sub_id, sub_info in list(self.subscriptions.items()):
            try:
                await sub_info['subscription'].unsubscribe()
            except Exception as e:
                logger.error(f"Error unsubscribing from {sub_id}: {e}")
        
        self.subscriptions.clear()
        logger.info("Channel bridge service stopped")
    
    async def bridge_channel(self, tenant_id: str, channel_id: str):
        """Start bridging a specific channel to WebSocket clients"""
        if not self.running:
            logger.warning("Channel bridge service not running")
            return
            
        # NATS subject for this channel
        subject = f"tenant.{tenant_id}.channel.{channel_id}"
        sub_id = f"{tenant_id}:{channel_id}"
        
        # Check if already subscribed
        if sub_id in self.subscriptions:
            logger.info(f"Already bridging channel {sub_id}")
            return
        
        try:
            # Subscribe to NATS channel
            async def message_handler(msg):
                try:
                    # Parse NATS message
                    data = json.loads(msg.data.decode())
                    
                    # Forward to WebSocket connections
                    await self._forward_to_websocket(tenant_id, channel_id, data)
                    
                except Exception as e:
                    logger.error(f"Error handling channel message: {e}")
            
            subscription = await self.nats_manager.subscribe(subject, callback=message_handler)
            self.subscriptions[sub_id] = {
                'subscription': subscription,
                'tenant_id': tenant_id,
                'channel_id': channel_id,
                'subject': subject
            }
            
            logger.info(f"Started bridging channel {sub_id} (subject: {subject})")
            
        except Exception as e:
            logger.error(f"Failed to bridge channel {sub_id}: {e}")
    
    async def _forward_to_websocket(self, tenant_id: str, channel_id: str, data: Dict[str, Any]):
        """Forward a message to WebSocket connections subscribed to this channel"""
        try:
            # Query DynamoDB for connections subscribed to this channel
            # In production, this would use a GSI on channelId
            # For now, we'll use Lambda to handle the distribution
            
            # Prepare the message
            message = {
                'type': 'channel_message',
                'channel': channel_id,
                'tenant': tenant_id,
                'from': data.get('from', 'Unknown'),
                'content': data.get('content', data),
                'timestamp': data.get('timestamp', datetime.utcnow().isoformat())
            }
            
            # Invoke Lambda to distribute the message
            # The Lambda function will query connections and send to each
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.lambda_client.invoke(
                    FunctionName='artcafe-websocket-handler',
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps({
                        'action': 'broadcast',
                        'tenant': tenant_id,
                        'channel': channel_id,
                        'message': message
                    })
                )
            )
            
            logger.debug(f"Forwarded message to WebSocket for channel {channel_id}")
            
        except Exception as e:
            logger.error(f"Failed to forward to WebSocket: {e}")
    
    async def publish_to_channel(self, tenant_id: str, channel_id: str, message: Dict[str, Any]):
        """Publish a message to a NATS channel (called when WebSocket clients send messages)"""
        if not self.nats_manager.is_connected:
            logger.error("NATS not connected")
            return
        
        subject = f"tenant.{tenant_id}.channel.{channel_id}"
        
        try:
            # Add metadata to the message
            message['timestamp'] = datetime.utcnow().isoformat()
            message['tenant_id'] = tenant_id
            message['channel_id'] = channel_id
            
            # Publish to NATS
            await self.nats_manager.publish(subject, message)
            logger.debug(f"Published message to NATS channel {subject}")
            
        except Exception as e:
            logger.error(f"Failed to publish to NATS channel: {e}")


# Global instance
channel_bridge = ChannelBridgeService()