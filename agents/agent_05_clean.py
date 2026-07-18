"""Agent 5: Cleaning & Harmonization Agent."""
from __future__ import annotations
import logging
import re
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState, CleaningAction
from core.exceptions import CleaningError
from utils.ai_engine import LocalAIEngine
from prompts.template import (
    harmonization_prompt, keyword_normalization_prompt,
    author_disambiguation_prompt, institution_harmonization_prompt,
    journal_normalization_prompt
)

logger = logging.getLogger("aibef.clean")


class CleaningHarmonizationAgent:
    NAME = "CleaningHarmonizationAgent"

    # Known country/region mappings
    COUNTRY_FIXES = {
        "usa": "United States", "us": "United States", "u.s.a.": "United States",
        "u.s.": "United States", "uk": "United Kingdom", "u.k.": "United Kingdom",
        "england": "United Kingdom", "scotland": "United Kingdom",
        "wales": "United Kingdom", "peoples r china": "China",
        "pr china": "China", "china pr": "China", "s korea": "South Korea",
        "republic korea": "South Korea", "south-korea": "South Korea",
        "ussr": "Russia", "soviet union": "Russia",
    }

    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting cleaning & harmonization", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning cleaning & harmonization")

        df = state.master_dataset.copy()
        if df is None or df.empty:
            raise CleaningError("No dataset to clean")

        ai = LocalAIEngine(model_name=state.config.model_name)
        repairs = 0

        # 1. Standardize column names
        df.columns = [c.strip().upper() for c in df.columns]

        # 2. Fix encoding issues in text columns
        text_cols = ["TI", "AB", "SO", "AU", "AF", "DE", "ID", "C1"]
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].apply(self._fix_encoding)
                # Record some actions
                for idx in range(min(5, len(df))):
                    val = df.at[idx, col] if idx < len(df) else None
                    if pd.notna(val):
                        state.cleaning_actions.append(CleaningAction(
                            record_id=str(df.iloc[idx].get("__record_id__", idx)),
                            field=col, original_value="(original)",
                            cleaned_value=str(val)[:100], action_type="encoding_fix",
                            source_file=str(df.iloc[idx].get("__source_file__", "unknown"))
                        ))

        # 3. Normalize authors: ensure "Last, Initials" format
        if "AU" in df.columns:
            df["AU"] = df["AU"].apply(self._normalize_authors)
            repairs += 1

        # 4. Normalize year column
        if "PY" in df.columns:
            df["PY"] = pd.to_numeric(df["PY"], errors="coerce")
            df["PY"] = df["PY"].apply(
                lambda x: int(x) if pd.notna(x) and 1900 <= x <= 2030 else np.nan
            )
            repairs += 1

        # 5. Clean DOI
        if "DI" in df.columns:
            df["DI"] = df["DI"].apply(self._clean_doi)
            repairs += 1

        # 6. Normalize keyword separators
        for kw_col in ["DE", "ID"]:
            if kw_col in df.columns:
                df[kw_col] = df[kw_col].apply(
                    lambda x: self._normalize_semicolons(x) if pd.notna(x) else x
                )
                repairs += 1

        # 7. Country extraction from C1
        if "C1" in df.columns and "SC" not in df.columns:
            df["SC"] = df["C1"].apply(self._extract_countries)

        # 8. Standardize journal names using AI
        if "SO" in df.columns:
            journals = df["SO"].dropna().unique().tolist()
            if journals:
                prompt = journal_normalization_prompt(journals[:30])
                response = ai.generate(prompt)
                logger.info("[%s] Journal normalization AI response: %s",
                            self.NAME, response[:200])

        # 9. Keyword harmonization using AI
        if "DE" in df.columns:
            all_kws = []
            for val in df["DE"].dropna():
                if isinstance(val, str):
                    all_kws.extend([k.strip() for k in val.split(";") if k.strip()])
            if all_kws:
                prompt = keyword_normalization_prompt(list(set(all_kws))[:30])
                response = ai.generate(prompt)
                logger.info("[%s] Keyword harmonization AI response: %s",
                            self.NAME, response[:200])

        # 10. Fill NaN in string columns with empty
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].fillna("")

        # 11. Drop fully empty rows
        key_cols = [c for c in ["TI", "AU", "SO"] if c in df.columns]
        if key_cols:
            df = df.dropna(subset=key_cols, how="all")
            df = df[~(df[key_cols].eq("").all(axis=1))]

        df = df.reset_index(drop=True)
        state.cleaned_dataset = df
        state.stats.after_cleaning = len(df)
        state.stats.metadata_repairs = repairs
        state.stats.after_harmonization = len(df)

        logger.info("[%s] Cleaning complete: %d records, %d repairs",
                    self.NAME, len(df), repairs)

        state.log_stage(self.NAME, "complete",
                        f"Cleaned {len(df)} records, {repairs} repair actions",
                        {"records": len(df), "repairs": repairs})

        return state

    def _fix_encoding(self, text):
        if not isinstance(text, str):
            return text
        text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        text = re.sub(r"\u00e2\u0080[\u0090-\u009f]", "-", text)
        return text.strip()

    def _normalize_authors(self, text):
        if not isinstance(text, str) or not text.strip():
            return text
        authors = [a.strip() for a in text.split(";") if a.strip()]
        normalized = []
        for author in authors:
            if "," in author:
                parts = author.split(",", 1)
                last = parts[0].strip()
                initials = parts[1].strip() if len(parts) > 1 else ""
                normalized.append(f"{last}, {initials}")
            else:
                normalized.append(author)
        return "; ".join(normalized)

    def _clean_doi(self, doi):
        if not isinstance(doi, str) or not doi.strip():
            return doi
        doi = doi.strip()
        doi = re.sub(r"https?://doi\.org/", "", doi)
        doi = re.sub(r"https?://dx\.doi\.org/", "", doi)
        return doi

    def _normalize_semicolons(self, text):
        if not isinstance(text, str):
            return text
        text = re.sub(r"\s*;\s*", "; ", text)
        return text.strip().rstrip(";")

    def _extract_countries(self, address):
        if not isinstance(address, str):
            return ""
        parts = address.split(";")
        countries = set()
        for part in parts:
            country = part.split(",")[-1].strip() if "," in part else ""
            if country:
                country_lower = country.lower().strip()
                if country_lower in self.COUNTRY_FIXES:
                    country = self.COUNTRY_FIXES[country_lower]
                countries.add(country)
        return "; ".join(sorted(countries))
