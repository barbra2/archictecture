import pika
import json
import os
from typing import Callable

class MessageConsumer:
    def __init__(self):
        rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        self.connection = pika.BlockingConnection(pika.URLParameters(rabbitmq_url))
        self.channel = self.connection.channel()
        
        # Declare exchanges and queues
        self.channel.exchange_declare(exchange='book_events', exchange_type='topic', durable=True)
        self.channel.exchange_declare(exchange='cqrs_commands', exchange_type='topic', durable=True)
        
        # Command queues
        self.channel.queue_declare(queue='create_book_commands', durable=True)
        self.channel.queue_declare(queue='update_book_commands', durable=True)
        self.channel.queue_declare(queue='delete_book_commands', durable=True)
        
        # Bind command queues
        self.channel.queue_bind(exchange='cqrs_commands', queue='create_book_commands', routing_key='command.create_book')
        self.channel.queue_bind(exchange='cqrs_commands', queue='update_book_commands', routing_key='command.update_book')
        self.channel.queue_bind(exchange='cqrs_commands', queue='delete_book_commands', routing_key='command.delete_book')
    
    def publish_event(self, event_type: str, event_data: dict):
        """Publish event after command processing"""
        try:
            routing_key = f"event.{event_type}"
            message = {
                "event_type": event_type,
                "event_data": event_data
            }
            
            self.channel.basic_publish(
                exchange='book_events',
                routing_key=routing_key,
                body=json.dumps(message, default=str),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json'
                )
            )
            print(f"Published event: {event_type}")
            return True
        except Exception as e:
            print(f"Failed to publish event: {e}")
            return False
    
    def start_consuming(self, command_handler: Callable):
        """Start consuming commands"""
        def callback(ch, method, properties, body):
            try:
                message = json.loads(body)
                print(f"Received command: {message}")
                
                # Process command
                result = command_handler(message)
                
                # Acknowledge message
                ch.basic_ack(delivery_tag=method.delivery_tag)
                
                # Publish resulting events
                if result and 'events' in result:
                    for event in result['events']:
                        self.publish_event(event['event_type'], event['event_data'])
                
            except Exception as e:
                print(f"Error processing command: {e}")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        
        # Set up consumers
        self.channel.basic_qos(prefetch_count=1)
        self.channel.basic_consume(queue='create_book_commands', on_message_callback=callback)
        self.channel.basic_consume(queue='update_book_commands', on_message_callback=callback)
        self.channel.basic_consume(queue='delete_book_commands', on_message_callback=callback)
        
        print("Starting to consume commands...")
        self.channel.start_consuming()
    
    def close(self):
        """Close connection"""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
