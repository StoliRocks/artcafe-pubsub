from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, validator

from .base import BaseSchema


class MetricType(str):
    """Metric types"""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    NETWORK_IN = "network_in"
    NETWORK_OUT = "network_out"
    TASKS_PROCESSED = "tasks_processed"
    TASKS_FAILED = "tasks_failed"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    UPTIME = "uptime"


class AgentMetrics(BaseSchema):
    """Agent metrics model"""
    tenant_agent_id: str  # Composite key: tenant_id#agent_id
    timestamp: int  # Unix timestamp for sort key
    
    # Core metrics (percentages 0-100)
    cpu_usage: Optional[float] = Field(None, ge=0, le=100)
    memory_usage: Optional[float] = Field(None, ge=0, le=100)
    disk_usage: Optional[float] = Field(None, ge=0, le=100)
    
    # Network metrics (bytes)
    network_in: Optional[int] = Field(None, ge=0)
    network_out: Optional[int] = Field(None, ge=0)
    
    # Task metrics
    tasks_processed: Optional[int] = Field(None, ge=0)
    tasks_failed: Optional[int] = Field(None, ge=0)
    tasks_queued: Optional[int] = Field(None, ge=0)
    
    # Performance metrics
    error_rate: Optional[float] = Field(None, ge=0, le=100)
    response_time: Optional[float] = Field(None, ge=0)  # milliseconds
    
    # System info
    uptime: Optional[int] = Field(None, ge=0)  # seconds
    last_restart: Optional[datetime] = None
    
    # Process info
    process_count: Optional[int] = Field(None, ge=0)
    thread_count: Optional[int] = Field(None, ge=0)
    open_file_descriptors: Optional[int] = Field(None, ge=0)
    
    # Custom metrics
    custom_metrics: Optional[Dict[str, Any]] = {}
    
    # TTL for auto-deletion (7 days)
    ttl: Optional[int] = None
    
    @validator('timestamp', pre=True, always=True)
    def set_timestamp(cls, v, values):
        """Ensure timestamp is set"""
        if v:
            return v
        return int(datetime.utcnow().timestamp())
    
    @validator('ttl', pre=True, always=True)
    def set_ttl(cls, v, values):
        """Set TTL to 7 days from creation"""
        if v:
            return v
        
        # Use timestamp if available, otherwise current time
        base_time = values.get('timestamp', int(datetime.utcnow().timestamp()))
        # 7 days in seconds
        return base_time + (7 * 24 * 60 * 60)


class AgentMetricsCreate(BaseModel):
    """Agent metrics creation model"""
    agent_id: str
    
    # Core metrics
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    disk_usage: Optional[float] = None
    
    # Network metrics
    network_in: Optional[int] = None
    network_out: Optional[int] = None
    
    # Task metrics
    tasks_processed: Optional[int] = None
    tasks_failed: Optional[int] = None
    tasks_queued: Optional[int] = None
    
    # Performance metrics
    error_rate: Optional[float] = None
    response_time: Optional[float] = None
    
    # System info
    uptime: Optional[int] = None
    last_restart: Optional[datetime] = None
    
    # Process info
    process_count: Optional[int] = None
    thread_count: Optional[int] = None
    open_file_descriptors: Optional[int] = None
    
    # Custom metrics
    custom_metrics: Optional[Dict[str, Any]] = {}


class AgentMetricsSummary(BaseModel):
    """Agent metrics summary"""
    agent_id: str
    tenant_id: str
    
    # Current metrics (latest values)
    current_metrics: Optional[AgentMetrics] = None
    
    # Averages over time period
    avg_cpu_usage: Optional[float] = None
    avg_memory_usage: Optional[float] = None
    avg_disk_usage: Optional[float] = None
    avg_response_time: Optional[float] = None
    
    # Totals over time period
    total_tasks_processed: int = 0
    total_tasks_failed: int = 0
    total_network_in: int = 0
    total_network_out: int = 0
    
    # Min/Max values
    max_cpu_usage: Optional[float] = None
    max_memory_usage: Optional[float] = None
    min_response_time: Optional[float] = None
    max_response_time: Optional[float] = None
    
    # Time period info
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    data_points: int = 0
    
    # Health indicators
    health_score: Optional[float] = Field(None, ge=0, le=100)
    availability_percentage: Optional[float] = Field(None, ge=0, le=100)
    error_percentage: Optional[float] = Field(None, ge=0, le=100)


class MetricsAggregation(BaseModel):
    """Metrics aggregation for multiple agents"""
    tenant_id: str
    
    # Aggregate metrics
    total_agents: int = 0
    active_agents: int = 0
    
    # System-wide metrics
    total_cpu_usage: float = 0
    total_memory_usage: float = 0
    total_disk_usage: float = 0
    
    # Network totals
    total_network_in: int = 0
    total_network_out: int = 0
    
    # Task totals
    total_tasks_processed: int = 0
    total_tasks_failed: int = 0
    total_tasks_queued: int = 0
    
    # Average metrics
    avg_cpu_per_agent: float = 0
    avg_memory_per_agent: float = 0
    avg_response_time: float = 0
    
    # Health summary
    healthy_agents: int = 0
    warning_agents: int = 0
    critical_agents: int = 0
    
    # Time period
    period_start: datetime
    period_end: datetime