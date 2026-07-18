"""Centralized logging for AIBEF."""
import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "agent": getattr(record, "agent", "system"),
            "stage": getattr(record, "stage", "general"),
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

class AuditLog:
    """Persistent audit log stored as JSON."""
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.entries: list[dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.log_path.exists():
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    self.entries = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.entries = []

    def add(self, agent: str, action: str, details: dict[str, Any]):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent": agent,
            "action": action,
            "details": details,
        }
        self.entries.append(entry)
        self._save()

    def _save(self):
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, ensure_ascii=False)

    def get_entries(self, agent: Optional[str] = None) -> list[dict]:
        if agent:
            return [e for e in self.entries if e["agent"] == agent]
        return self.entries

def setup_logging(log_dir: Path, name: str = "aibef") -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler(
        log_dir / f"aibef_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
    ))
    logger.addHandler(file_handler)
    
    json_handler = logging.FileHandler(
        log_dir / "audit_log.json", encoding="utf-8"
    )
    json_handler.setLevel(logging.INFO)
    json_handler.setFormatter(JSONFormatter())
    logger.addHandler(json_handler)
    
    return logger
