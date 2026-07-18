"""Tests for Biblioshiny Launch Manager."""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from biblioshiny_launcher import (
    BiblioshinyLaunchManager,
    BiblioshinyConfig,
    LaunchPrechecks,
    LaunchResult,
    REnvironmentInfo,
    DatasetInfo,
    CertificationCheck,
)
from biblioshiny_launcher.validator import (
    check_certification,
    verify_r_environment,
    locate_certified_dataset,
    run_full_prechecks,
)
from biblioshiny_launcher.r_interface import build_launch_command, launch_biblioshiny
from biblioshiny_launcher.browser import wait_and_open_browser, open_validated_browser
from biblioshiny_launcher.models import LaunchPrechecks, ServerDetectionResult, ProbeResult
from biblioshiny_launcher.server_discovery import ShinyServerDiscovery
from biblioshiny_launcher.config import ServerDetectionConfig


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestBiblioshinyConfig:
    def test_default_config(self):
        cfg = BiblioshinyConfig()
        assert cfg.enabled is True
        assert cfg.require_certification is True
        assert cfg.certification_status == "READY_FOR_BIBLIOSHINY"
        assert cfg.use_external_r_process is True
        assert cfg.auto_open_browser is True
        assert cfg.allow_uncertified_launch is False
        assert "Rscript" in cfg.rscript_path or "Rscript" in cfg.rscript_path.lower() or cfg.rscript_path.endswith(".exe")
        assert cfg.certified_dataset_name == "Bibliometrix_Compatible.txt"

    def test_config_custom_values(self):
        cfg = BiblioshinyConfig(enabled=False, allow_uncertified_launch=True)
        assert cfg.enabled is False
        assert cfg.allow_uncertified_launch is True


# ---------------------------------------------------------------------------
# Models tests
# ---------------------------------------------------------------------------

class TestModels:
    def test_certification_check_to_dict(self):
        c = CertificationCheck(name="test", passed=True, message="ok")
        d = c.to_dict()
        assert d["name"] == "test"
        assert d["passed"] is True
        assert d["message"] == "ok"

    def test_dataset_info_to_dict(self):
        ds = DatasetInfo(path="/tmp/test.txt", exists=True, record_count=100)
        d = ds.to_dict()
        assert d["path"] == "/tmp/test.txt"
        assert d["exists"] is True
        assert d["record_count"] == 100

    def test_r_environment_info_to_dict(self):
        r = REnvironmentInfo(r_version="4.5.3", bibliometrix_installed=True)
        d = r.to_dict()
        assert d["r_version"] == "4.5.3"
        assert d["bibliometrix_installed"] is True

    def test_launch_prechecks_to_dict(self):
        p = LaunchPrechecks(certification_status="READY_FOR_BIBLIOSHINY", all_passed=True)
        d = p.to_dict()
        assert d["certification_status"] == "READY_FOR_BIBLIOSHINY"
        assert d["all_passed"] is True

    def test_launch_result_to_dict(self):
        r = LaunchResult(success=True, process_id=12345)
        d = r.to_dict()
        assert d["success"] is True
        assert d["process_id"] == 12345


# ---------------------------------------------------------------------------
# Certification check tests
# ---------------------------------------------------------------------------

class TestCertificationCheck:
    def test_check_with_valid_audit_log(self, tmp_path):
        audit = tmp_path / "Audit_Log.json"
        audit.write_text(json.dumps({
            "stages": {
                "import": {"status": "PASS", "duration": 0.5},
                "export": {"status": "PASS", "duration": 1.0},
            },
            "r_certification": {
                "convert2df": {"success": True},
                "biblioAnalysis": {"success": True},
                "summary": {"success": True},
            },
        }), encoding="utf-8")
        (tmp_path / "Bibliometrix_Validation_Report.docx").touch()
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("FN Clarivate Analytics Web of Science\nVR 1.0\nPT J\nTI Test\n")
        (tmp_path / "Bibliometrix_Compatible.xlsx").touch()
        (tmp_path / "Bibliometrix_Compatible.csv").touch()

        checks = check_certification(tmp_path)
        assert len(checks) == 5
        assert all(c.passed for c in checks)

    def test_check_missing_audit_log(self, tmp_path):
        checks = check_certification(tmp_path)
        names = [c.name for c in checks]
        assert "pipeline_stages" in names
        stage_check = next(c for c in checks if c.name == "pipeline_stages")
        assert stage_check.passed is False

    def test_check_missing_dataset(self, tmp_path):
        audit = tmp_path / "Audit_Log.json"
        audit.write_text(json.dumps([{"agent": "x", "stage": "complete"}]), encoding="utf-8")
        checks = check_certification(tmp_path)
        ds_check = next(c for c in checks if c.name == "certified_dataset_exists")
        assert ds_check.passed is False


