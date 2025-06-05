import pika
import json
import os
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import threading
from database import get_db, BookReadModelDB

class EventProjector:
    def __init__(self):
        rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare exchange and queue for events
        self.channel.exchange_declare(exchange='book_events', exchange_type='topic', durable=True)
        
        # Declare queue for this service
        result = self.channel.queue_declare(queue='', exclusive=True)
        self.queue_name = result.method.queue
        
        # Bind to all book events
        self.channel.queue_bind(exchange='book_events', queue=self.queue_name, routing_key='book.*')
        self.channel.queue_bind(exchange='book_events', queue=self.queue_name, routing_key='event.*')
    
    def project_book_created(self, event_data: dict, db: Session):
        """Project book created event to read model"""
        try:
            book_data = event_data.get('book_data', event_data)
            
            read_model = BookReadModelDB(
                id=uuid.UUID(str(book_data['id'])),
                title=book_data['title'],
                description=book_data.get('description'),
                author=book_data['author'],
                version=1,
                created_at=datetime.fromisoformat(book_data['created_at'].replace('Z', '+00:00')) if isinstance(book_data['created_at'], str) else book_data['created_at'],
                updated_at=datetime.fromisoformat(book_data['updated_at'].replace('Z', '+00:00')) if isinstance(book_data['updated_at'], str) else book_data['updated_at']
            )
            
            db.add(read_model)
            db.commit()
            print(f"Projected book created: {book_data['title']}")
            
        except Exception as e:
            print(f"Error projecting book created event: {e}")
            db.rollback()
    
    def project_book_updated(self, event_data: dict, db: Session):
        """Project book updated event to read model"""
        try:
            book_data = event_data.get('book_data', event_data)
            book_id = uuid.UUID(str(book_data['id']))
            
            read_model = db.query(BookReadModelDB).filter(BookReadModelDB.id == book_id).first()
            if read_model:
                if 'title' in book_data:
                    read_model.title = book_data['title']
                if 'description' in book_data:
                    read_model.description = book_data['description']
                if 'author' in book_data:
                    read_model.author = book_data['author']
                
                read_model.version += 1
                read_model.updated_at = datetime.fromisoformat(book_data['updated_at'].replace('Z', '+00:00')) if isinstance(book_data['updated_at'], str) else book_data['updated_at']
                
                db.commit()
                print(f"Projected book updated: {read_model.title}")
            
        except Exception as e:
            print(f"Error projecting book updated event: {e}")
            db.rollback()
    
    def project_book_deleted(self, event_data: dict, db: Session):
        """Project book deleted event to read model"""
        try:
            book_data = event_data.get('book_data', event_data)
            book_id = uuid.UUID(str(book_data['id']))
            
            read_model = db.query(BookReadModelDB).filter(BookReadModelDB.id == book_id).first()
            if read_model:
                db.delete(read_model)
                db.commit()
                print(f"Projected book deleted: {book_id}")
            
        except Exception as e:
            print(f"Error projecting book deleted event: {e}")
            db.rollback()
    
    def process_event(self, event_type: str, event_data: dict):
        """Process incoming event"""
        with next(get_db()) as db:
            if event_type in ['created', 'book_created', 'book.created']:
                self.project_book_created(event_data, db)
            elif event_type in ['updated', 'book_updated', 'book.updated']:
                self.project_book_updated(event_data, db)
            elif event_type in ['deleted', 'book_deleted', 'book.deleted']:
                self.project_book_deleted(event_data, db)
            else:
                print(f"Unknown event type: {event_type}")
    
    def start_consuming(self):
        """Start consuming events"""
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                print(f"Received event: {message}")
                
                event_type = message.get('event_type', method.routing_key.split('.')[-1])
                event_data = message.get('book_data', message.get('event_data', message))
                
                self.process_event(event_type, event_data)
                
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
            except Exception as e:
                print(f"Error processing event: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue=self.queue_name, on_message_callback=callback)
        
        print("Starting to consume events for read model projection...")
        self.channel.start_consuming()
    
    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
