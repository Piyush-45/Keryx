"""Shared loading of the JSON Schemas in packages/shared/ and a common error type."""

import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any

# Repo layout: packages/shared/<schema>, this file at packages/shared/python/vp_shared/.
_REPO_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class SchemaError:
    path: str
    """JSONPath of the offending value, e.g. `$.voice.tts.fallback[0]`."""
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


@cache
def load_schema_file(filename: str) -> dict[str, Any]:
    """Return a schema bundled in the wheel, or read it from the repo."""
    bundled = resources.files("vp_shared").joinpath(filename)
    text = bundled.read_text() if bundled.is_file() else (_REPO_DIR / filename).read_text()
    schema: dict[str, Any] = json.loads(text)
    return schema
