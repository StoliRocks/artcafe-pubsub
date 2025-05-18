# ArtCafe.ai Frontend Security Best Practices

This document outlines security best practices for the ArtCafe.ai multi-tenant React frontend application.

## Authentication & Authorization

### JWT Token Security

1. **Token Storage**
   - Store access tokens in memory (variables) only, not in localStorage
   - Store refresh tokens in HTTPOnly cookies to prevent XSS attacks
   - Use short expiration times for access tokens (15-30 minutes)
   - Use longer expiration times for refresh tokens (hours to days)

2. **Token Validation**
   - Validate token signature on the backend for every request
   - Check token expiration time before processing requests
   - Verify audience (`aud`) and issuer (`iss`) claims
   - Include and validate the `tenant_id` claim for multi-tenant security

3. **CSRF Protection**
   - Implement CSRF tokens for all state-changing operations
   - Use the `SameSite=Strict` cookie attribute for all session cookies
   - Include custom headers (like `X-Requested-With`) in AJAX requests

### Multi-Tenant Isolation

1. **Tenant Identification**
   - Include `tenant_id` in all API requests via HTTP header
   - Validate tenant ID on both client and server side
   - Use tenant context to scope all data operations

2. **Tenant Switching**
   - Re-authenticate when switching tenants
   - Clear all cached data when tenant context changes
   - Log all tenant switching activities

3. **Cross-Tenant Prevention**
   - Ensure tenant A cannot access tenant B's data through UI manipulation
   - Add tenant ID checks in all API routes
   - Create separate Redux stores/slices for each tenant

## Frontend Application Security

### XSS Prevention

1. **Content Security Policy (CSP)**
   - Implement a strict CSP to prevent XSS attacks
   - Disable inline scripts and styles
   - Use nonces or hashes for necessary inline scripts
   - Configure your CSP in `index.html`:

```html
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' api.artcafe.ai;">
```

2. **Data Sanitization**
   - Sanitize all user-generated content before rendering
   - Use React's built-in XSS protection (automatic HTML escaping)
   - For dangerouslySetInnerHTML, sanitize content with libraries like DOMPurify:

```typescript
import DOMPurify from 'dompurify';

const sanitizedHtml = DOMPurify.sanitize(userGeneratedContent);

<div dangerouslySetInnerHTML={{ __html: sanitizedHtml }} />;
```

3. **Output Encoding**
   - Encode user data in URL parameters
   - Use proper HTML entity encoding for dynamic content
   - Avoid concatenating unsanitized strings directly into HTML

### Secure Communication

1. **HTTPS Only**
   - Force HTTPS for all communication
   - Use HSTS headers to prevent downgrade attacks
   - Redirect HTTP to HTTPS automatically

2. **WebSocket Security**
   - Use secure WebSocket connections (WSS)
   - Include authentication token with each WebSocket connection
   - Implement message validation for all WebSocket messages
   - Close inactive WebSocket connections

3. **API Request Security**
   - Set appropriate CORS headers to restrict API access
   - Validate all input data before sending to API
   - Implement rate limiting on the client side

## SSH Key Management Security

### Key Generation & Storage

1. **Secure Key Generation**
   - Generate keys on the client machine, not on the server
   - Use strong key types (e.g., RSA 4096 or Ed25519)
   - Ensure proper entropy for key generation
   - Never transmit private keys over the network

2. **Key Storage Guidance**
   - Provide clear instructions for users to store private keys securely
   - Recommend password protection for private keys
   - Discourage sharing of private keys

### Key Rotation & Revocation

1. **Regular Key Rotation**
   - Implement a UI for key rotation
   - Encourage periodic key rotation (30-90 days)
   - Allow for overlapping valid keys during rotation periods

2. **Immediate Revocation**
   - Provide a simple mechanism to revoke compromised keys
   - Implement a blacklist of revoked keys
   - Ensure revocation propagates quickly across all services

3. **Audit Logging**
   - Log all key management operations
   - Include metadata (IP, timestamp, user agent)
   - Make logs available to administrators

## Secure Development Practices

### Dependency Management

1. **Regular Updates**
   - Regularly update dependencies
   - Use npm audit or similar tools
   - Configure dependabot or similar automated dependency updates

2. **Minimize Dependencies**
   - Limit third-party dependencies to reduce attack surface
   - Vet all new dependencies for security issues
   - Consider using lockfiles (yarn.lock, package-lock.json)

