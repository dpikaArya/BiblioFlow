"""Biblioshiny Launch Manager - Data models."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class REnvironmentInfo:
    """Captured R environment state."""
    r_home: str = ""
    rscript_path: str = ""
    r_version: str = ""
    bibliometrix_installed: bool = False
    bibliometrix_version: str = ""
    dependencies_available: bool = False
    load_test_passed: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DatasetInfo:
    """Certified dataset metadata."""
    path: str = ""
    exists: bool = False
    record_count: int = 0
    field_count: int = 0
    file_hash: str = ""
    certification_id: str = ""
    pipeline_run_id: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CertificationCheck:
    """Single certification check result."""
    name: str
    passed: bool
    message: str = ""
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LaunchPrechecks:
    """Complete pre-launch validation results."""
    certification_status: str = "NOT_CERTIFIED"
    certification_checks: list[CertificationCheck] = field(default_factory=list)
    r_environment: Optional[REnvironmentInfo] = None
    dataset: Optional[DatasetInfo] = None
    all_passed: bool = False
    block_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "certification_status": self.certification_status,
            "certification_checks": [c.to_dict() for c in self.certification_checks],
            "r_environment": self.r_environment.to_dict() if self.r_environment else None,
            "dataset": self.dataset.to_dict() if self.dataset else None,
            "all_passed": self.all_passed,
            "block_reason": self.block_reason,
        }


@dataclass
class ProbeResult:
    """Result of probing a single TCP port."""
    host: str = "127.0.0.1"
    port: int = 0
    is_open: bool = False
    http_status: int = 0
    is_shiny: bool = False
    is_biblioshiny: bool = False
    response_latency_ms: float = 0.0
    process_pid: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ServerDetectionResult:
    """Result of the dual Shiny server detection process."""
    detected: bool = False
    url: str = ""
    host: str = ""
    port: int = 0
    protocol: str = "http"
    detection_method: str = "none"
    console_detection_succeeded: bool = False
    fallback_detection_succeeded: bool = False
    detection_time_seconds: float = 0.0
    probe_attempts: int = 0
    http_status: int = 0
    shiny_application_detected: bool = False
    biblioshiny_identified: bool = False
    server_reachable: bool = False
    response_latency_ms: float = 0.0
    browser_launch_status: str = "not_attempted"
    manual_url: str = ""
    error_message: str = ""
    probe_results: list[ProbeResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["probe_results"] = [p.to_dict() for p in self.probe_results]
        return d


@dataclass
class LaunchResult:
    """Result of a Biblioshiny launch attempt."""
    success: bool = False
    process_id: Optional[int] = None
    launch_time: str = ""
    dataset_path: str = ""
    dataset_hash: str = ""
    r_version: str = ""
    bibliometrix_version: str = ""
    browser_status: str = "pending"
    error_message: str = ""
    server_detection: Optional[ServerDetectionResult] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["server_detection"] = self.server_detection.to_dict() if self.server_detection else None
        return d
