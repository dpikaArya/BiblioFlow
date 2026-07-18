"""Custom exceptions for the Global AI Model Registry."""


class RegistryError(Exception):
    """Base exception for all registry errors."""
    pass


class ModelNotFoundError(RegistryError):
    """Raised when a requested model is not found in the registry."""
    pass


class ModelLoadError(RegistryError):
    """Raised when a model fails to load."""
    pass


class ModelVerificationError(RegistryError):
    """Raised when model verification fails."""
    pass


class ModelCacheError(RegistryError):
    """Raised when model caching operations fail."""
    pass


class RegistryConfigError(RegistryError):
    """Raised when registry configuration is invalid."""
    pass


class NoModelAvailableError(RegistryError):
    """Raised when no model matches the request criteria."""
    pass


class InferenceError(RegistryError):
    """Raised when model inference fails."""
    pass
