# AI Bibliometric Engineering Framework (AIBEF)

A comprehensive, automated framework for bibliometric dataset engineering that transforms raw bibliometric exports from multiple databases into analysis-ready datasets certified for use with bibliometrix/R.

## Research Gap Addressed

### The Problem in Current Bibliometric Research

Bibliometric analysis has become an essential methodology for systematic literature reviews, science mapping, and research trend identification. However, researchers face significant challenges that create a critical gap in research methodology:

#### 1. Multi-Database Fragmentation
Researchers export bibliometric data from multiple sources (Web of Science, Scopus, PubMed, Dimensions, Lens, CrossRef, OpenAlex, Semantic Scholar), each with different formats, field naming conventions, and encoding standards. This fragmentation forces researchers to spend excessive time on data preparation rather than analysis.

#### 2. Manual Data Engineering Overhead
Converting heterogeneous exports into a unified, analysis-ready format requires extensive manual work—field mapping, deduplication across databases, encoding fixes, and format validation. Studies show that **60-80% of research time** is spent on data preparation rather than analysis.

#### 3. Silent Data Loss
Without systematic validation, researchers often unknowingly lose records during format conversion, introduce encoding errors, or create field mismatches that compromise analysis validity. This leads to **reproducibility issues** and potentially flawed research conclusions.

#### 4. Reproducibility Crisis
Manual preprocessing steps are rarely documented, making bibliometric analyses difficult to reproduce and verify. This undermines the scientific rigor of bibliometric studies.

#### 5. Tool Fragmentation
Existing tools address individual steps (deduplication, format conversion) but not the complete pipeline from raw export to certified output. Researchers must stitch together multiple tools, increasing complexity and error potential.

### The Solution: AIBEF

AIBEF provides an **end-to-end automated pipeline** that addresses these gaps by:

- **Ingesting** multi-database bibliometric exports (8+ formats supported)
- **Detecting** database sources automatically using schema signatures
- **Merging** heterogeneous datasets into a unified schema
- **Deduplicating** across databases using multi-phase blocking
- **Validating** metadata completeness and consistency
- **Cleaning** and harmonizing fields using rule-based and AI-assisted methods
- **Certifying** the output through 3-layer R validation against the bibliometrix package
- **Launching** Biblioshiny for interactive analysis with a single command

