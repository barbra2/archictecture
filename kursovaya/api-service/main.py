from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator
import uuid
from typing import List, Optional

from models import Book, BookCreate, BookUpdate, BookResponse
from database import get_db, BookDB
from cache_service import CacheService
from message_broker import MessageBroker

# Initialize FastAPI app
app = FastAPI(
    title="Books API Service",
    description="API для управления книгами с кэшированием и событиями",
    version="1.0.0"
)

@app.middleware("http")
async def add_utf8_header(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Add CORS middleware with UTF-8 support
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_utf8_header(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Initialize services
cache_service = CacheService()
message_broker = MessageBroker()

# Prometheus metrics
books_operations_total = Counter(
    'books_operations_total',
    'Total number of book operations',
    ['operation', 'status']
)

books_cache_hits_total = Counter(
    'books_cache_hits_total', 
    'Total number of cache hits'
)

books_cache_misses_total = Counter(
    'books_cache_misses_total',
    'Total number of cache misses'
)

request_duration_seconds = Histogram(
    'books_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

active_books_count = Gauge(
    'active_books_count',
    'Number of active books'
)

# Initialize Prometheus instrumentation
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

@app.get("/metrics", response_class=Response)
def get_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "api-service"}

@app.post("/books", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(book: BookCreate, db: Session = Depends(get_db)):
    """Создать новую книгу"""
    try:
        # Create book in database
        db_book = BookDB(**book.dict())
        db.add(db_book)
        db.commit()
        db.refresh(db_book)
        
        # Convert to dict for caching and messaging
        book_dict = {
            "id": str(db_book.id),
            "title": db_book.title,
            "description": db_book.description,
            "author": db_book.author,
            "created_at": db_book.created_at,
            "updated_at": db_book.updated_at
        }
        
        # Cache the book
        cache_service.set_book(str(db_book.id), book_dict)
        
        # Invalidate books list cache
        cache_service.invalidate_books_list()
        
        # Publish event
        message_broker.publish_event("created", book_dict)
        
        # Update metrics
        books_operations_total.labels(operation='create', status='success').inc()
        
        return BookResponse(**book_dict)
    
    except Exception as e:
        books_operations_total.labels(operation='create', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to create book: {str(e)}")

@app.get("/books", response_model=List[BookResponse])
def get_books(db: Session = Depends(get_db)):
    """Получить все книги"""
    try:
        # Try cache first
        cached_books = cache_service.get_books_list()
        if cached_books:
            books_cache_hits_total.inc()
            books_operations_total.labels(operation='list', status='success').inc()
            return [BookResponse(**book) for book in cached_books]
        
        # Cache miss - get from database
        books_cache_misses_total.inc()
        books = db.query(BookDB).all()
        
        # Convert to dict list
        books_list = []
        for book in books:
            book_dict = {
                "id": str(book.id),
                "title": book.title,
                "description": book.description,
                "author": book.author,
                "created_at": book.created_at,
                "updated_at": book.updated_at
            }
            books_list.append(book_dict)
        
        # Cache the list
        cache_service.set_books_list(books_list)
        
        # Update metrics
        books_operations_total.labels(operation='list', status='success').inc()
        active_books_count.set(len(books_list))
        
        return [BookResponse(**book) for book in books_list]
    
    except Exception as e:
        books_operations_total.labels(operation='list', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get books: {str(e)}")

@app.get("/books/{book_id}", response_model=BookResponse)
def get_book(book_id: str, db: Session = Depends(get_db)):
    """Получить книгу по ID"""
    try:
        # Validate UUID
        uuid.UUID(book_id)
        
        # Try cache first
        cached_book = cache_service.get_book(book_id)
        if cached_book:
            books_cache_hits_total.inc()
            books_operations_total.labels(operation='get', status='success').inc()
            return BookResponse(**cached_book)
        
        # Cache miss - get from database
        books_cache_misses_total.inc()
        book = db.query(BookDB).filter(BookDB.id == book_id).first()
        
        if not book:
            books_operations_total.labels(operation='get', status='not_found').inc()
            raise HTTPException(status_code=404, detail="Book not found")
        
        # Convert to dict
        book_dict = {
            "id": str(book.id),
            "title": book.title,
            "description": book.description,
            "author": book.author,
            "created_at": book.created_at,
            "updated_at": book.updated_at
        }
        
        # Cache the book
        cache_service.set_book(book_id, book_dict)
        
        # Update metrics
        books_operations_total.labels(operation='get', status='success').inc()
        
        return BookResponse(**book_dict)
    
    except ValueError:
        books_operations_total.labels(operation='get', status='error').inc()
        raise HTTPException(status_code=400, detail="Invalid book ID format")
    except HTTPException:
        raise
    except Exception as e:
        books_operations_total.labels(operation='get', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get book: {str(e)}")

@app.get("/books/search/{title}", response_model=List[BookResponse])
def search_books_by_title(title: str, db: Session = Depends(get_db)):
    """Поиск книг по названию"""
    try:
        books = db.query(BookDB).filter(BookDB.title.ilike(f"%{title}%")).all()
        
        books_list = []
        for book in books:
            book_dict = {
                "id": str(book.id),
                "title": book.title,
                "description": book.description,
                "author": book.author,
                "created_at": book.created_at,
                "updated_at": book.updated_at
            }
            books_list.append(book_dict)
        
        books_operations_total.labels(operation='search', status='success').inc()
        return [BookResponse(**book) for book in books_list]
    
    except Exception as e:
        books_operations_total.labels(operation='search', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to search books: {str(e)}")

@app.put("/books/{book_id}", response_model=BookResponse)
def update_book(book_id: str, book_update: BookUpdate, db: Session = Depends(get_db)):
    """Обновить книгу"""
    try:
        # Validate UUID
        uuid.UUID(book_id)
        
        # Get book from database
        book = db.query(BookDB).filter(BookDB.id == book_id).first()
        if not book:
            books_operations_total.labels(operation='update', status='not_found').inc()
            raise HTTPException(status_code=404, detail="Book not found")
        
        # Update fields
        update_data = book_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(book, field, value)
        
        db.commit()
        db.refresh(book)
        
        # Convert to dict
        book_dict = {
            "id": str(book.id),
            "title": book.title,
            "description": book.description,
            "author": book.author,
            "created_at": book.created_at,
            "updated_at": book.updated_at
        }
        
        # Update cache
        cache_service.set_book(book_id, book_dict)
        cache_service.invalidate_books_list()
        
        # Publish event
        message_broker.publish_event("updated", book_dict)
        
        # Update metrics
        books_operations_total.labels(operation='update', status='success').inc()
        
        return BookResponse(**book_dict)
    
    except ValueError:
        books_operations_total.labels(operation='update', status='error').inc()
        raise HTTPException(status_code=400, detail="Invalid book ID format")
    except HTTPException:
        raise
    except Exception as e:
        books_operations_total.labels(operation='update', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to update book: {str(e)}")

@app.delete("/books/{book_id}")
def delete_book(book_id: str, db: Session = Depends(get_db)):
    """Удалить книгу"""
    try:
        # Validate UUID
        uuid.UUID(book_id)
        
        # Get book from database
        book = db.query(BookDB).filter(BookDB.id == book_id).first()
        if not book:
            books_operations_total.labels(operation='delete', status='not_found').inc()
            raise HTTPException(status_code=404, detail="Book not found")
        
        # Convert to dict for event
        book_dict = {
            "id": str(book.id),
            "title": book.title,
            "description": book.description,
            "author": book.author,
            "created_at": book.created_at,
            "updated_at": book.updated_at
        }
        
        # Delete from database
        db.delete(book)
        db.commit()
        
        # Remove from cache
        cache_service.delete_book(book_id)
        cache_service.invalidate_books_list()
        
        # Publish event
        message_broker.publish_event("deleted", book_dict)
        
        # Update metrics
        books_operations_total.labels(operation='delete', status='success').inc()
        
        return {"message": "Book deleted successfully"}
    
    except ValueError:
        books_operations_total.labels(operation='delete', status='error').inc()
        raise HTTPException(status_code=400, detail="Invalid book ID format")
    except HTTPException:
        raise
    except Exception as e:
        books_operations_total.labels(operation='delete', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to delete book: {str(e)}")

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on shutdown"""
    try:
        message_broker.close()
    except:
        pass
