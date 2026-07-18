"""Tests for the Global AI Model Registry."""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.ai_model_registry.models import (
    InferenceBackend, InferenceRecord, ModelCapability, ModelInfo,
    ModelRequest, ModelResponse, ModelStatus, RegistryStats,
)
from core.ai_model_registry.exceptions import (
    ModelLoadError, ModelNotFoundError, ModelVerificationError,
    NoModelAvailableError, RegistryConfigError, RegistryError,
    InferenceError,
)
from core.ai_model_registry.registry_loader import (
    load_registry_config, parse_model_info,
)
from core.ai_model_registry.registry_validator import (
    verify_model, verify_all_models,
)
from core.ai_model_registry.model_selector import select_model
from core.ai_model_registry.model_cache import ModelCache
from core.ai_model_registry.model_verifier import (
    verify_local_path, verify_version, compute_file_checksum,
    verify_model_integrity,
)
from core.ai_model_registry.model_loader import estimate_model_size_mb
from core.ai_model_registry.model_factory import ModelInstance, create_model_instance
from core.ai_model_registry.registry import ModelRegistry, REGISTRY_VERSION


# ── Models ────────────────────────────────────────────────────────────

class TestModelCapability:
    def test_all_capabilities_exist(self):
        caps = [
            "embedding", "semantic_search", "keyword_extraction",
            "named_entity_recognition", "text_classification",
            "topic_modelling", "scientific_summarization",
            "sequence_to_sequence", "information_extraction",
            "semantic_similarity", "document_ranking",
            "biomedical_nlp", "agricultural_nlp", "general_scientific_nlp",
            "text_generation",
        ]
        for c in caps:
            assert ModelCapability(c) is not None

    def test_invalid_capability(self):
        with pytest.raises(ValueError):
            ModelCapability("nonexistent_capability")


class TestModelInfo:
    def test_creation(self):
        info = ModelInfo(
            model_id="test-model",
            model_path="org/test-model",
            display_name="Test Model",
        )
        assert info.model_id == "test-model"
        assert info.status == ModelStatus.REGISTERED
        assert info.priority == 0

    def test_to_dict(self):
        info = ModelInfo(
            model_id="test",
            model_path="org/test",
            display_name="Test",
            capabilities=[ModelCapability.TEXT_GENERATION],
        )
        d = info.to_dict()
        assert d["model_id"] == "test"
        assert "text_generation" in d["capabilities"]
        assert d["status"] == "registered"

    def test_rule_based(self):
        info = ModelInfo(
            model_id="rule_based",
            model_path="__rule_based__",
            display_name="Rule-Based",
        )
        assert info.model_path == "__rule_based__"


class TestModelRequest:
    def test_default_request_id(self):
        r1 = ModelRequest(task="test")
        r2 = ModelRequest(task="test")
        assert r1.request_id != r2.request_id

    def test_custom_request_id(self):
        r = ModelRequest(task="test", request_id="custom-id")
        assert r.request_id == "custom-id"


class TestModelResponse:
    def test_to_dict(self):
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        resp = ModelResponse(request_id="r1", model=info)
        d = resp.to_dict()
        assert d["model_id"] == "m1"
        assert d["fallback_used"] is False


class TestInferenceRecord:
    def test_to_dict(self):
        rec = InferenceRecord(model_id="m1", capability="text_generation")
        d = rec.to_dict()
        assert d["model_id"] == "m1"
        assert d["success"] is True


class TestRegistryStats:
    def test_to_dict(self):
        stats = RegistryStats(total_models=5)
        d = stats.to_dict()
        assert d["total_models"] == 5


# ── Registry Loader ──────────────────────────────────────────────────

