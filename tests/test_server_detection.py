"""Tests for Dual Shiny Server Detection Strategy."""
from __future__ import annotations
import io
import json
import socket
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from biblioshiny_launcher.server_discovery import ShinyServerDiscovery, _LISTENING_PATTERNS
from biblioshiny_launcher.config import ServerDetectionConfig, BiblioshinyConfig
from biblioshiny_launcher.models import ServerDetectionResult, ProbeResult
from biblioshiny_launcher.browser import (
    wait_and_open_browser, open_browser, open_validated_browser,
    check_biblioshiny_running, BIBLIOSHINY_DEFAULT_URL,
)


# ---------------------------------------------------------------------------
# Console detection (primary)
# ---------------------------------------------------------------------------

class TestConsoleDetection:
    def test_parse_listening_on_standard(self):
        text = "Listening on http://127.0.0.1:7654"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["protocol"] == "http"
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 7654
        assert result["url"] == "http://127.0.0.1:7654"

    def test_parse_listening_on_localhost(self):
        text = "Listening on http://localhost:8888"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["host"] == "localhost"
        assert result["port"] == 8888

    def test_parse_listening_on_https(self):
        text = "Listening on https://127.0.0.1:4443"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["protocol"] == "https"
        assert result["port"] == 4443

    def test_parse_listening_on_bare_url(self):
        text = "http://127.0.0.1:12737"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["port"] == 12737

    def test_parse_listening_on_0_0_0_0(self):
        text = "Listening on http://0.0.0.0:3838"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["host"] == "127.0.0.1"

    def test_parse_listening_no_match(self):
        text = "Loading required package: shiny"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is None

    def test_parse_listening_in_long_output(self):
        text = (
            "R version 4.5.3 (2025-12-08)\n"
            "Loading required package: bibliometrix\n"
            "\n"
            "Listening on http://127.0.0.1:12737\n"
        )
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["port"] == 12737

    def test_primary_detection_from_stdout(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None

        output = b"Loading package...\nListening on http://127.0.0.1:7654\n"
        proc.stdout = io.BytesIO(output)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>shiny</html>"

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=False,
        ))

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            result = discovery.discover(process=proc, timeout_seconds=2)

        assert result.detected is True
        assert result.port == 7654
        assert result.url == "http://127.0.0.1:7654"
        assert result.detection_method == "console_detection"
        assert result.console_detection_succeeded is True

    def test_primary_detection_empty_stdout(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=False,
        ))
        result = discovery.discover(process=proc, timeout_seconds=0.5)

        assert result.detected is False
        assert result.detection_method == "none"


# ---------------------------------------------------------------------------
# Console detection failure
# ---------------------------------------------------------------------------

class TestConsoleDetectionFailure:
    def test_no_process(self):
        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=False,
        ))
        result = discovery.discover(process=None, timeout_seconds=1)
        assert result.detected is False

    def test_process_exits_before_output(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = 1
        proc.stdout = io.BytesIO(b"Error: package not found\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=False,
        ))
        result = discovery.discover(process=proc, timeout_seconds=1)
        assert result.detected is False

    def test_no_stdout_pipe(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = None

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=False,
        ))
        result = discovery.discover(process=proc, timeout_seconds=0.5)
        assert result.detected is False


# ---------------------------------------------------------------------------
# Fallback detection (port scan)
# ---------------------------------------------------------------------------

class TestFallbackDetection:
    def test_fallback_activates_when_console_fails(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 99999
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=True,
        ))

        with patch.object(
            ShinyServerDiscovery, "_get_process_tcp_ports", return_value=[12345]
        ), patch.object(
            ShinyServerDiscovery, "_is_port_in_use", return_value=True
        ), patch.object(
            discovery, "_probe_port"
        ) as mock_probe:
            probe = ProbeResult(
                host="127.0.0.1", port=12345, is_open=True,
                http_status=200, is_shiny=True, is_biblioshiny=True,
                response_latency_ms=15.0, process_pid=99999,
            )
            mock_probe.return_value = probe

            result = discovery.discover(process=proc, timeout_seconds=0.5)

            assert result.detected is True
            assert result.detection_method == "port_discovery"
            assert result.fallback_detection_succeeded is True

    def test_fallback_disabled(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 99999
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=False,
        ))
        result = discovery.discover(process=proc, timeout_seconds=0.5)
        assert result.detected is False

    def test_fallback_no_ports_found(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 99999
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=True,
        ))

        with patch.object(
            ShinyServerDiscovery, "_get_process_tcp_ports", return_value=[]
        ):
            result = discovery.discover(process=proc, timeout_seconds=0.5)
            assert result.detected is False

    def test_fallback_all_ports_closed(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 99999
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=True,
        ))

        with patch.object(
            ShinyServerDiscovery, "_get_process_tcp_ports", return_value=[3000, 4000]
        ), patch.object(
            ShinyServerDiscovery, "_is_port_in_use", return_value=False
        ):
            result = discovery.discover(process=proc, timeout_seconds=0.5)
            assert result.detected is False
            assert result.probe_attempts == 2