### Build & Deployment Security

1. **Build Process Security**
   - Implement integrity checks on build artifacts
   - Use subresource integrity (SRI) for external scripts
   - Sanitize environment variables during build

2. **Source Map Protection**
   - Do not expose source maps in production
   - If needed, host source maps in a restricted location

3. **Bundle Analysis**
   - Analyze bundles for unexpected or malicious code
   - Check for code splitting issues that might expose sensitive logic

## Runtime Security

### Error Handling & Logging

1. **Secure Error Handling**
   - Don't expose stack traces or sensitive info in error messages
   - Implement generic error messages for users
   - Log detailed error information server-side

```typescript
// Bad
const handleError = (err) => {
  alert(`Error: ${err.stack}`);
};

// Good
const handleError = (err) => {
  console.error('Application error:', err); // For debugging
  alertService.show('An error occurred. Please try again later.'); // For users
  logService.captureException(err); // For monitoring
};
```

2. **Logging Best Practices**
   - Never log sensitive information (tokens, passwords)
   - Use appropriate log levels
   - Implement secure log transmission and storage

### User Input Validation

1. **Frontend Validation**
   - Validate all user inputs on the client side
   - Implement strict type checking
   - Use libraries like Yup, Zod, or Joi for schema validation

```typescript
import * as yup from 'yup';

const schema = yup.object().shape({
  name: yup.string().required().min(2).max(50),
  email: yup.string().required().email(),
  role: yup.string().oneOf(['admin', 'user']),
});

const validateInput = async (data) => {
  try {
    await schema.validate(data);
    return { valid: true };
  } catch (err) {
    return { valid: false, error: err.message };
  }
};
```

2. **Defense in Depth**
   - Assume backend validation might fail
   - Implement multiple layers of validation
   - Validate response data before processing

## Multi-Tenant Frontend Architecture

### Tenant-Aware Components

1. **Component Isolation**
   - Design components to be tenant-aware
   - Avoid sharing state between tenant contexts
   - Use tenant-specific configuration

```typescript
const TenantAwareComponent = () => {
  const { currentTenant } = useTenant();
  
  // Load tenant-specific configuration
  const config = useTenantConfig(currentTenant.id);
  
  return (
    <div>
      <h2>{currentTenant.name}</h2>
      {/* Render tenant-specific UI */}
    </div>
  );
};
```

2. **Tenant-Based Rendering**
   - Implement conditional rendering based on tenant settings
   - Handle tenant-specific feature flags
   - Consider using Higher-Order Components for tenant context

```typescript
const withTenantFeatures = (Component) => {
  return (props) => {
    const { currentTenant } = useTenant();
    const tenantFeatures = useTenantFeatures(currentTenant.id);
    
    return (
      <Component 
        {...props} 
        features={tenantFeatures} 
        tenantId={currentTenant.id} 
      />
    );
  };
};

// Usage
const EnhancedDashboard = withTenantFeatures(Dashboard);
```

### Tenant-Aware Data Handling

1. **Data Prefixing**
   - Prefix all cached data with tenant IDs
   - Use separate cache stores for each tenant
   - Implement tenant-aware Redux selectors

```typescript
// Tenant-aware Redux selectors
const selectAgentsByTenant = (state, tenantId) => {
  return state.agents.entities.filter(agent => agent.tenantId === tenantId);
};

// Tenant-aware caching
const useTenantCache = (tenantId, key, fetchFn) => {
  const cacheKey = `tenant:${tenantId}:${key}`;
  // Use this cache key with your caching mechanism
};
```

2. **Tenant Switching Logic**
   - Clear caches when switching tenants
   - Re-fetch data for the new tenant context
   - Reset application state

```typescript
const switchTenant = async (newTenantId) => {
  // Clear any tenant-specific data
  dispatch(clearTenantData());
  
  // Update tenant in context
  await tenantService.setCurrentTenant(newTenantId);
  
  // Reload data for new tenant
  dispatch(fetchTenantData(newTenantId));
  
  // Update UI for new tenant
  history.push('/dashboard');
};
```

## Implementation Examples

### Secure Authentication Component

