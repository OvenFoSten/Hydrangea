from pydantic import BaseModel

from ..config import LLMConfig


class OpenAIConfig(BaseModel):
    api_key: str
    model_name: str
    base_url: str


def llm_config_to_openai_config(
    config: LLMConfig,
) -> OpenAIConfig:
    return OpenAIConfig(
        api_key=config.api_key,
        model_name=config.model_name,
        base_url=config.base_url,
    )


__all__ = ["OpenAIConfig"]
