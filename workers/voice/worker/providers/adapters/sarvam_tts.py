from pipecat.services.sarvam.tts import SarvamTTSService, SarvamTTSSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext

# Pinned, not Pipecat's default: Sarvam retired bulbul:v2 (its API rejects it) and voice ids are
# per model, so a silent model change would break every published sarvam voice.
MODEL = "bulbul:v3"


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> SarvamTTSService:
    settings = SarvamTTSSettings(model=MODEL, voice=spec.model, language=Language(ctx.language))
    return SarvamTTSService(api_key=api_key, settings=settings)


ADAPTER = Adapter(kind="tts", vendor="sarvam", factory=_build)
