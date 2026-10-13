"""Every real adapter builds its Pipecat service from a spec with a dummy key, offline."""

import uuid

import pytest
from pipecat.processors.frame_processor import FrameProcessor

from vp_shared.providers import KINDS, PRESETS, VENDORS, ProviderSpec, resolve_voice
from worker.providers import BuildContext, default_registry
from worker.providers.adapters import ALL_ADAPTERS

SPECS = {
    ("stt", "deepgram"): "deepgram:nova-3",
    ("stt", "sarvam"): "sarvam",
    ("llm", "openai"): "openai:gpt-4.1-mini",
    ("llm", "gemini"): "gemini:gemini-2.5-flash",
    ("llm", "anthropic"): "anthropic:claude-haiku-5-5",
    ("tts", "cartesia"): "cartesia:voice-1",
    ("tts", "elevenlabs"): "elevenlabs:21m00Tcm4TlvDq8ikWAM",
    ("tts", "sarvam"): "sarvam:anushka",
}


class DummyKeys:
    async def api_key(self, org_id: uuid.UUID, vendor: str) -> str | None:
        return f"dummy-{vendor}"


def test_one_adapter_per_catalog_vendor() -> None:
    have = sorted((a.kind, a.vendor) for a in ALL_ADAPTERS)
    want = sorted((k, v) for k in KINDS for v in VENDORS[k])
    assert have == want == sorted(SPECS)


@pytest.mark.parametrize("language", ["hi-IN", "en-IN"])
@pytest.mark.parametrize("key", sorted(SPECS), ids=lambda k: f"{k[0]}-{k[1]}")
async def test_adapter_builds_service(key: tuple[str, str], language: str) -> None:
    kind, _ = key
    spec = ProviderSpec.parse(kind, SPECS[key])  # type: ignore[arg-type]
    ctx = BuildContext(org_id=uuid.uuid4(), language=language, llm_temperature=0.4)
    built = await default_registry(DummyKeys()).build_one(spec, ctx)
    assert isinstance(built.service, FrameProcessor)
    assert built.spec == spec


@pytest.mark.parametrize("preset", sorted(PRESETS))
async def test_every_preset_builds_primary_for_every_kind(preset: str) -> None:
    resolved = resolve_voice({"preset": preset})
    ctx = BuildContext(org_id=uuid.uuid4(), language="hi-IN")
    reg = default_registry(DummyKeys())
    for kind in KINDS:
        built, records = await reg.chain(kind, resolved.choice(kind), ctx).build_first()
        assert records == [], records
        assert built.spec == resolved.choice(kind).primary


@pytest.mark.parametrize("key", sorted(SPECS), ids=lambda k: f"{k[0]}-{k[1]}")
async def test_settings_reach_the_service(key: tuple[str, str]) -> None:
    """Model/voice/language/temperature are applied, not silently dropped.

    Reads Pipecat's private `_settings` (pinned pipecat-ai 1.x); update if Pipecat renames it.
    """
    kind, _ = key
    spec = ProviderSpec.parse(kind, SPECS[key])  # type: ignore[arg-type]
    ctx = BuildContext(org_id=uuid.uuid4(), language="hi-IN", llm_temperature=0.4)
    built = await default_registry(DummyKeys()).build_one(spec, ctx)
    settings = built.service._settings  # type: ignore[attr-defined]
    if kind == "llm":
        assert settings.model == spec.model
        assert settings.temperature == 0.4
    else:
        assert str(getattr(settings.language, "value", settings.language)).startswith("hi")
    if kind == "tts":
        assert settings.voice == spec.model
    if kind == "stt" and spec.model:
        assert settings.model == spec.model
