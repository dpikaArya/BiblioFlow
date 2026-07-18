"""Model caching and memory management."""
from __future__ import annotations

import logging
import time
import threading
from collections import OrderedDict
from typing import Any, Optional

from .models import ModelInfo, ModelStatus
from .exceptions import ModelCacheError

logger = logging.getLogger("aibef.registry.cache")


class ModelCache:
    """LRU cache for loaded models with memory management.

    Thread-safe. Manages model instances, tokenizers, and associated
    metadata. Supports configurable maximum cache size and eviction.
    """

    def __init__(self, max_models: int = 3, max_size_mb: int = 4096):
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._max_models = max_models
        self._max_size_mb = max_size_mb
        self._current_size_mb = 0
        self._hit_count = 0
        self._miss_count = 0

    def get(self, model_id: str) -> Optional[dict[str, Any]]:
        """Get a cached model by ID. Moves to end (most recently used).

        Returns:
            Cached entry dict with keys: model, tokenizer, model_info, loaded_at, access_count.
            None if not cached.
        """
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                self._cache[model_id]["access_count"] += 1
                self._hit_count += 1
                logger.debug("Cache HIT for model '%s'", model_id)
                return self._cache[model_id]
            self._miss_count += 1
            logger.debug("Cache MISS for model '%s'", model_id)
            return None

    def put(self, model_id: str, model: Any, tokenizer: Any,
            model_info: ModelInfo, size_mb: float = 0.0) -> None:
        """Add a model to the cache. Evicts LRU if at capacity."""
        with self._lock:
            if model_id in self._cache:
                self._cache.move_to_end(model_id)
                self._cache[model_id]["model"] = model
                self._cache[model_id]["tokenizer"] = tokenizer
                self._cache[model_id]["access_count"] += 1
                return

            while len(self._cache) >= self._max_models:
                evicted_id, _ = self._cache.popitem(last=False)
                self._current_size_mb -= self._cache.get(evicted_id, {}).get("size_mb", 0)
                logger.info("Evicted model '%s' from cache", evicted_id)

            self._cache[model_id] = {
                "model": model,
                "tokenizer": tokenizer,
                "model_info": model_info,
                "loaded_at": time.time(),
                "access_count": 1,
                "size_mb": size_mb,
            }
            self._current_size_mb += size_mb
            model_info.status = ModelStatus.CACHED
            logger.info("Cached model '%s' (%.1f MB)", model_id, size_mb)

    def remove(self, model_id: str) -> bool:
        """Remove a model from the cache."""
        with self._lock:
            if model_id in self._cache:
                del self._cache[model_id]
                logger.info("Removed model '%s' from cache", model_id)
                return True
            return False

    def clear(self) -> int:
        """Clear all cached models. Returns number of models cleared."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._current_size_mb = 0
            logger.info("Cache cleared: %d models removed", count)
            return count

    def contains(self, model_id: str) -> bool:
        """Check if a model is cached."""
        with self._lock:
            return model_id in self._cache

    @property
    def size(self) -> int:
        """Number of models in cache."""
        with self._lock:
            return len(self._cache)

    @property
    def size_mb(self) -> float:
        """Estimated total size of cached models in MB."""
        with self._lock:
            return self._current_size_mb

    @property
    def hit_rate(self) -> float:
        """Cache hit rate as a fraction."""
        total = self._hit_count + self._miss_count
        return self._hit_count / total if total > 0 else 0.0

    @property
    def stats(self) -> dict[str, Any]:
        """Cache statistics."""
        with self._lock:
            return {
                "cached_models": list(self._cache.keys()),
                "size": len(self._cache),
                "max_size": self._max_models,
                "size_mb": round(self._current_size_mb, 1),
                "max_size_mb": self._max_size_mb,
                "hit_count": self._hit_count,
                "miss_count": self._miss_count,
                "hit_rate": round(self.hit_rate, 3),
            }

    def get_all_model_ids(self) -> list[str]:
        """Return all cached model IDs."""
        with self._lock:
            return list(self._cache.keys())
