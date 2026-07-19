"""Agent 7: Bibliometrix Validation Agent.

Three-layer validation architecture:
    Layer 1: Structural Validation (Python-only, no R required)
    Layer 2: Scientific Validation (R: convert2df -> biblioAnalysis -> summary)
    Layer 3: Reporting Layer (JSON, DOCX, execution summary)

Certification depends ONLY on Layer 1 PASS AND Layer 2 PASS.
Layer 3 failures NEVER invalidate certification.
"""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from core.exceptions import CompatibilityError

logger = logging.getLogger("aibef.bibvalidate")

import shutil as _shutil
_rscript_which = _shutil.which("Rscript")
RSCRIPT = _rscript_which if _rscript_which else "Rscript"

WOS_MANDATORY_TAGS = {"PT", "AU", "TI", "SO", "PY", "DT", "UT"}
WOS_RECOMMENDED_TAGS = {"AF", "LA", "DE", "ID", "AB", "C1", "RP", "DI", "CR", "TC"}


class BibliometrixValidationAgent:
    NAME = "BibliometrixValidationAgent"
    MAX_ATTEMPTS = 3

    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting 3-layer Bibliometrix validation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning 3-layer validation chain")

        df = state.bibliometrix_compatible
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise CompatibilityError("No compatible dataset to validate")

        output_dir = state.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        # ------------------------------------------------------------------
        # Layer 1: Structural Validation (Python-only, instant, no R)
        # ------------------------------------------------------------------
        logger.info("[%s] Layer 1: Structural Validation", self.NAME)
        layer1 = self._layer1_structural_validation(df)
        logger.info("[%s] Layer 1 result: %s", self.NAME, layer1["status"])

        # ------------------------------------------------------------------
        # Layer 2: Scientific Validation (R chain)
        # ------------------------------------------------------------------
        logger.info("[%s] Layer 2: Scientific Validation (R chain)", self.NAME)
        layer2 = self._layer2_scientific_validation(df, output_dir)
        logger.info("[%s] Layer 2 result: overall=%s (convert2df=%s, biblio=%s, summary=%s)",
                    self.NAME, layer2.get("overall"),
                    layer2.get("convert2df", {}).get("success"),
                    layer2.get("biblioAnalysis", {}).get("success"),
                    layer2.get("summary", {}).get("success"))

        # ------------------------------------------------------------------
        # Layer 3: Reporting (JSON, DOCX) - failures never invalidate cert
        # ------------------------------------------------------------------
        logger.info("[%s] Layer 3: Reporting", self.NAME)
        layer3 = self._layer3_reporting(layer1, layer2, df, state, output_dir)
        logger.info("[%s] Layer 3 result: %s", self.NAME, layer3["status"])

        # ------------------------------------------------------------------
        # Certification: Layer 1 PASS AND Layer 2 PASS
        # ------------------------------------------------------------------
        layer1_pass = layer1["status"] == "PASS"
        layer2_pass = layer2.get("overall", False)
        certified = layer1_pass and layer2_pass

        logger.info("[%s] Certification: Layer1=%s Layer2=%s -> %s",
                    self.NAME, layer1["status"], layer2_pass,
                    "READY_FOR_BIBLIOSHINY" if certified else "NOT_CERTIFIED")

        # Set preliminary result BEFORE Layer 3 (so Layer 3 can read cert status)
        combined_result = {
            "layer1_structural": layer1,
            "layer2_scientific": layer2,
            "certification": {
                "ready_for_biblioshiny": certified,
                "layer1_pass": layer1_pass,
                "layer2_pass": layer2_pass,
                "certification_status": "READY_FOR_BIBLIOSHINY" if certified else "NOT_CERTIFIED",
                "certification_time": datetime.now().isoformat(),
            },
            "success": certified or layer2_pass or layer1_pass,
            "convert2df": layer2.get("convert2df", {}),
            "biblioAnalysis": layer2.get("biblioAnalysis", {}),
            "summary": layer2.get("summary", {}),
            "message": layer2.get("message", ""),
        }
        state.prisma_data["r_validation"] = combined_result

        # ------------------------------------------------------------------
        # Layer 3: Reporting (JSON, DOCX) - failures never invalidate cert
        # ------------------------------------------------------------------
        logger.info("[%s] Layer 3: Reporting", self.NAME)
        layer3 = self._layer3_reporting(layer1, layer2, df, state, output_dir)
        logger.info("[%s] Layer 3 result: %s", self.NAME, layer3["status"])

        # Update combined result with Layer 3
        combined_result["layer3_reporting"] = layer3
        state.prisma_data["r_validation"] = combined_result

        state.validated_dataset = df.copy()

        state.log_stage(self.NAME, "complete",
                        f"3-layer validation complete: cert={'YES' if certified else 'NO'}",
                        combined_result)

        return state

    # ==================================================================
    # Layer 1: Structural Validation (Python-only)
    # ==================================================================

    def _layer1_structural_validation(self, df: pd.DataFrame) -> dict:
        """Verify dataset structure without R. Instant, deterministic."""
        checks = {}
        all_pass = True

        # Check record count
        checks["record_count"] = {
            "status": "PASS" if len(df) > 0 else "FAIL",
            "count": len(df),
        }
        if len(df) == 0:
            all_pass = False

        # Check mandatory columns exist
        missing_mandatory = [c for c in WOS_MANDATORY_TAGS if c not in df.columns]
        checks["mandatory_columns"] = {
            "status": "PASS" if not missing_mandatory else "FAIL",
            "present": [c for c in WOS_MANDATORY_TAGS if c in df.columns],
            "missing": missing_mandatory,
        }
        if missing_mandatory:
            all_pass = False

        # Check recommended columns
        missing_recommended = [c for c in WOS_RECOMMENDED_TAGS if c not in df.columns]
        checks["recommended_columns"] = {
            "status": "PASS" if not missing_recommended else "WARNING",
            "present": [c for c in WOS_RECOMMENDED_TAGS if c in df.columns],
            "missing": missing_recommended,
        }

        # Check field integrity: mandatory fields have values
        field_popularity = {}
        for col in WOS_MANDATORY_TAGS:
            if col in df.columns:
                col_data = df[col]
                if isinstance(col_data, pd.DataFrame):
                    col_data = col_data.iloc[:, 0]
                non_empty = int((col_data.notna() & (col_data.astype(str).str.strip() != "") & (col_data.astype(str) != "nan")).sum())
                pct = (non_empty / len(df) * 100) if len(df) > 0 else 0
                field_popularity[col] = {"non_empty": non_empty, "percentage": round(pct, 1)}
            else:
                field_popularity[col] = {"non_empty": 0, "percentage": 0.0}

        low_fields = [f for f, v in field_popularity.items() if v["percentage"] < 50]
        checks["field_integrity"] = {
            "status": "PASS" if not low_fields else "WARNING",
            "field_stats": field_popularity,
            "low_coverage_fields": low_fields,
        }

        # Check author format
        if "AU" in df.columns:
            au_col = df["AU"]
            if isinstance(au_col, pd.DataFrame):
                au_col = au_col.iloc[:, 0]
            sample = au_col.head(50).dropna()
            comma_fmt = int(sample.astype(str).str.contains(",", na=False).sum())
            checks["author_format"] = {
                "status": "PASS" if comma_fmt > len(sample) * 0.5 else "WARNING",
                "comma_separated_count": comma_fmt,
                "sample_size": len(sample),
            }

        # Check year range
        if "PY" in df.columns:
            py_col = df["PY"]
            if isinstance(py_col, pd.DataFrame):
                py_col = py_col.iloc[:, 0]
            years = pd.to_numeric(py_col, errors="coerce").dropna()
            if len(years) > 0:
                checks["year_range"] = {
                    "status": "PASS" if 1900 <= int(years.min()) <= int(years.max()) <= 2030 else "WARNING",
                    "min": int(years.min()),
                    "max": int(years.max()),
                    "valid_count": len(years),
                }
            else:
                checks["year_range"] = {"status": "FAIL", "valid_count": 0}

        # Check DOI coverage
        if "DI" in df.columns:
            di_col = df["DI"]
            if isinstance(di_col, pd.DataFrame):
                di_col = di_col.iloc[:, 0]
            dois = int((di_col.notna() & (di_col.astype(str).str.strip() != "") & (di_col.astype(str) != "nan")).sum())
            checks["doi_coverage"] = {
                "status": "PASS" if dois > 0 else "WARNING",
                "count": dois,
                "percentage": round(dois / len(df) * 100, 1) if len(df) > 0 else 0,
            }

        status = "PASS" if all_pass else "FAIL"
        return {
            "status": status,
            "checks": checks,
            "validation_time": datetime.now().isoformat(),
        }

    # ==================================================================
    # Layer 2: Scientific Validation (R chain)
    # ==================================================================

    def _layer2_scientific_validation(self, df: pd.DataFrame,
                                      output_dir: Path) -> dict:
        """Run R validation chain with 3 fallback extraction methods.

        Method 1: Structured R objects -> JSON
        Method 2: R console output -> parse known fields -> JSON
        Method 3: Raw R output -> store as-is -> partial JSON
        """
        tmp_dir = Path(tempfile.mkdtemp(prefix="aibef_bibval_"))
        wos_path = tmp_dir / "validated_export.txt"
        r_script = tmp_dir / "bibliometrix_validate.R"
        r_result_json = tmp_dir / "result.json"
        r_output_path = tmp_dir / "R_output.txt"

        result = {
            "overall": False,
            "convert2df": {"success": False},
            "biblioAnalysis": {"success": False},
            "summary": {"success": False},
            "method_used": "none",
            "execution_time_seconds": 0,
            "r_version": "",
            "bibliometrix_version": "",
            "parser_method": "none",
        }

        try:
            # Write WoS plaintext file
            logger.info("[%s] Writing WoS plaintext file (%d records)...", self.NAME, len(df))
            self._write_wos_plaintext(wos_path, df)
            logger.info("[%s] WoS file written: %d bytes", self.NAME, wos_path.stat().st_size)

            # Write R script (with console output capture)
            self._write_r_validation_script_v2(r_script, wos_path, r_result_json, r_output_path)

            # Execute R
            logger.info("[%s] Running Rscript...", self.NAME)
            start = time.time()
            env = dict(os.environ)
            if os.environ.get("R_HOME"):
                env["R_HOME"] = os.environ["R_HOME"]
            proc = subprocess.run(
                [RSCRIPT, str(r_script)],
                capture_output=True, text=True, timeout=300,
                env=env
            )
            elapsed = time.time() - start
            result["execution_time_seconds"] = round(elapsed, 2)
            logger.info("[%s] Rscript finished in %.1fs (exit code %d)", self.NAME, elapsed, proc.returncode)

            # Read R console output (always)
            r_console = ""
            if r_output_path.exists():
                r_console = r_output_path.read_text(encoding="utf-8", errors="replace")
            if proc.stdout:
                r_console += "\n" + proc.stdout
            if proc.stderr:
                r_console += "\n" + proc.stderr

            # Parse R version and bibliometrix version from console
            result["r_version"] = self._extract_r_version(r_console)
            result["bibliometrix_version"] = self._extract_bibliometrix_version(r_console)

            # Save raw R output permanently
            raw_output_path = output_dir / "R_Validation_Output.txt"
            self._save_raw_output(raw_output_path, r_console, r_wos_path=wos_path,
                                  r_script=r_script, elapsed=elapsed, proc=proc)

            # Method 1: Try structured JSON extraction
            if r_result_json.exists():
                try:
                    parsed = self._method1_structured_json(r_result_json)
                    if parsed is not None:
                        result.update(parsed)
                        result["parser_method"] = "method1_structured_json"
                        result["overall"] = parsed.get("overall", False)
                        logger.info("[%s] Method 1 (structured JSON) succeeded (overall=%s)", self.NAME, result["overall"])
                        return result
                except Exception as e:
                    logger.warning("[%s] Method 1 failed: %s", self.NAME, e)

            # Method 2: Parse R console output for known fields
            try:
                parsed = self._method2_console_parsing(r_console)
                if parsed is not None:
                    result.update(parsed)
                    result["parser_method"] = "method2_console_parsing"
                    result["overall"] = parsed.get("convert2df", {}).get("success", False)
                    logger.info("[%s] Method 2 (console parsing) succeeded", self.NAME)
                    return result
            except Exception as e:
                logger.warning("[%s] Method 2 failed: %s", self.NAME, e)

            # Method 3: Raw output with partial JSON
            try:
                parsed = self._method3_raw_output_fallback(r_console)
                result.update(parsed)
                result["parser_method"] = "method3_raw_fallback"
                result["overall"] = parsed.get("convert2df", {}).get("success", False)
                logger.info("[%s] Method 3 (raw fallback) applied", self.NAME)
                return result
            except Exception as e:
                logger.warning("[%s] Method 3 failed: %s", self.NAME, e)

            return result

        except Exception as e:
            logger.error("[%s] Scientific validation error: %s", self.NAME, e)
            result["error"] = str(e)
            return result
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Extraction Method 1: Structured R objects -> JSON
    # ------------------------------------------------------------------

    def _method1_structured_json(self, json_path: Path) -> Optional[dict]:
        """Parse R-generated JSON with robust handling."""
        raw = json_path.read_text(encoding="utf-8", errors="replace")
        raw = raw.strip()
        if not raw:
            return None

        # Try direct JSON parse
        data = json.loads(raw)

        # Handle case where JSON is a list (wrapping bug)
        if isinstance(data, list):
            if len(data) > 0 and isinstance(data[0], dict):
                data = data[0]
            else:
                return None

        if not isinstance(data, dict):
            return None

        # Normalize all values to simple types
        normalized = {}
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)):
                normalized[k] = v
            elif isinstance(v, dict):
                normalized[k] = v
            elif isinstance(v, list):
                normalized[k] = str(v)[:2000]
            elif v is None:
                normalized[k] = ""
            else:
                normalized[k] = str(v)[:2000]

        overall = normalized.get("overall", "")
        is_success = overall == "TRUE" or overall is True

        conv_val = normalized.get("convert2df", "FALSE")
        bio_val = normalized.get("biblioAnalysis", "FALSE")
        summ_val = normalized.get("summary", "FALSE")

        return {
            "overall": is_success,
            "convert2df": {
                "success": str(conv_val) == "TRUE",
                "nrow": int(normalized.get("convert2df_nrow", 0) or 0),
                "ncol": int(normalized.get("convert2df_ncol", 0) or 0),
                "columns": str(normalized.get("convert2df_cols", "")),
            },
            "biblioAnalysis": {
                "success": str(bio_val) == "TRUE",
                "status": str(bio_val),
                "M": str(normalized.get("biblioAnalysis_M", "")),
                "n": str(normalized.get("biblioAnalysis_n", "")),
            },
            "summary": {
                "success": str(summ_val) == "TRUE",
                "status": str(summ_val),
                "output": str(normalized.get("summary_output", ""))[:2000],
            },
            "message": str(normalized.get("message", "")),
        }

    # ------------------------------------------------------------------
    # Extraction Method 2: Parse R console output
    # ------------------------------------------------------------------

    def _method2_console_parsing(self, console_output: str) -> Optional[dict]:
        """Parse known Bibliometrix output patterns from R console."""
        if not console_output:
            return None

        result = {
            "overall": False,
            "convert2df": {"success": False, "nrow": 0, "ncol": 0, "columns": ""},
            "biblioAnalysis": {"success": False, "status": ""},
            "summary": {"success": False, "status": "", "output": ""},
            "message": "",
        }

        # Parse convert2df
        conv_match = re.search(
            r"AIBEF_R:\s*convert2df\s+OK\s*-\s*(\d+)\s+rows?,\s*(\d+)\s+cols?",
            console_output
        )
        if conv_match:
            result["convert2df"]["success"] = True
            result["convert2df"]["nrow"] = int(conv_match.group(1))
            result["convert2df"]["ncol"] = int(conv_match.group(2))

        # Check for convert2df error
        if "FATAL ERROR" in console_output and "convert2df" in console_output:
            result["convert2df"]["success"] = False
            return None

        # Parse biblioAnalysis
        if "biblioAnalysis OK" in console_output:
            result["biblioAnalysis"]["success"] = True
            result["biblioAnalysis"]["status"] = "TRUE"
        elif "biblioAnalysis error" in console_output:
            err_match = re.search(r"biblioAnalysis error:\s*(.+)", console_output)
            result["biblioAnalysis"]["status"] = f"ERROR: {err_match.group(1) if err_match else 'unknown'}"

        # Parse summary
        if re.search(r"summary OK", console_output):
            result["summary"]["success"] = True
            result["summary"]["status"] = "TRUE"
        elif "summary error" in console_output:
            err_match = re.search(r"summary error:\s*(.+)", console_output)
            result["summary"]["status"] = f"ERROR: {err_match.group(1) if err_match else 'unknown'}"

        # Extract summary output block
        summary_match = re.search(
            r"\n(MAIN BIBLIOMETRIC ANALYSIS.*?)(?:\n\n|\Z)",
            console_output, re.DOTALL
        )
        if summary_match:
            result["summary"]["output"] = summary_match.group(1)[:2000]

        result["overall"] = result["convert2df"]["success"]
        result["message"] = (
            f"convert2df: {'TRUE' if result['convert2df']['success'] else 'FALSE'}"
            f" | biblioAnalysis: {result['biblioAnalysis']['status']}"
            f" | summary: {result['summary']['status']}"
        )

        return result if result["convert2df"]["success"] else None

    # ------------------------------------------------------------------
    # Extraction Method 3: Raw output fallback
    # ------------------------------------------------------------------

    def _method3_raw_output_fallback(self, console_output: str) -> dict:
        """Last resort: store raw output and generate partial JSON."""
        has_convert = "convert2df" in console_output.lower()
        has_rows = bool(re.search(r"\d+\s+rows?", console_output))

        return {
            "overall": has_convert and has_rows,
            "convert2df": {
                "success": has_convert,
                "nrow": 0,
                "ncol": 0,
                "columns": "",
            },
            "biblioAnalysis": {"success": False, "status": "NOT_PARSED"},
            "summary": {"success": False, "status": "NOT_PARSED", "output": ""},
            "message": f"Raw fallback: convert2df mention={'YES' if has_convert else 'NO'}",
        }

    # ------------------------------------------------------------------
    # Helpers for Layer 2
    # ------------------------------------------------------------------

    def _extract_r_version(self, console: str) -> str:
        m = re.search(r"R version (\d+\.\d+\.\d+)", console)
        return m.group(1) if m else ""

    def _extract_bibliometrix_version(self, console: str) -> str:
        m = re.search(r"bibliometrix version:\s*(\S+)", console)
        if m:
            return m.group(1)
        m = re.search(r"bibliometrix\s+(\d+\.\d+\.\d+)", console)
        return m.group(1) if m else ""

    def _save_raw_output(self, path: Path, console: str, *,
                         r_wos_path: Path = None, r_script: Path = None,
                         elapsed: float = 0, proc: subprocess.CompletedProcess = None):
        """Write R_Validation_Output.txt as permanent certification evidence."""
        lines = [
            "=" * 70,
            "AIBEF R VALIDATION OUTPUT - PERMANENT CERTIFICATION EVIDENCE",
            "=" * 70,
            f"Timestamp: {datetime.now().isoformat()}",
            f"R Version: {self._extract_r_version(console)}",
            f"Bibliometrix Version: {self._extract_bibliometrix_version(console)}",
            f"Execution Time: {elapsed:.1f}s",
            f"R Exit Code: {proc.returncode if proc else 'N/A'}",
            f"WoS Source: {r_wos_path}",
            f"R Script: {r_script}",
            "",
            "-" * 70,
            "R CONSOLE OUTPUT:",
            "-" * 70,
            console,
            "",
            "-" * 70,
            "R STDOUT (raw):",
            "-" * 70,
            proc.stdout if proc else "N/A",
            "",
            "-" * 70,
            "R STDERR (raw):",
            "-" * 70,
            proc.stderr if proc else "N/A",
            "",
            "=" * 70,
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")

    # ==================================================================
    # Layer 3: Reporting (JSON, DOCX)
    # ==================================================================

    def _layer3_reporting(self, layer1: dict, layer2: dict,
                          df: pd.DataFrame, state: PipelineState,
                          output_dir: Path) -> dict:
        """Generate R_Validation.json and extend DOCX report.
        Failures here NEVER invalidate certification."""
        reporting_status = "PASS"
        files_generated = []

        # Generate R_Validation.json
        try:
            json_path = output_dir / "R_Validation.json"
            json_data = {
                "execution_status": "COMPLETE",
                "timestamp": datetime.now().isoformat(),
                "rows": len(df),
                "columns": len(df.columns),
                "r_version": layer2.get("r_version", ""),
                "bibliometrix_version": layer2.get("bibliometrix_version", ""),
                "convert2df": layer2.get("convert2df", {}),
                "biblioAnalysis": layer2.get("biblioAnalysis", {}),
                "summary": layer2.get("summary", {}),
                "statistics": {
                    "total_records": len(df),
                    "mandatory_fields_present": [c for c in WOS_MANDATORY_TAGS if c in df.columns],
                    "mandatory_fields_missing": [c for c in WOS_MANDATORY_TAGS if c not in df.columns],
                },
                "warnings": layer1.get("checks", {}).get("field_integrity", {}).get("low_coverage_fields", []),
                "errors": [layer2["message"]] if layer2.get("message") and "ERROR" in str(layer2.get("message", "")) else [],
                "execution_time_seconds": layer2.get("execution_time_seconds", 0),
                "certification_status": state.prisma_data.get("r_validation", {}).get("certification", {}).get("certification_status", "UNKNOWN"),
                "parser_method": layer2.get("parser_method", "unknown"),
                "layer1_structural": layer1,
            }
            json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False, default=str),
                                encoding="utf-8")
            files_generated.append("R_Validation.json")
        except Exception as e:
            logger.error("[%s] Layer 3: JSON generation failed: %s", self.NAME, e)
            reporting_status = "PARTIAL"

        # Extend DOCX (handled by export agent)
        try:
            self._export_validation_docx_v2(layer1, layer2, df, state, output_dir)
            files_generated.append("Bibliometrix_Validation_Report.docx")
        except Exception as e:
            logger.error("[%s] Layer 3: DOCX generation failed: %s", self.NAME, e)
            reporting_status = "PARTIAL"

        return {
            "status": reporting_status,
            "files_generated": files_generated,
        }

    # ------------------------------------------------------------------
    # DOCX Report (3-layer)
    # ------------------------------------------------------------------

    def _export_validation_docx_v2(self, layer1: dict, layer2: dict,
                                    df: pd.DataFrame, state: PipelineState,
                                    output_dir: Path):
        """Generate the 3-layer Bibliometrix Validation Report."""
        from docx import Document
        from docx.shared import Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        path = output_dir / "Bibliometrix_Validation_Report.docx"
        doc = Document()
        title = doc.add_heading("Bibliometrix Validation Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")

        # Certification status
        cert = state.prisma_data.get("r_validation", {}).get("certification", {})
        cert_status = cert.get("certification_status", "UNKNOWN")
        p = doc.add_paragraph()
        run = p.add_run(f"Certification Status: {cert_status}")
        run.bold = True
        doc.add_paragraph("")

        # ---- Layer 1: Structural Validation ----
        doc.add_heading("Layer 1: Structural Validation (Python-only)", level=1)
        p = doc.add_paragraph()
        run = p.add_run(f"Status: {layer1['status']}")
        run.bold = True

        l1_checks = layer1.get("checks", {})
        for check_name, check_data in l1_checks.items():
            doc.add_heading(check_name.replace("_", " ").title(), level=2)
            status = check_data.get("status", "UNKNOWN")
            p = doc.add_paragraph()
            p.add_run(f"Status: {status}").bold = True
            for key, value in check_data.items():
                if key != "status":
                    if isinstance(value, dict):
                        doc.add_paragraph(f"  {key}:")
                        for sk, sv in value.items():
                            if isinstance(sv, dict):
                                doc.add_paragraph(f"    {sk}: {sv.get('non_empty', 'N/A')} ({sv.get('percentage', 'N/A')}%)")
                            else:
                                doc.add_paragraph(f"    {sk}: {sv}")
                    elif isinstance(value, list):
                        doc.add_paragraph(f"  {key}: {', '.join(str(v) for v in value[:20])}")
                    else:
                        doc.add_paragraph(f"  {key}: {value}")

        # ---- Layer 2: Scientific Validation ----
        doc.add_heading("Layer 2: Scientific Validation (R Chain)", level=1)
        p = doc.add_paragraph()
        run = p.add_run(f"Overall: {'PASS' if layer2.get('overall') else 'FAIL'}")
        run.bold = True

        if layer2.get("r_version"):
            doc.add_paragraph(f"R Version: {layer2['r_version']}")
        if layer2.get("bibliometrix_version"):
            doc.add_paragraph(f"Bibliometrix Version: {layer2['bibliometrix_version']}")
        if layer2.get("execution_time_seconds"):
            doc.add_paragraph(f"Execution Time: {layer2['execution_time_seconds']}s")

        # convert2df
        conv = layer2.get("convert2df", {})
        doc.add_heading("convert2df()", level=2)
        t = doc.add_table(rows=4, cols=2, style="Table Grid")
        t.cell(0, 0).text = "Status"
        t.cell(0, 1).text = "PASSED" if conv.get("success") else "FAILED"
        t.cell(1, 0).text = "Rows"
        t.cell(1, 1).text = str(conv.get("nrow", "N/A"))
        t.cell(2, 0).text = "Columns"
        t.cell(2, 1).text = str(conv.get("ncol", "N/A"))
        t.cell(3, 0).text = "Column Names"
        t.cell(3, 1).text = str(conv.get("columns", "N/A"))[:200]

        # biblioAnalysis
        bio = layer2.get("biblioAnalysis", {})
        doc.add_heading("biblioAnalysis()", level=2)
        t = doc.add_table(rows=3, cols=2, style="Table Grid")
        t.cell(0, 0).text = "Status"
        t.cell(0, 1).text = "PASSED" if bio.get("success") else "FAILED"
        t.cell(1, 0).text = "M (Sources)"
        t.cell(1, 1).text = str(bio.get("M", "N/A"))
        t.cell(2, 0).text = "n (Documents)"
        t.cell(2, 1).text = str(bio.get("n", "N/A"))

        # summary
        summ = layer2.get("summary", {})
        doc.add_heading("summary()", level=2)
        p = doc.add_paragraph()
        p.add_run(f"Status: {'PASSED' if summ.get('success') else 'FAILED/SKIPPED'}").bold = True
        if summ.get("output"):
            doc.add_paragraph(summ["output"][:1500])

        # ---- Layer 3: Reporting ----
        doc.add_heading("Layer 3: Reporting", level=1)
        doc.add_paragraph(f"Parser Method: {layer2.get('parser_method', 'unknown')}")
        doc.add_paragraph(f"Raw Output: R_Validation_Output.txt")
        doc.add_paragraph(f"JSON Status: R_Validation.json")
        doc.add_paragraph("Note: Layer 3 failures do NOT invalidate certification.")

        # ---- Certification Summary ----
        doc.add_heading("Certification Summary", level=1)
        t = doc.add_table(rows=5, cols=2, style="Table Grid")
        t.cell(0, 0).text = "Layer 1 (Structural)"
        t.cell(0, 1).text = layer1["status"]
        t.cell(1, 0).text = "Layer 2 (Scientific)"
        t.cell(1, 1).text = "PASS" if layer2.get("overall") else "FAIL"
        t.cell(2, 0).text = "Certification"
        t.cell(2, 1).text = cert_status
        t.cell(3, 0).text = "Dataset Rows"
        t.cell(3, 1).text = str(len(df))
        t.cell(4, 0).text = "Dataset Columns"
        t.cell(4, 1).text = str(len(df.columns))

        doc.save(str(path))
        logger.info("[%s] DOCX report saved: %s", self.NAME, path)

    # ==================================================================
    # WoS plaintext writer
    # ==================================================================

    def _write_wos_plaintext(self, path: Path, df: pd.DataFrame):
        """Write the full dataset as a valid WoS plaintext export."""
        WOS_TAGS = ["PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID",
                     "AB", "C1", "RP", "EM", "FU", "FX", "CR", "NR", "TC",
                     "Z9", "U1", "U2", "PY", "PU", "PI", "PA", "SN", "EI",
                     "J9", "JI", "PD", "VL", "IS", "BP", "EP", "DI", "PG",
                     "WC", "SC", "GA", "UT", "DA"]
        MULTI_LINE_TAGS = {"AU", "AF", "C1", "DE", "ID", "CR", "AB", "FX", "FU"}

        work = df.copy()
        for col in ["PT", "LA", "DT"]:
            if col not in work.columns:
                work[col] = ""
            work[col] = work[col].replace("", {"PT": "J", "LA": "English", "DT": "Article"}.get(col, ""))

        if "C1" not in work.columns:
            work["C1"] = ""
        if "RP" not in work.columns:
            work["RP"] = ""

        for idx in range(len(work)):
            c1_val = str(work.iloc[idx].get("C1", "")).strip()
            af_val = str(work.iloc[idx].get("AF", "")).strip()
            rp_val = str(work.iloc[idx].get("RP", "")).strip()
            if not c1_val and af_val:
                work.at[work.index[idx], "C1"] = f"[Unknown] {af_val}"
            if not rp_val and af_val:
                first_author = af_val.split(";")[0].strip()
                work.at[work.index[idx], "RP"] = first_author

        lines = ["FN Clarivate Analytics Web of Science", "VR 1.0"]

        for idx in range(len(work)):
            row = work.iloc[idx]
            pt_val = str(row.get("PT", "")).strip() or "J"
            lines.append(f"PT  {pt_val}")
            for tag in WOS_TAGS:
                if tag == "PT":
                    continue
                if tag not in work.columns:
                    continue
                raw = row.get(tag, "")
                if isinstance(raw, pd.Series):
                    raw = raw.iloc[0] if len(raw) > 0 else ""
                if pd.isna(raw):
                    continue
                val = str(raw).strip()
                if not val:
                    continue
                # Normalize embedded newlines to spaces to prevent malformed WoS lines
                val = val.replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
                val = ' '.join(val.split())
                if tag in MULTI_LINE_TAGS and len(val) > 80:
                    lines.append(f"{tag}  {val[:80]}")
                    remaining = val[80:]
                    while remaining:
                        lines.append(f"   {remaining[:80]}")
                        remaining = remaining[80:]
                else:
                    lines.append(f"{tag}  {val}")
            lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    # ==================================================================
    # R Script Writer (v2 with console capture + robust JSON)
    # ==================================================================

    def _write_r_validation_script_v2(self, script_path: Path,
                                       wos_path: Path, result_path: Path,
                                       output_path: Path):
        """Write R script with console output capture and robust JSON generation."""
        wos_esc = str(wos_path).replace("\\", "/")
        res_esc = str(result_path).replace("\\", "/")
        out_esc = str(output_path).replace("\\", "/")

        script = (
            '# AIBEF R Validation Script (v2)\n'
            '# Captures console output AND writes structured JSON\n'
            'tryCatch(suppressMessages(library(bibliometrix)), error=function(e) {\n'
            '    cat(paste0("AIBEF_R: bibliometrix load FAILED: ", conditionMessage(e), "\\n"))\n'
            '})\n'
            'cat(paste0("R version: ", R.version.string, "\\n"))\n'
            'cat(paste0("bibliometrix version: ", as.character(packageVersion("bibliometrix")), "\\n"))\n'
            '\n'
            '# Capture all console output to file\n'
            'con <- file("' + out_esc + '", open="wt")\n'
            'sink(con, type="output")\n'
            'sink(con, type="message")\n'
            '\n'
            'result <- list()\n'
            'result$convert2df <- "FALSE"\n'
            'result$biblioAnalysis <- "FALSE"\n'
            'result$summary <- "FALSE"\n'
            'result$overall <- "FALSE"\n'
            '\n'
            'tryCatch({\n'
            '    cat("AIBEF_R: Running convert2df...\\n")\n'
            '    bib <- convert2df("' + wos_esc + '", dbsource="wos", format="plaintext")\n'
            '    cat(paste0("AIBEF_R: convert2df OK - ", nrow(bib), " rows, ", ncol(bib), " cols\\n"))\n'
            '    result$convert2df_nrow <- as.character(nrow(bib))\n'
            '    result$convert2df_ncol <- as.character(ncol(bib))\n'
            '    result$convert2df_cols <- paste(names(bib), collapse=", ")\n'
            '    result$convert2df <- "TRUE"\n'
            '\n'
            '    cat("AIBEF_R: Running biblioAnalysis...\\n")\n'
            '    bibAnalysis <- tryCatch({\n'
            '        ba <- biblioAnalysis(bib, sep=";")\n'
            '        cat("AIBEF_R: biblioAnalysis OK\\n")\n'
            '        result$biblioAnalysis <- "TRUE"\n'
            '        result$biblioAnalysis_M <- tryCatch(as.character(ba$M), error=function(e) "NA")\n'
            '        result$biblioAnalysis_n <- tryCatch(as.character(ba$n), error=function(e) "NA")\n'
            '        ba\n'
            '    }, error=function(e) {\n'
            '        cat(paste0("AIBEF_R: biblioAnalysis error: ", conditionMessage(e), "\\n"))\n'
            '        result$biblioAnalysis <- paste0("ERROR: ", conditionMessage(e))\n'
            '        NULL\n'
            '    })\n'
            '\n'
            '    if (!is.null(bibAnalysis)) {\n'
            '        cat("AIBEF_R: Running summary...\\n")\n'
            '        s <- tryCatch({\n'
            '            sm <- summary(bibAnalysis, k=10, pause=FALSE)\n'
            '            cat("AIBEF_R: summary OK\\n")\n'
            '            result$summary <- "TRUE"\n'
            '            sm\n'
            '        }, error=function(e) {\n'
            '            cat(paste0("AIBEF_R: summary error: ", conditionMessage(e), "\\n"))\n'
            '            result$summary <- paste0("ERROR: ", conditionMessage(e))\n'
            '            NULL\n'
            '        })\n'
            '        if (!is.null(s)) {\n'
            '            result$summary_output <- tryCatch(\n'
            '                paste(capture.output(print(s)), collapse="\\n"),\n'
            '                error=function(e) "capture failed"\n'
            '            )\n'
            '        }\n'
            '    } else {\n'
            '        result$summary <- "SKIPPED"\n'
            '    }\n'
            '\n'
            '    result$overall <- "TRUE"\n'
            '    result$message <- paste0(\n'
            '        "convert2df: ", result$convert2df,\n'
            '        " | biblioAnalysis: ", result$biblioAnalysis,\n'
            '        " | summary: ", result$summary\n'
            '    )\n'
            '}, error=function(e) {\n'
            '    cat(paste0("AIBEF_R: FATAL ERROR - ", conditionMessage(e), "\\n"))\n'
            '    result$overall <- "FALSE"\n'
            '    result$error <- conditionMessage(e)\n'
            '})\n'
            '\n'
            '# Flush console sinks BEFORE writing JSON\n'
            'sink()\n'
            'sink()\n'
            '\n'
            '# Write JSON with fallback\n'
            'tryCatch({\n'
            '    json_str <- jsonlite::toJSON(result, auto_unbox=TRUE, pretty=TRUE)\n'
            '    writeLines(json_str, "' + res_esc + '")\n'
            '    cat("AIBEF_R: JSON result written\\n")\n'
            '}, error=function(e) {\n'
            '    cat(paste0("AIBEF_R: JSON write error: ", conditionMessage(e), "\\n"))\n'
            '    # Manual JSON fallback\n'
            '    lines <- c("{")\n'
            '    for (nm in names(result)) {\n'
            '        val <- result[[nm]]\n'
            '        if (is.null(val)) val <- ""\n'
            '        val_str <- gsub("\\\\", "\\\\\\\\", as.character(val))\n'
            '        val_str <- gsub("\\\"", "\\\\\\\"", val_str)\n'
            '        val_str <- gsub("\\n", " ", val_str)\n'
            '        lines <- c(lines, paste0("  \\"", nm, "\\": \\"", val_str, "\\""))\n'
            '    }\n'
            '    lines <- c(lines, "}")\n'
            '    writeLines(paste(lines, collapse="\\n"), "' + res_esc + '")\n'
            '    cat("AIBEF_R: Manual JSON written\\n")\n'
            '})\n'
        )
        script_path.write_text(script, encoding="utf-8")

    # ==================================================================
    # Dataset repair (unchanged from original)
    # ==================================================================

    def _repair_dataset(self, df: pd.DataFrame, error: str) -> pd.DataFrame:
        """Attempt to repair based on error message."""
        df = df.copy()

        if "column" in error.lower() or "missing" in error.lower():
            for col in ["PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID",
                         "AB", "C1", "RP", "PY", "UT"]:
                if col not in df.columns:
                    df[col] = ""

        if "author" in error.lower():
            if "AU" in df.columns:
                col = df["AU"]
                if isinstance(col, pd.DataFrame):
                    col = col.iloc[:, 0]
                df["AU"] = col.apply(
                    lambda x: x if pd.notna(x) and "," in str(x) else x
                )

        if "year" in error.lower() or "py" in error.lower():
            if "PY" in df.columns:
                col = df["PY"]
                if isinstance(col, pd.DataFrame):
                    col = col.iloc[:, 0]
                df["PY"] = pd.to_numeric(col, errors="coerce").fillna(0).astype(int)

        if "encoding" in error.lower():
            for col in df.select_dtypes(include=["object"]).columns:
                series = df[col]
                if isinstance(series, pd.DataFrame):
                    series = series.iloc[:, 0]
                df[col] = series.apply(
                    lambda x: x.encode("utf-8", errors="replace").decode("utf-8")
                    if isinstance(x, str) else x
                )

        if "empty" in error.lower() or "rows" in error.lower():
            for col in ["AU", "TI", "SO"]:
                if col in df.columns:
                    series = df[col]
                    if isinstance(series, pd.DataFrame):
                        series = series.iloc[:, 0]
                    df = df[series.replace("", pd.NA).notna()]

        df = df.reset_index(drop=True)
        df = df.replace({np.nan: "", None: ""})
        return df
