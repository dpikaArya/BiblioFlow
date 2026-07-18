"""Biblioshiny Launch Manager - Configuration."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ServerDetectionConfig:
    """Configuration for dual Shiny server detection."""
    mode: str = "dual"
    primary_detection: str = "console_output"
    fallback_detection: str = "process_port_discovery"
    probe_interval_ms: int = 500
    probe_timeout_seconds: int = 30
    console_detection_timeout_seconds: int = 10
    verify_http_response: bool = True
    verify_shiny_application: bool = True
    verify_process_owner: bool = True
    allow_process_port_scan: bool = True
    max_probe_attempts: int = 60
    shiny_identifiers: list[str] = field(default_factory=lambda: [
        "shiny", "Shiny", "biblioshiny", "bibliometrix",
        "session", "htmlwidget",
    ])

    def to_dict(self) -> dict:
        return {
            "server_detection_mode": self.mode,
            "primary_detection": self.primary_detection,
            "fallback_detection": self.fallback_detection,
            "probe_interval_ms": self.probe_interval_ms,
            "probe_timeout_seconds": self.probe_timeout_seconds,
            "console_detection_timeout_seconds": self.console_detection_timeout_seconds,
            "verify_http_response": self.verify_http_response,
            "verify_shiny_application": self.verify_shiny_application,
            "verify_process_owner": self.verify_process_owner,
            "allow_process_port_scan": self.allow_process_port_scan,
            "max_probe_attempts": self.max_probe_attempts,
        }


@dataclass
class BiblioshinyConfig:
    """Configuration for the Biblioshiny Launch Manager."""
    enabled: bool = True
    require_certification: bool = True
    certification_status: str = "READY_FOR_BIBLIOSHINY"
    use_external_r_process: bool = True
    auto_open_browser: bool = True
    allow_uncertified_launch: bool = False
    r_home: str = r"C:\Program Files\R\R-4.5.3"
    rscript_path: str = r"C:\Program Files\R\R-4.5.3\bin\Rscript.exe"
    certified_dataset_name: str = "Bibliometrix_Compatible.txt"
    launch_timeout_seconds: int = 30
    log_dir: str = ""
    report_dir: str = ""
    server_detection: ServerDetectionConfig = field(default_factory=ServerDetectionConfig)

    def __post_init__(self):
        if not self.rscript_path or not Path(self.rscript_path).exists():
            import shutil
            found = shutil.which("Rscript")
            if found:
                self.rscript_path = found
