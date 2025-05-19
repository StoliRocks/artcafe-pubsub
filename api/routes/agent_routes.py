from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from auth import get_current_tenant_id
from models import AgentCreate, AgentUpdate, AgentResponse, AgentCreateResponse, AgentsResponse
from api.services import agent_service, usage_service

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
    
    # Get agents
    result = await agent_service.list_agents(
        tenant_id=tenant_id,
        status=status,
        limit=limit,
        next_token=next_token
    )
    
    return AgentsResponse(
        agents=result["agents"],
        next_token=result["next_token"]
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
    agent = await agent_service.get_agent(tenant_id, agent_id)
    
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
    agent, private_key = await agent_service.create_agent(tenant_id, agent_data)
    
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
    agent = await agent_service.update_agent(tenant_id, agent_id, agent_data)
    
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
    success = await agent_service.delete_agent(tenant_id, agent_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )
        
    return  # No content for 204