"""Agent 6: Bibliometrix Compatibility Agent."""
from __future__ import annotations
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG, BIBLIOMETRIX_COLUMNS
from core.models import PipelineState
from core.exceptions import CompatibilityError

logger = logging.getLogger("aibef.compat")


class BibliometrixCompatAgent:
    NAME = "BibliometrixCompatAgent"
    
    # Fields that Bibliometrix expects
    REQUIRED_BIB_FIELDS = ["PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID", "AB", "C1", "RP", "PY", "UT"]
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting Bibliometrix compatibility", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning Bibliometrix compatibility check")
        
        df = state.cleaned_dataset.copy()
        if df is None or df.empty:
            raise CompatibilityError("No cleaned dataset for compatibility check")
        
        repairs = 0
        
        # 1. Ensure all required columns exist
        for col in self.REQUIRED_BIB_FIELDS:
            if col not in df.columns:
                df[col] = ""
                repairs += 1
                logger.info("[%s] Added missing column: %s", self.NAME, col)
        
        # 2. Ensure PT (Publication Type) is set
        if "PT" in df.columns:
            df["PT"] = df["PT"].replace("", "J")
            df["PT"] = df["PT"].fillna("J")
        
        # 3. Ensure LA (Language) is set
        if "LA" in df.columns:
            df["LA"] = df["LA"].replace("", "English")
            df["LA"] = df["LA"].fillna("English")
        
        # 4. Ensure DT (Document Type) is set
        if "DT" in df.columns:
            df["DT"] = df["DT"].replace("", "Article")
            df["DT"] = df["DT"].fillna("Article")
        
        # 5. Verify author format: semicolon-separated, "Last, Initials" format
        if "AU" in df.columns:
            df["AU"] = df["AU"].apply(self._ensure_author_format)
            repairs += 1
        
        # 6. Verify keyword format: semicolon-separated
        for kw_col in ["DE", "ID"]:
            if kw_col in df.columns:
                df[kw_col] = df[kw_col].apply(self._ensure_keyword_format)
        
        # 7. Ensure PY is numeric
        if "PY" in df.columns:
            df["PY"] = pd.to_numeric(df["PY"], errors="coerce").fillna(0).astype(int)
        
        # 8. Ensure UT exists (generate if missing)
        if "UT" in df.columns:
            df["UT"] = df.apply(self._ensure_ut, axis=1)
        
        # 9. Ensure DI format
        if "DI" in df.columns:
            df["DI"] = df["DI"].apply(lambda x: str(x).strip() if pd.notna(x) and str(x).strip() else "")
        
        # 10. Drop internal columns that would confuse Bibliometrix
        internal_cols = [c for c in df.columns if c.startswith("__")]
        df = df.drop(columns=internal_cols, errors="ignore")
        
        # 11. Ensure no duplicate column names
        seen = {}
        new_cols = []
        for col in df.columns:
            if col in seen:
                seen[col] += 1
                new_cols.append(f"{col}_{seen[col]}")
            else:
                seen[col] = 0
                new_cols.append(col)
        df.columns = new_cols
        
        # 12. Reorder to match Bibliometrix expected order where possible
        ordered_cols = [c for c in BIBLIOMETRIX_COLUMNS if c in df.columns]
        remaining = [c for c in df.columns if c not in ordered_cols]
        df = df[ordered_cols + remaining]
        
        state.bibliometrix_compatible = df
        logger.info("[%s] Compatibility check complete: %d columns, %d records, %d repairs",
                    self.NAME, len(df.columns), len(df), repairs)
        
        state.log_stage(self.NAME, "complete",
                        f"Bibliometrix compatibility: {len(df.columns)} columns, {repairs} repairs",
                        {"columns": list(df.columns), "repairs": repairs})
        
        return state
    
    def _ensure_author_format(self, text):
        if not isinstance(text, str) or not text.strip():
            return text
        authors = [a.strip() for a in re.split(r";\s*", text) if a.strip()]
        formatted = []
        for author in authors:
            if "," in author:
                formatted.append(author)
            else:
                parts = author.split()
                if len(parts) >= 2:
                    formatted.append(f"{parts[-1]}, {' '.join(parts[:-1])}")
                else:
                    formatted.append(author)
        return "; ".join(formatted)
    
    def _ensure_keyword_format(self, text):
        if not isinstance(text, str) or not text.strip():
            return ""
        text = text.replace("|", ";").replace(",", ";")
        text = re.sub(r";\s*;", ";", text)
        text = re.sub(r"\s*;\s*", "; ", text)
        return text.strip().rstrip(";")
    
    def _ensure_ut(self, row):
        ut = row.get("UT", "")
        if pd.isna(ut) or str(ut).strip() == "":
            di = str(row.get("DI", "")) if pd.notna(row.get("DI", "")) else ""
            if di:
                return f"WOS:{di.replace('/', '_')[:50]}"
            ti = str(row.get("TI", ""))[:20]
            return f"WOS:GEN{hash(ti) % 100000:06d}"
        return str(ut)
