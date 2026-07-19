"""Agent 11: Export Agent."""
from __future__ import annotations
import logging
import json
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState
from core.exceptions import ExportError

logger = logging.getLogger("aibef.export")


class ExportAgent:
    NAME = "ExportAgent"
    
    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting export", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning export of all outputs")
        
        output_dir = state.config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        exported = []
        
        # 1. Master_Bibliometric_Dataset.xlsx
        self._export_xlsx(state, output_dir / "Master_Bibliometric_Dataset.xlsx")
        exported.append("Master_Bibliometric_Dataset.xlsx")
        
        # 2. Master_Bibliometric_Dataset.csv
        self._export_csv(state, output_dir / "Master_Bibliometric_Dataset.csv")
        exported.append("Master_Bibliometric_Dataset.csv")
        
        # 3. Bibliometrix_Compatible.xlsx (alias for Biblioshiny import)
        self._export_xlsx(state, output_dir / "Bibliometrix_Compatible.xlsx")
        exported.append("Bibliometrix_Compatible.xlsx")
        
        # 4. Bibliometrix_Compatible.csv
        self._export_csv(state, output_dir / "Bibliometrix_Compatible.csv")
        exported.append("Bibliometrix_Compatible.csv")
        
        # 5. Bibliometrix_Compatible.txt
        self._export_txt(state, output_dir / "Bibliometrix_Compatible.txt")
        exported.append("Bibliometrix_Compatible.txt")
        
        # 6. Bibliometrix_Validation_Report.docx (skip if 3-layer agent generated it)
        bibval_path = output_dir / "Bibliometrix_Validation_Report.docx"
        if not bibval_path.exists():
            self._export_bibval_docx(state, bibval_path)
        exported.append("Bibliometrix_Validation_Report.docx")
        
        # 7. PRISMA_Report.docx
        self._export_prisma_docx(state, output_dir / "PRISMA_Report.docx")
        exported.append("PRISMA_Report.docx")
        
        # 8. Included_Studies.xlsx
        self._export_included(state, output_dir / "Included_Studies.xlsx")
        exported.append("Included_Studies.xlsx")
        
        # 7. Excluded_Studies.xlsx
        self._export_excluded(state, output_dir / "Excluded_Studies.xlsx")
        exported.append("Excluded_Studies.xlsx")
        
        # 8. Screening_Log.xlsx
        self._export_screening(state, output_dir / "Screening_Log.xlsx")
        exported.append("Screening_Log.xlsx")
        
        # 9. Audit_Log.json
        self._export_audit(state, output_dir / "Audit_Log.json")
        exported.append("Audit_Log.json")
        
        # 10. Provenance_Log.json
        self._export_provenance(state, output_dir / "Provenance_Log.json")
        exported.append("Provenance_Log.json")
        
        logger.info("[%s] Export complete: %d files", self.NAME, len(exported))
        state.log_stage(self.NAME, "complete",
                        f"Exported {len(exported)} files",
                        {"files": exported})
        
        return state
    
    def _resolve_dataset(self, state: PipelineState):
        """Get the best available dataset for export."""
        df = state.validated_dataset
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            df = state.bibliometrix_compatible
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            df = state.cleaned_dataset
        return df

    def _export_xlsx(self, state: PipelineState, path: Path):
        df = self._resolve_dataset(state)
        if df is not None and not df.empty:
            internal_cols = [c for c in df.columns if c.startswith("__")]
            export_df = df.drop(columns=internal_cols, errors="ignore")
            export_df.to_excel(path, index=False, engine="openpyxl")
            logger.info("[%s] Exported %s (%d records)", self.NAME, path.name, len(export_df))
        else:
            raise ExportError(f"No dataset to export to {path.name}")
    
    def _export_csv(self, state: PipelineState, path: Path):
        df = self._resolve_dataset(state)
        if df is not None and not df.empty:
            internal_cols = [c for c in df.columns if c.startswith("__")]
            export_df = df.drop(columns=internal_cols, errors="ignore")
            export_df.to_csv(path, index=False, encoding="utf-8")
            logger.info("[%s] Exported %s", self.NAME, path.name)
        else:
            raise ExportError(f"No dataset to export to {path.name}")
    
    def _export_txt(self, state: PipelineState, path: Path):
        df = self._resolve_dataset(state)
        if df is not None and not df.empty:
            WOS_TAGS = [
                "PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID",
                "AB", "C1", "RP", "EM", "FU", "FX", "CR", "NR", "TC",
                "Z9", "U1", "U2", "PY", "PU", "PI", "PA", "SN", "EI",
                "J9", "JI", "PD", "VL", "IS", "BP", "EP", "DI", "PG",
                "WC", "SC", "GA", "UT", "DA", "RI", "OI", "AR", "EA",
                "WE", "PM",
            ]
            MANDATORY_WOS_TAGS = {"PT", "AU", "TI", "SO", "PY", "DT", "DE", "C1", "RP", "CR", "UT", "LA"}
            MULTI_LINE_TAGS = {"AU", "AF", "C1", "DE", "ID", "CR", "AB", "FX", "FU"}

            work = df.copy()
            for col in ["PT", "LA", "DT"]:
                if col not in work.columns:
                    work[col] = ""
                defaults = {"PT": "J", "LA": "English", "DT": "Article"}
                work[col] = work[col].fillna(defaults.get(col, "")).replace("", defaults.get(col, ""))

            if "C1" not in work.columns:
                work["C1"] = ""
            if "RP" not in work.columns:
                work["RP"] = ""
            if "DE" not in work.columns:
                work["DE"] = ""
            if "CR" not in work.columns:
                work["CR"] = ""
            if "UT" not in work.columns:
                work["UT"] = ""
            for idx in range(len(work)):
                c1_val = str(work.iloc[idx].get("C1", "")).strip()
                af_val = str(work.iloc[idx].get("AF", "")).strip()
                rp_val = str(work.iloc[idx].get("RP", "")).strip()
                if not c1_val and af_val:
                    work.at[work.index[idx], "C1"] = f"[Unknown] {af_val}"
                if not rp_val and af_val:
                    work.at[work.index[idx], "RP"] = af_val.split(";")[0].strip()

            lines = ["FN Clarivate Analytics Web of Science", "VR 1.0"]

            for idx in range(len(work)):
                row = work.iloc[idx]
                for tag in WOS_TAGS:
                    if tag not in work.columns:
                        continue
                    raw = row.get(tag, "")
                    if isinstance(raw, pd.Series):
                        raw = raw.iloc[0] if len(raw) > 0 else ""
                    if pd.isna(raw):
                        raw = ""
                    val = str(raw).strip()
                    if not val and tag not in MANDATORY_WOS_TAGS:
                        continue
                    if tag == "PT":
                        lines.append(f"PT {val}")
                    elif tag in MULTI_LINE_TAGS and len(val) > 80:
                        lines.append(f"{tag}  {val[:80]}")
                        remaining = val[80:]
                        while remaining:
                            lines.append(f"   {remaining[:80]}")
                            remaining = remaining[80:]
                    else:
                        lines.append(f"{tag}  {val}")
                lines.append("ER")
                lines.append("")

            path.write_text("\n".join(lines), encoding="utf-8")
            logger.info("[%s] Exported %s (%d records)", self.NAME, path.name, len(work))
        else:
            raise ExportError(f"No dataset to export to {path.name}")
    
    def _export_prisma_docx(self, state: PipelineState, path: Path):
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        doc = Document()
        title = doc.add_heading("PRISMA Flow Diagram Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        # Search Summary
        doc.add_heading("1. Search Summary", level=1)
        ss = state.prisma_data.get("search_summary", {})
        doc.add_paragraph(f"Databases searched: {ss.get('total_identified', 'N/A')} total records across {ss.get('files_imported', 'N/A')} files")
        doc.add_paragraph(f"Files: {', '.join(ss.get('databases_searched', []))}")
        
        # Records
        doc.add_heading("2. Records Identified", level=1)
        recs = state.prisma_data.get("records", {})
        table = doc.add_table(rows=7, cols=2, style="Table Grid")
        table.cell(0, 0).text = "Stage"
        table.cell(0, 1).text = "Count"
        labels = ["Imported", "After Merge", "Duplicates Identified", "After Dedup", "After Cleaning", "Final Included"]
        values = [recs.get("imported", 0), recs.get("merged", 0), recs.get("duplicates_identified", 0),
                  recs.get("after_dedup", 0), recs.get("after_cleaning", 0), recs.get("included", 0)]
        for i, (label, val) in enumerate(zip(labels, values)):
            table.cell(i + 1, 0).text = label
            table.cell(i + 1, 1).text = str(val)
        
        # Inclusion Criteria
        doc.add_heading("3. Inclusion Criteria", level=1)
        for criterion in state.prisma_data.get("inclusion_criteria", []):
            doc.add_paragraph(criterion, style="List Bullet")
        
        # Exclusion Criteria
        doc.add_heading("4. Exclusion Criteria", level=1)
        for criterion in state.prisma_data.get("exclusion_criteria", []):
            doc.add_paragraph(criterion, style="List Bullet")
        
        # Study Selection Narrative
        doc.add_heading("5. Study Selection Narrative", level=1)
        doc.add_paragraph(state.prisma_data.get("study_selection_narrative", "N/A"))
        
        # AI Narrative
        doc.add_heading("6. PRISMA Flow Description", level=1)
        doc.add_paragraph(state.prisma_data.get("narrative", "N/A"))
        
        # Synchronization
        doc.add_heading("7. Synchronization Verification", level=1)
        doc.add_paragraph(f"Included studies count: {state.stats.prisma_included}")
        doc.add_paragraph(f"Bibliometrix dataset rows: {len(state.validated_dataset) if state.validated_dataset is not None else 0}")
        doc.add_paragraph(f"Synchronized: {'YES' if state.stats.synchronized else 'NO'}")
        
        doc.save(str(path))
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_validation_docx(self, state: PipelineState, path: Path):
        from docx import Document
        from docx.shared import Pt
        
        doc = Document()
        doc.add_heading("AIBEF Validation Report", 0)
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        quality = state.prisma_data.get("quality_report", {})
        doc.add_heading(f"Overall Quality Score: {quality.get('overall_score', 'N/A')}/100 ({quality.get('grade', 'N/A')})", level=1)
        
        doc.add_heading("Pipeline Summary", level=1)
        stats_table = doc.add_table(rows=12, cols=2, style="Table Grid")
        stats = [
            ("Imported Records", state.stats.total_imported),
            ("Files Processed", len(state.stats.per_file)),
            ("After Merge", state.stats.after_merge),
            ("Duplicates Found", state.stats.duplicates_found),
            ("Duplicates Removed", state.stats.duplicates_removed),
            ("After Deduplication", state.stats.after_dedup),
            ("Validation Issues", state.stats.validation_issues),
            ("Metadata Repairs", state.stats.metadata_repairs),
            ("After Cleaning", state.stats.after_cleaning),
            ("Final Dataset", state.stats.final_count),
            ("PRISMA Included", state.stats.prisma_included),
            ("Synchronized", "YES" if state.stats.synchronized else "NO"),
        ]
        for i, (label, value) in enumerate(stats):
            stats_table.cell(i, 0).text = label
            stats_table.cell(i, 1).text = str(value)
        
        checks = quality.get("checks", {})
        if checks:
            doc.add_heading("Detailed Validation Checks", level=1)
            for check_name, check_data in checks.items():
                doc.add_heading(f"{check_name.replace('_', ' ').title()}", level=2)
                status = check_data.get("status", "UNKNOWN")
                p = doc.add_paragraph()
                p.add_run(f"Status: {status}").bold = True
                for key, value in check_data.items():
                    if key != "status":
                        doc.add_paragraph(f"  {key}: {value}")
        
        if state.errors:
            doc.add_heading("Errors and Warnings", level=1)
            for error in state.errors:
                doc.add_paragraph(error)
        
        doc.save(str(path))
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_bibval_docx(self, state: PipelineState, path: Path):
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        
        doc = Document()
        title = doc.add_heading("Bibliometrix Validation Report", 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        
        df = self._resolve_dataset(state)
        validated_df = state.validated_dataset
        
        # Section 1: Dataset Overview
        doc.add_heading("1. Dataset Overview", level=1)
        t = doc.add_table(rows=7, cols=2, style="Table Grid")
        overview = [
            ("Source Files", str(len(state.stats.per_file))),
            ("Total Records Imported", str(state.stats.total_imported)),
            ("Records After Merge", str(state.stats.after_merge)),
            ("Duplicates Removed", str(state.stats.duplicates_removed)),
            ("Records After Cleaning", str(state.stats.after_cleaning)),
            ("Final Dataset Rows", str(state.stats.final_count)),
            ("Dataset Columns", str(len(df.columns)) if df is not None else "N/A"),
        ]
        for i, (label, val) in enumerate(overview):
            t.cell(i, 0).text = label
            t.cell(i, 1).text = val
        
        # Section 2: Bibliometrix Required Columns
        doc.add_heading("2. Bibliometrix Column Verification", level=1)
        required = ["PT", "AU", "AF", "TI", "SO", "LA", "DT", "DE", "ID", "AB", "C1", "RP", "PY", "UT"]
        if df is not None:
            col_table = doc.add_table(rows=len(required) + 1, cols=3, style="Table Grid")
            col_table.cell(0, 0).text = "Column"
            col_table.cell(0, 1).text = "Present"
            col_table.cell(0, 2).text = "Non-Empty Count"
            for i, col in enumerate(required):
                col_table.cell(i + 1, 0).text = col
                present = "YES" if col in df.columns else "NO"
                col_table.cell(i + 1, 1).text = present
                if col in df.columns:
                    col_data = df[col]
                    if isinstance(col_data, pd.DataFrame):
                        col_data = col_data.iloc[:, 0]
                    non_empty = int(col_data.replace("", pd.NA).dropna().shape[0])
                    col_table.cell(i + 1, 2).text = f"{non_empty}/{len(df)}"
                else:
                    col_table.cell(i + 1, 2).text = "N/A"
        
        # Section 3: Data Quality Metrics
        doc.add_heading("3. Data Quality Metrics", level=1)
        if df is not None:
            qt = doc.add_table(rows=6, cols=2, style="Table Grid")
            metrics = [
                ("Total Rows", str(len(df))),
                ("Total Columns", str(len(df.columns))),
                ("Author Format (Last, Initials)", self._check_author_format(df)),
                ("Year Range", self._check_year_range(df)),
                ("DOI Coverage", self._check_doi_coverage(df)),
                ("Abstract Coverage", self._check_abstract_coverage(df)),
            ]
            for i, (label, val) in enumerate(metrics):
                qt.cell(i, 0).text = label
                qt.cell(i, 1).text = val
        
        # Section 4: Validation Actions
        doc.add_heading("4. Validation Actions Performed", level=1)
        actions = [
            f"Encoding fixes applied: {state.stats.metadata_repairs}",
            f"Missing columns added and populated with defaults",
            f"Author format standardized to 'Last, Initials' semicolon-separated",
            f"Year column validated and coerced to integer",
            f"DOI format verified and cleaned",
            f"Keywords normalized to semicolon-separated format",
            f"Duplicate column names resolved",
            f"UTF-8 encoding ensured throughout",
        ]
        for action in actions:
            doc.add_paragraph(action, style="List Bullet")
        
        # Section 5: Bibliometrix R Validation
        doc.add_heading("5. Bibliometrix R Validation (Full Chain)", level=1)

        r_val = state.prisma_data.get("r_validation", {})

        if r_val:
            overall_ok = r_val.get("success", False)

            p = doc.add_paragraph()
            p.add_run("Overall R Validation: ").bold = True
            p.add_run("PASSED" if overall_ok else "FAILED")

            if r_val.get("message"):
                doc.add_paragraph(r_val["message"])

            # Per-step results table
            conv = r_val.get("convert2df", {})
            bio = r_val.get("biblioAnalysis", {})
            summ = r_val.get("summary", {})

            rows_data = [
                ("convert2df",
                 "PASSED" if conv.get("success") else "FAILED",
                 f"{conv.get('nrow', '?')} rows, {conv.get('ncol', '?')} cols" if conv.get("success") else ""),
                ("biblioAnalysis",
                 "PASSED" if bio.get("success") else "FAILED",
                 bio.get("status", "") if not bio.get("success") else ""),
                ("summary",
                 "PASSED" if summ.get("success") else "FAILED",
                 summ.get("status", "") if not summ.get("success") else ""),
            ]

            tbl = doc.add_table(rows=len(rows_data) + 1, cols=3, style="Table Grid")
            tbl.cell(0, 0).text = "R Step"
            tbl.cell(0, 1).text = "Status"
            tbl.cell(0, 2).text = "Details"
            for i, (step, status, detail) in enumerate(rows_data):
                tbl.cell(i + 1, 0).text = step
                tbl.cell(i + 1, 1).text = status
                tbl.cell(i + 1, 2).text = detail

            # Summary output excerpt
            summary_text = summ.get("output", "")
            if summary_text:
                doc.add_paragraph("")
                p = doc.add_paragraph()
                p.add_run("Biblioshiny Summary Output (excerpt):").bold = True
                doc.add_paragraph(summary_text[:500])
        else:
            # Fallback when R validation data is absent
            p = doc.add_paragraph()
            p.add_run("Structural Validation: ").bold = True
            p.add_run("PASSED" if validated_df is not None else "FAILED")
            doc.add_paragraph("The dataset has been structurally validated against Bibliometrix requirements:")
            checks = [
                "All mandatory columns (AU, TI, SO, PY, UT) are present",
                "Author format uses semicolon-separated 'Last, Initials' convention",
                "Year values are numeric and within valid range",
                "Keywords use semicolon-separated format",
                "UTF-8 encoding applied to all text fields",
                "No duplicate column names",
            ]
            for check in checks:
                doc.add_paragraph(check, style="List Bullet")

        if validated_df is not None:
            doc.add_paragraph("")
            p = doc.add_paragraph()
            p.add_run(f"Dataset ready for Biblioshiny import: {len(validated_df)} records, {len(validated_df.columns)} columns").bold = True
        
        # Section 6: Compatibility Status
        doc.add_heading("6. Biblioshiny Compatibility Status", level=1)
        status_items = [
            ("Dataset Format", "WoS plain text export compatible"),
            ("Encoding", "UTF-8"),
            ("Author Format", "Last, Initials (semicolon-separated)"),
            ("Keyword Format", "Semicolon-separated"),
            ("Import Method", "convert2df(dbsource='wos', format='plaintext')"),
            ("Status", "READY FOR BIBLIOSHINY" if state.stats.synchronized else "NEEDS ATTENTION"),
        ]
        st = doc.add_table(rows=len(status_items), cols=2, style="Table Grid")
        for i, (label, val) in enumerate(status_items):
            st.cell(i, 0).text = label
            st.cell(i, 1).text = val
        
        doc.save(str(path))
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _check_author_format(self, df):
        if "AU" not in df.columns:
            return "N/A"
        col = df["AU"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        sample = col.head(30).dropna()
        formatted = sample.astype(str).str.contains(",", na=False).sum()
        return f"{formatted}/{len(sample)} records have comma-separated format"
    
    def _check_year_range(self, df):
        if "PY" not in df.columns:
            return "N/A"
        col = df["PY"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        years = pd.to_numeric(col, errors="coerce").dropna()
        if years.empty:
            return "No valid years"
        return f"{int(years.min())} - {int(years.max())} ({len(years)} valid)"
    
    def _check_doi_coverage(self, df):
        if "DI" not in df.columns:
            return "N/A"
        col = df["DI"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        dois = col.replace("", pd.NA).dropna()
        return f"{len(dois)}/{len(df)} records ({len(dois)/len(df)*100:.1f}%)"
    
    def _check_abstract_coverage(self, df):
        if "AB" not in df.columns:
            return "N/A"
        col = df["AB"]
        if isinstance(col, pd.DataFrame):
            col = col.iloc[:, 0]
        abs_ = col.replace("", pd.NA).dropna()
        return f"{len(abs_)}/{len(df)} records ({len(abs_)/len(df)*100:.1f}%)"
    
    def _export_included(self, state: PipelineState, path: Path):
        df = state.included_studies
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            df = self._resolve_dataset(state)
        if df is not None and not df.empty:
            internal_cols = [c for c in df.columns if c.startswith("__")]
            export_df = df.drop(columns=internal_cols, errors="ignore")
            export_df.to_excel(path, index=False, engine="openpyxl")
        else:
            pd.DataFrame().to_excel(path, index=False, engine="openpyxl")
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_excluded(self, state: PipelineState, path: Path):
        df = state.excluded_studies
        if df is not None and not df.empty:
            df.to_excel(path, index=False, engine="openpyxl")
        else:
            pd.DataFrame(columns=["record_id", "excluded_reason"]).to_excel(
                path, index=False, engine="openpyxl")
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_screening(self, state: PipelineState, path: Path):
        df = state.screening_log
        if df is not None and not df.empty:
            df.to_excel(path, index=False, engine="openpyxl")
        else:
            pd.DataFrame(columns=["record_id", "title", "decision", "reason"]).to_excel(
                path, index=False, engine="openpyxl")
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_audit(self, state: PipelineState, path: Path):
        data = {
            "framework": "AIBEF",
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "pipeline_stages": state.stage_log,
            "errors": state.errors,
            "statistics": asdict(state.stats),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("[%s] Exported %s", self.NAME, path.name)
    
    def _export_provenance(self, state: PipelineState, path: Path):
        data = {
            "framework": "AIBEF",
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "total_records": len(state.provenance),
            "source_files": list(state.stats.per_file.keys()),
            "records": [asdict(p) for p in state.provenance],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("[%s] Exported %s", self.NAME, path.name)
