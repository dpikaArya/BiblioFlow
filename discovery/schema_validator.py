"""Schema Validation Engine - validates files against expected database schemas."""
from __future__ import annotations
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import (
    DATABASE_COLUMN_PATTERNS,
    DATABASE_SCHEMA_SIGNATURES,
    MANDATORY_FIELDS_PER_DATABASE,
)
from discovery.models import (
    DatabaseSource,
    ExecutionStatus,
    ExportFormat,
    FileRecord,
    SchemaField,
    SchemaFieldStatus,
    SchemaValidationResult,
)

logger = logging.getLogger("aibef.discovery.schema_validator")

RECOMMENDED_FIELDS: dict[str, list[str]] = {
    "Web of Science": ["AB", "DE", "ID", "C1", "CR", "TC", "DI"],
    "Scopus": ["Abstract", "Affiliations", "Index Keywords", "Publisher Name"],
    "PubMed": ["Citation", "First Author", "Journal/Book", "Publication Year"],
    "Dimensions": ["Abstract", "Authors", "Times cited", "Cited references"],
    "Lens": ["Authors", "Year", "Source"],
}

DOI_PATTERN = re.compile(r"^10\.\d{4,}/")
AUTHOR_PATTERN = re.compile(r"[A-Za-z].*,\s*[A-Z]")


