#!/usr/bin/env python3
"""
Deployment test script for ArtCafe.ai PubSub Service

This script verifies that a deployed PubSub service is functioning correctly
by testing the various API endpoints.

Usage:
    python test_deployment.py --api-url https://your-api-endpoint:8000 [--tenant-id your-tenant-id]

Requirements:
    pip install requests pytest
"""

import argparse
import json
import requests
import sys
import time
import uuid

# Test configuration
DEFAULT_HEADERS = {
    "Content-Type": "application/json"
}

# Tenant management
def create_tenant(api_url):
    """Create a test tenant and return its ID"""
    print("Creating test tenant...")
    
    tenant_data = {
        "name": f"Test Tenant {uuid.uuid4()}",
        "admin_email": "test@example.com",
        "subscription_tier": "basic",
        "metadata": {
            "created_from": "test_script",
            "timestamp": time.time()
        }
    }
    
    response = requests.post(
        f"{api_url}/tenants", 
        headers=DEFAULT_HEADERS,
        json=tenant_data
    )
    
    if response.status_code != 200 and response.status_code != 201:
        print(f"Failed to create tenant: {response.status_code} - {response.text}")
        sys.exit(1)
        
    data = response.json()
    tenant_id = data.get("tenant_id")
    api_key = data.get("api_key")
    
    print(f"Tenant created with ID: {tenant_id}")
    print(f"API Key: {api_key}")
    
    return tenant_id, api_key

