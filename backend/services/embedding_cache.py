"""
InkFlow Embedding Cache

LRU cache for vector embeddings to avoid repeated computation.
Adapted from Lumina project.
"""

import logging
import hashlib
import time
from typing import Optional, List, Callable, Any
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger("EmbeddingCache")


class EmbeddingCache:
    """
    Thread-safe LRU cache for embedding vectors.
    
    Features:
    - Fixed size with LRU eviction
    - TTL support
    - Cache stats for monitoring
    """
    
    DEFAULT_MAX_SIZE = 512
    DEFAULT_TTL_SECONDS = 3600  # 1 hour
    
    def __init__(self, max_size: int = DEFAULT_MAX_SIZE, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = Lock()
        
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, text: str, model_name: str = "default") -> str:
        text_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return f"{model_name}:{text_hash}"
    
    def get(self, text: str, model_name: str = "default") -> Optional[List[float]]:
        """Get cached embedding if exists and not expired."""
        key = self._make_key(text, model_name)
        
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            vector, timestamp = self._cache[key]
            
            if time.time() - timestamp > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            
            self._cache.move_to_end(key)
            self._hits += 1
            return vector
    
    def put(self, text: str, vector: List[float], model_name: str = "default"):
        """Store an embedding in cache."""
        key = self._make_key(text, model_name)
        
        with self._lock:
            if key in self._cache:
                self._cache[key] = (vector, time.time())
                self._cache.move_to_end(key)
                return
            
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            
            self._cache[key] = (vector, time.time())
    
    def get_or_compute(
        self, 
        text: str, 
        compute_fn: Callable[[str], List[float]],
        model_name: str = "default"
    ) -> List[float]:
        """Get from cache or compute and cache."""
        cached = self.get(text, model_name)
        if cached is not None:
            return cached
        
        vector = compute_fn(text)
        self.put(text, vector, model_name)
        return vector
    
    def get_stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": f"{hit_rate:.1f}%",
            }


# Global instance
_cache: Optional[EmbeddingCache] = None


def get_embedding_cache() -> EmbeddingCache:
    """Get or create the global embedding cache."""
    global _cache
    if _cache is None:
        _cache = EmbeddingCache()
        logger.info("⚡ EmbeddingCache initialized")
    return _cache
