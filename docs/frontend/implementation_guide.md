# ArtCafe.ai Frontend Implementation Guide

This document provides step-by-step instructions for implementing the ArtCafe.ai multi-tenant React frontend application.

## Project Setup

### 1. Initialize React Project

Use Create React App with TypeScript template:

```bash
npx create-react-app artcafe-frontend --template typescript
cd artcafe-frontend
```

### 2. Install Dependencies

```bash
# Core dependencies
npm install react-router-dom axios @reduxjs/toolkit react-redux 

# UI framework (choose one)
npm install @mui/material @emotion/react @emotion/styled
# OR
npm install tailwindcss postcss autoprefixer

# Form handling
npm install react-hook-form yup @hookform/resolvers 

# WebSocket
npm install socket.io-client
# OR use native WebSocket API

# Utilities
npm install date-fns uuid jwt-decode
```

### 3. Configure TypeScript

Update `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es5",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "noFallthroughCasesInSwitch": true,
    "module": "esnext",
    "moduleResolution": "node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "baseUrl": "src",
    "paths": {
      "@/*": ["*"]
    }
  },
  "include": ["src"]
}
```

### 4. Set Up Environment Variables

Create `.env.development` and `.env.production` files:

```
# .env.development
REACT_APP_API_URL=http://localhost:8000/api/v1
REACT_APP_WS_URL=ws://localhost:8000/ws

# .env.production
REACT_APP_API_URL=https://api.artcafe.ai/api/v1
REACT_APP_WS_URL=wss://api.artcafe.ai/ws
```

## Implementation Steps

### Step 1: Define TypeScript Interfaces

Create type definitions for API responses and application state:

```typescript
// src/types/agent.ts
export interface Capability {
  name: string;
  description: string;
  parameters: Record<string, any>;
  version: string;
}

export interface Agent {
  agent_id: string;
  name: string;
  type: string;
  status: 'online' | 'offline' | 'busy' | 'error';
  capabilities: Capability[];
  last_seen: string | null;
  created_at: string;
  metadata: Record<string, any>;
  current_task?: string;
  cpu_usage?: number;
  memory_usage?: number;
}

export interface AgentCreate {
  name: string;
  type: string;
  capabilities: Capability[];
  metadata?: Record<string, any>;
}

// src/types/ssh-key.ts
export interface SSHKey {
  key_id: string;
  name: string;
  public_key: string;
  key_type: 'access' | 'agent' | 'deployment';
  agent_id?: string;
  fingerprint: string;
  status: 'active' | 'revoked';
  last_used: string | null;
  revoked: boolean;
  revoked_at: string | null;
  revocation_reason: string | null;
  created_at: string;
}

export interface SSHKeyCreate {
  name: string;
  public_key: string;
  key_type?: 'access' | 'agent' | 'deployment';
  agent_id?: string;
  metadata?: Record<string, any>;
}

// src/types/tenant.ts
export interface Tenant {
  tenant_id: string;
  name: string;
  admin_email: string;
  status: 'active' | 'inactive' | 'suspended';
  subscription_tier: 'free' | 'basic' | 'standard' | 'premium';
  created_at: string;
  metadata: Record<string, any>;
  payment_status: 'active' | 'inactive' | 'trial' | 'expired';
  subscription_expires_at: string | null;
}

// src/types/auth.ts
export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
}

// src/types/websocket.ts
export interface WebSocketMessage {
  type: string;
  id: string;
  data: Record<string, any>;
  timestamp: string;
}
```

### Step 2: Implement API Client

Create API client utilities:

