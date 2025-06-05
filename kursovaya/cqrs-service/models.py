from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
from datetime import datetime
from enum import Enum

# Commands
class CommandType(str, Enum):
    CREATE_BOOK = "create_book"
    UPDATE_BOOK = "update_book"
    DELETE_BOOK = "delete_book"

class CreateBookCommand(BaseModel):
    command_type: CommandType = CommandType.CREATE_BOOK
    aggregate_id: uuid.UUID
    title: str
    description: Optional[str] = None
    author: str

class UpdateBookCommand(BaseModel):
    command_type: CommandType = CommandType.UPDATE_BOOK
    aggregate_id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None

class DeleteBookCommand(BaseModel):
    command_type: CommandType = CommandType.DELETE_BOOK
    aggregate_id: uuid.UUID

# Events
class EventType(str, Enum):
    BOOK_CREATED = "book_created"
    BOOK_UPDATED = "book_updated"
    BOOK_DELETED = "book_deleted"

class Event(BaseModel):
    id: Optional[int] = None
    aggregate_id: uuid.UUID
    aggregate_type: str = "Book"
    event_type: EventType
    event_data: Dict[Any, Any]
    event_version: int
    occurred_at: Optional[datetime] = None

class BookCreatedEvent(BaseModel):
    event_type: EventType = EventType.BOOK_CREATED
    aggregate_id: uuid.UUID
    title: str
    description: Optional[str]
    author: str
    created_at: datetime

class BookUpdatedEvent(BaseModel):
    event_type: EventType = EventType.BOOK_UPDATED
    aggregate_id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    updated_at: datetime

class BookDeletedEvent(BaseModel):
    event_type: EventType = EventType.BOOK_DELETED
    aggregate_id: uuid.UUID
    deleted_at: datetime

# Aggregate
class BookAggregate(BaseModel):
    id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None
    version: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_deleted: bool = False

    def apply_event(self, event: Event):
        """Apply event to aggregate"""
        if event.event_type == EventType.BOOK_CREATED:
            self.title = event.event_data["title"]
            self.description = event.event_data.get("description")
            self.author = event.event_data["author"]
            self.created_at = datetime.fromisoformat(event.event_data["created_at"])
            self.updated_at = self.created_at
        elif event.event_type == EventType.BOOK_UPDATED:
            if "title" in event.event_data:
                self.title = event.event_data["title"]
            if "description" in event.event_data:
                self.description = event.event_data["description"]
            if "author" in event.event_data:
                self.author = event.event_data["author"]
            self.updated_at = datetime.fromisoformat(event.event_data["updated_at"])
        elif event.event_type == EventType.BOOK_DELETED:
            self.is_deleted = True
            
        self.version = event.event_version
