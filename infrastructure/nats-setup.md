# NATS Server Setup

This document describes the NATS server setup on the ArtCafe PubSub EC2 instance.

## Installation

1. **NATS Server Version**: v2.10.18 (ARM64)
   - Downloaded from: https://github.com/nats-io/nats-server/releases/
   - Installed to: `/usr/local/bin/nats-server`

2. **System Service**: `/etc/systemd/system/nats.service`
   ```ini
   [Unit]
   Description=NATS Server
   After=network.target

   [Service]
   Type=exec
   User=ubuntu
   ExecStart=/usr/local/bin/nats-server -p 4222
   Restart=always
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

3. **Service Management**:
   ```bash
   sudo systemctl enable nats
   sudo systemctl start nats
   sudo systemctl status nats
   ```

## ArtCafe PubSub Configuration

To enable NATS in the ArtCafe PubSub service, the following environment variable was added to the service override:

**File**: `/etc/systemd/system/artcafe-pubsub.service.d/override.conf`
```ini
[Service]
Environment="AGENT_TABLE_NAME=artcafe-agents"
Environment="SSH_KEY_TABLE_NAME=artcafe-ssh-keys"
Environment="CHANNEL_TABLE_NAME=artcafe-channels"
Environment="TENANT_TABLE_NAME=artcafe-tenants"
Environment="USAGE_METRICS_TABLE_NAME=artcafe-usage-metrics"
Environment="CHANNEL_SUBSCRIPTIONS_TABLE_NAME=artcafe-channel-subscriptions"
Environment="USER_TENANT_TABLE_NAME=artcafe-user-tenants"
Environment="USER_TENANT_INDEX_TABLE_NAME=artcafe-user-tenant-index"
Environment="NATS_ENABLED=true"
```

## Verification

Check that NATS is properly connected:

1. **Service Status**:
   ```bash
   sudo systemctl status artcafe-pubsub
   ```

2. **Health Endpoint**:
   ```bash
   curl http://localhost:8000/health
   ```
   Should return:
   ```json
   {
     "status": "ok",
     "nats_connected": true
   }
   ```

3. **Check Logs**:
   ```bash
   sudo journalctl -u artcafe-pubsub -n 50 | grep -i nats
   ```

## Deployment Date

These changes were deployed on May 18, 2025.