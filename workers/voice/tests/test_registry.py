import uuid
from typing import Any

import pytest
from pipecat.processors.frame_processor import FrameProcessor

from vp_shared.providers import ProviderChoice, ProviderSpec
from worker.providers import (
    Adapter,
    BuildContext,
    FallbackRecord,
    NoProviderAvailableError,
    ProviderRegistry,
)

CTX = BuildContext(org_id=uuid.uuid4(), language="hi-IN")


class FakeService(FrameProcessor):
    def __init__(self, spec: ProviderSpec, api_key: str) -> None:
        super().__init__()
        self.spec = spec
        self.api_key = api_key


class Keys:
    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = keys

    async def api_key(self, org_id: uuid.UUID, vendor: str) -> str | None:
        return self.keys.get(vendor)


def fake(kind: Any, vendor: str, *, fails: bool = False) -> Adapter:
    def factory(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> FrameProcessor:
        if fails:
            raise RuntimeError("boom")
        return FakeService(spec, api_key)

    return Adapter(kind=kind, vendor=vendor, factory=factory)


TTS = ProviderChoice.from_json(
    "tts", {"provider": "sarvam:priya", "fallback": ["cartesia:v1", "elevenlabs:v2"]}
)


def registry(keys: dict[str, str], failing: frozenset[str] = frozenset()) -> ProviderRegistry:
    adapters = [fake("tts", v, fails=v in failing) for v in ("sarvam", "cartesia", "elevenlabs")]
    return ProviderRegistry(adapters, Keys(keys))


ALL_KEYS = {"sarvam": "k1", "cartesia": "k2", "elevenlabs": "k3"}


async def test_primary_builds_without_fallback() -> None:
    built, records = await registry(ALL_KEYS).chain("tts", TTS, CTX).build_first()
    assert str(built.spec) == "sarvam:priya"
    assert built.cost_unit == "character"
    assert isinstance(built.service, FakeService)
    assert built.service.api_key == "k1"
    assert records == []


async def test_missing_key_falls_back_and_records_it() -> None:
    keys = {"cartesia": "k2", "elevenlabs": "k3"}
    built, records = await registry(keys).chain("tts", TTS, CTX).build_first()
    assert str(built.spec) == "cartesia:v1"
    assert records == [
        FallbackRecord("tts", TTS.primary, TTS.fallback[0], "startup", "no API key for sarvam")
    ]


async def test_adapter_error_falls_back() -> None:
    reg = registry(ALL_KEYS, failing=frozenset({"sarvam", "cartesia"}))
    built, records = await reg.chain("tts", TTS, CTX).build_first()
    assert str(built.spec) == "elevenlabs:v2"
    assert [(str(r.from_spec), str(r.to_spec)) for r in records] == [
        ("sarvam:priya", "cartesia:v1"),
        ("cartesia:v1", "elevenlabs:v2"),
    ]
    assert records[0].detail == "RuntimeError: boom"


async def test_all_fail_raises_with_every_attempt() -> None:
    with pytest.raises(NoProviderAvailableError) as exc:
        await registry({}).chain("tts", TTS, CTX).build_first()
    assert exc.value.kind == "tts"
    assert [str(r.from_spec) for r in exc.value.records] == [str(s) for s in TTS.chain]
    assert exc.value.records[-1].to_spec is None


async def test_runtime_failover_moves_past_the_failed_provider() -> None:
    chain = registry(ALL_KEYS).chain("tts", TTS, CTX)
    built, records = await chain.build_next(TTS.primary, "error", "websocket closed")
    assert str(built.spec) == "cartesia:v1"
    assert records == [
        FallbackRecord("tts", TTS.primary, TTS.fallback[0], "error", "websocket closed")
    ]


async def test_runtime_failover_from_last_provider_is_exhausted() -> None:
    chain = registry(ALL_KEYS).chain("tts", TTS, CTX)
    with pytest.raises(NoProviderAvailableError) as exc:
        await chain.build_next(TTS.fallback[-1], "latency", "ttfb 2400ms")
    assert exc.value.records == [
        FallbackRecord("tts", TTS.fallback[-1], None, "latency", "ttfb 2400ms")
    ]


async def test_unknown_vendor_is_a_build_failure() -> None:
    reg = ProviderRegistry([fake("tts", "cartesia")], Keys(ALL_KEYS))
    built, records = await reg.chain("tts", TTS, CTX).build_first()
    assert str(built.spec) == "cartesia:v1"
    assert records[0].detail == "no adapter for tts:sarvam"


def test_duplicate_adapters_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ProviderRegistry([fake("tts", "sarvam"), fake("tts", "sarvam")], Keys({}))


def test_chain_kind_must_match_choice() -> None:
    with pytest.raises(ValueError, match="choice is for tts"):
        registry(ALL_KEYS).chain("stt", TTS, CTX)
