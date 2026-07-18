"""Biblioshiny Launch Manager - Certification validator."""
from __future__ import annotations
import json
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional

from .models import CertificationCheck, LaunchPrechecks, DatasetInfo, REnvironmentInfo
from .config import BiblioshinyConfig


def check_certification(output_dir: Path) -> list[CertificationCheck]:
    """Check AIBEF certification status from the certification run output.

    Verifies that all pipeline stages passed and R certification passed.
    Returns a list of CertificationCheck results.
    """
    checks: list[CertificationCheck] = []

    audit_path = output_dir / "Audit_Log.json"
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            stages = audit.get("stages", {}) if isinstance(audit, dict) else {}
            r_cert = audit.get("r_certification", {}) if isinstance(audit, dict) else {}

            passed_count = 0
            failed_stages = []
            if isinstance(stages, dict):
                for name, info in stages.items():
                    if isinstance(info, dict):
                        status = info.get("status", "")
                        if status == "PASS":
                            passed_count += 1
                        elif status in ("FAIL", "FAILED"):
                            failed_stages.append(name)
                    else:
                        passed_count += 1

            r_all_pass = True
            if isinstance(r_cert, dict):
                for step_name, step_info in r_cert.items():
                    if isinstance(step_info, dict) and not step_info.get("success", False):
                        r_all_pass = False

            checks.append(CertificationCheck(
                name="pipeline_stages",
                passed=len(failed_stages) == 0 and passed_count > 0,
                message=f"{passed_count} stages passed, {len(failed_stages)} failed",
            ))
            checks.append(CertificationCheck(
                name="r_certification",
                passed=r_all_pass and len(r_cert) > 0,
                message=f"{len(r_cert)} R checks" if r_cert else "No R certification data",
            ))
        except Exception as e:
            checks.append(CertificationCheck(
                name="pipeline_stages", passed=False,
                message=f"Failed to read audit log: {e}",
            ))
    else:
        checks.append(CertificationCheck(
            name="pipeline_stages", passed=False,
            message="No Audit_Log.json found",
        ))

    bibval_report = output_dir / "Bibliometrix_Validation_Report.docx"
    checks.append(CertificationCheck(
        name="bibliometrix_validation_report",
        passed=bibval_report.exists(),
        message=str(bibval_report) if bibval_report.exists() else "Validation report not found",
    ))

    bib_txt = output_dir / "Bibliometrix_Compatible.txt"
    checks.append(CertificationCheck(
        name="certified_dataset_exists",
        passed=bib_txt.exists() and bib_txt.stat().st_size > 0,
        message=f"{bib_txt.stat().st_size} bytes" if bib_txt.exists() else "Dataset not found",
    ))

    bib_xlsx = output_dir / "Bibliometrix_Compatible.xlsx"
    bib_csv = output_dir / "Bibliometrix_Compatible.csv"
    checks.append(CertificationCheck(
        name="export_artifacts",
        passed=bib_xlsx.exists() and bib_csv.exists(),
        message="XLSX and CSV present" if (bib_xlsx.exists() and bib_csv.exists()) else "Missing export artifacts",
    ))

    return checks