class TestRegistryLoader:
    def test_load_default_config(self):
        config = load_registry_config()
        assert "models" in config
        assert len(config["models"]) > 0
        assert config["registry_version"] == "1.0.0"

    def test_load_custom_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "registry_version": "2.0.0",
                "models": [
                    {
                        "model_id": "custom",
                        "model_path": "org/custom",
                        "display_name": "Custom",
                    }
                ]
            }, f)
            f.flush()
            config = load_registry_config(Path(f.name))
            assert config["registry_version"] == "2.0.0"
        os.unlink(f.name)

    def test_missing_config(self):
        with pytest.raises(RegistryConfigError):
            load_registry_config(Path("/nonexistent/config.json"))

    def test_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()
            with pytest.raises(RegistryConfigError):
                load_registry_config(Path(f.name))
        os.unlink(f.name)

    def test_missing_models_key(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"registry_version": "1.0.0"}, f)
            f.flush()
            with pytest.raises(RegistryConfigError):
                load_registry_config(Path(f.name))
        os.unlink(f.name)

    def test_parse_model_info(self):
        model_def = {
            "model_id": "test",
            "model_path": "org/test",
            "display_name": "Test",
            "capabilities": ["text_generation", "embedding"],
            "backend": "transformers",
            "priority": 10,
        }
        info = parse_model_info(model_def)
        assert info.model_id == "test"
        assert ModelCapability.TEXT_GENERATION in info.capabilities
        assert ModelCapability.EMBEDDING in info.capabilities
        assert info.priority == 10
        assert info.backend == InferenceBackend.TRANSFORMERS

    def test_parse_unknown_capability(self):
        model_def = {
            "model_id": "test",
            "model_path": "org/test",
            "display_name": "Test",
            "capabilities": ["unknown_cap"],
        }
        info = parse_model_info(model_def)
        assert len(info.capabilities) == 1
        assert info.capabilities[0] == ModelCapability.GENERAL_SCIENTIFIC_NLP


# ── Registry Validator ───────────────────────────────────────────────

class TestRegistryValidator:
    def test_verify_rule_based(self):
        info = ModelInfo(
            model_id="rb", model_path="__rule_based__", display_name="RB"
        )
        result = verify_model(info, offline=True)
        assert result.status == ModelStatus.AVAILABLE

    def test_verify_unavailable(self):
        info = ModelInfo(
            model_id="missing",
            model_path="org/missing",
            display_name="Missing",
        )
        result = verify_model(info, offline=True)
        assert result.status == ModelStatus.UNAVAILABLE

    def test_verify_all_models(self):
        models = [
            ModelInfo(model_id="rb1", model_path="__rule_based__", display_name="RB1"),
            ModelInfo(model_id="miss1", model_path="org/miss1", display_name="Miss1"),
        ]
        verified, unavailable = verify_all_models(models, offline=True)
        assert len(verified) == 1
        assert len(unavailable) == 1
        assert verified[0].model_id == "rb1"

    def test_checksum_mismatch(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".bin", delete=False) as f:
            f.write("model data here")
            f.flush()
            tmppath = f.name
        try:
            info = ModelInfo(
                model_id="test",
                model_path="org/test",
                display_name="Test",
                checksum="wrong_checksum",
                local_path=tmppath,
            )
            with pytest.raises(ModelVerificationError):
                verify_model(info, offline=True)
        finally:
            os.unlink(tmppath)


# ── Model Selector ───────────────────────────────────────────────────

