#!/bin/bash

# ArtCafe PubSub API Monitor Script
# This script monitors the API and sends logs to CloudWatch

# Configuration
API_ENDPOINT="http://localhost:8000"
HEALTH_ENDPOINT="$API_ENDPOINT/health"
LOG_GROUP="/aws/ec2/artcafe-pubsub"
LOG_STREAM="monitor"
CHECK_INTERVAL=60  # seconds
REGION="us-east-1"

# CloudWatch Logs configuration
configure_cloudwatch_logs() {
    # Install CloudWatch agent if not present
    if ! command -v aws-cwlogs &> /dev/null; then
        wget https://aws-amazoncloudwatch-agent.s3.amazonaws.com/latest/cloudwatch-agent.deb
        sudo dpkg -i -E ./cloudwatch-agent.deb
        rm cloudwatch-agent.deb
    fi
}

# Send metric to CloudWatch
send_metric() {
    local metric_name=$1
    local value=$2
    local unit=${3:-None}
    
    aws cloudwatch put-metric-data \
        --metric-name "$metric_name" \
        --namespace "ArtCafePubSub" \
        --value "$value" \
        --unit "$unit" \
        --region "$REGION" || true
}

# Log to CloudWatch
log_to_cloudwatch() {
    local level=$1
    local message=$2
    local timestamp=$(date -u +%s000)
    
    aws logs put-log-events \
        --log-group-name "$LOG_GROUP" \
        --log-stream-name "$LOG_STREAM" \
        --log-events "timestamp=$timestamp,message=[$level] $message" \
        --region "$REGION" || true
}

# Create log stream if it doesn't exist
create_log_stream() {
    aws logs create-log-stream \
        --log-group-name "$LOG_GROUP" \
        --log-stream-name "$LOG_STREAM" \
        --region "$REGION" 2>/dev/null || true
}

# Monitor function
monitor() {
    while true; do
        # Check health endpoint
        start_time=$(date +%s.%N)
        response=$(curl -s -w "\n%{http_code}" "$HEALTH_ENDPOINT" 2>/dev/null)
        end_time=$(date +%s.%N)
        
        # Parse response
        http_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | head -n-1)
        response_time=$(echo "$end_time - $start_time" | bc)
        
        # Check if service is healthy
        if [ "$http_code" = "200" ]; then
            if echo "$body" | grep -q '"status":"ok"'; then
                log_to_cloudwatch "INFO" "Health check passed"
                send_metric "HealthCheckSuccess" 1
                send_metric "ResponseTime" "$response_time" "Seconds"
                
                # Check NATS connection
                if echo "$body" | grep -q '"nats_connected":true'; then
                    send_metric "NATSConnected" 1
                else
                    log_to_cloudwatch "WARN" "NATS not connected"
                    send_metric "NATSConnected" 0
                fi
            else
                log_to_cloudwatch "ERROR" "Health check failed: unhealthy status"
                send_metric "HealthCheckSuccess" 0
            fi
        else
            log_to_cloudwatch "ERROR" "Health check failed: HTTP $http_code"
            send_metric "HealthCheckSuccess" 0
            
            # Check if service is running
            if ! systemctl is-active --quiet artcafe-pubsub; then
                log_to_cloudwatch "ERROR" "Service is not running, attempting restart"
                sudo systemctl restart artcafe-pubsub
                send_metric "ServiceRestart" 1
            fi
        fi
        
        # Check memory usage
        memory_usage=$(ps aux | grep -E "python.*api.app" | grep -v grep | awk '{print $4}' | head -1)
        if [ ! -z "$memory_usage" ]; then
            send_metric "MemoryUsagePercent" "$memory_usage" "Percent"
        fi
        
        # Check CPU usage
        cpu_usage=$(ps aux | grep -E "python.*api.app" | grep -v grep | awk '{print $3}' | head -1)
        if [ ! -z "$cpu_usage" ]; then
            send_metric "CPUUsagePercent" "$cpu_usage" "Percent"
        fi
        
        sleep "$CHECK_INTERVAL"
    done
}

# Main
main() {
    echo "Starting ArtCafe PubSub Monitor..."
    configure_cloudwatch_logs
    create_log_stream
    log_to_cloudwatch "INFO" "Monitor started"
    monitor
}

main