from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

class BookBase(BaseModel):
    title: str
    description: Optional[str] = None
    author: str

class BookCreate(BookBase):
    pass

class BookUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    author: Optional[str] = None

class Book(BookBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str]
    author: str
    created_at: datetime
    updated_at: datetime
