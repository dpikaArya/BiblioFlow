# AI Bibliometric Engineering Framework (AIBEF) v2.0

A comprehensive, automated framework for bibliometric dataset engineering that transforms raw bibliometric exports from multiple databases into analysis-ready datasets certified for use with bibliometrix/R.

## Research Gap Addressed

Bibliometric analysis has become an essential methodology for systematic literature reviews, science mapping, and research trend identification. However, researchers face significant challenges:

### The Problem

1. **Multi-Database Fragmentation**: Researchers export bibliometric data from multiple sources (Web of Science, Scopus, PubMed, Dimensions, Lens, CrossRef, OpenAlex, Semantic Scholar), each with different formats, field naming conventions, and encoding standards.

2. **Manual Data Engineering**: Converting heterogeneous exports into a unified, analysis-ready format requires extensive manual work—field mapping, deduplication across databases, encoding fixes, and format validation.

3. **Silent Data Loss**: Without systematic validation, researchers often unknowingly lose records during format conversion, introduce encoding errors, or create field mismatches that compromise analysis validity.

4. **Reproducibility Crisis**: Manual preprocessing steps are rarely documented, making bibliometric analyses difficult to reproduce and verify.

5. **Tool Fragmentation**: Existing tools address individual steps (deduplication, format conversion) but not the complete pipeline from raw export to certified output.

### The Solution

AIBEF provides an **end-to-end automated pipeline** that:

- **Ingests** multi-database bibliometric exports (7+ formats supported)
- **Detects** database sources automatically using schema signatures
- **Merges** heterogeneous datasets into a unified schema
- **Deduplicates** across databases using multi-phase blocking (DOI, UT, title similarity, author+year)
- **Validates** metadata completeness and consistency
- **Cleans** and harmonizes fields using rule-based and AI-assisted methods
- **Certifies** the output through 3-layer R validation against the bibliometrix package
- **Launches** Biblioshiny for interactive analysis with a single command

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AIBEF Pipeline Architecture                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  Web of      │    │   Scopus     │    │  PubMed      │                   │
│  │  Science     │    │              │    │              │                   │
│  │  (.txt)      │    │  (.csv)      │    │  (.nbib)     │                   │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                   │                           │
│         └───────────────────┼───────────────────┘                           │
│                             ▼                                               │
│              ┌──────────────────────────┐                                   │
│              │   Agent 01: Import       │                                   │
│              │   - Auto-detect format   │                                   │
│              │   - Parse multi-format   │                                   │
│              │   - Normalize encoding   │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 02: Merge        │                                   │
│              │   - Schema harmonization │                                   │
│              │   - Field mapping        │                                   │
│              │   - Provenance tracking  │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 03: Deduplicate  │                                   │
│              │   - Phase 1: DOI match   │                                   │
│              │   - Phase 2: UT match    │                                   │
│              │   - Phase 3: Title sim   │                                   │
│              │   - Phase 4: Author+Year │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 04: Validate     │                                   │
│              │   - Field completeness   │                                   │
│              │   - Data type checks     │                                   │
│              │   - Consistency rules    │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 05: Clean        │                                   │
│              │   - Journal normalization│                                   │
│              │   - Keyword harmonization│                                   │
│              │   - Author standardize   │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 05b: Map Valid.  │                                   │
│              │   - Database field audit │                                   │
│              │   - Unmapped columns     │                                   │
│              │   - Metadata preservation│                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 06: Compat       │                                   │
│              │   - Bibliometrix schema  │                                   │
│              │   - Required fields      │                                   │
│              │   - Format compliance    │                                   │
│              └────────────┬─────────────┘                                   │
│                           ▼                                                 │
│              ┌──────────────────────────┐                                   │
│              │   Agent 07: R Validation │                                   │
│              │   - Layer 1: Structural  │                                   │
│              │   - Layer 2: Scientific  │─────── R/bibliometrix ──────────┐ │
│              │   - Layer 3: Reporting   │                                  │ │
│              └────────────┬─────────────┘                                  │ │
│                           ▼                                                │ │
│              ┌──────────────────────────┐                                  │ │
│              │   Agent 08: PRISMA       │                                  │ │
│              │   - Flow diagram         │                                  │ │
│              │   - Screening log        │                                  │ │
│              │   - Exclusion criteria   │                                  │ │
│              └────────────┬─────────────┘                                  │ │
│                           ▼                                                │ │
│              ┌──────────────────────────┐                                  │ │
│              │   Agent 09: Synchronize  │                                  │ │
│              │   - Record alignment     │                                  │ │
│              │   - Audit trail          │                                  │ │
│              │   - Integrity check      │                                  │ │
│              └────────────┬─────────────┘                                  │ │
│                           ▼                                                │ │
│              ┌──────────────────────────┐                                  │ │
│              │   Agent 10: Quality      │                                  │ │
│              │   - Statistical summary  │                                  │ │
│              │   - Coverage analysis    │                                  │ │
│              │   - Anomaly detection    │                                  │ │
│              └────────────┬─────────────┘                                  │ │
│                           ▼                                                │ │
│              ┌──────────────────────────┐                                  │ │
│              │   Agent 11: Export       │                                  │ │
│              │   - Multi-format output  │                                  │ │
│              │   - Certified .txt       │                                  │ │
│              │   - Reports (DOCX)       │                                  │ │
│              └────────────┬─────────────┘                                  │ │
│                           ▼                                                │ │
│              ┌──────────────────────────┐     ┌──────────────────────────┐ │ │
│              │  READY_FOR_BIBLIOSHINY   │────▶│  Biblioshiny Launch Mgr  │◄┘ │
│              │  - Certified dataset     │     │  - Pre-flight checks     │    │
│              │  - Validation reports    │     │  - R environment verify  │    │
│              │  - Launch command        │     │  - Browser launch        │    │
│              └──────────────────────────┘     └──────────────────────────┘    │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Multi-Database Support
- **Web of Science** (.txt): Full field support including UT, DOI, CR
- **Scopus** (.csv): EID, Scopus ID, affiliations
- **PubMed** (.nbib): PMID, PMCID, MeSH terms
- **Dimensions** (.csv): Publication ID, Fields of Research
- **Lens** (.csv): Lens ID, Scholarly AI
- **CrossRef** (.json): DOI-based metadata
- **OpenAlex** (.json): Open access indicators
- **Semantic Scholar** (.json): Citation contexts

