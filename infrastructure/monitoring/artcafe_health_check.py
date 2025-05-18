"""
CloudWatch Synthetics Canary script for monitoring ArtCafe PubSub API
"""

import json
import urllib3
import time
from aws_synthetics.selenium import synthetics_webdriver as webdriver
from aws_synthetics.common import synthetics_logger as logger
from aws_synthetics.common import synthetics_configuration

# Main canary handler
def handler(event, context):
    """Check API health endpoint"""
    # Get the API endpoint from environment or use default
    api_endpoint = synthetics_configuration.get_syn_env_var("API_ENDPOINT", "http://3.229.1.223:8000")
    
    # Create HTTP client
    http = urllib3.PoolManager()
    
    try:
        # Check health endpoint
        logger.info(f"Checking health endpoint: {api_endpoint}/health")
        response = http.request('GET', f"{api_endpoint}/health", timeout=10)
        
        # Parse response
        data = json.loads(response.data.decode('utf-8'))
        
        # Check status
        if response.status == 200 and data.get('status') == 'ok':
            logger.info("Health check passed")
            
            # Add custom metrics
            add_custom_metric("HealthCheckStatus", 1)
            add_custom_metric("APIResponseTime", response.time)
            
            # Check NATS connection (warn if not connected but don't fail)
            if not data.get('nats_connected', False):
                logger.warning("NATS is not connected")
                add_custom_metric("NATSConnected", 0)
            else:
                add_custom_metric("NATSConnected", 1)
            
            return True
        else:
            logger.error(f"Health check failed with status {response.status}")
            add_custom_metric("HealthCheckStatus", 0)
            return False
            
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        add_custom_metric("HealthCheckStatus", 0)
        raise e

def add_custom_metric(metric_name, value, unit="None"):
    """Add custom CloudWatch metric"""
    synthetics_configuration.add_user_agent({
        "metricName": metric_name,
        "metricValue": value,
        "metricUnit": unit
    })