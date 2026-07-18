"""Database Grouping Engine - groups validated files by database source."""
from __future__ import annotations
import logging
import shutil
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import DatabaseDiscoveryConfig
from discovery.models import (
    DatabaseGroup,
    DatabaseSource,
    ExecutionStatus,
    FileRecord,
    GroupCertificationStatus,
    SchemaValidationResult,
)

logger = logging.getLogger("aibef.discovery.grouping")


class DatabaseGroupingEngine:
    """Groups validated files by database source. Enforces merge safety."""

    def __init__(self, config: Optional[DatabaseDiscoveryConfig] = None):
        self.config = config or DatabaseDiscoveryConfig()
        self._groups: dict[str, DatabaseGroup] = {}
        self._group_counter = 0

    def group(
        self,
        file_records: list[FileRecord],
        schema_results: list[SchemaValidationResult],
        output_base: Optional[Path] = None,
    ) -> list[DatabaseGroup]:
        """Group files by database source, enforcing schema validation."""
        logger.info("Starting database grouping for %d files", len(file_records))
        self._groups.clear()
        self._group_counter = 0

        validated_map: dict[str, SchemaValidationResult] = {}
        for sr in schema_results:
            validated_map[sr.file_record.file_name] = sr

        skipped = []
        for record in file_records:
            sr = validated_map.get(record.file_name)
            if self.config.validate_schema_before_grouping:
                if sr is None or not sr.is_valid:
                    logger.warning(
                        "Skipping %s: schema validation not passed (score=%.2f)",
                        record.file_name,
                        sr.validation_score if sr else 0.0,
                    )
                    skipped.append(record)
                    continue

            db_key = record.database_source.value
            if db_key not in self._groups:
                self._group_counter += 1
                group_id = f"Group_{self._group_counter:03d}"
                group_name = f"{group_id}_{self._sanitize_name(db_key)}"
                output_dir = None
                if output_base:
                    output_dir = output_base / group_name
                    output_dir.mkdir(parents=True, exist_ok=True)
                self._groups[db_key] = DatabaseGroup(
                    group_id=group_id,
                    group_name=group_name,
                    database_source=record.database_source,
                    output_dir=output_dir,
                )

            self._groups[db_key].files.append(record)
            self._groups[db_key].total_records += record.record_count

        groups = list(self._groups.values())
        for g in groups:
            g.schema_validated = True
            g.merge_safe = True

        logger.info(
            "Grouping complete: %d groups from %d files (%d skipped)",
            len(groups), len(file_records), len(skipped),
        )

        for g in groups:
            logger.info(
                "  %s (%s): %d files, %d records",
                g.group_name, g.database_source.value,
                len(g.files), g.total_records,
            )

        return groups

    def validate_merge(
        self, group1: DatabaseGroup, group2: DatabaseGroup
    ) -> tuple[bool, str]:
        """Check if two groups can be merged."""
        if group1.database_source != group2.database_source:
            return False, (
                f"BLOCKED: Cross-database merge attempted: "
                f"{group1.database_source.value} + {group2.database_source.value}"
            )
        return True, "ALLOWED: Same database source"

    def check_all_merge_policies(
        self, groups: list[DatabaseGroup]
    ) -> list[tuple[str, str, bool, str]]:
        """Check merge policy for all group pairs."""
        results = []
        for i, g1 in enumerate(groups):
            for g2 in groups[i + 1:]:
                allowed, reason = self.validate_merge(g1, g2)
                pair_key = f"{g1.group_name}+{g2.group_name}"
                results.append((pair_key, f"{g1.database_source.value}+{g2.database_source.value}", allowed, reason))
                if not allowed:
                    logger.info("Merge policy: %s -> %s", pair_key, reason)
        return results

    def prepare_group_files(self, group: DatabaseGroup, temp_dir: Path) -> Path:
        """Copy group files to a temporary directory for pipeline processing."""
        group_dir = temp_dir / group.group_name
        group_dir.mkdir(parents=True, exist_ok=True)

        for record in group.files:
            dest = group_dir / record.file_name
            if not dest.exists():
                shutil.copy2(record.file_path, dest)
                logger.info("Copied %s -> %s", record.file_name, group_dir)

        return group_dir

    @staticmethod
    def _sanitize_name(name: str) -> str:
        return name.replace(" ", "").replace("/", "_")