class TestModelSelector:
    def _make_models(self):
        return [
            ModelInfo(
                model_id="gen", model_path="org/gen", display_name="Gen",
                capabilities=[ModelCapability.TEXT_GENERATION],
                domain="general", priority=10, status=ModelStatus.AVAILABLE,
            ),
            ModelInfo(
                model_id="emb", model_path="org/emb", display_name="Emb",
                capabilities=[ModelCapability.EMBEDDING],
                domain="general", priority=10, status=ModelStatus.AVAILABLE,
            ),
            ModelInfo(
                model_id="bio", model_path="org/bio", display_name="Bio",
                capabilities=[ModelCapability.EMBEDDING, ModelCapability.BIOMEDICAL_NLP],
                domain="biomedical", priority=5, status=ModelStatus.AVAILABLE,
            ),
            ModelInfo(
                model_id="cached", model_path="org/cached", display_name="Cached",
                capabilities=[ModelCapability.TEXT_GENERATION],
                domain="general", priority=5, status=ModelStatus.CACHED,
            ),
        ]

    def test_select_by_task(self):
        models = self._make_models()
        request = ModelRequest(task="text_generation", preferred_capability=ModelCapability.TEXT_GENERATION)
        resp = select_model(request, models)
        assert resp.model.model_id in ("gen", "cached")

    def test_select_by_domain(self):
        models = self._make_models()
        request = ModelRequest(
            task="biomedical_ner",
            domain="biomedical",
            preferred_capability=ModelCapability.BIOMEDICAL_NLP,
        )
        resp = select_model(request, models)
        assert resp.model.model_id == "bio"

    def test_select_excludes(self):
        models = self._make_models()
        request = ModelRequest(
            task="text_generation",
            preferred_capability=ModelCapability.TEXT_GENERATION,
            exclude_ids=["gen"],
        )
        resp = select_model(request, models)
        assert resp.model.model_id != "gen"

    def test_select_no_match_fallback(self):
        models = self._make_models()
        request = ModelRequest(
            task="nonexistent",
            preferred_capability=ModelCapability.TOPIC_MODELLING,
        )
        resp = select_model(request, models, fallback_chain=["gen", "emb"])
        assert resp.fallback_used is True

    def test_select_no_match_no_fallback(self):
        models = self._make_models()
        request = ModelRequest(
            task="nonexistent",
            preferred_capability=ModelCapability.TOPIC_MODELLING,
            allow_fallback=False,
        )
        with pytest.raises(NoModelAvailableError):
            select_model(request, models)

    def test_select_avoids_unavailable(self):
        models = [
            ModelInfo(
                model_id="unavail", model_path="org/u", display_name="U",
                capabilities=[ModelCapability.TEXT_GENERATION],
                status=ModelStatus.UNAVAILABLE,
            ),
            ModelInfo(
                model_id="avail", model_path="org/a", display_name="A",
                capabilities=[ModelCapability.TEXT_GENERATION],
                status=ModelStatus.AVAILABLE,
            ),
        ]
        request = ModelRequest(
            task="text_generation",
            preferred_capability=ModelCapability.TEXT_GENERATION,
        )
        resp = select_model(request, models)
        assert resp.model.model_id == "avail"

    def test_select_prefers_cached(self):
        models = self._make_models()
        request = ModelRequest(
            task="text_generation",
            preferred_capability=ModelCapability.TEXT_GENERATION,
        )
        resp = select_model(request, models)
        assert resp.model.model_id == "cached"

    def test_select_empty_models_fallback(self):
        request = ModelRequest(task="test")
        rule = ModelInfo(
            model_id="rule_based", model_path="__rule_based__",
            display_name="Rule", status=ModelStatus.AVAILABLE,
        )
        resp = select_model(request, [rule], fallback_chain=["rule_based"])
        assert resp.fallback_used is True


# ── Model Cache ──────────────────────────────────────────────────────