# ---------------------------------------------------------------------------
# Dataset discovery tests
# ---------------------------------------------------------------------------

class TestDatasetDiscovery:
    def test_locate_existing_dataset(self, tmp_path):
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("FN Clarivate Analytics Web of Science\nVR 1.0\nPT J\nTI Test\n\nPT J\nTI Test2\n", encoding="utf-8")
        (tmp_path / "Bibliometrix_Compatible.csv").write_text("TI,SO\nTest,J\nTest2,J\n", encoding="utf-8")

        cfg = BiblioshinyConfig()
        ds = locate_certified_dataset(tmp_path, cfg)
        assert ds.exists is True
        assert ds.record_count == 2
        assert ds.field_count == 2
        assert len(ds.file_hash) == 16

    def test_locate_missing_dataset(self, tmp_path):
        cfg = BiblioshinyConfig()
        ds = locate_certified_dataset(tmp_path, cfg)
        assert ds.exists is False
        assert ds.record_count == 0

    def test_locate_empty_dataset(self, tmp_path):
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("", encoding="utf-8")

        cfg = BiblioshinyConfig()
        ds = locate_certified_dataset(tmp_path, cfg)
        assert ds.exists is False


# ---------------------------------------------------------------------------
# R environment tests
# ---------------------------------------------------------------------------

class TestREnvironment:
    def test_verify_r_env_with_real_r(self):
        cfg = BiblioshinyConfig()
        if not Path(cfg.rscript_path).exists():
            pytest.skip("R not installed")

        env = verify_r_environment(cfg)
        assert env.r_version != ""
        assert env.bibliometrix_installed is True
        assert env.load_test_passed is True
        assert env.dependencies_available is True

    def test_verify_r_env_missing_rscript(self):
        cfg = BiblioshinyConfig(rscript_path="/nonexistent/Rscript")
        env = verify_r_environment(cfg)
        assert env.dependencies_available is False
        assert len(env.errors) > 0


# ---------------------------------------------------------------------------
# R interface tests
# ---------------------------------------------------------------------------

class TestRInterface:
    def test_build_launch_command(self):
        cfg = BiblioshinyConfig()
        cmd = build_launch_command(Path("/data/Bibliometrix_Compatible.txt"), cfg)
        assert cmd[0] == cfg.rscript_path
        assert cmd[1] == "-e"
        assert "biblioshiny()" in cmd[2]
        assert "library(bibliometrix" in cmd[2]

    def test_build_launch_command_with_spaces(self):
        cfg = BiblioshinyConfig()
        cmd = build_launch_command(Path("C:/Users/Dr.Manisha ji/data/file.txt"), cfg)
        assert "biblioshiny()" in cmd[2]
        assert cmd[0] == cfg.rscript_path
        assert cmd[1] == "-e"

    def test_launch_missing_rscript(self):
        cfg = BiblioshinyConfig(rscript_path="/nonexistent/Rscript")
        result, proc = launch_biblioshiny(Path("/tmp/test.txt"), cfg)
        assert result.success is False
        assert proc is None
        assert "not found" in result.error_message.lower() or "Failed" in result.error_message

    def test_launch_missing_dataset(self):
        cfg = BiblioshinyConfig()
        result, proc = launch_biblioshiny(Path("/nonexistent/file.txt"), cfg)
        assert result.success is False
        assert proc is None
        assert "not found" in result.error_message.lower() or "not found" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Browser tests
