"""Global AI Model Registry — the central API for all AI model operations.

This is the single source of truth for ALL AI models in AIBEF.
No AI component shall directly load, instantiate, or hard-code any model.
All AI components must request models exclusively through this registry.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from .models import (
    InferenceBackend, InferenceRecord, ModelCapability, ModelInfo,
    ModelRequest, ModelResponse, ModelStatus, RegistryStats,
)
from .registry_loader import load_registry_config, parse_model_info
from .registry_validator import verify_model, verify_all_models
from .model_selector import select_model
from .model_loader import load_model, estimate_model_size_mb
from .model_verifier import verify_local_path
from .model_cache import ModelCache
from .model_factory import ModelInstance, create_model_instance
from .exceptions import (
    ModelNotFoundError, RegistryConfigError, NoModelAvailableError,
    ModelLoadError,
)

logger = logging.getLogger("aibef.registry")

REGISTRY_VERSION = "1.0.0"


class ModelRegistry:
    """Global AI Model Registry.

    The single source of truth for all AI models used throughout AIBEF.
    Provides centralized model management, selection, loading, caching,
    and provenance tracking.

    Usage:
        registry = ModelRegistry()
        instance = registry.request_model(
            task="keyword_generation",
            domain="general",
        )
        response = instance.generate("Normalize these keywords: ...")
    """

    _instance: Optional[ModelRegistry] = None

    def __init__(self, config_path: Optional[Path] = None, offline: bool = True):
        """Initialize the registry.

        Args:
            config_path: Path to model_registry.json. Uses default if None.
            offline: If True, operate in offline mode (no downloads).
        """
        self._offline = offline
        self._config: dict[str, Any] = {}
        self._models: dict[str, ModelInfo] = {}
        self._verified_models: list[ModelInfo] = []
        self._unavailable_models: list[ModelInfo] = []
        self._fallback_chain: list[str] = []
        self._cache = ModelCache()
        self._inference_log: list[InferenceRecord] = []
        self._total_requests = 0
        self._total_inferences = 0
        self._total_fallbacks = 0
        self._total_errors = 0
        self._inference_times: list[float] = []

        try:
            self._config = load_registry_config(config_path)
            self._initialize_models()
        except RegistryConfigError as e:
            logger.warning("Registry config error: %s. Using minimal defaults.", e)
            self._initialize_defaults()

        ModelRegistry._instance = self

    def _initialize_models(self) -> None:
        """Parse config and verify all registered models."""
        for model_def in self._config.get("models", []):
            model_info = parse_model_info(model_def)
            self._models[model_info.model_id] = model_info

        self._fallback_chain = self._config.get("fallback_chain", ["rule_based"])

        cache_cfg = self._config.get("cache", {})
        self._cache = ModelCache(
            max_models=cache_cfg.get("max_loaded_models", 3),
            max_size_mb=cache_cfg.get("max_cache_size_mb", 4096),
        )

        self._verified_models, self._unavailable_models = verify_all_models(
            list(self._models.values()), offline=self._offline
        )

        verified_ids = {m.model_id for m in self._verified_models}
        unavailable_ids = {m.model_id for m in self._unavailable_models}

        for mid, minfo in self._models.items():
            if mid in verified_ids:
                minfo.status = ModelStatus.AVAILABLE
            elif mid in unavailable_ids:
                minfo.status = ModelStatus.UNAVAILABLE
            else:
                if minfo.model_path == "__rule_based__":
                    minfo.status = ModelStatus.AVAILABLE
                else:
                    minfo.status = ModelStatus.UNAVAILABLE

        logger.info("Registry initialized: %d models registered, %d verified, %d unavailable",
                     len(self._models), len(self._verified_models),
                     len(self._unavailable_models))

    def _initialize_defaults(self) -> None:
        """Initialize with minimal defaults when config is unavailable."""
        self._models = {
            "rule_based": ModelInfo(
                model_id="rule_based",
                model_path="__rule_based__",
                display_name="Rule-Based Fallback",
                capabilities=[ModelCapability.TEXT_GENERATION],
                backend=InferenceBackend.CUSTOM,
                task="fallback",
                domain="general",
                status=ModelStatus.AVAILABLE,
            )
        }
        self._verified_models = [self._models["rule_based"]]
        self._fallback_chain = ["rule_based"]
        self._cache = ModelCache(max_models=3)

    # ── Public API ────────────────────────────────────────────────────

    def request_model(
        self,
        task: str,
        domain: str = "general",
        preferred_capability: Optional[ModelCapability] = None,
        required_capabilities: Optional[list[ModelCapability]] = None,
        exclude_ids: Optional[list[str]] = None,
        allow_fallback: bool = True,
    ) -> ModelInstance:
        """Request a model for a specific task.

        This is the primary API for all AI components.

        Args:
            task: The task identifier (e.g., "keyword_generation").
            domain: Research domain (e.g., "biomedical", "general").
            preferred_capability: Preferred model capability.
            required_capabilities: Capabilities that must be present.
            exclude_ids: Model IDs to exclude from selection.
            allow_fallback: Whether to use fallback chain.

        Returns:
            ModelInstance ready for inference.
        """
        self._total_requests += 1

        request = ModelRequest(
            task=task,
            domain=domain,
            preferred_capability=preferred_capability,
            required_capabilities=required_capabilities or [],
            exclude_ids=exclude_ids or [],
            allow_fallback=allow_fallback,
        )

        task_defaults = self._config.get("task_defaults", {}).get(task, {})
        if not preferred_capability and "preferred_capability" in task_defaults:
            cap_str = task_defaults["preferred_capability"]
            try:
                request.preferred_capability = ModelCapability(cap_str)
            except ValueError:
                pass
        if domain == "general" and "domain" in task_defaults:
            request.domain = task_defaults["domain"]

        try:
            response = select_model(
                request,
                self._verified_models + [self._models.get("rule_based", self._verified_models[0])],
                fallback_chain=self._fallback_chain,
            )
        except NoModelAvailableError:
            rule_model = self._models.get("rule_based")
            if rule_model and allow_fallback:
                response = ModelResponse(
                    request_id=request.request_id,
                    model=rule_model,
                    fallback_used=True,
                    fallback_chain=self._fallback_chain,
                    selection_reason="Forced rule-based fallback",
                )
            else:
                raise

        if response.fallback_used:
            self._total_fallbacks += 1

        instance = create_model_instance(
            response, self._cache, offline=self._offline
        )

        logger.info("Model '%s' dispatched for task='%s', domain='%s' (fallback=%s)",
                     instance.model_id, task, domain, response.fallback_used)
        return instance

    def get_model_info(self, model_id: str) -> ModelInfo:
        """Get information about a registered model."""
        if model_id not in self._models:
            raise ModelNotFoundError(f"Model not found: {model_id}")
        return self._models[model_id]

    def list_models(
        self,
        capability: Optional[ModelCapability] = None,
        domain: Optional[str] = None,
        status: Optional[ModelStatus] = None,
    ) -> list[ModelInfo]:
        """List registered models with optional filters."""
        models = list(self._models.values())
        if capability:
            models = [m for m in models if capability in m.capabilities]
        if domain:
            models = [m for m in models if m.domain == domain or m.domain == "general"]
        if status:
            models = [m for m in models if m.status == status]
        return models

    def register_model(self, model_info: ModelInfo) -> None:
        """Register a new model at runtime."""
        self._models[model_info.model_id] = model_info
        verified = verify_model(model_info, offline=self._offline)
        if verified.status in (ModelStatus.AVAILABLE, ModelStatus.CACHED):
            self._verified_models.append(verified)
        else:
            self._unavailable_models.append(verified)
        logger.info("Registered model '%s' (status=%s)", model_info.model_id, verified.status.value)

    def unregister_model(self, model_id: str) -> bool:
        """Remove a model from the registry."""
        if model_id not in self._models:
            return False
        del self._models[model_id]
        self._verified_models = [m for m in self._verified_models if m.model_id != model_id]
        self._unavailable_models = [m for m in self._unavailable_models if m.model_id != model_id]
        self._cache.remove(model_id)
        logger.info("Unregistered model '%s'", model_id)
        return True

    def record_inference(self, record: InferenceRecord) -> None:
        """Record an inference for provenance tracking."""
        self._inference_log.append(record)
        self._total_inferences += 1
        if record.inference_time_ms > 0:
            self._inference_times.append(record.inference_time_ms)
        if not record.success:
            self._total_errors += 1

    def get_inference_log(self) -> list[dict[str, Any]]:
        """Get all inference records as dicts."""
        return [r.to_dict() for r in self._inference_log]

    def get_stats(self) -> RegistryStats:
        """Get aggregate registry statistics."""
        stats = RegistryStats(
            total_models=len(self._models),
            verified_models=len(self._verified_models),
            loaded_models=self._cache.size,
            total_requests=self._total_requests,
            total_inferences=self._total_inferences,
            total_fallbacks=self._total_fallbacks,
            total_errors=self._total_errors,
        )
        if self._inference_times:
            stats.avg_inference_time_ms = sum(self._inference_times) / len(self._inference_times)
        for model in self._models.values():
            for cap in model.capabilities:
                cap_str = cap.value
                stats.models_by_capability[cap_str] = stats.models_by_capability.get(cap_str, 0) + 1
            stats.models_by_domain[model.domain] = stats.models_by_domain.get(model.domain, 0) + 1
        if self._inference_log:
            stats.last_request_time = self._inference_log[-1].timestamp
        return stats

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self._cache.stats

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def offline(self) -> bool:
        return self._offline

    @classmethod
    def instance(cls) -> ModelRegistry:
        """Get the singleton instance, creating if necessary."""
        if cls._instance is None:
            cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        if cls._instance is not None:
            cls._instance._cache.clear()
        cls._instance = None
