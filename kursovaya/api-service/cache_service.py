import redis
import json
import os
from typing import Optional, List
from models import Book

class CacheService:
    def __init__(self):
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.default_ttl = 3600  # 1 hour
    
    def get_book(self, book_id: str) -> Optional[dict]:
        """Get book from cache"""
        try:
            key = f"book:{book_id}"
            cached_data = self.redis_client.get(key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    def set_book(self, book_id: str, book_data: dict) -> bool:
        """Set book in cache"""
        try:
            key = f"book:{book_id}"
            self.redis_client.setex(key, self.default_ttl, json.dumps(book_data, default=str))
            return True
        except Exception as e:
            print(f"Cache set error: {e}")
            return False
    
    def delete_book(self, book_id: str) -> bool:
        """Delete book from cache"""
        try:
            key = f"book:{book_id}"
            self.redis_client.delete(key)
            return True
        except Exception as e:
            print(f"Cache delete error: {e}")
            return False
    
    def get_books_list(self) -> Optional[List[dict]]:
        """Get books list from cache"""
        try:
            key = "books:all"
            cached_data = self.redis_client.get(key)
            if cached_data:
                return json.loads(cached_data)
            return None
        except Exception as e:
            print(f"Cache get list error: {e}")
            return None
    
    def set_books_list(self, books_data: List[dict]) -> bool:
        """Set books list in cache"""
        try:
            key = "books:all"
            self.redis_client.setex(key, self.default_ttl, json.dumps(books_data, default=str))
            return True
        except Exception as e:
            print(f"Cache set list error: {e}")
            return False
    
    def invalidate_books_list(self) -> bool:
        """Invalidate books list cache"""
        try:
            self.redis_client.delete("books:all")
            return True
        except Exception as e:
            print(f"Cache invalidate error: {e}")
            return False
