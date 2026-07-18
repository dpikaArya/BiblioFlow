"""AIBEF - AI Bibliometric Dataset Engineering Framework.

Main entry point for running the complete pipeline.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import CONFIG, FrameworkConfig
from pipelines.orchestrator import PipelineOrchestrator
from validation.checks import ValidationChecks
from reports.generators import ReportGenerator


def run_pipeline(input_dir: str = None, output_dir: str = None):
    """Run the full AIBEF pipeline."""
    config = FrameworkConfig()
    if input_dir:
        config.input_dir = Path(input_dir)
    if output_dir:
        config.output_dir = Path(output_dir)

    orchestrator = PipelineOrchestrator(config)
    state = orchestrator.run()

    ReportGenerator.generate_all(state, config.report_dir)

    sync_ok = ValidationChecks.verify_synchronization(state)
    bib_ok = ValidationChecks.verify_bibliometrix_compatible(state)
    outputs_ok = ValidationChecks.verify_all_outputs(config.output_dir)

    print("\n" + "=" * 60)
    print("AIBEF PIPELINE RESULTS")
    print("=" * 60)
    print(f"Total imported:   {state.stats.total_imported}")
    print(f"After merge:     {state.stats.after_merge}")
    print(f"Duplicates:      {state.stats.duplicates_removed}")
    print(f"After cleaning:  {state.stats.after_cleaning}")
    print(f"Final dataset:   {state.stats.final_count}")
    print(f"Synchronized:    {'YES' if sync_ok else 'NO'}")
    print(f"Bib compatible:  {'YES' if bib_ok else 'NO'}")
    print(f"\nOutput files ({config.output_dir}):")
    for filename, exists in outputs_ok.items():
        status = "OK" if exists else "MISSING"
        print(f"  [{status}] {filename}")

    if state.errors:
        print(f"\nErrors ({len(state.errors)}):")
        for error in state.errors:
            print(f"  - {error}")

    print("=" * 60)
    return state, config


def launch_biblioshiny_only(output_dir: str = None):
    """Launch Biblioshiny using an existing certified dataset."""
    from biblioshiny_launcher import BiblioshinyLaunchManager, BiblioshinyConfig

    cfg = BiblioshinyConfig()
    out = Path(output_dir) if output_dir else CONFIG.output_dir

    manager = BiblioshinyLaunchManager(cfg)
    result = manager.run(output_dir=out, launch=True)

    if not result["prechecks"]["all_passed"]:
        block = result["prechecks"].get("block_reason", "Unknown")
        print(f"\nBiblioshiny launch blocked: {block}")
        print(f"See: {out / 'Biblioshiny_Launch_Block_Report.docx'}")
        return False

    print(f"\nBiblioshiny launched (PID: {result.get('launch_result', {}).get('process_id', 'N/A')})")
    for f in result.get("files_generated", []):
        print(f"  Generated: {f}")
    return True


def run_pipeline_and_launch(input_dir: str = None, output_dir: str = None):
    """Run the full pipeline, then launch Biblioshiny if certified."""
    state, config = run_pipeline(input_dir, output_dir)

    from biblioshiny_launcher import BiblioshinyLaunchManager, BiblioshinyConfig

    cfg = BiblioshinyConfig()
    manager = BiblioshinyLaunchManager(cfg)
    result = manager.run(output_dir=config.output_dir, launch=True)

    if not result["prechecks"]["all_passed"]:
        block = result["prechecks"].get("block_reason", "Unknown")
        print(f"\nBiblioshiny not launched: {block}")
    else:
        pid = result.get("launch_result", {}).get("process_id", "N/A")
        print(f"\nBiblioshiny launched (PID: {pid})")

    for f in result.get("files_generated", []):
        print(f"  Generated: {f}")

    return state


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="AIBEF - AI Bibliometric Dataset Engineering Framework"
    )
    parser.add_argument("--input", "-i", type=str, default=None,
                        help="Input directory with TXT files")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory")
    parser.add_argument("--launch-biblioshiny", action="store_true",
                        help="Run pipeline then launch Biblioshiny if certified")
    parser.add_argument("--launch-biblioshiny-only", action="store_true",
                        help="Launch Biblioshiny using existing certified dataset (skip pipeline)")
    args = parser.parse_args()

    if args.launch_biblioshiny_only:
        launch_biblioshiny_only(args.output)
    elif args.launch_biblioshiny:
        run_pipeline_and_launch(args.input, args.output)
    else:
        run_pipeline(args.input, args.output)
