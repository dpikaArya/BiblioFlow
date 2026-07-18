"""Central configuration for AIBEF framework."""
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Force R_HOME for rpy2
R_HOME = r"C:\Program Files\R\R-4.5.3"
os.environ["R_HOME"] = R_HOME

PROJECT_ROOT = Path(__file__).parent.parent
INPUT_DIR = Path.home() / "Desktop" / "CR"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
REQUIRED_TXT_COUNT = 6

BIBLIOMETRIX_COLUMNS = [
    "PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID", "AB",
    "C1", "RP", "EM", "FU", "FX", "CR", "NR", "TC", "Z9", "U1",
    "U2", "PY", "PU", "PI", "PA", "SN", "EI", "J9", "JI", "PD",
    "PY", "VL", "IS", "BP", "EP", "DI", "PG", "WC", "SC", "GA",
    "UT", "DA"
]

BIBLIOMETRIX_MANDATORY_FIELDS = [
    "AU", "TI", "SO", "PY", "DT", "DI", "DE", "ID", "CR", "C1", "RP", "TC", "LA",
]

DATABASE_FIELD_MAPPINGS: dict[str, dict[str, str]] = {
    "Web of Science": {
        "AU": "AU", "TI": "TI", "SO": "SO", "PY": "PY", "DT": "DT",
        "DE": "DE", "ID": "ID", "AB": "AB", "C1": "C1", "RP": "RP",
        "DI": "DI", "CR": "CR", "TC": "TC", "LA": "LA", "UT": "UT",
        "AF": "AF", "NR": "NR", "Z9": "Z9", "U1": "U1", "U2": "U2",
        "PU": "PU", "PI": "PI", "PA": "PA", "SN": "SN", "EI": "EI",
        "J9": "J9", "JI": "JI", "PD": "PD", "VL": "VL", "IS": "IS",
        "BP": "BP", "EP": "EP", "PG": "PG", "WC": "WC", "SC": "SC",
        "GA": "GA", "DA": "DA", "EM": "EM", "FU": "FU", "FX": "FX",
        "PT": "PT",
    },
    "Scopus": {
        "Title": "TI", "Authors": "AU", "Source": "SO", "Year": "PY",
        "Document Type": "DT", "Author Keywords": "DE", "Index Keywords": "ID",
        "Abstract": "AB", "Affiliations": "C1", "DOI": "DI",
        "Cited by": "TC", "Language": "LA", "Scopus ID": "UT",
        "EID": "UT", "ISSN": "SN", "eISSN": "EI",
        "Volume": "VL", "Issue": "IS", "Page start": "BP", "Page end": "EP",
        "Publisher Name": "PU",
    },
    "PubMed": {
        "Title": "TI", "Authors": "AU", "Journal/Book": "SO",
        "Publication Year": "PY", "DOI": "DI", "PMID": "UT",
        "PMCID": "UT", "Citation": "CR", "First Author": "AF",
    },
    "Dimensions": {
        "Title": "TI", "Authors": "AU", "Source title": "SO",
        "Year": "PY", "DOI": "DI", "Author Keywords": "DE",
    },
    "Lens": {
        "Title": "TI", "Authors": "AU", "DOI": "DI", "Year": "PY",
        "Source": "SO", "Volume": "VL", "Issue": "IS", "Pages": "BP",
        "Lens ID": "UT",
    },
    "CrossRef": {
        "Title": "TI", "DOI": "DI",
        "container-title": "SO", "published-print": "PY",
        "author": "AU", "type": "DT",
    },
    "OpenAlex": {
        "title": "TI", "doi": "DI", "display_name": "SO",
        "publication_year": "PY", "authorships": "AU",
        "type": "DT", "cited_by_count": "TC",
        "keywords": "DE",
    },
    "Semantic Scholar": {
        "title": "TI", "externalIds": "DI", "venue": "SO",
        "year": "PY", "authors": "AU", "abstract": "AB",
        "citationCount": "TC",
    },
}

MANDATORY_FIELDS_PER_DATABASE: dict[str, list[str]] = {
    "Web of Science": ["AU", "TI", "SO", "PY"],
    "Scopus": ["Title", "Authors", "DOI"],
    "PubMed": ["PMID", "Title", "DOI"],
    "Dimensions": ["Publication ID", "Title", "DOI", "PubYear"],
    "Lens": ["Lens ID", "Title"],
    "CrossRef": ["DOI", "Title"],
    "OpenAlex": ["Title"],
    "Semantic Scholar": ["Title"],
}


@dataclass
class MappingValidationConfig:
    """Configuration for Database Mapping Validation."""
    enabled: bool = True
    run_after_normalization: bool = True
    required_field_coverage: float = 95.0
    allow_missing_source_fields: bool = True
    report_unmapped_columns: bool = True
    preserve_metadata: bool = True


@dataclass
class AgentConfig:
    """Configuration for a single agent."""
    name: str
    enabled: bool = True
    max_retries: int = 3
    timeout_seconds: int = 300
    model_name: str = "Qwen/Qwen2-0.5B-Instruct"
    use_local_model: bool = True
    temperature: float = 0.3
    max_tokens: int = 512

