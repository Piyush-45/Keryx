"""Load and validate agent config JSON against the shared schema.

JSON Schema covers shape; `validate_agent_config` adds cross-reference checks the schema
cannot express (state ids, tool names, template variables).
"""

import json
import re
from collections import Counter
from collections.abc import Iterable
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "1"
SCHEMA_FILENAME = "agent_config.schema.json"

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
# Repo layout: packages/shared/<schema>, this file at packages/shared/python/vp_shared/.
_REPO_SCHEMA = Path(__file__).resolve().parents[2] / SCHEMA_FILENAME


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


def _reference_errors(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    variables = [v["name"] for v in config.get("variables", [])]
    for name in _duplicates(variables):
        errors.append(f"variables: duplicate variable '{name}'")
    declared = set(variables)
    templates = {"greeting": config["greeting"], "persona.prompt": config["persona"]["prompt"]}

    tool_names = [t["name"] for t in config.get("tools", [])]
    for name in _duplicates(tool_names):
        errors.append(f"tools: duplicate tool name '{name}'")
    tools = set(tool_names)

    flow = config["flow"]
    state_ids = [s["id"] for s in flow["states"]]
    for sid in _duplicates(state_ids):
        errors.append(f"flow.states: duplicate state id '{sid}'")
    states = set(state_ids)
    if flow["initial_state"] not in states:
        errors.append(f"flow.initial_state: unknown state '{flow['initial_state']}'")

    for i, state in enumerate(flow["states"]):
        templates[f"flow.states[{i}].task_prompt"] = state["task_prompt"]
        for target in state.get("next", []):
            if target not in states:
                errors.append(f"flow.states[{i}].next: unknown state '{target}'")
        for tool in state.get("tools", []):
            if tool not in tools:
                errors.append(f"flow.states[{i}].tools: unknown tool '{tool}'")

    for path, text in templates.items():
        for name in sorted(set(_PLACEHOLDER.findall(text)) - declared):
            errors.append(f"{path}: placeholder '{{{name}}}' is not declared in variables")

    return errors


def validate_agent_config(config: Any) -> list[str]:
    """Return a list of human-readable errors; empty means the config is valid."""
    schema_errors = sorted(_validator().iter_errors(config), key=lambda e: list(e.absolute_path))
    if schema_errors:
        return [f"{e.json_path}: {e.message}" for e in schema_errors]
    return _reference_errors(config)