def verify_r_environment(config: BiblioshinyConfig) -> REnvironmentInfo:
    """Verify R is installed, Rscript is available, and bibliometrix loads."""
    info = REnvironmentInfo()
    info.r_home = config.r_home
    info.rscript_path = config.rscript_path

    rscript = Path(config.rscript_path)
    if not rscript.exists():
        info.errors.append(f"Rscript not found at {config.rscript_path}")
        return info

    env = {**os.environ, "R_HOME": config.r_home}

    try:
        proc = subprocess.run(
            [str(rscript), "--version"],
            capture_output=True, text=True, timeout=15, env=env,
        )
        version_text = proc.stdout.strip() or proc.stderr.strip()
        info.r_version = version_text.split("\n")[0] if version_text else "unknown"
    except Exception as e:
        info.errors.append(f"Failed to get R version: {e}")
        return info

    tmp = Path(tempfile.mkdtemp(prefix="blm_envtest_"))
    try:
        script = tmp / "env_test.R"
        result_file = tmp / "result.json"
        res_esc = str(result_file).replace("\\", "/")

        script.write_text(f'''
suppressMessages({{
    library(bibliometrix, lib.loc=Sys.getenv("R_LIBS_USER"))
}})
result <- list()
result$bibliometrix_loaded <- "TRUE"
result$bibliometrix_version <- as.character(packageVersion("bibliometrix"))
tryCatch({{
    data(small-coll, package="bibliometrix")
    result$load_test <- "TRUE"
}}, error=function(e) {{
    result$load_test <- "FALSE"
    result$load_test_error <- conditionMessage(e)
}})
writeLines(jsonlite::toJSON(result, auto_unbox=TRUE, pretty=TRUE), "{res_esc}")
''', encoding="utf-8")

        proc = subprocess.run(
            [str(rscript), str(script)],
            capture_output=True, text=True, timeout=60, env=env,
        )

        if result_file.exists():
            data = json.loads(result_file.read_text(encoding="utf-8"))
            info.bibliometrix_installed = data.get("bibliometrix_loaded") == "TRUE"
            info.bibliometrix_version = data.get("bibliometrix_version", "")
            info.load_test_passed = data.get("load_test") == "TRUE"
            info.dependencies_available = info.bibliometrix_installed and info.load_test_passed
        else:
            info.errors.append(f"No result file. Exit code: {proc.returncode}")
            if proc.stderr:
                info.errors.append(proc.stderr[:300])
    except Exception as e:
        info.errors.append(f"Environment test failed: {e}")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    return info


def locate_certified_dataset(output_dir: Path, config: BiblioshinyConfig) -> DatasetInfo:
    """Locate the certified Bibliometrix_Compatible.txt and extract metadata."""
    import hashlib

    info = DatasetInfo()
    dataset_path = output_dir / config.certified_dataset_name
    info.path = str(dataset_path)
    info.exists = dataset_path.exists() and dataset_path.stat().st_size > 0

    if not info.exists:
        return info

    content = dataset_path.read_bytes()
    info.file_hash = hashlib.sha256(content).hexdigest()[:16]

    record_count = 0
    field_count = 0
    in_header = True
    for line in content.decode("utf-8", errors="replace").split("\n"):
        if in_header:
            if line.startswith("PT ") or line == "PT J":
                in_header = False
                record_count = 1
        elif line.startswith("PT ") or line == "PT J":
            record_count += 1

    record_count = max(record_count, 1)

    import pandas as pd
    try:
        csv_path = output_dir / "Bibliometrix_Compatible.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path, nrows=0)
            field_count = len(df.columns)
    except Exception:
        pass

    info.record_count = record_count
    info.field_count = field_count
    info.timestamp = datetime.now().isoformat()

    audit_path = output_dir / "Audit_Log.json"
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            info.pipeline_run_id = audit.get("run_id", "") if isinstance(audit, dict) else ""
        except Exception:
            pass

    info.certification_id = f"cert_{info.file_hash}"

    return info


from datetime import datetime


def run_full_prechecks(output_dir: Path, config: BiblioshinyConfig) -> LaunchPrechecks:
    """Run all pre-launch checks and return aggregated result."""
    prechecks = LaunchPrechecks()

    cert_checks = check_certification(output_dir)
    prechecks.certification_checks = cert_checks

    all_cert_passed = all(c.passed for c in cert_checks)
    prechecks.r_environment = verify_r_environment(config)
    prechecks.dataset = locate_certified_dataset(output_dir, config)

    r_ok = prechecks.r_environment.dependencies_available
    ds_ok = prechecks.dataset.exists

    prechecks.all_passed = all_cert_passed and r_ok and ds_ok

    if not all_cert_passed:
        failed = [c.name for c in cert_checks if not c.passed]
        prechecks.block_reason = f"Certification failed: {', '.join(failed)}"
        prechecks.certification_status = "NOT_CERTIFIED"
    elif not r_ok:
        prechecks.block_reason = "R environment not ready: " + "; ".join(prechecks.r_environment.errors)
        prechecks.certification_status = "R_NOT_READY"
    elif not ds_ok:
        prechecks.block_reason = "Certified dataset not found"
        prechecks.certification_status = "DATASET_NOT_FOUND"
    else:
        prechecks.certification_status = "READY_FOR_BIBLIOSHINY"

    return prechecks
