import copy
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from vp_shared.events import (
    EVENT_TYPES,
    REDACTED_CARD,
    InvalidEventError,
    build_event,
    load_schema,
    parse_event,
    redact_card_numbers,
    redact_payload,
    validate_event,
)
from vp_shared.generated.events import Turn

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "events"


def _example(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((EXAMPLES / f"{name}.json").read_text())
    return data


def test_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(load_schema())


def test_schema_and_code_agree_on_event_types() -> None:
    consts = [
        d["properties"]["type"]["const"]
        for name, d in load_schema()["$defs"].items()
        if name.endswith("Event")
    ]
    assert sorted(consts) == sorted(EVENT_TYPES)


def test_every_event_type_has_an_example() -> None:
    types = {json.loads(p.read_text())["type"] for p in EXAMPLES.glob("*.json")}
    assert types == set(EVENT_TYPES)


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.stem)
def test_examples_are_valid_and_round_trip(path: Path) -> None:
    data = json.loads(path.read_text())
    assert validate_event(data) == []
    event = parse_event(data)
    assert type(event).model_validate(event.model_dump(mode="json")) == event
    assert event.model_dump(mode="json", exclude={"ts"}, exclude_unset=True) == {
        k: v for k, v in data.items() if k != "ts"
    }


# --- turn rules (user/agent sides with offsets) --------------------------------------------------


def test_greeting_turn_has_no_user_side() -> None:
    turn = parse_event(_example("turn_greeting"))
    assert isinstance(turn, Turn)
    assert turn.payload.user is None
    assert turn.payload.agent is not None
    assert (turn.payload.agent.start_ms, turn.payload.agent.end_ms) == (420, 3900)


def test_double_utterance_turn_has_no_agent_side() -> None:
    event = _example("turn_exchange")
    event["payload"]["agent"] = None
    event["payload"]["timings"] = dict.fromkeys(event["payload"]["timings"])
    assert validate_event(event) == []


def _mutated(name: str, path: str, value: Any) -> dict[str, Any]:
    event = copy.deepcopy(_example(name))
    *parents, last = path.split(".")
    node: Any = event
    for key in parents:
        node = node[key]
    node[last] = value
    return event


INVALID: list[tuple[str, str, str, Any, str]] = [
    ("turn_without_sides", "turn_greeting", "payload.agent", None, "needs a user side"),
    ("end_before_start", "turn_exchange", "payload.user.end_ms", 100, "end_ms is before start_ms"),
    ("negative_offset", "turn_exchange", "payload.agent.start_ms", -5, "less than the minimum"),
    (
        "missing_offsets",
        "turn_exchange",
        "payload.user",
        {"text": "hi"},
        "'start_ms' is a required",
    ),
    ("v2v_without_user", "turn_greeting", "payload.timings.v2v_ms", 900, "without a user side"),
    ("unknown_type", "call_started", "type", "call.exploded", "unknown event type 'call.exploded'"),
    ("bad_version", "call_started", "v", 2, "1 was expected"),
    ("negative_seq", "tool_call", "seq", -1, "less than the minimum"),
    ("bad_number", "call_started", "payload.from_number", "98123", "'98123' does not match"),
    ("extra_payload_key", "tool_call", "payload.raw_audio", "x", "Additional properties"),
    ("bad_ts", "call_started", "ts", "yesterday", "$.ts: Input should be a valid datetime"),
    ("naive_ts", "call_started", "ts", "2026-10-13T10:00:00", "$.ts: Input should have timezone"),
    (
        "usage_unit_for_wrong_kind",
        "call_ended",
        "payload.usage",
        [{"kind": "tts", "spec": "sarvam:anushka", "units": {"input_tokens": 5}}],
        "tts cannot report input_tokens",
    ),
]


@pytest.mark.parametrize(
    ("name", "path", "value", "expected"), [c[1:] for c in INVALID], ids=[c[0] for c in INVALID]
)
def test_invalid_events_rejected(name: str, path: str, value: Any, expected: str) -> None:
    errors = validate_event(_mutated(name, path, value))
    assert any(expected in str(e) for e in errors), errors
    with pytest.raises(InvalidEventError):
        parse_event(_mutated(name, path, value))


# --- card-number redaction ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "my card is 4111111111111111 ok",
        "my card is 4111 1111 1111 1111 ok",
        "my card is 4111-1111-1111-1111 ok",
        "amex 378282246310005 ok",
    ],
)
def test_luhn_valid_card_numbers_are_redacted(text: str) -> None:
    redacted = redact_card_numbers(text)
    assert REDACTED_CARD in redacted
    assert redacted.endswith(" ok")
    assert not any(ch.isdigit() for ch in redacted.replace("is ", "").split(REDACTED_CARD)[1])


@pytest.mark.parametrize(
    "text",
    [
        "call me on +919812345678",
        "order 4111111111111112 (fails Luhn)",
        "reference 12345 and 987654321",
        "aadhaar-like 1234 5678 9012",  # 12 digits: not a card length
    ],
)
def test_non_card_digits_are_kept(text: str) -> None:
    assert redact_card_numbers(text) == text


def test_redact_payload_skips_structural_fields() -> None:
    payload = {
        "to_number": "+919800000000",
        "args": {"note": "card 4111111111111111", "nested": ["4111 1111 1111 1111"]},
        "result_summary": "charged 5555555555554444",
    }
    out = redact_payload(payload)
    assert out["to_number"] == "+919800000000"
    assert out["args"] == {"note": f"card {REDACTED_CARD}", "nested": [REDACTED_CARD]}
    assert out["result_summary"] == f"charged {REDACTED_CARD}"


def test_build_event_redacts_and_validates() -> None:
    payload = _example("turn_exchange")["payload"]
    payload["user"]["text"] = "card number 4111 1111 1111 1111 expiry next year"
    event = build_event("turn", org_id=uuid.uuid4(), call_id=uuid.uuid4(), seq=3, payload=payload)
    assert event["payload"]["user"]["text"] == f"card number {REDACTED_CARD} expiry next year"
    assert validate_event(event) == []
