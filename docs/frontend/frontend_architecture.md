# ArtCafe.ai Frontend Architecture

This document outlines the architecture and implementation guidelines for building the ArtCafe.ai multi-tenant React frontend application.

## System Overview

The ArtCafe.ai frontend is a React-based single-page application (SPA) that interacts with the PubSub backend service. It provides interfaces for:

1. Tenant management and onboarding
2. Agent management (registration, monitoring, control)
3. SSH key management
4. Real-time communication via WebSockets
5. Usage tracking and billing

## Architecture Principles

The frontend architecture follows these key principles:

1. **Multi-tenant by design**: Strict data isolation between tenants
2. **Security-first approach**: JWT authentication, HTTP-only cookies, and RBAC
3. **Real-time capabilities**: WebSocket integration for live updates
4. **Responsive design**: Mobile-friendly using responsive frameworks
5. **Performance optimized**: Code splitting, lazy loading, and caching
6. **Scalable architecture**: Component-based design with separation of concerns

## Tech Stack

- **Framework**: React 18+ with TypeScript
- **State Management**: Redux Toolkit or React Query
- **UI Framework**: Material UI or Tailwind CSS
- **Routing**: React Router v6+
- **API Communication**: Axios or React Query
- **WebSocket**: Socket.IO client or native WebSocket API
- **Authentication**: JWT tokens with refresh capabilities
- **Form Handling**: React Hook Form or Formik
- **Testing**: Jest and React Testing Library
- **Deployment**: AWS Amplify

## Application Structure

```
src/
├── api/               # API service integration
│   ├── agent.ts       # Agent-related API calls
│   ├── auth.ts        # Authentication API calls
│   ├── ssh-key.ts     # SSH key management API calls
│   ├── tenant.ts      # Tenant management API calls
│   └── websocket.ts   # WebSocket connection handler
├── components/        # Shared UI components
│   ├── common/        # Common UI elements
│   ├── agents/        # Agent-related components
│   ├── keys/          # SSH key management components
│   ├── layout/        # Layout components
│   └── tenant/        # Tenant management components
├── context/           # React context providers
│   ├── AuthContext.tsx    # Authentication context
│   ├── TenantContext.tsx  # Tenant context
│   └── WebSocketContext.tsx # WebSocket context
├── hooks/             # Custom React hooks
│   ├── useAuth.ts     # Authentication hook
│   ├── useTenant.ts   # Tenant management hook
│   └── useWebSocket.ts # WebSocket communication hook
├── pages/             # Application pages
│   ├── auth/          # Authentication pages
│   ├── dashboard/     # Dashboard pages
│   ├── agents/        # Agent management pages
│   ├── keys/          # SSH key management pages
│   └── settings/      # Settings pages
├── store/             # State management (Redux)
│   ├── slices/        # Redux slices
│   └── store.ts       # Redux store configuration
├── types/             # TypeScript type definitions
├── utils/             # Utility functions
├── App.tsx            # Main application component
└── index.tsx          # Application entry point
```

## Authentication Flow

### JWT-Based Authentication

1. User logs in with email/password or SSO
2. Backend returns JWT access token and refresh token
3. Frontend stores tokens (access token in memory, refresh token in HTTP-only cookie)
4. Include access token in all API requests
5. Implement token refresh logic for expired tokens

### Multi-Tenant Support

1. Tenant ID is included in JWT payload
2. All API requests include tenant ID in header (`x-tenant-id`)
3. Implement tenant switching in UI if users have access to multiple tenants

## WebSocket Integration

### Connection Setup

