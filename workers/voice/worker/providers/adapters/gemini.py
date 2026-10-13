from typing import Any

from pipecat.services.google.llm import GoogleLLMService, GoogleLLMSettings

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext

DEFAULT_MODEL = "gemini-2.5-flash"


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> GoogleLLMService:
    settings: dict[str, Any] = {"model": spec.model or DEFAULT_MODEL}
    if ctx.llm_temperature is not None:
        settings["temperature"] = ctx.llm_temperature
    return GoogleLLMService(api_key=api_key, settings=GoogleLLMSettings(**settings))


ADAPTER = Adapter(kind="llm", vendor="gemini", factory=_build)
