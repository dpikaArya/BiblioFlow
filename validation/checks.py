"""Validation checks."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.models import PipelineState

logger = logging.getLogger("aibef.validation")


class ValidationChecks:
    """Run validation checks on pipeline state."""

    @staticmethod
    def verify_synchronization(state: PipelineState) -> bool:
        """Verify included studies == validated dataset rows."""
        validated = len(state.validated_dataset) if state.validated_dataset is not None else 0
        included = len(state.included_studies) if state.included_studies is not None else 0

        if validated != included:
            logger.error("SYNCHRONIZATION FAILED: validated=%d, included=%d",
                        validated, included)
            return False
        logger.info("Synchronization verified: %d records", validated)
        return True

    @staticmethod
    def verify_bibliometrix_compatible(state: PipelineState) -> bool:
        """Check basic Bibliometrix compatibility."""
        df = state.validated_dataset
        if df is None or df.empty:
            return False
        required = ["AU", "TI", "SO", "PY"]
        for col in required:
            if col not in df.columns:
                return False
        return True

    @staticmethod
    def verify_all_outputs(output_dir: Path) -> dict[str, bool]:
        """Verify all expected output files exist."""
        expected = [
            "Bibliometrix_Compatible.xlsx",
            "Bibliometrix_Compatible.csv",
            "Bibliometrix_Compatible.txt",
            "Bibliometrix_Validation_Report.docx",
            "PRISMA_Report.docx",
            "Validation_Report.docx",
            "Included_Studies.xlsx",
            "Excluded_Studies.xlsx",
            "Screening_Log.xlsx",
            "Audit_Log.json",
            "Provenance_Log.json",
            "R_Validation_Output.txt",
            "R_Validation.json",
        ]
        results = {}
        for filename in expected:
            path = output_dir / filename
            results[filename] = path.exists() and path.stat().st_size > 0
        return results
