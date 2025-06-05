from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from prometheus_fastapi_instrumentator import Instrumentator
import uuid
from typing import List, Optional
import threading
from datetime import datetime, timedelta
from collections import Counter as CollectionCounter

from models import BookReadModel, BookSearchRequest, BookStatistics
from database import get_db, BookReadModelDB
from event_projector import EventProjector

# Initialize FastAPI app
app = FastAPI(
    title="Query Service",
    description="Сервис для чтения данных (Read Models) в CQRS архитектуре",
    version="1.0.0"
)

@app.middleware("http")
async def add_utf8_header(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

# Prometheus metrics
queries_total = Counter(
    'queries_total',
    'Total number of queries executed',
    ['query_type', 'status']
)

query_duration_seconds = Histogram(
    'query_duration_seconds',
    'Query execution duration in seconds',
    ['query_type']
)

read_models_count = Gauge(
    'read_models_count',
    'Number of read models in the system'
)

# Initialize Prometheus instrumentation
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app)

# Global variables for event projector
event_projector = None
projector_thread = None

@app.on_event("startup")
def startup_event():
    """Initialize event projector on startup"""
    global event_projector, projector_thread
    
    # Start event projector in separate thread
    event_projector = EventProjector()
    projector_thread = threading.Thread(
        target=event_projector.start_consuming,
        daemon=True
    )
    projector_thread.start()

@app.on_event("shutdown")
def shutdown_event():
    """Cleanup on shutdown"""
    global event_projector
    if event_projector:
        try:
            event_projector.close()
        except:
            pass

@app.get("/metrics", response_class=Response)
def get_metrics():
    """Prometheus metrics endpoint"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "query-service"}

@app.get("/books", response_model=List[BookReadModel])
def get_all_books(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get all books (read models)"""
    try:
        books = db.query(BookReadModelDB).offset(offset).limit(limit).all()
        
        # Update metrics
        queries_total.labels(query_type='get_all_books', status='success').inc()
        read_models_count.set(db.query(BookReadModelDB).count())
        
        return [
            BookReadModel(
                id=book.id,
                title=book.title,
                description=book.description,
                author=book.author,
                version=book.version,
                created_at=book.created_at,
                updated_at=book.updated_at
            )
            for book in books
        ]
    
    except Exception as e:
        queries_total.labels(query_type='get_all_books', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get books: {str(e)}")

@app.get("/books/{book_id}", response_model=BookReadModel)
def get_book_by_id(book_id: str, db: Session = Depends(get_db)):
    """Get book by ID from read model"""
    try:
        # Validate UUID
        uuid.UUID(book_id)
        
        book = db.query(BookReadModelDB).filter(BookReadModelDB.id == book_id).first()
        
        if not book:
            queries_total.labels(query_type='get_book_by_id', status='not_found').inc()
            raise HTTPException(status_code=404, detail="Book not found")
        
        queries_total.labels(query_type='get_book_by_id', status='success').inc()
        
        return BookReadModel(
            id=book.id,
            title=book.title,
            description=book.description,
            author=book.author,
            version=book.version,
            created_at=book.created_at,
            updated_at=book.updated_at
        )
    
    except ValueError:
        queries_total.labels(query_type='get_book_by_id', status='error').inc()
        raise HTTPException(status_code=400, detail="Invalid book ID format")
    except HTTPException:
        raise
    except Exception as e:
        queries_total.labels(query_type='get_book_by_id', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get book: {str(e)}")

@app.get("/books/by-author/{author}", response_model=List[BookReadModel])
def get_books_by_author(
    author: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get books by author"""
    try:
        books = db.query(BookReadModelDB).filter(
            BookReadModelDB.author.ilike(f"%{author}%")
        ).offset(offset).limit(limit).all()
        
        queries_total.labels(query_type='get_books_by_author', status='success').inc()
        
        return [
            BookReadModel(
                id=book.id,
                title=book.title,
                description=book.description,
                author=book.author,
                version=book.version,
                created_at=book.created_at,
                updated_at=book.updated_at
            )
            for book in books
        ]
    
    except Exception as e:
        queries_total.labels(query_type='get_books_by_author', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get books by author: {str(e)}")

@app.post("/books/search", response_model=List[BookReadModel])
def search_books(
    search_request: BookSearchRequest,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Search books by multiple criteria"""
    try:
        query = db.query(BookReadModelDB)
        
        if search_request.title:
            query = query.filter(BookReadModelDB.title.ilike(f"%{search_request.title}%"))
        
        if search_request.author:
            query = query.filter(BookReadModelDB.author.ilike(f"%{search_request.author}%"))
        
        if search_request.description:
            query = query.filter(BookReadModelDB.description.ilike(f"%{search_request.description}%"))
        
        books = query.offset(offset).limit(limit).all()
        
        queries_total.labels(query_type='search_books', status='success').inc()
        
        return [
            BookReadModel(
                id=book.id,
                title=book.title,
                description=book.description,
                author=book.author,
                version=book.version,
                created_at=book.created_at,
                updated_at=book.updated_at
            )
            for book in books
        ]
    
    except Exception as e:
        queries_total.labels(query_type='search_books', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to search books: {str(e)}")

@app.get("/books/recent", response_model=List[BookReadModel])
def get_recent_books(
    hours: int = Query(24, ge=1, le=168),  # Last 24 hours by default, max 1 week
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Get recently created books"""
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        
        books = db.query(BookReadModelDB).filter(
            BookReadModelDB.created_at >= since
        ).order_by(desc(BookReadModelDB.created_at)).limit(limit).all()
        
        queries_total.labels(query_type='get_recent_books', status='success').inc()
        
        return [
            BookReadModel(
                id=book.id,
                title=book.title,
                description=book.description,
                author=book.author,
                version=book.version,
                created_at=book.created_at,
                updated_at=book.updated_at
            )
            for book in books
        ]
    
    except Exception as e:
        queries_total.labels(query_type='get_recent_books', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get recent books: {str(e)}")

@app.get("/statistics", response_model=BookStatistics)
def get_statistics(db: Session = Depends(get_db)):
    """Get book statistics"""
    try:
        # Total books count
        total_books = db.query(BookReadModelDB).count()
        
        # Books by author
        author_counts = db.query(
            BookReadModelDB.author,
            func.count(BookReadModelDB.id).label('count')
        ).group_by(BookReadModelDB.author).all()
        
        books_by_author = {author: count for author, count in author_counts}
        
        # Most popular author
        most_popular_author = None
        if author_counts:
            most_popular_author = max(author_counts, key=lambda x: x.count)[0]
        
        # Recent books (last 24 hours)
        since = datetime.utcnow() - timedelta(hours=24)
        recent_books = db.query(BookReadModelDB).filter(
            BookReadModelDB.created_at >= since
        ).count()
        
        queries_total.labels(query_type='get_statistics', status='success').inc()
        
        return BookStatistics(
            total_books=total_books,
            books_by_author=books_by_author,
            recent_books=recent_books,
            most_popular_author=most_popular_author
        )
    
    except Exception as e:
        queries_total.labels(query_type='get_statistics', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")

@app.get("/authors", response_model=List[str])
def get_all_authors(db: Session = Depends(get_db)):
    """Get list of all unique authors"""
    try:
        authors = db.query(BookReadModelDB.author).distinct().all()
        
        queries_total.labels(query_type='get_all_authors', status='success').inc()
        
        return [author[0] for author in authors]
    
    except Exception as e:
        queries_total.labels(query_type='get_all_authors', status='error').inc()
        raise HTTPException(status_code=500, detail=f"Failed to get authors: {str(e)}")
