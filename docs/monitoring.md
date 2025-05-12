# Monitoring and Metrics Guide

This document provides an overview of the monitoring and metrics capabilities in the ArtCafe.ai PubSub service.

## Overview

The PubSub service includes a comprehensive metrics collection system that tracks:

- Agent activity and counts
- Channel activity and counts
- Message throughput (in/out)
- API call volume
- Resource usage (CPU, memory, disk)
- User actions (e.g., key creation, revocation)

These metrics are collected, aggregated, and stored in DynamoDB for persistence and analysis.

## Metrics Collection

### How Metrics Are Collected

1. **Automatic Collection**
   - **Active Connections**: WebSocket connections are tracked in real-time
   - **Message Throughput**: Messages passing through NATS subjects are counted
   - **System Resources**: CPU, memory, and disk usage are monitored periodically

2. **Manual Instrumentation**
   - **API Calls**: Each API endpoint tracks usage when called
   - **Actions**: User actions like key creation are tracked

3. **Collection Frequency**
   - Basic metrics are collected every 1 minute
   - Aggregated metrics are written to DynamoDB every 5 minutes
   - Resource metrics are collected every 5 minutes

### Metrics Storage

Metrics are stored in two DynamoDB tables:

1. **UsageMetrics Table**
   - Primary Key: `tenant_id` (Partition Key), `date` (Sort Key)
   - Stores daily aggregated metrics for each tenant
   - Retention: 90 days by default

2. **Challenges Table**
   - Primary Key: `tenant_id` (Partition Key), `challenge` (Sort Key)
   - Stores authentication challenges with TTL expiration
   - Automatic cleanup via DynamoDB TTL

## Available Metrics

### Tenant Metrics

| Metric | Description | Units |
|--------|-------------|-------|
| `agents_count` | Total number of agents | count |
| `active_agents_count` | Number of currently active agents | count |
| `channels_count` | Total number of channels | count |
| `active_channels_count` | Number of currently active channels | count |
| `messages_in_count` | Number of inbound messages | count |
| `messages_out_count` | Number of outbound messages | count |
| `api_calls_count` | Number of API calls | count |
| `storage_used_bytes` | Storage usage | bytes |

### System Metrics

| Metric | Description | Units |
|--------|-------------|-------|
| `cpu_percent` | CPU utilization | percentage |
| `memory_percent` | Memory utilization | percentage |
| `disk_percent` | Disk utilization | percentage |
| `nats_connections` | NATS client connections | count |
| `websocket_connections` | WebSocket connections | count |

## Accessing Metrics

### API Access

Metrics can be accessed through the API:

```
GET /api/v1/usage-metrics
```

Parameters:
- `start_date`: Start date in ISO format (YYYY-MM-DD)
- `end_date`: End date in ISO format (YYYY-MM-DD)

Example response:
```json
{
  "metrics": [
    {
      "tenant_id": "tenant-123",
      "date": "2023-09-28",
      "agents_count": 10,
      "active_agents_count": 5,
      "channels_count": 8,
      "active_channels_count": 3,
      "messages_count": 1240,
      "api_calls_count": 356,
      "storage_used_bytes": 123456789,
      "created_at": "2023-09-28T14:32:10.123456Z"
    },
    ...
  ],
  "totals": {
    "tenant_id": "tenant-123",
    "start_date": "2023-09-28",
    "end_date": "2023-09-29",
    "agents_total": 10,
    "active_agents_total": 6,
    "channels_total": 8,
    "active_channels_total": 4,
    "messages_in_total": 1500,
    "messages_out_total": 1096,
    "api_calls_total": 768,
    "timestamp": "2023-09-30T00:00:00.000000Z"
  },
  "limits": {
    "max_agents": 10,
    "max_channels": 20,
    "max_messages_per_day": 50000,
    "max_api_calls_per_day": 10000,
    "max_storage_bytes": 1073741824,
    "concurrent_connections": 50
  },
  "success": true
}
```

### CloudWatch Dashboard

For AWS deployments, metrics are exported to CloudWatch and can be viewed in a prebuilt dashboard. The dashboard provides:

- Real-time agent/channel status
- Message throughput
- API usage
- Subscription utilization percentage
- System health metrics

## Alerting and Notifications

The service includes configurable alerts for:

1. **Resource Usage**
   - CPU exceeds 80% for 5 minutes
   - Memory exceeds 85% for 5 minutes
   - Disk exceeds 90%
   - 95% of subscription limits reached

2. **Security**
   - Multiple failed authentication attempts
   - Unusual access patterns
   - Key revocation events

3. **Operational**
   - NATS connection issues
   - DynamoDB throttling
   - API latency exceeds thresholds

Alerts are sent via:
- CloudWatch Alarms
- SNS notifications
- Email (configurable)

## Usage Anomaly Detection

The metrics service includes basic anomaly detection for:

- Sudden spikes in message volume
- Unusual API call patterns
- Abnormal agent connection behavior
- Potential security issues

## Tenant Dashboard

Tenants can view their own metrics through the admin portal:

- Usage breakdown by service area
- Current active agents and channels
- Message volume trends
- Subscription utilization
- Cost projections

## Configuring Metrics

Settings can be adjusted in the `config/settings.py` file:

```python
# Metrics settings
METRICS_COLLECTION_INTERVAL = 60  # 1 minute
METRICS_FLUSH_INTERVAL = 300  # 5 minutes
METRICS_RETENTION_DAYS = 90
ENABLE_USAGE_ANOMALY_DETECTION = True
```

## Custom Metrics

To add custom metrics:

1. **Service-level Metrics**

   ```python
   from infrastructure.metrics_service import metrics_service
   
   # Increment a counter
   metrics_service.increment_metric(
       tenant_id="tenant-123",
       category="custom",
       metric="my_counter",
       value=1
   )
   
   # Set a value
   metrics_service.set_metric(
       tenant_id="tenant-123",
       category="custom",
       metric="my_gauge",
       value=42
   )
   ```

2. **Periodic Collection**

   Create a collection function and add it to the metrics service:

   ```python
   async def collect_my_metrics():
       # Collect custom metrics
       value = await get_some_value()
       metrics_service.set_metric("tenant-123", "custom", "my_metric", value)
   
   # Add to collection loop
   metrics_service.add_collector(collect_my_metrics)
   ```

## Best Practices

1. **Limit Metrics Cardinality**
   - Avoid creating metrics with unbounded dimensions
   - Use bucketing for high-cardinality values

2. **Optimize Collection Frequency**
   - Balance between accuracy and resource usage
   - Increase intervals for less critical metrics

3. **Consider Aggregation**
   - Pre-aggregate metrics where possible
   - Focus on meaningful statistics rather than raw data

4. **Use Tags for Filtering**
   - Add metadata to metrics for better filtering
   - Standardize tag names across services