"""Agent 10: Quality Validation Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState

logger = logging.getLogger("aibef.quality")


class QualityValidationAgent:
    NAME = "QualityValidationAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting quality validation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning quality validation")
        
        checks = {}
        score = 100
        
        # 1. Import check
        checks["import"] = {
            "status": "PASS" if state.stats.total_imported > 0 else "FAIL",
            "total_imported": state.stats.total_imported,
            "per_file": state.stats.per_file,
        }
        if state.stats.total_imported == 0:
            score -= 25
        
        # 2. Merge check
        checks["merge"] = {
            "status": "PASS" if state.stats.after_merge > 0 else "FAIL",
            "after_merge": state.stats.after_merge,
        }
        if state.stats.after_merge == 0:
            score -= 25
        
        # 3. Deduplication check
        checks["deduplication"] = {
            "status": "PASS",
            "duplicates_found": state.stats.duplicates_found,
            "after_dedup": state.stats.after_dedup,
        }
        
        # 4. Metadata validation
        checks["metadata_validation"] = {
            "status": "PASS" if state.stats.validation_issues < state.stats.after_dedup * 0.5 else "WARNING",
            "issues_found": state.stats.validation_issues,
        }
        
        # 5. Cleaning check
        checks["cleaning"] = {
            "status": "PASS" if state.stats.after_cleaning > 0 else "FAIL",
            "repairs_made": state.stats.metadata_repairs,
            "after_cleaning": state.stats.after_cleaning,
        }
        if state.stats.after_cleaning == 0:
            score -= 20
        
        # 6. Bibliometrix compatibility check
        bib_valid = state.validated_dataset is not None and not state.validated_dataset.empty
        checks["bibliometrix_compatibility"] = {
            "status": "PASS" if bib_valid else "FAIL",
            "dataset_ready": bib_valid,
        }
        if not bib_valid:
            score -= 25
        
        # 7. PRISMA synchronization
        checks["prisma_synchronization"] = {
            "status": "PASS" if state.stats.synchronized else "FAIL",
            "synchronized": state.stats.synchronized,
            "prisma_included": state.stats.prisma_included,
            "final_count": state.stats.final_count,
        }
        if not state.stats.synchronized:
            score -= 20
        
        # 8. Record count consistency
        validated_count = len(state.validated_dataset) if state.validated_dataset is not None else 0
        included_count = len(state.included_studies) if state.included_studies is not None else 0
        checks["count_consistency"] = {
            "status": "PASS" if validated_count == included_count else "FAIL",
            "validated_count": validated_count,
            "included_count": included_count,
        }
        if validated_count != included_count:
            score -= 15
        
        state.stats.final_count = validated_count
        
        quality_report = {
            "timestamp": datetime.now().isoformat(),
            "overall_score": max(0, score),
            "grade": self._grade(score),
            "checks": checks,
            "total_errors": len(state.errors),
            "warnings": [e for e in state.errors if "warning" in e.lower() or "Warning" in e],
        }
        
        state.prisma_data["quality_report"] = quality_report
        
        logger.info("[%s] Quality score: %d/100 (%s)", self.NAME, score, quality_report["grade"])
        state.log_stage(self.NAME, "complete",
                        f"Quality score: {score}/100 ({quality_report['grade']})",
                        quality_report)
        
        return state
    
    def _grade(self, score: int) -> str:
        if score >= 90:
            return "A - Excellent"
        elif score >= 75:
            return "B - Good"
        elif score >= 60:
            return "C - Adequate"
        elif score >= 40:
            return "D - Poor"
        return "F - Failing"
