"""Biblioshiny Launch Manager - Dual Shiny Server Detection.

Primary: Monitor R stdout/stderr for "Listening on" patterns.
Fallback: Enumerate TCP ports of spawned R process, HTTP probe.
"""
from __future__ import annotations
import re
import time
import urllib.request
import urllib.error
import socket
import subprocess
from typing import Optional

from .config import ServerDetectionConfig
from .models import ServerDetectionResult, ProbeResult


_LISTENING_PATTERNS = [
    re.compile(
        r"Listening on\s+"
        r"(?P<protocol>https?)://(?P<host>[^:\s]+):(?P<port>\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<protocol>https?)://(?P<host>127\.0\.0\.1|localhost):(?P<port>\d+)",
        re.IGNORECASE,
    ),
]

_SHINY_BODY_MARKERS = [
    "shiny", "Shiny", "biblioshiny", "bibliometrix",
    "session", "htmlwidget", "shinyApp", "runApp",
]

_SHINY_HTML_MARKERS = [
    "shiny.js", "shiny.min.js", "shinycss", "shiny-autoreload",
    "bootstrap-3", "data-display-if", "shiny-session",
]


class ShinyServerDiscovery:
    """Detect a running Shiny server using dual strategy.

    Strategy 1 (primary): Parse R process stdout/stderr for the listening URL.
    Strategy 2 (fallback): Enumerate TCP ports of the spawned R process,
    probe each with HTTP, verify the endpoint hosts a Shiny application.
    """

    def __init__(self, config: Optional[ServerDetectionConfig] = None):
        self.config = config or ServerDetectionConfig()
        self._result = ServerDetectionResult()

    @property
    def result(self) -> ServerDetectionResult:
        return self._result

    def discover(
        self,
        process: Optional[subprocess.Popen] = None,
        timeout_seconds: Optional[float] = None,
    ) -> ServerDetectionResult:
        """Run the dual detection strategy.

        Args:
            process: The spawned R subprocess with PIPE stdout/stderr.
            timeout_seconds: Override for console detection timeout.

        Returns:
            ServerDetectionResult with detection details.
        """
        self._result = ServerDetectionResult()
        t0 = time.time()

        if timeout_seconds is None:
            timeout_seconds = self.config.console_detection_timeout_seconds

        if process is not None:
            detected = self._primary_console_detection(process, timeout_seconds)
            if detected:
                self._result.detection_method = "console_detection"
                self._result.console_detection_succeeded = True
                self._result.detection_time_seconds = time.time() - t0
                self._validate_server()
                return self._result

        if self.config.allow_process_port_scan and process is not None:
            detected = self._fallback_port_detection(process)
            if detected:
                self._result.detection_method = "port_discovery"
                self._result.fallback_detection_succeeded = True
                self._result.detection_time_seconds = time.time() - t0
                self._validate_server()
                return self._result

        self._result.detection_time_seconds = time.time() - t0
        self._result.error_message = (
            "Server detection failed: no valid Shiny endpoint found"
        )
        return self._result

    def discover_from_url(
        self,
        url: str,
        timeout_seconds: Optional[float] = None,
    ) -> ServerDetectionResult:
        """Detect/validate a server at a known URL (for testing or manual input).

        Args:
            url: The full URL to validate (e.g. "http://127.0.0.1:12737").
            timeout_seconds: Override for console detection timeout.

        Returns:
            ServerDetectionResult with detection details.
        """
        self._result = ServerDetectionResult()
        t0 = time.time()
        if timeout_seconds is None:
            timeout_seconds = self.config.console_detection_timeout_seconds

        parsed = self._parse_url(url)
        if parsed:
            self._result.url = url
            self._result.host = parsed["host"]
            self._result.port = parsed["port"]
            self._result.protocol = parsed["protocol"]
            self._result.detection_method = "manual_url"
            self._result.console_detection_succeeded = True
            self._validate_server()
        else:
            self._result.error_message = f"Invalid URL format: {url}"

        self._result.detection_time_seconds = time.time() - t0
        return self._result

    # ------------------------------------------------------------------
    # Primary: Console output detection
    # ------------------------------------------------------------------

    def _primary_console_detection(
        self,
        process: subprocess.Popen,
        timeout_seconds: float,
    ) -> bool:
        """Monitor R process stdout/stderr for Listening patterns."""
        stream = process.stdout
        if stream is None:
            return False

        deadline = time.time() + timeout_seconds
        buffer = b""
        poll_interval = min(0.1, timeout_seconds / 50)

        while time.time() < deadline:
            if process.poll() is not None:
                break

            try:
                chunk = stream.read(4096)
                if chunk:
                    buffer += chunk
                    decoded = buffer.decode("utf-8", errors="replace")
                    parsed = self._parse_listening_output(decoded)
                    if parsed:
                        self._result.url = parsed["url"]
                        self._result.host = parsed["host"]
                        self._result.port = parsed["port"]
                        self._result.protocol = parsed["protocol"]
                        return True
                    last_nl = decoded.rfind("\n")
                    if last_nl > 0:
                        buffer = decoded[last_nl + 1:].encode("utf-8", errors="replace")
                else:
                    time.sleep(poll_interval)
            except (BlockingIOError, ValueError):
                time.sleep(poll_interval)

        if process.stderr is not None:
            try:
                stderr_data = process.stderr.read(65536)
                if stderr_data:
                    decoded = stderr_data.decode("utf-8", errors="replace")
                    parsed = self._parse_listening_output(decoded)
                    if parsed:
                        self._result.url = parsed["url"]
                        self._result.host = parsed["host"]
                        self._result.port = parsed["port"]
                        self._result.protocol = parsed["protocol"]
                        return True
            except Exception:
                pass

        return False

    @staticmethod
    def _parse_listening_output(text: str) -> Optional[dict]:
        """Extract host:port from R console output."""
        for pattern in _LISTENING_PATTERNS:
            match = pattern.search(text)
            if match:
                protocol = match.group("protocol").lower()
                host = match.group("host")
                if host in ("0.0.0.0", "0", "*"):
                    host = "127.0.0.1"
                port = int(match.group("port"))
                if 1 <= port <= 65535:
                    return {
                        "url": f"{protocol}://{host}:{port}",
                        "host": host,
                        "port": port,
                        "protocol": protocol,
                    }
        return None

    @staticmethod
    def _parse_url(url: str) -> Optional[dict]:
        """Parse a URL into protocol, host, port components."""
        match = re.match(
            r"^(?P<protocol>https?)://(?P<host>[^:\s]+):(?P<port>\d+)(?:/.*)?$",
            url.strip(),
        )
        if match:
            port = int(match.group("port"))
            if 1 <= port <= 65535:
                return {
                    "protocol": match.group("protocol").lower(),
                    "host": match.group("host"),
                    "port": port,
                }
        return None

    # ------------------------------------------------------------------
    # Fallback: Process-specific port discovery
    # ------------------------------------------------------------------

    def _fallback_port_detection(self, process: subprocess.Popen) -> bool:
        """Enumerate TCP ports of the R process, probe each."""
        pid = process.pid
        if pid is None:
            return False

        ports = self._get_process_tcp_ports(pid)
        if not ports:
            return False

        self._result.probe_attempts = len(ports)
        best: Optional[ProbeResult] = None

        for port in ports:
            if self._is_port_in_use("127.0.0.1", port):
                probe = self._probe_port("127.0.0.1", port, pid)
                self._result.probe_results.append(probe)
                if probe.is_shiny:
                    if best is None or probe.is_biblioshiny:
                        best = probe
                        if probe.is_biblioshiny:
                            break
            else:
                self._result.probe_results.append(ProbeResult(
                    host="127.0.0.1",
                    port=port,
                    is_open=False,
                    process_pid=pid,
                ))

        if best and best.is_shiny:
            protocol = "https" if self._result.protocol == "https" else "http"
            self._result.url = f"{protocol}://{best.host}:{best.port}"
            self._result.host = best.host
            self._result.port = best.port
            self._result.server_reachable = True
            self._result.http_status = best.http_status
            self._result.shiny_application_detected = True
            self._result.biblioshiny_identified = best.is_biblioshiny
            self._result.response_latency_ms = best.response_latency_ms
            return True

        return False

    @staticmethod
    def _get_process_tcp_ports(pid: int) -> list[int]:
        """Get TCP port numbers owned by a specific process.

        Uses psutil if available, falls back to platform-specific commands.
        Only returns ports bound to localhost/127.0.0.1.
        """
        ports: list[int] = []

        try:
            import psutil as _psutil
            proc = _psutil.Process(pid)
            for conn in proc.connections(kind="tcp"):
                if conn.status == "LISTEN":
                    addr = conn.laddr
                    if addr.ip in ("127.0.0.1", "localhost", "::1", ""):
                        ports.append(addr.port)
            return sorted(set(ports))
        except ImportError:
            pass
        except (_psutil.NoSuchProcess, _psutil.AccessDenied):
            pass

        try:
            output = subprocess.check_output(
                ["netstat", "-ano"],
                text=True, timeout=5, stderr=subprocess.DEVNULL,
            )
            for line in output.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in line:
                    addr = parts[1]
                    if ":" in addr:
                        host_part = addr.rsplit(":", 1)[0]
                        port_part = addr.rsplit(":", 1)[1]
                        try:
                            port = int(port_part)
                        except ValueError:
                            continue
                        if host_part in ("127.0.0.1", "localhost", "::1", ""):
                            try:
                                conn_pid = int(parts[-1])
                            except ValueError:
                                continue
                            if conn_pid == pid:
                                ports.append(port)
        except Exception:
            pass

        return sorted(set(ports))

    @staticmethod
    def _is_port_in_use(host: str, port: int) -> bool:
        """Check if a specific port is in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    def _probe_port(
        self,
        host: str,
        port: int,
        expected_pid: Optional[int] = None,
    ) -> ProbeResult:
        """Probe a single port with an HTTP request."""
        probe = ProbeResult(
            host=host,
            port=port,
            is_open=True,
            process_pid=expected_pid,
        )

        url = f"http://{host}:{port}"
        t0 = time.time()

        try:
            req = urllib.request.Request(
                url,
                method="GET",
                headers={"User-Agent": "AIBEF-BLM/1.0"},
            )
            resp = urllib.request.urlopen(req, timeout=3)
            probe.http_status = resp.status
            probe.server_reachable = True
            probe.response_latency_ms = (time.time() - t0) * 1000

            content_type = resp.headers.get("Content-Type", "")
            body = resp.read(32768).decode("utf-8", errors="replace")

            if "html" in content_type or "<html" in body.lower():
                probe.is_shiny = self._is_shiny_response(body)
                if probe.is_shiny:
                    probe.is_biblioshiny = self._is_biblioshiny_response(body)
        except (urllib.error.URLError, ConnectionRefusedError,
                socket.timeout, OSError, ValueError):
            pass

        return probe

    def _is_shiny_response(self, body: str) -> bool:
        """Verify the HTTP response contains Shiny application markers."""
        if not self.config.verify_shiny_application:
            return True

        body_lower = body.lower()

        for marker in _SHINY_BODY_MARKERS:
            if marker.lower() in body_lower:
                return True

        for marker in _SHINY_HTML_MARKERS:
            if marker.lower() in body_lower:
                return True

        return False

    def _is_biblioshiny_response(self, body: str) -> bool:
        """Check if the response is specifically Biblioshiny."""
        body_lower = body.lower()
        return "biblioshiny" in body_lower or "bibliometrix" in body_lower

    # ------------------------------------------------------------------
    # Server validation (runs after detection)
    # ------------------------------------------------------------------

    def _validate_server(self) -> None:
        """Validate the detected server before declaring success."""
        if not self._result.url:
            return

        try:
            req = urllib.request.Request(
                self._result.url,
                method="GET",
                headers={"User-Agent": "AIBEF-BLM/1.0"},
            )
            t0 = time.time()
            resp = urllib.request.urlopen(req, timeout=5)
            self._result.http_status = resp.status
            self._result.server_reachable = True
            self._result.response_latency_ms = (time.time() - t0) * 1000

            body = resp.read(32768).decode("utf-8", errors="replace")
            self._result.shiny_application_detected = self._is_shiny_response(body)
            self._result.biblioshiny_identified = self._is_biblioshiny_response(body)
        except Exception:
            pass

        if self._result.server_reachable:
            self._result.detected = True
        else:
            self._result.detected = False
            self._result.error_message = "URL detected but server not reachable"
