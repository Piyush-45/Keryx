"""One module per vendor and kind. The only modules allowed to import vendor services."""

from worker.providers.adapters import (
    anthropic,
    cartesia,
    deepgram,
    elevenlabs,
    gemini,
    openai,
    sarvam_stt,
    sarvam_tts,
)
from worker.providers.base import Adapter

ALL_ADAPTERS: tuple[Adapter, ...] = (
    deepgram.ADAPTER,
    sarvam_stt.ADAPTER,
    openai.ADAPTER,
    gemini.ADAPTER,
    anthropic.ADAPTER,
    cartesia.ADAPTER,
    elevenlabs.ADAPTER,
    sarvam_tts.ADAPTER,
)
