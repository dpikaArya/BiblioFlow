"""Pipeline orchestrator for AIBEF."""
from __future__ import annotations
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG, FrameworkConfig
from core.models import PipelineState
from core.logging_config import setup_logging, AuditLog
from agents import (
    DatasetImportAgent, DatasetMergeAgent, DuplicateDetectionAgent,
    MetadataValidationAgent, CleaningHarmonizationAgent,
    BibliometrixCompatAgent, BibliometrixValidationAgent,
    PRISMAAgent, SynchronizationAgent, QualityValidationAgent,
    ExportAgent,
)

logger = logging.getLogger("aibef.orchestrator")

PIPELINE_STEPS = [
    ("import", DatasetImportAgent, "Dataset Import"),
    ("merge", DatasetMergeAgent, "Dataset Merge"),
    ("deduplicate", DuplicateDetectionAgent, "Duplicate Detection"),
    ("validate", MetadataValidationAgent, "Metadata Validation"),
    ("clean", CleaningHarmonizationAgent, "Cleaning & Harmonization"),
    ("compat", BibliometrixCompatAgent, "Bibliometrix Compatibility"),
    ("biblio_validate", BibliometrixValidationAgent, "Bibliometrix Validation"),
    ("prisma", PRISMAAgent, "PRISMA Generation"),
    ("sync", SynchronizationAgent, "Synchronization"),
    ("quality", QualityValidationAgent, "Quality Validation"),
    ("export", ExportAgent, "Export"),
]


class PipelineOrchestrator:
    """Orchestrates all agents in sequence."""

    def __init__(self, config: Optional[FrameworkConfig] = None):
        self.config = config or CONFIG
        self.logger = setup_logging(self.config.log_dir)
        self.audit = AuditLog(self.config.output_dir / "Audit_Log.json")
        self.state: Optional[PipelineState] = None

    def run(self) -> PipelineState:
        """Execute the full pipeline."""
        self.logger.info("=" * 60)
        self.logger.info("AIBEF Pipeline Starting")
        self.logger.info("Input: %s", self.config.input_dir)
        self.logger.info("Output: %s", self.config.output_dir)
        self.logger.info("=" * 60)

        start_time = time.time()

        self.state = PipelineState(config=self.config)

        for step_key, agent_cls, step_name in PIPELINE_STEPS:
            step_start = time.time()
            self.logger.info("-" * 40)
            self.logger.info("Step: %s (%s)", step_name, agent_cls.__name__)
            self.logger.info("-" * 40)

            try:
                agent = agent_cls()
                self.state = agent.execute(self.state)

                step_time = time.time() - step_start
                self.logger.info("Step '%s' completed in %.1fs", step_name, step_time)

                self.audit.add(
                    agent=step_key,
                    action="complete",
                    details={
                        "step_name": step_name,
                        "duration_seconds": round(step_time, 2),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            except Exception as e:
                step_time = time.time() - step_start
                self.logger.error("Step '%s' FAILED: %s", step_name, e, exc_info=True)
                self.state.add_error(step_key, str(e))

                self.audit.add(
                    agent=step_key,
                    action="failed",
                    details={
                        "step_name": step_name,
                        "error": str(e),
                        "duration_seconds": round(step_time, 2),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                if step_key in ("import", "merge"):
                    self.logger.error("Critical step failed. Aborting pipeline.")
                    raise

                self.logger.warning("Non-critical step failed. Continuing pipeline.")

        total_time = time.time() - start_time
        self.logger.info("=" * 60)
        self.logger.info("AIBEF Pipeline Complete in %.1fs", total_time)
        self.logger.info("Total errors: %d", len(self.state.errors))
        self.logger.info("=" * 60)

        self.audit.add(
            agent="system",
            action="pipeline_complete",
            details={
                "total_duration": round(total_time, 2),
                "errors": len(self.state.errors),
                "final_count": self.state.stats.final_count,
            }
        )

        return self.state
