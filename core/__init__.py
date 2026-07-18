"""Core infrastructure for AIBEF."""
from .config import CONFIG, FrameworkConfig, AgentConfig
from .logging_config import setup_logging, AuditLog
from .exceptions import (
    AIBEFError, ImportError_, MergeError, DeduplicationError,
    ValidationError, CleaningError, CompatibilityError,
    SynchronizationError, ExportError, ModelError, ConfigurationError
)
from .models import (
    RecordStats, DuplicateMapping, ValidationIssue,
    CleaningAction, ProvenanceEntry, PipelineState
)
