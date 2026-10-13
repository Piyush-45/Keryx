from pipecat.services.sarvam.tts import SarvamTTSService, SarvamTTSSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> SarvamTTSService:
    settings = SarvamTTSSettings(voice=spec.model, language=Language(ctx.language))
    return SarvamTTSService(api_key=api_key, settings=settings)


ADAPTER = Adapter(kind="tts", vendor="sarvam", factory=_build)
