"""Agent 4: Metadata Validation Agent."""
from __future__ import annotations
import logging
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState, ValidationIssue
from core.exceptions import ValidationError

logger = logging.getLogger("aibef.validate")


class MetadataValidationAgent:
    NAME = "MetadataValidationAgent"
    
    MANDATORY_FIELDS = ["TI", "AU", "SO", "PY", "DT"]
    RECOMMENDED_FIELDS = ["AB", "DE", "DI", "UT", "C1"]
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting metadata validation", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning metadata validation")
        
        df = state.master_dataset
        if df is None or df.empty:
            raise ValidationError("No dataset to validate")
        
        issues = []
        
        for idx in range(len(df)):
            record_id = str(df.iloc[idx].get("__record_id__", idx))
            source = str(df.iloc[idx].get("__source_file__", "unknown"))
            
            # Validate mandatory fields
            for field in self.MANDATORY_FIELDS:
                if field not in df.columns:
                    issues.append(ValidationIssue(
                        record_id=record_id, field=field,
                        issue_type="missing_column", severity="critical",
                        description=f"Mandatory field '{field}' missing from dataset",
                        source_file=source
                    ))
                    continue
                val = df.iloc[idx].get(field)
                if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                    issues.append(ValidationIssue(
                        record_id=record_id, field=field,
                        issue_type="missing_value", severity="high",
                        description=f"Mandatory field '{field}' is empty",
                        source_file=source
                    ))
            
            # Validate year
            if "PY" in df.columns:
                py_val = df.iloc[idx].get("PY")
                if pd.notna(py_val):
                    try:
                        year = int(float(py_val))
                        if year < 1900 or year > 2030:
                            issues.append(ValidationIssue(
                                record_id=record_id, field="PY",
                                issue_type="invalid_value", severity="medium",
                                description=f"Year {year} out of typical range",
                                source_file=source
                            ))
                    except (ValueError, TypeError):
                        issues.append(ValidationIssue(
                            record_id=record_id, field="PY",
                            issue_type="invalid_format", severity="high",
                            description=f"Cannot parse year: {py_val}",
                            source_file=source
                        ))
            
            # Validate DOI format
            if "DI" in df.columns:
                di_val = df.iloc[idx].get("DI")
                if pd.notna(di_val) and isinstance(di_val, str) and di_val.strip():
                    if not re.match(r"^10\.\d{4,}/", di_val):
                        issues.append(ValidationIssue(
                            record_id=record_id, field="DI",
                            issue_type="invalid_format", severity="medium",
                            description=f"DOI format suspicious: {di_val[:50]}",
                            source_file=source
                        ))
            
            # Validate title length
            if "TI" in df.columns:
                ti_val = df.iloc[idx].get("TI")
                if pd.notna(ti_val) and isinstance(ti_val, str):
                    if len(ti_val.strip()) < 10:
                        issues.append(ValidationIssue(
                            record_id=record_id, field="TI",
                            issue_type="short_title", severity="low",
                            description=f"Title suspiciously short ({len(ti_val.strip())} chars)",
                            source_file=source
                        ))
                    elif len(ti_val) > 500:
                        issues.append(ValidationIssue(
                            record_id=record_id, field="TI",
                            issue_type="long_title", severity="low",
                            description=f"Title unusually long ({len(ti_val)} chars)",
                            source_file=source
                        ))
            
            # Validate authors
            if "AU" in df.columns:
                au_val = df.iloc[idx].get("AU")
                if pd.notna(au_val) and isinstance(au_val, str):
                    authors = [a.strip() for a in au_val.split(";") if a.strip()]
                    if not authors:
                        issues.append(ValidationIssue(
                            record_id=record_id, field="AU",
                            issue_type="empty_authors", severity="high",
                            description="No authors parsed",
                            source_file=source
                        ))
            
            # Validate recommended fields (lower severity)
            for field in self.RECOMMENDED_FIELDS:
                if field in df.columns:
                    val = df.iloc[idx].get(field)
                    if pd.isna(val) or (isinstance(val, str) and not val.strip()):
                        issues.append(ValidationIssue(
                            record_id=record_id, field=field,
                            issue_type="missing_recommended", severity="low",
                            description=f"Recommended field '{field}' is empty",
                            source_file=source
                        ))
        
        state.validation_issues = issues
        state.stats.validation_issues = len(issues)
        
        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")
        
        logger.info("[%s] Found %d validation issues: %d critical, %d high, %d medium, %d low",
                    self.NAME, len(issues), critical, high, medium, low)
        
        state.log_stage(self.NAME, "complete",
                        f"Found {len(issues)} validation issues",
                        {"critical": critical, "high": high, "medium": medium, "low": low})
        
        return state
