"""Agent 5b: Database Mapping Validation Agent.

Validates that bibliographic metadata from different source databases
has been correctly mapped into the framework's internal Bibliometrix schema.
Executes after Normalization (agent_05) and before Bibliometrix Validation (agent_07).
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import (
    BIBLIOMETRIX_MANDATORY_FIELDS,
    DATABASE_FIELD_MAPPINGS,
    DATABASE_COLUMN_PATTERNS,
    MappingValidationConfig,
)
from core.models import (
    PipelineState,
    MappingFieldResult,
    UnmappedColumn,
    MetadataPreservationResult,
    MappingValidationResult,
)
from core.exceptions import MappingValidationError

logger = logging.getLogger("aibef.mapping_validation")


class DatabaseMappingValidationAgent:
    """Validates database-to-Bibliometrix field mapping correctness."""
    NAME = "DatabaseMappingValidationAgent"

    def __init__(self, config: Optional[MappingValidationConfig] = None):
        self.config = config or MappingValidationConfig()

    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting database mapping validation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning database mapping validation")

        if not self.config.enabled:
            logger.info("[%s] Mapping validation disabled, skipping", self.NAME)
            state.log_stage(self.NAME, "skipped", "Mapping validation disabled")
            return state

        df = state.cleaned_dataset
        if df is None or df.empty:
            raise MappingValidationError("No cleaned dataset available for mapping validation")

        source_db = self._detect_source_database(state)
        logger.info("[%s] Detected source database: %s", self.NAME, source_db)

        field_mapping = DATABASE_FIELD_MAPPINGS.get(source_db, {})
        if not field_mapping:
            logger.warning("[%s] No field mapping defined for %s", self.NAME, source_db)
            state.log_stage(self.NAME, "warning",
                            f"No field mapping defined for {source_db}")
            state.mapping_validation_result = MappingValidationResult(
                source_database=source_db,
                detected_format="unknown",
                overall_status="WARNING",
                warnings=[f"No field mapping defined for database: {source_db}"],
            )
            return state

        original_df = self._get_original_dataset(state)

        result = MappingValidationResult(
            source_database=source_db,
            detected_format=self._detect_format(state),
        )

        self._validate_mandatory_fields(df, source_db, result)
        self._validate_field_mappings(df, original_df, source_db, field_mapping, result)
        self._detect_unmapped_columns(df, original_df, source_db, field_mapping, result)
        self._check_metadata_preservation(df, original_df, result)
        self._calculate_field_coverage_score(result)
        self._calculate_mapping_quality_score(result)
        self._determine_overall_status(result)

        state.mapping_validation_result = result
        state.stats.mapping_validation_issues = len(result.warnings)

        self._generate_reports(result, state)

        logger.info(
            "[%s] Validation complete: status=%s coverage=%.1f%% quality=%.1f%%",
            self.NAME, result.overall_status, result.field_coverage_score,
            result.mapping_quality_score,
        )
        state.log_stage(
            self.NAME, "complete",
            f"Mapping validation {result.overall_status}: "
            f"coverage={result.field_coverage_score:.1f}% quality={result.mapping_quality_score:.1f}%",
            result.to_dict(),
        )

        return state

    def _detect_source_database(self, state: PipelineState) -> str:
        """Detect the source database from raw dataset columns and file names."""
        all_columns = set()
        all_filenames = []
        for name, df in state.raw_datasets.items():
            all_columns.update(df.columns)
            all_filenames.append(name.lower())

        unique_indicators = {
            "Dimensions": ["Publication ID", "Dimensions URL", "Sustainable Development Goals"],
            "PubMed": ["PMID", "PMCID", "NIHMS ID"],
            "Web of Science": ["FN ", "VR ", "PT ", "UT "],
            "Scopus": ["Scopus ID", "EID", "Index Keywords"],
            "Lens": ["Lens ID"],
            "CrossRef": ["crossref"],
            "OpenAlex": ["cited_by_count", "openalex"],
            "Semantic Scholar": ["CorpusId"],
        }
        for db_name, indicators in unique_indicators.items():
            match_count = sum(1 for ind in indicators if ind in all_columns)
            if match_count >= 1:
                return db_name

        for db_name, patterns in DATABASE_COLUMN_PATTERNS.items():
            match_count = sum(1 for p in patterns if p in all_columns)
            if match_count >= 3:
                return db_name

        filename_hints = {
            "Web of Science": ["wos", "web of science", "savedrecs"],
            "Scopus": ["scopus"],
            "pubmed": ["pubmed", "pmid"],
            "Dimensions": ["dimension"],
            "Lens": ["lens"],
        }
        for db_name, hints in filename_hints.items():
            for hint in hints:
                if any(hint in fn for fn in all_filenames):
                    return db_name

        return "Unknown"

    def _detect_format(self, state: PipelineState) -> str:
        """Detect the export format from file extensions."""
        for name in state.raw_datasets.keys():
            lower = name.lower()
            if lower.endswith(".txt"):
                return "TXT"
            if lower.endswith(".csv"):
                return "CSV"
            if lower.endswith(".ris"):
                return "RIS"
            if lower.endswith(".bib") or lower.endswith(".bibtex"):
                return "BIB"
        return "UNKNOWN"

    def _get_original_dataset(self, state: PipelineState) -> Optional[pd.DataFrame]:
        """Get the original merged dataset before cleaning for comparison."""
        if state.master_dataset is not None and not state.master_dataset.empty:
            return state.master_dataset
        return None

    def _validate_mandatory_fields(
        self, df: pd.DataFrame, source_db: str, result: MappingValidationResult
    ):
        """Verify all mandatory Bibliometrix fields exist in the cleaned dataset."""
        field_mapping = DATABASE_FIELD_MAPPINGS.get(source_db, {})
        mapped_targets = set(field_mapping.values())

        for field in BIBLIOMETRIX_MANDATORY_FIELDS:
            if field not in df.columns:
                if field not in mapped_targets:
                    field_result = MappingFieldResult(
                        source_field="N/A",
                        target_field=field,
                        mapped_records=0,
                        missing_records=0,
                        null_percentage=0.0,
                        status="NOT_AVAILABLE_FROM_SOURCE",
                    )
                    result.field_results.append(field_result)
                else:
                    field_result = MappingFieldResult(
                        source_field="N/A",
                        target_field=field,
                        mapped_records=0,
                        missing_records=len(df),
                        null_percentage=100.0,
                        status="FAILED",
                    )
                    result.field_results.append(field_result)
                    result.warnings.append(
                        f"Mandatory field '{field}' missing from dataset"
                    )
            else:
                col = df[field]
                null_count = int(col.isna().sum()) + int((col == "").sum())
                non_null = len(df) - null_count
                null_pct = (null_count / len(df) * 100) if len(df) > 0 else 0.0
                status = "PASS" if null_pct < 10.0 else "WARNING"
                field_result = MappingFieldResult(
                    source_field=field,
                    target_field=field,
                    mapped_records=non_null,
                    missing_records=null_count,
                    null_percentage=round(null_pct, 1),
                    status=status,
                )
                result.field_results.append(field_result)
                if status == "WARNING":
                    result.warnings.append(
                        f"Mandatory field '{field}' has {null_pct:.1f}% null values"
                    )

    def _validate_field_mappings(
        self,
        df: pd.DataFrame,
        original_df: Optional[pd.DataFrame],
        source_db: str,
        field_mapping: dict[str, str],
        result: MappingValidationResult,
    ):
        """Validate that source fields were correctly mapped to target fields."""
        for source_field, target_field in field_mapping.items():
            source_exists_in_original = (
                original_df is not None and source_field in original_df.columns
            )
            target_exists_in_cleaned = target_field in df.columns

            if not source_exists_in_original:
                continue

            if not target_exists_in_cleaned:
                mapped_count = 0
                missing_count = len(df) if len(df) > 0 else 0
                null_pct = 100.0
                status = "NOT_AVAILABLE_FROM_SOURCE" if not source_exists_in_original else "FAILED"
            else:
                original_col = original_df[source_field]
                target_col = df[target_field]
                total = len(df)
                mapped_count = int(target_col.notna().sum()) + int((target_col != "").sum())
                missing_count = total - mapped_count
                null_pct = (missing_count / total * 100) if total > 0 else 0.0

                if source_field == target_field:
                    status = "PASS" if null_pct < 10.0 else "WARNING"
                else:
                    if mapped_count > 0:
                        status = "PASS" if null_pct < 10.0 else "WARNING"
                    else:
                        status = "NOT_AVAILABLE_FROM_SOURCE"

            field_result = MappingFieldResult(
                source_field=source_field,
                target_field=target_field,
                mapped_records=mapped_count,
                missing_records=missing_count,
                null_percentage=round(null_pct, 1),
                status=status,
            )
            result.field_results.append(field_result)

    def _detect_unmapped_columns(
        self,
        df: pd.DataFrame,
        original_df: Optional[pd.DataFrame],
        source_db: str,
        field_mapping: dict[str, str],
        result: MappingValidationResult,
    ):
        """Detect columns present in the original dataset that were not mapped."""
        if original_df is None or not self.config.report_unmapped_columns:
            return

        mapped_source_fields = set(field_mapping.keys())
        internal_fields = {"__source_file__", "__record_id__"}

        for col in original_df.columns:
            if col in internal_fields:
                continue
            if col in mapped_source_fields:
                continue

            is_optional = col.upper() in {
                "ACKNOWLEDGEMENTS", "FUNDING", "BOOK EDITORS",
                "ANTHOLOGY TITLE", "OPEN ACCESS", "RCR", "FCR",
                "SOURCE LINKOUT", "DIMENSIONS URL", "SDGS",
            }
            is_unknown = col.upper() not in {
                c.upper() for c in BIBLIOMETRIX_MANDATORY_FIELDS
            } and not is_optional

            if is_optional:
                classification = "OPTIONAL"
                suggestion = f"Column '{col}' is optional and not mapped"
            elif is_unknown:
                classification = "POTENTIAL_CANDIDATE"
                suggestion = f"Column '{col}' could be mapped to a Bibliometrix field"
            else:
                classification = "UNUSED"
                suggestion = f"Column '{col}' was not mapped"

            result.unmapped_columns.append(UnmappedColumn(
                column_name=col,
                classification=classification,
                suggestion=suggestion,
            ))

    def _check_metadata_preservation(
        self,
        df: pd.DataFrame,
        original_df: Optional[pd.DataFrame],
        result: MappingValidationResult,
    ):
        """Compare original vs normalized dataset metadata statistics."""
        if original_df is None:
            return

        checks = [
            ("Record Count", len(original_df), len(df)),
            ("Document Count",
             self._count_nonempty(original_df, ["TI"]),
             self._count_nonempty(df, ["TI"])),
            ("Author Count",
             self._count_nonempty(original_df, ["AU", "Authors"]),
             self._count_nonempty(df, ["AU"])),
            ("DOI Count",
             self._count_nonempty(original_df, ["DI", "DOI"]),
             self._count_nonempty(df, ["DI"])),
            ("Journal Count",
             self._count_unique_nonempty(original_df, ["SO", "Source", "Journal/Book", "Source title"]),
             self._count_unique_nonempty(df, ["SO"])),
            ("Keyword Count",
             self._count_nonempty(original_df, ["DE", "ID", "Author Keywords", "Index Keywords", "MeSH terms"]),
             self._count_nonempty(df, ["DE", "ID"])),
        ]

        year_cols_orig = ["PY", "Year", "PubYear", "Publication Year", "published-print"]
        year_cols_clean = ["PY"]
        orig_years = self._get_year_range(original_df, year_cols_orig)
        clean_years = self._get_year_range(df, year_cols_clean)
        if orig_years and clean_years:
            checks.append(("Publication Year Range", orig_years, clean_years))

        aff_cols_orig = ["C1", "Affiliations", "Authors Affiliations", "Authors (Raw Affiliation)"]
        checks.append((
            "Affiliation Count",
            self._count_nonempty(original_df, aff_cols_orig),
            self._count_nonempty(df, ["C1"]),
        ))

        for metric, orig_val, clean_val in checks:
            diff = None
            classification = "Expected"
            if isinstance(orig_val, (int, float)) and isinstance(clean_val, (int, float)):
                diff = clean_val - orig_val
                if abs(diff) > len(original_df) * 0.05:
                    classification = "Unexpected"
                elif diff != 0:
                    classification = "Configuration Driven"
            elif orig_val != clean_val:
                diff = f"{orig_val} -> {clean_val}"
                classification = "Configuration Driven"

            result.metadata_preservation.append(MetadataPreservationResult(
                metric=metric,
                original_value=str(orig_val),
                normalized_value=str(clean_val),
                difference=str(diff) if diff is not None else "0",
                classification=classification,
            ))

            if classification == "Unexpected":
                result.warnings.append(
                    f"Unexpected metadata change for {metric}: "
                    f"{orig_val} -> {clean_val}"
                )

    def _calculate_field_coverage_score(self, result: MappingValidationResult):
        """Calculate Field Coverage Score = mapped mandatory fields / available mandatory fields * 100."""
        mandatory_results = [
            f for f in result.field_results
            if f.target_field in BIBLIOMETRIX_MANDATORY_FIELDS
        ]
        if not mandatory_results:
            result.field_coverage_score = 0.0
            return

        passed = sum(1 for f in mandatory_results if f.status in ("PASS", "NOT_AVAILABLE_FROM_SOURCE"))
        total = len(mandatory_results)
        result.field_coverage_score = round((passed / total) * 100, 1) if total > 0 else 0.0

    def _calculate_mapping_quality_score(self, result: MappingValidationResult):
        """Calculate overall Mapping Quality Score (0-100)."""
        scores = []

        scores.append(result.field_coverage_score * 0.30)

        mapped_results = [f for f in result.field_results if f.status != "NOT_AVAILABLE_FROM_SOURCE"]
        if mapped_results:
            avg_populated = sum(
                (1 - f.null_percentage / 100.0) for f in mapped_results
            ) / len(mapped_results)
            scores.append(avg_populated * 100 * 0.25)
        else:
            scores.append(0.0)

        passed_count = sum(1 for f in result.field_results if f.status == "PASS")
        total_count = len(result.field_results) if result.field_results else 1
        accuracy = passed_count / total_count
        scores.append(accuracy * 100 * 0.20)

        schema_consistency = 100.0 - min(len(result.warnings) * 5.0, 40.0)
        scores.append(max(schema_consistency, 0.0) * 0.15)

        unexpected_changes = sum(
            1 for m in result.metadata_preservation
            if m.classification == "Unexpected"
        )
        preservation_score = 100.0 - min(unexpected_changes * 20.0, 80.0)
        scores.append(max(preservation_score, 0.0) * 0.10)

        result.mapping_quality_score = round(sum(scores), 1)

    def _determine_overall_status(self, result: MappingValidationResult):
        """Determine the final validation status."""
        has_failed = any(f.status == "FAILED" for f in result.field_results)
        has_unexpected_loss = any(
            m.classification == "Unexpected" for m in result.metadata_preservation
        )
        has_warnings = len(result.warnings) > 0

        if has_failed or has_unexpected_loss:
            result.overall_status = "FAILED"
        elif has_warnings:
            result.overall_status = "WARNING"
        elif result.field_coverage_score >= 95.0:
            result.overall_status = "PASS"
        else:
            result.overall_status = "PASS_WITH_INFORMATION"

        if result.overall_status == "FAILED":
            result.recommendations.append(
                "Review failed field mappings and correct source-to-target assignments"
            )
        if has_unexpected_loss:
            result.recommendations.append(
                "Investigate unexpected metadata loss during normalization"
            )
        if result.field_coverage_score < self.config.required_field_coverage:
            result.recommendations.append(
                f"Field coverage ({result.field_coverage_score:.1f}%) is below "
                f"threshold ({self.config.required_field_coverage}%)"
            )

    def _generate_reports(self, result: MappingValidationResult, state: PipelineState):
        """Generate XLSX and DOCX validation reports."""
        try:
            self._generate_xlsx_report(result, state)
        except Exception as e:
            logger.error("[%s] Failed to generate XLSX report: %s", self.NAME, e)

        try:
            self._generate_docx_report(result, state)
        except Exception as e:
            logger.error("[%s] Failed to generate DOCX report: %s", self.NAME, e)

    def _generate_xlsx_report(self, result: MappingValidationResult, state: PipelineState):
        """Generate Database_Mapping_Validation_Report.xlsx."""
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = Workbook()

        ws_summary = wb.active
        ws_summary.title = "Summary"
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

        summary_data = [
            ("Source Database", result.source_database),
            ("Detected Format", result.detected_format),
            ("Field Coverage Score", f"{result.field_coverage_score:.1f}%"),
            ("Mapping Quality Score", f"{result.mapping_quality_score:.1f}"),
            ("Overall Status", result.overall_status),
            ("Total Warnings", len(result.warnings)),
            ("Unmapped Columns", len(result.unmapped_columns)),
            ("Validation Timestamp", datetime.now().isoformat()),
        ]
        for i, (label, value) in enumerate(summary_data, 1):
            ws_summary.cell(row=i, column=1, value=label).font = Font(bold=True)
            ws_summary.cell(row=i, column=2, value=str(value))
        ws_summary.column_dimensions["A"].width = 30
        ws_summary.column_dimensions["B"].width = 50

        ws_fields = wb.create_sheet("Field Mapping")
        field_headers = [
            "Source Field", "Target Field", "Mapped Records",
            "Missing Records", "Null %", "Validation Status",
        ]
        for col_idx, header in enumerate(field_headers, 1):
            cell = ws_fields.cell(row=1, column=col_idx, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for row_idx, fr in enumerate(result.field_results, 2):
            ws_fields.cell(row=row_idx, column=1, value=fr.source_field)
            ws_fields.cell(row=row_idx, column=2, value=fr.target_field)
            ws_fields.cell(row=row_idx, column=3, value=fr.mapped_records)
            ws_fields.cell(row=row_idx, column=4, value=fr.missing_records)
            ws_fields.cell(row=row_idx, column=5, value=f"{fr.null_percentage:.1f}%")
            status_cell = ws_fields.cell(row=row_idx, column=6, value=fr.status)
            if fr.status == "PASS":
                status_cell.fill = PatternFill(start_color="C6EFCE", fill_type="solid")
            elif fr.status == "WARNING":
                status_cell.fill = PatternFill(start_color="FFEB9C", fill_type="solid")
            elif fr.status == "FAILED":
                status_cell.fill = PatternFill(start_color="FFC7CE", fill_type="solid")

        for col in range(1, 7):
            ws_fields.column_dimensions[chr(64 + col)].width = 20

        if result.unmapped_columns:
            ws_unmapped = wb.create_sheet("Unmapped Columns")
            unmapped_headers = ["Column Name", "Classification", "Suggestion"]
            for col_idx, header in enumerate(unmapped_headers, 1):
                cell = ws_unmapped.cell(row=1, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
            for row_idx, uc in enumerate(result.unmapped_columns, 2):
                ws_unmapped.cell(row=row_idx, column=1, value=uc.column_name)
                ws_unmapped.cell(row=row_idx, column=2, value=uc.classification)
                ws_unmapped.cell(row=row_idx, column=3, value=uc.suggestion)
            ws_unmapped.column_dimensions["A"].width = 30
            ws_unmapped.column_dimensions["B"].width = 25
            ws_unmapped.column_dimensions["C"].width = 60

        if result.metadata_preservation:
            ws_meta = wb.create_sheet("Metadata Preservation")
            meta_headers = ["Metric", "Original", "Normalized", "Difference", "Classification"]
            for col_idx, header in enumerate(meta_headers, 1):
                cell = ws_meta.cell(row=1, column=col_idx, value=header)
                cell.font = header_font
                cell.fill = header_fill
            for row_idx, mp in enumerate(result.metadata_preservation, 2):
                ws_meta.cell(row=row_idx, column=1, value=mp.metric)
                ws_meta.cell(row=row_idx, column=2, value=mp.original_value)
                ws_meta.cell(row=row_idx, column=3, value=mp.normalized_value)
                ws_meta.cell(row=row_idx, column=4, value=mp.difference)
                ws_meta.cell(row=row_idx, column=5, value=mp.classification)
            for col in range(1, 6):
                ws_meta.column_dimensions[chr(64 + col)].width = 25

        output_dir = state.config.output_dir / "mapping_validation"
        output_dir.mkdir(parents=True, exist_ok=True)
        xlsx_path = output_dir / "Database_Mapping_Validation_Report.xlsx"
        wb.save(str(xlsx_path))
        logger.info("[%s] XLSX report saved: %s", self.NAME, xlsx_path)

    def _generate_docx_report(self, result: MappingValidationResult, state: PipelineState):
        """Generate Database_Mapping_Validation_Report.docx."""
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()
        style = doc.styles["Normal"]
        style.font.size = Pt(10)

        title = doc.add_heading("Database Mapping Validation Report", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_paragraph(f"Source Database: {result.source_database}")
        doc.add_paragraph(f"Detected Format: {result.detected_format}")
        doc.add_paragraph(f"Validation Timestamp: {datetime.now().isoformat()}")

        doc.add_heading("Scores", level=1)
        score_table = doc.add_table(rows=3, cols=2)
        score_table.style = "Light Grid Accent 1"
        cells = score_table.rows[0].cells
        cells[0].text = "Field Coverage Score"
        cells[1].text = f"{result.field_coverage_score:.1f}%"
        cells = score_table.rows[1].cells
        cells[0].text = "Mapping Quality Score"
        cells[1].text = f"{result.mapping_quality_score:.1f}"
        cells = score_table.rows[2].cells
        cells[0].text = "Overall Status"
        cells[1].text = result.overall_status

        if result.overall_status == "PASS":
            doc.add_paragraph("Overall Status: PASS", style="Intense Quote")
        elif result.overall_status == "WARNING":
            doc.add_paragraph("Overall Status: WARNING", style="Intense Quote")
        elif result.overall_status == "FAILED":
            doc.add_paragraph("Overall Status: FAILED", style="Intense Quote")

        doc.add_heading("Field Mapping Results", level=1)
        if result.field_results:
            ftable = doc.add_table(rows=1 + len(result.field_results), cols=6)
            ftable.style = "Light Grid Accent 1"
            headers = ["Source", "Target", "Mapped", "Missing", "Null %", "Status"]
            for i, h in enumerate(headers):
                ftable.rows[0].cells[i].text = h
            for idx, fr in enumerate(result.field_results):
                row = ftable.rows[idx + 1]
                row.cells[0].text = fr.source_field
                row.cells[1].text = fr.target_field
                row.cells[2].text = str(fr.mapped_records)
                row.cells[3].text = str(fr.missing_records)
                row.cells[4].text = f"{fr.null_percentage:.1f}%"
                row.cells[5].text = fr.status

        doc.add_heading("Metadata Preservation", level=1)
        if result.metadata_preservation:
            mtable = doc.add_table(rows=1 + len(result.metadata_preservation), cols=5)
            mtable.style = "Light Grid Accent 1"
            mheaders = ["Metric", "Original", "Normalized", "Difference", "Classification"]
            for i, h in enumerate(mheaders):
                mtable.rows[0].cells[i].text = h
            for idx, mp in enumerate(result.metadata_preservation):
                row = mtable.rows[idx + 1]
                row.cells[0].text = mp.metric
                row.cells[1].text = str(mp.original_value)
                row.cells[2].text = str(mp.normalized_value)
                row.cells[3].text = str(mp.difference)
                row.cells[4].text = mp.classification

        if result.unmapped_columns:
            doc.add_heading("Unmapped Columns", level=1)
            for uc in result.unmapped_columns:
                doc.add_paragraph(
                    f"{uc.column_name} [{uc.classification}]: {uc.suggestion}",
                    style="List Bullet",
                )

        if result.warnings:
            doc.add_heading("Warnings", level=1)
            for w in result.warnings:
                doc.add_paragraph(w, style="List Bullet")

        if result.recommendations:
            doc.add_heading("Recommendations", level=1)
            for r in result.recommendations:
                doc.add_paragraph(r, style="List Bullet")

        doc.add_heading("Coverage Classification", level=1)
        if result.field_coverage_score >= 100:
            classification = "EXCELLENT (100%)"
        elif result.field_coverage_score >= 95:
            classification = f"GOOD ({result.field_coverage_score:.1f}%)"
        elif result.field_coverage_score >= 90:
            classification = f"ACCEPTABLE ({result.field_coverage_score:.1f}%)"
        else:
            classification = f"NEEDS_REVIEW ({result.field_coverage_score:.1f}%)"
        doc.add_paragraph(f"Field Coverage Classification: {classification}")

        output_dir = state.config.output_dir / "mapping_validation"
        output_dir.mkdir(parents=True, exist_ok=True)
        docx_path = output_dir / "Database_Mapping_Validation_Report.docx"
        doc.save(str(docx_path))
        logger.info("[%s] DOCX report saved: %s", self.NAME, docx_path)

    @staticmethod
    def _count_nonempty(df: pd.DataFrame, columns: list[str]) -> int:
        """Count rows where at least one of the given columns has a non-empty value."""
        if df is None or df.empty:
            return 0
        mask = pd.Series([False] * len(df), index=df.index)
        for col in columns:
            if col in df.columns:
                mask = mask | (df[col].notna() & (df[col].astype(str).str.strip() != ""))
        return int(mask.sum())

    @staticmethod
    def _count_unique_nonempty(df: pd.DataFrame, columns: list[str]) -> int:
        """Count unique non-empty values across the given columns."""
        if df is None or df.empty:
            return 0
        values = set()
        for col in columns:
            if col in df.columns:
                for val in df[col].dropna():
                    s = str(val).strip()
                    if s and s != "nan":
                        values.add(s)
        return len(values)

    @staticmethod
    def _get_year_range(df: pd.DataFrame, year_columns: list[str]) -> Optional[str]:
        """Get the year range from year columns."""
        if df is None or df.empty:
            return None
        years = []
        for col in year_columns:
            if col in df.columns:
                numeric = pd.to_numeric(df[col], errors="coerce").dropna()
                years.extend(numeric.tolist())
        if not years:
            return None
        return f"{int(min(years))}-{int(max(years))}"
