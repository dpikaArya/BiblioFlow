"""Text utilities for parsing Web of Science files and normalizing text."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Optional
import pandas as pd


WOS_FIELD_TAGS = {
    "PT": "Publication Type",
    "AU": "Authors",
    "AF": "Author Full Names",
    "TI": "Title",
    "SO": "Source (Journal)",
    "LA": "Language",
    "DT": "Document Type",
    "DE": "Author Keywords",
    "ID": "Keywords Plus",
    "AB": "Abstract",
    "C1": "Author Addresses",
    "RP": "Reprint Addresses",
    "EM": "Email",
    "FU": "Funding",
    "FX": "Funding Text",
    "CR": "Cited References",
    "NR": "Cited Reference Count",
    "TC": "Times Cited",
    "Z9": "Total Times Cited Count",
    "U1": "Usage Count 180 Day",
    "U2": "Usage Count Since 2013",
    "PY": "Year",
    "PU": "Publisher",
    "PI": "Publisher City",
    "PA": "Publisher Address",
    "SN": "ISSN",
    "EI": "eISSN",
    "J9": "Abbreviated Journal",
    "JI": "Journal ID",
    "PD": "Publication Date",
    "VL": "Volume",
    "IS": "Issue",
    "BP": "Beginning Page",
    "EP": "Ending Page",
    "DI": "DOI",
    "PG": "Page Count",
    "WC": "Web of Science Categories",
    "SC": "Research Areas",
    "GA": "Document Delivery Number",
    "UT": "Accession Number",
    "DA": "Date Added",
}


class WoSParser:
    """Parse Web of Science plain text export files."""

    # Two-char field tag pattern at start of line (possibly with leading spaces)
    _TAG_RE = re.compile(r"^([A-Z]{2})\s+(.*)")
    _CONT_RE = re.compile(r"^\s{3,}(.*)")

    def __init__(self, file_path: Path, encoding: str = "utf-8"):
        self.file_path = file_path
        self.encoding = encoding
        self.source_name = file_path.stem

    def parse(self) -> pd.DataFrame:
        records = []
        current_record: dict[str, str] = {}
        current_tag: Optional[str] = None

        def _flush_record():
            nonlocal current_record, current_tag
            if current_record:
                current_record["__source_file__"] = self.source_name
                records.append(current_record)
                current_record = {}
                current_tag = None

        with open(self.file_path, "r", encoding=self.encoding, errors="replace") as f:
            for line in f:
                line = line.rstrip("\n\r")

                # Skip header lines
                if line.startswith("FN ") or line.startswith("VR "):
                    continue

                # Empty line = record separator
                if not line.strip():
                    _flush_record()
                    continue

                tag_match = self._TAG_RE.match(line)
                if tag_match:
                    current_tag = tag_match.group(1)
                    value = tag_match.group(2).strip()
                    if current_tag in current_record:
                        current_record[current_tag] += "; " + value
                    else:
                        current_record[current_tag] = value
                else:
                    cont_match = self._CONT_RE.match(line)
                    if cont_match and current_tag:
                        continuation = cont_match.group(1).strip()
                        if current_tag in current_record:
                            current_record[current_tag] += " " + continuation
                        else:
                            current_record[current_tag] = continuation

        _flush_record()

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        # Assign unique IDs
        df["__record_id__"] = [f"{self.source_name}_{i}" for i in range(len(df))]
        return df


class CSVParser:
    """Parse CSV files from various bibliographic databases (Dimensions, PubMed, Scopus, etc.)."""

    # Metadata lines to skip (non-record rows)
    _METADATA_PREFIXES = (
        "About the data",
        "#",
        "Note:",
        "This file",
        "Export date",
        "Created:",
        "Source:",
    )

    # Column name mappings: database-specific -> WoS-compatible
    COLUMN_MAPPINGS = {
        "dimensions": {
            "DOI": "DI",
            "Title": "TI",
            "Abstract": "AB",
            "Authors": "AU",
            "Source title": "SO",
            "PubYear": "PY",
            "Publication date": "PD",
            "Volume": "VL",
            "Issue": "IS",
            "Pagination": "BP",
            "Times cited": "TC",
            "Publication Type": "DT",
            "Publication ID": "__publication_id__",
            "PMID": "__pmid__",
            "PMCID": "__pmcid__",
            "Keywords": "DE",
            "Author Keywords": "DE",
            "MeSH terms": "ID",
            "Fields of Research (ANZSRC 2020)": "WC",
            "Authors Affiliations": "C1",
            "Corresponding Authors": "RP",
            "Authors (Raw Affiliation)": "__raw_affiliation__",
        },
        "pubmed": {
            "PMID": "UT",
            "Title": "TI",
            "Authors": "AU",
            "Journal/Book": "SO",
            "Publication Year": "PY",
            "DOI": "DI",
            "PMCID": "__pmcid__",
            "Citation": "CR",
            "First Author": "AF",
        },
        "scopus": {
            "DOI": "DI",
            "Title": "TI",
            "Abstract": "AB",
            "Authors": "AU",
            "Source title": "SO",
            "Year": "PY",
            "Volume": "VL",
            "Issue": "IS",
            "Art. No.": "BP",
            "Page start": "BP",
            "Page end": "EP",
            "Cited by": "TC",
            "Document Type": "DT",
            "Author Keywords": "DE",
            "Index Keywords": "ID",
            "Scopus ID": "__scopus_id__",
        },
    }

    def __init__(self, file_path: Path, encoding: str = "utf-8", delimiter: str = ","):
        self.file_path = file_path
        self.encoding = encoding
        self.delimiter = delimiter
        self.source_name = file_path.stem

    def parse(self) -> pd.DataFrame:
        try:
            # First pass: read without headers to detect metadata preamble
            preview = pd.read_csv(
                self.file_path,
                encoding=self.encoding,
                delimiter=self.delimiter,
                dtype=str,
                nrows=5,
                header=None,
                on_bad_lines="warn",
            )
            actual_header_row = 0
            if len(preview) > 0:
                first_row_vals = preview.iloc[0].astype(str).tolist()
                for val in first_row_vals:
                    val_stripped = val.strip()
                    if any(val_stripped.startswith(p) for p in self._METADATA_PREFIXES):
                        actual_header_row = 1
                        break

            # Second pass: read with correct header
            df = pd.read_csv(
                self.file_path,
                encoding=self.encoding,
                delimiter=self.delimiter,
                dtype=str,
                skiprows=actual_header_row,
                on_bad_lines="warn",
            )
        except Exception as e:
            raise ValueError(f"Failed to parse CSV {self.file_path}: {e}")

        if df.empty:
            return pd.DataFrame()

        # Remove metadata/pre-header rows that may appear before actual data
        # Some databases (e.g., Dimensions) prepend disclaimer rows
        df = self._remove_metadata_rows(df)

        # Detect database type and normalize column names
        db_type = self._detect_database_type(df)
        df = self._normalize_columns(df, db_type)

        # Assign source tracking
        df["__source_file__"] = self.source_name
        df["__record_id__"] = [f"{self.source_name}_{i}" for i in range(len(df))]
        return df

    def _detect_database_type(self, df: pd.DataFrame) -> str:
        """Detect database type from column names."""
        cols = set(df.columns)
        if "Publication ID" in cols and "Dimensions URL" in cols:
            return "dimensions"
        if "PMID" in cols and "NIHMS ID" in cols:
            return "pubmed"
        if "Scopus ID" in cols or "EID" in cols:
            return "scopus"
        return "unknown"

    def _normalize_columns(self, df: pd.DataFrame, db_type: str) -> pd.DataFrame:
        """Normalize column names to WoS-compatible format."""
        mapping = self.COLUMN_MAPPINGS.get(db_type, {})
        if not mapping:
            return df

        rename_map = {}
        for orig_col in df.columns:
            if orig_col in mapping:
                rename_map[orig_col] = mapping[orig_col]

        if rename_map:
            df = df.rename(columns=rename_map)
        return df

    def _remove_metadata_rows(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove leading non-data rows (metadata, disclaimers, etc.)."""
        # Check if first row looks like a header (all column names are strings, no NaN)
        first_row = df.iloc[0] if len(df) > 0 else None
        if first_row is None:
            return df

        # If first row values match column names exactly, it's a duplicate header row
        is_dup_header = all(
            str(first_row[col]).strip() == str(col).strip()
            for col in df.columns
            if pd.notna(first_row[col])
        )
        if is_dup_header:
            df = df.iloc[1:].reset_index(drop=True)
            return df

        # Check for metadata prefix patterns
        first_col_values = df.iloc[:5, 0].astype(str).tolist()
        for val in first_col_values:
            if any(val.strip().startswith(prefix) for prefix in self._METADATA_PREFIXES):
                # Find the actual header row (first row where all values are not metadata)
                for i, row in df.iterrows():
                    first_val = str(row.iloc[0]).strip()
                    if not any(first_val.startswith(p) for p in self._METADATA_PREFIXES):
                        df = df.iloc[i:].reset_index(drop=True)
                        break
                break

        return df


def normalize_text(text: str) -> str:
    """Basic text normalization."""
    if not isinstance(text, str):
        return ""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_field_tag(line: str) -> tuple[Optional[str], str]:
    """Extract WoS field tag and value from a line."""
    tag_match = WoSParser._TAG_RE.match(line.rstrip())
    if tag_match:
        return tag_match.group(1), tag_match.group(2).strip()
    return None, line.strip()
