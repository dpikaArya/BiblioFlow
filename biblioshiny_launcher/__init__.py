"""Biblioshiny Launch Manager (BLM).

Lightweight post-certification usability layer that bridges AIBEF
certified output to interactive Biblioshiny analysis.

Usage:
    from biblioshiny_launcher import BiblioshinyLaunchManager, BiblioshinyConfig

    config = BiblioshinyConfig()
    manager = BiblioshinyLaunchManager(config)
    result = manager.run(output_dir=Path("outputs/certification_run"))
"""
from .launcher import BiblioshinyLaunchManager
from .config import BiblioshinyConfig, ServerDetectionConfig
from .models import (
    LaunchPrechecks,
    LaunchResult,
    REnvironmentInfo,
    DatasetInfo,
    CertificationCheck,
    ServerDetectionResult,
    ProbeResult,
)
from .server_discovery import ShinyServerDiscovery

__all__ = [
    "BiblioshinyLaunchManager",
    "BiblioshinyConfig",
    "ServerDetectionConfig",
    "LaunchPrechecks",
    "LaunchResult",
    "REnvironmentInfo",
    "DatasetInfo",
    "CertificationCheck",
    "ServerDetectionResult",
    "ProbeResult",
    "ShinyServerDiscovery",
]
