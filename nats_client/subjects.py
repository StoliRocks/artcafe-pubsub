"""NATS subject naming conventions for ArtCafe pub/sub"""


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