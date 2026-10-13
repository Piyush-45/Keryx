from pipecat.services.cartesia.tts import CartesiaTTSService, CartesiaTTSSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> CartesiaTTSService:
    settings = CartesiaTTSSettings(voice=spec.model, language=Language(ctx.language))
    return CartesiaTTSService(api_key=api_key, settings=settings)


ADAPTER = Adapter(kind="tts", vendor="cartesia", factory=_build)