```typescript
// In WebSocketContext.tsx
import { createContext, useContext, useEffect, useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTenant } from '../hooks/useTenant';

const WebSocketContext = createContext(null);

export const WebSocketProvider = ({ children }) => {
  const [socket, setSocket] = useState(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState([]);
  const { accessToken } = useAuth();
  const { currentTenant } = useTenant();
  
  useEffect(() => {
    if (!accessToken || !currentTenant) return;
    
    // Create WebSocket connection
    const ws = new WebSocket('wss://api.artcafe.ai/api/v1/ws');
    
    // Connection opened
    ws.addEventListener('open', (event) => {
      console.log('Connected to WebSocket');
      setConnected(true);
      
      // Send authentication message
      ws.send(JSON.stringify({
        type: 'auth',
        data: {
          token: accessToken,
          tenant_id: currentTenant.id
        }
      }));
    });
    
    // Listen for messages
    ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      setMessages(prev => [...prev, message]);
      
      // Handle different message types
      switch(message.type) {
        case 'agent_status':
          // Update agent status
          break;
        case 'notification':
          // Show notification
          break;
        default:
          console.log('Received message:', message);
      }
    });
    
    // Connection closed
    ws.addEventListener('close', (event) => {
      console.log('Disconnected from WebSocket');
      setConnected(false);
    });
    
    // Handle errors
    ws.addEventListener('error', (error) => {
      console.error('WebSocket error:', error);
    });
    
    setSocket(ws);
    
    // Cleanup on unmount
    return () => {
      ws.close();
    };
  }, [accessToken, currentTenant]);
  
  // Function to send messages
  const sendMessage = (type, data) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    
    socket.send(JSON.stringify({
      type,
      data,
      timestamp: new Date().toISOString()
    }));
  };
  
  return (
    <WebSocketContext.Provider value={{ connected, messages, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => useContext(WebSocketContext);
```

### Example Usage

```typescript
// In AgentList.tsx
import { useEffect, useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchAgents } from '../api/agent';

const AgentList = () => {
  const [agents, setAgents] = useState([]);
  const { connected, messages, sendMessage } = useWebSocket();
  
  useEffect(() => {
    // Fetch initial agent list
    const loadAgents = async () => {
      const data = await fetchAgents();
      setAgents(data);
    };
    
    loadAgents();
  }, []);
  
  useEffect(() => {
    // Update agents when receiving WebSocket messages
    const agentStatusMessages = messages.filter(m => m.type === 'agent_status');
    
    if (agentStatusMessages.length > 0) {
      // Update agent statuses
      setAgents(prev => {
        return prev.map(agent => {
          const statusMessage = agentStatusMessages.find(m => m.data.agent_id === agent.id);
          if (statusMessage) {
            return { ...agent, status: statusMessage.data.status };
          }
          return agent;
        });
      });
    }
  }, [messages]);
  
  // Request agent status updates
  const requestStatusUpdates = () => {
    sendMessage('status_request', { agent_ids: agents.map(a => a.id) });
  };
  
  return (
    <div>
      <h1>Agents</h1>
      <button onClick={requestStatusUpdates} disabled={!connected}>
        Refresh Status
      </button>
      
      <div className="agent-grid">
        {agents.map(agent => (
          <AgentCard 
            key={agent.id} 
            agent={agent} 
            onSendCommand={command => {
              sendMessage('command', {
                agent_id: agent.id,
                command,
                timestamp: new Date().toISOString()
              });
            }} 
          />
        ))}
      </div>
    </div>
  );
};
```

## SSH Key Management

### Generating Keys

Provide a UI for generating SSH keys or uploading existing public keys:

