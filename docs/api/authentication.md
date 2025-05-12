# Authentication Flow Guide

This document explains the authentication flow for the ArtCafe.ai PubSub API.

## Overview

The ArtCafe.ai PubSub API supports two authentication methods:

1. **JWT Token Authentication** - Used for general API access
2. **SSH Key Authentication** - Used for secure agent authentication

All API requests require a tenant ID, which can be provided in the `x-tenant-id` header or included in the JWT token payload.

## JWT Token Authentication

JWT (JSON Web Token) authentication is the standard method for authenticating with the API. It provides a secure way to transmit user claims between the client and the API.

### JWT Token Structure

A JWT token consists of three parts:

1. **Header** - Contains the token type and signing algorithm
2. **Payload** - Contains the claims (data)
3. **Signature** - Used to verify the token

The payload of a JWT token contains the following claims:

```json
{
  "sub": "user_id or key_id",
  "tenant_id": "tenant-123456",
  "key_type": "access|agent|deployment",
  "agent_id": "agent-123456 (optional)",
  "iat": 1625097600,
  "exp": 1625101200
}
```

### Using JWT Tokens

To authenticate with the API using a JWT token, include the token in the `Authorization` header of your HTTP request:

```
Authorization: Bearer <your_token>
```

### Token Expiration and Renewal

JWT tokens expire after 1 hour. When a token expires, the client must obtain a new token through the authentication flow.

## SSH Key Authentication

SSH key authentication is used for secure agent authentication. It provides a high level of security, as it relies on asymmetric cryptography.

### Prerequisites

Before starting the SSH key authentication flow, you need:

1. An SSH key pair (public and private keys)
2. The public key registered with the ArtCafe.ai PubSub API
3. A valid tenant ID

### SSH Key Authentication Flow

The SSH key authentication flow consists of the following steps:

1. **Challenge Generation**
   - The client requests a challenge from the API
   - The API generates a random challenge and returns it to the client

2. **Challenge Signing**
   - The client signs the challenge with their private SSH key
   - The signature is encoded in base64

3. **Challenge Verification**
   - The client sends the signature back to the API
   - The API verifies the signature using the public key
   - If the signature is valid, the API issues a JWT token

### Example: SSH Key Authentication Flow

#### Step 1: Request a Challenge

```http
POST /api/v1/auth/challenge
x-tenant-id: tenant-123456
Content-Type: application/json

{
  "agent_id": "agent-123456"
}
```

Response:

```json
{
  "challenge": "8f7d9a6b5c4d3e2f1a0b1c2d3e4f5a6b",
  "expires_at": "2023-07-01T12:05:00Z",
  "tenant_id": "tenant-123456",
  "agent_id": "agent-123456"
}
```

#### Step 2: Sign the Challenge

On the client side, sign the challenge with your private SSH key:

```bash
# 1. Calculate the SHA256 hash of the challenge
echo -n "8f7d9a6b5c4d3e2f1a0b1c2d3e4f5a6b" | sha256sum

# 2. Sign the hash with your private key
echo -n "8f7d9a6b5c4d3e2f1a0b1c2d3e4f5a6b" | 
  openssl dgst -sha256 -sign ~/.ssh/id_rsa | 
  base64
```

This will produce a base64-encoded signature.

#### Step 3: Verify the Challenge

```http
POST /api/v1/auth/verify
Content-Type: application/json

{
  "tenant_id": "tenant-123456",
  "key_id": "key-123456",
  "challenge": "8f7d9a6b5c4d3e2f1a0b1c2d3e4f5a6b",
  "response": "base64_encoded_signature",
  "agent_id": "agent-123456"
}
```

Response:

```json
{
  "valid": true,
  "message": "Authentication successful",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

#### Step 4: Use the JWT Token

Now you can use the JWT token for subsequent API requests:

```http
GET /api/v1/agents
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Implementation Examples

### Python Example

```python
import requests
import base64
import subprocess
import json
from datetime import datetime, timedelta

class ArtCafeClient:
    def __init__(self, api_url, tenant_id, private_key_path, key_id, agent_id=None):
        self.api_url = api_url
        self.tenant_id = tenant_id
        self.private_key_path = private_key_path
        self.key_id = key_id
        self.agent_id = agent_id
        self.token = None
        self.token_expiry = None
    
    def _sign_challenge(self, challenge):
        """Sign a challenge with the private key"""
        cmd = [
            "openssl", "dgst", "-sha256", "-sign", self.private_key_path
        ]
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(challenge.encode('utf-8'))
        if process.returncode != 0:
            raise Exception(f"Failed to sign challenge: {stderr.decode('utf-8')}")
        return base64.b64encode(stdout).decode('utf-8')
    
    def authenticate(self):
        """Authenticate with the API and get a token"""
        # Step 1: Request a challenge
        headers = {'x-tenant-id': self.tenant_id, 'Content-Type': 'application/json'}
        data = {}
        if self.agent_id:
            data['agent_id'] = self.agent_id
        
        response = requests.post(
            f"{self.api_url}/auth/challenge",
            headers=headers,
            json=data
        )
        response.raise_for_status()
        challenge_data = response.json()
        
        challenge = challenge_data['challenge']
        
        # Step 2: Sign the challenge
        signature = self._sign_challenge(challenge)
        
        # Step 3: Verify the challenge
        verify_data = {
            'tenant_id': self.tenant_id,
            'key_id': self.key_id,
            'challenge': challenge,
            'response': signature
        }
        if self.agent_id:
            verify_data['agent_id'] = self.agent_id
        
        response = requests.post(
            f"{self.api_url}/auth/verify",
            headers={'Content-Type': 'application/json'},
            json=verify_data
        )
        response.raise_for_status()
        result = response.json()
        
        if not result['valid']:
            raise Exception(f"Authentication failed: {result['message']}")
        
        self.token = result['token']
        self.token_expiry = datetime.now() + timedelta(hours=1)
        
        return self.token
    
    def get_token(self):
        """Get a valid token, authenticating if necessary"""
        if not self.token or not self.token_expiry or datetime.now() >= self.token_expiry:
            self.authenticate()
        return self.token
    
    def request(self, method, path, **kwargs):
        """Make an authenticated request to the API"""
        token = self.get_token()
        headers = kwargs.pop('headers', {})
        headers.update({
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        })
        
        response = requests.request(
            method,
            f"{self.api_url}{path}",
            headers=headers,
            **kwargs
        )
        response.raise_for_status()
        return response.json()
    
    def list_agents(self):
        """List all agents"""
        return self.request('GET', '/agents')
    
    def get_agent(self, agent_id):
        """Get agent details"""
        return self.request('GET', f"/agents/{agent_id}")
    
    def list_ssh_keys(self):
        """List all SSH keys"""
        return self.request('GET', '/ssh-keys')
    
    def get_ssh_key(self, key_id):
        """Get SSH key details"""
        return self.request('GET', f"/ssh-keys/{key_id}")

# Usage example
client = ArtCafeClient(
    api_url="https://api.artcafe.ai/v1",
    tenant_id="tenant-123456",
    private_key_path="~/.ssh/id_rsa",
    key_id="key-123456",
    agent_id="agent-123456"
)

# List agents
agents = client.list_agents()
print(json.dumps(agents, indent=2))
```