# ---------------------------------------------------------------------------
# HTTP probing
# ---------------------------------------------------------------------------

class TestHttpProbing:
    def test_probe_port_shiny_response(self):
        discovery = ShinyServerDiscovery()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            b"<html><head><script src='shiny.js'></script></head>"
            b"<body><div class='shiny'>App</div></body></html>"
        )
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            probe = discovery._probe_port("127.0.0.1", 7654, expected_pid=12345)

            assert probe.is_open is True
            assert probe.http_status == 200
            assert probe.is_shiny is True
            assert probe.process_pid == 12345

    def test_probe_port_non_shiny_response(self):
        discovery = ShinyServerDiscovery()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html><body>Hello World</body></html>"
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            probe = discovery._probe_port("127.0.0.1", 8080)

            assert probe.is_open is True
            assert probe.is_shiny is False

    def test_probe_port_biblioshiny_response(self):
        discovery = ShinyServerDiscovery()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            b"<html><body><script>Biblioshiny App</script></body></html>"
        )
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            probe = discovery._probe_port("127.0.0.1", 12737)

            assert probe.is_shiny is True
            assert probe.is_biblioshiny is True

    def test_probe_port_connection_refused(self):
        discovery = ShinyServerDiscovery()

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen",
                    side_effect=ConnectionRefusedError):
            probe = discovery._probe_port("127.0.0.1", 9999)

            assert probe.is_open is True
            assert probe.http_status == 0
            assert probe.is_shiny is False


# ---------------------------------------------------------------------------
# Shiny verification
# ---------------------------------------------------------------------------

class TestShinyVerification:
    def test_is_shiny_with_script_marker(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_shiny_response("<script src='shiny.js'>") is True

    def test_is_shiny_with_biblioshiny_marker(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_shiny_response("Biblioshiny App") is True

    def test_is_shiny_with_bibliometrix_marker(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_shiny_response("bibliometrix loaded") is True

    def test_is_shiny_with_session_marker(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_shiny_response("session connected") is True

    def test_is_not_shiny(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_shiny_response("Hello World") is False

    def test_verify_disabled(self):
        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            verify_shiny_application=False,
        ))
        assert discovery._is_shiny_response("anything") is True

    def test_is_biblioshiny(self):
        discovery = ShinyServerDiscovery()
        assert discovery._is_biblioshiny_response("biblioshiny running") is True
        assert discovery._is_biblioshiny_response("bibliometrix loaded") is True
        assert discovery._is_biblioshiny_response("shiny app") is False


# ---------------------------------------------------------------------------
# Browser launch
# ---------------------------------------------------------------------------

class TestBrowserLaunch:
    @patch("biblioshiny_launcher.browser.webbrowser.open", return_value=True)
    def test_open_browser_success(self, mock_open):
        assert open_browser("http://127.0.0.1:12737") is True
        mock_open.assert_called_once_with("http://127.0.0.1:12737")

    @patch("biblioshiny_launcher.browser.webbrowser.open", side_effect=Exception("no browser"))
    def test_open_browser_failure(self, mock_open):
        assert open_browser("http://127.0.0.1:12737") is False

    @patch("biblioshiny_launcher.browser.webbrowser.open", return_value=True)
    def test_wait_and_open_browser(self, mock_open):
        result = wait_and_open_browser(delay=0.01)
        assert result is True

    @patch("biblioshiny_launcher.browser.webbrowser.open", side_effect=Exception("fail"))
    def test_wait_and_open_browser_failure(self, mock_open):
        result = wait_and_open_browser(delay=0.01)
        assert result is False

    def test_open_validated_browser_detected(self):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            server_reachable=True,
        )
        with patch("biblioshiny_launcher.browser.open_browser", return_value=True):
            result = open_validated_browser(det, auto_open=True)
            assert result.browser_status == "launched"
            assert result.manual_url == "http://127.0.0.1:12737"

    def test_open_validated_browser_not_detected(self):
        det = ServerDetectionResult(detected=False)
        result = open_validated_browser(det, auto_open=True)
        assert result.browser_status == "not_detected"

    def test_open_validated_browser_not_reachable(self):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            server_reachable=False,
        )
        result = open_validated_browser(det, auto_open=True)
        assert result.browser_status == "server_unreachable"

    def test_open_validated_browser_manual_only(self):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            server_reachable=True,
        )
        result = open_validated_browser(det, auto_open=False)
        assert result.browser_status == "manual_url_ready"
        assert result.manual_url == "http://127.0.0.1:12737"

    def test_open_validated_browser_fallback_manual(self):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            server_reachable=True,
        )
        with patch("biblioshiny_launcher.browser.open_browser", return_value=False):
            result = open_validated_browser(det, auto_open=True)
            assert result.browser_status == "manual_url_displayed"
            assert result.manual_url == "http://127.0.0.1:12737"

    @patch("biblioshiny_launcher.browser.webbrowser.open")
    def test_open_validated_browser_success(self, mock_open):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            server_reachable=True,
        )
        result = open_validated_browser(det, auto_open=True)
        assert result.browser_status == "launched"
        mock_open.assert_called_once()


