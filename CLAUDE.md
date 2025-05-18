# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ArtCafe.ai PubSub Service is a NATS-based pub/sub service that implements API endpoints used by the frontend. This service facilitates agent communication, management, and messaging. The project uses FastAPI for REST endpoints, NATS for messaging, DynamoDB for persistence, and supports multi-tenancy.

## Commands

### Environment Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Start local NATS server (using Docker)
docker run -p 4222:4222 nats
```

### Development

```bash
# Run the FastAPI application
python -m api.app

# Access API documentation
# Visit http://localhost:8000/docs
```

### Testing

```bash
# Run the test client with default settings
python -m tests.test_client

# Run test client with custom settings
python -m tests.test_client --api-endpoint http://localhost:8000/api/v1 --token <jwt-token> --tenant-id <tenant-id>
```

### Deployment

```bash
# Deploy to AWS (requires AWS CLI configured with appropriate credentials)
cd infrastructure
chmod +x deploy.sh
./deploy.sh --env dev --key-name YOUR_KEY_PAIR_NAME

# Optional deployment parameters:
# --region REGION_NAME           AWS region (default: us-east-1)
# --stack-name STACK_NAME        CloudFormation stack name (default: artcafe-pubsub)
# --code-package PACKAGE_NAME    Name of zip file (default: lambda.zip)
# --nats-instance-type TYPE      EC2 instance type for NATS (default: t3.small)
# --api-instance-type TYPE       EC2 instance type for API (default: t3.small)
# --skip-package                 Skip packaging (for infrastructure-only updates)
```

## Architecture

### Core Components

1. **API Layer** (api/ directory)
   - FastAPI application with RESTful endpoints
   - Authentication via JWT tokens
   - Multi-tenant support via headers
   - Routes for agents, channels, SSH keys, tenants, and usage

2. **Messaging Core** (core/ and nats/ directories)
   - NATS client implementation
   - Pub/sub and request-reply patterns
   - Connection management and reconnection handling
   - TLS support for secure connections

3. **Persistence Layer** (api/db/ directory)
   - DynamoDB tables for storing entity data
   - Multi-tenant data isolation
   - Automatic table creation and maintenance

4. **Infrastructure** (infrastructure/ directory)
   - AWS CloudFormation for deployments
   - EC2 instances for NATS and API servers
   - DynamoDB tables for persistence
   - Deployment automation script

### Data Models

The system uses several data models for different entities:

- `Agent`: Represents an agent with capabilities and status
- `Channel`: Communication channels between agents and users
- `SSHKey`: SSH key management for secure access
- `Tenant`: Multi-tenant isolation for organizations
- `Usage`: Usage metrics and billing information

### Authentication

- JWT authentication is used for API endpoints
- Multi-tenant support with tenant IDs in headers
- SSH key-based authentication for agent access

### API Endpoints

- `/api/v1/agents`: Agent registration and management
- `/api/v1/ssh-keys`: SSH key management
- `/api/v1/channels`: Channel creation and management
- `/api/v1/tenants`: Tenant provisioning and management
- `/api/v1/usage-metrics`: Usage tracking and reporting