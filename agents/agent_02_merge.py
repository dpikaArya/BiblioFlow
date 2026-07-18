"""Agent 2: Dataset Merge Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from core.exceptions import MergeError

logger = logging.getLogger("aibef.merge")


class DatasetMergeAgent:
    NAME = "DatasetMergeAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting merge", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning dataset merge")
        
        if not state.raw_datasets:
            raise MergeError("No raw datasets available for merging")
        
        all_dfs = list(state.raw_datasets.values())
        
        # Find common columns across all dataframes
        common_columns = set(all_dfs[0].columns)
        for df in all_dfs[1:]:
            common_columns &= set(df.columns)
        
        # Keep all columns but align with NaN where missing
        master = pd.concat(all_dfs, ignore_index=True, sort=False)
        
        state.master_dataset = master
        state.stats.after_merge = len(master)
        
        logger.info("[%s] Merged %d datasets into %d records, %d columns",
                    self.NAME, len(all_dfs), len(master), len(master.columns))
        
        state.log_stage(self.NAME, "complete",
                        f"Merged {len(all_dfs)} datasets into {len(master)} records",
                        {"total_datasets": len(all_dfs), "columns": list(master.columns)})
        
        return state