```typescript
// src/components/auth/SecureLogin.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as yup from 'yup';

const loginSchema = yup.object().shape({
  email: yup.string().required('Email is required').email('Invalid email format'),
  password: yup.string().required('Password is required').min(8, 'Password must be at least 8 characters'),
});

const SecureLogin = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  
  const validateForm = async () => {
    try {
      await loginSchema.validate({ email, password }, { abortEarly: false });
      return true;
    } catch (err) {
      const validationErrors = {};
      err.inner.forEach(error => {
        validationErrors[error.path] = error.message;
      });
      setErrors(validationErrors);
      return false;
    }
  };
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Clear previous errors
    setErrors({});
    
    // Validate form
    const isValid = await validateForm();
    if (!isValid) return;
    
    try {
      setLoading(true);
      
      // Call API with CSRF token
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'include', // Include cookies
        body: JSON.stringify({ email, password })
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || 'Authentication failed');
      }
      
      const data = await response.json();
      
      // Store token in memory (not localStorage)
      window.sessionStorage.setItem('accessTokenExpiry', data.expiresAt);
      
      // Update auth state using context
      authContext.setAuthState({
        isAuthenticated: true,
        user: data.user,
        // Store token in memory variable, not localStorage
        accessToken: data.accessToken
      });
      
      // Redirect to dashboard
      navigate('/dashboard');
      
    } catch (error) {
      setErrors({ general: error.message || 'Authentication failed' });
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <form onSubmit={handleSubmit} className="secure-login-form">
      {errors.general && (
        <div className="error-message">{errors.general}</div>
      )}
      
      <div className="form-group">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={errors.email ? 'input-error' : ''}
        />
        {errors.email && <div className="field-error">{errors.email}</div>}
      </div>
      
      <div className="form-group">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={errors.password ? 'input-error' : ''}
          autoComplete="current-password"
        />
        {errors.password && <div className="field-error">{errors.password}</div>}
      </div>
      
      <button 
        type="submit" 
        className="submit-button"
        disabled={loading}
      >
        {loading ? 'Logging in...' : 'Log In'}
      </button>
    </form>
  );
};

export default SecureLogin;
```

### Secure WebSocket Connection

```typescript
// src/services/secureWebSocket.ts
import { authService } from './auth';
import { logService } from './logging';

class SecureWebSocketService {
  private socket: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private messageHandlers: Record<string, Function[]> = {};
  
  connect() {
    const token = authService.getAccessToken();
    const tenantId = authService.getCurrentTenantId();
    
    if (!token || !tenantId) {
      logService.warn('Attempted to connect WebSocket without auth credentials');
      return;
    }
    
    // Use secure WebSocket connection
    this.socket = new WebSocket(`wss://api.artcafe.ai/ws`);
    
    this.socket.onopen = () => {
      // Reset reconnect attempts on successful connection
      this.reconnectAttempts = 0;
      
      // Send authentication message
      this.send('auth', {
        token,
        tenant_id: tenantId
      });
      
      // Log successful connection
      logService.info('WebSocket connected');
    };
    
    this.socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        
        // Validate message format
        if (!message.type || !message.id) {
          logService.warn('Invalid message format received', { message });
          return;
        }
        
        // Handle message
        this.handleMessage(message);
      } catch (err) {
        logService.error('Error handling WebSocket message', err);
      }
    };
    
    this.socket.onclose = (event) => {
      logService.info('WebSocket disconnected', { code: event.code });
      
      // Attempt to reconnect if not closed cleanly
      if (event.code !== 1000 && event.code !== 1001) {
        this.attemptReconnect();
      }
    };
    
    this.socket.onerror = (error) => {
      logService.error('WebSocket error', error);
    };
  }
  
  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      logService.error('Maximum WebSocket reconnect attempts reached');
      return;
    }
    
    // Exponential backoff
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    
    setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }
  
  send(type: string, data: any) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      logService.warn('Attempted to send message on closed WebSocket');
      return false;
    }
    
    try {
      // Add security fields
      const message = {
        type,
        id: crypto.randomUUID(),
        data,
        timestamp: new Date().toISOString(),
        tenant_id: authService.getCurrentTenantId()
      };
      
      this.socket.send(JSON.stringify(message));
      return true;
    } catch (err) {
      logService.error('Error sending WebSocket message', err);
      return false;
    }
  }
  
  on(messageType: string, handler: Function) {
    if (!this.messageHandlers[messageType]) {
      this.messageHandlers[messageType] = [];
    }
    
    this.messageHandlers[messageType].push(handler);
  }
  
  off(messageType: string, handler: Function) {
    if (!this.messageHandlers[messageType]) return;
    
    this.messageHandlers[messageType] = this.messageHandlers[messageType]
      .filter(h => h !== handler);
  }
  
  private handleMessage(message: any) {
    // Call appropriate handlers
    const handlers = this.messageHandlers[message.type] || [];
    
    handlers.forEach(handler => {
      try {
        handler(message);
      } catch (err) {
        logService.error('Error in WebSocket message handler', err);
      }
    });
  }
  
  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}

