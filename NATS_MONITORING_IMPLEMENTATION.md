# NATS Monitoring Implementation Guide

## Overview

This document describes the new NATS-based monitoring system that replaces WebSocket-based tracking for clients connecting directly to NATS with NKeys.

## Architecture

### Core Components

1. **NATS Monitoring Service** (`api/services/nats_monitoring_service.py`)
   - Subscribes to all tenant message subjects using wildcards
   - Tracks messages, client presence, and advanced metrics
   - Provides multi-tenant isolation and security
   - Implements tiered metrics for different subscription levels

2. **Heartbeat Handler** (`api/services/nats_heartbeat_handler.py`)
   - Processes client heartbeats for presence detection
   - Validates heartbeat data and updates client status
   - Monitors client health and alerts on issues

3. **Metrics API Routes** (`api/routes/metrics_routes.py`)
   - Provides REST endpoints for accessing metrics
   - Enforces tier-based access control
   - Returns real-time and historical analytics

## Security Features

### Multi-Tenant Isolation
- Each tenant's messages are isolated using subject namespacing
- Wildcard subscriptions are scoped to individual tenants
- No cross-tenant data leakage

### Anomaly Detection
- Message rate spike detection (10x normal)
- Error rate monitoring (>10% threshold)
- Unusual subject pattern detection
- Real-time alerting for security events

## Metric Tiers

### Basic Tier (Free/Starter)
- Message counts
- Active client counts
- Basic throughput metrics
- Current day statistics

### Professional Tier
- All Basic features plus:
- Message latency tracking
- Throughput analytics (Mbps)
- Subject distribution analysis
- 7-day historical data
- Client presence tracking

### Enterprise Tier
- All Professional features plus:
- Anomaly detection
- Predictive analytics
- Client behavior analysis
- Error rate monitoring
- 30-day historical data
- Custom alerting

## Client Requirements

### Heartbeat Protocol
Clients must implement heartbeats to maintain presence:

```json
{
  "client_id": "string",
  "tenant_id": "string",
  "timestamp": "ISO8601",
  "status": "healthy|degraded|unhealthy",
  "metrics": {
    "messages_sent": 0,
    "messages_received": 0,
    "errors": 0,
    "uptime_seconds": 0
  }
}
```

Heartbeat subject: `_HEARTBEAT.tenant.{tenant_id}.client.{client_id}`
Frequency: Every 30 seconds
Timeout: 90 seconds marks client offline

## API Endpoints

### GET /api/v1/metrics/realtime
Real-time metrics based on subscription tier

### GET /api/v1/metrics/presence
Current client presence information

### GET /api/v1/metrics/analytics?period=24h
Historical analytics (Professional/Enterprise)

### GET /api/v1/metrics/anomalies?hours=24
Detected anomalies (Enterprise only)

### GET /api/v1/metrics/health-check
System health overview

## Implementation Steps

1. **Deploy the monitoring service**
   ```bash
   # Add to app.py startup
   from api.services.nats_monitoring_service import nats_monitoring_service
   from api.services.nats_heartbeat_handler import setup_heartbeat_subscription
   
   # In startup_event():
   await nats_monitoring_service.start()
   await setup_heartbeat_subscription(nats_monitoring_service, nats_manager)
   ```

2. **Add metrics routes**
   ```python
   # In api/routes/__init__.py
   from .metrics_routes import router as metrics_router
   router.include_router(metrics_router)
   ```

3. **Update clients to send heartbeats**
   - Implement heartbeat protocol in client SDKs
   - Add health monitoring to existing clients

4. **Configure tenant subscriptions**
   - Update tenant model with metric tier field
   - Map subscription plans to metric tiers

## Monitoring Dashboard Updates

The frontend dashboard should be updated to:

1. Use new `/api/v1/metrics/realtime` endpoint
2. Show client presence status from `/api/v1/metrics/presence`
3. Display tier-appropriate metrics
4. Add enterprise features conditionally

## Benefits

### For Basic Users
- Accurate message counting
- Real-time client status
- Basic usage visibility

### For Professional Users
- Performance analytics
- Throughput monitoring
- Historical trends
- Capacity planning

### For Enterprise Users
- Security monitoring
- Anomaly detection
- Predictive insights
- Custom analytics

## Scalability Considerations

1. **Message Volume**: Uses Redis for aggregation, scales to millions of messages
2. **Tenant Count**: Each tenant has isolated subscriptions
3. **Geographic Distribution**: Can run multiple monitoring instances
4. **Data Retention**: Configurable based on tier (1-30 days)

## Cost Optimization

1. **Selective Monitoring**: Only monitor active tenants
2. **Tiered Storage**: Hot data in Redis, cold in DynamoDB
3. **Sampling**: High-volume tenants can use sampling
4. **Batch Processing**: Analytics processed in batches

## Future Enhancements

1. **Machine Learning**: Predictive analytics and anomaly detection
2. **Custom Metrics**: User-defined metrics and KPIs
3. **Alerting Integration**: PagerDuty, Slack, email alerts
4. **Export APIs**: Data export for BI tools
5. **Compliance Reports**: GDPR, SOC2 compliance metrics