# ---------------------------------------------------------------------------

class TestBrowser:
    @patch("biblioshiny_launcher.browser.webbrowser.open")
    def test_wait_and_open_browser(self, mock_open):
        result = wait_and_open_browser(delay=0.01)
        assert result is True
        mock_open.assert_called_once()

    @patch("biblioshiny_launcher.browser.webbrowser.open", side_effect=Exception("no browser"))
    def test_wait_and_open_browser_failure(self, mock_open):
        result = wait_and_open_browser(delay=0.01)
        assert result is False


# ---------------------------------------------------------------------------
# Full prechecks integration
# ---------------------------------------------------------------------------

class TestFullPrechecks:
    def test_run_prechecks_ready(self, tmp_path):
        audit = tmp_path / "Audit_Log.json"
        audit.write_text(json.dumps({
            "stages": {
                "import": {"status": "PASS", "duration": 0.5},
                "export": {"status": "PASS", "duration": 1.0},
            },
            "r_certification": {
                "convert2df": {"success": True},
                "biblioAnalysis": {"success": True},
                "summary": {"success": True},
            },
        }), encoding="utf-8")
        (tmp_path / "Bibliometrix_Validation_Report.docx").touch()
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("FN Clarivate Analytics Web of Science\nVR 1.0\nPT J\nTI Test\n", encoding="utf-8")
        (tmp_path / "Bibliometrix_Compatible.xlsx").touch()
        (tmp_path / "Bibliometrix_Compatible.csv").write_text("TI\nTest\n", encoding="utf-8")

        cfg = BiblioshinyConfig()
        prechecks = run_full_prechecks(tmp_path, cfg)

        assert prechecks.certification_status == "READY_FOR_BIBLIOSHINY"
        assert prechecks.all_passed is True
        assert prechecks.dataset is not None
        assert prechecks.dataset.exists is True
        assert prechecks.r_environment is not None

    def test_run_prechecks_not_certified(self, tmp_path):
        cfg = BiblioshinyConfig()
        prechecks = run_full_prechecks(tmp_path, cfg)
        assert prechecks.all_passed is False
        assert prechecks.certification_status != "READY_FOR_BIBLIOSHINY"
        assert prechecks.block_reason != ""


# ---------------------------------------------------------------------------
# Launcher manager tests
# ---------------------------------------------------------------------------

