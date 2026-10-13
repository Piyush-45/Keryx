"""Call events: build, redact, validate, parse (decision 0007).

`packages/shared/events.schema.json` is authoritative. `validate_event` = schema + rules it cannot
express. Producers use `vp_shared.eventbus.EventEmitter`, which calls `build_event` and
`validate_event` on every emit.
"""

import re
import uuid
from datetime import UTC, datetime
from functools import cache
from typing import Any, Literal, cast, get_args

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaError
from jsonschema.exceptions import best_match
from pydantic import ValidationError

from vp_shared._schemas import SchemaError, load_schema_file
from vp_shared.generated.events import (
    CallEnded,
    CallStarted,
    ExtractionDone,
    ProviderFallback,
    ToolCall,
    Transfer,
    Turn,
)

SCHEMA_FILENAME = "events.schema.json"
EVENT_VERSION = 1

EventType = Literal[
    "call.started",
    "turn",
    "tool_call",
    "transfer",
    "provider.fallback",
    "call.ended",
    "extraction.done",
]
EVENT_TYPES: tuple[EventType, ...] = get_args(EventType)

AnyEvent = CallStarted | Turn | ToolCall | Transfer | ProviderFallback | CallEnded | ExtractionDone
EVENT_MODELS: dict[str, type[AnyEvent]] = {
    "call.started": CallStarted,
    "turn": Turn,
    "tool_call": ToolCall,
    "transfer": Transfer,
    "provider.fallback": ProviderFallback,
    "call.ended": CallEnded,
    "extraction.done": ExtractionDone,
}

# Which usage units each kind may report (metered in vp_shared.providers.COST_UNIT terms).
_USAGE_UNITS: dict[str, frozenset[str]] = {
    "stt": frozenset({"audio_seconds"}),
    "llm": frozenset({"input_tokens", "output_tokens", "cached_input_tokens"}),
    "tts": frozenset({"characters"}),
}


def load_schema() -> dict[str, Any]:
    return load_schema_file(SCHEMA_FILENAME)


@cache
def _validator(event_type: str) -> Draft202012Validator:
    """Validator for one event type, so errors point into that type instead of the root anyOf."""
    schema = load_schema()
    (def_name,) = (
        name
        for name, d in schema["$defs"].items()
        if name.endswith("Event") and d["properties"]["type"]["const"] == event_type
    )
    return Draft202012Validator({"$ref": f"#/$defs/{def_name}", "$defs": schema["$defs"]})


# --- card-number redaction (CLAUDE.md: no card data in the pipeline) -----------------------------

REDACTED_CARD = "[redacted card number]"
# 13-19 digits, optionally grouped with single spaces or dashes.
_CARD_CANDIDATE = re.compile(r"(?<![\d+])\d(?:[ -]?\d){12,18}(?!\d)")
# Structural fields: never free text, never redacted (phone numbers, ids, provider specs).
_NOT_FREE_TEXT = frozenset(
    {
        "from_number",
        "to_number",
        "agent_version_id",
        "campaign_id",
        "contact_id",
        "providers",
        "spec",
        "from_spec",
        "to_spec",
        "state_id",
        "recording_ref",
    }
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact_card_numbers(text: str) -> str:
    """Replace digit runs that look like payment card numbers (13-19 digits, Luhn-valid)."""

    def repl(m: re.Match[str]) -> str:
        digits = re.sub(r"[ -]", "", m.group(0))
        return REDACTED_CARD if _luhn_ok(digits) else m.group(0)

    return _CARD_CANDIDATE.sub(repl, text)


def redact_payload(value: Any, key: str | None = None) -> Any:
    """Redact card numbers in every free-text string of a payload (recursively)."""
    if key in _NOT_FREE_TEXT:
        return value
    if isinstance(value, str):
        return redact_card_numbers(value)
    if isinstance(value, dict):
        return {k: redact_payload(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_payload(v) for v in value]
    return value


# --- build / validate / parse ---------------------------------------------------------------------


def build_event(
    type: EventType,
    *,
    org_id: uuid.UUID,
    call_id: uuid.UUID,
    seq: int,
    payload: dict[str, Any],
    ts: datetime | None = None,
) -> dict[str, Any]:
    """Return a JSON-ready event envelope with a redacted payload. Does not validate."""
    return {
        "id": str(uuid.uuid4()),
        "type": type,
        "v": EVENT_VERSION,
        "org_id": str(org_id),
        "call_id": str(call_id),
        "seq": seq,
        "ts": (ts or datetime.now(UTC)).isoformat(),
        "payload": redact_payload(payload),
    }


def _rule_errors(event: dict[str, Any]) -> list[SchemaError]:
    errors: list[SchemaError] = []
    payload = event["payload"]
    if event["type"] == "turn":
        if payload["user"] is None and payload["agent"] is None:
            errors.append(
                SchemaError("$.payload", "a turn needs a user side, an agent side, or both")
            )
        for side in ("user", "agent"):
            part = payload[side]
            if part is not None and part["end_ms"] < part["start_ms"]:
                errors.append(SchemaError(f"$.payload.{side}", "end_ms is before start_ms"))
        if payload["user"] is None and payload["timings"]["v2v_ms"] is not None:
            errors.append(
                SchemaError("$.payload.timings.v2v_ms", "must be null without a user side")
            )
    elif event["type"] == "call.ended":
        for i, item in enumerate(payload["usage"]):
            extra = set(item["units"]) - _USAGE_UNITS[item["kind"]]
            if extra:
                errors.append(
                    SchemaError(
                        f"$.payload.usage[{i}].units",
                        f"{item['kind']} cannot report {', '.join(sorted(extra))}",
                    )
                )
    return errors


def validate_event(event: Any) -> list[SchemaError]:
    """All errors for an event; empty means valid."""
    if not isinstance(event, dict):
        return [SchemaError("$", "event must be a JSON object")]
    event_type = event.get("type")
    if event_type not in EVENT_MODELS:
        return [SchemaError("$.type", f"unknown event type {event_type!r}")]
    schema_errors = sorted(
        _validator(event_type).iter_errors(event), key=lambda e: list(e.absolute_path)
    )
    if schema_errors:
        return [_specific(e) for e in schema_errors]
    errors = _rule_errors(event)
    try:
        # Format checks the schema leaves to the parser (e.g. `ts` must be an aware datetime).
        EVENT_MODELS[event_type].model_validate(event)
    except ValidationError as exc:
        errors += [
            SchemaError("$." + ".".join(str(p) for p in err["loc"]), err["msg"])
            for err in exc.errors()
        ]
    return errors


def _specific(error: JsonSchemaError) -> SchemaError:
    """Nullable fields are `anyOf: [X, null]`; report why the value failed X, not "not valid under
    any of the given schemas"."""
    while error.validator == "anyOf" and error.context:
        branches = cast(list[Any], error.validator_value)
        relevant = [
            e
            for e in error.context
            if not (
                error.instance is not None and branches[int(e.schema_path[0])] == {"type": "null"}
            )
        ]
        error = best_match(relevant or error.context)
    return SchemaError(error.json_path, error.message)


class InvalidEventError(ValueError):
    def __init__(self, errors: list[SchemaError]) -> None:
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))


def parse_event(event: Any) -> AnyEvent:
    """Validate with the full rule set, then return the typed model for the event's type."""
    errors = validate_event(event)
    if errors:
        raise InvalidEventError(errors)
    return EVENT_MODELS[event["type"]].model_validate(event)
