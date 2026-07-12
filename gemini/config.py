from dataclasses import dataclass
from pydantic import BaseModel
#TODO: Use .config file to load api_key & model_name

class GeminiConfig(BaseModel):
    api_key: str
    model_name: str