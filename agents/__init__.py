"""AIBEF Agents."""
from .agent_01_import import DatasetImportAgent
from .agent_02_merge import DatasetMergeAgent
from .agent_03_deduplicate import DuplicateDetectionAgent
from .agent_04_validate import MetadataValidationAgent
from .agent_05_clean import CleaningHarmonizationAgent
from .agent_05b_mapping_validation import DatabaseMappingValidationAgent
from .agent_06_compat import BibliometrixCompatAgent
from .agent_07_bibvalidate import BibliometrixValidationAgent
from .agent_08_prisma import PRISMAAgent
from .agent_09_sync import SynchronizationAgent
from .agent_10_quality import QualityValidationAgent
from .agent_11_export import ExportAgent

ALL_AGENTS = [
    DatasetImportAgent,
    DatasetMergeAgent,
    DuplicateDetectionAgent,
    MetadataValidationAgent,
    CleaningHarmonizationAgent,
    DatabaseMappingValidationAgent,
    BibliometrixCompatAgent,
    BibliometrixValidationAgent,
    PRISMAAgent,
    SynchronizationAgent,
    QualityValidationAgent,
    ExportAgent,
]
