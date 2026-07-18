"""Database Identification Engine - detects source, format, and confidence."""
from __future__ import annotations
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import (
    DATABASE_COLUMN_PATTERNS,
    DATABASE_SCHEMA_SIGNATURES,
    SUPPORTED_FILE_EXTENSIONS,
)
from discovery.models import (
    DatabaseSource,
    DetectionConfidence,
    ExportFormat,
    FileRecord,
    IdentificationWarning,
)

logger = logging.getLogger("aibef.discovery.identification")


FORMAT_EXTENSION_MAP: dict[str, ExportFormat] = {
    ".txt": ExportFormat.TXT,
    ".csv": ExportFormat.CSV,
    ".ris": ExportFormat.RIS,
    ".nbib": ExportFormat.NBIB,
    ".bib": ExportFormat.BIB,
    ".bibtex": ExportFormat.BIBTEX,
    ".xml": ExportFormat.XML,
    ".end": ExportFormat.ENDNOTE,
    ".enw": ExportFormat.ENDNOTE,
    ".ciw": ExportFormat.TXT,
}

KNOWN_EXPORT_SIGNATURES: dict[str, list[str]] = {
    "Web of Science": [
        r"^FN\s+(Clarivate|Web of Science|ISI)",
        r"^VR\s+1\.0",
        r"^PT\s+[A-Z]+$",
        r"UT\s+WOS:",
    ],
    "Scopus": [
        r"Scopus ID",
        r"EID\s*2-s2\.0-",
        r"^Source\s+Title:",
    ],
    "PubMed": [
        r"^PMID-?\s*\d+",
        r"\[pubmed\]",
        r"\[pmc\]",
    ],
    "Dimensions": [
        r"About the data:.*Exported on",
        r"Digital Science.*Research Solutions",
        r"Publication ID\s*,DOI\s*,Title",
    ],
    "Lens": [
        r"Lens ID",
        r"lens\.org",
    ],
    "CrossRef": [
        r"crossref",
        r"Crossref",
    ],
    "OpenAlex": [
        r"openalex",
        r"OpenAlex",
    ],
    "Semantic Scholar": [
        r"CorpusId",
        r"Semantic Scholar",
    ],
}

WOS_TAG_PATTERN = re.compile(r"^[A-Z]{2}\s+")


