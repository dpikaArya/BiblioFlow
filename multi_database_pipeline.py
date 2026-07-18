"""Multi-Database Pipeline - new entry point for AIBEF with discovery engine."""
from __future__ import annotations
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import DatabaseDiscoveryConfig, FrameworkConfig, CONFIG
from discovery.engine import MultiDatabaseDiscoveryEngine

logger = logging.getLogger("aibef.multi_db_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AIBEF Multi-Database Discovery & Pipeline Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python multi_database_pipeline.py
  python multi_database_pipeline.py --input ~/Desktop/CR --output ./outputs
  python multi_database_pipeline.py --min-confidence 0.80 --no-pipeline
        """,
    )
    parser.add_argument(
        "--input", type=Path, default=None,
        help="Directory to scan for bibliographic files (default: ~/Desktop/CR)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output directory for results (default: ./outputs)",
    )
    parser.add_argument(
        "--min-confidence", type=float, default=0.95,
        help="Minimum detection confidence threshold (default: 0.95)",
    )
    parser.add_argument(
        "--no-recursive", action="store_true",
        help="Disable recursive directory scanning",
    )
    parser.add_argument(
        "--skip-pipeline", action="store_true",
        help="Only discover and group, do not execute pipeline",
    )
    parser.add_argument(
        "--low-confidence-action", choices=["skip", "ask_user", "abort"],
        default="skip",
        help="Action for low-confidence identifications (default: skip)",
    )
    parser.add_argument(
        "--allow-cross-merge", action="store_true",
        help="Allow cross-database merging (default: blocked)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    disc_config = DatabaseDiscoveryConfig(
        enabled=True,
        recursive_scan=not args.no_recursive,
        minimum_detection_confidence=args.min_confidence,
        allow_cross_database_merge=args.allow_cross_merge,
        low_confidence_action=args.low_confidence_action,
    )

    fw_config = CONFIG
    if args.input:
        fw_config.input_dir = args.input
    if args.output:
        fw_config.output_dir = args.output
        fw_config.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("AIBEF Multi-Database Pipeline Starting")
    logger.info("Input: %s", fw_config.input_dir)
    logger.info("Output: %s", fw_config.output_dir)
    logger.info("Min Confidence: %.2f", disc_config.minimum_detection_confidence)

    engine = MultiDatabaseDiscoveryEngine(
        discovery_config=disc_config,
        framework_config=fw_config,
    )

    search_dir = args.input or fw_config.input_dir
    report = engine.discover_and_execute(search_dir=search_dir)

    print("\n" + "=" * 60)
    print("AIBEF MULTI-DATABASE PIPELINE - RESULTS")
    print("=" * 60)
    print(f"Run ID:                  {report.run_id}")
    print(f"Files Discovered:        {report.files_discovered}")
    print(f"Database Groups:         {report.database_groups}")
    print(f"Total Records:           {report.total_records}")
    print(f"Cross-DB Merge:          {report.cross_database_merge_status}")
    print()
    for g in report.groups:
        print(
            f"  {g.group_name}: {g.database_source.value} "
            f"({len(g.files)} files, {g.total_records} records)"
        )
    print()
    for pr in report.pipeline_results:
        status_icon = "\u2705" if pr.status.value == "PASSED" else "\u274c"
        print(
            f"  {status_icon} {pr.group_name}: {pr.status.value} "
            f"| {pr.records_final} records "
            f"| Quality: {pr.quality_score}/100 ({pr.quality_grade})"
            f" | {pr.duration_seconds:.1f}s"
        )
    print()
    print(f"Health Score:            {report.framework_health_score:.1f}/100")
    print(f"Release Readiness:       {report.release_readiness}")
    print(f"Overall Status:          {report.overall_status.value}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    main()
