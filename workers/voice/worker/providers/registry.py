"""Builds provider chains (primary, then fallbacks) for a call.

Start of call: `ProviderChain.build_first()` walks the chain until one provider builds; every skip
is returned as a FallbackRecord for the caller to emit as a `provider.fallback` event.
Runtime failover (per-request LLM fallback in the pipeline factory): `build_next(after, ...)`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pipecat.processors.frame_processor import FrameProcessor

from vp_shared.providers import COST_UNIT, CostUnit, Kind, ProviderChoice, ProviderSpec
from worker.providers.base import Adapter, BuildContext
from worker.providers.credentials import CredentialResolver, EnvCredentialResolver

FallbackReason = Literal["startup", "error", "latency"]


@dataclass(frozen=True)
class BuiltProvider:
    spec: ProviderSpec
    service: FrameProcessor
    cost_unit: CostUnit


@dataclass(frozen=True)
class FallbackRecord:
    kind: Kind
    from_spec: ProviderSpec
    to_spec: ProviderSpec | None
    """None when the chain is exhausted."""
    reason: FallbackReason
    detail: str


class ProviderBuildError(Exception):
    pass


class NoProviderAvailableError(RuntimeError):
    def __init__(self, kind: Kind, records: list[FallbackRecord]) -> None:
        self.kind = kind
        self.records = records
        tried = ", ".join(f"{r.from_spec} ({r.detail})" for r in records)
        super().__init__(f"no {kind} provider available; tried: {tried}")


class ProviderRegistry:
    def __init__(self, adapters: Iterable[Adapter], credentials: CredentialResolver) -> None:
        self._adapters: dict[tuple[Kind, str], Adapter] = {}
        for adapter in adapters:
            key = (adapter.kind, adapter.vendor)
            if key in self._adapters:
                raise ValueError(f"duplicate adapter for {key}")
            self._adapters[key] = adapter
        self._credentials = credentials

    @property
    def supported(self) -> frozenset[tuple[Kind, str]]:
        return frozenset(self._adapters)

    def chain(self, kind: Kind, choice: ProviderChoice, ctx: BuildContext) -> "ProviderChain":
        return ProviderChain(self, kind, choice, ctx)

    async def build_one(self, spec: ProviderSpec, ctx: BuildContext) -> BuiltProvider:
        adapter = self._adapters.get((spec.kind, spec.vendor))
        if adapter is None:
            raise ProviderBuildError(f"no adapter for {spec.kind}:{spec.vendor}")
        api_key = await self._credentials.api_key(ctx.org_id, spec.vendor)
        if not api_key:
            raise ProviderBuildError(f"no API key for {spec.vendor}")
        try:
            service = adapter.factory(spec, api_key, ctx)
        except Exception as exc:
            raise ProviderBuildError(f"{type(exc).__name__}: {exc}") from exc
        return BuiltProvider(spec=spec, service=service, cost_unit=COST_UNIT[spec.kind])


class ProviderChain:
    def __init__(
        self, registry: ProviderRegistry, kind: Kind, choice: ProviderChoice, ctx: BuildContext
    ) -> None:
        if choice.primary.kind != kind:
            raise ValueError(f"choice is for {choice.primary.kind}, not {kind}")
        self.kind = kind
        self.specs = choice.chain
        self._registry = registry
        self._ctx = ctx

    async def build_first(self) -> tuple[BuiltProvider, list[FallbackRecord]]:
        """Build the first provider in the chain that works."""
        return await self._build_from(0, [])

    async def build_next(
        self, after: ProviderSpec, reason: FallbackReason, detail: str
    ) -> tuple[BuiltProvider, list[FallbackRecord]]:
        """Fail over from `after` (which failed at runtime) to the next provider that builds."""
        index = self.specs.index(after) + 1
        to_spec = self.specs[index] if index < len(self.specs) else None
        records = [FallbackRecord(self.kind, after, to_spec, reason, detail)]
        return await self._build_from(index, records)

    async def _build_from(
        self, index: int, records: list[FallbackRecord]
    ) -> tuple[BuiltProvider, list[FallbackRecord]]:
        for i in range(index, len(self.specs)):
            spec = self.specs[i]
            try:
                return await self._registry.build_one(spec, self._ctx), records
            except ProviderBuildError as exc:
                to_spec = self.specs[i + 1] if i + 1 < len(self.specs) else None
                records.append(FallbackRecord(self.kind, spec, to_spec, "startup", str(exc)))
        raise NoProviderAvailableError(self.kind, records)


def default_registry(credentials: CredentialResolver | None = None) -> ProviderRegistry:
    from worker.providers.adapters import ALL_ADAPTERS

    return ProviderRegistry(ALL_ADAPTERS, credentials or EnvCredentialResolver())
