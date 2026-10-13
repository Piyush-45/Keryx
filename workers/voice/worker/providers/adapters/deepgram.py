from pipecat.services.deepgram.stt import DeepgramSTTService, DeepgramSTTSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> DeepgramSTTService:
    settings = DeepgramSTTSettings(model=spec.model or "nova-3", language=Language(ctx.language))
    return DeepgramSTTService(api_key=api_key, settings=settings)


ADAPTER = Adapter(kind="stt", vendor="deepgram", factory=_build)
