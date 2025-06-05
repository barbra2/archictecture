from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

class BookReadModel(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    author: str
    version: int
    created_at: datetime
    updated_at: datetime

class BookSearchRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None

class BookStatistics(BaseModel):
    total_books: int
    books_by_author: dict
    recent_books: int  # Books created in last 24 hours
    most_popular_author: Optional[str] = None
