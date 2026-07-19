"""Agent 3: Duplicate Detection Agent.

Optimized with blocking strategies to handle large datasets efficiently.
"""
from __future__ import annotations
import logging
import re
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


def _normalize_title(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""
    t = text.lower().strip()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


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

        # Phase 1: Exact DOI match (fast)
        if "DI" in df.columns:
            logger.info("[%s] Phase 1: DOI exact matching", self.NAME)
            doi_valid = df["DI"].notna() & (df["DI"].astype(str).str.strip() != "") & (df["DI"].astype(str) != "nan")
            if doi_valid.any():
                doi_groups = df[doi_valid].groupby("DI").filter(lambda x: len(x) > 1)
                if not doi_groups.empty:
                    for _, group in doi_groups.groupby("DI"):
                        if len(group) > 1:
                            keep_idx = group.index[0]
                            for idx in group.index[1:]:
                                if not duplicate_mask[idx]:
                                    duplicate_mask[idx] = True
                                    self._add_mapping(state, df, idx, keep_idx, "doi_exact", 100.0)

        # Phase 2: Exact UT match (fast)
        if "UT" in df.columns:
            logger.info("[%s] Phase 2: UT exact matching", self.NAME)
            ut_valid = df["UT"].notna() & (df["UT"].astype(str).str.strip() != "") & (df["UT"].astype(str) != "nan")
            if ut_valid.any():
                ut_groups = df[ut_valid].groupby("UT").filter(lambda x: len(x) > 1)
                if not ut_groups.empty:
                    for _, group in ut_groups.groupby("UT"):
                        if len(group) > 1:
                            keep_idx = group.index[0]
                            for idx in group.index[1:]:
                                if not duplicate_mask[idx]:
                                    duplicate_mask[idx] = True
                                    self._add_mapping(state, df, idx, keep_idx, "ut_exact", 100.0)

        # Phase 3: Title similarity with blocking (optimized)
        threshold = state.config.title_similarity_threshold
        title_col = "TI" if "TI" in df.columns else None

        if title_col:
            logger.info("[%s] Phase 3: Title similarity (blocked)", self.NAME)
            non_dup_indices = df[~duplicate_mask].index.tolist()
            titles = {}
            for idx in non_dup_indices:
                t = _normalize_title(str(df.loc[idx, title_col]))
                if t and len(t) > 5:
                    titles[idx] = t

            # Blocking: group by first 4 chars to reduce comparisons
            blocks: dict[str, list[int]] = {}
            for idx, title in titles.items():
                block_key = title[:4]
                if block_key not in blocks:
                    blocks[block_key] = []
                blocks[block_key].append(idx)

            total_comparisons = 0
            for block_key, block_indices in blocks.items():
                if len(block_indices) < 2:
                    continue
                block_titles = [titles[i] for i in block_indices]

                # Use rapidfuzz cdist for batch comparison within block
                if len(block_titles) >= 2:
                    n = len(block_titles)
                    for i in range(n):
                        if duplicate_mask[block_indices[i]]:
                            continue
                        for j in range(i + 1, n):
                            if duplicate_mask[block_indices[j]]:
                                continue
                            sim = fuzz.ratio(block_titles[i], block_titles[j])
                            total_comparisons += 1
                            if sim >= threshold:
                                duplicate_mask[block_indices[j]] = True
                                self._add_mapping(state, df, block_indices[j], block_indices[i],
                                                 "title_similarity", sim)

            logger.info("[%s] Phase 3: %d title comparisons in %d blocks",
                        self.NAME, total_comparisons, len(blocks))

        # Phase 4: Author + Year match (blocked by year)
        if "AU" in df.columns and "PY" in df.columns and title_col:
            logger.info("[%s] Phase 4: Author+Year matching (blocked by year)", self.NAME)
            non_dup_indices = df[~duplicate_mask].index.tolist()

            # Group by year first
            year_groups: dict[str, list[int]] = {}
            for idx in non_dup_indices:
                year_val = str(df.loc[idx, "PY"]).strip()
                if year_val and year_val != "nan":
                    year_groups.setdefault(year_val, []).append(idx)

            for year_val, year_indices in year_groups.items():
                if len(year_indices) < 2:
                    continue

                # Further block by first author initial for performance
                auth_blocks: dict[str, list[int]] = {}
                for idx in year_indices:
                    auth_val = str(df.loc[idx, "AU"]).strip().lower()
                    if not auth_val or auth_val == "nan":
                        continue
                    first_auth = auth_val.split(";")[0].strip()[:20]
                    auth_blocks.setdefault(first_auth, []).append(idx)

                for block_key, block_indices in auth_blocks.items():
                    if len(block_indices) < 2:
                        continue
                    for i_pos in range(len(block_indices)):
                        idx_i = block_indices[i_pos]
                        if duplicate_mask[idx_i]:
                            continue
                        auth_i = str(df.loc[idx_i, "AU"])
                        title_i = _normalize_title(str(df.loc[idx_i, title_col]))
                        if not auth_i or auth_i == "nan":
                            continue
                        for j_pos in range(i_pos + 1, len(block_indices)):
                            idx_j = block_indices[j_pos]
                            if duplicate_mask[idx_j]:
                                continue
                            auth_j = str(df.loc[idx_j, "AU"])
                            title_j = _normalize_title(str(df.loc[idx_j, title_col]))
                            if not auth_j or auth_j == "nan":
                                continue
                            auth_sim = fuzz.ratio(auth_i.lower(), auth_j.lower())
                            if auth_sim >= 85:
                                combined = (auth_sim + fuzz.ratio(title_i, title_j)) / 2
                                if combined >= threshold:
                                    duplicate_mask[idx_j] = True
                                    self._add_mapping(state, df, idx_j, idx_i,
                                                     "author_year_title", combined)

        n_duplicates = int(duplicate_mask.sum())
        df_clean = df[~duplicate_mask].reset_index(drop=True)

        state.master_dataset = df_clean
        state.stats.duplicates_found = n_duplicates
        state.stats.duplicates_removed = n_duplicates
        state.stats.after_dedup = len(df_clean)

        logger.info("[%s] Removed %d duplicates from %d records -> %d remaining",
                    self.NAME, n_duplicates, n_before, len(df_clean))

        state.log_stage(self.NAME, "complete",
                        f"Removed {n_duplicates} duplicates, {len(df_clean)} records remain",
                        {"before": n_before, "removed": n_duplicates,
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
