from datetime import datetime
import json

class AnalyticsService:
    def __init__(self):
        self.events = []
    
    def track_event(self, event_type: str, user_id: str = None, metadata: dict = None):
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'user_id': user_id,
            'metadata': metadata or {}
        }
        
        self.events.append(event)
        
        # In production, send to analytics service
        # self.send_to_analytics_service(event)
    
    def get_usage_stats(self):
        return {
            'total_events': len(self.events),
            'events_by_type': self._group_by_type(),
            'recent_activity': self.events[-10:]
        }
    
    def _group_by_type(self):
        stats = {}
        for event in self.events:
            event_type = event['event_type']
            stats[event_type] = stats.get(event_type, 0) + 1
        return stats