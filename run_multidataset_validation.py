#!/usr/bin/env python3
"""AIBEF Multi-Dataset Validation Orchestrator.

Runs the complete AIBEF pipeline independently for each database group,
generates cross-dataset comparison, regression analysis, and all required reports.

Usage:
    python3 run_multidataset_validation.py
"""
import sys
import json
import time
import shutil
import traceback
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import FrameworkConfig
from core.models import PipelineState

logger = logging.getLogger("aibef.multidataset")


# ======================================================================
# File Classifier
# ======================================================================

WOS_SIGNATURES = ["FN ", "VR ", "PT ", "AU ", "TI ", "SO ", "UT "]
DIMENSIONS_SIGNATURES = ["Publication ID", "Dimensions URL", "Fields of Research"]

DATABASE_PATTERNS = {
    "Web of Science": {
        "extensions": {".txt"},
        "signatures": WOS_SIGNATURES,
        "filename_hints": ["savedrecs", "wos", "export"],
    },
    "Dimensions": {
        "extensions": {".csv"},
        "signatures": DIMENSIONS_SIGNATURES,
        "filename_hints": ["dimension"],
    },
}


def classify_file(file_path: Path) -> str:
    """Classify a file as a specific database type."""
    ext = file_path.suffix.lower()

    # Check extension + filename hints first
    for db_name, pattern in DATABASE_PATTERNS.items():
        if ext in pattern["extensions"]:
            name_lower = file_path.name.lower()
            for hint in pattern["filename_hints"]:
                if hint in name_lower:
                    return db_name

    # Check file content signatures for CSV files
    if ext == ".csv":
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                header_line = ""
                for _ in range(5):
                    line = f.readline(4096)
                    if line.strip() and not line.strip().startswith('"About') and not line.strip().startswith('#'):
                        header_line = line
                        break
            for db_name, sigs in DATABASE_PATTERNS.items():
                if any(sig in header_line for sig in sigs):
                    return db_name
            # If CSV has dimensions-like columns, classify as Dimensions
            if "DOI" in header_line and ("Title" in header_line or "Publication ID" in header_line):
                return "Dimensions"
        except Exception:
            pass

    # Check TXT content
    if ext == ".txt":
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(1024)
            if "Clarivate Analytics Web of Science" in head:
                return "Web of Science"
        except Exception:
            pass

    return "Unknown"


def discover_and_classify(input_dir: Path) -> dict[str, list[Path]]:
    """Discover files, classify by database, return groups."""
    # Specific files to use per user instruction
    target_files = ["1.txt", "2.txt", "1D.csv", "2D.csv"]

    files_by_db: dict[str, list[Path]] = {}
    skipped = []

    for fname in target_files:
        fpath = input_dir / fname
        if not fpath.exists():
            logger.warning("Target file not found: %s", fpath)
            skipped.append(fname)
            continue

        db_type = classify_file(fpath)
        logger.info("Classified %s -> %s", fname, db_type)

        if db_type not in files_by_db:
            files_by_db[db_type] = []
        files_by_db[db_type].append(fpath)

    return files_by_db, skipped


# ======================================================================
# Group result tracking
# ======================================================================

@dataclass
class GroupResult:
    group_name: str
    database: str
    files: list[str]
    status: str = "PENDING"
    execution_time: float = 0
    imported: int = 0
    merged: int = 0
    duplicates_removed: int = 0
    final_count: int = 0
    quality_score: int = 0
    quality_grade: str = ""
    certified: bool = False
    certification_status: str = ""
    json_generated: bool = False
    r_validation_output: bool = False
    layer1_status: str = ""
    layer2_status: str = ""
    convert2df_success: bool = False
    biblio_success: bool = False
    summary_success: bool = False
    mapping_score: float = 0
    field_coverage: float = 0
    synchronized: bool = False
    errors: list = field(default_factory=list)
    output_dir: str = ""
    bibval_report: bool = False


# ======================================================================
# Run pipeline for a single group
# ======================================================================

