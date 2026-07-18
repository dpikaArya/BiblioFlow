"""Report generation utilities."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.models import PipelineState

logger = logging.getLogger("aibef.reports")


class ReportGenerator:
    """Generate all report files."""

    @staticmethod
    def generate_all(state: PipelineState, output_dir: Path):
        """Generate all report files."""
        ReportGenerator._prisma_flow_text(state, output_dir / "prisma_flow.txt")
        ReportGenerator._summary_table(state, output_dir / "pipeline_summary.txt")

    @staticmethod
    def _prisma_flow_text(state: PipelineState, path: Path):
        recs = state.prisma_data.get("records", {})
        lines = [
            "=" * 60,
            "PRISMA FLOW DIAGRAM",
            "=" * 60,
            "",
            f"Records identified through database searching:",
            f"  Total: {recs.get('imported', 'N/A')}",
            f"  Per file: {dict(state.stats.per_file)}",
            "",
            f"Records after merging: {recs.get('merged', 'N/A')}",
            "",
            f"Duplicates removed: {recs.get('duplicates_identified', 'N/A')}",
            f"Records after deduplication: {recs.get('after_dedup', 'N/A')}",
            "",
            f"Records after cleaning: {recs.get('after_cleaning', 'N/A')}",
            "",
            f"Studies included in final review: {recs.get('included', 'N/A')}",
            "",
            "=" * 60,
        ]
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _summary_table(state: PipelineState, path: Path):
        lines = [
            "AIBEF Pipeline Summary",
            "=" * 40,
            f"Total imported: {state.stats.total_imported}",
            f"After merge: {state.stats.after_merge}",
            f"Duplicates found: {state.stats.duplicates_found}",
            f"After dedup: {state.stats.after_dedup}",
            f"Validation issues: {state.stats.validation_issues}",
            f"Metadata repairs: {state.stats.metadata_repairs}",
            f"After cleaning: {state.stats.after_cleaning}",
            f"Final count: {state.stats.final_count}",
            f"Synchronized: {state.stats.synchronized}",
            f"Errors: {len(state.errors)}",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
