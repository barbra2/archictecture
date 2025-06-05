from sqlalchemy.orm import Session
from typing import List, Optional
import uuid
from datetime import datetime

from database import EventStoreDB
from models import Event, BookAggregate, EventType

class EventStore:
    def __init__(self, db: Session):
        self.db = db
    
    def save_event(self, event: Event) -> Event:
        """Save event to event store"""
        db_event = EventStoreDB(
            aggregate_id=event.aggregate_id,
            aggregate_type=event.aggregate_type,
            event_type=event.event_type,
            event_data=event.event_data,
            event_version=event.event_version
        )
        
        self.db.add(db_event)
        self.db.commit()
        self.db.refresh(db_event)
        
        event.id = db_event.id
        event.occurred_at = db_event.occurred_at
        return event
    
    def get_events_by_aggregate_id(self, aggregate_id: uuid.UUID) -> List[Event]:
        """Get all events for an aggregate"""
        events = self.db.query(EventStoreDB).filter(
            EventStoreDB.aggregate_id == aggregate_id
        ).order_by(EventStoreDB.event_version).all()
        
        return [
            Event(
                id=event.id,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                event_type=event.event_type,
                event_data=event.event_data,
                event_version=event.event_version,
                occurred_at=event.occurred_at
            )
            for event in events
        ]
    
    def get_latest_version(self, aggregate_id: uuid.UUID) -> int:
        """Get latest version for aggregate"""
        latest = self.db.query(EventStoreDB).filter(
            EventStoreDB.aggregate_id == aggregate_id
        ).order_by(EventStoreDB.event_version.desc()).first()
        
        return latest.event_version if latest else 0
    
    def get_all_events(self, event_type: Optional[str] = None) -> List[Event]:
        """Get all events, optionally filtered by type"""
        query = self.db.query(EventStoreDB)
        if event_type:
            query = query.filter(EventStoreDB.event_type == event_type)
        
        events = query.order_by(EventStoreDB.occurred_at).all()
        
        return [
            Event(
                id=event.id,
                aggregate_id=event.aggregate_id,
                aggregate_type=event.aggregate_type,
                event_type=event.event_type,
                event_data=event.event_data,
                event_version=event.event_version,
                occurred_at=event.occurred_at
            )
            for event in events
        ]

class AggregateRepository:
    def __init__(self, event_store: EventStore):
        self.event_store = event_store
    
    def save(self, aggregate: BookAggregate, events: List[Event]) -> BookAggregate:
        """Save aggregate by saving its events"""
        for event in events:
            self.event_store.save_event(event)
        return aggregate
    
    def get_by_id(self, aggregate_id: uuid.UUID) -> Optional[BookAggregate]:
        """Reconstruct aggregate from events"""
        events = self.event_store.get_events_by_aggregate_id(aggregate_id)
        
        if not events:
            return None
        
        aggregate = BookAggregate(id=aggregate_id)
        
        for event in events:
            aggregate.apply_event(event)
        
        return aggregate if not aggregate.is_deleted else None
    
    def get_all_aggregates(self) -> List[BookAggregate]:
        """Get all book aggregates"""
        # Get all unique aggregate IDs
        all_events = self.event_store.get_all_events()
        aggregate_ids = set(event.aggregate_id for event in all_events)
        
        aggregates = []
        for aggregate_id in aggregate_ids:
            aggregate = self.get_by_id(aggregate_id)
            if aggregate and not aggregate.is_deleted:
                aggregates.append(aggregate)
        
        return aggregates
