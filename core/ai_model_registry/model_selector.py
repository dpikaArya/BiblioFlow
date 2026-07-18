"""Select the best model for a given task/request."""
from __future__ import annotations

import logging
from typing import Optional

from .models import (
    ModelCapability, ModelInfo, ModelRequest, ModelResponse, ModelStatus,
)
from .exceptions import NoModelAvailableError

logger = logging.getLogger("aibef.registry.selector")


def select_model(
    request: ModelRequest,
    available_models: list[ModelInfo],
    fallback_chain: list[str] | None = None,
) -> ModelResponse:
    """Select the best model for a request from available models.

    Selection algorithm:
    1. Filter by required capabilities (if any).
    2. Filter by domain match (prefer exact, allow general).
    3. Exclude explicitly excluded model IDs.
    4. Filter by availability status.
    5. Score remaining candidates.
    6. Sort by score (descending), then priority (descending).
    7. If no match, follow fallback chain.

    Args:
        request: The model request.
        available_models: Models available for selection.
        fallback_chain: Ordered list of fallback model IDs.

    Returns:
        ModelResponse with the selected model.

    Raises:
        NoModelAvailableError: If no model can be selected.
    """
    fallback_chain = fallback_chain or []

    candidates = _filter_candidates(request, available_models)

    if candidates:
        scored = [(m, _score_model(m, request)) for m in candidates]
        scored.sort(key=lambda x: (x[1], x[0].priority), reverse=True)
        best = scored[0][0]
        reason = f"Best match for task='{request.task}', domain='{request.domain}'"
        logger.info("Selected model '%s' (score=%.2f) for task='%s'",
                     best.model_id, scored[0][1], request.task)
        return ModelResponse(
            request_id=request.request_id,
            model=best,
            all_candidates=[m for m, _ in scored],
            fallback_used=False,
            selection_reason=reason,
        )

    if request.allow_fallback and fallback_chain:
        return _apply_fallback(request, available_models, fallback_chain)

    raise NoModelAvailableError(
        f"No model found for task='{request.task}', domain='{request.domain}'"
    )


def _filter_candidates(
    request: ModelRequest, models: list[ModelInfo]
) -> list[ModelInfo]:
    """Filter models based on request constraints."""
    result = []
    for model in models:
        if model.model_id in request.exclude_ids:
            continue
        if model.status in (ModelStatus.UNAVAILABLE, ModelStatus.ERROR, ModelStatus.DEPRECATED):
            continue
        if model.model_path == "__rule_based__":
            continue
        if request.required_capabilities:
            if not all(c in model.capabilities for c in request.required_capabilities):
                continue
        if request.preferred_capability:
            if request.preferred_capability not in model.capabilities:
                continue
        result.append(model)
    return result


def _score_model(model: ModelInfo, request: ModelRequest) -> float:
    """Score a model for a request. Higher is better."""
    score = 0.0

    domain_match = _domain_match_score(model.domain, request.domain)
    score += domain_match * 40.0

    if request.preferred_capability and request.preferred_capability in model.capabilities:
        score += 30.0

    if model.status == ModelStatus.CACHED:
        score += 15.0
    elif model.status == ModelStatus.LOADED:
        score += 20.0

    score += min(model.priority, 10)

    if model.parameters:
        try:
            size_str = model.parameters.upper().replace("M", "").replace("B", "")
            size_val = float(size_str)
            if "B" in model.parameters.upper():
                size_val *= 1000
            if size_val <= 500:
                score += 5.0
        except (ValueError, AttributeError):
            pass

    return score


def _domain_match_score(model_domain: str, request_domain: str) -> float:
    """Score domain match. Exact=1.0, general=0.5, mismatch=0.0."""
    if model_domain == request_domain:
        return 1.0
    if model_domain == "general" or request_domain == "general":
        return 0.5
    return 0.0


def _apply_fallback(
    request: ModelRequest,
    available_models: list[ModelInfo],
    fallback_chain: list[str],
) -> ModelResponse:
    """Apply the fallback chain when no primary model matches."""
    model_map = {m.model_id: m for m in available_models}

    for fb_id in fallback_chain:
        if fb_id in request.exclude_ids:
            continue
        if fb_id in model_map:
            model = model_map[fb_id]
            if model.status in (ModelStatus.UNAVAILABLE, ModelStatus.ERROR):
                continue
            logger.info("Using fallback model '%s' for task='%s'", fb_id, request.task)
            return ModelResponse(
                request_id=request.request_id,
                model=model,
                all_candidates=[],
                fallback_used=True,
                fallback_chain=fallback_chain,
                selection_reason=f"Fallback: no primary match for task='{request.task}'",
            )

    raise NoModelAvailableError(
        f"No model available (including fallbacks) for task='{request.task}'"
    )
