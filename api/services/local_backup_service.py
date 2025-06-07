"""
Local Backup Service - Simple file-based backup for usage metrics
Cost-effective alternative to DynamoDB for early-stage startups
"""

import json
import os
import gzip
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .local_message_tracker import LocalMessageTracker

logger = logging.getLogger(__name__)


class LocalBackupService:
    """
    Simple file-based backup for Redis usage data.
    
    Features:
    - Daily JSON backups compressed with gzip
    - Automatic rotation (keep last 90 days)
    - Easy to restore
    - Can migrate to DynamoDB later
    """
    
    def __init__(self, backup_dir: str = "/opt/artcafe/usage-backups"):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.message_tracker = LocalMessageTracker()
        self.backup_interval = 3600  # Every hour
        self.backup_task = None
        
    async def start(self):
        """Start the backup service"""
        self.backup_task = asyncio.create_task(self._backup_loop())
        logger.info(f"Local backup service started, backing up to {self.backup_dir}")
        
    async def stop(self):
        """Stop the backup service"""
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
                
    async def _backup_loop(self):
        """Run backups periodically"""
        while True:
            try:
                await self.backup_current_data()
                await self.cleanup_old_backups()
                await asyncio.sleep(self.backup_interval)
            except Exception as e:
                logger.error(f"Backup error: {e}")
                await asyncio.sleep(300)  # Retry in 5 minutes
                
    async def backup_current_data(self):
        """Backup current day's data"""
        try:
            today = datetime.now(timezone.utc)
            await self.backup_date(today)
            
            # Also backup yesterday to ensure complete data
            yesterday = today - timedelta(days=1)
            await self.backup_date(yesterday)
            
            logger.info("Backup completed successfully")
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            
    async def backup_date(self, date: datetime):
        """Backup a specific date's data"""
        date_str = date.strftime("%Y%m%d")
        backup_file = self.backup_dir / f"usage_{date_str}.json.gz"
        
        # Collect all data for this date
        data = {
            "date": date_str,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tenants": {}
        }
        
        # Get all tenant keys for this date
        pattern = f"stats:d:{date_str}:*"
        keys = self.message_tracker.redis_client.keys(pattern)
        
        for key in keys:
            key_str = key.decode('utf-8')
            parts = key_str.split(':')
            if len(parts) >= 4:
                tenant_id = parts[3]
                
                # Get stats
                stats = self.message_tracker.redis_client.hgetall(key)
                if stats:
                    # Get active agents and channels
                    agents_key = f"active:d:{date_str}:{tenant_id}:agents"
                    channels_key = f"active:d:{date_str}:{tenant_id}:channels"
                    
                    agents = self.message_tracker.redis_client.smembers(agents_key)
                    channels = self.message_tracker.redis_client.smembers(channels_key)
                    
                    data["tenants"][tenant_id] = {
                        "messages": int(stats.get(b'messages', 0)),
                        "bytes": int(stats.get(b'bytes', 0)),
                        "api_calls": int(stats.get(b'api_calls', 0)),
                        "agents": [a.decode('utf-8') for a in agents] if agents else [],
                        "channels": [c.decode('utf-8') for c in channels] if channels else []
                    }
        
        # Write compressed backup
        if data["tenants"]:
            with gzip.open(backup_file, 'wt', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Backed up {len(data['tenants'])} tenants for {date_str}")
            
    async def cleanup_old_backups(self):
        """Remove backups older than 90 days"""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=90)
        
        for backup_file in self.backup_dir.glob("usage_*.json.gz"):
            try:
                # Extract date from filename
                date_str = backup_file.stem.replace("usage_", "").replace(".json", "")
                file_date = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
                
                if file_date < cutoff_date:
                    backup_file.unlink()
                    logger.info(f"Deleted old backup: {backup_file.name}")
            except Exception as e:
                logger.error(f"Error cleaning up {backup_file}: {e}")
                
    async def restore_from_backup(self, date: datetime) -> Dict:
        """Restore data from backup file"""
        date_str = date.strftime("%Y%m%d")
        backup_file = self.backup_dir / f"usage_{date_str}.json.gz"
        
        if not backup_file.exists():
            logger.warning(f"No backup found for {date_str}")
            return {}
            
        try:
            with gzip.open(backup_file, 'rt', encoding='utf-8') as f:
                data = json.load(f)
                
            # Restore to Redis
            for tenant_id, stats in data["tenants"].items():
                # Restore daily stats
                daily_key = f"stats:d:{date_str}:{tenant_id}"
                self.message_tracker.redis_client.hset(daily_key, mapping={
                    "messages": stats["messages"],
                    "bytes": stats["bytes"],
                    "api_calls": stats["api_calls"]
                })
                self.message_tracker.redis_client.expire(daily_key, 86400 * 90)
                
                # Restore active sets
                if stats.get("agents"):
                    agents_key = f"active:d:{date_str}:{tenant_id}:agents"
                    self.message_tracker.redis_client.sadd(agents_key, *stats["agents"])
                    self.message_tracker.redis_client.expire(agents_key, 86400)
                    
                if stats.get("channels"):
                    channels_key = f"active:d:{date_str}:{tenant_id}:channels"
                    self.message_tracker.redis_client.sadd(channels_key, *stats["channels"])
                    self.message_tracker.redis_client.expire(channels_key, 86400)
                    
            logger.info(f"Restored {len(data['tenants'])} tenants from backup for {date_str}")
            return data["tenants"]
            
        except Exception as e:
            logger.error(f"Error restoring from backup: {e}")
            return {}
            
    async def get_backup_list(self) -> List[Dict]:
        """List all available backups"""
        backups = []
        
        for backup_file in sorted(self.backup_dir.glob("usage_*.json.gz")):
            try:
                # Get file info
                stat = backup_file.stat()
                date_str = backup_file.stem.replace("usage_", "").replace(".json", "")
                
                backups.append({
                    "date": date_str,
                    "file": backup_file.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                })
            except Exception as e:
                logger.error(f"Error listing backup {backup_file}: {e}")
                
        return backups


# Singleton instance
_backup_service = None


def get_backup_service() -> LocalBackupService:
    """Get the singleton backup service instance"""
    global _backup_service
    if _backup_service is None:
        _backup_service = LocalBackupService()
    return _backup_service