class TestModelCache:
    def test_put_and_get(self):
        cache = ModelCache(max_models=3)
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        cache.put("m1", "model_obj", "tokenizer_obj", info, size_mb=100.0)
        entry = cache.get("m1")
        assert entry is not None
        assert entry["model"] == "model_obj"
        assert cache.size == 1

    def test_cache_miss(self):
        cache = ModelCache()
        assert cache.get("nonexistent") is None
        assert cache.size == 0

    def test_lru_eviction(self):
        cache = ModelCache(max_models=2)
        for i in range(3):
            info = ModelInfo(model_id=f"m{i}", model_path="p", display_name=f"M{i}")
            cache.put(f"m{i}", f"model_{i}", None, info)
        assert cache.size == 2
        assert cache.get("m0") is None

    def test_lru_access_refreshes(self):
        cache = ModelCache(max_models=2)
        for i in range(2):
            info = ModelInfo(model_id=f"m{i}", model_path="p", display_name=f"M{i}")
            cache.put(f"m{i}", f"model_{i}", None, info)
        cache.get("m0")
        info = ModelInfo(model_id="m2", model_path="p", display_name="M2")
        cache.put("m2", "model_2", None, info)
        assert cache.get("m0") is not None
        assert cache.get("m1") is None

    def test_remove(self):
        cache = ModelCache()
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        cache.put("m1", "m", None, info)
        assert cache.remove("m1") is True
        assert cache.get("m1") is None
        assert cache.remove("m1") is False

    def test_clear(self):
        cache = ModelCache()
        for i in range(3):
            info = ModelInfo(model_id=f"m{i}", model_path="p", display_name=f"M{i}")
            cache.put(f"m{i}", f"model_{i}", None, info)
        count = cache.clear()
        assert count == 3
        assert cache.size == 0

    def test_hit_rate(self):
        cache = ModelCache()
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        cache.put("m1", "m", None, info)
        cache.get("m1")
        cache.get("m2")
        assert cache.hit_rate == 0.5

    def test_stats(self):
        cache = ModelCache(max_models=5)
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        cache.put("m1", "m", None, info, size_mb=10.0)
        stats = cache.stats
        assert stats["size"] == 1
        assert stats["max_size"] == 5
        assert "m1" in stats["cached_models"]

    def test_contains(self):
        cache = ModelCache()
        info = ModelInfo(model_id="m1", model_path="p", display_name="M1")
        cache.put("m1", "m", None, info)
        assert cache.contains("m1") is True
        assert cache.contains("m2") is False

    def test_get_all_model_ids(self):
        cache = ModelCache()
        for i in range(3):
            info = ModelInfo(model_id=f"m{i}", model_path="p", display_name=f"M{i}")
            cache.put(f"m{i}", f"model_{i}", None, info)
        ids = cache.get_all_model_ids()
        assert set(ids) == {"m0", "m1", "m2"}


# ── Model Verifier ───────────────────────────────────────────────────