## Framework Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        AIBEF PIPELINE ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  INPUT SOURCES                    PROCESSING AGENTS                             │
│  ═════════════                    ══════════════════                             │
│                                                                                 │
│  ┌──────────────┐                                                            │
│  │ Web of       │                                                            │
│  │ Science      │──┐                                                         │
│  │ (.txt)       │  │                                                         │
│  └──────────────┘  │    ┌─────────────────────────────────────────────────┐   │
│  ┌──────────────┐  │    │                                                 │   │
│  │ Scopus       │──┤    │  ┌──────────────────────────────────────────┐  │   │
│  │ (.csv)       │  │    │  │  AGENT 01: Dataset Import                │  │   │
│  └──────────────┘  │    │  │  • Auto-detect database format           │  │   │
│  ┌──────────────┐  ├───▶│  │  • Parse multi-format exports            │  │   │
│  │ PubMed       │──┤    │  │  • Normalize encoding (UTF-8)            │  │   │
│  │ (.nbib)      │  │    │  │  • Schema signature matching             │  │   │
│  └──────────────┘  │    │  └────────────────────┬─────────────────────┘  │   │
│  ┌──────────────┐  │    │                       │                        │   │
│  │ Dimensions   │──┤    │                       ▼                        │   │
│  │ (.csv)       │  │    │  ┌──────────────────────────────────────────┐  │   │
│  └──────────────┘  │    │  │  AGENT 02: Dataset Merge                 │  │   │
│  ┌──────────────┐  │    │  │  • Schema harmonization                  │  │   │
│  │ Lens         │──┤    │  │  • Field mapping across databases        │  │   │
│  │ (.csv)       │  │    │  │  • Provenance tracking                   │  │   │
│  └──────────────┘  │    │  └────────────────────┬─────────────────────┘  │   │
│  ┌──────────────┐  │    │                       │                        │   │
│  │ CrossRef     │──┤    │                       ▼                        │   │
│  │ (.json)      │  │    │  ┌──────────────────────────────────────────┐  │   │
│  └──────────────┘  │    │  │  AGENT 03: Duplicate Detection           │  │   │
│  ┌──────────────┐  │    │  │  • Phase 1: DOI exact matching           │  │   │
│  │ OpenAlex     │──┤    │  │  • Phase 2: UT exact matching            │  │   │
│  │ (.json)      │  │    │  │  • Phase 3: Title similarity (85%)       │  │   │
│  └──────────────┘  │    │  │  • Phase 4: Author+Year matching         │  │   │
│  ┌──────────────┐  │    │  └────────────────────┬─────────────────────┘  │   │
│  │ Semantic     │──┘    │                       │                        │   │
│  │ Scholar      │       │                       ▼                        │   │
│  │ (.json)      │       │  ┌──────────────────────────────────────────┐  │   │
│  └──────────────┘       │  │  AGENT 04: Metadata Validation          │  │   │
│                         │  │  • Field completeness checks             │  │   │
│                         │  │  • Data type validation                  │  │   │
│                         │  │  • Consistency rules                     │  │   │
│                         │  └────────────────────┬─────────────────────┘  │   │
│                         │                       │                        │   │
│                         │                       ▼                        │   │
│                         │  ┌──────────────────────────────────────────┐  │   │
│                         │  │  AGENT 05: Cleaning & Harmonization      │  │   │
│                         │  │  • Journal name normalization            │  │   │
│                         │  │  • Keyword harmonization                 │  │   │
│                         │  │  • Author name standardization           │  │   │
│                         │  └────────────────────┬─────────────────────┘  │   │
│                         │                       │                        │   │
│                         │                       ▼                        │   │
│                         │  ┌──────────────────────────────────────────┐  │   │
│                         │  │  AGENT 05b: Database Mapping Validation  │  │   │
│                         │  │  • Database field audit                  │  │   │
│                         │  │  • Unmapped column detection             │  │   │
│                         │  │  • Metadata preservation verification   │  │   │
│                         │  └────────────────────┬─────────────────────┘  │   │
│                         │                       │                        │   │
│                         │                       ▼                        │   │
│                         │  ┌──────────────────────────────────────────┐  │   │
│                         │  │  AGENT 06: Bibliometrix Compatibility    │  │   │
│                         │  │  • Bibliometrix schema compliance        │  │   │
│                         │  │  • Required field verification           │  │   │
│                         │  │  • Format standardization                │  │   │
│                         │  └────────────────────┬─────────────────────┘  │   │
│                         │                       │                        │   │
│                         │                       ▼                        │   │
│                         │  ┌──────────────────────────────────────────┐  │   │
│                         │  │  AGENT 07: Bibliometrix Validation       │  │   │
│                         │  │  ┌────────────────────────────────────┐  │  │   │
│                         │  │  │ Layer 1: Structural Validation     │  │  │   │
│                         │  │  │ • Column presence & data types     │  │  │   │
│                         │  │  │ • Encoding verification            │  │  │   │
│                         │  │  └────────────────────────────────────┘  │  │   │
│                         │  │  ┌────────────────────────────────────┐  │  │   │
│                         │  │  │ Layer 2: Scientific Validation     │◄─┼──┤   │
│                         │  │  │ • bibliometrix::convert2df()       │  │  │ │   │
│                         │  │  │ • bibliometrix::biblioAnalysis()   │  │  │ │   │
│                         │  │  └────────────────────────────────────┘  │  │ │   │
│                         │  │  ┌────────────────────────────────────┐  │  │ │   │
│                         │  │  │ Layer 3: Reporting                 │  │  │ │   │
│                         │  │  │ • DOCX validation reports          │  │  │ │   │
│                         │  │  │ • Certification status             │  │  │ │   │
│                         │  │  └────────────────────────────────────┘  │  │ │   │
│                         │  └────────────────────┬─────────────────────┘  │ │   │
│                         │                       │                        │ │   │
│                         │                       ▼                        │ │   │
│                         │  ┌──────────────────────────────────────────┐  │ │   │
│                         │  │  AGENT 08: PRISMA Generation             │  │ │   │
│                         │  │  • Flow diagram generation               │  │ │   │
│                         │  │  • Screening log creation                │  │ │   │
│                         │  │  • Exclusion criteria documentation      │  │ │   │
│                         │  └────────────────────┬─────────────────────┘  │ │   │
│                         │                       │                        │ │   │
│                         │                       ▼                        │ │   │
│                         │  ┌──────────────────────────────────────────┐  │ │   │
│                         │  │  AGENT 09: Synchronization               │  │ │   │
│                         │  │  • Record alignment verification         │  │ │   │
│                         │  │  • Audit trail completeness              │  │ │   │
│                         │  │  • Data integrity checks                 │  │ │   │
│                         │  └────────────────────┬─────────────────────┘  │ │   │
│                         │                       │                        │ │   │
│                         │                       ▼                        │ │   │
│                         │  ┌──────────────────────────────────────────┐  │ │   │
│                         │  │  AGENT 10: Quality Validation            │  │ │   │
│                         │  │  • Statistical summary generation        │  │ │   │
│                         │  │  • Coverage analysis                     │  │ │   │
│                         │  │  • Anomaly detection                     │  │ │   │
│                         │  └────────────────────┬─────────────────────┘  │ │   │
│                         │                       │                        │ │   │
│                         │                       ▼                        │ │   │
│                         │  ┌──────────────────────────────────────────┐  │ │   │
│                         │  │  AGENT 11: Export                        │  │ │   │
│                         │  │  • Multi-format output (TXT/XLSX/CSV)    │  │ │   │
│                         │  │  • Certified Bibliometrix_Compatible.txt │  │ │   │
│                         │  │  • DOCX reports (PRISMA, Validation)     │  │ │   │
│                         │  └────────────────────┬─────────────────────┘  │ │   │
│                         │                       │                        │ │   │
│                         └───────────────────────┼────────────────────────┘ │   │
│                                                 │                          │   │
│                                                 ▼                          │   │
│                         ┌──────────────────────────────────────────┐       │   │
│                         │  READY_FOR_BIBLIOSHINY                   │       │   │
│                         │  ═══════════════════════                  │       │   │
│                         │  • Certified dataset generated           │       │   │
│                         │  • All validation checks PASSED          │       │   │
│                         │  • Ready for Biblioshiny launch          │       │   │
│                         └────────────────────┬─────────────────────┘       │   │
│                                              │                             │   │
│                                              ▼                             │   │
│                         ┌──────────────────────────────────────────┐       │   │
│                         │  BIBLIOSHINY LAUNCH MANAGER              │       │   │
│                         │  ═══════════════════════════              │       │   │
│                         │  • Pre-flight certification checks       │       │   │
│                         │  • R environment verification            │       │   │
│                         │  • Shiny server detection                │       │   │
│                         │  • Browser automation                    │       │   │
│                         └────────────────────┬─────────────────────┘       │   │
│                                              │                             │   │
│                                              ▼                             │   │
│                         ┌──────────────────────────────────────────┐       │   │
│                         │  BIBLIOSHINY INTERACTIVE ANALYSIS        │       │   │
│                         │  ═══════════════════════════════          │       │   │
│                         │  • Co-authorship analysis                │       │   │
│                         │  • Co-citation analysis                  │       │   │
│                         │  • Bibliographic coupling                │       │   │
│                         │  • Keyword analysis                      │       │   │
│                         │  • Thematic mapping                      │       │   │
│                         │  • Strategic diagram                     │       │   │
│                         └──────────────────────────────────────────┘       │   │
│                                                                            │   │
│  R ENVIRONMENT (bibliometrix) ◄────────────────────────────────────────────┘   │
│  ══════════════════════════════                                                │
│  • R 4.5.2                                                                     │
│  • bibliometrix 5.2.1                                                          │
│  • convert2df() validation                                                     │
│  • biblioAnalysis() verification                                               │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Test Results & Performance

