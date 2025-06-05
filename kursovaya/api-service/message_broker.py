import pika
import json
import os
from typing import Dict, Any

class MessageBroker:
    def __init__(self):
        rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare exchanges
        self.channel.exchange_declare(exchange='book_events', exchange_type='topic', durable=True)
        
        # Declare queues
        self.channel.queue_declare(queue='book_created', durable=True)
        self.channel.queue_declare(queue='book_updated', durable=True)
        self.channel.queue_declare(queue='book_deleted', durable=True)
        
        # Bind queues to exchanges
        self.channel.queue_bind(exchange='book_events', queue='book_created', routing_key='book.created')
        self.channel.queue_bind(exchange='book_events', queue='book_updated', routing_key='book.updated')
        self.channel.queue_bind(exchange='book_events', queue='book_deleted', routing_key='book.deleted')
    
    def publish_event(self, event_type: str, book_data: Dict[Any, Any]):
        """Publish book event to RabbitMQ"""
        try:
            routing_key = f"book.{event_type}"
            message = {
                "event_type": event_type,
                "book_data": book_data,
                "timestamp": str(book_data.get("updated_at", book_data.get("created_at")))
            }
            
            self.channel.basic_publish(
                exchange='book_events',
                routing_key=routing_key,
                body=json.dumps(message, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Make message persistent
                    content_type='application/json'
                )
            )
            print(f"Published event: {event_type} for book {book_data.get('id')}")
            return True
        except Exception as e:
            print(f"Failed to publish event: {e}")
            return False
    
    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
