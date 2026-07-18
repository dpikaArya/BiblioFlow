"""Model factory — create model instances, pipelines, and inference wrappers."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from .models import (
    InferenceBackend, InferenceRecord, ModelInfo, ModelResponse, ModelStatus,
)
from .model_loader import load_model, estimate_model_size_mb
from .model_cache import ModelCache
from .exceptions import InferenceError, ModelLoadError

logger = logging.getLogger("aibef.registry.factory")

_RULE_BASED_ID = "__rule_based__"


class ModelInstance:
    """A loaded model ready for inference.

    Wraps the raw model and tokenizer, provides inference methods,
    and tracks provenance.
    """

    def __init__(
        self,
        model_info: ModelInfo,
        model: Any,
        tokenizer: Any = None,
        fallback_used: bool = False,
    ):
        self.model_info = model_info
        self.model = model
        self.tokenizer = tokenizer
        self.fallback_used = fallback_used
        self._inference_count = 0

    @property
    def is_rule_based(self) -> bool:
        return self.model is None and self.tokenizer is None

    @property
    def model_id(self) -> str:
        return self.model_info.model_id

    @property
    def capabilities(self):
        return self.model_info.capabilities

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_new_tokens: int = 512,
        temperature: float = 0.3,
        top_p: float = 0.9,
    ) -> str:
        """Generate text from a prompt.

        Returns:
            Generated text, or rule-based fallback response.
        """
        if self.is_rule_based:
            self._inference_count += 1
            return self._rule_based_generate(prompt)

        record = InferenceRecord(
            model_id=self.model_info.model_id,
            model_version=self.model_info.model_version,
            model_path=self.model_info.model_path,
            capability="text_generation",
            task="generate",
            domain=self.model_info.domain,
            fallback_used=self.fallback_used,
            input_length=len(prompt),
        )
        start = time.time()

        try:
            import torch
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.tokenizer([text], return_tensors="pt").to(
                self.model.device
            )
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    do_sample=temperature > 0,
                    top_p=top_p,
                )
            response = self.tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )
            result = response.strip()

            record.output_length = len(result)
            record.success = True
            return result

        except Exception as e:
            record.success = False
            record.error_message = str(e)
            logger.warning("Inference failed for '%s': %s. Using fallback.",
                           self.model_id, e)
            return self._rule_based_generate(prompt)
        finally:
            elapsed = (time.time() - start) * 1000
            record.inference_time_ms = elapsed
            self._inference_count += 1

    def encode(self, texts: list[str]) -> Any:
        """Encode texts into embeddings (for sentence-transformer models)."""
        if self.is_rule_based:
            raise InferenceError("Rule-based model does not support encoding")

        if hasattr(self.model, "encode"):
            return self.model.encode(texts, show_progress_bar=False)

        raise InferenceError(
            f"Model '{self.model_id}' does not support encoding"
        )

    def classify(self, text: str, labels: list[str] | None = None) -> Any:
        """Classify text (for pipeline models)."""
        if self.is_rule_based:
            return self._rule_based_classify(text, labels)

        if callable(self.model):
            return self.model(text)

        raise InferenceError(
            f"Model '{self.model_id}' does not support classification"
        )

    @property
    def inference_count(self) -> int:
        return self._inference_count

    def _rule_based_generate(self, prompt: str) -> str:
        """Rule-based fallback generation."""
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

    def _rule_based_classify(self, text: str, labels: list[str] | None = None) -> dict:
        """Rule-based fallback classification."""
        if labels:
            return {"label": labels[0], "score": 0.5}
        return {"label": "unknown", "score": 0.0}


def create_model_instance(
    response: ModelResponse,
    cache: ModelCache,
    device: str = "auto",
    dtype: str = "auto",
    offline: bool = True,
) -> ModelInstance:
    """Create a ModelInstance from a registry response.

    This is the factory method that all AI components should use
    (indirectly through the registry).

    Args:
        response: The ModelResponse from the registry.
        cache: The model cache.
        device: Target device.
        dtype: Data type.
        offline: Offline mode.

    Returns:
        ModelInstance ready for inference.
    """
    model_info = response.model

    if model_info.model_path == _RULE_BASED_ID:
        logger.info("Creating rule-based model instance")
        return ModelInstance(
            model_info=model_info,
            model=None,
            tokenizer=None,
            fallback_used=response.fallback_used,
        )

    try:
        size_mb = estimate_model_size_mb(model_info)
        model, tokenizer = load_model(
            model_info, cache, device=device, dtype=dtype, offline=offline
        )
        return ModelInstance(
            model_info=model_info,
            model=model,
            tokenizer=tokenizer,
            fallback_used=response.fallback_used,
        )
    except ModelLoadError:
        logger.warning("Model load failed, falling back to rule-based")
        rule_info = ModelInfo(
            model_id="rule_based",
            model_path="__rule_based__",
            display_name="Rule-Based Fallback",
            capabilities=[],
            backend=InferenceBackend.CUSTOM,
        )
        return ModelInstance(
            model_info=rule_info,
            model=None,
            tokenizer=None,
            fallback_used=True,
        )
