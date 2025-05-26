# DynamoDB Tables Documentation

Last Updated: May 24, 2025

## Active Tables

### artcafe-agents
**Purpose**: Stores all agent configurations and metadata
- **Primary Key**: `tenant_id` (partition), `id` (sort)
- **Contains**: Agent name, description, public_key, capabilities, status, created/updated timestamps
- **Used by**: Agent service for CRUD operations, agent authentication
- **Note**: Public SSH keys are stored directly in agent records (no separate SSH key table needed)

### artcafe-tenants
**Purpose**: Stores tenant (organization) information
- **Primary Key**: `id`
- **Contains**: Tenant name, plan, limits, created/updated timestamps
- **Used by**: Tenant service, multi-tenancy authorization

### artcafe-user-tenants
**Purpose**: Maps users to tenants (many-to-many relationship)
- **Primary Key**: `user_id` (partition), `tenant_id` (sort)
- **Contains**: User-tenant associations, role, joined timestamp
- **Used by**: Authorization system to determine which tenants a user can access

### artcafe-user-tenant-index
**Purpose**: Reverse index for user-tenant lookups
- **Primary Key**: `tenant_id` (partition), `user_id` (sort)
- **Contains**: Same data as user-tenants but indexed differently
- **Used by**: Quickly find all users in a tenant
- **Note**: Has 20 items as of May 2025

### artcafe-channels
**Purpose**: Stores messaging channels for pub/sub communication
- **Primary Key**: `tenant_id` (partition), `id` (sort)
- **Contains**: Channel name, description, type, created/updated timestamps
- **Used by**: Channel service for agent communication routing

### artcafe-channel-subscriptions
**Purpose**: Tracks which agents are subscribed to which channels
- **Primary Key**: `tenant_id` (partition), `id` (sort)
- **Contains**: Channel ID, agent ID, subscription status
- **Used by**: Message routing system to determine message delivery

### artcafe-usage-metrics
**Purpose**: Tracks resource usage for billing and limits
- **Primary Key**: `tenant_id` (partition), `metric_id` (sort)
- **Contains**: Metric name, value, timestamp, period
- **Used by**: Usage service for tracking agent count, message volume, etc.

### artcafe-terms-acceptance
**Purpose**: Records legal terms acceptance by users
- **Primary Key**: `user_id` (partition), `version` (sort)
- **Contains**: Terms version, acceptance timestamp, IP address
- **Used by**: Legal compliance tracking

## Development Tables

### artcafe-agents-dev
**Purpose**: Development environment agents table
- **Structure**: Same as artcafe-agents
- **Used by**: Development and testing

### artcafe-tenants-dev
**Purpose**: Development environment tenants table
- **Structure**: Same as artcafe-tenants
- **Used by**: Development and testing

### artcafe-channels-dev
**Purpose**: Development environment channels table
- **Structure**: Same as artcafe-channels
- **Used by**: Development and testing

### artcafe-usage-metrics-dev
**Purpose**: Development environment usage metrics
- **Structure**: Same as artcafe-usage-metrics
- **Used by**: Development and testing

### artcafe-Challenges
**Purpose**: Temporary storage for authentication challenges
- **Primary Key**: `challenge_id` 
- **Contains**: Challenge string, tenant_id, agent_id, expiration timestamps
- **TTL**: 5 minutes (automatic cleanup via DynamoDB TTL on `ttl` attribute)
- **Used by**: SSH authentication flow for agent login
- **Note**: Created May 25, 2025 to support multi-server scaling

## Deleted Tables (May 24, 2025)

The following tables were deleted as they were unused:
- `artcafe-ssh-keys` - SSH keys are stored in agent records
- `artcafe-subscribers` - Replaced by channel-subscriptions
- `artcafe-subscriptions` - Replaced by channel-subscriptions
- `artcafe-organizations` - Using tenants table instead
- `artcafe-users` - User management via AWS Cognito
- `artcafe-user-tenants-index` - Typo, replaced by user-tenant-index
- `artcafe-ssh-keys-dev` - Not needed

Note: `artcafe-Challenges` was initially deleted but recreated on May 25, 2025 for proper multi-server support.

## Table Usage Patterns

### Multi-Tenancy
All primary tables use `tenant_id` as the partition key to ensure data isolation between tenants.

### Authentication Flow
1. User authenticates via Cognito (JWT)
2. JWT contains user_id
3. user-tenants table maps user to allowed tenants
4. All queries include tenant_id for isolation

### Agent Authentication
1. Agent stores public key in agent record
2. Challenge-response auth using SSH key
3. No separate SSH key table needed

### Message Routing
1. Agents subscribe to channels via channel-subscriptions
2. Messages published to channels
3. System routes to all subscribed agents in tenant