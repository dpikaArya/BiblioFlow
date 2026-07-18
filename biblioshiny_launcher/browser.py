"""Biblioshiny Launch Manager - Browser helper with server validation."""
from __future__ import annotations
import webbrowser
import time
import urllib.request
import urllib.error
from typing import Optional

from .models import ServerDetectionResult


BIBLIOSHINY_DEFAULT_URL = "http://127.0.0.1:12737"


def wait_and_open_browser(url: str = BIBLIOSHINY_DEFAULT_URL, delay: float = 5.0) -> bool:
    """Wait for Biblioshiny to start, then open in default browser.

    Returns True if browser was opened, False otherwise.
    """
    time.sleep(delay)
    return open_browser(url)


def open_browser(url: str) -> bool:
    """Open a URL in the default browser.

    Returns True if successful, False otherwise.
    """
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def open_validated_browser(
    detection_result: ServerDetectionResult,
    auto_open: bool = True,
) -> ServerDetectionResult:
    """Open the browser only after successful server validation.

    If browser launch fails, sets manual_url so the user can open it manually.

    Returns the updated ServerDetectionResult.
    """
    if not detection_result.detected or not detection_result.url:
        detection_result.browser_status = "not_detected"
        return detection_result

    if not detection_result.server_reachable:
        detection_result.browser_status = "server_unreachable"
        return detection_result

    detection_result.manual_url = detection_result.url

    if not auto_open:
        detection_result.browser_status = "manual_url_ready"
        return detection_result

    success = open_browser(detection_result.url)

    if success:
        detection_result.browser_status = "launched"
    else:
        detection_result.browser_status = "manual_url_displayed"

    return detection_result


def check_biblioshiny_running(url: str = BIBLIOSHINY_DEFAULT_URL, timeout: float = 10.0) -> bool:
    """Check if Biblioshiny is running by attempting to connect.

    Returns True if the server responds, False otherwise.
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            time.sleep(1.0)
    return False
