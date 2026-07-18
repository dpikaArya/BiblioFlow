"""Model loading — lazy loading, thread-safe, memory-managed."""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from .models import InferenceBackend, ModelInfo, ModelStatus
from .model_cache import ModelCache
from .exceptions import ModelLoadError

logger = logging.getLogger("aibef.registry.loader")

_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
}


def load_model(
    model_info: ModelInfo,
    cache: ModelCache,
    device: str = "auto",
    dtype: str = "auto",
    offline: bool = True,
) -> tuple[Any, Any]:
    """Load a model and its tokenizer, using cache when possible.

    This is the single entry point for model loading in the entire framework.
    All AI components must go through this function (or the registry that
    wraps it).

    Args:
        model_info: Model metadata from the registry.
        cache: The model cache instance.
        device: Target device ("auto", "cpu", "cuda").
        dtype: Data type ("auto", "float16", "float32").
        offline: If True, set offline environment variables.

    Returns:
        Tuple of (model, tokenizer) or (model, None) for non-tokenizer models.

    Raises:
        ModelLoadError: If loading fails and no fallback is available.
    """
    cached = cache.get(model_info.model_id)
    if cached is not None:
        logger.info("Using cached model '%s'", model_info.model_id)
        return cached["model"], cached["tokenizer"]

    if model_info.model_path == "__rule_based__":
        return None, None

    _set_offline_env(offline)

    backend = model_info.backend
    if backend == InferenceBackend.TRANSFORMERS:
        return _load_transformers(model_info, cache, device, dtype)
    elif backend == InferenceBackend.SENTENCE_TRANSFORMERS:
        return _load_sentence_transformers(model_info, cache)
    elif backend == InferenceBackend.PIPELINE:
        return _load_pipeline(model_info, cache)
    else:
        raise ModelLoadError(f"Unsupported backend: {backend}")


def _load_transformers(
    model_info: ModelInfo,
    cache: ModelCache,
    device: str,
    dtype: str,
) -> tuple[Any, Any]:
    """Load model via HuggingFace Transformers."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        actual_device = device
        if device == "auto":
            actual_device = "cuda" if torch.cuda.is_available() else "cpu"

        actual_dtype = torch.float32
        if dtype == "float16" or (dtype == "auto" and actual_device == "cuda"):
            actual_dtype = torch.float16

        overrides = model_info.config_overrides or {}
        trust_remote_code = overrides.get("trust_remote_code", True)

        logger.info("Loading model '%s' via Transformers on %s...",
                     model_info.model_id, actual_device)

        start = time.time()
        tokenizer = AutoTokenizer.from_pretrained(
            model_info.model_path,
            trust_remote_code=trust_remote_code,
            local_files_only=True if model_info.local_path else False,
        )

        load_kwargs = {
            "torch_dtype": actual_dtype,
            "trust_remote_code": trust_remote_code,
            "local_files_only": True if model_info.local_path else False,
        }

        if actual_device == "cuda":
            load_kwargs["device_map"] = overrides.get("device_map", "auto")
        else:
            load_kwargs["device_map"] = None

        model = AutoModelForCausalLM.from_pretrained(
            model_info.model_path, **load_kwargs
        )

        if actual_device == "cpu":
            model = model.to("cpu")

        elapsed = time.time() - start
        logger.info("Model '%s' loaded in %.1fs on %s",
                     model_info.model_id, elapsed, actual_device)

        model_info.status = ModelStatus.LOADED
        cache.put(model_info.model_id, model, tokenizer, model_info)

        return model, tokenizer

    except Exception as e:
        logger.error("Failed to load model '%s': %s", model_info.model_id, e)
        raise ModelLoadError(f"Cannot load {model_info.model_id}: {e}")


def _load_sentence_transformers(
    model_info: ModelInfo, cache: ModelCache
) -> tuple[Any, None]:
    """Load model via sentence-transformers (embedding models)."""
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformer model '%s'...", model_info.model_id)
        start = time.time()

        model = SentenceTransformer(
            model_info.model_path,
            local_files_only=bool(model_info.local_path),
        )

        elapsed = time.time() - start
        logger.info("Sentence-transformer '%s' loaded in %.1fs",
                     model_info.model_id, elapsed)

        model_info.status = ModelStatus.LOADED
        cache.put(model_info.model_id, model, None, model_info)

        return model, None

    except Exception as e:
        logger.error("Failed to load sentence-transformer '%s': %s",
                     model_info.model_id, e)
        raise ModelLoadError(f"Cannot load {model_info.model_id}: {e}")


def _load_pipeline(
    model_info: ModelInfo, cache: ModelCache
) -> tuple[Any, None]:
    """Load model via HuggingFace pipeline."""
    try:
        from transformers import pipeline as hf_pipeline

        logger.info("Loading pipeline model '%s'...", model_info.model_id)
        task = model_info.task or "text-classification"
        pipe = hf_pipeline(
            task,
            model=model_info.model_path,
            local_files_only=bool(model_info.local_path),
        )

        model_info.status = ModelStatus.LOADED
        cache.put(model_info.model_id, pipe, None, model_info)

        return pipe, None

    except Exception as e:
        logger.error("Failed to load pipeline '%s': %s", model_info.model_id, e)
        raise ModelLoadError(f"Cannot load {model_info.model_id}: {e}")


def _set_offline_env(offline: bool) -> None:
    """Set environment variables for offline operation."""
    if offline:
        for key, val in _OFFLINE_ENV.items():
            os.environ[key] = val
    else:
        for key in _OFFLINE_ENV:
            os.environ.pop(key, None)


def estimate_model_size_mb(model_info: ModelInfo) -> float:
    """Estimate model size in MB from its parameters string."""
    params = model_info.parameters.upper().strip()
    if not params or params == "0":
        return 0.0
    try:
        if "B" in params:
            return float(params.replace("B", "")) * 1000.0
        if "M" in params:
            return float(params.replace("M", ""))
        return float(params) / 1024.0
    except (ValueError, AttributeError):
        return 100.0