# ---------------------------------------------------------------------------
# Manual URL input
# ---------------------------------------------------------------------------

class TestManualUrlInput:
    def test_discover_from_valid_url(self):
        det_result = ServerDetectionResult()
        discovery = ShinyServerDiscovery()

        with patch.object(discovery, "_validate_server") as mock_val:
            mock_val.side_effect = lambda: setattr(discovery._result, "server_reachable", True)
            result = discovery.discover_from_url("http://127.0.0.1:12737")

        assert result.detected is False
        assert result.url == "http://127.0.0.1:12737"
        assert result.port == 12737
        assert result.host == "127.0.0.1"
        assert result.detection_method == "manual_url"

    def test_discover_from_invalid_url(self):
        discovery = ShinyServerDiscovery()
        result = discovery.discover_from_url("not-a-url")
        assert result.detected is False
        assert "Invalid URL" in result.error_message

    def test_discover_from_url_with_path(self):
        discovery = ShinyServerDiscovery()
        with patch.object(discovery, "_validate_server"):
            result = discovery.discover_from_url("http://localhost:3838/app")
        assert result.port == 3838
        assert result.host == "localhost"


# ---------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------

class TestUrlParsing:
    def test_parse_url_standard(self):
        result = ShinyServerDiscovery._parse_url("http://127.0.0.1:12737")
        assert result is not None
        assert result["protocol"] == "http"
        assert result["host"] == "127.0.0.1"
        assert result["port"] == 12737

    def test_parse_url_https(self):
        result = ShinyServerDiscovery._parse_url("https://localhost:4443")
        assert result is not None
        assert result["protocol"] == "https"

    def test_parse_url_with_path(self):
        result = ShinyServerDiscovery._parse_url("http://127.0.0.1:3838/app")
        assert result is not None
        assert result["port"] == 3838

    def test_parse_url_invalid_port(self):
        result = ShinyServerDiscovery._parse_url("http://127.0.0.1:99999")
        assert result is None

    def test_parse_url_no_port(self):
        result = ShinyServerDiscovery._parse_url("http://127.0.0.1")
        assert result is None

    def test_parse_url_garbage(self):
        result = ShinyServerDiscovery._parse_url("not-a-url")
        assert result is None


# ---------------------------------------------------------------------------
# Port scanning (process-specific)
# ---------------------------------------------------------------------------

class TestPortScanning:
    def test_get_ports_psutil(self):
        mock_proc = MagicMock()
        mock_conn = MagicMock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr = MagicMock(ip="127.0.0.1", port=7654)
        mock_proc.connections.return_value = [mock_conn]

        mock_psutil = MagicMock()
        mock_psutil.Process.return_value = mock_proc
        mock_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
        mock_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            ports = ShinyServerDiscovery._get_process_tcp_ports(12345)
            assert 7654 in ports

    def test_get_ports_empty_when_no_psutil(self):
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("No module named 'psutil'")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            with patch("subprocess.check_output", side_effect=FileNotFoundError):
                ports = ShinyServerDiscovery._get_process_tcp_ports(99999)
                assert ports == []

    def test_is_port_in_use_open(self):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.socket", return_value=mock_sock):
            assert ShinyServerDiscovery._is_port_in_use("127.0.0.1", 12737) is True

    def test_is_port_in_use_closed(self):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 1
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with patch("socket.socket", return_value=mock_sock):
            assert ShinyServerDiscovery._is_port_in_use("127.0.0.1", 9999) is False


