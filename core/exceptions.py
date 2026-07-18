"""Custom exceptions for AIBEF framework."""

class AIBEFError(Exception):
    """Base exception for AIBEF."""
    pass

class ImportError_(AIBEFError):
    """Error during dataset import."""
    pass

class MergeError(AIBEFError):
    """Error during dataset merging."""
    pass

class DeduplicationError(AIBEFError):
    """Error during duplicate detection."""
    pass

class ValidationError(AIBEFError):
    """Error during metadata validation."""
    pass

class CleaningError(AIBEFError):
    """Error during cleaning/harmonization."""
    pass

class CompatibilityError(AIBEFError):
    """Error during Bibliometrix compatibility check."""
    pass

class MappingValidationError(AIBEFError):
    """Error during Database Mapping Validation."""
    pass

class SynchronizationError(AIBEFError):
    """Error during PRISMA-dataset synchronization."""
    pass

class ExportError(AIBEFError):
    """Error during file export."""
    pass

class ModelError(AIBEFError):
    """Error loading or running local model."""
    pass

class ConfigurationError(AIBEFError):
    """Configuration error."""
    pass
