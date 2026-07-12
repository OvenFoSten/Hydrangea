from pydantic import BaseModel


class GeminiConfig(BaseModel):
    api_key: str
    model_name: str