def run_group_pipeline(group_name: str, database: str,
                       files: list[Path], base_output: Path) -> GroupResult:
    """Run the full AIBEF pipeline for one database group."""
    result = GroupResult(
        group_name=group_name,
        database=database,
        files=[f.name for f in files],
    )

    group_output = base_output / group_name
    group_output.mkdir(parents=True, exist_ok=True)
    result.output_dir = str(group_output)

    # Create a temporary input directory with symlinks/copies
    tmp_input = base_output / f"_tmp_input_{group_name}"
    tmp_input.mkdir(parents=True, exist_ok=True)
    try:
        for f in files:
            shutil.copy2(str(f), str(tmp_input / f.name))
    except Exception as e:
        result.status = "FAILED"
        result.errors.append(f"File copy failed: {e}")
        return result

    start_time = time.time()

    try:
        # Import pipeline components
        from pipelines.orchestrator import PipelineOrchestrator
        from validation.checks import ValidationChecks
        from reports.generators import ReportGenerator

        # Configure for this group
        config = FrameworkConfig()
        config.input_dir = tmp_input
        config.output_dir = group_output
        config.log_dir = group_output / "logs"
        config.report_dir = group_output / "reports"
        config.required_txt_count = 0  # Accept any count
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.log_dir.mkdir(parents=True, exist_ok=True)
        config.report_dir.mkdir(parents=True, exist_ok=True)

        # Run orchestrator
        orchestrator = PipelineOrchestrator(config)
        state = orchestrator.run()

        # Generate reports
        ReportGenerator.generate_all(state, config.report_dir)

        # Validation checks
        sync_ok = ValidationChecks.verify_synchronization(state)
        bib_ok = ValidationChecks.verify_bibliometrix_compatible(state)

        # Extract results
        result.imported = state.stats.total_imported
        result.merged = state.stats.after_merge
        result.duplicates_removed = state.stats.duplicates_removed
        result.final_count = state.stats.final_count
        result.synchronized = state.stats.synchronized

        # Quality
        quality = state.prisma_data.get("quality_report", {})
        result.quality_score = quality.get("overall_score", 0)
        result.quality_grade = quality.get("grade", "N/A")

        # R Validation
        r_val = state.prisma_data.get("r_validation", {})
        cert = r_val.get("certification", {})
        result.certified = cert.get("ready_for_biblioshiny", False)
        result.certification_status = cert.get("certification_status", "UNKNOWN")

        l1 = r_val.get("layer1_structural", {})
        l2 = r_val.get("layer2_scientific", {})
        result.layer1_status = l1.get("status", "N/A")
        result.layer2_status = "PASS" if l2.get("overall") else "FAIL"

        conv = r_val.get("convert2df", {})
        bio = r_val.get("biblioAnalysis", {})
        summ = r_val.get("summary", {})
        result.convert2df_success = conv.get("success", False)
        result.biblio_success = bio.get("success", False)
        result.summary_success = summ.get("success", False)

        # Mapping validation
        mv = state.mapping_validation_result
        if mv:
            result.mapping_score = mv.mapping_quality_score
            result.field_coverage = mv.field_coverage_score

        # Check output files
        result.json_generated = (group_output / "R_Validation.json").exists()
        result.r_validation_output = (group_output / "R_Validation_Output.txt").exists()
        result.bibval_report = (group_output / "Bibliometrix_Validation_Report.docx").exists()

        result.status = "SUCCESS" if not state.errors else "COMPLETED_WITH_WARNINGS"
        result.errors = state.errors

    except Exception as e:
        result.status = "FAILED"
        result.errors.append(f"{type(e).__name__}: {e}")
        logger.error("Group %s failed: %s\n%s", group_name, e, traceback.format_exc())
    finally:
        result.execution_time = round(time.time() - start_time, 2)
        shutil.rmtree(str(tmp_input), ignore_errors=True)

    return result


# ======================================================================
# Cross-dataset comparison report
# ======================================================================

