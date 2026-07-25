from pydantic import BaseModel


class AsterLLMConfig(BaseModel):
    api_key: str
    model_name: str
    base_url: str


__all__ = ["AsterLLMConfig"]
