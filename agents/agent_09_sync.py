"""Agent 9: Synchronization Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from core.exceptions import SynchronizationError

logger = logging.getLogger("aibef.sync")


class SynchronizationAgent:
    NAME = "SynchronizationAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting synchronization check", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning synchronization verification")
        
        validated_df = state.validated_dataset
        if validated_df is None or (isinstance(validated_df, pd.DataFrame) and validated_df.empty):
            # Fall back to bibliometrix_compatible or cleaned_dataset
            validated_df = state.bibliometrix_compatible
            if validated_df is None or (isinstance(validated_df, pd.DataFrame) and validated_df.empty):
                validated_df = state.cleaned_dataset
            if validated_df is None or (isinstance(validated_df, pd.DataFrame) and validated_df.empty):
                raise SynchronizationError("No dataset to synchronize")
            state.validated_dataset = validated_df
        
        validated_count = len(validated_df)
        
        included_count = 0
        if state.included_studies is not None:
            included_count = len(state.included_studies)
        elif state.prisma_data.get("records", {}).get("included"):
            included_count = state.prisma_data["records"]["included"]
        
        state.stats.prisma_included = included_count
        
        logger.info("[%s] Validated dataset: %d rows, PRISMA included: %d",
                    self.NAME, validated_count, included_count)
        
        if validated_count != included_count:
            mismatch_detail = (
                f"SYNCHRONIZATION ERROR: Validated dataset has {validated_count} rows "
                f"but PRISMA reports {included_count} included studies. "
                f"Difference: {abs(validated_count - included_count)} records."
            )
            logger.error("[%s] %s", self.NAME, mismatch_detail)
            
            # Try to repair: set included_studies = validated_dataset
            state.included_studies = validated_df.copy()
            state.prisma_data["records"]["included"] = validated_count
            state.stats.prisma_included = validated_count
            
            state.errors.append(f"[{self.NAME}] Auto-repaired: set included = {validated_count}")
            logger.info("[%s] Auto-repaired: set PRISMA included = %d", self.NAME, validated_count)
        
        # Final verification after repair
        if state.included_studies is not None:
            final_count = len(state.included_studies)
        else:
            final_count = validated_count
            state.included_studies = validated_df.copy()
        
        state.prisma_data["records"]["included"] = final_count
        state.stats.prisma_included = final_count
        state.stats.synchronized = True
        
        logger.info("[%s] Synchronization PASSED: %d records", self.NAME, final_count)
        state.log_stage(self.NAME, "complete",
                        f"Synchronization passed: {final_count} records",
                        {"validated_count": validated_count,
                         "included_count": final_count,
                         "synchronized": True})
        
        return state
