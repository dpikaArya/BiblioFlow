"""Agent 8: AI PRISMA Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from utils.ai_engine import LocalAIEngine
from prompts.template import prisma_narrative_prompt, PRISMA_NARRATIVE_SYSTEM

logger = logging.getLogger("aibef.prisma")


class PRISMAAgent:
    NAME = "PRISMAAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting PRISMA generation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning PRISMA generation")
        
        ai = LocalAIEngine(model_name=state.config.model_name)
        
        validated_df = state.validated_dataset
        if validated_df is None or validated_df.empty:
            logger.warning("[%s] No validated dataset, using cleaned dataset", self.NAME)
            validated_df = state.cleaned_dataset
        
        included_count = len(validated_df) if validated_df is not None else 0
        excluded_count = state.stats.duplicates_removed
        
        # Build PRISMA data
        prisma_data = {
            "title": "Systematic Review PRISMA Flow Diagram",
            "date_generated": datetime.now().isoformat(),
            "search_summary": {
                "databases_searched": list(state.stats.per_file.keys()),
                "total_identified": state.stats.total_imported,
                "files_imported": len(state.stats.per_file),
            },
            "records": {
                "imported": state.stats.total_imported,
                "per_database": dict(state.stats.per_file),
                "merged": state.stats.after_merge,
                "duplicates_identified": state.stats.duplicates_found,
                "after_dedup": state.stats.after_dedup,
                "after_cleaning": state.stats.after_cleaning,
                "included": included_count,
                "excluded_duplicates": state.stats.duplicates_removed,
            },
            "exclusion_criteria": [
                "Duplicate records (matched by DOI, UT, or title similarity)",
                "Records with missing mandatory fields (title, authors, year, journal)",
                "Non-English publications (if filtered)",
                "Non-article document types (if filtered)",
            ],
            "inclusion_criteria": [
                "Original research articles",
                "Records with complete metadata",
                "English language publications",
                "Published in peer-reviewed journals",
            ],
            "narrative": "",
            "study_selection_narrative": "",
        }
        
        # Generate AI narratives
        prompt = prisma_narrative_prompt(prisma_data["records"])
        narrative = ai.generate(prompt, system_prompt=PRISMA_NARRATIVE_SYSTEM)
        prisma_data["narrative"] = narrative
        
        selection_prompt = (
            f"Write a study selection narrative for a systematic review.\n"
            f"Total records identified: {state.stats.total_imported}\n"
            f"After deduplication: {state.stats.after_dedup}\n"
            f"After cleaning: {state.stats.after_cleaning}\n"
            f"Final included studies: {included_count}\n"
            f"Duplicates removed: {state.stats.duplicates_removed}\n"
            f"Databases used: {', '.join(state.stats.per_file.keys())}\n"
            f"Provide a concise 2-3 paragraph narrative."
        )
        selection_narrative = ai.generate(selection_prompt, system_prompt=PRISMA_NARRATIVE_SYSTEM)
        prisma_data["study_selection_narrative"] = selection_narrative
        
        # Create included/excluded studies data
        state.prisma_data.update(prisma_data)
        
        if validated_df is not None and not validated_df.empty:
            state.included_studies = validated_df.copy()
        
        # Screening log: all records with decisions
        screening_data = []
        if state.master_dataset is not None:
            for _, row in state.master_dataset.iterrows():
                screening_data.append({
                    "record_id": str(row.get("__record_id__", "")),
                    "title": str(row.get("TI", ""))[:100],
                    "source_file": str(row.get("__source_file__", "")),
                    "decision": "included",
                    "reason": "Passed all validation criteria"
                })
        
        # Mark excluded (duplicates)
        for dm in state.duplicate_mappings:
            screening_data.append({
                "record_id": dm.record_id,
                "title": "Duplicate - excluded",
                "source_file": dm.source_file,
                "decision": "excluded",
                "reason": f"Duplicate of {dm.duplicate_of} ({dm.match_type}, score={dm.similarity_score:.1f})"
            })
        
        state.screening_log = pd.DataFrame(screening_data)
        
        # Excluded studies
        excluded_data = []
        for dm in state.duplicate_mappings:
            excluded_data.append({
                "record_id": dm.record_id,
                "excluded_reason": f"Duplicate ({dm.match_type})",
                "duplicate_of": dm.duplicate_of,
                "similarity_score": dm.similarity_score,
                "source_file": dm.source_file,
            })
        state.excluded_studies = pd.DataFrame(excluded_data) if excluded_data else pd.DataFrame(
            columns=["record_id", "excluded_reason", "duplicate_of", "similarity_score", "source_file"]
        )
        
        logger.info("[%s] PRISMA generation complete: %d included, %d excluded",
                    self.NAME, included_count, len(excluded_data))
        
        state.log_stage(self.NAME, "complete",
                        f"PRISMA: {included_count} included, {len(excluded_data)} excluded",
                        {"included": included_count, "excluded": len(excluded_data)})
        
        return state
