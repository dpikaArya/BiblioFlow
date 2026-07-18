"""Agent 1: Dataset Import Agent."""
from __future__ import annotations
import logging
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from core.models import PipelineState, ProvenanceEntry
from core.exceptions import ImportError_
from utils.text_utils import WoSParser, CSVParser

logger = logging.getLogger("aibef.import")


class DatasetImportAgent:
    NAME = "DatasetImportAgent"

    def execute(self, state: PipelineState) -> PipelineState:
        logger.info("[%s] Starting dataset import", self.NAME)
        state.log_stage(self.NAME, "start", "Beginning dataset import")

        input_dir = state.config.input_dir
        txt_files = sorted(input_dir.glob("*.txt"))
        csv_files = sorted(input_dir.glob("*.csv"))

        all_files = []
        for f in txt_files:
            all_files.append(("txt", f))
        for f in csv_files:
            all_files.append(("csv", f))

        if not all_files:
            raise ImportError_(f"No TXT or CSV files found in {input_dir}")

        required_count = state.config.required_txt_count
        if required_count > 0 and len(all_files) != required_count:
            raise ImportError_(
                f"Expected exactly {required_count} files, "
                f"found {len(all_files)}: {[f[1].name for f in all_files]}"
            )

        logger.info("[%s] Found %d files: %s", self.NAME, len(all_files),
                    [f[1].name for f in all_files])

        total_imported = 0
        for file_type, file_path in all_files:
            try:
                if file_type == "txt":
                    parser = WoSParser(file_path, encoding=state.config.encoding)
                    df = parser.parse()
                else:
                    df = self._parse_csv(file_path, state.config.encoding)
            except Exception as e:
                logger.warning("[%s] Failed to parse %s: %s", self.NAME, file_path.name, e)
                continue

            if df.empty:
                logger.warning("[%s] File %s parsed to empty DataFrame", self.NAME, file_path.name)
                continue

            state.raw_datasets[file_path.name] = df
            count = len(df)
            total_imported += count
            state.stats.per_file[file_path.name] = count

            for idx in range(count):
                record_id = df.iloc[idx].get("__record_id__", f"{file_path.name}_{idx}")
                state.provenance.append(ProvenanceEntry(
                    record_id=str(record_id),
                    source_file=file_path.name,
                    original_index=idx,
                    status="imported",
                    transformations=[]
                ))

            logger.info("[%s] Imported %s: %d records", self.NAME, file_path.name, count)

        state.stats.total_imported = total_imported
        state.log_stage(self.NAME, "complete",
                        f"Imported {total_imported} records from {len(all_files)} files",
                        {"per_file": state.stats.per_file})
        logger.info("[%s] Import complete: %d total records", self.NAME, total_imported)
        return state

    def _parse_csv(self, file_path: Path, encoding: str):
        """Parse a CSV file with auto-detected delimiter."""
        import csv
        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                sample = f.read(8192)
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ","
        except Exception:
            delimiter = ","

        parser = CSVParser(file_path, encoding=encoding, delimiter=delimiter)
        return parser.parse()