class DatabaseIdentificationEngine:
    """Detects database source, export format, and confidence for each file."""

    def __init__(self):
        self._warnings: list[IdentificationWarning] = []

    def identify(self, file_path: Path) -> FileRecord:
        """Identify a single file's database source and format."""
        logger.info("Identifying file: %s", file_path.name)

        record = FileRecord(
            file_path=file_path,
            file_name=file_path.name,
            file_size=file_path.stat().st_size,
            encoding="utf-8",
        )

        encoding = self._detect_encoding(file_path)
        record.encoding = encoding

        ext = file_path.suffix.lower()
        record.export_format = FORMAT_EXTENSION_MAP.get(ext, ExportFormat.UNKNOWN)

        first_lines = self._read_preview(file_path, encoding, line_count=30)
        full_header = self._read_preview(file_path, encoding, line_count=5)
        record.metadata_snippet = full_header[:500] if full_header else ""

        db_score = self._score_database_match(record, first_lines)
        best_db = max(db_score, key=db_score.get) if db_score else DatabaseSource.UNKNOWN
        best_score = db_score.get(best_db, 0.0) if db_score else 0.0

        record.database_source = best_db
        record.confidence = best_score
        record.confidence_level = self._score_to_level(best_score)

        detection_methods = []
        if self._check_file_signatures(record, first_lines):
            detection_methods.append("export_signatures")
        if self._check_column_headers(record, first_lines):
            detection_methods.append("column_headers")
        if self._check_metadata_lines(record, first_lines):
            detection_methods.append("metadata_lines")
        if self._check_file_extension(record, ext):
            detection_methods.append("file_extension")
        record.detection_method = "+".join(detection_methods) if detection_methods else "none"

        if record.export_format == ExportFormat.TXT and best_db == DatabaseSource.WEB_OF_SCIENCE:
            record.field_tags = self._extract_wos_tags(first_lines)

        if record.export_format == ExportFormat.CSV:
            delimiter = self._detect_csv_delimiter(file_path, encoding)
            record.delimiter = delimiter
            headers = self._read_csv_headers(file_path, encoding, delimiter)
            record.column_names = headers

        if record.confidence_level == DetectionConfidence.LOW:
            warning = self._generate_warning(record, detection_methods)
            self._warnings.append(warning)

        record.status = "PASSED"
        logger.info(
            "Identified %s as %s (%s) confidence=%.2f",
            record.file_name, record.database_source.value,
            record.export_format.value, record.confidence,
        )
        return record

    @property
    def warnings(self) -> list[IdentificationWarning]:
        return list(self._warnings)

    def _score_database_match(
        self, record: FileRecord, first_lines: str
    ) -> dict[DatabaseSource, float]:
        scores: dict[DatabaseSource, float] = {}

        for db_name, signatures in DATABASE_SCHEMA_SIGNATURES.items():
            score = 0.0
            matches = 0
            total_possible = len(signatures)

            for sig in signatures:
                if sig.lower() in first_lines.lower():
                    matches += 1
                    score += 1.0 / max(total_possible, 1)

            if matches > 0:
                match_ratio = matches / total_possible
                score = match_ratio * 0.8 + (matches * 0.04)
                score = min(score, 0.99)
                db_source = self._db_name_to_enum(db_name)
                scores[db_source] = score

        for db_name, patterns in KNOWN_EXPORT_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, first_lines, re.MULTILINE | re.IGNORECASE):
                    db_source = self._db_name_to_enum(db_name)
                    current = scores.get(db_source, 0.0)
                    scores[db_source] = max(current, 0.95)
                    break

        return scores

    def _check_file_signatures(self, record: FileRecord, first_lines: str) -> bool:
        for db_name, patterns in KNOWN_EXPORT_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, first_lines, re.MULTILINE | re.IGNORECASE):
                    return True
        return False

    def _check_column_headers(self, record: FileRecord, first_lines: str) -> bool:
        if record.export_format == ExportFormat.CSV:
            headers = first_lines.strip().split("\n")[0]
            for db_name, columns in DATABASE_COLUMN_PATTERNS.items():
                match_count = sum(1 for col in columns if col in headers)
                if match_count >= 3:
                    return True
        return False

    def _check_metadata_lines(self, record: FileRecord, first_lines: str) -> bool:
        for db_name, patterns in KNOWN_EXPORT_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, first_lines, re.MULTILINE | re.IGNORECASE):
                    return True
        return False

    def _check_file_extension(self, record: FileRecord, ext: str) -> bool:
        return ext in SUPPORTED_FILE_EXTENSIONS

    def _extract_wos_tags(self, first_lines: str) -> list[str]:
        tags = []
        for line in first_lines.split("\n"):
            if WOS_TAG_PATTERN.match(line):
                tag = line.split()[0]
                if tag not in tags:
                    tags.append(tag)
        return tags

    def _detect_encoding(self, file_path: Path) -> str:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                f.read(10000)
            return "utf-8"
        except UnicodeDecodeError:
            pass

        try:
            with open(file_path, "r", encoding="latin-1") as f:
                f.read(10000)
            return "latin-1"
        except UnicodeDecodeError:
            pass

        try:
            with open(file_path, "r", encoding="cp1252") as f:
                f.read(10000)
            return "cp1252"
        except UnicodeDecodeError:
            return "utf-8"

    def _detect_csv_delimiter(self, file_path: Path, encoding: str) -> str:
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                sample = f.read(8192)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            return dialect.delimiter
        except (csv.Error, UnicodeDecodeError):
            return ","

    def _read_csv_headers(
        self, file_path: Path, encoding: str, delimiter: str
    ) -> list[str]:
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                for row in reader:
                    if row:
                        return [h.strip().strip('"') for h in row]
            return []
        except Exception:
            return []

    def _read_preview(
        self, file_path: Path, encoding: str, line_count: int = 30
    ) -> str:
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= line_count:
                        break
                    lines.append(line)
            return "".join(lines)
        except Exception:
            return ""

    @staticmethod
    def _score_to_level(score: float) -> DetectionConfidence:
        if score >= 0.95:
            return DetectionConfidence.HIGH
        elif score >= 0.80:
            return DetectionConfidence.MEDIUM
        return DetectionConfidence.LOW

    @staticmethod
    def _db_name_to_enum(name: str) -> DatabaseSource:
        mapping = {e.value: e for e in DatabaseSource}
        return mapping.get(name, DatabaseSource.UNKNOWN)

    def _generate_warning(
        self, record: FileRecord, methods: list[str]
    ) -> IdentificationWarning:
        return IdentificationWarning(
            file_name=record.file_name,
            reason="Detection confidence below threshold",
            evidence=f"Confidence={record.confidence:.2f}, methods={methods}",
            suggested_database=record.database_source.value,
            suggested_repair="Manually verify database source and provide correct export",
            user_action_required="Review file and confirm database source",
        )
