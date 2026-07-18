"""Validate models in the registry — local paths, checksums, compatibility."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from .models import ModelInfo, ModelStatus
from .exceptions import ModelVerificationError

logger = logging.getLogger("aibef.registry.validator")

_RULE_BASED_PATH = "__rule_based__"


def verify_model(model: ModelInfo, offline: bool = True) -> ModelInfo:
    """Verify a model is locally available and update its status.

    Checks:
    1. Rule-based models are always available.
    2. Local path exists if specified.
    3. Checksum matches if specified.
    4. Model can be resolved via its backend.

    Args:
        model: The model info to verify.
        offline: If True, only check local availability (no downloads).

    Returns:
        Updated ModelInfo with verification status.
    """
    if model.model_path == _RULE_BASED_PATH:
        model.status = ModelStatus.AVAILABLE
        logger.info("Model '%s' is rule-based, always available", model.model_id)
        return model

    if model.local_path and Path(model.local_path).exists():
        model.status = ModelStatus.AVAILABLE
        if model.checksum:
            _verify_checksum(model)
        logger.info("Model '%s' verified at local_path: %s", model.model_id, model.local_path)
        return model

    if not offline:
        try:
            return _verify_remote(model)
        except Exception as e:
            logger.warning("Remote verification failed for '%s': %s", model.model_id, e)

    model.status = ModelStatus.UNAVAILABLE
    logger.warning("Model '%s' not available locally at '%s'",
                   model.model_id, model.model_path)
    return model


def _verify_checksum(model: ModelInfo) -> None:
    """Verify file checksum if specified."""
    if not model.local_path or not model.checksum:
        return
    path = Path(model.local_path)
    if not path.is_file():
        return
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    computed = sha256.hexdigest()
    if computed != model.checksum:
        model.status = ModelStatus.ERROR
        raise ModelVerificationError(
            f"Checksum mismatch for {model.model_id}: "
            f"expected {model.checksum}, got {computed}"
        )
    logger.info("Checksum verified for %s", model.model_id)


def _verify_remote(model: ModelInfo) -> ModelInfo:
    """Verify model availability on HuggingFace Hub (only when offline=False)."""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        api.model_info(model.model_path, offline=False)
        model.status = ModelStatus.AVAILABLE
        logger.info("Model '%s' verified on HuggingFace Hub", model.model_id)
        return model
    except Exception as e:
        model.status = ModelStatus.UNAVAILABLE
        raise ModelVerificationError(
            f"Cannot verify '{model.model_path}' on Hub: {e}"
        )


def verify_all_models(
    models: list[ModelInfo], offline: bool = True
) -> tuple[list[ModelInfo], list[ModelInfo]]:
    """Verify all models and return (verified, unavailable) lists.

    Args:
        models: List of ModelInfo to verify.
        offline: If True, only check local paths.

    Returns:
        Tuple of (verified_models, unavailable_models).
    """
    verified = []
    unavailable = []
    for model in models:
        try:
            result = verify_model(model, offline=offline)
            if result.status in (ModelStatus.AVAILABLE, ModelStatus.CACHED, ModelStatus.LOADED):
                verified.append(result)
            else:
                unavailable.append(result)
        except ModelVerificationError as e:
            model.status = ModelStatus.ERROR
            unavailable.append(model)
            logger.error("Verification error for '%s': %s", model.model_id, e)
    return verified, unavailable
