"""Biblioshiny Launch Manager - R interface."""
from __future__ import annotations
import subprocess
import os
from pathlib import Path
from typing import Optional

from .config import BiblioshinyConfig
from .models import REnvironmentInfo, LaunchResult


def build_launch_command(
    dataset_path: Path,
    config: BiblioshinyConfig,
) -> list[str]:
    """Build the Rscript command to launch Biblioshiny.

    Returns the command list suitable for subprocess.run/exec.
    """
    bib_esc = str(dataset_path).replace("\\", "/")

    r_code = (
        f'library(bibliometrix, lib.loc=Sys.getenv("R_LIBS_USER")); '
        f'biblioshiny()'
    )

    return [config.rscript_path, "-e", r_code]


def launch_biblioshiny(
    dataset_path: Path,
    config: BiblioshinyConfig,
    env: Optional[dict] = None,
) -> tuple[LaunchResult, Optional[subprocess.Popen]]:
    """Launch Biblioshiny in a new external R process.

    Uses subprocess.Popen so the R process runs independently.
    Returns (LaunchResult, process_handle) tuple.
    The process handle is needed by ShinyServerDiscovery for console
    monitoring and port scanning.
    """
    result = LaunchResult()
    result.dataset_path = str(dataset_path)
    result.launch_time = __import__("datetime").datetime.now().isoformat()

    if not Path(config.rscript_path).exists():
        result.error_message = f"Rscript not found: {config.rscript_path}"
        return result, None

    if not dataset_path.exists():
        result.error_message = f"Dataset not found: {dataset_path}"
        return result, None

    run_env = {**(env or os.environ), "R_HOME": config.r_home}

    cmd = build_launch_command(dataset_path, config)

    try:
        proc = subprocess.Popen(
            cmd,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        result.process_id = proc.pid
        result.success = True
        return result, proc
    except FileNotFoundError as e:
        result.error_message = f"Failed to start R: {e}"
        return result, None
    except Exception as e:
        result.error_message = f"Launch error: {e}"
        return result, None


def launch_biblioshiny_legacy(
    dataset_path: Path,
    config: BiblioshinyConfig,
    env: Optional[dict] = None,
) -> LaunchResult:
    """Legacy interface: launch without returning the process handle."""
    result, _proc = launch_biblioshiny(dataset_path, config, env)
    result.browser_status = "launched" if result.success else result.browser_status
    return result