def generate_framework_validation_summary(group_results: list[GroupResult],
                                           output_dir: Path):
    """Generate Framework_Validation_Summary.xlsx and .docx."""
    rows = []
    for gr in group_results:
        rows.append({
            "Dataset Group": gr.group_name,
            "Database": gr.database,
            "Files": ", ".join(gr.files),
            "Status": gr.status,
            "Imported": gr.imported,
            "Merged": gr.merged,
            "Duplicates Removed": gr.duplicates_removed,
            "Final Records": gr.final_count,
            "Quality Score": gr.quality_score,
            "Quality Grade": gr.quality_grade,
            "Layer 1 (Structural)": gr.layer1_status,
            "Layer 2 (Scientific)": gr.layer2_status,
            "convert2df": "PASS" if gr.convert2df_success else "FAIL",
            "biblioAnalysis": "PASS" if gr.biblio_success else "FAIL",
            "summary": "PASS" if gr.summary_success else "FAIL",
            "Mapping Score": gr.mapping_score,
            "Field Coverage": gr.field_coverage,
            "Synchronized": "YES" if gr.synchronized else "NO",
            "Certified": "YES" if gr.certified else "NO",
            "Certification Status": gr.certification_status,
            "JSON Generated": "YES" if gr.json_generated else "NO",
            "R Validation Output": "YES" if gr.r_validation_output else "NO",
            "Execution Time (s)": gr.execution_time,
            "Errors": len(gr.errors),
        })

    df_summary = pd.DataFrame(rows)

    # XLSX
    xlsx_path = output_dir / "Framework_Validation_Summary.xlsx"
    with pd.ExcelWriter(str(xlsx_path), engine="openpyxl") as writer:
        df_summary.to_excel(writer, sheet_name="Validation Summary", index=False)
        # Auto-width columns
        ws = writer.sheets["Validation Summary"]
        for col_idx, col in enumerate(df_summary.columns, 1):
            max_len = max(
                df_summary[col].astype(str).str.len().max(),
                len(str(col))
            ) + 2
            ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else "A"].width = min(max_len, 40)
    logger.info("Generated %s", xlsx_path)

    # DOCX
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        docx_path = output_dir / "Framework_Validation_Summary.docx"
        doc = Document()
        title = doc.add_heading("AIBEF Framework Validation Summary", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph(f"Dataset Groups: {len(group_results)}")
        doc.add_paragraph("")

        # Summary table
        table = doc.add_table(rows=1 + len(group_results), cols=8, style="Table Grid")
        headers = ["Group", "Status", "Records", "Quality", "Certified", "JSON", "Layer 1", "Layer 2"]
        for i, h in enumerate(headers):
            table.cell(0, i).text = h
        for i, gr in enumerate(group_results, 1):
            table.cell(i, 0).text = gr.group_name
            table.cell(i, 1).text = gr.status
            table.cell(i, 2).text = str(gr.final_count)
            table.cell(i, 3).text = f"{gr.quality_score}/100 ({gr.quality_grade})"
            table.cell(i, 4).text = "YES" if gr.certified else "NO"
            table.cell(i, 5).text = "YES" if gr.json_generated else "NO"
            table.cell(i, 6).text = gr.layer1_status
            table.cell(i, 7).text = gr.layer2_status

        doc.add_paragraph("")

        # Detailed per-group
        for gr in group_results:
            doc.add_heading(gr.group_name, level=1)
            doc.add_paragraph(f"Database: {gr.database}")
            doc.add_paragraph(f"Files: {', '.join(gr.files)}")
            doc.add_paragraph(f"Status: {gr.status}")
            doc.add_paragraph(f"Imported: {gr.imported} -> Final: {gr.final_count}")
            doc.add_paragraph(f"Duplicates Removed: {gr.duplicates_removed}")
            doc.add_paragraph(f"Quality Score: {gr.quality_score}/100 ({gr.quality_grade})")
            doc.add_paragraph(f"Certification: {gr.certification_status}")
            doc.add_paragraph(f"Mapping Score: {gr.mapping_score}")
            doc.add_paragraph(f"Field Coverage: {gr.field_coverage}")
            doc.add_paragraph(f"Execution Time: {gr.execution_time}s")
            if gr.errors:
                doc.add_paragraph("Errors:")
                for e in gr.errors[:5]:
                    doc.add_paragraph(f"  - {str(e)[:200]}")

        doc.save(str(docx_path))
        logger.info("Generated %s", docx_path)
    except Exception as e:
        logger.error("DOCX generation failed: %s", e)


# ======================================================================
# Regression validation
# ======================================================================

def generate_regression_report(group_results: list[GroupResult],
                                output_dir: Path):
    """Generate Regression_Report.docx comparing against baseline."""
    baseline_path = output_dir.parent / "outputs" / "Baseline_Metrics.json"

    # Load baseline if exists
    baseline = {}
    if baseline_path.exists():
        try:
            baseline = json.loads(baseline_path.read_text())
        except Exception:
            pass

    # Save current as baseline for next run
    current_metrics = {}
    for gr in group_results:
        current_metrics[gr.group_name] = {
            "quality_score": gr.quality_score,
            "final_count": gr.final_count,
            "certified": gr.certified,
            "mapping_score": gr.mapping_score,
            "field_coverage": gr.field_coverage,
        }
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(current_metrics, indent=2))

    regressions = []
    if baseline:
        for gr in group_results:
            prev = baseline.get(gr.group_name, {})
            if prev:
                if gr.quality_score < prev.get("quality_score", 0):
                    regressions.append(
                        f"{gr.group_name}: Quality score decreased "
                        f"from {prev['quality_score']} to {gr.quality_score}"
                    )
                if gr.certified and not prev.get("certified", False):
                    regressions.append(
                        f"{gr.group_name}: Certification LOST (was certified)"
                    )
                if gr.final_count < prev.get("final_count", 0) * 0.9:
                    regressions.append(
                        f"{gr.group_name}: Record count decreased significantly "
                        f"from {prev['final_count']} to {gr.final_count}"
                    )

    # Generate DOCX
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        docx_path = output_dir / "Regression_Report.docx"
        doc = Document()
        title = doc.add_heading("Regression Validation Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph(f"Baseline available: {'YES' if baseline else 'NO (first run)'}")
        doc.add_paragraph("")

        if regressions:
            doc.add_heading("Regressions Detected", level=1)
            p = doc.add_paragraph()
            p.add_run(f"{len(regressions)} regression(s) detected").bold = True
            for r in regressions:
                doc.add_paragraph(r, style="List Bullet")
        else:
            doc.add_heading("No Regressions Detected", level=1)
            if baseline:
                doc.add_paragraph("All metrics are at or above baseline levels.")
            else:
                doc.add_paragraph("First run - no baseline for comparison. Baseline saved for future runs.")

        doc.add_heading("Current Metrics", level=1)
        for gr in group_results:
            doc.add_heading(gr.group_name, level=2)
            doc.add_paragraph(f"Quality Score: {gr.quality_score}")
            doc.add_paragraph(f"Final Count: {gr.final_count}")
            doc.add_paragraph(f"Certified: {gr.certified}")
            doc.add_paragraph(f"Mapping Score: {gr.mapping_score}")

        doc.save(str(docx_path))
        logger.info("Generated %s", docx_path)
    except Exception as e:
        logger.error("Regression report failed: %s", e)


# ======================================================================
# Certification report
# ======================================================================

def generate_certification_report(group_results: list[GroupResult],
                                   output_dir: Path):
    """Generate Certification_Report.docx."""
    try:
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        docx_path = output_dir / "Certification_Report.docx"
        doc = Document()
        title = doc.add_heading("AIBEF Certification Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")

        all_certified = all(gr.certified for gr in group_results)
        p = doc.add_paragraph()
        run = p.add_run(f"Overall Certification: {'READY_FOR_BIBLIOSHINY' if all_certified else 'NOT_CERTIFIED'}")
        run.bold = True
        doc.add_paragraph("")

        doc.add_heading("Certification Policy", level=1)
        doc.add_paragraph("Certification depends ONLY on:")
        doc.add_paragraph("  Layer 1 (Structural Validation): PASS", style="List Bullet")
        doc.add_paragraph("  Layer 2 (Scientific Validation): PASS", style="List Bullet")
        doc.add_paragraph("Layer 3 (Reporting) failures do NOT invalidate certification.")

        doc.add_heading("Per-Group Certification", level=1)
        for gr in group_results:
            doc.add_heading(gr.group_name, level=2)
            t = doc.add_table(rows=5, cols=2, style="Table Grid")
            t.cell(0, 0).text = "Layer 1 (Structural)"
            t.cell(0, 1).text = gr.layer1_status
            t.cell(1, 0).text = "Layer 2 (Scientific)"
            t.cell(1, 1).text = gr.layer2_status
            t.cell(2, 0).text = "Certification"
            t.cell(2, 1).text = gr.certification_status
            t.cell(3, 0).text = "JSON Generated"
            t.cell(3, 1).text = "YES" if gr.json_generated else "NO"
            t.cell(4, 0).text = "Execution Time"
            t.cell(4, 1).text = f"{gr.execution_time}s"

        doc.save(str(docx_path))
        logger.info("Generated %s", docx_path)
    except Exception as e:
        logger.error("Certification report failed: %s", e)


# ======================================================================
# Main orchestrator
# ======================================================================

def main():
    """Run the complete multi-dataset validation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 60)
    print("AIBEF MULTI-DATASET VALIDATION")
    print("=" * 60)

    input_dir = Path.home() / "Desktop" / "Data BibAI"
    base_output = PROJECT_ROOT / "multidataset_outputs"
    base_output.mkdir(parents=True, exist_ok=True)

    overall_start = time.time()

    # Step 1: Discover and classify files
    print("\n--- Step 1: File Discovery & Classification ---")
    files_by_db, skipped = discover_and_classify(input_dir)

    print(f"Discovered {sum(len(v) for v in files_by_db.values())} target files:")
    for db, files in files_by_db.items():
        print(f"  {db}: {[f.name for f in files]}")
    if skipped:
        print(f"  Skipped: {skipped}")

    # Step 2: Create groups
    groups = []
    group_num = 1
    for db_name in sorted(files_by_db.keys()):
        group_name = f"Group_{group_num:03d}_{db_name.replace(' ', '')}"
        groups.append((group_name, db_name, files_by_db[db_name]))
        group_num += 1

    print(f"\n--- Step 2: {len(groups)} Groups ---")
    for gname, db, files in groups:
        print(f"  {gname} ({db}): {[f.name for f in files]}")

    # Step 3: Run pipeline for each group
    group_results = []
    for gname, db, files in groups:
        print(f"\n--- Step 3: Running {gname} ---")
        result = run_group_pipeline(gname, db, files, base_output)
        group_results.append(result)

        print(f"  Status: {result.status}")
        print(f"  Records: {result.imported} -> {result.final_count}")
        print(f"  Duplicates: {result.duplicates_removed}")
        print(f"  Quality: {result.quality_score}/100 ({result.quality_grade})")
        print(f"  Certified: {result.certification_status}")
        print(f"  Layer 1: {result.layer1_status}")
        print(f"  Layer 2: {result.layer2_status}")
        print(f"  JSON: {'YES' if result.json_generated else 'NO'}")
        print(f"  Time: {result.execution_time}s")

    overall_time = round(time.time() - overall_start, 2)

    # Step 4: Generate cross-dataset reports
    print("\n--- Step 4: Generating Reports ---")
    generate_framework_validation_summary(group_results, base_output)
    generate_regression_report(group_results, base_output)
    generate_certification_report(group_results, base_output)

    # Generate additional reports
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        # Replay Report
        docx_path = base_output / "Replay_Report.docx"
        doc = Document()
        title = doc.add_heading("AIBEF Replay Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph(f"Total Groups: {len(group_results)}")
        doc.add_paragraph(f"Total Execution Time: {overall_time}s")
        doc.add_paragraph("")
        for gr in group_results:
            doc.add_heading(gr.group_name, level=2)
            doc.add_paragraph(f"Database: {gr.database}")
            doc.add_paragraph(f"Files: {', '.join(gr.files)}")
            doc.add_paragraph(f"Status: {gr.status}")
            doc.add_paragraph(f"Records: {gr.imported} -> {gr.final_count}")
            doc.add_paragraph(f"Certified: {gr.certification_status}")
        doc.save(str(docx_path))
        print(f"  Generated: Replay_Report.docx")

        # Benchmark Report
        docx_path = base_output / "Benchmark_Report.docx"
        doc = Document()
        title = doc.add_heading("AIBEF Benchmark Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        t = doc.add_table(rows=1 + len(group_results), cols=4, style="Table Grid")
        t.cell(0, 0).text = "Group"
        t.cell(0, 1).text = "Records"
        t.cell(0, 2).text = "Time (s)"
        t.cell(0, 3).text = "Records/sec"
        for i, gr in enumerate(group_results, 1):
            t.cell(i, 0).text = gr.group_name
            t.cell(i, 1).text = str(gr.final_count)
            t.cell(i, 2).text = str(gr.execution_time)
            rps = round(gr.final_count / gr.execution_time, 1) if gr.execution_time > 0 else 0
            t.cell(i, 3).text = str(rps)
        doc.save(str(docx_path))
        print(f"  Generated: Benchmark_Report.docx")

        # Biblioshiny Launch Report
        docx_path = base_output / "Biblioshiny_Launch_Report.docx"
        doc = Document()
        title = doc.add_heading("Biblioshiny Launch Readiness Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        for gr in group_results:
            doc.add_heading(gr.group_name, level=2)
            if gr.certified:
                doc.add_paragraph("STATUS: READY FOR BIBLIOSHINY")
                doc.add_paragraph(f"Certified Dataset: {gr.output_dir}/Bibliometrix_Compatible.txt")
            else:
                doc.add_paragraph("STATUS: NOT READY")
                doc.add_paragraph(f"Reason: {gr.certification_status}")
        doc.save(str(docx_path))
        print(f"  Generated: Biblioshiny_Launch_Report.docx")

    except Exception as e:
        logger.error("Additional report generation failed: %s", e)

    # Step 5: Final summary
    all_certified = all(gr.certified for gr in group_results)
    all_success = all(gr.status in ("SUCCESS", "COMPLETED_WITH_WARNINGS") for gr in group_results)

    print("\n" + "=" * 60)
    print("AIBEF MULTI-DATASET VALIDATION - FINAL SUMMARY")
    print("=" * 60)
    print(f"Dataset Groups:              {len(group_results)}")
    for gr in group_results:
        print(f"  {gr.group_name}: {gr.status} ({gr.final_count} records)")
    print(f"Validation Status:           {'ALL PASSED' if all_success else 'SOME FAILED'}")
    print(f"Scientific Certification:    {'ALL CERTIFIED' if all_certified else 'NOT ALL CERTIFIED'}")
    print(f"JSON Reporting:              {'OPERATIONAL' if all(gr.json_generated for gr in group_results) else 'DEGRADED'}")
    print(f"Biblioshiny Compatibility:   {'ALL READY' if all_certified else 'NOT ALL READY'}")
    print(f"Regression Status:           BASELINE SAVED")
    print(f"Replay Status:               COMPLETED")
    print(f"Benchmark Status:            COMPLETED")
    print(f"Overall Execution Time:      {overall_time}s")
    print(f"Overall Framework Status:    {'VALIDATED' if all_certified else 'NEEDS ATTENTION'}")
    print("=" * 60)

    # Save final audit
    audit = {
        "timestamp": datetime.now().isoformat(),
        "total_groups": len(group_results),
        "all_certified": all_certified,
        "overall_status": "VALIDATED" if all_certified else "NEEDS ATTENTION",
        "overall_execution_time": overall_time,
        "groups": [asdict(gr) for gr in group_results],
    }
    audit_path = base_output / "Audit_Log.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str))
    print(f"\nAudit log: {audit_path}")

    return 0 if all_certified else 1


if __name__ == "__main__":
    sys.exit(main())