```typescript
// src/api/client.ts
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('accessToken');
    const tenantId = localStorage.getItem('currentTenantId');
    
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    if (tenantId) {
      config.headers['x-tenant-id'] = tenantId;
    }
    
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      // Redirect to login if refresh token isn't implemented
      window.location.href = '/login';
      return Promise.reject(error);
      
      // Uncomment below to implement token refresh
      /*
      try {
        const refreshToken = localStorage.getItem('refreshToken');
        
        if (!refreshToken) {
          window.location.href = '/login';
          return Promise.reject(error);
        }
        
        const response = await axios.post(
          `${process.env.REACT_APP_API_URL}/auth/refresh-token`,
          { refresh_token: refreshToken }
        );
        
        const { access_token } = response.data;
        localStorage.setItem('accessToken', access_token);
        
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
      */
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

### Step 3: Set Up Authentication

Create authentication context and hooks:

```typescript
// src/context/AuthContext.tsx
import { createContext, useContext, useState, useEffect } from 'react';
import jwtDecode from 'jwt-decode';
import { User, AuthState } from '../types/auth';

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC = ({ children }) => {
  const [authState, setAuthState] = useState<AuthState>({
    user: null,
    accessToken: null,
    isAuthenticated: false,
    loading: true,
    error: null,
  });
  
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('accessToken');
      
      if (!token) {
        setAuthState(prev => ({ ...prev, loading: false }));
        return;
      }
      
      try {
        // Decode the token
        const decoded: any = jwtDecode(token);
        
        // Check if token is expired
        const currentTime = Date.now() / 1000;
        if (decoded.exp < currentTime) {
          localStorage.removeItem('accessToken');
          setAuthState(prev => ({ 
            ...prev, 
            loading: false,
            error: 'Session expired. Please log in again.'
          }));
          return;
        }
        
        // Extract user data from token
        const user: User = {
          id: decoded.sub,
          email: decoded.email,
          name: decoded.name || decoded.email,
          role: decoded.role || 'user',
        };
        
        setAuthState({
          user,
          accessToken: token,
          isAuthenticated: true,
          loading: false,
          error: null,
        });
      } catch (error) {
        localStorage.removeItem('accessToken');
        setAuthState(prev => ({ 
          ...prev, 
          loading: false,
          error: 'Invalid session. Please log in again.'
        }));
      }
    };
    
    initAuth();
  }, []);
  
  const login = async (email: string, password: string) => {
    setAuthState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      // Call login API endpoint
      const response = await fetch(`${process.env.REACT_APP_API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      
      if (!response.ok) {
        throw new Error('Login failed. Please check your credentials.');
      }
      
      const data = await response.json();
      
      // Save token to localStorage
      localStorage.setItem('accessToken', data.access_token);
      
      // Decode token to get user info
      const decoded: any = jwtDecode(data.access_token);
      
      const user: User = {
        id: decoded.sub,
        email: decoded.email,
        name: decoded.name || decoded.email,
        role: decoded.role || 'user',
      };
      
      setAuthState({
        user,
        accessToken: data.access_token,
        isAuthenticated: true,
        loading: false,
        error: null,
      });
    } catch (error) {
      setAuthState(prev => ({ 
        ...prev, 
        loading: false,
        error: error instanceof Error ? error.message : 'An unknown error occurred'
      }));
    }
  };
  
  const logout = () => {
    localStorage.removeItem('accessToken');
    localStorage.removeItem('refreshToken');
    
    setAuthState({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      loading: false,
      error: null,
    });
  };
  
  return (
    <AuthContext.Provider 
      value={{ 
        ...authState,
        login,
        logout
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
```

### Step 4: Set Up Tenant Context

Implement tenant context for multi-tenancy:

```typescript
// src/context/TenantContext.tsx
import { createContext, useContext, useState, useEffect } from 'react';
import { Tenant } from '../types/tenant';
import { useAuth } from '../hooks/useAuth';
import apiClient from '../api/client';

interface TenantContextType {
  currentTenant: Tenant | null;
  tenants: Tenant[];
  loading: boolean;
  switchTenant: (tenantId: string) => Promise<void>;
}

const TenantContext = createContext<TenantContextType | undefined>(undefined);

export const TenantProvider: React.FC = ({ children }) => {
  const [currentTenant, setCurrentTenant] = useState<Tenant | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const { isAuthenticated } = useAuth();
  
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
        // Fetch tenants the user has access to
        const response = await apiClient.get('/tenants');
        const tenantsData = response.data.tenants;
        setTenants(tenantsData);
        
        // Get tenant ID from local storage
        const storedTenantId = localStorage.getItem('currentTenantId');
        
        if (storedTenantId && tenantsData.some(t => t.tenant_id === storedTenantId)) {
          // If stored tenant ID is valid, fetch its details
          const tenantResponse = await apiClient.get(`/tenants/${storedTenantId}`);
          setCurrentTenant(tenantResponse.data);
        } else if (tenantsData.length > 0) {
          // Otherwise use the first tenant
          const tenantResponse = await apiClient.get(`/tenants/${tenantsData[0].tenant_id}`);
          setCurrentTenant(tenantResponse.data);
          localStorage.setItem('currentTenantId', tenantsData[0].tenant_id);
        }
      } catch (err) {
        console.error('Error loading tenants:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadTenants();
  }, [isAuthenticated]);
  
  const switchTenant = async (tenantId: string) => {
    if (!tenants.some(t => t.tenant_id === tenantId)) {
      throw new Error('Invalid tenant ID');
    }
    
    setLoading(true);
    try {
      const response = await apiClient.get(`/tenants/${tenantId}`);
      setCurrentTenant(response.data);
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

export const useTenant = () => {
  const context = useContext(TenantContext);
  if (context === undefined) {
    throw new Error('useTenant must be used within a TenantProvider');
  }
  return context;
};
```

### Step 5: Implement WebSocket Context

Create WebSocket context for real-time communication:

```typescript
// src/context/WebSocketContext.tsx
import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';
import { useTenant } from '../hooks/useTenant';
import { WebSocketMessage } from '../types/websocket';

interface WebSocketContextType {
  connected: boolean;
  messages: WebSocketMessage[];
  sendMessage: (type: string, data: Record<string, any>) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const WebSocketProvider: React.FC = ({ children }) => {
  const [socket, setSocket] = useState<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const { accessToken, isAuthenticated } = useAuth();
  const { currentTenant } = useTenant();
  
  const connectWebSocket = useCallback(() => {
    if (!isAuthenticated || !accessToken || !currentTenant) {
      return;
    }
    
    // Close existing socket if any
    if (socket) {
      socket.close();
    }
    
    // Create WebSocket connection
    const ws = new WebSocket(process.env.REACT_APP_WS_URL || 'ws://localhost:8000/ws');
    
    // Connection opened
    ws.addEventListener('open', () => {
      console.log('Connected to WebSocket');
      setConnected(true);
      
      // Send authentication message
      ws.send(JSON.stringify({
        type: 'auth',
        data: {
          token: accessToken,
          tenant_id: currentTenant.tenant_id
        },
        timestamp: new Date().toISOString()
      }));
    });
    
    // Listen for messages
    ws.addEventListener('message', (event) => {
      try {
        const message = JSON.parse(event.data) as WebSocketMessage;
        setMessages(prev => [...prev, message]);
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    });
    
    // Connection closed
    ws.addEventListener('close', () => {
      console.log('Disconnected from WebSocket');
      setConnected(false);
      
      // Attempt to reconnect after delay
      setTimeout(connectWebSocket, 5000);
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
  }, [isAuthenticated, accessToken, currentTenant]);
  
  useEffect(() => {
    connectWebSocket();
    
    return () => {
      if (socket) {
        socket.close();
      }
    };
  }, [connectWebSocket]);
  
  // Function to send messages
  const sendMessage = (type: string, data: Record<string, any>) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected');
      return;
    }
    
    socket.send(JSON.stringify({
      type,
      id: crypto.randomUUID(),
      data,
      timestamp: new Date().toISOString()
    }));
  };
  
  return (
    <WebSocketContext.Provider 
      value={{ 
        connected, 
        messages, 
        sendMessage 
      }}
    >
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};
```

### Step 6: Set Up Application Layout

Create layout components:

```typescript
// src/components/layout/MainLayout.tsx
import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import AppBar from './AppBar';
import Sidebar from './Sidebar';
import { useAuth } from '../../hooks/useAuth';

const MainLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { isAuthenticated } = useAuth();
  
  if (!isAuthenticated) {
    // Redirect to login or show auth required message
    return <div>Please log in to access this page</div>;
  }
  
  return (
    <div className="app-container">
      <AppBar onMenuClick={() => setSidebarOpen(true)} />
      
      <div className="app-content">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        
        <main className="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default MainLayout;

// src/components/layout/AppBar.tsx
import { useAuth } from '../../hooks/useAuth';
import { useTenant } from '../../hooks/useTenant';
import TenantSelector from '../tenant/TenantSelector';

interface AppBarProps {
  onMenuClick: () => void;
}

const AppBar: React.FC<AppBarProps> = ({ onMenuClick }) => {
  const { user, logout } = useAuth();
  
  return (
    <header className="app-bar">
      <div className="app-bar-left">
        <button className="menu-button" onClick={onMenuClick}>
          <span>≡</span>
        </button>
        <div className="app-logo">ArtCafe.ai</div>
      </div>
      
      <div className="app-bar-center">
        <TenantSelector />
      </div>
      
      <div className="app-bar-right">
        <div className="user-info">
          <span>{user?.name}</span>
          <button className="logout-button" onClick={logout}>
            Logout
          </button>
        </div>
      </div>
    </header>
  );
};

export default AppBar;

// src/components/layout/Sidebar.tsx
import { NavLink } from 'react-router-dom';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
  return (
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="sidebar-header">
        <button className="close-button" onClick={onClose}>
          ×
        </button>
      </div>
      
      <nav className="sidebar-nav">
        <ul>
          <li>
            <NavLink to="/dashboard" onClick={onClose}>
              Dashboard
            </NavLink>
          </li>
          <li>
            <NavLink to="/agents" onClick={onClose}>
              Agents
            </NavLink>
          </li>
          <li>
            <NavLink to="/keys" onClick={onClose}>
              SSH Keys
            </NavLink>
          </li>
          <li>
            <NavLink to="/usage" onClick={onClose}>
              Usage
            </NavLink>
          </li>
          <li>
            <NavLink to="/settings" onClick={onClose}>
              Settings
            </NavLink>
          </li>
        </ul>
      </nav>
    </aside>
  );
};

export default Sidebar;
```

### Step 7: Implement Login Page

Create login form:

```typescript
// src/pages/auth/LoginPage.tsx
import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { login, loading, error } = useAuth();
  const navigate = useNavigate();
  
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err) {
      // Error handling is done in the auth context
    }
  };
  
  return (
    <div className="auth-page">
      <div className="auth-container">
        <div className="auth-header">
          <h1>ArtCafe.ai</h1>
          <p>Sign in to your account</p>
        </div>
        
        <form className="auth-form" onSubmit={handleSubmit}>
          {error && (
            <div className="auth-error">
              {error}
            </div>
          )}
          
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          
          <button 
            type="submit" 
            className="auth-button"
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
        
        <div className="auth-footer">
          <p>
            Don't have an account?{' '}
            <Link to="/signup">Sign up</Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
```

### Step 8: Implement Agent Pages

Create agent list and detail pages:

```typescript
// src/pages/agents/AgentListPage.tsx
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useWebSocket } from '../../hooks/useWebSocket';
import { fetchAgents } from '../../api/agent';
import { Agent } from '../../types/agent';
import AgentCard from '../../components/agents/AgentCard';

const AgentListPage: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { connected, messages } = useWebSocket();
  
  useEffect(() => {
    const loadAgents = async () => {
      try {
        setLoading(true);
        const data = await fetchAgents();
        setAgents(data.agents);
        setError(null);
      } catch (err) {
        setError('Failed to load agents');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    loadAgents();
  }, []);
  
  useEffect(() => {
    // Process WebSocket messages
    const agentMessages = messages.filter(m => 
      ['agent_status', 'heartbeat'].includes(m.type)
    );
    
    if (agentMessages.length > 0) {
      // Create a map for quick lookup of latest message per agent
      const latestMessages = new Map();
      
      agentMessages.forEach(message => {
        const agentId = message.data.agent_id;
        if (!latestMessages.has(agentId) || 
            new Date(message.timestamp) > new Date(latestMessages.get(agentId).timestamp)) {
          latestMessages.set(agentId, message);
        }
      });
      
      // Update agents
      setAgents(prev => {
        return prev.map(agent => {
          const message = latestMessages.get(agent.agent_id);
          if (message) {
            return {
              ...agent,
              status: message.data.status || agent.status,
              last_seen: message.timestamp,
              // Add other real-time fields
            };
          }
          return agent;
        });
      });
    }
  }, [messages]);
  
  if (loading) {
    return <div>Loading agents...</div>;
  }
  
  if (error) {
    return <div className="error-message">{error}</div>;
  }
  
  return (
    <div className="agent-list-page">
      <div className="page-header">
        <h1>Agents</h1>
        <div className="connection-status">
          {connected ? 
            <span className="status-online">● Connected</span> : 
            <span className="status-offline">● Disconnected</span>
          }
        </div>
        <Link to="/agents/new" className="button-primary">
          Register New Agent
        </Link>
      </div>
      
      {agents.length === 0 ? (
        <div className="empty-state">
          <p>No agents found. Start by registering a new agent.</p>
        </div>
      ) : (
        <div className="agent-grid">
          {agents.map(agent => (
            <AgentCard
              key={agent.agent_id}
              agent={agent}
              onSelect={() => {/* Handle selection */}}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default AgentListPage;

// src/components/agents/AgentCard.tsx
import { format } from 'date-fns';
import { Agent } from '../../types/agent';

interface AgentCardProps {
  agent: Agent;
  onSelect: () => void;
}

const AgentCard: React.FC<AgentCardProps> = ({ agent, onSelect }) => {
  const statusColors = {
    online: 'green',
    offline: 'gray',
    busy: 'orange',
    error: 'red'
  };
  
  return (
    <div 
      className={`agent-card status-${agent.status}`}
      onClick={onSelect}
    >
      <div className="agent-card-header">
        <h3>{agent.name}</h3>
        <div 
          className="agent-status" 
          style={{ backgroundColor: statusColors[agent.status] }}
        >
          {agent.status}
        </div>
      </div>
      
      <div className="agent-card-body">
        <div className="agent-info">
          <div>Type: {agent.type}</div>
          <div>
            Capabilities: {agent.capabilities.length}
          </div>
          {agent.last_seen && (
            <div>
              Last seen: {format(new Date(agent.last_seen), 'PPp')}
            </div>
          )}
        </div>
        
        {agent.current_task && (
          <div className="agent-task">
            Current task: {agent.current_task}
          </div>
        )}
      </div>
      
      <div className="agent-card-footer">
        <span className="agent-id">ID: {agent.agent_id}</span>
      </div>
    </div>
  );
};

export default AgentCard;
```

### Step 9: Implement SSH Key Management

Create SSH key management pages:

```typescript
// src/pages/keys/SSHKeyListPage.tsx
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { fetchSSHKeys } from '../../api/ssh-key';
import { SSHKey } from '../../types/ssh-key';
import SSHKeyItem from '../../components/keys/SSHKeyItem';

const SSHKeyListPage: React.FC = () => {
  const [keys, setKeys] = useState<SSHKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    const loadKeys = async () => {
      try {
        setLoading(true);
        const data = await fetchSSHKeys();
        setKeys(data.ssh_keys);
        setError(null);
      } catch (err) {
        setError('Failed to load SSH keys');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    
    loadKeys();
  }, []);
  
  const handleDeleteKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to delete this key?')) {
      return;
    }
    
    try {
      await deleteSSHKey(keyId);
      // Remove deleted key from state
      setKeys(keys.filter(key => key.key_id !== keyId));
    } catch (err) {
      alert('Failed to delete key');
      console.error(err);
    }
  };
  
  const handleRevokeKey = async (keyId: string) => {
    if (!confirm('Are you sure you want to revoke this key?')) {
      return;
    }
    
    const reason = prompt('Please provide a reason for revocation:');
    if (!reason) return;
    
    try {
      const updatedKey = await revokeSSHKey(keyId, reason);
      // Update the key in state
      setKeys(keys.map(key => 
        key.key_id === keyId ? updatedKey : key
      ));
    } catch (err) {
      alert('Failed to revoke key');
      console.error(err);
    }
  };
  
  if (loading) {
    return <div>Loading SSH keys...</div>;
  }
  
  if (error) {
    return <div className="error-message">{error}</div>;
  }
  
  return (
    <div className="ssh-key-list-page">
      <div className="page-header">
        <h1>SSH Keys</h1>
        <Link to="/keys/new" className="button-primary">
          Add New Key
        </Link>
      </div>
      
      {keys.length === 0 ? (
        <div className="empty-state">
          <p>No SSH keys found. Start by adding a new key.</p>
        </div>
      ) : (
        <div className="ssh-key-list">
          {keys.map(key => (
            <SSHKeyItem
              key={key.key_id}
              sshKey={key}
              onDelete={() => handleDeleteKey(key.key_id)}
              onRevoke={() => handleRevokeKey(key.key_id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default SSHKeyListPage;

// src/components/keys/SSHKeyItem.tsx
import { format } from 'date-fns';
import { SSHKey } from '../../types/ssh-key';

interface SSHKeyItemProps {
  sshKey: SSHKey;
  onDelete: () => void;
  onRevoke: () => void;
}

const SSHKeyItem: React.FC<SSHKeyItemProps> = ({ 
  sshKey, 
  onDelete, 
  onRevoke 
}) => {
  return (
    <div className={`ssh-key-item ${sshKey.revoked ? 'revoked' : ''}`}>
      <div className="ssh-key-header">
        <h3>{sshKey.name}</h3>
        <div className="ssh-key-type">
          {sshKey.key_type}
        </div>
      </div>
      
      <div className="ssh-key-body">
        <div className="ssh-key-fingerprint">
          {sshKey.fingerprint}
        </div>
        
        <div className="ssh-key-public">
          <div className="public-key-preview">
            {sshKey.public_key.substring(0, 30)}...
          </div>
          <button 
            className="button-small"
            onClick={() => navigator.clipboard.writeText(sshKey.public_key)}
          >
            Copy
          </button>
        </div>
        
        {sshKey.agent_id && (
          <div className="ssh-key-agent">
            Associated Agent: {sshKey.agent_id}
          </div>
        )}
        
        <div className="ssh-key-info">
          <div>Created: {format(new Date(sshKey.created_at), 'PPp')}</div>
          {sshKey.last_used && (
            <div>Last used: {format(new Date(sshKey.last_used), 'PPp')}</div>
          )}
        </div>
        
        {sshKey.revoked && (
          <div className="ssh-key-revoked">
            <div>Revoked: {format(new Date(sshKey.revoked_at!), 'PPp')}</div>
            <div>Reason: {sshKey.revocation_reason}</div>
          </div>
        )}
      </div>
      
      <div className="ssh-key-actions">
        {!sshKey.revoked && (
          <button 
            className="button-warning"
            onClick={onRevoke}
          >
            Revoke
          </button>
        )}
        <button 
          className="button-danger"
          onClick={onDelete}
        >
          Delete
        </button>
      </div>
    </div>
  );
};

export default SSHKeyItem;
```

### Step 10: Set Up Routes

Configure application routes:

```typescript
// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { TenantProvider } from './context/TenantContext';
import { WebSocketProvider } from './context/WebSocketContext';
import RequireAuth from './components/auth/RequireAuth';
import MainLayout from './components/layout/MainLayout';
import LoginPage from './pages/auth/LoginPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import AgentListPage from './pages/agents/AgentListPage';
import AgentDetailPage from './pages/agents/AgentDetailPage';
import AgentRegisterPage from './pages/agents/AgentRegisterPage';
import SSHKeyListPage from './pages/keys/SSHKeyListPage';
import SSHKeyAddPage from './pages/keys/SSHKeyAddPage';
import SettingsPage from './pages/settings/SettingsPage';
import NotFoundPage from './pages/NotFoundPage';

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <TenantProvider>
          <WebSocketProvider>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<LoginPage />} />
              
              {/* Protected routes */}
              <Route element={<RequireAuth />}>
                <Route element={<MainLayout />}>
                  <Route path="/" element={<Navigate to="/dashboard" replace />} />
                  <Route path="/dashboard" element={<DashboardPage />} />
                  
                  <Route path="/agents">
                    <Route index element={<AgentListPage />} />
                    <Route path=":id" element={<AgentDetailPage />} />
                    <Route path="new" element={<AgentRegisterPage />} />
                  </Route>
                  
                  <Route path="/keys">
                    <Route index element={<SSHKeyListPage />} />
                    <Route path="new" element={<SSHKeyAddPage />} />
                  </Route>
                  
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>
              
              {/* Not found route */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </WebSocketProvider>
        </TenantProvider>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;

// src/components/auth/RequireAuth.tsx
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';

const RequireAuth: React.FC = () => {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  
  if (loading) {
    return <div>Loading...</div>;
  }
  
  if (!isAuthenticated) {
    // Redirect to login page, but save the current location to redirect back after login
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  
  return <Outlet />;
};

export default RequireAuth;
```

### Step 11: Styling the Application

Create styles for the application:

```scss
// src/styles/main.scss

// Variables
$primary-color: #4a6cf7;
$secondary-color: #6c757d;
$success-color: #28a745;
$danger-color: #dc3545;
$warning-color: #ffc107;
$info-color: #17a2b8;
$light-color: #f8f9fa;
$dark-color: #343a40;

$status-online: #4caf50;
$status-offline: #9e9e9e;
$status-busy: #ff9800;
$status-error: #f44336;

$breakpoint-sm: 576px;
$breakpoint-md: 768px;
$breakpoint-lg: 992px;
$breakpoint-xl: 1200px;

// Reset & Base
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  line-height: 1.6;
  color: $dark-color;
  background-color: #f4f7fa;
}

a {
  color: $primary-color;
  text-decoration: none;
  
  &:hover {
    text-decoration: underline;
  }
}

button, .button {
  cursor: pointer;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: 500;
  transition: all 0.3s ease;
  
  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
}

.button-primary {
  background-color: $primary-color;
  color: white;
  border: none;
  
  &:hover {
    background-color: darken($primary-color, 10%);
  }
}

.button-secondary {
  background-color: $secondary-color;
  color: white;
  border: none;
  
  &:hover {
    background-color: darken($secondary-color, 10%);
  }
}

.button-danger {
  background-color: $danger-color;
  color: white;
  border: none;
  
  &:hover {
    background-color: darken($danger-color, 10%);
  }
}

// Layout
.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-content {
  display: flex;
  flex: 1;
}

.main-content {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

// App Bar
.app-bar {
  height: 64px;
  background-color: white;
  border-bottom: 1px solid #ddd;
  display: flex;
  align-items: center;
  padding: 0 20px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  z-index: 10;
  
  .app-bar-left, .app-bar-center, .app-bar-right {
    flex: 1;
    display: flex;
    align-items: center;
  }
  
  .app-bar-left {
    justify-content: flex-start;
  }
  
  .app-bar-center {
    justify-content: center;
  }
  
  .app-bar-right {
    justify-content: flex-end;
  }
  
  .app-logo {
    font-size: 1.5rem;
    font-weight: bold;
    color: $primary-color;
    margin-left: 15px;
  }
  
  .menu-button {
    background: none;
    border: none;
    font-size: 1.5rem;
    color: $dark-color;
    cursor: pointer;
  }
  
  .user-info {
    display: flex;
    align-items: center;
    
    span {
      margin-right: 15px;
    }
    
    .logout-button {
      background: none;
      border: none;
      color: $danger-color;
      font-weight: 500;
      cursor: pointer;
    }
  }
}

// Sidebar
.sidebar {
  width: 250px;
  background-color: white;
  border-right: 1px solid #ddd;
  height: calc(100vh - 64px);
  position: fixed;
  top: 64px;
  left: 0;
  z-index: 5;
  transform: translateX(-100%);
  transition: transform 0.3s ease;
  overflow-y: auto;
  
  &.open {
    transform: translateX(0);
  }
  
  @media (min-width: $breakpoint-lg) {
    transform: translateX(0);
    position: relative;
    top: 0;
  }
  
  .sidebar-header {
    padding: 20px;
    border-bottom: 1px solid #ddd;
    
    .close-button {
      display: block;
      background: none;
      border: none;
      font-size: 1.5rem;
      cursor: pointer;
      margin-left: auto;
      
      @media (min-width: $breakpoint-lg) {
        display: none;
      }
    }
  }
  
  .sidebar-nav {
    ul {
      list-style: none;
      padding: 0;
      
      li {
        a {
          display: block;
          padding: 15px 20px;
          color: $dark-color;
          border-left: 3px solid transparent;
          
          &:hover, &.active {
            background-color: #f5f5f5;
            border-left-color: $primary-color;
            text-decoration: none;
          }
          
          &.active {
            color: $primary-color;
            font-weight: 500;
          }
        }
      }
    }
  }
}

// Page header
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  
  h1 {
    margin: 0;
    font-size: 1.8rem;
  }
}

// Connection status
.connection-status {
  display: flex;
  align-items: center;
  font-size: 0.9rem;
  
  .status-online {
    color: $status-online;
  }
  
  .status-offline {
    color: $status-offline;
  }
}

// Agent card
.agent-card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
  }
  
  &.status-online {
    border-top: 3px solid $status-online;
  }
  
  &.status-offline {
    border-top: 3px solid $status-offline;
  }
  
  &.status-busy {
    border-top: 3px solid $status-busy;
  }
  
  &.status-error {
    border-top: 3px solid $status-error;
  }
  
  .agent-card-header {
    padding: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #eee;
    
    h3 {
      margin: 0;
      font-size: 1.1rem;
    }
    
    .agent-status {
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 0.8rem;
      color: white;
      text-transform: capitalize;
    }
  }
  
  .agent-card-body {
    padding: 16px;
    
    .agent-info {
      font-size: 0.9rem;
      color: $secondary-color;
      
      > div {
        margin-bottom: 4px;
      }
    }
    
    .agent-task {
      margin-top: 12px;
      padding: 8px;
      background-color: #f8f9fa;
      border-radius: 4px;
      font-size: 0.9rem;
    }
  }
  
  .agent-card-footer {
    padding: 12px 16px;
    background-color: #f8f9fa;
    border-top: 1px solid #eee;
    
    .agent-id {
      font-size: 0.8rem;
      color: $secondary-color;
    }
  }
}

.agent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 24px;
  
  @media (max-width: $breakpoint-sm) {
    grid-template-columns: 1fr;
  }
}

// SSH Key Item
.ssh-key-item {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  margin-bottom: 16px;
  
  &.revoked {
    opacity: 0.6;
  }
  
  .ssh-key-header {
    padding: 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #eee;
    
    h3 {
      margin: 0;
      font-size: 1.1rem;
    }
    
    .ssh-key-type {
      padding: 4px 8px;
      background-color: #e9ecef;
      border-radius: 4px;
      font-size: 0.8rem;
      text-transform: capitalize;
    }
  }
  
  .ssh-key-body {
    padding: 16px;
    
    .ssh-key-fingerprint {
      font-family: monospace;
      background-color: #f5f5f5;
      padding: 8px;
      border-radius: 4px;
      margin-bottom: 16px;
      font-size: 0.9rem;
      word-break: break-all;
    }
    
    .ssh-key-public {
      display: flex;
      align-items: center;
      margin-bottom: 16px;
      
      .public-key-preview {
        font-family: monospace;
        background-color: #f5f5f5;
        padding: 8px;
        border-radius: 4px;
        margin-right: 8px;
        flex: 1;
        font-size: 0.9rem;
      }
    }
    
    .ssh-key-agent {
      margin-bottom: 16px;
      padding: 8px;
      background-color: #f5f5f5;
      border-radius: 4px;
      font-size: 0.9rem;
    }
    
    .ssh-key-info {
      font-size: 0.9rem;
      color: $secondary-color;
      
      > div {
        margin-bottom: 4px;
      }
    }
    
    .ssh-key-revoked {
      margin-top: 12px;
      padding: 12px;
      background-color: #fff3cd;
      border-radius: 4px;
      font-size: 0.9rem;
    }
  }
  
  .ssh-key-actions {
    padding: 12px 16px;
    background-color: #f8f9fa;
    border-top: 1px solid #eee;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }
}

// Forms
.form-group {
  margin-bottom: 20px;
  
  label {
    display: block;
    margin-bottom: 6px;
    font-weight: 500;
  }
  
  input, select, textarea {
    width: 100%;
    padding: 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 1rem;
    
    &:focus {
      outline: none;
      border-color: $primary-color;
    }
  }
  
  textarea {
    min-height: 100px;
  }
  
  .input-hint {
    font-size: 0.8rem;
    color: $secondary-color;
    margin-top: 4px;
  }
}

// Auth pages
.auth-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f5f7fa;
  
  .auth-container {
    width: 100%;
    max-width: 400px;
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    overflow: hidden;
  }
  
  .auth-header {
    padding: 24px;
    text-align: center;
    border-bottom: 1px solid #eee;
    
    h1 {
      margin: 0 0 8px;
      color: $primary-color;
    }
    
    p {
      margin: 0;
      color: $secondary-color;
    }
  }
  
  .auth-form {
    padding: 24px;
    
    .auth-error {
      padding: 12px;
      margin-bottom: 16px;
      background-color: #f8d7da;
      border: 1px solid #f5c6cb;
      border-radius: 4px;
      color: $danger-color;
    }
    
    .auth-button {
      width: 100%;
      padding: 12px;
      background-color: $primary-color;
      color: white;
      border: none;
      border-radius: 4px;
      font-size: 1rem;
      font-weight: 500;
      cursor: pointer;
      
      &:hover {
        background-color: darken($primary-color, 10%);
      }
      
      &:disabled {
        background-color: lighten($primary-color, 20%);
        cursor: not-allowed;
      }
    }
  }
  
  .auth-footer {
    padding: 16px 24px;
    text-align: center;
    background-color: #f8f9fa;
    border-top: 1px solid #eee;
    
    p {
      margin: 0;
      font-size: 0.9rem;
      
      a {
        color: $primary-color;
        font-weight: 500;
      }
    }
  }
}

// Empty states
.empty-state {
  padding: 40px;
  text-align: center;
  background-color: #f8f9fa;
  border-radius: 8px;
  margin-top: 24px;
  
  p {
    color: $secondary-color;
    margin-bottom: 16px;
  }
}

// Error message
.error-message {
  padding: 16px;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  border-radius: 4px;
  color: $danger-color;
  margin-bottom: 24px;
}
```

### Step 12: Final Application Entry Point

Set up the entry point:

```typescript
// src/index.tsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/main.scss';

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

## Deployment Steps

### Step 1: Build the Application

```bash
npm run build
```

### Step 2: Set Up AWS Amplify

1. Create a new AWS Amplify app:
   - Go to AWS Amplify console
   - Click "Create app"
   - Choose "Deploy without Git provider" for manual deployments

2. Configure the build settings:
   - Deploy type: Manual deployment
   - Build settings: Use the default settings
   - Environment variables: Configure your API endpoint and other settings

3. Upload the build files:
   - Compress the `build` directory into a zip file
   - Upload the zip file to Amplify

### Step 3: Configure Custom Domain (Optional)

1. In the Amplify console, go to "Domain management"
2. Add a custom domain
3. Configure DNS settings as directed by Amplify

### Step 4: Verify Deployment

1. Check the provided Amplify URL to ensure the app is working
2. Test all functionality with the deployed backend

## Conclusion

This implementation guide provides the foundation for building a robust, multi-tenant React application that integrates with the ArtCafe.ai PubSub service. By following these steps, you'll create a frontend that supports:

1. Secure authentication with JWT tokens
2. Multi-tenant data isolation
3. Real-time agent status monitoring via WebSockets
4. SSH key management for agent authentication
5. A responsive, modern user interface

The guide is structured to be modular, allowing you to adapt and extend it based on your specific requirements. As the application grows, consider implementing additional features like advanced filtering, analytics dashboards, and user role management.