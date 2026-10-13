from typing import Any

from pipecat.services.sarvam.stt import SarvamSTTService, SarvamSTTSettings
from pipecat.transcriptions.language import Language

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> SarvamSTTService:
    settings: dict[str, Any] = {"language": Language(ctx.language)}
    if spec.model:  # otherwise Pipecat's default Sarvam model
        settings["model"] = spec.model
    return SarvamSTTService(api_key=api_key, settings=SarvamSTTSettings(**settings))


ADAPTER = Adapter(kind="stt", vendor="sarvam", factory=_build)
