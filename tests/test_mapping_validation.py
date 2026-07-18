"""Unit tests for Database Mapping Validation Agent."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import (
    BIBLIOMETRIX_MANDATORY_FIELDS,
    DATABASE_FIELD_MAPPINGS,
    MappingValidationConfig,
)
from core.models import (
    PipelineState,
    RecordStats,
    MappingFieldResult,
    UnmappedColumn,
    MetadataPreservationResult,
    MappingValidationResult,
)
from core.exceptions import MappingValidationError
from agents.agent_05b_mapping_validation import DatabaseMappingValidationAgent


def _make_config(**kwargs) -> MappingValidationConfig:
    return MappingValidationConfig(**kwargs)


def _make_state(
    cleaned_df: pd.DataFrame,
    master_df: pd.DataFrame = None,
    raw_datasets: dict = None,
    source_file: str = "test_file",
    output_dir: Path = None,
) -> PipelineState:
    config = MagicMock()
    config.output_dir = output_dir or Path("C:/temp/test_output")
    state = PipelineState(config=config)
    state.cleaned_dataset = cleaned_df
    state.master_dataset = master_df
    state.raw_datasets = raw_datasets or {}
    state.stats = RecordStats()
    return state


class TestModels:
    def test_mapping_field_result_creation(self):
        r = MappingFieldResult(
            source_field="Title", target_field="TI",
            mapped_records=100, missing_records=5,
            null_percentage=4.8, status="PASS",
        )
        assert r.source_field == "Title"
        assert r.target_field == "TI"
        assert r.mapped_records == 100
        assert r.missing_records == 5
        assert r.null_percentage == 4.8
        assert r.status == "PASS"

    def test_mapping_field_result_to_dict(self):
        r = MappingFieldResult(
            source_field="Title", target_field="TI",
            mapped_records=100, missing_records=5,
            null_percentage=4.8, status="PASS",
        )
        d = r.to_dict()
        assert d["source_field"] == "Title"
        assert d["target_field"] == "TI"
        assert d["status"] == "PASS"

    def test_unmapped_column_creation(self):
        u = UnmappedColumn(
            column_name="Funding",
            classification="OPTIONAL",
            suggestion="Column is optional",
        )
        assert u.column_name == "Funding"
        assert u.classification == "OPTIONAL"

    def test_unmapped_column_to_dict(self):
        u = UnmappedColumn(
            column_name="Funding", classification="OPTIONAL", suggestion="test"
        )
        d = u.to_dict()
        assert d["column_name"] == "Funding"
        assert d["classification"] == "OPTIONAL"

    def test_metadata_preservation_result_creation(self):
        m = MetadataPreservationResult(
            metric="Record Count",
            original_value="1000",
            normalized_value="995",
            difference="-5",
            classification="Configuration Driven",
        )
        assert m.metric == "Record Count"
        assert m.classification == "Configuration Driven"

    def test_mapping_validation_result_creation(self):
        r = MappingValidationResult(
            source_database="Web of Science",
            detected_format="TXT",
        )
        assert r.source_database == "Web of Science"
        assert r.overall_status == "PENDING"
        assert r.field_results == []

    def test_mapping_validation_result_to_dict(self):
        r = MappingValidationResult(
            source_database="PubMed", detected_format="CSV",
            field_coverage_score=95.0,
            mapping_quality_score=88.5,
            overall_status="PASS",
        )
        d = r.to_dict()
        assert d["source_database"] == "PubMed"
        assert d["field_coverage_score"] == 95.0
        assert d["overall_status"] == "PASS"

    def test_record_stats_has_mapping_field(self):
        s = RecordStats()
        assert hasattr(s, "mapping_validation_issues")
        assert s.mapping_validation_issues == 0


class TestAgentInit:
    def test_agent_default_config(self):
        agent = DatabaseMappingValidationAgent()
        assert agent.config.enabled is True
        assert agent.config.required_field_coverage == 95.0

    def test_agent_custom_config(self):
        config = MappingValidationConfig(enabled=False, required_field_coverage=80.0)
        agent = DatabaseMappingValidationAgent(config=config)
        assert agent.config.enabled is False
        assert agent.config.required_field_coverage == 80.0

    def test_agent_name(self):
        agent = DatabaseMappingValidationAgent()
        assert agent.NAME == "DatabaseMappingValidationAgent"


class TestDisabledAgent:
    def test_skip_when_disabled(self):
        agent = DatabaseMappingValidationAgent(
            config=MappingValidationConfig(enabled=False)
        )
        cleaned = pd.DataFrame({"TI": ["A"], "AU": ["B"]})
        state = _make_state(cleaned_df=cleaned)
        state = agent.execute(state)
        assert state.mapping_validation_result is None
        assert state.stats.mapping_validation_issues == 0


class TestNoDataset:
    def test_raises_when_no_dataset(self):
        agent = DatabaseMappingValidationAgent()
        state = PipelineState(config=MagicMock())
        state.cleaned_dataset = None
        with pytest.raises(MappingValidationError, match="No cleaned dataset"):
            agent.execute(state)

    def test_raises_when_empty_dataset(self):
        agent = DatabaseMappingValidationAgent()
        state = PipelineState(config=MagicMock())
        state.cleaned_dataset = pd.DataFrame()
        with pytest.raises(MappingValidationError, match="No cleaned dataset"):
            agent.execute(state)


class TestWoSMapping:
    def test_wos_detection(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO", "PY", "UT", "AB"])}
        cleaned = pd.DataFrame({
            "AU": ["Author1"], "TI": ["Title1"], "SO": ["Journal1"],
            "PY": [2024], "DT": ["Article"], "DI": ["10.1234/test"],
            "DE": ["kw1"], "ID": ["kw2"], "CR": ["ref1"],
            "C1": ["Aff1"], "RP": ["Author1"], "TC": [5],
            "LA": ["English"], "UT": ["WOS:001"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.source_database == "Web of Science"
        assert result.detected_format == "TXT"

    def test_wos_mandatory_fields_present(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO", "PY"])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
            "PY": [2024], "DT": ["Article"], "DI": ["10.1/x"],
            "DE": ["k"], "ID": ["k2"], "CR": ["r"],
            "C1": ["aff"], "RP": ["A"], "TC": [1],
            "LA": ["English"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        mandatory_results = [
            f for f in result.field_results
            if f.target_field in BIBLIOMETRIX_MANDATORY_FIELDS
        ]
        for fr in mandatory_results:
            assert fr.status in ("PASS", "NOT_AVAILABLE_FROM_SOURCE")

    def test_wos_missing_mandatory_field(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO"])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        failed = [f for f in result.field_results if f.status == "FAILED"]
        assert len(failed) > 0


class TestScopusMapping:
    def test_scopus_detection(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"scopus.csv": pd.DataFrame(columns=["Title", "Authors", "Source", "Year", "DOI"])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
            "PY": [2024], "DT": ["Article"], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": ["English"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.source_database == "Scopus"

    def test_scopus_field_mapping(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"scopus.csv": pd.DataFrame(columns=["Title", "Authors", "DOI", "Year"])}
        original = pd.DataFrame({
            "Title": ["Test Title"], "Authors": ["Author1"], "DOI": ["10.1/x"], "Year": [2024],
        })
        cleaned = pd.DataFrame({
            "AU": ["Author1"], "TI": ["Test Title"], "SO": [""],
            "PY": [2024], "DT": [""], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.mapping_quality_score > 0


class TestDimensionsMapping:
    def test_dimensions_detection(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"Agarwood.csv": pd.DataFrame(columns=[
            "Publication ID", "Title", "DOI", "PubYear", "Authors", "Source title", "Times cited",
        ])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
            "PY": [2024], "DT": [""], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [5],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.source_database == "Dimensions"

    def test_dimensions_field_mapping(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"data.csv": pd.DataFrame(columns=[
            "Title", "DOI", "PubYear", "Authors", "Times cited",
        ])}
        original = pd.DataFrame({
            "Title": ["Title1"], "DOI": ["10.1/x"], "PubYear": [2024],
            "Authors": ["Author1"], "Times cited": [10],
        })
        cleaned = pd.DataFrame({
            "AU": ["Author1"], "TI": ["Title1"], "SO": [""],
            "PY": [2024], "DT": [""], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [10],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        ti_result = [f for f in result.field_results if f.target_field == "TI"]
        assert len(ti_result) > 0
        assert ti_result[0].mapped_records == 1


class TestPubMedMapping:
    def test_pubmed_detection(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"pubmed.csv": pd.DataFrame(columns=[
            "PMID", "Title", "DOI", "Authors", "Journal/Book", "Publication Year",
        ])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
            "PY": [2024], "DT": [""], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": [""], "UT": ["12345"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.source_database == "PubMed"


class TestMetadataPreservation:
    def test_record_count_preserved(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO"])}
        original = pd.DataFrame({
            "AU": ["A1", "A2", "A3"], "TI": ["T1", "T2", "T3"],
            "SO": ["S1", "S2", "S3"],
        })
        cleaned = pd.DataFrame({
            "AU": ["A1", "A2", "A3"], "TI": ["T1", "T2", "T3"],
            "SO": ["S1", "S2", "S3"],
            "PY": [2024, 2024, 2024], "DT": ["Article"] * 3,
            "DI": ["10.1/x", "10.1/y", "10.1/z"],
            "DE": [""] * 3, "ID": [""] * 3, "CR": [""] * 3,
            "C1": [""] * 3, "RP": [""] * 3, "TC": [0] * 3,
            "LA": ["English"] * 3,
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        rc = [m for m in result.metadata_preservation if m.metric == "Record Count"]
        assert len(rc) > 0
        assert rc[0].original_value == "3"
        assert rc[0].normalized_value == "3"

    def test_unexpected_loss_detected(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI"])}
        original = pd.DataFrame({
            "AU": ["A"] * 100, "TI": ["T"] * 100,
        })
        cleaned = pd.DataFrame({
            "AU": ["A"] * 50, "TI": ["T"] * 50,
            "PY": [2024] * 50, "DT": ["Article"] * 50,
            "DI": [""] * 50, "DE": [""] * 50, "ID": [""] * 50,
            "CR": [""] * 50, "C1": [""] * 50, "RP": [""] * 50,
            "TC": [0] * 50, "LA": ["English"] * 50,
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        unexpected = [m for m in result.metadata_preservation if m.classification == "Unexpected"]
        assert len(unexpected) > 0


class TestUnmappedColumns:
    def test_unmapped_columns_detected(self):
        agent = DatabaseMappingValidationAgent(
            config=MappingValidationConfig(report_unmapped_columns=True)
        )
        raw = {"data.csv": pd.DataFrame(columns=["Title", "Authors", "DOI"])}
        original = pd.DataFrame({
            "Title": ["T"], "Authors": ["A"], "DOI": ["10.1/x"],
            "Funding": ["NSF Grant"], "CustomField": ["value"],
        })
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": [""],
            "PY": [2024], "DT": [""], "DI": ["10.1/x"],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert len(result.unmapped_columns) > 0

    def test_unmapped_disabled(self):
        agent = DatabaseMappingValidationAgent(
            config=MappingValidationConfig(report_unmapped_columns=False)
        )
        raw = {"data.csv": pd.DataFrame(columns=["Title"])}
        original = pd.DataFrame({"Title": ["T"], "Extra": ["E"]})
        cleaned = pd.DataFrame({
            "AU": [""], "TI": ["T"], "SO": [""],
            "PY": [2024], "DT": [""], "DI": [""],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, master_df=original, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert len(result.unmapped_columns) == 0


class TestCoverageScore:
    def test_perfect_coverage(self):
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        for field in BIBLIOMETRIX_MANDATORY_FIELDS:
            result.field_results.append(MappingFieldResult(
                source_field=field, target_field=field,
                mapped_records=100, missing_records=0,
                null_percentage=0.0, status="PASS",
            ))
        agent = DatabaseMappingValidationAgent()
        agent._calculate_field_coverage_score(result)
        assert result.field_coverage_score == 100.0

    def test_partial_coverage(self):
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        fields = BIBLIOMETRIX_MANDATORY_FIELDS[:5]
        for i, field in enumerate(fields):
            result.field_results.append(MappingFieldResult(
                source_field=field, target_field=field,
                mapped_records=100, missing_records=0,
                null_percentage=0.0,
                status="PASS" if i < 4 else "FAILED",
            ))
        agent = DatabaseMappingValidationAgent()
        agent._calculate_field_coverage_score(result)
        assert result.field_coverage_score < 100.0

    def test_zero_coverage(self):
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        agent = DatabaseMappingValidationAgent()
        agent._calculate_field_coverage_score(result)
        assert result.field_coverage_score == 0.0


class TestQualityScore:
    def test_high_quality(self):
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.field_coverage_score = 100.0
        for field in BIBLIOMETRIX_MANDATORY_FIELDS:
            result.field_results.append(MappingFieldResult(
                source_field=field, target_field=field,
                mapped_records=100, missing_records=0,
                null_percentage=0.0, status="PASS",
            ))
        result.metadata_preservation.append(MetadataPreservationResult(
            metric="Record Count", original_value="100", normalized_value="100",
            difference="0", classification="Expected",
        ))
        agent = DatabaseMappingValidationAgent()
        agent._calculate_mapping_quality_score(result)
        assert result.mapping_quality_score > 80.0

    def test_low_quality(self):
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.field_coverage_score = 50.0
        for field in BIBLIOMETRIX_MANDATORY_FIELDS:
            result.field_results.append(MappingFieldResult(
                source_field=field, target_field=field,
                mapped_records=0, missing_records=100,
                null_percentage=100.0, status="FAILED",
            ))
        result.warnings.append("Multiple failures")
        agent = DatabaseMappingValidationAgent()
        agent._calculate_mapping_quality_score(result)
        assert result.mapping_quality_score < 50.0


class TestOverallStatus:
    def test_pass_status(self):
        agent = DatabaseMappingValidationAgent()
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.field_coverage_score = 100.0
        agent._determine_overall_status(result)
        assert result.overall_status == "PASS"

    def test_warning_status(self):
        agent = DatabaseMappingValidationAgent()
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.field_coverage_score = 100.0
        result.warnings.append("Some warning")
        agent._determine_overall_status(result)
        assert result.overall_status == "WARNING"

    def test_failed_status(self):
        agent = DatabaseMappingValidationAgent()
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.field_results.append(MappingFieldResult(
            source_field="X", target_field="Y",
            mapped_records=0, missing_records=100,
            null_percentage=100.0, status="FAILED",
        ))
        agent._determine_overall_status(result)
        assert result.overall_status == "FAILED"

    def test_failed_on_unexpected_loss(self):
        agent = DatabaseMappingValidationAgent()
        result = MappingValidationResult(source_database="Test", detected_format="TXT")
        result.metadata_preservation.append(MetadataPreservationResult(
            metric="Record Count", original_value="100", normalized_value="50",
            difference="-50", classification="Unexpected",
        ))
        agent._determine_overall_status(result)
        assert result.overall_status == "FAILED"


class TestUnknownDatabase:
    def test_unknown_database_gets_warning(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"random.txt": pd.DataFrame(columns=["Col1", "Col2", "Col3"])}
        cleaned = pd.DataFrame({
            "AU": [""], "TI": [""], "SO": [""],
            "PY": [2024], "DT": [""], "DI": [""],
            "DE": [""], "ID": [""], "CR": [""],
            "C1": [""], "RP": [""], "TC": [0],
            "LA": [""],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        result = state.mapping_validation_result
        assert result.source_database == "Unknown"
        assert result.overall_status == "WARNING"


class TestRegressionStability:
    def test_run_twice_same_result(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO", "PY"])}
        cleaned = pd.DataFrame({
            "AU": ["A"], "TI": ["T"], "SO": ["S"],
            "PY": [2024], "DT": ["Article"], "DI": ["10.1/x"],
            "DE": ["k"], "ID": ["k2"], "CR": ["r"],
            "C1": ["aff"], "RP": ["A"], "TC": [5],
            "LA": ["English"],
        })

        state1 = _make_state(cleaned_df=cleaned.copy(), raw_datasets=raw)
        state1 = agent.execute(state1)
        result1 = state1.mapping_validation_result

        agent2 = DatabaseMappingValidationAgent()
        state2 = _make_state(cleaned_df=cleaned.copy(), raw_datasets=raw)
        state2 = agent2.execute(state2)
        result2 = state2.mapping_validation_result

        assert result1.source_database == result2.source_database
        assert result1.field_coverage_score == result2.field_coverage_score
        assert result1.mapping_quality_score == result2.mapping_quality_score
        assert result1.overall_status == result2.overall_status

    def test_all_field_statuses_are_valid(self):
        agent = DatabaseMappingValidationAgent()
        raw = {"0.txt": pd.DataFrame(columns=["PT", "AU", "TI", "SO", "PY"])}
        cleaned = pd.DataFrame({
            "AU": ["A", "B"], "TI": ["T1", "T2"], "SO": ["S1", "S2"],
            "PY": [2024, 2023], "DT": ["Article", "Review"],
            "DI": ["10.1/x", ""], "DE": ["k", ""], "ID": ["k2", ""],
            "CR": ["r", ""], "C1": ["aff", ""], "RP": ["A", "B"],
            "TC": [5, 0], "LA": ["English", "English"],
        })
        state = _make_state(cleaned_df=cleaned, raw_datasets=raw)
        state = agent.execute(state)
        valid_statuses = {"PASS", "WARNING", "FAILED", "NOT_AVAILABLE_FROM_SOURCE"}
        for fr in state.mapping_validation_result.field_results:
            assert fr.status in valid_statuses
