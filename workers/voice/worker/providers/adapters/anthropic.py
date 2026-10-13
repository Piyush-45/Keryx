from typing import Any

from pipecat.services.anthropic.llm import AnthropicLLMService, AnthropicLLMSettings

from vp_shared.providers import ProviderSpec
from worker.providers.base import Adapter, BuildContext

DEFAULT_MODEL = "claude-haiku-5-5"


def _build(spec: ProviderSpec, api_key: str, ctx: BuildContext) -> AnthropicLLMService:
    settings: dict[str, Any] = {"model": spec.model or DEFAULT_MODEL}
    if ctx.llm_temperature is not None:
        settings["temperature"] = ctx.llm_temperature
    return AnthropicLLMService(api_key=api_key, settings=AnthropicLLMSettings(**settings))


ADAPTER = Adapter(kind="llm", vendor="anthropic", factory=_build)