@dataclass
class FrameworkConfig:
    """Master configuration for AIBEF."""
    input_dir: Path = field(default_factory=lambda: INPUT_DIR)
    output_dir: Path = field(default_factory=lambda: OUTPUT_DIR)
    log_dir: Path = field(default_factory=lambda: LOG_DIR)
    report_dir: Path = field(default_factory=lambda: REPORT_DIR)
    required_txt_count: int = REQUIRED_TXT_COUNT
    model_name: str = "Qwen/Qwen2-0.5B-Instruct"
    use_local_model: bool = True
    duplicate_threshold: float = 85.0
    title_similarity_threshold: float = 90.0
    encoding: str = "utf-8"
    batch_size: int = 64
    max_retries: int = 3
    strict_mode: bool = True
    
    agents: dict = field(default_factory=lambda: {
        "import": AgentConfig(name="Dataset Import Agent"),
        "merge": AgentConfig(name="Dataset Merge Agent"),
        "deduplicate": AgentConfig(name="Duplicate Detection Agent"),
        "validate": AgentConfig(name="Metadata Validation Agent"),
        "clean": AgentConfig(name="Cleaning & Harmonization Agent"),
        "mapping_validation": AgentConfig(name="Database Mapping Validation Agent"),
        "compat": AgentConfig(name="Bibliometrix Compatibility Agent"),
        "biblio_validate": AgentConfig(name="Bibliometrix Validation Agent"),
        "prisma": AgentConfig(name="AI PRISMA Agent"),
        "sync": AgentConfig(name="Synchronization Agent"),
        "quality": AgentConfig(name="Quality Validation Agent"),
        "export": AgentConfig(name="Export Agent"),
    })
    
    def __post_init__(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

CONFIG = FrameworkConfig()


SUPPORTED_FILE_EXTENSIONS = {
    ".txt", ".csv", ".ris", ".nbib", ".bib", ".bibtex",
    ".xml", ".end", ".enw", ".ciw",
}

SUPPORTED_DATABASES = [
    "Web of Science", "Scopus", "PubMed", "Dimensions",
    "Lens", "CrossRef", "OpenAlex", "Semantic Scholar",
]

DATABASE_SCHEMA_SIGNATURES: dict[str, list[str]] = {
    "Web of Science": [
        "FN ", "VR ", "PT ", "AU ", "TI ", "SO ", "UT ",
    ],
    "Scopus": [
        "Scopus ID", "EID", "Source", "Affiliations",
        "Publisher Name", "Index Keywords", "Chemicals",
    ],
    "PubMed": [
        "PMID", "PMCID", "NIHMS ID", "Medline",
    ],
    "Dimensions": [
        "Publication ID", "Dimensions URL", "Fields of Research",
        "Sustainable Development Goals", "RCR", "FCR",
    ],
    "Lens": [
        "Lens ID", "lens.org",
    ],
    "CrossRef": [
        "crossref", "Crossref",
    ],
    "OpenAlex": [
        "openalex", "OpenAlex", "cited_by_count",
    ],
    "Semantic Scholar": [
        "CorpusId", "Semantic Scholar",
    ],
}

DATABASE_COLUMN_PATTERNS: dict[str, list[str]] = {
    "Web of Science": [
        "PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID",
        "AB", "C1", "RP", "EM", "FU", "FX", "CR", "NR", "TC",
        "Z9", "U1", "U2", "PY", "PU", "PI", "PA", "SN", "EI",
        "J9", "JI", "PD", "VL", "IS", "BP", "EP", "DI", "PG",
        "WC", "SC", "GA", "UT", "DA",
    ],
    "Scopus": [
        "Scopus ID", "EID", "Title", "Authors", "Source",
        "Publisher Name", "ISSN", "eISSN", "DOI", "Year",
        "Abstract", "Affiliations", "Index Keywords",
    ],
    "PubMed": [
        "PMID", "Title", "Authors", "Citation", "First Author",
        "Journal/Book", "Publication Year", "Create Date",
        "PMCID", "NIHMS ID", "DOI",
    ],
    "Dimensions": [
        "Publication ID", "DOI", "Title", "Abstract",
        "Source title/Anthology title", "PubYear", "Volume",
        "Issue", "Pagination", "Authors", "Dimensions URL",
        "Times cited", "Cited references",
        "Authors Affiliations - Name of Research organization",
        "Authors Affiliations - Country of Research organization",
    ],
    "Lens": [
        "Lens ID", "Title", "Authors", "DOI", "Year",
        "Source", "Volume", "Issue", "Pages",
    ],
}


@dataclass
class DatabaseDiscoveryConfig:
    """Configuration for the Multi-Database Discovery Engine."""
    enabled: bool = True
    recursive_scan: bool = True
    minimum_detection_confidence: float = 0.95
    validate_schema_before_grouping: bool = True
    allow_cross_database_merge: bool = False
    cross_database_harmonization: bool = False
    preserve_provenance: bool = True
    generate_group_reports: bool = True
    generate_global_summary: bool = True
    low_confidence_action: str = "skip"
    supported_extensions: list = field(
        default_factory=lambda: list(SUPPORTED_FILE_EXTENSIONS)
    )
    discovery_output_dir: Optional[Path] = None
    group_output_base: Optional[Path] = None

    def __post_init__(self):
        if self.low_confidence_action not in ("skip", "ask_user", "abort"):
            self.low_confidence_action = "skip"


@dataclass
class BiblioshinyLaunchConfig:
    """Configuration for the Biblioshiny Launch Manager."""
    enabled: bool = True
    require_certification: bool = True
    certification_status: str = "READY_FOR_BIBLIOSHINY"
    use_external_r_process: bool = True
    auto_open_browser: bool = True
    allow_uncertified_launch: bool = False
    r_home: str = R_HOME
    rscript_path: str = r"C:\Program Files\R\R-4.5.3\bin\Rscript.exe"
    certified_dataset_name: str = "Bibliometrix_Compatible.txt"
    launch_timeout_seconds: int = 30
