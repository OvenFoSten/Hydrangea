from pydantic import BaseModel

from ..config import LLMConfig


class GeminiConfig(BaseModel):
    api_key: str
    model_name: str


def _llm_config_to_gemini_config(
    config: LLMConfig,
) -> GeminiConfig:
    return GeminiConfig(
        api_key=config.api_key,
        model_name=config.model_name,
    )


__all__ = ["GeminiConfig"]