# Test the health endpoint
def test_health(api_url):
    """Test the API health endpoint"""
    print("Testing health endpoint...")
    
    try:
        response = requests.get(f"{api_url}/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
        
        nats_connected = data.get("nats_connected")
        print(f"NATS connected: {nats_connected}")
        
        return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False

# Test agent management
def test_agent_management(api_url, tenant_id, api_key):
    """Test agent management endpoints"""
    print("Testing agent management...")
    
    headers = {
        **DEFAULT_HEADERS,
        "x-tenant-id": tenant_id,
        "x-api-key": api_key
    }
    
    # Create an agent
    agent_data = {
        "name": "Test Agent",
        "type": "worker",
        "status": "online",
        "metadata": {
            "description": "Test agent for deployment verification"
        }
    }
    
    create_response = requests.post(
        f"{api_url}/agents", 
        headers=headers, 
        json=agent_data
    )
    
    if create_response.status_code != 200 and create_response.status_code != 201:
        print(f"Failed to create agent: {create_response.status_code} - {create_response.text}")
        return False
    
    agent_id = create_response.json().get("id")
    print(f"Agent created with ID: {agent_id}")
    
    # List agents
    list_response = requests.get(
        f"{api_url}/agents", 
        headers=headers
    )
    
    if list_response.status_code != 200:
        print(f"Failed to list agents: {list_response.status_code} - {list_response.text}")
        return False
    
    agents = list_response.json().get("agents", [])
    print(f"Found {len(agents)} agents")
    
    # Get agent details
    get_response = requests.get(
        f"{api_url}/agents/{agent_id}", 
        headers=headers
    )
    
    if get_response.status_code != 200:
        print(f"Failed to get agent: {get_response.status_code} - {get_response.text}")
        return False
    
    agent = get_response.json()
    print(f"Agent details retrieved: {agent.get('name')}")
    
    return True

# Test channel management
def test_channel_management(api_url, tenant_id, api_key):
    """Test channel management endpoints"""
    print("Testing channel management...")
    
    headers = {
        **DEFAULT_HEADERS,
        "x-tenant-id": tenant_id,
        "x-api-key": api_key
    }
    
    # Create a channel
    channel_data = {
        "name": "test-channel",
        "description": "Test channel for deployment verification",
        "status": "active"
    }
    
    create_response = requests.post(
        f"{api_url}/channels", 
        headers=headers, 
        json=channel_data
    )
    
    if create_response.status_code != 200 and create_response.status_code != 201:
        print(f"Failed to create channel: {create_response.status_code} - {create_response.text}")
        return False
    
    channel_id = create_response.json().get("id")
    print(f"Channel created with ID: {channel_id}")
    
    # List channels
    list_response = requests.get(
        f"{api_url}/channels", 
        headers=headers
    )
    
    if list_response.status_code != 200:
        print(f"Failed to list channels: {list_response.status_code} - {list_response.text}")
        return False
    
    channels = list_response.json().get("channels", [])
    print(f"Found {len(channels)} channels")
    
    # Get channel details
    get_response = requests.get(
        f"{api_url}/channels/{channel_id}", 
        headers=headers
    )
    
    if get_response.status_code != 200:
        print(f"Failed to get channel: {get_response.status_code} - {get_response.text}")
        return False
    
    channel = get_response.json()
    print(f"Channel details retrieved: {channel.get('name')}")
    
    return True

# Test SSH key management
def test_ssh_key_management(api_url, tenant_id, api_key):
    """Test SSH key management endpoints"""
    print("Testing SSH key management...")
    
    headers = {
        **DEFAULT_HEADERS,
        "x-tenant-id": tenant_id,
        "x-api-key": api_key
    }
    
    # Create an SSH key
    key_data = {
        "name": "Test Key",
        "public_key": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQ... test-key"
    }
    
    create_response = requests.post(
        f"{api_url}/ssh-keys", 
        headers=headers, 
        json=key_data
    )
    
    if create_response.status_code != 200 and create_response.status_code != 201:
        print(f"Failed to create SSH key: {create_response.status_code} - {create_response.text}")
        return False
    
    key_id = create_response.json().get("id")
    print(f"SSH key created with ID: {key_id}")
    
    # List SSH keys
    list_response = requests.get(
        f"{api_url}/ssh-keys", 
        headers=headers
    )
    
    if list_response.status_code != 200:
        print(f"Failed to list SSH keys: {list_response.status_code} - {list_response.text}")
        return False
    
    keys = list_response.json().get("keys", [])
    print(f"Found {len(keys)} SSH keys")
    
    return True

# Test usage metrics
def test_usage_metrics(api_url, tenant_id, api_key):
    """Test usage metrics endpoints"""
    print("Testing usage metrics...")
    
    headers = {
        **DEFAULT_HEADERS,
        "x-tenant-id": tenant_id,
        "x-api-key": api_key
    }
    
    # Get usage metrics
    response = requests.get(
        f"{api_url}/usage-metrics", 
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"Failed to get usage metrics: {response.status_code} - {response.text}")
        return False
    
    metrics = response.json()
    print(f"Usage metrics retrieved successfully")
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Test ArtCafe.ai PubSub deployment")
    parser.add_argument("--api-url", required=True, help="API endpoint URL")
    parser.add_argument("--tenant-id", help="Existing tenant ID")
    parser.add_argument("--api-key", help="API key for the tenant")
    
    args = parser.parse_args()
    api_url = args.api_url.rstrip("/")
    
    print(f"Testing ArtCafe.ai PubSub deployment at {api_url}")
    
    # Test health endpoint
    if not test_health(api_url):
        print("Health check failed. Aborting further tests.")
        sys.exit(1)
    
    # Get or create tenant
    tenant_id = args.tenant_id
    api_key = args.api_key
    
    if not tenant_id:
        tenant_id, api_key = create_tenant(api_url)
    
    if not tenant_id:
        print("No tenant ID provided or created. Aborting further tests.")
        sys.exit(1)
    
    # Run functional tests
    tests = [
        ("Agent management", test_agent_management),
        ("Channel management", test_channel_management),
        ("SSH key management", test_ssh_key_management),
        ("Usage metrics", test_usage_metrics)
    ]
    
    results = []
    
    for name, test_func in tests:
        print(f"\n--- Testing {name} ---")
        try:
            result = test_func(api_url, tenant_id, api_key)
            results.append((name, result))
        except Exception as e:
            print(f"Error during test: {e}")
            results.append((name, False))
    
    # Print summary
    print("\n\n=== Test Results ===")
    all_passed = True
    
    for name, result in results:
        status = "PASSED" if result else "FAILED"
        if not result:
            all_passed = False
        print(f"{name}: {status}")
    
    if all_passed:
        print("\nAll tests passed! The deployment appears to be working correctly.")
        sys.exit(0)
    else:
        print("\nSome tests failed. Please check the deployment and logs.")
        sys.exit(1)

if __name__ == "__main__":
    main()