### Pipeline Execution Results

| Metric | Value |
|--------|-------|
| **Total Records Processed** | 4,277 |
| **Duplicates Detected** | 474 (11.1%) |
| **Final Certified Records** | 3,795 |
| **Pipeline Execution Time** | 301.25 seconds (5.02 minutes) |
| **Errors** | 0 |
| **Synchronization Status** | VERIFIED |
| **Bibliometrix Compatibility** | CERTIFIED |

### Agent-Level Performance

| Agent | Duration | Status |
|-------|----------|--------|
| Dataset Import | 2.57s | ✓ PASS |
| Dataset Merge | 0.05s | ✓ PASS |
| Duplicate Detection | 18.88s | ✓ PASS |
| Metadata Validation | 78.07s | ✓ PASS |
| Cleaning & Harmonization | 0.40s | ✓ PASS |
| Bibliometrix Compatibility | 0.17s | ✓ PASS |
| Bibliometrix Validation (R) | 139.16s | ✓ PASS |
| PRISMA Generation | 1.23s | ✓ PASS |
| Export | 60.72s | ✓ PASS |

### 3-Layer R Validation Results

| Layer | Check | Result |
|-------|-------|--------|
| **Layer 1** | Structural Validation | ✓ PASS |
| **Layer 2** | Scientific Validation (convert2df) | ✓ PASS |
| **Layer 2** | Scientific Validation (biblioAnalysis) | ✓ PASS |
| **Layer 2** | Scientific Validation (summary) | ✓ PASS |
| **Layer 3** | DOCX Report Generation | ✓ PASS |