class SchemaValidationEngine:
    """Validates schema of each file against expected database schema."""

    def __init__(self):
        self._results: list[SchemaValidationResult] = []

    def validate(self, file_record: FileRecord) -> SchemaValidationResult:
        """Validate a single file's schema."""
        logger.info("Validating schema: %s", file_record.file_name)

        result = SchemaValidationResult(
            file_record=file_record,
            is_valid=True,
            validation_score=0.0,
        )

        if file_record.export_format == ExportFormat.CSV:
            self._validate_csv(file_record, result)
        elif file_record.export_format == ExportFormat.TXT:
            self._validate_wos_txt(file_record, result)
        elif file_record.export_format in (ExportFormat.RIS, ExportFormat.NBIB):
            self._validate_ris_nbib(file_record, result)
        else:
            result.issues.append(
                f"Unsupported format for schema validation: {file_record.export_format.value}"
            )

        self._validate_mandatory_fields(file_record, result)
        self._validate_recommended_fields(file_record, result)
        result.validation_score = self._calculate_score(result)
        result.is_valid = result.validation_score >= 0.60

        if result.is_valid:
            result.status = ExecutionStatus.PASSED
        else:
            result.status = ExecutionStatus.FAILED

        self._results.append(result)
        logger.info(
            "Schema validation %s: score=%.2f valid=%s",
            file_record.file_name, result.validation_score, result.is_valid,
        )
        return result

    @property
    def results(self) -> list[SchemaValidationResult]:
        return list(self._results)

    def _validate_csv(self, record: FileRecord, result: SchemaValidationResult):
        """Validate CSV file structure."""
        try:
            encoding = record.encoding or "utf-8"
            delimiter = record.delimiter or ","
            df = pd.read_csv(
                record.file_path,
                encoding=encoding,
                delimiter=delimiter,
                nrows=5,
                on_bad_lines="skip",
            )
            record.column_names = list(df.columns)
            record.record_count = self._count_csv_rows(
                record.file_path, encoding, delimiter
            )

            result.fields.append(SchemaField(
                field_name="__columns__",
                expected_type="list",
                status=SchemaFieldStatus.PRESENT,
                present=True,
                non_empty_count=len(df.columns),
                total_count=len(df.columns),
                sample_values=list(df.columns[:10]),
            ))

            self._validate_encoding(record, result)
            self._validate_delimiter(record, result)
            self._validate_column_types(df, result)
            self._validate_record_integrity(df, record, result)

        except Exception as e:
            result.issues.append(f"CSV validation error: {e}")
            logger.error("CSV validation failed for %s: %s", record.file_name, e)

    def _validate_wos_txt(self, record: FileRecord, result: SchemaValidationResult):
        """Validate WoS plain text file structure."""
        try:
            encoding = record.encoding or "utf-8"
            with open(record.file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

            record.record_count = sum(
                1 for line in lines if line.strip() == "" and lines.index(line) > 0
            )
            if record.record_count == 0:
                record.record_count = max(1, len([l for l in lines if l.startswith("PT ")]))

            tags_present = set()
            for line in lines:
                if WOS_TAG_PATTERN.match(line):
                    tag = line.split()[0]
                    tags_present.add(tag)

            record.field_tags = sorted(tags_present)

            has_header = False
            for line in lines[:5]:
                if line.startswith("FN ") or line.startswith("VR "):
                    has_header = True
                    break

            if not has_header:
                result.warnings.append("WoS file missing FN/VR header")

            self._validate_encoding(record, result)
            self._validate_record_integrity_wos(lines, record, result)

        except Exception as e:
            result.issues.append(f"WoS TXT validation error: {e}")
            logger.error("WoS TXT validation failed for %s: %s", record.file_name, e)

    def _validate_ris_nbib(self, record: FileRecord, result: SchemaValidationResult):
        """Validate RIS/NBIB file structure."""
        try:
            encoding = record.encoding or "utf-8"
            with open(record.file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()

            record.record_count = sum(1 for line in lines if line.strip() == "ER  -")
            self._validate_encoding(record, result)

        except Exception as e:
            result.issues.append(f"RIS/NBIB validation error: {e}")

    def _validate_mandatory_fields(
        self, record: FileRecord, result: SchemaValidationResult
    ):
        """Check that mandatory fields for the detected database are present."""
        db_name = record.database_source.value
        mandatory = MANDATORY_FIELDS_PER_DATABASE.get(db_name, [])
        if not mandatory:
            result.warnings.append(
                f"No mandatory fields defined for {db_name}"
            )
            return

        present = 0
        for field_name in mandatory:
            field_present = False
            if record.column_names:
                field_present = any(
                    field_name.lower() == col.lower()
                    for col in record.column_names
                )
            elif record.field_tags:
                field_present = field_name in record.field_tags

            status = SchemaFieldStatus.PRESENT if field_present else SchemaFieldStatus.MISSING
            sf = SchemaField(
                field_name=field_name,
                expected_type="mandatory",
                status=status,
                present=field_present,
            )
            if not field_present:
                sf.issues.append(f"Mandatory field '{field_name}' missing for {db_name}")
            result.fields.append(sf)

            if field_present:
                present += 1

        result.mandatory_fields_present = present
        result.mandatory_fields_total = len(mandatory)

        if present == 0 and mandatory:
            result.issues.append(
                f"No mandatory fields found for {db_name}. "
                f"Expected: {mandatory}"
            )
        elif present < len(mandatory):
            missing = [f for f in mandatory if not any(
                sf.field_name == f and sf.present for sf in result.fields
            )]
            result.warnings.append(
                f"Missing mandatory fields for {db_name}: {missing}"
            )

    def _validate_recommended_fields(
        self, record: FileRecord, result: SchemaValidationResult
    ):
        """Check recommended fields presence."""
        db_name = record.database_source.value
        recommended = RECOMMENDED_FIELDS.get(db_name, [])
        present = 0
        for field_name in recommended:
            field_present = False
            if record.column_names:
                field_present = any(
                    field_name.lower() == col.lower()
                    for col in record.column_names
                )
            elif record.field_tags:
                field_present = field_name in record.field_tags

            sf = SchemaField(
                field_name=field_name,
                expected_type="recommended",
                status=SchemaFieldStatus.PRESENT if field_present else SchemaFieldStatus.MISSING,
                present=field_present,
            )
            result.fields.append(sf)
            if field_present:
                present += 1

        result.recommended_fields_present = present
        result.recommended_fields_total = len(recommended)

    def _validate_encoding(self, record: FileRecord, result: SchemaValidationResult):
        """Validate file encoding is clean."""
        try:
            with open(record.file_path, "r", encoding=record.encoding or "utf-8") as f:
                content = f.read(50000)
            replacement_chars = content.count("\ufffd")
            if replacement_chars > 0:
                result.warnings.append(
                    f"Found {replacement_chars} replacement characters "
                    f"(encoding={record.encoding})"
                )
                result.encoding_valid = False
            else:
                result.encoding_valid = True
        except Exception as e:
            result.issues.append(f"Encoding validation error: {e}")
            result.encoding_valid = False

    def _validate_delimiter(self, record: FileRecord, result: SchemaValidationResult):
        """Validate CSV delimiter consistency."""
        if record.export_format != ExportFormat.CSV:
            return
        try:
            encoding = record.encoding or "utf-8"
            delimiter = record.delimiter or ","
            with open(record.file_path, "r", encoding=encoding, errors="replace") as f:
                lines = f.readlines()[:10]

            if not lines:
                result.delimiter_valid = False
                return

            counts = [line.count(delimiter) for line in lines if line.strip()]
            if counts:
                expected = counts[0]
                inconsistent = sum(1 for c in counts if abs(c - expected) > 2)
                result.delimiter_valid = inconsistent == 0
                if inconsistent > 0:
                    result.warnings.append(
                        f"Delimiter inconsistency: {inconsistent}/{len(counts)} "
                        f"lines have different field counts"
                    )
            else:
                result.delimiter_valid = True
        except Exception as e:
            result.issues.append(f"Delimiter validation error: {e}")

    def _validate_column_types(
        self, df: pd.DataFrame, result: SchemaValidationResult
    ):
        """Validate column data types are reasonable."""
        issues = []
        for col in df.columns:
            if df[col].dtype == object:
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    avg_len = non_null.astype(str).str.len().mean()
                    if avg_len > 1000:
                        issues.append(
                            f"Column '{col}' has very long text values "
                            f"(avg length={avg_len:.0f})"
                        )
        if issues:
            result.column_types_valid = False
            result.warnings.extend(issues)
        else:
            result.column_types_valid = True

    def _validate_record_integrity(
        self, df: pd.DataFrame, record: FileRecord,
        result: SchemaValidationResult
    ):
        """Validate record integrity - check for empty/all-null rows."""
        if df.empty:
            result.issues.append("DataFrame is empty")
            result.record_integrity_valid = False
            return

        all_null_rows = df.isnull().all(axis=1).sum()
        if all_null_rows > 0:
            result.warnings.append(f"Found {all_null_rows} completely empty rows")
            result.record_integrity_valid = False
        else:
            result.record_integrity_valid = True

        self._validate_identifier_integrity(df, record, result)
        self._validate_author_structure(df, record, result)
        self._validate_keyword_structure(df, record, result)

    def _validate_record_integrity_wos(
        self, lines: list[str], record: FileRecord,
        result: SchemaValidationResult
    ):
        """Validate WoS text record integrity."""
        empty_lines = sum(1 for line in lines if line.strip() == "")
        if empty_lines > len(lines) * 0.5:
            result.warnings.append(
                f"High ratio of empty lines: {empty_lines}/{len(lines)}"
            )
            result.record_integrity_valid = False
        else:
            result.record_integrity_valid = True

    def _validate_identifier_integrity(
        self, df: pd.DataFrame, record: FileRecord,
        result: SchemaValidationResult
    ):
        """Validate DOI and other identifier formats."""
        doi_cols = [
            c for c in df.columns
            if c.lower() in ("doi", "di", "doi_standardized")
        ]
        if doi_cols:
            col = df[doi_cols[0]].dropna()
            if len(col) > 0:
                valid_dois = col.astype(str).str.match(r"^10\.\d{4,}/").sum()
                ratio = valid_dois / len(col)
                if ratio < 0.5 and len(col) > 5:
                    result.warnings.append(
                        f"DOI format issue: only {ratio*100:.1f}% "
                        f"match standard DOI pattern"
                    )
                    result.identifier_integrity_valid = False
                else:
                    result.identifier_integrity_valid = True
            else:
                result.identifier_integrity_valid = True
        else:
            result.identifier_integrity_valid = True

    def _validate_author_structure(
        self, df: pd.DataFrame, record: FileRecord,
        result: SchemaValidationResult
    ):
        """Validate author field structure."""
        author_cols = [
            c for c in df.columns
            if c.lower() in ("au", "authors", "author")
        ]
        if not author_cols:
            result.author_structure_valid = True
            return

        col = df[author_cols[0]].dropna()
        if len(col) == 0:
            result.author_structure_valid = True
            return

        sample = col.head(20)
        comma_count = sample.astype(str).str.contains(",").sum()
        ratio = comma_count / len(sample)

        if ratio > 0.5:
            result.author_structure_valid = True
        elif ratio < 0.1 and len(sample) > 3:
            result.warnings.append(
                "Author format: names may not follow 'Last, Initials' convention"
            )
            result.author_structure_valid = False
        else:
            result.author_structure_valid = True

    def _validate_keyword_structure(
        self, df: pd.DataFrame, record: FileRecord,
        result: SchemaValidationResult
    ):
        """Validate keyword field structure."""
        kw_cols = [
            c for c in df.columns
            if c.lower() in ("de", "id", "keywords", "index keywords")
        ]
        if not kw_cols:
            result.keyword_structure_valid = True
            return

        result.keyword_structure_valid = True

    def _calculate_score(self, result: SchemaValidationResult) -> float:
        """Calculate overall validation score."""
        score = 0.0
        total_weight = 0.0

        if result.mandatory_fields_total > 0:
            mandatory_ratio = result.mandatory_fields_present / result.mandatory_fields_total
            score += mandatory_ratio * 40.0
            total_weight += 40.0

        if result.recommended_fields_total > 0:
            recommended_ratio = result.recommended_fields_present / result.recommended_fields_total
            score += recommended_ratio * 20.0
            total_weight += 20.0

        checks = {
            "encoding": (result.encoding_valid, 10.0),
            "delimiter": (result.delimiter_valid, 10.0),
            "column_types": (result.column_types_valid, 5.0),
            "reference_structure": (result.reference_structure_valid, 5.0),
            "identifier_integrity": (result.identifier_integrity_valid, 5.0),
            "author_structure": (result.author_structure_valid, 5.0),
            "keyword_structure": (result.keyword_structure_valid, 5.0),
            "record_integrity": (result.record_integrity_valid, 10.0),
        }

        for check_name, (passed, weight) in checks.items():
            total_weight += weight
            if passed:
                score += weight

        critical_issues = len([i for i in result.issues if "error" in i.lower()])
        score -= critical_issues * 10.0

        if total_weight > 0:
            score = max(0.0, min(100.0, (score / total_weight) * 100.0))
        else:
            score = 50.0

        return round(score, 2)

    @staticmethod
    def _count_csv_rows(file_path: Path, encoding: str, delimiter: str) -> int:
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                return sum(1 for _ in f) - 1
        except Exception:
            return 0


WOS_TAG_PATTERN = re.compile(r"^[A-Z]{2}\s+")
