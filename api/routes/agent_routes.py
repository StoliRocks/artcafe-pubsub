from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from auth import get_current_tenant_id
from models import AgentCreate, AgentUpdate

# Response models for agents
from pydantic import BaseModel, Field
from typing import List, Dict, Any

class AgentResponse(BaseModel):
    """Response for single agent"""
    agent: Dict[str, Any]

class AgentsResponse(BaseModel):
    """Response for agent list"""
    agents: List[Dict[str, Any]]
    next_token: Optional[str] = None

class AgentCreateResponse(BaseModel):
    """Response for agent creation"""
    agent: Dict[str, Any]
    nkey_seed: Optional[str] = None
    warning: Optional[str] = None


from api.services import agent_nkey_service, usage_service
from api.services.heartbeat_service import heartbeat_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=AgentsResponse)
async def list_agents(
    tenant_id: str = Depends(get_current_tenant_id),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, description="Maximum number of results"),
    next_token: Optional[str] = Query(None, description="Pagination token")
):
    """
    List agents for a tenant
    
    Returns:
        List of agents
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get agents from agent service
    result = await agent_nkey_service.list_agents(
        tenant_id=tenant_id,
        status=status,
        limit=limit
    )
    
    # Handle response - could be a list or dict
    if isinstance(result, list):
        agents_list = result
    else:
        agents_list = result.get("agents", [])
    
    # Convert Agent objects to dicts and add type field for frontend
    formatted_agents = []
    for agent in agents_list:
        # Convert to dict if it's a model object
        if hasattr(agent, 'dict'):
            agent_dict = agent.dict()
        elif hasattr(agent, 'model_dump'):
            agent_dict = agent.model_dump()
        else:
            agent_dict = agent if isinstance(agent, dict) else vars(agent)
        
        # Add type field for frontend
        agent_dict["type"] = agent_dict.get("auth_type", "ssh")  # default to ssh for existing agents
        
        # Get real-time status from heartbeat service
        agent_id = agent_dict.get("agent_id")
        if agent_id:
            status_info = await heartbeat_service.get_agent_status(tenant_id, agent_id)
            agent_dict["status"] = status_info.get("status", "offline")
            agent_dict["last_seen"] = status_info.get("last_heartbeat")
        
        formatted_agents.append(agent_dict)
    
    return AgentsResponse(
        agents=formatted_agents,
        next_token=result.get("next_token") if isinstance(result, dict) else None
    )


@router.get("/status/summary")
async def get_agents_status_summary(
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get real-time agent status summary for dashboard.
    Optimized for performance using Redis cache.
    """
    try:
        # Get online count from ultra-fast cache
        online_count = await heartbeat_service.get_online_agents_count(tenant_id)
        
        # Get total agents from DB
        result = await agent_nkey_service.list_agents(tenant_id=tenant_id, limit=1000)
        total_count = len(result) if isinstance(result, list) else len(result.get("agents", []))
        
        return {
            "total_agents": total_count,
            "online_agents": online_count,
            "offline_agents": total_count - online_count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting agent status summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get agent status"
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str = Path(..., description="Agent ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Get agent by ID
    
    Args:
        agent_id: Agent ID
        
    Returns:
        Agent details
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Get agent
    agent = await agent_nkey_service.get_agent(tenant_id, agent_id)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
        
    return AgentResponse(agent=agent)


@router.post("", response_model=AgentCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent_data: AgentCreate,
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Create a new agent
    
    Args:
        agent_data: Agent data
        
    Returns:
        Created agent with private key if generated
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Create agent
    agent, private_key = await agent_nkey_service.create_agent(tenant_id, agent_data)
    
    return AgentCreateResponse(agent=agent, private_key=private_key)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_data: AgentUpdate,
    agent_id: str = Path(..., description="Agent ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Update an agent
    
    Args:
        agent_id: Agent ID
        agent_data: Agent update data
        
    Returns:
        Updated agent
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Update agent
    agent = await agent_nkey_service.update_agent(tenant_id, agent_id, agent_data)
    
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
        
    return AgentResponse(agent=agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str = Path(..., description="Agent ID"),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Delete an agent
    
    Args:
        agent_id: Agent ID
    """
    # Track API call
    await usage_service.increment_api_calls(tenant_id)
    
    # Delete agent
    success = await agent_nkey_service.delete_agent(tenant_id, agent_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
        
    return  # No content for 204