# ---------------------------------------------------------------------------
# Server validation
# ---------------------------------------------------------------------------

class TestServerValidation:
    def test_validate_server_reachable(self):
        discovery = ShinyServerDiscovery()
        discovery._result = ServerDetectionResult(
            url="http://127.0.0.1:12737",
        )

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>shiny app</html>"

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            discovery._validate_server()

            assert discovery._result.detected is True
            assert discovery._result.server_reachable is True
            assert discovery._result.shiny_application_detected is True
            assert discovery._result.http_status == 200

    def test_validate_server_unreachable(self):
        discovery = ShinyServerDiscovery()
        discovery._result = ServerDetectionResult(
            url="http://127.0.0.1:9999",
        )

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen",
                    side_effect=ConnectionRefusedError):
            discovery._validate_server()

            assert discovery._result.detected is False
            assert discovery._result.server_reachable is False

    def test_validate_no_url(self):
        discovery = ShinyServerDiscovery()
        discovery._result = ServerDetectionResult()
        discovery._validate_server()
        assert discovery._result.detected is False


# ---------------------------------------------------------------------------
# Full discovery workflow (integration)
# ---------------------------------------------------------------------------

class TestFullDiscoveryWorkflow:
    def test_dual_strategy_primary_succeeds(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Listening on http://127.0.0.1:7654\n")
        proc.stderr = io.BytesIO(b"")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>shiny biblioshiny</html>"

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            allow_process_port_scan=True,
        ))

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            result = discovery.discover(process=proc, timeout_seconds=2)

        assert result.detected is True
        assert result.detection_method == "console_detection"
        assert result.console_detection_succeeded is True
        assert result.fallback_detection_succeeded is False
        assert result.biblioshiny_identified is True

    def test_dual_strategy_fallback_succeeds(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>biblioshiny</html>"

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=True,
        ))

        with patch.object(
            ShinyServerDiscovery, "_get_process_tcp_ports", return_value=[12345]
        ), patch.object(
            ShinyServerDiscovery, "_is_port_in_use", return_value=True
        ), patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            result = discovery.discover(process=proc, timeout_seconds=0.5)

        assert result.detected is True
        assert result.detection_method == "port_discovery"
        assert result.fallback_detection_succeeded is True

    def test_dual_strategy_both_fail(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Loading...\n")
        proc.stderr = io.BytesIO(b"")

        discovery = ShinyServerDiscovery(ServerDetectionConfig(
            console_detection_timeout_seconds=0.5,
            allow_process_port_scan=True,
        ))

        with patch.object(
            ShinyServerDiscovery, "_get_process_tcp_ports", return_value=[12345]
        ), patch.object(
            ShinyServerDiscovery, "_is_port_in_use", return_value=True
        ), patch.object(
            discovery, "_probe_port"
        ) as mock_probe:
            probe = ProbeResult(
                host="127.0.0.1", port=12345, is_open=True,
                http_status=200, is_shiny=False, is_biblioshiny=False,
            )
            mock_probe.return_value = probe

            result = discovery.discover(process=proc, timeout_seconds=0.5)

        assert result.detected is False
        assert result.error_message != ""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestServerDetectionConfig:
    def test_default_config(self):
        cfg = ServerDetectionConfig()
        assert cfg.mode == "dual"
        assert cfg.primary_detection == "console_output"
        assert cfg.fallback_detection == "process_port_discovery"
        assert cfg.probe_interval_ms == 500
        assert cfg.probe_timeout_seconds == 30
        assert cfg.console_detection_timeout_seconds == 10
        assert cfg.verify_http_response is True
        assert cfg.verify_shiny_application is True
        assert cfg.verify_process_owner is True
        assert cfg.allow_process_port_scan is True
        assert cfg.max_probe_attempts == 60

    def test_config_to_dict(self):
        cfg = ServerDetectionConfig()
        d = cfg.to_dict()
        assert d["server_detection_mode"] == "dual"
        assert d["primary_detection"] == "console_output"
        assert d["probe_interval_ms"] == 500

    def test_biblioshiny_config_includes_detection(self):
        cfg = BiblioshinyConfig()
        assert hasattr(cfg, "server_detection")
        assert isinstance(cfg.server_detection, ServerDetectionConfig)
        assert cfg.server_detection.mode == "dual"


# ---------------------------------------------------------------------------
# Model serialization
# ---------------------------------------------------------------------------

class TestModels:
    def test_probe_result_to_dict(self):
        p = ProbeResult(
            host="127.0.0.1", port=7654, is_open=True,
            http_status=200, is_shiny=True, is_biblioshiny=True,
            response_latency_ms=12.5, process_pid=12345,
        )
        d = p.to_dict()
        assert d["host"] == "127.0.0.1"
        assert d["port"] == 7654
        assert d["is_shiny"] is True
        assert d["process_pid"] == 12345

    def test_server_detection_result_to_dict(self):
        det = ServerDetectionResult(
            detected=True, url="http://127.0.0.1:12737",
            host="127.0.0.1", port=12737, protocol="http",
            detection_method="console_detection",
            http_status=200, server_reachable=True,
        )
        d = det.to_dict()
        assert d["detected"] is True
        assert d["url"] == "http://127.0.0.1:12737"
        assert d["probe_results"] == []

    def test_server_detection_result_with_probes(self):
        p1 = ProbeResult(host="127.0.0.1", port=3000, is_open=True)
        p2 = ProbeResult(host="127.0.0.1", port=7654, is_open=True, is_shiny=True)
        det = ServerDetectionResult(probe_results=[p1, p2])
        d = det.to_dict()
        assert len(d["probe_results"]) == 2
        assert d["probe_results"][0]["port"] == 3000
        assert d["probe_results"][1]["is_shiny"] is True

    def test_launch_result_includes_detection(self):
        det = ServerDetectionResult(detected=True, url="http://127.0.0.1:12737")
        from biblioshiny_launcher.models import LaunchResult
        lr = LaunchResult(
            success=True, process_id=12345,
            server_detection=det,
        )
        d = lr.to_dict()
        assert d["server_detection"]["detected"] is True
        assert d["server_detection"]["url"] == "http://127.0.0.1:12737"


# ---------------------------------------------------------------------------
# Detection timing
# ---------------------------------------------------------------------------

class TestDetectionTiming:
    def test_detection_time_recorded(self):
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = 12345
        proc.poll.return_value = None
        proc.stdout = io.BytesIO(b"Listening on http://127.0.0.1:7654\n")
        proc.stderr = io.BytesIO(b"")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>shiny</html>"

        discovery = ShinyServerDiscovery()

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            result = discovery.discover(process=proc, timeout_seconds=2)

        assert result.detection_time_seconds >= 0


# ---------------------------------------------------------------------------
# Regression compatibility
# ---------------------------------------------------------------------------

class TestRegressionCompatibility:
    def test_existing_browser_module_interface(self):
        from biblioshiny_launcher.browser import wait_and_open_browser, check_biblioshiny_running
        assert callable(wait_and_open_browser)
        assert callable(check_biblioshiny_running)

    def test_existing_r_interface_still_works(self):
        from biblioshiny_launcher.r_interface import build_launch_command, launch_biblioshiny_legacy
        cfg = BiblioshinyConfig()
        cmd = build_launch_command(Path("/tmp/test.txt"), cfg)
        assert "biblioshiny()" in cmd[2]

    def test_existing_models_still_work(self):
        from biblioshiny_launcher.models import (
            LaunchPrechecks, LaunchResult, REnvironmentInfo,
            DatasetInfo, CertificationCheck,
        )
        p = LaunchPrechecks()
        assert p.all_passed is False
        r = LaunchResult()
        assert r.success is False

    def test_import_from_package(self):
        from biblioshiny_launcher import (
            BiblioshinyLaunchManager, BiblioshinyConfig,
            ServerDetectionConfig, ServerDetectionResult,
            ProbeResult, ShinyServerDiscovery,
        )
        assert callable(BiblioshinyLaunchManager)
        assert callable(ShinyServerDiscovery)


# ---------------------------------------------------------------------------
# Cross-platform considerations
# ---------------------------------------------------------------------------

class TestCrossPlatform:
    def test_0_0_0_0_mapped_to_localhost(self):
        text = "Listening on http://0.0.0.0:3838"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["host"] == "127.0.0.1"

    def test_wildcard_host_mapped_to_localhost(self):
        text = "Listening on http://*:3838"
        result = ShinyServerDiscovery._parse_listening_output(text)
        assert result is not None
        assert result["host"] == "127.0.0.1"

    def test_ipv6_localhost_in_probing(self):
        discovery = ShinyServerDiscovery()
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>shiny</html>"
        mock_resp.headers = {"Content-Type": "text/html"}

        with patch("biblioshiny_launcher.server_discovery.urllib.request.urlopen", return_value=mock_resp):
            probe = discovery._probe_port("127.0.0.1", 7654)
            assert probe.is_shiny is True
