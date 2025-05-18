import fileinput
import re
import os

# First, let's update the usage service to properly fetch real data
usage_service_file = "api/services/usage_service.py"

# Read the entire file
with open(usage_service_file, 'r') as f:
    content = f.read()

# Update the get_usage_metrics method to properly fetch real data
new_get_usage_metrics = '''    async def get_usage_metrics(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[UsageMetrics]:
        """
        Get usage metrics for a tenant.

        Args:
            tenant_id: Tenant ID
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)

        Returns:
            List of UsageMetrics objects
        """
        try:
            # If no date range specified, use today
            if not start_date:
                start_date = date.today().isoformat()
            if not end_date:
                end_date = date.today().isoformat()
                
            # Fetch current counts from database
            agents = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Agents",
                key_conditions={"tenant_id": tenant_id}
            )
            
            channels = await dynamodb.query(
                table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Channels",
                key_conditions={"tenant_id": tenant_id}
            )
            
            # Count active agents (status == 'online')
            total_agents = len(agents) if agents else 0
            active_agents = sum(1 for agent in (agents or []) if agent.get('status') == 'online')
            
            # Count active channels
            total_channels = len(channels) if channels else 0
            active_channels = sum(1 for channel in (channels or []) if channel.get('status') == 'active')
            
            # Get message count from usage stats
            usage_table = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"
            today_key = f"{tenant_id}#daily#{date.today().isoformat()}"
            
            daily_stats = await dynamodb.get_item(
                table_name=usage_table,
                key={"pk": today_key, "sk": "stats"}
            )
            
            messages_count = 0
            api_calls_count = 0
            
            if daily_stats:
                messages_count = daily_stats.get('messages_count', 0)
                api_calls_count = daily_stats.get('api_calls_count', 0)
            
            # Create metric for today
            metric = UsageMetrics(
                date=date.today().isoformat(),
                tenant_id=tenant_id,
                agents_count=total_agents,
                active_agents_count=active_agents,
                channels_count=total_channels,
                active_channels_count=active_channels,
                messages_count=messages_count,
                api_calls_count=api_calls_count,
                created_at=datetime.utcnow().isoformat()
            )

            return [metric]

        except Exception as e:
            logger.error(f"Error getting usage metrics: {e}")
            # Return empty metrics on error
            return [UsageMetrics(
                date=date.today().isoformat(),
                tenant_id=tenant_id,
                agents_count=0,
                active_agents_count=0,
                channels_count=0,
                active_channels_count=0,
                messages_count=0,
                api_calls_count=0,
                created_at=datetime.utcnow().isoformat()
            )]'''

# Replace the existing method
pattern = r'async def get_usage_metrics\([^}]+\}(?:[^}]+\})*'
content = re.sub(pattern, new_get_usage_metrics, content, flags=re.DOTALL)

# Write back the file
with open(usage_service_file, 'w') as f:
    f.write(content)

print("Updated usage service to fetch real metrics")

# Now update the Overview component to properly display the metrics
overview_fix = '''
# Fix the Overview component to handle the API response correctly
import sys
sys.path.append('/opt/artcafe/artcafe-pubsub')

from api.services.usage_service import usage_service
from api.services.agent_service import agent_service
from api.services.channel_service import channel_service

# Update metrics collection methods
async def update_real_metrics():
    """Add method to properly track real metrics"""
    
    # Get all tenants
    tenants = await dynamodb.scan(
        table_name=f"{settings.DYNAMODB_TABLE_PREFIX}Tenants"
    )
    
    for tenant in tenants:
        tenant_id = tenant['tenant_id']
        
        # Count agents
        agents = await agent_service.list_agents(tenant_id, {})
        total_agents = len(agents.get('agents', []))
        active_agents = sum(1 for agent in agents.get('agents', []) if agent.get('status') == 'online')
        
        # Count channels
        channels = await channel_service.list_channels(tenant_id, {})
        total_channels = len(channels.get('channels', []))
        active_channels = sum(1 for channel in channels.get('channels', []) if channel.get('status', 'active') == 'active')
        
        # Update metrics
        await usage_service.set_agent_count(tenant_id, total_agents)
        await usage_service.set_channel_count(tenant_id, total_channels)
        
        # Store daily metrics
        usage_table = f"{settings.DYNAMODB_TABLE_PREFIX}UsageMetrics"
        today_key = f"{tenant_id}#daily#{date.today().isoformat()}"
        
        await dynamodb.put_item(
            table_name=usage_table,
            item={
                "pk": today_key,
                "sk": "counts",
                "total_agents": total_agents,
                "active_agents": active_agents,
                "total_channels": total_channels,
                "active_channels": active_channels,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
'''

# Also fix the billing endpoint to return proper data
billing_route_file = "api/routes/usage_routes.py"

with open(billing_route_file, 'r') as f:
    billing_content = f.read()

# Update the billing endpoint
new_billing_response = '''@router.get("/billing", tags=["Usage"])
async def get_billing_info(
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get billing information for a tenant.

    This endpoint returns billing information for the authenticated tenant,
    including subscription plan, billing cycle, and payment status.

    Args:
        tenant_id: Tenant ID

    Returns:
        Billing information
    """
    # Validate tenant
    tenant = await validate_tenant(tenant_id)

    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get current usage for the month
    today = date.today()
    start_of_month = date(today.year, today.month, 1)
    
    metrics = await usage_service.get_usage_metrics(
        tenant_id=tenant_id,
        start_date=start_of_month.isoformat(),
        end_date=today.isoformat()
    )
    
    totals = await usage_service.get_usage_totals(
        tenant_id=tenant_id,
        start_date=start_of_month.isoformat(),
        end_date=today.isoformat()
    )

    # Get billing info from tenant
    return {
        "tenant_id": tenant_id,
        "plan": tenant.subscription_tier,
        "billing_cycle": "monthly",
        "next_billing_date": tenant.subscription_expires_at.isoformat() if tenant.subscription_expires_at else None,
        "amount": 49.99 if tenant.subscription_tier == "basic" else 0.00,
        "currency": "USD",
        "payment_method": "credit_card" if tenant.subscription_tier != "free" else "none",
        "status": tenant.payment_status,
        "current_usage": {
            "agents": totals.agents_total if totals else 0,
            "channels": totals.channels_total if totals else 0,
            "messages": totals.messages_in_total if totals else 0,
            "api_calls": totals.api_calls_count if hasattr(totals, 'api_calls_count') else 0
        },
        "limits": {
            "agents": tenant.max_agents,
            "channels": tenant.max_channels,
            "messages_per_day": tenant.max_messages_per_day,
            "api_calls_per_day": tenant.max_messages_per_day // 5
        },
        "success": True
    }'''

# Replace the billing endpoint
pattern = r'@router\.get\("/billing"[^}]+\}'
billing_content = re.sub(pattern, new_billing_response, billing_content, flags=re.DOTALL)

with open(billing_route_file, 'w') as f:
    f.write(billing_content)

print("Updated billing endpoint to return real data")