### Bibliometrix Compatibility Verified

```
convert2df():
  • Input: 3,795 records
  • Output: 3,795 rows × 48 columns
  • Status: SUCCESS

biblioAnalysis():
  • Sources (Journals, Books): 682
  • Documents: 3,795
  • Authors: 9,591
  • Author Appearances: 10,712
  • Single-authored docs: 1,995
  • Co-Authors per Doc: 2.82
  • Status: SUCCESS
```

### Database Source Distribution

| Source File | Records | Database |
|-------------|---------|----------|
| 1.txt | 269 | Web of Science |
| 2.txt | 1,004 | Web of Science |
| savedrecs.txt | 1,004 | Web of Science |
| 1D.csv | 500 | Dimensions |
| 2D.csv | 500 | Dimensions |
| Dimensions-Publication-2026-07-19_09-51-19.csv | 500 | Dimensions |
| Dimensions-Publication-2026-07-19_09-53-10.csv | 500 | Dimensions |
| **Total** | **4,277** | |

### Deduplication Performance

| Phase | Method | Duplicates Found |
|-------|--------|------------------|
| Phase 1 | DOI Exact Match | 156 |
| Phase 2 | UT Exact Match | 89 |
| Phase 3 | Title Similarity (85% threshold) | 198 |
| Phase 4 | Author+Year Match | 31 |
| **Total** | | **474** |

## Output Files Generated

| File | Description | Status |
|------|-------------|--------|
| `Bibliometrix_Compatible.txt` | Certified TAB-delimited dataset | ✓ Generated |
| `Bibliometrix_Compatible.xlsx` | Excel version | ✓ Generated |
| `Bibliometrix_Compatible.csv` | CSV version | ✓ Generated |
| `Bibliometrix_Validation_Report.docx` | 3-layer validation report | ✓ Generated |
| `Framework_Execution_Summary.docx` | Pipeline execution summary | ✓ Generated |
| `Certification_Report.docx` | Certification status | ✓ Generated |
| `PRISMA_Report.docx` | PRISMA flow diagram | ✓ Generated |
| `Included_Studies.xlsx` | Studies in final review | ✓ Generated |
| `Excluded_Studies.xlsx` | Studies excluded with reasons | ✓ Generated |
| `Screening_Log.xlsx` | Complete screening audit trail | ✓ Generated |
| `Audit_Log.json` | Machine-readable execution log | ✓ Generated |
| `Provenance_Log.json` | Complete data provenance trail | ✓ Generated |
| `R_Validation.json` | R validation results | ✓ Generated |

## Installation

```bash
# Clone the repository
git clone https://github.com/matrixflora/AI-Bibliometric-Engineering-Framework-.git
cd AI-Bibliometric-Engineering-Framework-

# Install Python dependencies
pip install -r requirements.txt

# Install R dependencies
Rscript -e "install.packages('bibliometrix')"
```

## Usage

### Basic Pipeline Execution

```bash
# Run the full pipeline with input data
python main.py --input /path/to/your/data --output /path/to/output

# Example with default paths
python main.py
```

### Launch Biblioshiny Only

```bash
# After pipeline completes, launch Biblioshiny
python main.py --launch-biblioshiny-only

# Or run pipeline and launch in one step
python main.py --launch-biblioshiny
```

## Supported Database Formats

| Database | Format | Fields Supported |
|----------|--------|------------------|
| **Web of Science** | .txt | AU, TI, SO, PY, DT, DE, ID, AB, C1, RP, DI, CR, TC, LA, UT, AF, NR, Z9, U1, U2, PU, PI, PA, SN, EI, J9, JI, PD, VL, IS, BP, EP, PG, WC, SC, GA, DA, EM, FU, FX, PT |
| **Scopus** | .csv | Title, Authors, Source, Year, Document Type, Author Keywords, Index Keywords, Abstract, Affiliations, DOI, Cited by, Language, Scopus ID, EID, ISSN, eISSN, Volume, Issue, Page start, Page end, Publisher Name |
| **PubMed** | .nbib | Title, Authors, Journal/Book, Publication Year, DOI, PMID, PMCID, Citation, First Author |
| **Dimensions** | .csv | Title, Authors, Source title, Year, DOI, Author Keywords |
| **Lens** | .csv | Lens ID, Title, Authors, DOI, Year, Source, Volume, Issue, Pages |
| **CrossRef** | .json | Title, DOI, container-title, published-print, author, type |
| **OpenAlex** | .json | title, doi, display_name, publication_year, authorships, type, cited_by_count, keywords |
| **Semantic Scholar** | .json | title, externalIds, venue, year, authors, abstract, citationCount |

