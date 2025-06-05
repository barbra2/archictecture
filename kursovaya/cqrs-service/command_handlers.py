from typing import List
import uuid
from datetime import datetime

from models import (
    CreateBookCommand, UpdateBookCommand, DeleteBookCommand,
    Event, EventType, BookAggregate
)
from event_store import AggregateRepository

class CommandHandler:
    def __init__(self, repository: AggregateRepository):
        self.repository = repository
    
    def handle_create_book(self, command: CreateBookCommand) -> List[Event]:
        """Handle create book command"""
        # Check if book already exists
        existing_aggregate = self.repository.get_by_id(command.aggregate_id)
        if existing_aggregate:
            raise ValueError(f"Book with ID {command.aggregate_id} already exists")
        
        # Create event
        now = datetime.utcnow()
        event = Event(
            aggregate_id=command.aggregate_id,
            aggregate_type="Book",
            event_type=EventType.BOOK_CREATED,
            event_data={
                "title": command.title,
                "description": command.description,
                "author": command.author,
                "created_at": now.isoformat()
            },
            event_version=1
        )
        
        return [event]
    
    def handle_update_book(self, command: UpdateBookCommand) -> List[Event]:
        """Handle update book command"""
        # Get existing aggregate
        aggregate = self.repository.get_by_id(command.aggregate_id)
        if not aggregate:
            raise ValueError(f"Book with ID {command.aggregate_id} not found")
        
        # Prepare update data
        update_data = {}
        if command.title is not None:
            update_data["title"] = command.title
        if command.description is not None:
            update_data["description"] = command.description
        if command.author is not None:
            update_data["author"] = command.author
        
        if not update_data:
            raise ValueError("No fields to update")
        
        # Create event
        now = datetime.utcnow()
        update_data["updated_at"] = now.isoformat()
        
        event = Event(
            aggregate_id=command.aggregate_id,
            aggregate_type="Book",
            event_type=EventType.BOOK_UPDATED,
            event_data=update_data,
            event_version=aggregate.version + 1
        )
        
        return [event]
    
    def handle_delete_book(self, command: DeleteBookCommand) -> List[Event]:
        """Handle delete book command"""
        # Get existing aggregate
        aggregate = self.repository.get_by_id(command.aggregate_id)
        if not aggregate:
            raise ValueError(f"Book with ID {command.aggregate_id} not found")
        
        # Create event
        now = datetime.utcnow()
        event = Event(
            aggregate_id=command.aggregate_id,
            aggregate_type="Book",
            event_type=EventType.BOOK_DELETED,
            event_data={
                "deleted_at": now.isoformat()
            },
            event_version=aggregate.version + 1
        )
        
        return [event]
