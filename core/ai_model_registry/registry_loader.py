"""Load and parse the model registry configuration."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .models import ModelCapability, ModelInfo, InferenceBackend, ModelStatus
from .exceptions import RegistryConfigError

logger = logging.getLogger("aibef.registry.loader")

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "model_registry.json"


def load_registry_config(config_path: Optional[Path] = None) -> dict[str, Any]:
    """Load the model registry configuration from JSON.

    Args:
        config_path: Path to the JSON config file. Uses default if None.

    Returns:
        Parsed configuration dictionary.

    Raises:
        RegistryConfigError: If config file is missing or malformed.
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise RegistryConfigError(f"Registry config not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise RegistryConfigError(f"Invalid JSON in registry config: {e}")

    _validate_config_structure(config)
    return config


def _validate_config_structure(config: dict[str, Any]) -> None:
    """Validate the minimum required structure of the config."""
    required_keys = ["registry_version", "models"]
    for key in required_keys:
        if key not in config:
            raise RegistryConfigError(f"Missing required config key: {key}")

    if not isinstance(config["models"], list):
        raise RegistryConfigError("'models' must be a list")

    for i, model_def in enumerate(config["models"]):
        for field in ("model_id", "model_path", "display_name"):
            if field not in model_def:
                raise RegistryConfigError(
                    f"Model entry {i} missing required field: {field}"
                )


def parse_model_info(model_def: dict[str, Any]) -> ModelInfo:
    """Parse a model definition dict into a ModelInfo dataclass."""
    caps = []
    for c in model_def.get("capabilities", []):
        try:
            caps.append(ModelCapability(c))
        except ValueError:
            logger.warning("Unknown capability '%s' for model %s, skipping",
                           c, model_def.get("model_id"))
            caps.append(ModelCapability.GENERAL_SCIENTIFIC_NLP)

    backend_str = model_def.get("backend", "transformers")
    try:
        backend = InferenceBackend(backend_str)
    except ValueError:
        backend = InferenceBackend.TRANSFORMERS

    return ModelInfo(
        model_id=model_def["model_id"],
        model_path=model_def["model_path"],
        display_name=model_def["display_name"],
        version=model_def.get("version", "1.0.0"),
        capabilities=caps,
        backend=backend,
        task=model_def.get("task", ""),
        domain=model_def.get("domain", "general"),
        priority=model_def.get("priority", 0),
        max_sequence_length=model_def.get("max_sequence_length", 512),
        embedding_dim=model_def.get("embedding_dim", 0),
        parameters=model_def.get("parameters", ""),
        local_path=model_def.get("local_path"),
        checksum=model_def.get("checksum"),
        metadata=model_def.get("metadata", {}),
        fallback_ids=model_def.get("fallback_ids", []),
        config_overrides=model_def.get("config_overrides", {}),
    )
