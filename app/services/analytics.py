from datetime import datetime
import json
from typing import Dict, List, Optional
from app.services.redis import redis_client, is_redis_available
from app.utils.logger import logger

class AnalyticsService:
    def __init__(self):
        self.redis_available = is_redis_available()
        if not self.redis_available:
            logger.warning("⚠️  Redis not available - analytics will use in-memory storage only")
            self.memory_events = []
    
    def _ensure_redis(self) -> bool:
        """Check if Redis is available"""
        return is_redis_available()
    
    def track_event(self, event_type: str, user_id: Optional[str] = None, metadata: Optional[Dict] = None):
        """Track an event and store it"""
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'metadata': metadata or {}
        }
        
        try:
            if self._ensure_redis():
                # Store in Redis with 30-day expiration
                event_key = f"paperbrain:analytics:event:{datetime.utcnow().timestamp()}"
                redis_client.setex(event_key, 86400 * 30, json.dumps(event))
            else:
                # Store in memory (volatile)
                self.memory_events.append(event)
                # Keep only last 1000 events in memory
                if len(self.memory_events) > 1000:
                    self.memory_events = self.memory_events[-1000:]
                    
        except Exception as e:
            logger.error(f"Failed to store analytics event: {e}")
        
        logger.info(f"Analytics event: {event_type} - User: {user_id}")
    
    def get_events(self, limit: int = 1000) -> List[Dict]:
        """Get analytics events"""
        try:
            if self._ensure_redis():
                # Get events from Redis
                event_keys = redis_client.keys("paperbrain:analytics:event:*")
                events = []
                
                for key in event_keys[:limit]:  # Limit to prevent memory issues
                    event_data = redis_client.get(key)
                    if event_data:
                        try:
                            events.append(json.loads(event_data))
                        except json.JSONDecodeError:
                            continue
                
                # Sort by timestamp
                events.sort(key=lambda x: x['timestamp'])
                return events
            else:
                return self.memory_events[-limit:] if self.memory_events else []
                
        except Exception as e:
            logger.error(f"Failed to get analytics events: {e}")
            return self.memory_events[-limit:] if self.memory_events else []
    
    def get_usage_stats(self) -> Dict:
        """Get usage statistics"""
        events = self.get_events(limit=10000)  # Get up to 10,000 events
        
        # Calculate statistics
        total_events = len(events)
        events_by_type = self._group_events_by_type(events)
        active_users = self._get_active_users(events)
        
        return {
            'total_events': total_events,
            'events_by_type': events_by_type,
            'active_users_count': len(active_users),
            'recent_activity': events[-20:] if events else [],
            'storage_backend': 'redis' if self._ensure_redis() else 'memory'
        }
    
    def _group_events_by_type(self, events: List[Dict]) -> Dict:
        """Group events by their type"""
        stats = {}
        for event in events:
            event_type = event['event_type']
            stats[event_type] = stats.get(event_type, 0) + 1
        return stats
    
    def _get_active_users(self, events: List[Dict]) -> set:
        """Get unique active users from events"""
        users = set()
        for event in events:
            if event.get('user_id'):
                users.add(event['user_id'])
        return users
    
    def get_user_activity(self, user_id: str, limit: int = 100) -> Dict:
        """Get activity for a specific user"""
        events = self.get_events(limit=10000)
        user_events = [event for event in events if event.get('user_id') == user_id]
        
        return {
            'user_id': user_id,
            'total_events': len(user_events),
            'events_by_type': self._group_events_by_type(user_events),
            'recent_activity': user_events[-limit:]
        }
    
    def cleanup_old_events(self, days: int = 30):
        """Clean up events older than specified days"""
        try:
            if self._ensure_redis():
                # Redis automatically expires events based on TTL
                pass
            else:
                # Clean up memory events
                cutoff = datetime.utcnow().timestamp() - (days * 86400)
                self.memory_events = [
                    event for event in self.memory_events 
                    if datetime.fromisoformat(event['timestamp']).timestamp() > cutoff
                ]
        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")

# Create singleton instance
analytics_service = AnalyticsService()