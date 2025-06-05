from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator
import uuid
from typing import List
import threading
import time

from models import (
    CreateBookCommand, UpdateBookCommand, DeleteBookCommand,
    Event, BookAggregate, EventType
)
from database import get_db
from event_store import EventStore, AggregateRepository
from command_handlers import CommandHandler
from message_consumer import MessageConsumer

# Initialize FastAPI app
app = FastAPI(
    title="CQRS/Event Sourcing Service",
    description="Сервис для обработки команд и событий с использованием CQRS и Event Sourcing",
    version="1.0.0"
)

@app.middleware("http")
async def add_utf8_header(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Prometheus metrics
commands_processed_total = Counter(
    'commands_processed_total',
    'Total number of commands processed',
    ['command_type', 'status']
)

events_stored_total = Counter(
    'events_stored_total',
    'Total number of events stored',
    ['event_type']
)

command_processing_duration = Histogram(
    'command_processing_duration_seconds',
    'Command processing duration in seconds',
    ['command_type']
)

# Initialize Prometheus instrumentation
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

# Global variables for message consumer
message_consumer = None
consumer_thread = None

@app.on_event("startup")
def startup_event():
    """Initialize message consumer on startup"""
    global message_consumer, consumer_thread
    
    def command_processor(message):
        """Process incoming commands"""
        try:
            with next(get_db()) as db:
                event_store = EventStore(db)
                repository = AggregateRepository(event_store)
                handler = CommandHandler(repository)
                
                command_type = message.get('command_type')
                command_data = message.get('command_data', {})
                
                start_time = time.time()
                
                if command_type == 'create_book':
                    command = CreateBookCommand(**command_data)
                    events = handler.handle_create_book(command)
                elif command_type == 'update_book':
                    command = UpdateBookCommand(**command_data)
                    events = handler.handle_update_book(command)
                elif command_type == 'delete_book':
                    command = DeleteBookCommand(**command_data)
                    events = handler.handle_delete_book(command)
                else:
                    raise ValueError(f"Unknown command type: {command_type}")
                
                # Save events
                for event in events:
                    event_store.save_event(event)
                    events_stored_total.labels(event_type=event.event_type).inc()
                
                # Update metrics
                duration = time.time() - start_time
                command_processing_duration.labels(command_type=command_type).observe(duration)
                commands_processed_total.labels(command_type=command_type, status='success').inc()
                
                return {
                    'status': 'success',
                    'events': [
                        {
                            'event_type': event.event_type,
                            'event_data': event.event_data
                        }
                        for event in events
                    ]
                }
                
        except Exception as e:
            commands_processed_total.labels(command_type=command_type, status='error').inc()
            print(f"Error processing command: {e}")
            return {'status': 'error', 'message': str(e)}
    
    # Start message consumer in separate thread
    message_consumer = MessageConsumer()
    consumer_thread = threading.Thread(
        target=message_consumer.start_consuming,
        args=(command_processor,),
        daemon=True
    )
    consumer_thread.start()

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on shutdown"""
    global message_consumer
    if message_consumer:
        try:
            message_consumer.close()
        except:
            pass

@app.get("/metrics", response_class=Response)
def get_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "cqrs-service"}

@app.post("/commands/create-book")
def create_book_command(command: CreateBookCommand, db: Session = Depends(get_db)):
    """Process create book command"""
    try:
        event_store = EventStore(db)
        repository = AggregateRepository(event_store)
        handler = CommandHandler(repository)
        
        events = handler.handle_create_book(command)
        
        # Save events
        for event in events:
            event_store.save_event(event)
            events_stored_total.labels(event_type=event.event_type).inc()
        
        commands_processed_total.labels(command_type='create_book', status='success').inc()
        
        return {
            "message": "Book creation command processed",
            "aggregate_id": str(command.aggregate_id),
            "events_count": len(events)
        }
    
    except Exception as e:
        commands_processed_total.labels(command_type='create_book', status='error').inc()
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/commands/update-book")
def update_book_command(command: UpdateBookCommand, db: Session = Depends(get_db)):
    """Process update book command"""
    try:
        event_store = EventStore(db)
        repository = AggregateRepository(event_store)
        handler = CommandHandler(repository)
        
        events = handler.handle_update_book(command)
        
        # Save events
        for event in events:
            event_store.save_event(event)
            events_stored_total.labels(event_type=event.event_type).inc()
        
        commands_processed_total.labels(command_type='update_book', status='success').inc()
        
        return {
            "message": "Book update command processed",
            "aggregate_id": str(command.aggregate_id),
            "events_count": len(events)
        }
    
    except Exception as e:
        commands_processed_total.labels(command_type='update_book', status='error').inc()
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/commands/delete-book")
def delete_book_command(command: DeleteBookCommand, db: Session = Depends(get_db)):
    """Process delete book command"""
    try:
        event_store = EventStore(db)
        repository = AggregateRepository(event_store)
        handler = CommandHandler(repository)
        
        events = handler.handle_delete_book(command)
        
        # Save events
        for event in events:
            event_store.save_event(event)
            events_stored_total.labels(event_type=event.event_type).inc()
        
        commands_processed_total.labels(command_type='delete_book', status='success').inc()
        
        return {
            "message": "Book deletion command processed",
            "aggregate_id": str(command.aggregate_id),
            "events_count": len(events)
        }
    
    except Exception as e:
        commands_processed_total.labels(command_type='delete_book', status='error').inc()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/events/{aggregate_id}")
def get_events_by_aggregate(aggregate_id: str, db: Session = Depends(get_db)):
    """Get all events for a specific aggregate"""
    try:
        # Validate UUID
        uuid.UUID(aggregate_id)
        
        event_store = EventStore(db)
        events = event_store.get_events_by_aggregate_id(uuid.UUID(aggregate_id))
        
        return {
            "aggregate_id": aggregate_id,
            "events": [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "event_data": event.event_data,
                    "event_version": event.event_version,
                    "occurred_at": event.occurred_at
                }
                for event in events
            ]
        }
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid aggregate ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/aggregates/{aggregate_id}")
def get_aggregate(aggregate_id: str, db: Session = Depends(get_db)):
    """Get aggregate by ID (reconstructed from events)"""
    try:
        # Validate UUID
        uuid.UUID(aggregate_id)
        
        event_store = EventStore(db)
        repository = AggregateRepository(event_store)
        aggregate = repository.get_by_id(uuid.UUID(aggregate_id))
        
        if not aggregate:
            raise HTTPException(status_code=404, detail="Aggregate not found")
        
        return {
            "id": str(aggregate.id),
            "title": aggregate.title,
            "description": aggregate.description,
            "author": aggregate.author,
            "version": aggregate.version,
            "created_at": aggregate.created_at,
            "updated_at": aggregate.updated_at,
            "is_deleted": aggregate.is_deleted
        }
    
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid aggregate ID format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/events")
def get_all_events(event_type: str = None, db: Session = Depends(get_db)):
    """Get all events, optionally filtered by type"""
    try:
        event_store = EventStore(db)
        events = event_store.get_all_events(event_type)
        
        return {
            "events": [
                {
                    "id": event.id,
                    "aggregate_id": str(event.aggregate_id),
                    "event_type": event.event_type,
                    "event_data": event.event_data,
                    "event_version": event.event_version,
                    "occurred_at": event.occurred_at
                }
                for event in events
            ],
            "total_count": len(events)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