```typescript
// In KeyGeneration.tsx
import { useState } from 'react';
import { createSSHKey } from '../api/ssh-key';

const KeyGeneration = () => {
  const [name, setName] = useState('');
  const [publicKey, setPublicKey] = useState('');
  const [keyType, setKeyType] = useState('access');
  const [agentId, setAgentId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  const handleGenerateKey = async () => {
    // This would typically be done client-side using a library
    // or call a separate microservice that generates keys
    
    // For this example, we'll just provide instructions
    alert('For security reasons, generate the SSH key pair locally using ssh-keygen and enter the public key here.');
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const response = await createSSHKey({
        name,
        public_key: publicKey,
        key_type: keyType,
        agent_id: keyType === 'agent' ? agentId : undefined
      });
      
      // Show success message
      alert(`Key ${response.key.name} added successfully`);
      
      // Reset form
      setName('');
      setPublicKey('');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div>
      <h2>Add SSH Key</h2>
      
      <button onClick={handleGenerateKey}>
        Generate Key Instructions
      </button>
      
      <form onSubmit={handleSubmit}>
        <div>
          <label htmlFor="name">Key Name</label>
          <input
            id="name"
            value={name}
            onChange={e => setName(e.target.value)}
            required
          />
        </div>
        
        <div>
          <label htmlFor="publicKey">Public Key</label>
          <textarea
            id="publicKey"
            value={publicKey}
            onChange={e => setPublicKey(e.target.value)}
            placeholder="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC..."
            required
          />
        </div>
        
        <div>
          <label htmlFor="keyType">Key Type</label>
          <select
            id="keyType"
            value={keyType}
            onChange={e => setKeyType(e.target.value)}
          >
            <option value="access">Access</option>
            <option value="agent">Agent</option>
            <option value="deployment">Deployment</option>
          </select>
        </div>
        
        {keyType === 'agent' && (
          <div>
            <label htmlFor="agentId">Agent</label>
            <input
              id="agentId"
              value={agentId}
              onChange={e => setAgentId(e.target.value)}
              required
            />
          </div>
        )}
        
        {error && <div className="error">{error}</div>}
        
        <button type="submit" disabled={loading}>
          {loading ? 'Adding...' : 'Add Key'}
        </button>
      </form>
    </div>
  );
};
```

## Agent Registration and Management

### Agent Registration Form

```typescript
// In AgentRegistration.tsx
import { useState } from 'react';
import { registerAgent } from '../api/agent';

const AgentRegistration = () => {
  const [name, setName] = useState('');
  const [type, setType] = useState('worker');
  const [capabilities, setCapabilities] = useState([
    { name: '', description: '', parameters: {}, version: '1.0.0' }
  ]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [agentId, setAgentId] = useState('');
  
  const handleAddCapability = () => {
    setCapabilities([
      ...capabilities,
      { name: '', description: '', parameters: {}, version: '1.0.0' }
    ]);
  };
  
  const handleCapabilityChange = (index, field, value) => {
    const newCapabilities = [...capabilities];
    newCapabilities[index][field] = value;
    setCapabilities(newCapabilities);
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccess(false);
    
    try {
      const response = await registerAgent({
        name,
        type,
        capabilities: capabilities.filter(c => c.name.trim() !== ''),
        metadata: {
          created_by: 'web_ui',
          timestamp: new Date().toISOString()
        }
      });
      
      setSuccess(true);
      setAgentId(response.agent_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div>
      <h2>Register New Agent</h2>
      
      {success ? (
        <div className="success">
          <p>Agent registered successfully!</p>
          <p>Agent ID: {agentId}</p>
          <p>
            <button onClick={() => setSuccess(false)}>
              Register Another Agent
            </button>
            <button onClick={() => window.location.href = `/agents/${agentId}/keys`}>
              Add SSH Key for this Agent
            </button>
          </p>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div>
            <label htmlFor="name">Agent Name</label>
            <input
              id="name"
              value={name}
              onChange={e => setName(e.target.value)}
              required
            />
          </div>
          
          <div>
            <label htmlFor="type">Agent Type</label>
            <select
              id="type"
              value={type}
              onChange={e => setType(e.target.value)}
            >
              <option value="worker">Worker</option>
              <option value="processor">Processor</option>
              <option value="connector">Connector</option>
              <option value="custom">Custom</option>
            </select>
          </div>
          
          <div>
            <h3>Capabilities</h3>
            {capabilities.map((capability, index) => (
              <div key={index} className="capability-form">
                <div>
                  <label htmlFor={`capability-name-${index}`}>Name</label>
                  <input
                    id={`capability-name-${index}`}
                    value={capability.name}
                    onChange={e => handleCapabilityChange(index, 'name', e.target.value)}
                  />
                </div>
                
                <div>
                  <label htmlFor={`capability-desc-${index}`}>Description</label>
                  <input
                    id={`capability-desc-${index}`}
                    value={capability.description}
                    onChange={e => handleCapabilityChange(index, 'description', e.target.value)}
                  />
                </div>
                
                <div>
                  <label htmlFor={`capability-version-${index}`}>Version</label>
                  <input
                    id={`capability-version-${index}`}
                    value={capability.version}
                    onChange={e => handleCapabilityChange(index, 'version', e.target.value)}
                  />
                </div>
              </div>
            ))}
            
            <button type="button" onClick={handleAddCapability}>
              Add Capability
            </button>
          </div>
          
          {error && <div className="error">{error}</div>}
          
          <button type="submit" disabled={loading}>
            {loading ? 'Registering...' : 'Register Agent'}
          </button>
        </form>
      )}
    </div>
  );
};
```

