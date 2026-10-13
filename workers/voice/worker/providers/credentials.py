import os
from typing import Protocol
from uuid import UUID

# Platform keys. Tenant BYOK keys (Phase 3) come from encrypted integrations via another resolver.
ENV_VARS: dict[str, str] = {
    "deepgram": "DEEPGRAM_API_KEY",
    "sarvam": "SARVAM_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "cartesia": "CARTESIA_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
}


class CredentialResolver(Protocol):
    async def api_key(self, org_id: UUID, vendor: str) -> str | None:
        """Return the key to use for `vendor` on this org's calls, or None if there is none."""
        ...


class EnvCredentialResolver:
    """Platform keys from environment variables (secrets manager in deployed envs)."""

    async def api_key(self, org_id: UUID, vendor: str) -> str | None:
        name = ENV_VARS.get(vendor)
        return (os.environ.get(name) or None) if name else None
