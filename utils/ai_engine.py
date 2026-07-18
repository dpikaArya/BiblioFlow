"""Local AI engine using Hugging Face Transformers.

This module provides the LocalAIEngine class used by AI agents for
inference. It delegates to the Global AI Model Registry for model
management, loading, and caching.

Backward-compatible: existing agents that use LocalAIEngine continue
to work unchanged. Internally, all model operations go through the
ModelRegistry singleton.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("aibef.ai_engine")

_registry = None
_registry_lock = threading.Lock()


def _get_registry():
    """Lazy-initialize the global registry singleton."""
    global _registry
    if _registry is not None:
        return _registry
    with _registry_lock:
        if _registry is not None:
            return _registry
        try:
            from core.ai_model_registry import ModelRegistry
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_DATASETS_OFFLINE"] = "1"
            _registry = ModelRegistry(offline=True)
            logger.info("AI Model Registry initialized")
        except Exception as e:
            logger.warning("Registry init failed: %s. Using direct loading.", e)
            _registry = None
    return _registry


def load_model(model_name: str = "Qwen/Qwen2-0.5B-Instruct"):
    """Load model lazily. Thread-safe.

    This function maintains backward compatibility with existing code
    that calls load_model() directly. Internally, it uses the registry
    when available, falling back to direct loading.

    Returns:
        Tuple of (model, tokenizer) or (None, None).
    """
    registry = _get_registry()
    if registry is not None:
        try:
            instance = registry.request_model(
                task="text_generation",
                domain="general",
            )
            return instance.model, instance.tokenizer
        except Exception as e:
            logger.warning("Registry request failed: %s. Direct loading.", e)

    return _direct_load(model_name)


def _direct_load(model_name: str):
    """Direct model loading fallback (original implementation)."""
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(
            model_name, trust_remote_code=True
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=dtype,
            device_map="auto" if device == "cuda" else None,
            trust_remote_code=True,
        )
        if device == "cpu":
            model = model.to("cpu")

        logger.info("Model loaded directly: %s on %s", model_name, device)
        return model, tokenizer
    except Exception as e:
        logger.warning("Failed to load model %s: %s. Using rule-based fallback.", model_name, e)
        return None, None


class LocalAIEngine:
    """Interface for local transformer inference.

    Backward-compatible with existing usage:
        ai = LocalAIEngine(model_name="Qwen/Qwen2-0.5B-Instruct")
        response = ai.generate(prompt, system_prompt=system)

    Internally delegates to the Global AI Model Registry.
    """

    def __init__(self, model_name: str = "Qwen/Qwen2-0.5B-Instruct",
                 temperature: float = 0.3, max_tokens: int = 512):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._instance = None

    def generate(self, prompt: str, system_prompt: str = "") -> str:
        """Generate text from a prompt.

        Delegates to the registry when available, falls back to direct
        loading.
        """
        if self._instance is None:
            self._load()

        if self._instance is not None:
            try:
                return self._instance.generate(
                    prompt,
                    system_prompt=system_prompt,
                    max_new_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
            except Exception as e:
                logger.warning("Registry inference failed: %s", e)

        return self._fallback_generate(prompt)

    def _load(self):
        """Load the model through the registry or directly."""
        registry = _get_registry()
        if registry is not None:
            try:
                self._instance = registry.request_model(
                    task="text_generation",
                    domain="general",
                )
                return
            except Exception as e:
                logger.warning("Registry dispatch failed: %s", e)

        model, tokenizer = _direct_load(self.model_name)
        if model is not None:
            try:
                from core.ai_model_registry.model_factory import ModelInstance, ModelInfo
                from core.ai_model_registry.models import InferenceBackend, ModelStatus
                info = ModelInfo(
                    model_id="direct_loaded",
                    model_path=self.model_name,
                    display_name=self.model_name,
                    backend=InferenceBackend.TRANSFORMERS,
                    status=ModelStatus.LOADED,
                )
                self._instance = ModelInstance(
                    model_info=info, model=model, tokenizer=tokenizer
                )
            except ImportError:
                self._instance = None

    def _fallback_generate(self, prompt: str) -> str:
        """Rule-based fallback when model is unavailable."""
        prompt_lower = prompt.lower()
        if "harmoniz" in prompt_lower or "standardize" in prompt_lower:
            return "Apply standard normalization rules."
        if "keyword" in prompt_lower:
            return "Normalize keywords by standardizing abbreviations and removing duplicates."
        if "author" in prompt_lower:
            return "Standardize author names using Last, Initials format."
        if "journal" in prompt_lower:
            return "Verify journal name against standard abbreviations."
        if "prisma" in prompt_lower:
            return "Generate PRISMA flow narrative based on the provided statistics."
        if "screening" in prompt_lower:
            return "Include study based on title and abstract relevance criteria."
        if "institution" in prompt_lower or "affiliation" in prompt_lower:
            return "Harmonize institutional affiliations to standard forms."
        return "Process according to standard bibliometric guidelines."

    def batch_generate(self, prompts: list[str],
                       system_prompt: str = "") -> list[str]:
        """Process multiple prompts."""
        return [self.generate(p, system_prompt) for p in prompts]