## Real-time Agent Status Dashboard

```typescript
// In AgentDashboard.tsx
import { useState, useEffect } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchAgents } from '../api/agent';
import AgentStatusCard from '../components/agents/AgentStatusCard';
import AgentCommandPanel from '../components/agents/AgentCommandPanel';

const AgentDashboard = () => {
  const [agents, setAgents] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const { connected, messages, sendMessage } = useWebSocket();
  const [lastUpdated, setLastUpdated] = useState(new Date());
  
  useEffect(() => {
    const loadAgents = async () => {
      const data = await fetchAgents();
      setAgents(data.agents);
    };
    
    loadAgents();
    
    // Set up automatic refresh
    const interval = setInterval(() => {
      loadAgents();
      setLastUpdated(new Date());
    }, 60000); // Refresh every minute
    
    return () => clearInterval(interval);
  }, []);
  
  useEffect(() => {
    // Process WebSocket messages
    const agentMessages = messages.filter(m => 
      ['agent_status', 'heartbeat', 'response'].includes(m.type)
    );
    
    if (agentMessages.length > 0) {
      // Update agent data based on WebSocket messages
      const latestMessages = new Map();
      
      // Get latest message for each agent
      agentMessages.forEach(message => {
        const agentId = message.data.agent_id;
        if (!latestMessages.has(agentId) || 
            new Date(message.timestamp) > new Date(latestMessages.get(agentId).timestamp)) {
          latestMessages.set(agentId, message);
        }
      });
      
      // Update agents with latest data
      setAgents(prev => {
        return prev.map(agent => {
          const message = latestMessages.get(agent.agent_id);
          if (message) {
            // Update agent with realtime data
            return {
              ...agent,
              status: message.data.status || agent.status,
              last_seen: message.timestamp,
              current_task: message.data.current_task,
              // Add any other real-time fields
              cpu_usage: message.data.cpu_usage,
              memory_usage: message.data.memory_usage
            };
          }
          return agent;
        });
      });
      
      setLastUpdated(new Date());
    }
  }, [messages]);
  
  const handleAgentSelect = (agent) => {
    setSelectedAgent(agent);
  };
  
  const handleRefresh = () => {
    // Request status updates for all agents
    sendMessage('status_request', {
      agent_ids: agents.map(a => a.agent_id)
    });
    
    // Also refresh from API
    fetchAgents().then(data => {
      setAgents(data.agents);
      setLastUpdated(new Date());
    });
  };
  
  const handleCommand = (command, args) => {
    if (!selectedAgent) return;
    
    sendMessage('command', {
      command,
      args,
      agent_id: selectedAgent.agent_id,
      timestamp: new Date().toISOString()
    });
  };
  
  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Agent Dashboard</h1>
        <div className="dashboard-controls">
          <span>Last updated: {lastUpdated.toLocaleTimeString()}</span>
          <button 
            onClick={handleRefresh} 
            disabled={!connected}
            className="refresh-button"
          >
            Refresh
          </button>
          <div className="connection-status">
            {connected ? 
              <span className="status-online">● Connected</span> : 
              <span className="status-offline">● Disconnected</span>
            }
          </div>
        </div>
      </div>
      
      <div className="dashboard-content">
        <div className="agent-grid">
          {agents.map(agent => (
            <AgentStatusCard
              key={agent.agent_id}
              agent={agent}
              selected={selectedAgent?.agent_id === agent.agent_id}
              onSelect={() => handleAgentSelect(agent)}
            />
          ))}
        </div>
        
        {selectedAgent && (
          <AgentCommandPanel
            agent={selectedAgent}
            onCommand={handleCommand}
          />
        )}
      </div>
    </div>
  );
};
```