class TestModelVerifier:
    def test_verify_local_path_rule_based(self):
        info = ModelInfo(model_id="rb", model_path="__rule_based__", display_name="RB")
        assert verify_local_path(info) is True

    def test_verify_local_path_missing(self):
        info = ModelInfo(
            model_id="missing", model_path="org/missing",
            display_name="Missing", local_path="/nonexistent/path",
        )
        assert verify_local_path(info) is False

    def test_verify_version_equal(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", version="2.0.0"
        )
        assert verify_version(info, "2.0.0") is True

    def test_verify_version_greater(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", version="2.1.0"
        )
        assert verify_version(info, "2.0.0") is True

    def test_verify_version_less(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", version="1.0.0"
        )
        assert verify_version(info, "2.0.0") is False

    def test_verify_version_no_requirement(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", version="1.0.0"
        )
        assert verify_version(info) is True

    def test_compute_checksum(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            f.flush()
            checksum = compute_file_checksum(f.name)
            assert len(checksum) == 64
            assert checksum == compute_file_checksum(f.name)
        os.unlink(f.name)

    def test_compute_checksum_missing(self):
        with pytest.raises(ModelVerificationError):
            compute_file_checksum("/nonexistent/file")

    def test_integrity_rule_based(self):
        info = ModelInfo(model_id="rb", model_path="__rule_based__", display_name="RB")
        ok, msg = verify_model_integrity(info)
        assert ok is True

    def test_integrity_missing_path(self):
        info = ModelInfo(
            model_id="m", model_path="org/m", display_name="M",
            local_path="/nonexistent",
        )
        ok, msg = verify_model_integrity(info)
        assert ok is False


# ── Model Loader ─────────────────────────────────────────────────────

class TestModelLoader:
    def test_estimate_size_mb(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", parameters="500M"
        )
        assert estimate_model_size_mb(info) == 500.0

    def test_estimate_size_gb(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", parameters="7B"
        )
        assert estimate_model_size_mb(info) == 7000.0

    def test_estimate_size_empty(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", parameters=""
        )
        assert estimate_model_size_mb(info) == 0.0

    def test_estimate_size_zero(self):
        info = ModelInfo(
            model_id="m", model_path="p", display_name="M", parameters="0"
        )
        assert estimate_model_size_mb(info) == 0.0


# ── Model Factory ────────────────────────────────────────────────────

class TestModelFactory:
    def test_rule_based_instance(self):
        info = ModelInfo(
            model_id="rule_based", model_path="__rule_based__",
            display_name="Rule-Based",
        )
        resp = ModelResponse(request_id="r1", model=info)
        cache = ModelCache()
        instance = create_model_instance(resp, cache, offline=True)
        assert instance.is_rule_based
        assert instance.model_id == "rule_based"

    def test_rule_based_generate(self):
        info = ModelInfo(
            model_id="rule_based", model_path="__rule_based__",
            display_name="Rule-Based",
        )
        instance = ModelInstance(model_info=info, model=None, tokenizer=None)
        result = instance.generate("Normalize these keywords")
        assert "keyword" in result.lower() or "normalize" in result.lower()

    def test_rule_based_classify(self):
        info = ModelInfo(
            model_id="rule_based", model_path="__rule_based__",
            display_name="Rule-Based",
        )
        instance = ModelInstance(model_info=info, model=None, tokenizer=None)
        result = instance.classify("test text", labels=["a", "b"])
        assert "label" in result

    def test_inference_count(self):
        info = ModelInfo(
            model_id="rule_based", model_path="__rule_based__",
            display_name="Rule-Based",
        )
        instance = ModelInstance(model_info=info, model=None, tokenizer=None)
        assert instance.inference_count == 0
        instance.generate("test")
        assert instance.inference_count == 1


# ── Model Registry (Integration) ─────────────────────────────────────

class TestModelRegistry:
    def test_singleton(self):
        ModelRegistry.reset()
        r1 = ModelRegistry()
        r2 = ModelRegistry.instance()
        assert r1 is r2
        ModelRegistry.reset()

    def test_init_default(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        assert reg.offline is True
        assert len(reg.list_models()) > 0
        ModelRegistry.reset()

    def test_request_rule_based(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        instance = reg.request_model(task="test_task")
        assert instance is not None
        assert instance.model_id is not None
        ModelRegistry.reset()

    def test_list_models(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        all_models = reg.list_models()
        assert len(all_models) >= 1
        gen_models = reg.list_models(capability=ModelCapability.TEXT_GENERATION)
        assert len(gen_models) >= 1
        ModelRegistry.reset()

    def test_get_model_info(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        models = reg.list_models()
        if models:
            info = reg.get_model_info(models[0].model_id)
            assert info.model_id == models[0].model_id
        ModelRegistry.reset()

    def test_get_model_info_not_found(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        with pytest.raises(ModelNotFoundError):
            reg.get_model_info("nonexistent_model_id")
        ModelRegistry.reset()

    def test_register_unregister(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        new_model = ModelInfo(
            model_id="test_new", model_path="__rule_based__",
            display_name="Test New",
        )
        reg.register_model(new_model)
        assert reg.get_model_info("test_new") is not None
        assert reg.unregister_model("test_new") is True
        with pytest.raises(ModelNotFoundError):
            reg.get_model_info("test_new")
        ModelRegistry.reset()

    def test_unregister_nonexistent(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        assert reg.unregister_model("nonexistent") is False
        ModelRegistry.reset()

    def test_stats(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        stats = reg.get_stats()
        assert stats.total_models > 0
        ModelRegistry.reset()

    def test_cache_stats(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        stats = reg.get_cache_stats()
        assert "size" in stats
        assert "hit_count" in stats
        ModelRegistry.reset()

    def test_inference_log(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        rec = InferenceRecord(model_id="test", task="test")
        reg.record_inference(rec)
        log = reg.get_inference_log()
        assert len(log) == 1
        assert log[0]["model_id"] == "test"
        ModelRegistry.reset()

    def test_config_property(self):
        ModelRegistry.reset()
        reg = ModelRegistry()
        assert isinstance(reg.config, dict)
        assert "models" in reg.config
        ModelRegistry.reset()


# ── Exceptions ───────────────────────────────────────────────────────

class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(ModelNotFoundError, RegistryError)
        assert issubclass(ModelLoadError, RegistryError)
        assert issubclass(ModelVerificationError, RegistryError)
        assert issubclass(NoModelAvailableError, RegistryError)
        assert issubclass(RegistryConfigError, RegistryError)
        assert issubclass(InferenceError, RegistryError)

    def test_message(self):
        err = ModelNotFoundError("test message")
        assert str(err) == "test message"
