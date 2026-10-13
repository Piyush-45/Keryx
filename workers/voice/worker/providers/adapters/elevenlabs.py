from pipecat.services.elevenlabs.tts import ElevenLabsTTSService, ElevenLabsTTSSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> ElevenLabsTTSService:
    settings = ElevenLabsTTSSettings(voice=spec.model, language=Language(ctx.language))
    return ElevenLabsTTSService(api_key=api_key, settings=settings)


ADAPTER = Adapter(kind="tts", vendor="elevenlabs", factory=_build)