## Implementing Multi-tenancy

### Tenant Context Provider

```typescript
// In TenantContext.tsx
import { createContext, useContext, useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { fetchTenantDetails, listTenants } from '../api/tenant';

const TenantContext = createContext(null);

export const TenantProvider = ({ children }) => {
  const [currentTenant, setCurrentTenant] = useState(null);
  const [tenants, setTenants] = useState([]);
  const [loading, setLoading] = useState(true);
  const { user, isAuthenticated } = useAuth();
  
  useEffect(() => {
    if (!isAuthenticated) {
      setCurrentTenant(null);
      setTenants([]);
      setLoading(false);
      return;
    }
    
    const loadTenants = async () => {
      setLoading(true);
      try {
        // Get tenants the user has access to
        const tenantsData = await listTenants();
        setTenants(tenantsData);
        
        // Get tenant ID from JWT or local storage
        const storedTenantId = localStorage.getItem('currentTenantId');
        
        if (storedTenantId && tenantsData.some(t => t.id === storedTenantId)) {
          // If stored tenant ID is valid, use it
          const tenantDetails = await fetchTenantDetails(storedTenantId);
          setCurrentTenant(tenantDetails);
        } else if (tenantsData.length > 0) {
          // Otherwise use the first tenant
          const tenantDetails = await fetchTenantDetails(tenantsData[0].id);
          setCurrentTenant(tenantDetails);
          localStorage.setItem('currentTenantId', tenantDetails.id);
        }
      } catch (err) {
        console.error('Error loading tenants:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadTenants();
  }, [isAuthenticated, user]);
  
  const switchTenant = async (tenantId) => {
    if (!tenants.some(t => t.id === tenantId)) {
      throw new Error('Invalid tenant ID');
    }
    
    setLoading(true);
    try {
      const tenantDetails = await fetchTenantDetails(tenantId);
      setCurrentTenant(tenantDetails);
      localStorage.setItem('currentTenantId', tenantId);
    } catch (err) {
      console.error('Error switching tenant:', err);
      throw err;
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <TenantContext.Provider 
      value={{ 
        currentTenant, 
        tenants, 
        loading, 
        switchTenant 
      }}
    >
      {children}
    </TenantContext.Provider>
  );
};

export const useTenant = () => useContext(TenantContext);
```

### Tenant Selection UI

```typescript
// In TenantSelector.tsx
import { useTenant } from '../hooks/useTenant';

const TenantSelector = () => {
  const { currentTenant, tenants, loading, switchTenant } = useTenant();
  
  const handleChange = async (e) => {
    const tenantId = e.target.value;
    try {
      await switchTenant(tenantId);
      // Reload data for new tenant
      window.location.reload();
    } catch (err) {
      alert('Error switching tenant: ' + err.message);
    }
  };
  
  if (loading) {
    return <div>Loading...</div>;
  }
  
  if (!currentTenant || tenants.length === 0) {
    return <div>No tenants available</div>;
  }
  
  return (
    <div className="tenant-selector">
      <label htmlFor="tenant-select">Tenant:</label>
      <select
        id="tenant-select"
        value={currentTenant.id}
        onChange={handleChange}
        disabled={tenants.length === 1}
      >
        {tenants.map(tenant => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name}
          </option>
        ))}
      </select>
    </div>
  );
};
```

## Implementing API Communication

### API Client Setup

