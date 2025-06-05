import os
from sqlalchemy import create_engine, Column, String, Text, DateTime, UUID, Integer, JSON, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
import uuid as uuid_pkg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/books_db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class EventStoreDB(Base):
    __tablename__ = "event_store"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    aggregate_type = Column(String(100), nullable=False)
    event_type = Column(String(100), nullable=False)
    event_data = Column(JSON, nullable=False)
    event_version = Column(Integer, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        UniqueConstraint('aggregate_id', 'event_version', name='uq_aggregate_version'),
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
