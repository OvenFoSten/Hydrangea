from enum import Enum


class GatewayType(Enum):
    gemini = "gemini"
    openai = "openai"


__all__ = ["GatewayType"]