### 2. Intelligent Deduplication
- **4-Phase Blocking Strategy**: DOI → UT → Title Similarity (85% threshold) → Author+Year
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

## Installation

```bash
# Clone the repository
git clone https://github.com/matrixflora/AI-Bibliometric-Engineering-Framework-v2.git
cd AI-Bibliometric-Engineering-Framework-v2

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

### Multi-Dataset Validation

```bash
# Validate multiple datasets across databases
python run_multidataset_validation.py
```

## Output Files

After successful pipeline execution, the following files are generated:

| File | Description |
|------|-------------|
| `Bibliometrix_Compatible.txt` | Certified dataset for bibliometrix (TAB-delimited) |
| `Bibliometrix_Compatible.xlsx` | Excel version of certified dataset |
| `Bibliometrix_Compatible.csv` | CSV version of certified dataset |
| `Bibliometrix_Validation_Report.docx` | 3-layer validation report |
| `Framework_Execution_Summary.docx` | Pipeline execution summary |
| `Certification_Report.docx` | Certification status report |
| `PRISMA_Report.docx` | PRISMA flow diagram report |
| `Included_Studies.xlsx` | Studies included in final review |
| `Excluded_Studies.xlsx` | Studies excluded with reasons |
| `Screening_Log.xlsx` | Complete screening audit trail |
| `Audit_Log.json` | Machine-readable execution log |
| `Provenance_Log.json` | Complete data provenance trail |

## Pipeline Statistics Example

```
============================================================
AIBEF PIPELINE RESULTS
============================================================
Total imported:   4277
After merge:     4277
Duplicates:      474
After cleaning:  3795
Final dataset:   3795
Synchronized:    YES
Bib compatible:  YES

READY_FOR_BIBLIOSHINY
============================================================
  Certified Dataset:  Bibliometrix_Compatible.txt
  Records:            3795
  Format:             TAB-delimited (.txt)
  Certification:      PASS (synchronized + bibliometrix compatible)

  The dataset is certified for direct use with Biblioshiny.
  Launch with: python main.py --launch-biblioshiny-only
============================================================
```

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
5. **Configuration_Cleanup_Report.docx**: Framework configuration changes

## Research Applications

AIBEF is designed for:

- **Systematic Literature Reviews**: Automated PRISMA-compliant screening
- **Science Mapping**: Co-authorship, co-citation, and bibliographic coupling analysis
- **Research Trend Analysis**: Temporal patterns and emerging topics
- **Cross-Database Studies**: Unified analysis across multiple bibliometric sources
- **Reproducible Research**: Complete audit trail and provenance tracking

## Citation

If you use AIBEF in your research, please cite:

```bibtex
@software{aibef2024,
  title={AI Bibliometric Engineering Framework (AIBEF)},
  year={2024},
  url={https://github.com/matrixflora/AI-Bibliometric-Engineering-Framework-v2}
}
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built on top of the [bibliometrix](https://www.bibliometrix.org/) R package
- Uses [python-docx](https://python-docx.readthedocs.io/) for report generation
- Implements [PRISMA 2020](http://www.prisma-statement.org/) guidelines for systematic reviews
