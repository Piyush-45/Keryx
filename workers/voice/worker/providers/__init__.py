"""Provider registry: the only way pipeline code gets STT/LLM/TTS services (decision 0006)."""

from worker.providers.base import Adapter, BuildContext
from worker.providers.credentials import CredentialResolver, EnvCredentialResolver
from worker.providers.registry import (
    BuiltProvider,
    FallbackRecord,
    NoProviderAvailableError,
    ProviderChain,
    ProviderRegistry,
    default_registry,
)

__all__ = [
    "Adapter",
    "BuildContext",
    "BuiltProvider",
    "CredentialResolver",
    "EnvCredentialResolver",
    "FallbackRecord",
    "NoProviderAvailableError",
    "ProviderChain",
    "ProviderRegistry",
    "default_registry",
]
