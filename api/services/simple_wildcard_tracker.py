"""
Simple Wildcard Message Tracker

This simplified version doesn't require NATS server configuration changes.
It uses wildcard subscriptions to intercept ALL messages.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Set

from nats_client import nats_manager
from api.services.local_message_tracker import message_tracker

logger = logging.getLogger(__name__)


class SimpleWildcardTracker:
    """
    Tracks ALL messages using wildcard subscriptions.
    Cannot be bypassed as it monitors everything.
    """
    
    def __init__(self):
        self.tracked_subjects: Set[str] = set()
        self.stats: Dict[str, int] = {
            "total_messages": 0,
            "total_bytes": 0
        }
        
    async def start(self):
        """Start wildcard tracking"""
        try:
            # Subscribe to EVERYTHING except system subjects
            # This catches ALL messages regardless of pattern
            wildcard_patterns = [
                ">",           # Single-token subjects
                "*.*",         # Two-token subjects
                "*.*.*",       # Three-token subjects
                "*.*.*.*",     # Four-token subjects
                "*.*.*.*.*",   # Five-token subjects
                "*.*.*.*.*.>", # Everything else
            ]
            
            for pattern in wildcard_patterns:
                try:
                    await nats_manager.subscribe(
                        pattern, 
                        callback=self._track_any_message
                    )
                    logger.info(f"Wildcard tracker subscribed to: {pattern}")
                except Exception as e:
                    logger.debug(f"Could not subscribe to {pattern}: {e}")
            
            # Also subscribe to specific known patterns for redundancy
            known_patterns = [
                "tenant.>",                # Standard tenant pattern
                "agent.>",                 # Agent pattern
                "_heartbeat.>",            # Heartbeats
                "_PRESENCE.>",             # Presence
                "cyberforge.>",            # Customer patterns
                "18311d36-8299-4eeb-9f1a-126c9197190a.>",  # Direct tenant ID patterns
            ]
            
            for pattern in known_patterns:
                try:
                    await nats_manager.subscribe(
                        pattern,
                        callback=self._track_any_message
                    )
                    logger.info(f"Wildcard tracker subscribed to known pattern: {pattern}")
                except Exception as e:
                    logger.debug(f"Could not subscribe to {pattern}: {e}")
                    
            logger.info("Simple wildcard tracker started - monitoring ALL messages")
            
        except Exception as e:
            logger.error(f"Failed to start wildcard tracker: {e}")
            
    async def _track_any_message(self, msg):
        """Track ANY message that comes through"""
        try:
            # Skip NATS system subjects and inbox replies
            if msg.subject.startswith("$") or msg.subject.startswith("_INBOX."):
                return
                
            # Log unique subjects for debugging
            if msg.subject not in self.tracked_subjects:
                self.tracked_subjects.add(msg.subject)
                logger.info(f"New subject detected: {msg.subject}")
            
            # Extract tenant ID from various patterns
            tenant_id = None
            parts = msg.subject.split('.')
            
            # Pattern 1: tenant.{tenant_id}.>
            if parts[0] == 'tenant' and len(parts) > 1:
                tenant_id = parts[1]
            # Pattern 2: {tenant_id}.> (UUID at start)
            elif len(parts[0]) == 36 and '-' in parts[0]:
                tenant_id = parts[0]
            # Pattern 3: _heartbeat.{tenant_id}.{agent_id}
            elif parts[0] == '_heartbeat' and len(parts) > 1:
                tenant_id = parts[1]
            # Pattern 4: Try to find UUID anywhere in subject
            else:
                for part in parts:
                    if len(part) == 36 and part.count('-') == 4:
                        tenant_id = part
                        break
            
            # Track the message
            message_size = len(msg.data) if msg.data else 0
            
            # Update global stats
            self.stats["total_messages"] += 1
            self.stats["total_bytes"] += message_size
            
            # Track using existing message tracker
            if tenant_id:
                # Extract possible channel/topic
                channel_id = None
                if len(parts) > 1:
                    # Use second part as channel if it's not a UUID
                    if not (len(parts[1]) == 36 and '-' in parts[1]):
                        channel_id = parts[1]
                
                await message_tracker.track_message(
                    tenant_id=tenant_id,
                    agent_id=None,  # Would need to extract from message data
                    channel_id=channel_id,
                    message_size=message_size
                )
                
                logger.debug(f"Tracked: subject={msg.subject}, tenant={tenant_id}, "
                           f"channel={channel_id}, bytes={message_size}")
            else:
                # Even if we can't identify tenant, count it
                logger.warning(f"Message without identifiable tenant: {msg.subject}")
                
        except Exception as e:
            logger.error(f"Error in wildcard tracker: {e}")
            
    def get_stats(self) -> Dict:
        """Get tracking statistics"""
        return {
            "tracked_subjects": len(self.tracked_subjects),
            "unique_subjects": list(self.tracked_subjects)[:100],  # First 100
            "total_messages": self.stats["total_messages"],
            "total_bytes": self.stats["total_bytes"],
            "timestamp": datetime.utcnow().isoformat()
        }


# Global instance
wildcard_tracker = SimpleWildcardTracker()