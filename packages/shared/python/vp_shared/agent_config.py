"""Load and validate agent config JSON against the shared schema.

JSON Schema covers shape; `validate_agent_config` adds the rules the schema cannot express
(state ids, tool names, template variables, fallback vendors). This is the only validator:
the dashboard calls it through the API rather than reimplementing it in TypeScript.
"""

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from vp_shared.generated.agent_config import AgentConfig

SCHEMA_VERSION = "1"
SCHEMA_FILENAME = "agent_config.schema.json"

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
# Repo layout: packages/shared/<schema>, this file at packages/shared/python/vp_shared/.
_REPO_SCHEMA = Path(__file__).resolve().parents[2] / SCHEMA_FILENAME


@dataclass(frozen=True)
class ConfigError:
    path: str
    """JSONPath of the offending value, e.g. `$.voice.tts.fallback[0]`."""
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class InvalidAgentConfigError(ValueError):
    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))


@cache
def load_schema() -> dict[str, Any]:
    """Return the agent config JSON Schema (bundled in the wheel, or read from the repo)."""
    bundled = resources.files("vp_shared").joinpath(SCHEMA_FILENAME)
    text = bundled.read_text() if bundled.is_file() else _REPO_SCHEMA.read_text()
    schema: dict[str, Any] = json.loads(text)
    return schema


@cache
def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema())


def _duplicates(values: Iterable[str]) -> list[str]:
    return sorted(v for v, n in Counter(values).items() if n > 1)


def _vendor(spec: str) -> str:
    return spec.split(":", 1)[0]


def _reference_errors(config: dict[str, Any]) -> list[ConfigError]:
    errors: list[ConfigError] = []

    variables = [v["name"] for v in config.get("variables", [])]
    for name in _duplicates(variables):
        errors.append(ConfigError("$.variables", f"duplicate variable '{name}'"))
    declared = set(variables)
    templates = {"$.greeting": config["greeting"], "$.persona.prompt": config["persona"]["prompt"]}

    tool_names = [t["name"] for t in config.get("tools", [])]
    for name in _duplicates(tool_names):
        errors.append(ConfigError("$.tools", f"duplicate tool name '{name}'"))
    tools = set(tool_names)

    flow = config["flow"]
    state_ids = [s["id"] for s in flow["states"]]
    for sid in _duplicates(state_ids):
        errors.append(ConfigError("$.flow.states", f"duplicate state id '{sid}'"))
    states = set(state_ids)
    if flow["initial_state"] not in states:
        errors.append(
            ConfigError("$.flow.initial_state", f"unknown state '{flow['initial_state']}'")
        )

    for i, state in enumerate(flow["states"]):
        templates[f"$.flow.states[{i}].task_prompt"] = state["task_prompt"]
        for target in state.get("next", []):
            if target not in states:
                errors.append(ConfigError(f"$.flow.states[{i}].next", f"unknown state '{target}'"))
        for tool in state.get("tools", []):
            if tool not in tools:
                errors.append(ConfigError(f"$.flow.states[{i}].tools", f"unknown tool '{tool}'"))

    for kind in ("stt", "llm", "tts"):
        choice = config["voice"].get(kind)
        if choice is None:
            continue
        primary = _vendor(choice["provider"])
        for j, spec in enumerate(choice["fallback"]):
            if _vendor(spec) == primary:
                errors.append(
                    ConfigError(
                        f"$.voice.{kind}.fallback[{j}]",
                        f"fallback '{spec}' uses the same vendor as the primary ('{primary}')",
                    )
                )

    for path, text in templates.items():
        for name in sorted(set(_PLACEHOLDER.findall(text)) - declared):
            errors.append(
                ConfigError(path, f"placeholder '{{{name}}}' is not declared in variables")
            )

    return errors


def validate_agent_config(config: Any) -> list[ConfigError]:
    """Return all errors; an empty list means the config is valid.

    Reference rules run only once the shape is valid, so they can assume required keys exist.
    """
    schema_errors = sorted(_validator().iter_errors(config), key=lambda e: list(e.absolute_path))
    if schema_errors:
        return [ConfigError(e.json_path, e.message) for e in schema_errors]
    return _reference_errors(config)


def parse_agent_config(config: Any) -> AgentConfig:
    """Validate with the full rule set, then return the typed model. Raises InvalidAgentConfigError.

    Always use this rather than `AgentConfig.model_validate`: the generated model does not
    enforce cross-reference rules or the recording-disclosure condition.
    """
    errors = validate_agent_config(config)
    if errors:
        raise InvalidAgentConfigError(errors)
    return AgentConfig.model_validate(config)