```typescript
// In api/client.ts
import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'https://api.artcafe.ai/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for authentication
apiClient.interceptors.request.use(
  (config) => {
    // Get token from localStorage or memory
    const token = localStorage.getItem('accessToken');
    
    // Get tenant ID from context or localStorage
    const tenantId = localStorage.getItem('currentTenantId');
    
    // Add token to header if available
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Add tenant ID to header if available
    if (tenantId) {
      config.headers['x-tenant-id'] = tenantId;
    }
    
    return config;
  },
  (error) => Promise.reject(error)
);

// Add response interceptor for token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // If error is 401 and we haven't tried to refresh token yet
    if (error.response.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      try {
        // Attempt to refresh token
        const refreshToken = localStorage.getItem('refreshToken');
        
        if (!refreshToken) {
          // No refresh token, redirect to login
          window.location.href = '/login';
          return Promise.reject(error);
        }
        
        const response = await axios.post(`${API_BASE_URL}/auth/refresh-token`, {
          refresh_token: refreshToken
        });
        
        // Update tokens
        const { access_token } = response.data;
        localStorage.setItem('accessToken', access_token);
        
        // Retry the original request with new token
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed, redirect to login
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

### Agent API Module

```typescript
// In api/agent.ts
import apiClient from './client';

export const fetchAgents = async (params = {}) => {
  const response = await apiClient.get('/agents', { params });
  return response.data;
};

export const fetchAgent = async (agentId) => {
  const response = await apiClient.get(`/agents/${agentId}`);
  return response.data;
};

export const registerAgent = async (agentData) => {
  const response = await apiClient.post('/agents', agentData);
  return response.data;
};

export const updateAgentStatus = async (agentId, status) => {
  const response = await apiClient.put(`/agents/${agentId}/status`, { status });
  return response.data;
};

export const deleteAgent = async (agentId) => {
  const response = await apiClient.delete(`/agents/${agentId}`);
  return response.data;
};
```

### SSH Key API Module

```typescript
// In api/ssh-key.ts
import apiClient from './client';

export const fetchSSHKeys = async (params = {}) => {
  const response = await apiClient.get('/ssh-keys', { params });
  return response.data;
};

export const createSSHKey = async (keyData) => {
  const response = await apiClient.post('/ssh-keys', keyData);
  return response.data;
};

export const deleteSSHKey = async (keyId) => {
  const response = await apiClient.delete(`/ssh-keys/${keyId}`);
  return response.status === 204;
};

export const revokeSSHKey = async (keyId, reason) => {
  const response = await apiClient.post(`/ssh-keys/${keyId}/revoke`, { reason });
  return response.data;
};
```

## Deployment with AWS Amplify

### Amplify Configuration

Create an `amplify.yml` file:

```yaml
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: build
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
```

### Environment Variables

Configure the following environment variables in Amplify Console:

- `REACT_APP_API_URL`: URL of your ArtCafe.ai PubSub API
- `REACT_APP_WS_URL`: WebSocket URL for real-time communication
- `REACT_APP_AUTH_DOMAIN`: Authentication domain (if using Cognito)
- `REACT_APP_AUTH_CLIENT_ID`: Authentication client ID (if using Cognito)

### Custom Domain and HTTPS

Configure a custom domain in Amplify Console with HTTPS enabled.

## Performance Optimization

1. **Code Splitting**: Use React.lazy and Suspense to split code by route
2. **Virtualized Lists**: Use react-window for long lists (agents, logs, etc.)
3. **Memoization**: Use useMemo and React.memo to prevent unnecessary re-renders
4. **Pagination**: Implement pagination for all list views
5. **Caching**: Use React Query or a similar tool for data caching
6. **Compression**: Enable Gzip/Brotli compression in your hosting config
7. **Bundler Optimization**: Configure your bundler (Webpack, etc.) for optimal output

## Accessibility Considerations

1. Ensure proper semantic HTML elements
2. Add ARIA attributes where needed
3. Maintain proper color contrast
4. Support keyboard navigation
5. Test with screen readers

## Browser Compatibility

Ensure support for:

1. Chrome (latest 2 versions)
2. Firefox (latest 2 versions)
3. Safari (latest 2 versions)
4. Edge (latest version)
5. Mobile browsers (iOS Safari, Android Chrome)