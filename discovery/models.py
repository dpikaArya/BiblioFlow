"""Data models for Multi-Database Discovery & Classification Engine."""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class ExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    BLOCKED = "BLOCKED"
    NOT_EXECUTED = "NOT_EXECUTED"


class DetectionConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DatabaseSource(str, Enum):
    WEB_OF_SCIENCE = "Web of Science"
    SCOPUS = "Scopus"
    PUBMED = "PubMed"
    DIMENSIONS = "Dimensions"
    LENS = "Lens"
    CROSSREF = "CrossRef"
    OPENALEX = "OpenAlex"
    SEMANTIC_SCHOLAR = "Semantic Scholar"
    UNKNOWN = "Unknown"


class ExportFormat(str, Enum):
    TXT = "TXT"
    CSV = "CSV"
    RIS = "RIS"
    NBIB = "NBIB"
    BIB = "BIB"
    BIBTEX = "BibTeX"
    XML = "XML"
    ENDNOTE = "EndNote"
    UNKNOWN = "UNKNOWN"


class GroupCertificationStatus(str, Enum):
    READY_FOR_BIBLIOSHINY = "READY_FOR_BIBLIOSHINY"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_CERTIFICATION = "FAILED_CERTIFICATION"
    FAILED_REGRESSION = "FAILED_REGRESSION"
    FAILED_REPRODUCIBILITY = "FAILED_REPRODUCIBILITY"
    FAILED_COMPATIBILITY = "FAILED_COMPATIBILITY"
    FAILED_PRISMA = "FAILED_PRISMA"


class LowConfidenceAction(str, Enum):
    SKIP = "skip"
    ASK_USER = "ask_user"
    ABORT = "abort"


class SchemaFieldStatus(str, Enum):
    PRESENT = "PRESENT"
    MISSING = "MISSING"
    EMPTY = "EMPTY"
    MALFORMED = "MALFORMED"


@dataclass
class FileRecord:
    """Represents a single discovered bibliographic file."""
    file_path: Path
    file_name: str
    file_size: int
    encoding: str
    delimiter: Optional[str] = None
    database_source: DatabaseSource = DatabaseSource.UNKNOWN
    export_format: ExportFormat = ExportFormat.UNKNOWN
    schema_version: Optional[str] = None
    confidence: float = 0.0
    confidence_level: DetectionConfidence = DetectionConfidence.LOW
    detection_method: str = ""
    record_count: int = 0
    column_names: list[str] = field(default_factory=list)
    field_tags: list[str] = field(default_factory=list)
    discovery_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    status: ExecutionStatus = ExecutionStatus.PENDING
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata_snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["file_path"] = str(self.file_path)
        d["database_source"] = self.database_source.value
        d["export_format"] = self.export_format.value
        d["confidence_level"] = self.confidence_level.value
        d["status"] = self.status.value
        return d


@dataclass
class SchemaField:
    """Describes a single schema field validation result."""
    field_name: str
    expected_type: str
    status: SchemaFieldStatus
    present: bool
    non_empty_count: int = 0
    total_count: int = 0
    sample_values: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


@dataclass
class SchemaValidationResult:
    """Result of schema validation for a single file."""
    file_record: FileRecord
    is_valid: bool
    validation_score: float
    fields: list[SchemaField] = field(default_factory=list)
    mandatory_fields_present: int = 0
    mandatory_fields_total: int = 0
    recommended_fields_present: int = 0
    recommended_fields_total: int = 0
    encoding_valid: bool = True
    delimiter_valid: bool = True
    column_types_valid: bool = True
    reference_structure_valid: bool = True
    identifier_integrity_valid: bool = True
    author_structure_valid: bool = True
    keyword_structure_valid: bool = True
    record_integrity_valid: bool = True
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        d = {
            "file_name": self.file_record.file_name,
            "database_source": self.file_record.database_source.value,
            "is_valid": self.is_valid,
            "validation_score": self.validation_score,
            "mandatory_fields_present": self.mandatory_fields_present,
            "mandatory_fields_total": self.mandatory_fields_total,
            "encoding_valid": self.encoding_valid,
            "delimiter_valid": self.delimiter_valid,
            "issues": self.issues,
            "warnings": self.warnings,
            "status": self.status.value,
        }
        return d


