"""Model verification — local path, version, and integrity checks."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from .models import ModelInfo, ModelStatus
from .exceptions import ModelVerificationError

logger = logging.getLogger("aibef.registry.verifier")

_RULE_BASED_ID = "__rule_based__"


def verify_local_path(model: ModelInfo) -> bool:
    """Check if the model's local path exists and is accessible.

    Returns:
        True if the model is locally available.
    """
    if model.model_path == _RULE_BASED_ID:
        return True

    if model.local_path:
        path = Path(model.local_path)
        if path.exists() and path.is_dir():
            has_files = any(path.iterdir())
            if has_files:
                logger.info("Model '%s' found at %s", model.model_id, model.local_path)
                return True
            logger.warning("Model '%s' path exists but is empty: %s",
                           model.model_id, model.local_path)
            return False

    cache_path = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{model.model_path.replace('/', '--')}"
    if cache_path.exists():
        model.local_path = str(cache_path)
        logger.info("Model '%s' found in HF cache: %s", model.model_id, cache_path)
        return True

    return False


def verify_version(model: ModelInfo, required_version: Optional[str] = None) -> bool:
    """Verify model version compatibility.

    Args:
        model: Model info to check.
        required_version: Minimum required version (semver-like comparison).

    Returns:
        True if version is compatible.
    """
    if required_version is None:
        return True

    model_parts = tuple(int(x) for x in model.version.split(".") if x.isdigit())
    req_parts = tuple(int(x) for x in required_version.split(".") if x.isdigit())

    if not req_parts:
        return True
    if not model_parts:
        return False

    return model_parts >= req_parts


def compute_file_checksum(file_path: str | Path, algorithm: str = "sha256") -> str:
    """Compute checksum of a file.

    Args:
        file_path: Path to the file.
        algorithm: Hash algorithm (sha256, md5, etc.).

    Returns:
        Hex digest of the checksum.
    """
    path = Path(file_path)
    if not path.exists():
        raise ModelVerificationError(f"File not found: {path}")

    hasher = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def verify_model_integrity(model: ModelInfo) -> tuple[bool, str]:
    """Comprehensive integrity check for a model.

    Returns:
        Tuple of (is_valid, message).
    """
    if model.model_path == _RULE_BASED_ID:
        return True, "Rule-based model, no integrity check needed"

    if not verify_local_path(model):
        return False, f"Local path not found for {model.model_id}"

    if model.checksum and model.local_path:
        path = Path(model.local_path)
        if path.is_file():
            try:
                computed = compute_file_checksum(path)
                if computed != model.checksum:
                    return False, (
                        f"Checksum mismatch: expected {model.checksum}, "
                        f"got {computed}"
                    )
            except ModelVerificationError:
                return False, f"Cannot compute checksum for {model.local_path}"

    if not verify_version(model):
        return False, f"Version {model.version} does not meet requirements"

    return True, "All integrity checks passed"
