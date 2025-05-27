import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
import re
from fuzzywuzzy import fuzz

from api.db import dynamodb
from config.settings import settings

logger = logging.getLogger(__name__)

# Table names
SEARCH_INDEX_TABLE = "artcafe-search-index"
AGENTS_TABLE = settings.AGENT_TABLE_NAME
CHANNELS_TABLE = settings.CHANNEL_TABLE_NAME
ACTIVITY_TABLE = "artcafe-activity-logs"


class SearchService:
    """Service for search functionality"""
    
    async def search(
        self,
        tenant_id: str,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50
    ) -> Dict[str, List[Any]]:
        """
        Search across multiple resources
        
        Args:
            tenant_id: Tenant ID
            query: Search query
            filters: Optional filters (resource_type, date_range, etc.)
            limit: Maximum results per category
            
        Returns:
            Dictionary with results by category
        """
        try:
            query = query.lower().strip()
            results = {
                "agents": [],
                "channels": [],
                "activities": [],
                "total_count": 0
            }
            
            # Search agents
            if not filters or filters.get("resource_type") in [None, "agent"]:
                agents = await self._search_agents(tenant_id, query, limit)
                results["agents"] = agents
                results["total_count"] += len(agents)
            
            # Search channels
            if not filters or filters.get("resource_type") in [None, "channel"]:
                channels = await self._search_channels(tenant_id, query, limit)
                results["channels"] = channels
                results["total_count"] += len(channels)
            
            # Search activities
            if not filters or filters.get("resource_type") in [None, "activity"]:
                activities = await self._search_activities(tenant_id, query, limit, filters)
                results["activities"] = activities
                results["total_count"] += len(activities)
            
            # Update search index for analytics
            await self._update_search_index(tenant_id, query)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching: {e}")
            return {"agents": [], "channels": [], "activities": [], "total_count": 0}
    
    async def _search_agents(self, tenant_id: str, query: str, limit: int) -> List[Dict]:
        """Search agents by name, description, or tags"""
        try:
            # Get all agents for tenant
            result = await dynamodb.query(
                table_name=AGENTS_TABLE,
                key_condition_expression="tenant_id = :tenant_id",
                expression_attribute_values={":tenant_id": tenant_id},
                limit=200  # Get more to filter
            )
            
            agents = result.get("items", [])
            scored_agents = []
            
            # Score each agent
            for agent in agents:
                score = 0
                
                # Check name
                if agent.get("name"):
                    name_score = fuzz.partial_ratio(query, agent["name"].lower())
                    score = max(score, name_score)
                
                # Check description
                if agent.get("description"):
                    desc_score = fuzz.partial_ratio(query, agent["description"].lower())
                    score = max(score, desc_score * 0.8)  # Weight description slightly lower
                
                # Check tags
                tags = agent.get("metadata", {}).get("tags", [])
                for tag in tags:
                    tag_score = fuzz.ratio(query, tag.lower())
                    score = max(score, tag_score * 0.9)
                
                # Check ID (exact match gets high score)
                if query in agent.get("id", "").lower():
                    score = 100
                
                if score > 40:  # Threshold for relevance
                    scored_agents.append({
                        "score": score,
                        "type": "agent",
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "description": agent.get("description"),
                        "status": agent.get("status"),
                        "created_at": agent.get("created_at"),
                        "tags": tags
                    })
            
            # Sort by score and return top results
            scored_agents.sort(key=lambda x: x["score"], reverse=True)
            return scored_agents[:limit]
            
        except Exception as e:
            logger.error(f"Error searching agents: {e}")
            return []
    
    async def _search_channels(self, tenant_id: str, query: str, limit: int) -> List[Dict]:
        """Search channels by name or description"""
        try:
            # Get all channels for tenant
            result = await dynamodb.query(
                table_name=CHANNELS_TABLE,
                key_condition_expression="tenant_id = :tenant_id",
                expression_attribute_values={":tenant_id": tenant_id},
                limit=200
            )
            
            channels = result.get("items", [])
            scored_channels = []
            
            # Score each channel
            for channel in channels:
                score = 0
                
                # Check name
                if channel.get("name"):
                    name_score = fuzz.partial_ratio(query, channel["name"].lower())
                    score = max(score, name_score)
                
                # Check description
                if channel.get("description"):
                    desc_score = fuzz.partial_ratio(query, channel["description"].lower())
                    score = max(score, desc_score * 0.8)
                
                # Check ID
                if query in channel.get("id", "").lower():
                    score = 100
                
                if score > 40:
                    scored_channels.append({
                        "score": score,
                        "type": "channel",
                        "id": channel.get("id"),
                        "name": channel.get("name"),
                        "description": channel.get("description"),
                        "type": channel.get("type"),
                        "created_at": channel.get("created_at")
                    })
            
            scored_channels.sort(key=lambda x: x["score"], reverse=True)
            return scored_channels[:limit]
            
        except Exception as e:
            logger.error(f"Error searching channels: {e}")
            return []
    
    async def _search_activities(
        self, 
        tenant_id: str, 
        query: str, 
        limit: int,
        filters: Optional[Dict] = None
    ) -> List[Dict]:
        """Search activities by message or action"""
        try:
            # Build date range filter
            if filters and filters.get("date_range"):
                start_date = filters["date_range"].get("start")
                end_date = filters["date_range"].get("end")
            else:
                # Default to last 7 days
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=7)
            
            # Query activities
            result = await dynamodb.query(
                table_name=ACTIVITY_TABLE,
                key_condition_expression="tenant_id = :tenant_id AND timestamp_activity_id BETWEEN :start AND :end",
                expression_attribute_values={
                    ":tenant_id": tenant_id,
                    ":start": start_date.isoformat(),
                    ":end": end_date.isoformat() + "~"
                },
                scan_index_forward=False,
                limit=500  # Get more to filter
            )
            
            activities = result.get("items", [])
            scored_activities = []
            
            # Score each activity
            for activity in activities:
                score = 0
                
                # Check message
                if activity.get("message"):
                    msg_score = fuzz.partial_ratio(query, activity["message"].lower())
                    score = max(score, msg_score)
                
                # Check action
                if activity.get("action"):
                    action_score = fuzz.partial_ratio(query, activity["action"].lower())
                    score = max(score, action_score * 0.9)
                
                # Check activity type
                if query in activity.get("activity_type", "").lower():
                    score = max(score, 80)
                
                # Check related IDs
                for field in ["agent_id", "channel_id", "resource_id"]:
                    if activity.get(field) and query in activity[field].lower():
                        score = max(score, 70)
                
                if score > 30:  # Lower threshold for activities
                    scored_activities.append({
                        "score": score,
                        "type": "activity",
                        "id": activity.get("activity_id"),
                        "activity_type": activity.get("activity_type"),
                        "action": activity.get("action"),
                        "message": activity.get("message"),
                        "status": activity.get("status"),
                        "created_at": activity.get("created_at"),
                        "agent_id": activity.get("agent_id"),
                        "channel_id": activity.get("channel_id")
                    })
            
            scored_activities.sort(key=lambda x: x["score"], reverse=True)
            return scored_activities[:limit]
            
        except Exception as e:
            logger.error(f"Error searching activities: {e}")
            return []
    
    async def _update_search_index(self, tenant_id: str, query: str):
        """Update search index for analytics"""
        try:
            # Record search query for analytics
            search_key = f"search#{datetime.utcnow().isoformat()}#{query[:50]}"
            
            await dynamodb.put_item(
                table_name=SEARCH_INDEX_TABLE,
                item={
                    "tenant_id": tenant_id,
                    "search_key": search_key,
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat(),
                    "ttl": int((datetime.utcnow() + timedelta(days=30)).timestamp())
                }
            )
        except Exception as e:
            logger.error(f"Error updating search index: {e}")
    
    async def get_popular_searches(self, tenant_id: str, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get popular search queries"""
        try:
            # Query recent searches
            start_key = f"search#{(datetime.utcnow() - timedelta(days=days)).isoformat()}"
            end_key = f"search#{datetime.utcnow().isoformat()}~"
            
            result = await dynamodb.query(
                table_name=SEARCH_INDEX_TABLE,
                key_condition_expression="tenant_id = :tenant_id AND search_key BETWEEN :start AND :end",
                expression_attribute_values={
                    ":tenant_id": tenant_id,
                    ":start": start_key,
                    ":end": end_key
                },
                limit=1000
            )
            
            # Count queries
            query_counts = {}
            for item in result.get("items", []):
                query = item.get("query", "").lower()
                query_counts[query] = query_counts.get(query, 0) + 1
            
            # Sort by count
            popular = sorted(query_counts.items(), key=lambda x: x[1], reverse=True)
            
            return [
                {"query": query, "count": count}
                for query, count in popular[:limit]
            ]
            
        except Exception as e:
            logger.error(f"Error getting popular searches: {e}")
            return []
    
    async def get_search_suggestions(self, tenant_id: str, prefix: str, limit: int = 5) -> List[str]:
        """Get search suggestions based on prefix"""
        try:
            # Get recent popular searches
            popular = await self.get_popular_searches(tenant_id, days=30, limit=50)
            
            # Filter by prefix
            suggestions = []
            prefix_lower = prefix.lower()
            
            for item in popular:
                query = item["query"]
                if query.startswith(prefix_lower):
                    suggestions.append(query)
                    if len(suggestions) >= limit:
                        break
            
            # If not enough suggestions, add common terms
            if len(suggestions) < limit:
                common_terms = ["agent", "channel", "error", "connected", "message", "task"]
                for term in common_terms:
                    if term.startswith(prefix_lower) and term not in suggestions:
                        suggestions.append(term)
                        if len(suggestions) >= limit:
                            break
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return []


# Create singleton instance
search_service = SearchService()