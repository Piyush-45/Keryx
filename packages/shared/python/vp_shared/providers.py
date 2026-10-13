"""Provider catalog, presets and voice resolution (decision 0006). No Pipecat imports here.

Specs are `vendor` or `vendor:model` (STT/LLM) and `vendor:voice-id` (TTS), as in the agent config
schema. A preset is resolved into explicit providers when an agent version is published, and the
result is stored on the agent version, so later preset edits never change published agents.
"""

from dataclasses import dataclass
from typing import Any, Literal, get_args

Kind = Literal["stt", "llm", "tts"]
KINDS: tuple[Kind, ...] = get_args(Kind)

CostUnit = Literal["audio_second", "token", "character"]

# What each kind is metered in. Adapters report usage in these units; prices live elsewhere.
COST_UNIT: dict[Kind, CostUnit] = {"stt": "audio_second", "llm": "token", "tts": "character"}

VENDORS: dict[Kind, frozenset[str]] = {
    "stt": frozenset({"deepgram", "sarvam"}),
    "llm": frozenset({"openai", "gemini", "anthropic"}),
    "tts": frozenset({"cartesia", "elevenlabs", "sarvam"}),
}


@dataclass(frozen=True)
class ProviderSpec:
    kind: Kind
    vendor: str
    model: str | None = None
    """Model id (STT/LLM, optional: vendor default) or voice id (TTS, required)."""

    @classmethod
    def parse(cls, kind: Kind, spec: str) -> "ProviderSpec":
        vendor, _, model = spec.partition(":")
        if vendor not in VENDORS[kind]:
            raise ValueError(f"unknown {kind} vendor '{vendor}' in '{spec}'")
        if kind == "tts" and not model:
            raise ValueError(f"tts spec '{spec}' must name a voice (vendor:voice-id)")
        return cls(kind=kind, vendor=vendor, model=model or None)

    def __str__(self) -> str:
        return f"{self.vendor}:{self.model}" if self.model else self.vendor


@dataclass(frozen=True)
class ProviderChoice:
    primary: ProviderSpec
    fallback: tuple[ProviderSpec, ...]

    @property
    def chain(self) -> tuple[ProviderSpec, ...]:
        return (self.primary, *self.fallback)

    @classmethod
    def from_json(cls, kind: Kind, data: dict[str, Any]) -> "ProviderChoice":
        return cls(
            primary=ProviderSpec.parse(kind, data["provider"]),
            fallback=tuple(ProviderSpec.parse(kind, s) for s in data["fallback"]),
        )

    def to_json(self) -> dict[str, Any]:
        return {"provider": str(self.primary), "fallback": [str(s) for s in self.fallback]}


@dataclass(frozen=True)
class ResolvedVoice:
    """Explicit providers for every kind. Stored on the agent version at publish."""

    stt: ProviderChoice
    llm: ProviderChoice
    tts: ProviderChoice
    preset: str | None = None
    llm_temperature: float | None = None

    def choice(self, kind: Kind) -> ProviderChoice:
        choice: ProviderChoice = getattr(self, kind)
        return choice

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {k: self.choice(k).to_json() for k in KINDS}
        out["preset"] = self.preset
        if self.llm_temperature is not None:
            out["llm"]["temperature"] = self.llm_temperature
        return out

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ResolvedVoice":
        return cls(
            stt=ProviderChoice.from_json("stt", data["stt"]),
            llm=ProviderChoice.from_json("llm", data["llm"]),
            tts=ProviderChoice.from_json("tts", data["tts"]),
            preset=data.get("preset"),
            llm_temperature=data["llm"].get("temperature"),
        )


# Platform presets. Data, not code paths: editing one affects only agent versions published after
# the edit (published versions store their resolved providers). Every fallback uses a different
# vendor than its primary (enforced by tests).
PRESETS: dict[str, dict[str, Any]] = {
    "india-standard": {
        "stt": {"provider": "sarvam", "fallback": ["deepgram:nova-3"]},
        "llm": {"provider": "openai:gpt-4.1-mini", "fallback": ["gemini:gemini-2.5-flash"]},
        "tts": {
            "provider": "sarvam:priya",
            "fallback": ["cartesia:4459a9a5-69d6-4680-b970-e13dc51845b6"],
        },
    },
}


class UnknownPresetError(ValueError):
    pass


def resolve_voice(voice: dict[str, Any]) -> ResolvedVoice:
    """Turn the agent config `voice` block into explicit providers.

    Explicit stt/llm/tts entries override the preset per kind. Assumes the config already passed
    `validate_agent_config` (which also rejects unknown presets).
    """
    preset_name: str | None = voice.get("preset")
    merged: dict[str, Any] = {}
    if preset_name is not None:
        if preset_name not in PRESETS:
            raise UnknownPresetError(f"unknown voice preset '{preset_name}'")
        merged.update(PRESETS[preset_name])
    for kind in KINDS:
        if kind in voice:
            merged[kind] = voice[kind]
    missing = [k for k in KINDS if k not in merged]
    if missing:
        raise ValueError(f"voice has no provider for: {', '.join(missing)}")
    temperature = voice.get("llm", {}).get("temperature")
    return ResolvedVoice(
        stt=ProviderChoice.from_json("stt", merged["stt"]),
        llm=ProviderChoice.from_json("llm", merged["llm"]),
        tts=ProviderChoice.from_json("tts", merged["tts"]),
        preset=preset_name,
        llm_temperature=temperature,
    )