export const secureWebSocketService = new SecureWebSocketService();
```

### Secure API Client

```typescript
// src/services/secureApiClient.ts
import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { authService } from './auth';
import { logService } from './logging';

class SecureApiClient {
  private client: AxiosInstance;
  private tokenRefreshPromise: Promise<string> | null = null;
  
  constructor() {
    this.client = axios.create({
      baseURL: process.env.REACT_APP_API_URL,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      }
    });
    
    this.setupInterceptors();
  }
  
  private setupInterceptors() {
    // Request interceptor
    this.client.interceptors.request.use(
      (config) => {
        // Add CSRF token if available
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        if (csrfToken) {
          config.headers['X-CSRF-Token'] = csrfToken;
        }
        
        // Add auth token if available
        const token = authService.getAccessToken();
        if (token) {
          config.headers['Authorization'] = `Bearer ${token}`;
        }
        
        // Add tenant ID
        const tenantId = authService.getCurrentTenantId();
        if (tenantId) {
          config.headers['x-tenant-id'] = tenantId;
        }
        
        return config;
      },
      (error) => {
        logService.error('API request error', error);
        return Promise.reject(error);
      }
    );
    
    // Response interceptor
    this.client.interceptors.response.use(
      (response) => response,
      async (error) => {
        const originalRequest = error.config;
        
        // Handle token expiration
        if (error.response?.status === 401 && !originalRequest._retry) {
          if (this.tokenRefreshPromise === null) {
            this.tokenRefreshPromise = this.refreshToken();
          }
          
          try {
            const newToken = await this.tokenRefreshPromise;
            this.tokenRefreshPromise = null;
            
            if (newToken) {
              // Update request with new token
              originalRequest.headers['Authorization'] = `Bearer ${newToken}`;
              originalRequest._retry = true;
              return this.client(originalRequest);
            }
          } catch (refreshError) {
            this.tokenRefreshPromise = null;
            // Handle refresh failure - redirect to login
            authService.logout();
            window.location.href = '/login';
            return Promise.reject(refreshError);
          }
        }
        
        // Log other errors
        if (error.response?.status >= 500) {
          logService.error('API server error', {
            status: error.response.status,
            url: originalRequest.url,
            method: originalRequest.method
          });
        }
        
        return Promise.reject(error);
      }
    );
  }
  
  private async refreshToken(): Promise<string> {
    try {
      const response = await axios.post(
        `${process.env.REACT_APP_API_URL}/auth/refresh-token`,
        {},
        { withCredentials: true } // Include cookies
      );
      
      const newToken = response.data.access_token;
      authService.setAccessToken(newToken);
      
      return newToken;
    } catch (error) {
      logService.error('Token refresh failed', error);
      authService.logout();
      window.location.href = '/login';
      throw error;
    }
  }
  
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }
  
  async post<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }
  
  async put<T>(url: string, data?: any, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.put<T>(url, data, config);
    return response.data;
  }
  
  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config);
    return response.data;
  }
}

export const secureApiClient = new SecureApiClient();
```

## Security Testing Checklist

- [ ] Run client-side linters with security rules
- [ ] Check for vulnerable dependencies with npm audit
- [ ] Perform penetration testing on the frontend
- [ ] Use browser security plugins for testing
- [ ] Test CORS configuration
- [ ] Verify token storage and handling
- [ ] Check for leaked credentials in the build
- [ ] Test multi-tenant isolation
- [ ] Verify secure WebSocket connections

## Conclusion

Implementing these security best practices in your ArtCafe.ai frontend application will help protect your multi-tenant environment from common security threats. Remember that security is an ongoing process, and you should regularly review and update your security measures as new threats emerge.

Key security principles to follow:
- Implement defense in depth
- Never trust client-side security alone
- Test security features regularly
- Keep dependencies updated
- Log security events
- Implement proper error handling
- Follow the principle of least privilege

By adhering to these best practices, you'll create a secure frontend that protects your users' data while providing a seamless multi-tenant experience.