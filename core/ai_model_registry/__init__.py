"""Global AI Model Registry — AIBEF framework-wide model management.

This module is the single source of truth for ALL AI models used
throughout the AIBEF framework. No AI component shall directly load,
instantiate, or hard-code any Transformer model.

Usage:
    from core.ai_model_registry import ModelRegistry, ModelCapability

    registry = ModelRegistry()
    instance = registry.request_model(
        task="keyword_generation",
        domain="general",
    )
    response = instance.generate("Normalize these keywords: ...")
"""
from .models import (
    InferenceBackend,
    InferenceRecord,
    ModelCapability,
    ModelInfo,
    ModelRequest,
    ModelResponse,
    ModelStatus,
    RegistryStats,
)
from .registry import ModelRegistry, REGISTRY_VERSION
from .model_factory import ModelInstance
from .exceptions import (
    InferenceError,
    ModelCacheError,
    ModelLoadError,
    ModelNotFoundError,
    ModelVerificationError,
    NoModelAvailableError,
    RegistryConfigError,
    RegistryError,
)

__all__ = [
    "ModelRegistry",
    "ModelInstance",
    "ModelCapability",
    "ModelInfo",
    "ModelRequest",
    "ModelResponse",
    "ModelStatus",
    "InferenceBackend",
    "InferenceRecord",
    "RegistryStats",
    "REGISTRY_VERSION",
    "RegistryError",
    "ModelNotFoundError",
    "ModelLoadError",
    "ModelVerificationError",
    "ModelCacheError",
    "NoModelAvailableError",
    "RegistryConfigError",
    "InferenceError",
]
