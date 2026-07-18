"""Agent 3: Duplicate Detection Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState, DuplicateMapping
from core.exceptions import DeduplicationError

logger = logging.getLogger("aibef.deduplicate")


class DuplicateDetectionAgent:
    NAME = "DuplicateDetectionAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting duplicate detection", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning duplicate detection")
        
        df = state.master_dataset
        if df is None or df.empty:
            raise DeduplicationError("No master dataset to deduplicate")
        
        n_before = len(df)
        duplicate_mask = pd.Series([False] * len(df), index=df.index)
        
        # Phase 1: Exact DOI match
        if "DI" in df.columns:
            doi_groups = df.groupby("DI").filter(lambda x: len(x) > 1 and pd.notna(x["DI"].iloc[0]))
            for _, group in doi_groups.groupby("DI"):
                if len(group) > 1:
                    keep_idx = group.index[0]
                    for idx in group.index[1:]:
                        duplicate_mask[idx] = True
                        self._add_mapping(state, df, idx, keep_idx, "doi_exact", 100.0)
        
        # Phase 2: Exact UT match
        if "UT" in df.columns:
            ut_groups = df.groupby("UT").filter(lambda x: len(x) > 1 and pd.notna(x["UT"].iloc[0]))
            for _, group in ut_groups.groupby("UT"):
                if len(group) > 1:
                    keep_idx = group.index[0]
                    for idx in group.index[1:]:
                        if not duplicate_mask[idx]:
                            duplicate_mask[idx] = True
                            self._add_mapping(state, df, idx, keep_idx, "ut_exact", 100.0)
        
        # Phase 3: Title similarity for remaining non-duplicates
        threshold = state.config.title_similarity_threshold
        non_dups = df[~duplicate_mask].copy()
        title_col = "TI" if "TI" in df.columns else None
        
        if title_col:
            indices = non_dups.index.tolist()
            for i in range(len(indices)):
                if duplicate_mask[indices[i]]:
                    continue
                title_i = str(non_dups.loc[indices[i], title_col])
                if not title_i or title_i == "nan":
                    continue
                for j in range(i + 1, len(indices)):
                    if duplicate_mask[indices[j]]:
                        continue
                    title_j = str(non_dups.loc[indices[j], title_col])
                    if not title_j or title_j == "nan":
                        continue
                    sim = fuzz.ratio(title_i.lower().strip(), title_j.lower().strip())
                    if sim >= threshold:
                        duplicate_mask[indices[j]] = True
                        self._add_mapping(state, df, indices[j], indices[i],
                                         "title_similarity", sim)
        
        # Phase 4: Author + Year match for remaining
        if "AU" in df.columns and "PY" in df.columns and "TI" in df.columns:
            still_non_dup = df[~duplicate_mask].copy()
            indices = still_non_dup.index.tolist()
            for i in range(len(indices)):
                if duplicate_mask[indices[i]]:
                    continue
                auth_i = str(still_non_dup.loc[indices[i], "AU"])
                year_i = str(still_non_dup.loc[indices[i], "PY"])
                title_i = str(still_non_dup.loc[indices[i], "TI"])
                if not auth_i or not year_i or year_i == "nan":
                    continue
                for j in range(i + 1, len(indices)):
                    if duplicate_mask[indices[j]]:
                        continue
                    auth_j = str(still_non_dup.loc[indices[j], "AU"])
                    year_j = str(still_non_dup.loc[indices[j], "PY"])
                    title_j = str(still_non_dup.loc[indices[j], "TI"])
                    if not auth_j or not year_j or year_j == "nan":
                        continue
                    if year_i == year_j:
                        auth_sim = fuzz.ratio(auth_i.lower(), auth_j.lower())
                        if auth_sim >= 85:
                            combined = (auth_sim + fuzz.ratio(
                                title_i.lower().strip(), title_j.lower().strip())) / 2
                            if combined >= threshold:
                                duplicate_mask[indices[j]] = True
                                self._add_mapping(state, df, indices[j], indices[i],
                                                 "author_year_title", combined)
        
        n_duplicates = duplicate_mask.sum()
        df_clean = df[~duplicate_mask].reset_index(drop=True)
        
        state.master_dataset = df_clean
        state.stats.duplicates_found = int(n_duplicates)
        state.stats.duplicates_removed = int(n_duplicates)
        state.stats.after_dedup = len(df_clean)
        
        logger.info("[%s] Removed %d duplicates from %d records -> %d remaining",
                    self.NAME, n_duplicates, n_before, len(df_clean))
        
        state.log_stage(self.NAME, "complete",
                        f"Removed {n_duplicates} duplicates, {len(df_clean)} records remain",
                        {"before": n_before, "removed": int(n_duplicates),
                         "after": len(df_clean),
                         "doi_exact": sum(1 for m in state.duplicate_mappings if m.match_type == "doi_exact"),
                         "title_similarity": sum(1 for m in state.duplicate_mappings if "title" in m.match_type),
                         "author_year_title": sum(1 for m in state.duplicate_mappings if m.match_type == "author_year_title")})
        
        return state
    
    def _add_mapping(self, state: PipelineState, df: pd.DataFrame,
                     dup_idx: int, keep_idx: int, match_type: str, score: float):
        dup_id = str(df.iloc[dup_idx].get("__record_id__", dup_idx))
        keep_id = str(df.iloc[keep_idx].get("__record_id__", keep_idx))
        source = str(df.iloc[dup_idx].get("__source_file__", "unknown"))
        state.duplicate_mappings.append(DuplicateMapping(
            record_id=dup_id,
            duplicate_of=keep_id,
            match_type=match_type,
            similarity_score=score,
            source_file=source,
        ))