class TestBiblioshinyLaunchManager:
    def test_manager_init(self):
        mgr = BiblioshinyLaunchManager()
        assert mgr.config is not None
        assert mgr.config.enabled is True

    def test_manager_check_certification(self, tmp_path):
        audit = tmp_path / "Audit_Log.json"
        audit.write_text(json.dumps({
            "stages": {"import": {"status": "PASS"}, "export": {"status": "PASS"}},
            "r_certification": {"convert2df": {"success": True}, "biblioAnalysis": {"success": True}, "summary": {"success": True}},
        }), encoding="utf-8")
        (tmp_path / "Bibliometrix_Validation_Report.docx").touch()
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("FN Clarivate Analytics Web of Science\nVR 1.0\n", encoding="utf-8")
        (tmp_path / "Bibliometrix_Compatible.xlsx").touch()
        (tmp_path / "Bibliometrix_Compatible.csv").touch()

        mgr = BiblioshinyLaunchManager()
        checks = mgr.check_certification(tmp_path)
        assert len(checks) == 5
        assert all(c.passed for c in checks)

    def test_generate_block_report(self, tmp_path):
        prechecks = LaunchPrechecks(
            certification_status="NOT_CERTIFIED",
            block_reason="Certification failed: pipeline_stages",
        )
        mgr = BiblioshinyLaunchManager()
        path = mgr.generate_block_report(prechecks, tmp_path / "block.docx")
        assert path.exists()
        assert path.stat().st_size > 0

    def test_generate_launch_report(self, tmp_path):
        prechecks = LaunchPrechecks(
            certification_status="READY_FOR_BIBLIOSHINY",
            dataset=DatasetInfo(path="/tmp/test.txt", exists=True, record_count=100, field_count=20),
            r_environment=REnvironmentInfo(r_version="4.5.3", bibliometrix_version="4.2.0", load_test_passed=True),
            all_passed=True,
        )
        mgr = BiblioshinyLaunchManager()
        path = mgr.generate_launch_report(prechecks, None, tmp_path / "report.docx")
        assert path.exists()
        assert path.stat().st_size > 0

    def test_generate_launch_log(self, tmp_path):
        prechecks = LaunchPrechecks(
            certification_status="READY_FOR_BIBLIOSHINY",
            dataset=DatasetInfo(path="/tmp/test.txt", file_hash="abc123"),
            all_passed=True,
        )
        result = LaunchResult(success=True, process_id=99999)
        mgr = BiblioshinyLaunchManager()
        path = mgr.generate_launch_log(prechecks, result, tmp_path / "log.json")
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["success"] is True
        assert data["process_id"] == 99999
        assert data["dataset_hash"] == "abc123"

    def test_run_blocked_no_certification(self, tmp_path):
        cfg = BiblioshinyConfig()
        mgr = BiblioshinyLaunchManager(cfg)
        result = mgr.run(output_dir=tmp_path, launch=True)
        assert result["prechecks"]["all_passed"] is False
        block_reports = [f for f in result["files_generated"] if "Block" in f]
        assert len(block_reports) == 1

    def test_run_allow_uncertified(self, tmp_path):
        bib_txt = tmp_path / "Bibliometrix_Compatible.txt"
        bib_txt.write_text("FN Clarivate Analytics Web of Science\nVR 1.0\nPT J\nTI Test\n", encoding="utf-8")
        (tmp_path / "Bibliometrix_Compatible.csv").write_text("TI\nTest\n", encoding="utf-8")

        cfg = BiblioshinyConfig(allow_uncertified_launch=True)
        mgr = BiblioshinyLaunchManager(cfg)
        result = mgr.run(output_dir=tmp_path, launch=False)
        report_files = [f for f in result["files_generated"] if "Report" in f]
        assert len(report_files) >= 1


# ---------------------------------------------------------------------------
# Backward compatibility tests
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_existing_agents_unchanged(self):
        from agents import (
            DatasetImportAgent, DatasetMergeAgent, DuplicateDetectionAgent,
            MetadataValidationAgent, CleaningHarmonizationAgent,
            DatabaseMappingValidationAgent,
            BibliometrixCompatAgent, BibliometrixValidationAgent,
            PRISMAAgent, SynchronizationAgent, QualityValidationAgent,
            ExportAgent,
        )
        agents = [
            DatasetImportAgent, DatasetMergeAgent, DuplicateDetectionAgent,
            MetadataValidationAgent, CleaningHarmonizationAgent,
            DatabaseMappingValidationAgent,
            BibliometrixCompatAgent, BibliometrixValidationAgent,
            PRISMAAgent, SynchronizationAgent, QualityValidationAgent,
            ExportAgent,
        ]
        for agent_cls in agents:
            assert hasattr(agent_cls, "execute")
            assert hasattr(agent_cls, "NAME")

    def test_main_pipeline_still_works(self):
        from main import run_pipeline, launch_biblioshiny_only
        assert callable(run_pipeline)
        assert callable(launch_biblioshiny_only)

    def test_core_config_unchanged(self):
        from core.config import CONFIG, FrameworkConfig, BIBLIOMETRIX_COLUMNS
        assert CONFIG is not None
        assert len(BIBLIOMETRIX_COLUMNS) > 0

    def test_biblioshiny_config_independent(self):
        from core.config import BiblioshinyLaunchConfig
        cfg = BiblioshinyLaunchConfig()
        assert cfg.enabled is True
        assert cfg.require_certification is True
        assert cfg.allow_uncertified_launch is False
