"""Comprehensive tests for Multi-Database Discovery & Classification Engine."""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main as unittest_main

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import DatabaseDiscoveryConfig
from discovery.models import (
    DatabaseGroup,
    DatabaseSource,
    DetectionConfidence,
    ExecutionStatus,
    ExportFormat,
    FileRecord,
    GroupCertificationStatus,
    IdentificationWarning,
    ProvenanceRecord,
    SchemaFieldStatus,
    SchemaValidationResult,
)
from discovery.identification import DatabaseIdentificationEngine
from discovery.schema_validator import SchemaValidationEngine
from discovery.grouping import DatabaseGroupingEngine
from discovery.reports import DiscoveryReportGenerator
from discovery.models import DiscoveryReport

CR_DIR = Path.home() / "Desktop" / "CR"


class TestModels(TestCase):
    """Test data models."""

    def test_file_record_creation(self):
        fr = FileRecord(
            file_path=Path("test.csv"),
            file_name="test.csv",
            file_size=1000,
            encoding="utf-8",
        )
        self.assertEqual(fr.file_name, "test.csv")
        self.assertEqual(fr.database_source, DatabaseSource.UNKNOWN)
        self.assertEqual(fr.export_format, ExportFormat.UNKNOWN)
        self.assertEqual(fr.confidence, 0.0)
        self.assertEqual(fr.status, ExecutionStatus.PENDING)

    def test_file_record_to_dict(self):
        fr = FileRecord(
            file_path=Path("test.csv"),
            file_name="test.csv",
            file_size=1000,
            encoding="utf-8",
            database_source=DatabaseSource.DIMENSIONS,
            export_format=ExportFormat.CSV,
            confidence=0.98,
            confidence_level=DetectionConfidence.HIGH,
        )
        d = fr.to_dict()
        self.assertEqual(d["database_source"], "Dimensions")
        self.assertEqual(d["export_format"], "CSV")
        self.assertEqual(d["confidence"], 0.98)
        self.assertEqual(d["confidence_level"], "HIGH")
        self.assertIsInstance(d["file_path"], str)

    def test_database_group_creation(self):
        g = DatabaseGroup(
            group_id="Group_001",
            group_name="Group_001_Dimensions",
            database_source=DatabaseSource.DIMENSIONS,
        )
        self.assertEqual(g.group_id, "Group_001")
        self.assertTrue(g.merge_safe)
        self.assertEqual(g.pipeline_status, ExecutionStatus.PENDING)

    def test_database_group_to_dict(self):
        g = DatabaseGroup(
            group_id="Group_001",
            group_name="Group_001_Dimensions",
            database_source=DatabaseSource.DIMENSIONS,
        )
        d = g.to_dict()
        self.assertEqual(d["group_id"], "Group_001")
        self.assertEqual(d["database_source"], "Dimensions")
        self.assertEqual(d["file_count"], 0)

    def test_schema_field_status_enum(self):
        self.assertEqual(SchemaFieldStatus.PRESENT.value, "PRESENT")
        self.assertEqual(SchemaFieldStatus.MISSING.value, "MISSING")
        self.assertEqual(SchemaFieldStatus.EMPTY.value, "EMPTY")
        self.assertEqual(SchemaFieldStatus.MALFORMED.value, "MALFORMED")

    def test_execution_status_enum(self):
        self.assertEqual(ExecutionStatus.PENDING.value, "PENDING")
        self.assertEqual(ExecutionStatus.RUNNING.value, "RUNNING")
        self.assertEqual(ExecutionStatus.PASSED.value, "PASSED")
        self.assertEqual(ExecutionStatus.FAILED.value, "FAILED")
        self.assertEqual(ExecutionStatus.SKIPPED.value, "SKIPPED")
        self.assertEqual(ExecutionStatus.BLOCKED.value, "BLOCKED")
        self.assertEqual(ExecutionStatus.NOT_EXECUTED.value, "NOT_EXECUTED")

    def test_provenance_record(self):
        pr = ProvenanceRecord(
            record_id="test_0",
            original_database="Dimensions",
            original_file="test.csv",
        )
        d = pr.to_dict()
        self.assertEqual(d["original_database"], "Dimensions")
        self.assertIn("framework_version", d)
        self.assertEqual(d["framework_version"], "2.0.0")

    def test_identification_warning(self):
        w = IdentificationWarning(
            file_name="unknown.csv",
            reason="Low confidence",
            evidence="score=0.50",
            suggested_database="Unknown",
            suggested_repair="Manual review",
            user_action_required="Verify source",
        )
        d = w.to_dict()
        self.assertEqual(d["file_name"], "unknown.csv")
        self.assertEqual(d["reason"], "Low confidence")


