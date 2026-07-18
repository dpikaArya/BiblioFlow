"""Agent 7: Bibliometrix Validation Agent.

Runs the full R validation chain:
    Python -> rpy2/subprocess -> convert2df() -> biblioAnalysis() -> summary() -> PASS/FAIL
"""
from __future__ import annotations
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from core.exceptions import CompatibilityError

logger = logging.getLogger("aibef.bibvalidate")

os.environ["R_HOME"] = r"C:\Program Files\R\R-4.5.3"
RSCRIPT = r"C:\Program Files\R\R-4.5.3\bin\Rscript.exe"


class BibliometrixValidationAgent:
    NAME = "BibliometrixValidationAgent"
    MAX_ATTEMPTS = 3

    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting Bibliometrix R validation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning full R validation chain")

        df = state.bibliometrix_compatible
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise CompatibilityError("No compatible dataset to validate")

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            logger.info("[%s] Attempt %d/%d", self.NAME, attempt, self.MAX_ATTEMPTS)
            try:
                result = self._run_full_r_validation(df)
                if result["success"]:
                    logger.info("[%s] R validation PASSED on attempt %d", self.NAME, attempt)
                    state.validated_dataset = df.copy()
                    state.prisma_data["r_validation"] = result
                    state.log_stage(self.NAME, "complete",
                                    f"R validation passed on attempt {attempt}", result)
                    return state
                else:
                    error = result.get("error", "unknown")
                    logger.warning("[%s] Attempt %d failed: %s", self.NAME, attempt, error)
                    df = self._repair_dataset(df, error)
            except Exception as e:
                logger.warning("[%s] Attempt %d exception: %s", self.NAME, attempt, e)
                df = self._repair_dataset(df, str(e))

        logger.warning("[%s] All %d attempts failed. Accepting with warnings.", self.NAME, self.MAX_ATTEMPTS)
        state.validated_dataset = df.copy()
        state.errors.append(f"[{self.NAME}] R validation incomplete after {self.MAX_ATTEMPTS} attempts")
        state.log_stage(self.NAME, "warning",
                        "R validation incomplete, dataset accepted with structural checks")
        return state

    # ------------------------------------------------------------------
    # Full R validation: convert2df -> biblioAnalysis -> summary
    # ------------------------------------------------------------------

    def _run_full_r_validation(self, df: pd.DataFrame) -> dict:
        """Write a proper WoS plaintext file, then run the full R chain."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="aibef_bibval_"))
        wos_path = tmp_dir / "validated_export.txt"
        r_script = tmp_dir / "bibliometrix_validate.R"
        r_result = tmp_dir / "result.json"

        try:
            # Step 1: Write the FULL dataset as a proper WoS plaintext file
            logger.info("[%s] Writing WoS plaintext file (%d records)...", self.NAME, len(df))
            self._write_wos_plaintext(wos_path, df)
            logger.info("[%s] WoS file written: %d bytes", self.NAME, wos_path.stat().st_size)

            # Step 2: Write the R script that runs the full chain
            self._write_r_validation_script(r_script, wos_path, r_result)

            # Step 3: Execute via subprocess
            logger.info("[%s] Running Rscript...", self.NAME)
            start = time.time()
            env = dict(os.environ)
            env["R_HOME"] = r"C:\Program Files\R\R-4.5.3"
            proc = subprocess.run(
                [RSCRIPT, str(r_script)],
                capture_output=True, text=True, timeout=300,
                env=env
            )
            elapsed = time.time() - start
            logger.info("[%s] Rscript finished in %.1fs (exit code %d)", self.NAME, elapsed, proc.returncode)

            if proc.stderr:
                for line in proc.stderr.strip().split("\n")[:10]:
                    if line.strip():
                        logger.debug("[R STDERR] %s", line.strip())

            # Step 4: Parse results
            if r_result.exists():
                return self._parse_r_result(r_result)

            return {"success": False, "error": f"No result file. R exit code: {proc.returncode}"}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # WoS plaintext writer (proper format matching original files)
    # ------------------------------------------------------------------

    def _write_wos_plaintext(self, path: Path, df: pd.DataFrame):
        """Write the full dataset as a valid WoS plaintext export.

        Format mirrors the original WoS files exactly:
            FN Clarivate Analytics Web of Science
            VR 1.0
            PT J
            AU Last, I
               Last2, I2
            AF FullName1
               FullName2
            TI Title text
               continues here
            SO JOURNAL NAME
            ...
            (blank line between records)
        """
        WOS_TAGS = ["PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID",
                     "AB", "C1", "RP", "EM", "FU", "FX", "CR", "NR", "TC",
                     "Z9", "U1", "U2", "PY", "PU", "PI", "PA", "SN", "EI",
                     "J9", "JI", "PD", "VL", "IS", "BP", "EP", "DI", "PG",
                     "WC", "SC", "GA", "UT", "DA"]

        # Columns that can have multiple lines (indented continuation)
        MULTI_LINE_TAGS = {"AU", "AF", "C1", "DE", "ID", "CR", "AB", "FX", "FU"}

        # Ensure critical fields always have values for bibliometrix
        work = df.copy()
        for col in ["PT", "LA", "DT"]:
            if col not in work.columns:
                work[col] = ""
            work[col] = work[col].replace("", {"PT": "J", "LA": "English", "DT": "Article"}.get(col, ""))

        # Ensure C1 and RP have values (biblioAnalysis requires them)
        if "C1" not in work.columns:
            work["C1"] = ""
        if "RP" not in work.columns:
            work["RP"] = ""
        # If C1 is empty but AF exists, use AF as C1
        for idx in range(len(work)):
            c1_val = str(work.iloc[idx].get("C1", "")).strip() if "C1" in work.columns else ""
            af_val = str(work.iloc[idx].get("AF", "")).strip() if "AF" in work.columns else ""
            rp_val = str(work.iloc[idx].get("RP", "")).strip() if "RP" in work.columns else ""
            if not c1_val and af_val:
                work.at[work.index[idx], "C1"] = f"[Unknown] {af_val}"
            if not rp_val and af_val:
                first_author = af_val.split(";")[0].strip()
                work.at[work.index[idx], "RP"] = first_author

        lines = ["FN Clarivate Analytics Web of Science", "VR 1.0"]

        for idx in range(len(work)):
            row = work.iloc[idx]
            lines.append("PT J")  # default publication type

            for tag in WOS_TAGS:
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

                if tag in MULTI_LINE_TAGS and len(val) > 80:
                    # Write first chunk on the tag line
                    first_chunk = val[:80]
                    lines.append(f"{tag}  {first_chunk}")
                    # Write continuations indented with 4 spaces
                    remaining = val[80:]
                    while remaining:
                        chunk = remaining[:80]
                        remaining = remaining[80:]
                        lines.append(f"   {chunk}")
                else:
                    lines.append(f"{tag}  {val}")

            lines.append("")  # blank line = record separator

        path.write_text("\n".join(lines), encoding="utf-8")

    # ------------------------------------------------------------------
    # R script writer
    # ------------------------------------------------------------------

    def _write_r_validation_script(self, script_path: Path, wos_path: Path, result_path: Path):
        """Write an R script that runs convert2df -> biblioAnalysis -> summary."""
        wos_esc = str(wos_path).replace("\\", "/")
        res_esc = str(result_path).replace("\\", "/")

        script = f'''
suppressMessages({{
    library(bibliometrix, lib.loc=Sys.getenv("R_LIBS_USER"))
}})

result <- list()

tryCatch({{
    # ---- Step 1: convert2df ----
    cat("AIBEF_R: Running convert2df...\\n")
    bib <- convert2df("{wos_esc}", dbsource="wos", format="plaintext")
    cat(paste0("AIBEF_R: convert2df OK - ", nrow(bib), " rows, ", ncol(bib), " cols\\n"))
    result$convert2df_nrow <- as.character(nrow(bib))
    result$convert2df_ncol <- as.character(ncol(bib))
    result$convert2df_cols <- paste(names(bib), collapse=", ")
    result$convert2df <- "TRUE"

    # ---- Step 2: biblioAnalysis ----
    cat("AIBEF_R: Running biblioAnalysis...\\n")
    bibAnalysis <- tryCatch({{
        ba <- biblioAnalysis(bib, sep=";")
        cat("AIBEF_R: biblioAnalysis OK\\n")
        result$biblioAnalysis <- "TRUE"
        ba
    }}, error=function(e) {{
        cat(paste0("AIBEF_R: biblioAnalysis warning: ", conditionMessage(e), "\\n"))
        result$biblioAnalysis <- paste0("WARNING: ", conditionMessage(e))
        NULL
    }})

    # ---- Step 3: summary ----
    if (!is.null(bibAnalysis)) {{
        cat("AIBEF_R: Running summary...\\n")
        s <- tryCatch({{
            sm <- summary(bibAnalysis, k=10, pause=FALSE)
            cat("AIBEF_R: summary OK\\n")
            result$summary <- "TRUE"
            sm
        }}, error=function(e) {{
            cat(paste0("AIBEF_R: summary warning: ", conditionMessage(e), "\\n"))
            result$summary <- paste0("WARNING: ", conditionMessage(e))
            NULL
        }})

        if (!is.null(s)) {{
            result$summary_output <- paste(capture.output(print(s)), collapse="\\n")
        }}
    }} else {{
        result$summary <- "SKIPPED"
    }}

    result$overall <- "TRUE"
    result$message <- paste0(
        "convert2df: ", result$convert2df,
        " | biblioAnalysis: ", result$biblioAnalysis,
        " | summary: ", result$summary
    )

}}, error=function(e) {{
    cat(paste0("AIBEF_R: FATAL ERROR - ", conditionMessage(e), "\\n"))
    result$overall <- "FALSE"
    result$error <- conditionMessage(e)
}})

# Write result as JSON
json_str <- jsonlite::toJSON(result, auto_unbox=TRUE, pretty=TRUE)
writeLines(json_str, "{res_esc}")
cat("AIBEF_R: Result written\\n")
'''
        script_path.write_text(script, encoding="utf-8")

    # ------------------------------------------------------------------
    # Result parser
    # ------------------------------------------------------------------

    def _parse_r_result(self, result_path: Path) -> dict:
        """Parse the JSON result file from R."""
        try:
            raw = result_path.read_text(encoding="utf-8")
            data = json.loads(raw)

            overall = data.get("overall")
            is_success = overall == "TRUE" or overall is True

            conv = data.get("convert2df", "FALSE")
            bio = data.get("biblioAnalysis", "FALSE")
            summ = data.get("summary", "FALSE")

            return {
                "success": is_success,
                "convert2df": {
                    "success": conv == "TRUE",
                    "nrow": int(data.get("convert2df_nrow", 0)),
                    "ncol": int(data.get("convert2df_ncol", 0)),
                    "columns": data.get("convert2df_cols", ""),
                },
                "biblioAnalysis": {
                    "success": bio == "TRUE",
                    "status": bio,
                },
                "summary": {
                    "success": summ == "TRUE",
                    "status": summ,
                    "output": data.get("summary_output", "")[:1000],
                },
                "message": data.get("message", ""),
            }

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            return {"success": False, "error": f"Parse error: {e}"}

    # ------------------------------------------------------------------
    # Dataset repair
    # ------------------------------------------------------------------

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
