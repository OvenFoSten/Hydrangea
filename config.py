from pydantic import BaseModel


class LLMConfig(BaseModel):
    api_key: str
    model_name: str
    base_url: str


__all__ = ["LLMConfig"]
