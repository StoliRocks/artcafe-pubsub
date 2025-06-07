"""
S3 Backup Service - Low-cost cloud backup for usage metrics
~$1/month for S3 storage with lifecycle policies
"""

import json
import gzip
import boto3
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from io import BytesIO

from .local_message_tracker import LocalMessageTracker

logger = logging.getLogger(__name__)


class S3BackupService:
    """
    S3-based backup for Redis usage data.
    
    Cost breakdown:
    - S3 Standard: $0.023/GB/month
    - S3 Glacier Instant: $0.004/GB/month (after 30 days)
    - Requests: Negligible for daily backups
    - Total: ~$1/month for typical usage
    """
    
    def __init__(self, bucket_name: str = "artcafe-usage-backups"):
        self.bucket_name = bucket_name
        self.s3_client = boto3.client('s3')
        self.message_tracker = LocalMessageTracker()
        self.backup_interval = 3600  # Every hour
        self.backup_task = None
        
        # Ensure bucket exists
        self._ensure_bucket()
        
    def _ensure_bucket(self):
        """Create S3 bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                
                # Add lifecycle policy to move to Glacier after 30 days
                lifecycle_policy = {
                    'Rules': [{
                        'ID': 'MoveToGlacier',
                        'Status': 'Enabled',
                        'Transitions': [{
                            'Days': 30,
                            'StorageClass': 'GLACIER_IR'  # Glacier Instant Retrieval
                        }],
                        'Expiration': {
                            'Days': 365  # Delete after 1 year
                        }
                    }]
                }
                
                self.s3_client.put_bucket_lifecycle_configuration(
                    Bucket=self.bucket_name,
                    LifecycleConfiguration=lifecycle_policy
                )
                
                logger.info(f"Created S3 bucket: {self.bucket_name}")
            except Exception as e:
                logger.error(f"Failed to create S3 bucket: {e}")
                
    async def start(self):
        """Start the backup service"""
        self.backup_task = asyncio.create_task(self._backup_loop())
        logger.info(f"S3 backup service started, backing up to s3://{self.bucket_name}")
        
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
                await asyncio.sleep(self.backup_interval)
            except Exception as e:
                logger.error(f"S3 backup error: {e}")
                await asyncio.sleep(300)  # Retry in 5 minutes
                
    async def backup_current_data(self):
        """Backup today's and yesterday's data"""
        try:
            today = datetime.now(timezone.utc)
            await self.backup_date(today)
            
            # Also backup yesterday
            yesterday = today - timedelta(days=1)
            await self.backup_date(yesterday)
            
            logger.info("S3 backup completed successfully")
            
        except Exception as e:
            logger.error(f"S3 backup failed: {e}")
            
    async def backup_date(self, date: datetime):
        """Backup a specific date's data to S3"""
        date_str = date.strftime("%Y%m%d")
        s3_key = f"daily/{date_str}/usage_{date_str}.json.gz"
        
        # Collect data (same as local backup)
        data = await self._collect_date_data(date_str)
        
        if data["tenants"]:
            # Compress data
            buffer = BytesIO()
            with gzip.open(buffer, 'wt', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            buffer.seek(0)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=buffer.getvalue(),
                ContentType='application/gzip',
                Metadata={
                    'tenant-count': str(len(data["tenants"])),
                    'backup-date': date_str
                }
            )
            
            logger.info(f"Backed up {len(data['tenants'])} tenants to S3 for {date_str}")
            
    async def _collect_date_data(self, date_str: str) -> Dict:
        """Collect all data for a specific date"""
        data = {
            "date": date_str,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tenants": {}
        }
        
        # Same collection logic as local backup
        pattern = f"stats:d:{date_str}:*"
        keys = self.message_tracker.redis_client.keys(pattern)
        
        for key in keys:
            key_str = key.decode('utf-8')
            parts = key_str.split(':')
            if len(parts) >= 4:
                tenant_id = parts[3]
                
                stats = self.message_tracker.redis_client.hgetall(key)
                if stats:
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
                    
        return data
        
    async def restore_from_s3(self, date: datetime) -> Dict:
        """Restore data from S3 backup"""
        date_str = date.strftime("%Y%m%d")
        s3_key = f"daily/{date_str}/usage_{date_str}.json.gz"
        
        try:
            # Download from S3
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=s3_key
            )
            
            # Decompress and parse
            with gzip.open(response['Body'], 'rt', encoding='utf-8') as f:
                data = json.load(f)
                
            # Restore to Redis (same as local backup)
            for tenant_id, stats in data["tenants"].items():
                daily_key = f"stats:d:{date_str}:{tenant_id}"
                self.message_tracker.redis_client.hset(daily_key, mapping={
                    "messages": stats["messages"],
                    "bytes": stats["bytes"],
                    "api_calls": stats["api_calls"]
                })
                self.message_tracker.redis_client.expire(daily_key, 86400 * 90)
                
                if stats.get("agents"):
                    agents_key = f"active:d:{date_str}:{tenant_id}:agents"
                    self.message_tracker.redis_client.sadd(agents_key, *stats["agents"])
                    self.message_tracker.redis_client.expire(agents_key, 86400)
                    
                if stats.get("channels"):
                    channels_key = f"active:d:{date_str}:{tenant_id}:channels"
                    self.message_tracker.redis_client.sadd(channels_key, *stats["channels"])
                    self.message_tracker.redis_client.expire(channels_key, 86400)
                    
            logger.info(f"Restored {len(data['tenants'])} tenants from S3 for {date_str}")
            return data["tenants"]
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.warning(f"No S3 backup found for {date_str}")
            return {}
        except Exception as e:
            logger.error(f"Error restoring from S3: {e}")
            return {}


# Singleton instance
_s3_backup_service = None


def get_s3_backup_service() -> S3BackupService:
    """Get the singleton S3 backup service instance"""
    global _s3_backup_service
    if _s3_backup_service is None:
        _s3_backup_service = S3BackupService()
    return _s3_backup_service