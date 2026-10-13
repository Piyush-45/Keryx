import json
import re
from pathlib import Path

import pytest

from vp_shared.agent_config import load_schema, validate_agent_config
from vp_shared.providers import (
    KINDS,
    PRESETS,
    VENDORS,
    ProviderChoice,
    ProviderSpec,
    ResolvedVoice,
    UnknownPresetError,
    resolve_voice,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_catalog_vendors_match_schema() -> None:
    defs = load_schema()["$defs"]
    for kind in KINDS:
        pattern = defs[f"{kind}Spec"]["pattern"]
        match = re.match(r"^\^\(([a-z|]+)\)", pattern)
        assert match, pattern
        assert set(match.group(1).split("|")) == VENDORS[kind]


@pytest.mark.parametrize(
    ("kind", "spec", "expected"),
    [
        ("stt", "sarvam", ProviderSpec("stt", "sarvam", None)),
        ("stt", "deepgram:nova-3", ProviderSpec("stt", "deepgram", "nova-3")),
        ("llm", "anthropic:claude-haiku-5-5", ProviderSpec("llm", "anthropic", "claude-haiku-5-5")),
        ("tts", "sarvam:priya", ProviderSpec("tts", "sarvam", "priya")),
    ],
)
def test_parse_round_trip(kind: str, spec: str, expected: ProviderSpec) -> None:
    parsed = ProviderSpec.parse(kind, spec)  # type: ignore[arg-type]
    assert parsed == expected
    assert str(parsed) == spec


@pytest.mark.parametrize(
    ("kind", "spec"), [("stt", "openai:whisper"), ("llm", "sarvam"), ("tts", "cartesia")]
)
def test_parse_rejects(kind: str, spec: str) -> None:
    with pytest.raises(ValueError, match=kind):
        ProviderSpec.parse(kind, spec)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", sorted(PRESETS))
def test_presets_are_valid_and_fallbacks_use_other_vendors(name: str) -> None:
    resolved = resolve_voice({"preset": name})
    for kind in KINDS:
        choice = resolved.choice(kind)
        assert choice.fallback, f"{name}.{kind} has no fallback"
        assert all(f.vendor != choice.primary.vendor for f in choice.fallback)
    # And a config using the preset passes the full validator.
    config = json.loads((EXAMPLES / "minimal.json").read_text())
    config["voice"] = {"preset": name}
    assert validate_agent_config(config) == []


def test_explicit_kinds_override_preset() -> None:
    tts = {"provider": "cartesia:voice-1", "fallback": ["sarvam:priya"]}
    resolved = resolve_voice({"preset": "india-standard", "tts": tts})
    assert resolved.tts.to_json() == tts
    assert resolved.stt == ProviderChoice.from_json("stt", PRESETS["india-standard"]["stt"])
    assert resolved.preset == "india-standard"


def test_explicit_voice_without_preset() -> None:
    config = json.loads((EXAMPLES / "minimal.json").read_text())
    resolved = resolve_voice(config["voice"])
    assert resolved.preset is None
    assert str(resolved.llm.primary) == "openai:gpt-4.1-mini"
    assert [str(s) for s in resolved.stt.chain] == ["deepgram:nova-3", "sarvam"]


def test_resolved_voice_json_round_trip() -> None:
    resolved = resolve_voice(
        {
            "preset": "india-standard",
            "llm": {
                "provider": "anthropic:claude-haiku-5-5",
                "fallback": ["openai:gpt-4.1-mini"],
                "temperature": 0.3,
            },
        }
    )
    data = json.loads(json.dumps(resolved.to_json()))
    assert ResolvedVoice.from_json(data) == resolved
    assert data["llm"]["temperature"] == 0.3


def test_unknown_preset() -> None:
    with pytest.raises(UnknownPresetError):
        resolve_voice({"preset": "nope"})
    config = json.loads((EXAMPLES / "minimal.json").read_text())
    config["voice"] = {"preset": "nope"}
    errors = validate_agent_config(config)
    assert [e.path for e in errors] == ["$.voice.preset"]
    assert "unknown preset 'nope'" in errors[0].message
