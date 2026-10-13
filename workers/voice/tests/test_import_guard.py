"""CLAUDE.md: providers via the registry only; no vendor SDK imports in pipeline code."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "worker"
ADAPTERS = PACKAGE / "providers" / "adapters"
VENDOR_MODULES = (
    "pipecat.services.",
    "deepgram",
    "openai",
    "anthropic",
    "google.genai",
    "google.generativeai",
    "cartesia",
    "elevenlabs",
    "sarvamai",
)


def _imports(path: Path) -> list[str]:
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_vendor_imports_only_in_adapters() -> None:
    offenders = [
        f"{path.relative_to(PACKAGE)}: {name}"
        for path in PACKAGE.rglob("*.py")
        if ADAPTERS not in path.parents
        for name in _imports(path)
        if name.startswith(VENDOR_MODULES)
    ]
    assert offenders == []


def test_guard_sees_adapter_imports() -> None:
    """Sanity check that the scan works: adapters do import vendor services."""
    assert any(
        name.startswith("pipecat.services.")
        for path in ADAPTERS.glob("*.py")
        for name in _imports(path)
    )
