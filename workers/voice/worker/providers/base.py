from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pipecat.processors.frame_processor import FrameProcessor

from vp_shared.providers import Kind, ProviderSpec


@dataclass(frozen=True)
class BuildContext:
    """Per-call inputs adapters may need. Built by the pipeline factory from the agent version."""

    org_id: UUID
    language: str
    """Primary BCP-47 locale of the agent, e.g. `hi-IN`."""
    llm_temperature: float | None = None


Factory = Callable[[ProviderSpec, str, BuildContext], FrameProcessor]


@dataclass(frozen=True)
class Adapter:
    """One vendor for one kind. `factory(spec, api_key, ctx)` returns a Pipecat service.

    Adapter modules (worker/providers/adapters/) are the only place vendor services are imported.
    Factories must not do network I/O; connections happen when the pipeline starts.
    """

    kind: Kind
    vendor: str
    factory: Factory
