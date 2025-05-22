"""NATS subject naming conventions for ArtCafe pub/sub"""

from typing import Optional


# Legacy subject patterns (for backward compatibility)

def get_tenant_subject(tenant_id: str) -> str:
    """Get base subject for a tenant"""
    return f"tenant.{tenant_id}"


def get_agent_subject(tenant_id: str, agent_id: str) -> str:
    """Get subject for a specific agent"""
    return f"tenant.{tenant_id}.agent.{agent_id}"


def get_agents_subject(tenant_id: str) -> str:
    """Get subject for all agents in a tenant"""
    return f"tenant.{tenant_id}.agent.>"


def get_channel_subject(tenant_id: str, channel_id: str) -> str:
    """Get subject for a specific channel"""
    return f"tenant.{tenant_id}.channel.{channel_id}"


def get_channels_subject(tenant_id: str) -> str:
    """Get subject for all channels in a tenant"""
    return f"tenant.{tenant_id}.channel.>"


def get_ssh_key_subject(tenant_id: str, key_id: str) -> str:
    """Get subject for a specific SSH key"""
    return f"tenant.{tenant_id}.key.{key_id}"


def get_ssh_keys_subject(tenant_id: str) -> str:
    """Get subject for all SSH keys in a tenant"""
    return f"tenant.{tenant_id}.key.>"


# New hierarchical subject patterns for agent protocol

def get_agent_task_subject(tenant_id: str, capability: str, specificity: str = "general") -> str:
    """Get subject for agent tasks requiring specific capability"""
    return f"agents.{tenant_id}.task.{capability}.{specificity}"


def get_agent_result_subject(tenant_id: str, agent_id: str, task_type: str = "general") -> str:
    """Get subject for agent results"""
    return f"agents.{tenant_id}.result.{agent_id}.{task_type}"


def get_agent_event_subject(tenant_id: str, event_type: str, specificity: Optional[str] = None) -> str:
    """Get subject for agent events"""
    if specificity:
        return f"agents.{tenant_id}.event.{event_type}.{specificity}"
    return f"agents.{tenant_id}.event.{event_type}"


def get_agent_query_subject(tenant_id: str, query_type: str = "general") -> str:
    """Get subject for agent queries"""
    return f"agents.{tenant_id}.query.{query_type}"


def get_agent_stream_subject(tenant_id: str, stream_id: str) -> str:
    """Get subject for streaming responses"""
    return f"agents.{tenant_id}.stream.response.{stream_id}"


def get_agent_command_subject(tenant_id: str, agent_id: Optional[str] = None) -> str:
    """Get subject for agent commands"""
    if agent_id:
        return f"agents.{tenant_id}.command.{agent_id}"
    return f"agents.{tenant_id}.command.broadcast"


def get_agent_heartbeat_subject(tenant_id: str) -> str:
    """Get subject for agent heartbeats"""
    return f"agents.{tenant_id}.heartbeat"


def get_agent_discovery_request_subject(tenant_id: str) -> str:
    """Get subject for agent discovery requests"""
    return f"agents.{tenant_id}.discovery.requests"


def get_agent_discovery_response_subject(tenant_id: str, discovery_id: str) -> str:
    """Get subject for agent discovery responses"""
    return f"agents.{tenant_id}.discovery.responses.{discovery_id}"


def get_agent_negotiation_subject(tenant_id: str, agent_id: str) -> str:
    """Get subject for agent-to-agent negotiations"""
    return f"agents.{tenant_id}.negotiation.{agent_id}"


def get_all_agent_subjects(tenant_id: str) -> str:
    """Get wildcard subject for all agent messages in a tenant"""
    return f"agents.{tenant_id}.>"


def get_capability_subject(tenant_id: str, capability: str) -> str:
    """Get wildcard subject for all messages related to a capability"""
    return f"agents.{tenant_id}.*.{capability}.>"