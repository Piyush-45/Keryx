import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from vp_shared.agent_config import SCHEMA_VERSION, load_schema, validate_agent_config

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / name).read_text())
    return data


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(load_schema())


def test_schema_version_matches_constant() -> None:
    assert load_schema()["properties"]["schema_version"]["const"] == SCHEMA_VERSION


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.name)
def test_examples_are_valid(path: Path) -> None:
    assert validate_agent_config(json.loads(path.read_text())) == []


def _set(cfg: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(".")
    node: Any = cfg
    for key in parents:
        node = node[int(key)] if key.isdigit() else node[key]
    if value is _DELETE:
        del node[last]
    else:
        node[int(last) if last.isdigit() else last] = value


_DELETE = object()

INVALID_CASES: list[tuple[str, str, Any, str]] = [
    # (id, dotted path, new value, expected substring in an error)
    ("unknown_schema_version", "schema_version", "2", "'1' was expected"),
    ("empty_language", "language", [], "should be non-empty"),
    ("bad_locale", "language", ["hindi"], "does not match"),
    ("extra_top_level_key", "api_key", "sk-123", "Additional properties"),
    ("missing_greeting", "greeting", _DELETE, "'greeting' is a required property"),
    (
        "voice_without_preset_or_all_kinds",
        "voice",
        {"tts": {"provider": "sarvam:x", "fallback": ["cartesia:y"]}},
        "is not valid under any of the given schemas",
    ),
    (
        "provider_without_fallback",
        "voice.tts",
        {"provider": "sarvam:anushka", "fallback": []},
        "should be non-empty",
    ),
    (
        "unknown_vendor",
        "voice.tts",
        {"provider": "acme:v1", "fallback": ["cartesia:y"]},
        "does not match",
    ),
    (
        "tts_without_voice",
        "voice.tts",
        {"provider": "sarvam", "fallback": ["cartesia:y"]},
        "does not match",
    ),
    ("http_tool_plain_http", "tools.3.url", "http://clinic.example.com/x", "not valid under any"),
    (
        "http_tool_inline_headers",
        "tools.3.headers",
        {"Authorization": "Bearer x"},
        "not valid under any",
    ),
    ("unknown_tool_type", "tools.0.type", "payment", "not valid under any"),
    ("transfer_not_e164", "transfer.number", "09800000000", "does not match"),
    (
        "recording_without_disclosure",
        "recording",
        {"enabled": True},
        "'disclosure_line' is a required property",
    ),
    ("limits_out_of_range", "limits.max_call_seconds", 99999, "is greater than the maximum"),
    ("bad_extraction_field_id", "extraction_fields", ["not-a-uuid"], "does not match"),
    # Cross-reference checks (not expressible in JSON Schema)
    (
        "unknown_initial_state",
        "flow.initial_state",
        "nope",
        "flow.initial_state: unknown state 'nope'",
    ),
    ("unknown_next_state", "flow.states.0.next", ["book", "nope"], "unknown state 'nope'"),
    ("unknown_state_tool", "flow.states.1.tools", ["check_slots", "nope"], "unknown tool 'nope'"),
    ("duplicate_tool_name", "tools.1.name", "check_slots", "duplicate tool name 'check_slots'"),
    ("duplicate_state_id", "flow.states.2.id", "book", "duplicate state id 'book'"),
    (
        "undeclared_placeholder",
        "greeting",
        "Hi {first_name}",
        "placeholder '{first_name}' is not declared",
    ),
]


@pytest.mark.parametrize(
    ("path", "value", "expected"), [c[1:] for c in INVALID_CASES], ids=[c[0] for c in INVALID_CASES]
)
def test_invalid_configs_are_rejected(path: str, value: Any, expected: str) -> None:
    cfg = copy.deepcopy(_example("clinic_booking.json"))
    _set(cfg, path, value)
    errors = validate_agent_config(cfg)
    assert any(expected in e for e in errors), errors