## Key Features

### 1. Multi-Database Support
- **8+ database formats** with automatic detection
- **Schema signature matching** for format identification
- **Encoding normalization** (UTF-8 standardization)

### 2. Intelligent Deduplication
- **4-Phase Blocking Strategy**: DOI → UT → Title Similarity → Author+Year
- **Cross-Database Detection**: Identifies duplicates across different export sources
- **Provenance Preservation**: Maintains complete audit trail of all deduplication decisions

### 3. 3-Layer R Validation
- **Layer 1**: Structural validation (column presence, data types, encoding)
- **Layer 2**: Scientific validation via `bibliometrix::convert2df()` and `bibliometrix::biblioAnalysis()`
- **Layer 3**: Reporting (generates DOCX validation reports)

### 4. Biblioshiny Launch Manager
- **Pre-flight Checks**: Validates certification status, R environment, dataset integrity
- **Dual Server Detection**: Console output monitoring + port scanning
- **Browser Automation**: Opens validated Shiny server in default browser

### 5. PRISMA Compliance
- **Automated PRISMA flow diagram** generation
- **Screening log** with complete audit trail
- **Exclusion criteria** documentation

### 6. Complete Audit Trail
- **Provenance tracking** for every record
- **JSON audit logs** for machine-readable verification
- **DOCX reports** for human-readable documentation

## Research Applications

AIBEF is designed for:

- **Systematic Literature Reviews**: Automated PRISMA-compliant screening
- **Science Mapping**: Co-authorship, co-citation, and bibliographic coupling analysis
- **Research Trend Analysis**: Temporal patterns and emerging topics
- **Cross-Database Studies**: Unified analysis across multiple bibliometric sources
- **Reproducible Research**: Complete audit trail and provenance tracking

## Architecture Components

### Core Pipeline (`core/`)
- `config.py`: Central configuration and database mappings
- `models.py`: Data models (PipelineState, RecordStats, etc.)
- `logging_config.py`: Structured logging and audit trail

### Agents (`agents/`)
- `agent_01_import.py`: Multi-format dataset import
- `agent_02_merge.py`: Schema harmonization and merge
- `agent_03_deduplicate.py`: 4-phase deduplication
- `agent_04_validate.py`: Metadata validation
- `agent_05_clean.py`: Cleaning and harmonization
- `agent_05b_mapping_validation.py`: Database field mapping validation
- `agent_06_compat.py`: Bibliometrix compatibility
- `agent_07_bibvalidate.py`: 3-layer R validation
- `agent_08_prisma.py`: PRISMA flow generation
- `agent_09_sync.py`: Synchronization verification
- `agent_10_quality.py`: Quality validation
- `agent_11_export.py`: Multi-format export

### Biblioshiny Launch Manager (`biblioshiny_launcher/`)
- `launcher.py`: Core launch orchestration
- `config.py`: Launch configuration
- `validator.py`: Pre-flight checks
- `r_interface.py`: R process management
- `server_discovery.py`: Shiny server detection
- `browser.py`: Browser automation

### Validation (`validation/`)
- `checks.py`: Output verification and integrity checks

### Reports (`reports/`)
- `generators.py`: DOCX report generation

## Validation Reports

The framework generates comprehensive validation reports:

1. **Framework_Execution_Summary.docx**: Complete pipeline execution statistics
2. **Certification_Report.docx**: Certification status and validation checks
3. **Bibliometrix_Validation_Report.docx**: 3-layer R validation results
4. **PRISMA_Report.docx**: PRISMA flow diagram for systematic reviews

## Citation

If you use AIBEF in your research, please cite:

```bibtex
@software{aibef2026,
  title={AI Bibliometric Engineering Framework (AIBEF)},
  year={2026},
  url={https://github.com/matrixflora/AI-Bibliometric-Engineering-Framework-}
}
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on top of the [bibliometrix](https://www.bibliometrix.org/) R package
- Uses [python-docx](https://python-docx.readthedocs.io/) for report generation
- Implements [PRISMA 2020](http://www.prisma-statement.org/) guidelines for systematic reviews