### JavaScript (Node.js) Example

```javascript
const axios = require('axios');
const crypto = require('crypto');
const fs = require('fs');
const util = require('util');

class ArtCafeClient {
  constructor(apiUrl, tenantId, privateKeyPath, keyId, agentId = null) {
    this.apiUrl = apiUrl;
    this.tenantId = tenantId;
    this.privateKeyPath = privateKeyPath;
    this.keyId = keyId;
    this.agentId = agentId;
    this.token = null;
    this.tokenExpiry = null;
  }

  async _signChallenge(challenge) {
    // Read the private key
    const privateKey = fs.readFileSync(this.privateKeyPath);
    
    // Create a sign object
    const sign = crypto.createSign('SHA256');
    
    // Update with the challenge
    sign.update(challenge);
    
    // Sign the challenge with the private key
    const signature = sign.sign(privateKey);
    
    // Return the base64-encoded signature
    return signature.toString('base64');
  }

  async authenticate() {
    // Step 1: Request a challenge
    const headers = { 'x-tenant-id': this.tenantId, 'Content-Type': 'application/json' };
    const data = {};
    if (this.agentId) {
      data.agent_id = this.agentId;
    }
    
    const challengeResponse = await axios.post(
      `${this.apiUrl}/auth/challenge`,
      data,
      { headers }
    );
    
    const challengeData = challengeResponse.data;
    const challenge = challengeData.challenge;
    
    // Step 2: Sign the challenge
    const signature = await this._signChallenge(challenge);
    
    // Step 3: Verify the challenge
    const verifyData = {
      tenant_id: this.tenantId,
      key_id: this.keyId,
      challenge: challenge,
      response: signature
    };
    
    if (this.agentId) {
      verifyData.agent_id = this.agentId;
    }
    
    const verifyResponse = await axios.post(
      `${this.apiUrl}/auth/verify`,
      verifyData,
      { headers: { 'Content-Type': 'application/json' } }
    );
    
    const result = verifyResponse.data;
    
    if (!result.valid) {
      throw new Error(`Authentication failed: ${result.message}`);
    }
    
    this.token = result.token;
    this.tokenExpiry = new Date(Date.now() + 3600 * 1000); // 1 hour from now
    
    return this.token;
  }

  async getToken() {
    if (!this.token || !this.tokenExpiry || new Date() >= this.tokenExpiry) {
      await this.authenticate();
    }
    return this.token;
  }

  async request(method, path, options = {}) {
    const token = await this.getToken();
    const headers = options.headers || {};
    headers['Authorization'] = `Bearer ${token}`;
    headers['Content-Type'] = 'application/json';
    
    const response = await axios({
      method,
      url: `${this.apiUrl}${path}`,
      headers,
      ...options
    });
    
    return response.data;
  }

  async listAgents() {
    return this.request('GET', '/agents');
  }

  async getAgent(agentId) {
    return this.request('GET', `/agents/${agentId}`);
  }

  async listSSHKeys() {
    return this.request('GET', '/ssh-keys');
  }

  async getSSHKey(keyId) {
    return this.request('GET', `/ssh-keys/${keyId}`);
  }
}

// Usage example
async function main() {
  const client = new ArtCafeClient(
    'https://api.artcafe.ai/v1',
    'tenant-123456',
    '~/.ssh/id_rsa',
    'key-123456',
    'agent-123456'
  );

  // List agents
  const agents = await client.listAgents();
  console.log(JSON.stringify(agents, null, 2));
}

main().catch(console.error);
```

## Security Considerations

1. **Store Private Keys Securely**
   - Never expose private keys in your code or public repositories
   - Use environment variables or secure vaults to store sensitive information

2. **Use HTTPS**
   - Always use HTTPS when communicating with the API
   - Verify the server's SSL certificate

3. **Token Security**
   - Treat JWT tokens as sensitive information
   - Store tokens securely and never expose them in client-side code

4. **Challenge Expiration**
   - Challenges expire after 5 minutes
   - Ensure your system's clock is synchronized with NTP to avoid time-related issues

5. **Key Rotation**
   - Regularly rotate your SSH keys to enhance security
   - Revoke unused or compromised keys promptly