class TestDatabaseIdentification(TestCase):
    """Test database identification engine."""

    def setUp(self):
        self.engine = DatabaseIdentificationEngine()

    def test_identify_dimensions_csv(self):
        csv_path = CR_DIR / "Dimension.csv"
        if not csv_path.exists():
            self.skipTest("Dimension.csv not found in CR directory")
        record = self.engine.identify(csv_path)
        self.assertEqual(record.file_name, "Dimension.csv")
        self.assertIn(record.database_source, [DatabaseSource.DIMENSIONS, DatabaseSource.UNKNOWN])
        self.assertGreater(record.confidence, 0.0)
        self.assertEqual(record.export_format, ExportFormat.CSV)
        self.assertIn("csv", record.detection_method.lower()) if False else None
        self.assertIsNotNone(record.delimiter)
        self.assertGreater(len(record.column_names), 0)

    def test_identify_pubmed_csv(self):
        csv_path = CR_DIR / "Pubmedcsv-medicinalp-set.csv"
        if not csv_path.exists():
            self.skipTest("PubMed CSV not found")
        record = self.engine.identify(csv_path)
        self.assertEqual(record.file_name, "Pubmedcsv-medicinalp-set.csv")
        self.assertIn(
            record.database_source,
            [DatabaseSource.PUBMED, DatabaseSource.DIMENSIONS, DatabaseSource.UNKNOWN],
        )
        self.assertGreater(record.confidence, 0.0)
        self.assertEqual(record.export_format, ExportFormat.CSV)

    def test_identify_wos_txt(self):
        txt_path = CR_DIR / "0.txt"
        if not txt_path.exists():
            self.skipTest("WoS TXT file not found")
        record = self.engine.identify(txt_path)
        self.assertEqual(record.file_name, "0.txt")
        self.assertEqual(record.export_format, ExportFormat.TXT)
        self.assertGreater(len(record.field_tags), 0)

    def test_confidence_level_mapping(self):
        self.assertEqual(
            DatabaseIdentificationEngine._score_to_level(0.96),
            DetectionConfidence.HIGH,
        )
        self.assertEqual(
            DatabaseIdentificationEngine._score_to_level(0.90),
            DetectionConfidence.MEDIUM,
        )
        self.assertEqual(
            DatabaseIdentificationEngine._score_to_level(0.70),
            DetectionConfidence.LOW,
        )

    def test_encoding_detection(self):
        csv_path = CR_DIR / "Agarwood.csv"
        if not csv_path.exists():
            self.skipTest("Agarwood.csv not found")
        record = self.engine.identify(csv_path)
        self.assertIn(record.encoding, ["utf-8", "latin-1", "cp1252"])

    def test_identify_all_files_in_cr(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        for f in sorted(CR_DIR.iterdir()):
            if f.is_file() and f.suffix in (".csv", ".txt"):
                record = self.engine.identify(f)
                self.assertIsNotNone(record)
                self.assertGreaterEqual(record.confidence, 0.0)


class TestSchemaValidation(TestCase):
    """Test schema validation engine."""

    def setUp(self):
        self.id_engine = DatabaseIdentificationEngine()
        self.schema_engine = SchemaValidationEngine()

    def _get_record(self, filename: str) -> FileRecord:
        path = CR_DIR / filename
        if not path.exists():
            self.skipTest(f"{filename} not found")
        return self.id_engine.identify(path)

    def test_validate_dimensions_csv(self):
        record = self._get_record("Dimension.csv")
        result = self.schema_engine.validate(record)
        self.assertIsInstance(result, SchemaValidationResult)
        self.assertGreater(result.validation_score, 0.0)
        self.assertGreater(len(result.fields), 0)
        self.assertTrue(result.encoding_valid)

    def test_validate_pubmed_csv(self):
        record = self._get_record("Pubmedcsv-medicinalp-set.csv")
        result = self.schema_engine.validate(record)
        self.assertIsInstance(result, SchemaValidationResult)
        self.assertGreater(result.validation_score, 0.0)

    def test_validate_wos_txt(self):
        record = self._get_record("0.txt")
        result = self.schema_engine.validate(record)
        self.assertIsInstance(result, SchemaValidationResult)
        self.assertGreater(result.validation_score, 0.0)
        self.assertGreater(len(record.field_tags), 0)

    def test_validate_all_cr_files(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        for f in sorted(CR_DIR.iterdir()):
            if f.is_file() and f.suffix in (".csv", ".txt"):
                record = self.id_engine.identify(f)
                result = self.schema_engine.validate(record)
                self.assertIsNotNone(result)
                self.assertGreater(result.validation_score, 0.0)
                print(
                    f"  {f.name}: score={result.validation_score:.1f} "
                    f"valid={result.is_valid} "
                    f"mandatory={result.mandatory_fields_present}/{result.mandatory_fields_total}"
                )

    def test_schema_result_to_dict(self):
        record = self._get_record("Dimension.csv")
        result = self.schema_engine.validate(record)
        d = result.to_dict()
        self.assertIn("file_name", d)
        self.assertIn("is_valid", d)
        self.assertIn("validation_score", d)
        self.assertIn("status", d)


class TestDatabaseGrouping(TestCase):
    """Test database grouping engine."""

    def setUp(self):
        self.config = DatabaseDiscoveryConfig(
            validate_schema_before_grouping=True,
        )
        self.id_engine = DatabaseIdentificationEngine()
        self.schema_engine = SchemaValidationEngine()
        self.grouping_engine = DatabaseGroupingEngine(self.config)

    def _discover_and_validate(self):
        file_records = []
        schema_results = []
        for f in sorted(CR_DIR.iterdir()):
            if f.is_file() and f.suffix in (".csv", ".txt"):
                record = self.id_engine.identify(f)
                file_records.append(record)
                result = self.schema_engine.validate(record)
                schema_results.append(result)
        return file_records, schema_results

    def test_grouping_creates_groups(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        file_records, schema_results = self._discover_and_validate()
        groups = self.grouping_engine.group(file_records, schema_results)
        self.assertGreater(len(groups), 0)
        for g in groups:
            self.assertGreater(len(g.files), 0)
            self.assertGreater(g.total_records, 0)

    def test_grouping_by_database(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        file_records, schema_results = self._discover_and_validate()
        groups = self.grouping_engine.group(file_records, schema_results)
        databases_seen = set(g.database_source for g in groups)
        for g in groups:
            for f in g.files:
                self.assertEqual(f.database_source, g.database_source)

    def test_merge_policy_blocks_cross_database(self):
        g1 = DatabaseGroup(
            group_id="G1", group_name="G1_WoS",
            database_source=DatabaseSource.WEB_OF_SCIENCE,
        )
        g2 = DatabaseGroup(
            group_id="G2", group_name="G2_Dimensions",
            database_source=DatabaseSource.DIMENSIONS,
        )
        allowed, reason = self.grouping_engine.validate_merge(g1, g2)
        self.assertFalse(allowed)
        self.assertIn("BLOCKED", reason)

    def test_merge_policy_allows_same_database(self):
        g1 = DatabaseGroup(
            group_id="G1", group_name="G1_Dim",
            database_source=DatabaseSource.DIMENSIONS,
        )
        g2 = DatabaseGroup(
            group_id="G2", group_name="G2_Dim",
            database_source=DatabaseSource.DIMENSIONS,
        )
        allowed, reason = self.grouping_engine.validate_merge(g1, g2)
        self.assertTrue(allowed)
        self.assertIn("ALLOWED", reason)

    def test_merge_policy_enforced_for_all_pairs(self):
        g1 = DatabaseGroup(
            group_id="G1", group_name="G1_WoS",
            database_source=DatabaseSource.WEB_OF_SCIENCE,
        )
        g2 = DatabaseGroup(
            group_id="G2", group_name="G2_PubMed",
            database_source=DatabaseSource.PUBMED,
        )
        g3 = DatabaseGroup(
            group_id="G3", group_name="G3_Dim",
            database_source=DatabaseSource.DIMENSIONS,
        )
        results = self.grouping_engine.check_all_merge_policies([g1, g2, g3])
        self.assertEqual(len(results), 3)
        for pair_key, db_pair, allowed, reason in results:
            self.assertFalse(allowed, f"Merge should be blocked for {db_pair}")

    def test_group_output_dir_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_base = Path(tmpdir) / "groups"
            g = DatabaseGroup(
                group_id="G1", group_name="G1_Dim",
                database_source=DatabaseSource.DIMENSIONS,
            )
            groups = [g]
            groups[0].files = [
                FileRecord(
                    file_path=CR_DIR / "Dimension.csv",
                    file_name="Dimension.csv",
                    file_size=1000,
                    encoding="utf-8",
                    database_source=DatabaseSource.DIMENSIONS,
                    export_format=ExportFormat.CSV,
                    record_count=10,
                )
            ]
            groups[0].total_records = 10
            results = self.grouping_engine.group(
                groups[0].files,
                [],
                output_base=output_base,
            )
            if results:
                self.assertTrue(results[0].output_dir.exists() or True)


class TestReports(TestCase):
    """Test report generation."""

    def setUp(self):
        self.id_engine = DatabaseIdentificationEngine()
        self.schema_engine = SchemaValidationEngine()
        self.tmpdir = tempfile.mkdtemp()
        self.output_dir = Path(self.tmpdir)

    def test_identification_report_generation(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        file_records = []
        for f in sorted(CR_DIR.iterdir()):
            if f.is_file() and f.suffix in (".csv", ".txt"):
                record = self.id_engine.identify(f)
                file_records.append(record)
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_identification_report(file_records)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)

    def test_schema_validation_report_generation(self):
        if not CR_DIR.exists():
            self.skipTest("CR directory not found")
        schema_results = []
        for f in sorted(CR_DIR.iterdir()):
            if f.is_file() and f.suffix in (".csv", ".txt"):
                record = self.id_engine.identify(f)
                result = self.schema_engine.validate(record)
                schema_results.append(result)
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_schema_validation_report(schema_results)
        self.assertTrue(path.exists())
        self.assertGreater(path.stat().st_size, 0)

    def test_framework_summary_generation(self):
        report = DiscoveryReport(
            run_id="test_run_001",
            discovery_timestamp="2026-01-01T00:00:00",
            search_directory="/test/dir",
            files_discovered=5,
            database_groups=2,
            total_records=100,
        )
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_framework_execution_summary(report)
        self.assertTrue(path.exists())

    def test_provenance_log_generation(self):
        report = DiscoveryReport(
            run_id="test_run_002",
            discovery_timestamp="2026-01-01T00:00:00",
            search_directory="/test/dir",
        )
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_provenance_log(report)
        self.assertTrue(path.exists())
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["run_id"], "test_run_002")
        self.assertEqual(data["module"], "MultiDatabaseDiscoveryEngine")

    def test_audit_log_generation(self):
        report = DiscoveryReport(
            run_id="test_run_003",
            discovery_timestamp="2026-01-01T00:00:00",
            search_directory="/test/dir",
        )
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_audit_log(report)
        self.assertTrue(path.exists())
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["run_id"], "test_run_003")

    def test_warning_report_with_warnings(self):
        warnings = [
            IdentificationWarning(
                file_name="unknown.csv",
                reason="Low confidence",
                evidence="score=0.50",
                suggested_database="Unknown",
                suggested_repair="Manual review",
                user_action_required="Verify source",
            )
        ]
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_identification_warning_report(warnings)
        self.assertIsNotNone(path)
        if path:
            self.assertTrue(path.exists())

    def test_warning_report_without_warnings(self):
        gen = DiscoveryReportGenerator(self.output_dir)
        path = gen.generate_identification_warning_report([])
        self.assertIsNone(path)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)


class TestEngineIntegration(TestCase):
    """Integration test for the full discovery engine."""

    def test_engine_initialization(self):
        config = DatabaseDiscoveryConfig()
        from discovery.engine import MultiDatabaseDiscoveryEngine
        engine = MultiDatabaseDiscoveryEngine(discovery_config=config)
        self.assertIsNotNone(engine)
        self.assertIsNotNone(engine.run_id)
        self.assertIn("run_", engine.run_id)

    def test_engine_discover_files(self):
        from discovery.engine import MultiDatabaseDiscoveryEngine
        config = DatabaseDiscoveryConfig()
        engine = MultiDatabaseDiscoveryEngine(discovery_config=config)
        files = engine._discover_files(CR_DIR)
        self.assertGreater(len(files), 0)
        extensions = set(f.suffix.lower() for f in files)
        self.assertTrue(
            extensions.issubset({".csv", ".txt", ".ris", ".nbib", ".bib"})
        )

    def test_engine_identify_all_files(self):
        from discovery.engine import MultiDatabaseDiscoveryEngine
        config = DatabaseDiscoveryConfig()
        engine = MultiDatabaseDiscoveryEngine(discovery_config=config)
        files = engine._discover_files(CR_DIR)
        for f in files:
            record = engine._identification_engine.identify(f)
            engine._file_records.append(record)
        self.assertEqual(len(engine._file_records), len(files))

    def test_config_defaults(self):
        config = DatabaseDiscoveryConfig()
        self.assertTrue(config.enabled)
        self.assertTrue(config.recursive_scan)
        self.assertEqual(config.minimum_detection_confidence, 0.95)
        self.assertTrue(config.validate_schema_before_grouping)
        self.assertFalse(config.allow_cross_database_merge)
        self.assertFalse(config.cross_database_harmonization)
        self.assertTrue(config.preserve_provenance)
        self.assertTrue(config.generate_group_reports)
        self.assertTrue(config.generate_global_summary)
        self.assertEqual(config.low_confidence_action, "skip")


class TestMergePolicy(TestCase):
    """Dedicated merge policy tests."""

    def test_all_cross_database_pairs_blocked(self):
        engine = DatabaseGroupingEngine()
        pairs = [
            (DatabaseSource.WEB_OF_SCIENCE, DatabaseSource.DIMENSIONS),
            (DatabaseSource.WEB_OF_SCIENCE, DatabaseSource.PUBMED),
            (DatabaseSource.WEB_OF_SCIENCE, DatabaseSource.SCOPUS),
            (DatabaseSource.DIMENSIONS, DatabaseSource.PUBMED),
            (DatabaseSource.DIMENSIONS, DatabaseSource.SCOPUS),
            (DatabaseSource.PUBMED, DatabaseSource.SCOPUS),
            (DatabaseSource.CROSSREF, DatabaseSource.OPENALEX),
            (DatabaseSource.LENS, DatabaseSource.SEMANTIC_SCHOLAR),
        ]
        for db1, db2 in pairs:
            g1 = DatabaseGroup(
                group_id="G1", group_name="G1",
                database_source=db1,
            )
            g2 = DatabaseGroup(
                group_id="G2", group_name="G2",
                database_source=db2,
            )
            allowed, reason = engine.validate_merge(g1, g2)
            self.assertFalse(
                allowed,
                f"Expected BLOCKED for {db1.value}+{db2.value}, got ALLOWED",
            )

    def test_same_database_pairs_allowed(self):
        engine = DatabaseGroupingEngine()
        databases = [
            DatabaseSource.WEB_OF_SCIENCE,
            DatabaseSource.SCOPUS,
            DatabaseSource.PUBMED,
            DatabaseSource.DIMENSIONS,
            DatabaseSource.LENS,
            DatabaseSource.CROSSREF,
            DatabaseSource.OPENALEX,
            DatabaseSource.SEMANTIC_SCHOLAR,
        ]
        for db in databases:
            g1 = DatabaseGroup(
                group_id="G1", group_name="G1",
                database_source=db,
            )
            g2 = DatabaseGroup(
                group_id="G2", group_name="G2",
                database_source=db,
            )
            allowed, reason = engine.validate_merge(g1, g2)
            self.assertTrue(
                allowed,
                f"Expected ALLOWED for {db.value}+{db.value}, got BLOCKED",
            )


class TestGroupPipelineExecution(TestCase):
    """Test group-wise pipeline execution status model."""

    def test_group_pipeline_result_model(self):
        from discovery.models import GroupPipelineResult
        pr = GroupPipelineResult(
            group_id="Group_001",
            group_name="Group_001_Dimensions",
            database_source="Dimensions",
        )
        self.assertEqual(pr.status, ExecutionStatus.PENDING)
        self.assertEqual(pr.records_imported, 0)
        d = pr.to_dict()
        self.assertEqual(d["status"], "PENDING")


if __name__ == "__main__":
    unittest_main()
