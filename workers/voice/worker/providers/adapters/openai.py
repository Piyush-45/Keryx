from typing import Any

from pipecat.services.openai.base_llm import OpenAILLMSettings
from pipecat.services.openai.llm import OpenAILLMService

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext

DEFAULT_MODEL = "gpt-4.1-mini"


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> OpenAILLMService:
    settings: dict[str, Any] = {"model": spec.model or DEFAULT_MODEL}
    if ctx.llm_temperature is not None:
        settings["temperature"] = ctx.llm_temperature
    return OpenAILLMService(api_key=api_key, settings=OpenAILLMSettings(**settings))


ADAPTER = Adapter(kind="llm", vendor="openai", factory=_build)
