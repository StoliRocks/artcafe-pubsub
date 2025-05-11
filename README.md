# ArtCafe.ai PubSub Service

A NATS-based pub/sub service for ArtCafe.ai that implements the API endpoints used by the frontend. This service facilitates agent communication, management, and messaging.

## Features

- FastAPI service with endpoints matching the frontend API calls
- NATS connection and client implementation
- Authentication with JWT tokens
- Multi-tenant support
- DynamoDB persistence
- Proper error handling
- Test clients for validation

## Project Structure

```
artcafe_pubsub/
├── api/                # API endpoints and routes
│   ├── app.py          # FastAPI application
│   ├── lambda_handler.py # AWS Lambda handler
│   └── router.py       # API routes
├── auth/               # Authentication
│   ├── jwt_auth.py     # JWT authentication
│   └── ssh_auth.py     # SSH key management
├── core/               # Core functionality
│   ├── messaging_service.py # Messaging service
│   └── nats_client.py  # NATS client
├── infrastructure/     # Deployment and infrastructure
│   ├── cloudformation.yml # AWS CloudFormation template
│   ├── deploy.sh       # Deployment script
│   └── dynamodb_service.py # DynamoDB service
├── models/             # Data models
│   ├── agent.py        # Agent models
│   ├── channel.py      # Channel models
│   ├── ssh_key.py      # SSH key models
│   ├── tenant.py       # Tenant models
│   └── usage.py        # Usage metrics models
├── tests/              # Tests
│   └── test_client.py  # Test client
└── requirements.txt    # Dependencies
```

## API Endpoints

### Agents

- `GET /api/v1/agents` - List all agents
- `POST /api/v1/agents` - Register a new agent
- `GET /api/v1/agents/{agent_id}` - Get agent details
- `PUT /api/v1/agents/{agent_id}/status` - Update agent status

### SSH Keys

- `GET /api/v1/ssh-keys` - List all SSH keys
- `POST /api/v1/ssh-keys` - Add a new SSH key
- `DELETE /api/v1/ssh-keys/{key_id}` - Delete SSH key

### Channels

- `GET /api/v1/channels` - List all channels
- `POST /api/v1/channels` - Create a new channel
- `GET /api/v1/channels/{channel_id}` - Get channel details

### Usage and Billing

- `GET /api/v1/usage-metrics` - Get usage metrics
- `GET /api/v1/billing` - Get billing information

## Setup and Installation

### Prerequisites

- Python 3.9+
- NATS Server
- AWS Account (for deployment)

### Local Development

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start a local NATS server:

```bash
# Using Docker
docker run -p 4222:4222 nats
```

3. Run the FastAPI application:

```bash
cd artcafe_pubsub
python -m api.app
```

4. Access the API documentation at http://localhost:8000/docs

### Testing

Run the test client:

```bash
python -m tests.test_client
```

### Deployment to AWS

1. Make sure you have AWS CLI installed and configured with appropriate credentials.

2. Create or import an EC2 key pair in the AWS Console. This will be used for SSH access to the EC2 instances.

3. Run the deployment script with the key pair name:

```bash
cd infrastructure
chmod +x deploy.sh
./deploy.sh --env dev --key-name YOUR_KEY_PAIR_NAME
```

This command:
- Packages the application code into a zip file
- Creates the CloudFormation stack with necessary AWS resources
- Uploads the application code to the EC2 instance
- Configures and starts the service

Optional parameters:
- `--region REGION_NAME` - AWS region to deploy to (default: us-east-1)
- `--stack-name STACK_NAME` - CloudFormation stack name (default: artcafe-pubsub)
- `--code-package PACKAGE_NAME` - Name of the zip file containing the application code (default: lambda.zip)
- `--nats-instance-type INSTANCE_TYPE` - EC2 instance type for NATS server (default: t3.small)
- `--api-instance-type INSTANCE_TYPE` - EC2 instance type for API server (default: t3.small)
- `--skip-package` - Skip packaging and uploading application code (useful for infrastructure-only updates)

4. After deployment completes, the script will output the URL of the deployed service.

## Authentication

The service uses JWT tokens for authentication. Pass the token in the `Authorization` header as a Bearer token:

```
Authorization: Bearer <your_token>
```

The tenant ID can be specified in the `x-tenant-id` header.

## Multi-tenancy

All resources are scoped to a tenant ID, which must be provided in the `x-tenant-id` header or in the JWT token payload.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -am 'Add new feature'`
4. Push to the branch: `git push origin feature/my-feature`
5. Submit a pull request

## License

This project is licensed under the MIT License.