@dataclass
class DatabaseGroup:
    """A group of files belonging to the same database."""
    group_id: str
    group_name: str
    database_source: DatabaseSource
    files: list[FileRecord] = field(default_factory=list)
    total_records: int = 0
    schema_validated: bool = False
    merge_safe: bool = True
    certification_status: GroupCertificationStatus = GroupCertificationStatus.READY_FOR_BIBLIOSHINY
    pipeline_status: ExecutionStatus = ExecutionStatus.PENDING
    output_dir: Optional[Path] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "database_source": self.database_source.value,
            "file_count": len(self.files),
            "files": [f.file_name for f in self.files],
            "total_records": self.total_records,
            "schema_validated": self.schema_validated,
            "merge_safe": self.merge_safe,
            "certification_status": self.certification_status.value,
            "pipeline_status": self.pipeline_status.value,
            "errors": self.errors,
        }


@dataclass
class ProvenanceRecord:
    """Extended provenance for a single record in the discovery system."""
    record_id: str
    original_database: str
    original_file: str
    original_record_identifier: Optional[str] = None
    original_export_format: str = ""
    import_timestamp: str = ""
    discovery_timestamp: str = ""
    database_group: str = ""
    cleaning_version: str = ""
    validation_version: str = ""
    certification_version: str = ""
    framework_version: str = "2.0.0"
    run_id: str = ""
    replay_id: str = ""
    regression_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GroupPipelineResult:
    """Result of executing the pipeline for a single database group."""
    group_id: str
    group_name: str
    database_source: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    records_imported: int = 0
    records_after_merge: int = 0
    records_after_dedup: int = 0
    records_after_cleaning: int = 0
    records_final: int = 0
    certification_status: str = ""
    quality_score: int = 0
    quality_grade: str = ""
    output_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    provenance_entries: list[ProvenanceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "database_source": self.database_source,
            "status": self.status.value,
            "records_imported": self.records_imported,
            "records_after_merge": self.records_after_merge,
            "records_after_dedup": self.records_after_dedup,
            "records_after_cleaning": self.records_after_cleaning,
            "records_final": self.records_final,
            "certification_status": self.certification_status,
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade,
            "output_files": self.output_files,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class DiscoveryReport:
    """Complete report of the multi-database discovery process."""
    run_id: str
    discovery_timestamp: str
    search_directory: str
    files_discovered: int = 0
    files_supported: int = 0
    files_unsupported: int = 0
    database_groups: int = 0
    total_records: int = 0
    file_records: list[FileRecord] = field(default_factory=list)
    schema_results: list[SchemaValidationResult] = field(default_factory=list)
    groups: list[DatabaseGroup] = field(default_factory=list)
    pipeline_results: list[GroupPipelineResult] = field(default_factory=list)
    cross_database_merge_status: str = "BLOCKED"
    overall_status: ExecutionStatus = ExecutionStatus.PENDING
    framework_health_score: float = 0.0
    release_readiness: str = "NOT_READY"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "discovery_timestamp": self.discovery_timestamp,
            "search_directory": self.search_directory,
            "files_discovered": self.files_discovered,
            "files_supported": self.files_supported,
            "files_unsupported": self.files_unsupported,
            "database_groups": self.database_groups,
            "total_records": self.total_records,
            "file_records": [f.to_dict() for f in self.file_records],
            "groups": [g.to_dict() for g in self.groups],
            "pipeline_results": [p.to_dict() for p in self.pipeline_results],
            "cross_database_merge_status": self.cross_database_merge_status,
            "overall_status": self.overall_status.value,
            "framework_health_score": self.framework_health_score,
            "release_readiness": self.release_readiness,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class IdentificationWarning:
    """Warning generated for low-confidence identifications."""
    file_name: str
    reason: str
    evidence: str
    suggested_database: str
    suggested_repair: str
    user_action_required: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
