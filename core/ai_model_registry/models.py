"""Data models for the Global AI Model Registry."""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ModelCapability(str, Enum):
    """Supported AI model capabilities."""
    EMBEDDING = "embedding"
    SEMANTIC_SEARCH = "semantic_search"
    KEYWORD_EXTRACTION = "keyword_extraction"
    NAMED_ENTITY_RECOGNITION = "named_entity_recognition"
    TEXT_CLASSIFICATION = "text_classification"
    TOPIC_MODELLING = "topic_modelling"
    SCIENTIFIC_SUMMARIZATION = "scientific_summarization"
    SEQUENCE_TO_SEQUENCE = "sequence_to_sequence"
    INFORMATION_EXTRACTION = "information_extraction"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    DOCUMENT_RANKING = "document_ranking"
    BIOMEDICAL_NLP = "biomedical_nlp"
    AGRICULTURAL_NLP = "agricultural_nlp"
    GENERAL_SCIENTIFIC_NLP = "general_scientific_nlp"
    TEXT_GENERATION = "text_generation"
    TEXT_CLASSIFICATION_ZERO_SHOT = "text_classification_zero_shot"
    FILL_MASK = "fill_mask"
    QUESTION_ANSWERING = "question_answering"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"


class ModelStatus(str, Enum):
    """Model lifecycle status."""
    REGISTERED = "registered"
    VERIFIED = "verified"
    AVAILABLE = "available"
    CACHED = "cached"
    LOADED = "loaded"
    UNAVAILABLE = "unavailable"
    DEPRECATED = "deprecated"
    ERROR = "error"


class InferenceBackend(str, Enum):
    """Supported inference backends."""
    TRANSFORMERS = "transformers"
    SENTENCE_TRANSFORMERS = "sentence_transformers"
    PIPELINE = "pipeline"
    CUSTOM = "custom"


@dataclass
class ModelInfo:
    """Complete information about a registered model."""
    model_id: str
    model_path: str
    display_name: str
    version: str = "1.0.0"
    capabilities: list[ModelCapability] = field(default_factory=list)
    backend: InferenceBackend = InferenceBackend.TRANSFORMERS
    task: str = ""
    domain: str = "general"
    priority: int = 0
    max_sequence_length: int = 512
    embedding_dim: int = 0
    parameters: str = ""
    status: ModelStatus = ModelStatus.REGISTERED
    local_path: Optional[str] = None
    checksum: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    fallback_ids: list[str] = field(default_factory=list)
    config_overrides: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_path": self.model_path,
            "display_name": self.display_name,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "backend": self.backend.value,
            "task": self.task,
            "domain": self.domain,
            "priority": self.priority,
            "max_sequence_length": self.max_sequence_length,
            "embedding_dim": self.embedding_dim,
            "parameters": self.parameters,
            "status": self.status.value,
            "local_path": self.local_path,
            "checksum": self.checksum,
            "metadata": self.metadata,
            "fallback_ids": self.fallback_ids,
            "config_overrides": self.config_overrides,
        }


@dataclass
class ModelRequest:
    """A request for a model from the registry."""
    task: str
    domain: str = "general"
    preferred_capability: Optional[ModelCapability] = None
    required_capabilities: list[ModelCapability] = field(default_factory=list)
    exclude_ids: list[str] = field(default_factory=list)
    max_model_size: Optional[str] = None
    prefer_local: bool = True
    allow_fallback: bool = True
    request_id: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.request_id:
            raw = f"{self.task}:{self.domain}:{self.timestamp}"
            self.request_id = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ModelResponse:
    """Response from the registry containing selected model information."""
    request_id: str
    model: ModelInfo
    all_candidates: list[ModelInfo] = field(default_factory=list)
    fallback_used: bool = False
    fallback_chain: list[str] = field(default_factory=list)
    selection_reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "model_id": self.model.model_id,
            "model_path": self.model.model_path,
            "version": self.model.version,
            "capabilities": [c.value for c in self.model.capabilities],
            "fallback_used": self.fallback_used,
            "fallback_chain": self.fallback_chain,
            "selection_reason": self.selection_reason,
            "timestamp": self.timestamp,
        }


@dataclass
class InferenceRecord:
    """Record of a single AI inference for provenance tracking."""
    record_id: str = ""
    registry_version: str = "1.0.0"
    model_id: str = ""
    model_version: str = ""
    model_path: str = ""
    capability: str = ""
    task: str = ""
    domain: str = ""
    fallback_used: bool = False
    inference_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    input_length: int = 0
    output_length: int = 0
    success: bool = True
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "registry_version": self.registry_version,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_path": self.model_path,
            "capability": self.capability,
            "task": self.task,
            "domain": self.domain,
            "fallback_used": self.fallback_used,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "timestamp": self.timestamp,
            "input_length": self.input_length,
            "output_length": self.output_length,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class RegistryStats:
    """Aggregate statistics for the registry."""
    total_models: int = 0
    verified_models: int = 0
    loaded_models: int = 0
    total_requests: int = 0
    total_inferences: int = 0
    total_fallbacks: int = 0
    total_errors: int = 0
    avg_inference_time_ms: float = 0.0
    models_by_capability: dict[str, int] = field(default_factory=dict)
    models_by_domain: dict[str, int] = field(default_factory=dict)
    last_request_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_models": self.total_models,
            "verified_models": self.verified_models,
            "loaded_models": self.loaded_models,
            "total_requests": self.total_requests,
            "total_inferences": self.total_inferences,
            "total_fallbacks": self.total_fallbacks,
            "total_errors": self.total_errors,
            "avg_inference_time_ms": round(self.avg_inference_time_ms, 2),
            "models_by_capability": self.models_by_capability,
            "models_by_domain": self.models_by_domain,
            "last_request_time": self.last_request_time,
        }
