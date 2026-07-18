"""Data models for AIBEF pipeline state."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
import pandas as pd


@dataclass
class RecordStats:
    total_imported: int = 0
    per_file: dict[str, int] = field(default_factory=dict)
    after_merge: int = 0
    duplicates_found: int = 0
    duplicates_removed: int = 0
    after_dedup: int = 0
    validation_issues: int = 0
    metadata_repairs: int = 0
    after_cleaning: int = 0
    after_harmonization: int = 0
    mapping_validation_issues: int = 0
    final_count: int = 0
    prisma_included: int = 0
    synchronized: bool = False


@dataclass
class DuplicateMapping:
    record_id: str
    duplicate_of: str
    match_type: str
    similarity_score: float
    source_file: str


@dataclass
class ValidationIssue:
    record_id: str
    field: str
    issue_type: str
    severity: str
    description: str
    source_file: str


@dataclass 
class CleaningAction:
    record_id: str
    field: str
    original_value: str
    cleaned_value: str
    action_type: str
    source_file: str


@dataclass
class MappingFieldResult:
    """Result of validating a single field mapping."""
    source_field: str
    target_field: str
    mapped_records: int
    missing_records: int
    null_percentage: float
    status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnmappedColumn:
    """An unmapped source column detected during validation."""
    column_name: str
    classification: str
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetadataPreservationResult:
    """Result of metadata preservation comparison."""
    metric: str
    original_value: Any
    normalized_value: Any
    difference: Any
    classification: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MappingValidationResult:
    """Complete result of the Database Mapping Validation."""
    source_database: str
    detected_format: str
    field_coverage_score: float = 0.0
    mapping_quality_score: float = 0.0
    overall_status: str = "PENDING"
    field_results: list[MappingFieldResult] = field(default_factory=list)
    unmapped_columns: list[UnmappedColumn] = field(default_factory=list)
    metadata_preservation: list[MetadataPreservationResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_database": self.source_database,
            "detected_format": self.detected_format,
            "field_coverage_score": self.field_coverage_score,
            "mapping_quality_score": self.mapping_quality_score,
            "overall_status": self.overall_status,
            "field_results": [f.to_dict() for f in self.field_results],
            "unmapped_columns": [u.to_dict() for u in self.unmapped_columns],
            "metadata_preservation": [m.to_dict() for m in self.metadata_preservation],
            "warnings": self.warnings,
            "recommendations": self.recommendations,
        }


@dataclass
class ProvenanceEntry:
    record_id: str
    source_file: str
    original_index: int
    final_index: Optional[int] = None
    transformations: list[str] = field(default_factory=list)
    status: str = "imported"


@dataclass
class PipelineState:
    """Immutable-ish state object passed between agents."""
    config: Any = None
    raw_datasets: dict[str, pd.DataFrame] = field(default_factory=dict)
    master_dataset: Optional[pd.DataFrame] = None
    cleaned_dataset: Optional[pd.DataFrame] = None
    bibliometrix_compatible: Optional[pd.DataFrame] = None
    validated_dataset: Optional[pd.DataFrame] = None
    included_studies: Optional[pd.DataFrame] = None
    excluded_studies: Optional[pd.DataFrame] = None
    screening_log: Optional[pd.DataFrame] = None
    duplicate_mappings: list[DuplicateMapping] = field(default_factory=list)
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    cleaning_actions: list[CleaningAction] = field(default_factory=list)
    mapping_validation_result: Optional[MappingValidationResult] = None
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    stats: RecordStats = field(default_factory=RecordStats)
    prisma_data: dict[str, Any] = field(default_factory=dict)
    stage_log: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    
    def log_stage(self, agent_name: str, stage: str, message: str, 
                  details: Optional[dict] = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent_name,
            "stage": stage,
            "message": message,
            "details": details or {}
        }
        self.stage_log.append(entry)
    
    def add_error(self, agent: str, error: str):
        self.errors.append(f"[{agent}] {error}")
    
    def save_provenance(self, path: Path):
        data = [asdict(p) for p in self.provenance]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def save_audit_log(self, path: Path):
        data = self.stage_log
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
