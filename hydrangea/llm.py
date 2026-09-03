from typing import Protocol
from typing_extensions import assert_never

from .instruction import SystemInstruction
from .config import LLMConfig
from .context import (
    Context,
    NativeContent,
    ContextImplementation,
)
from .gateway import GatewayType
from .gemini.llm import Gemini
from .reasoning import ReasoningEffort
from .tool import ToolDeclaration


class _LLMImplementation(Protocol):
    @property
    def gateway_type(self) -> GatewayType:
        ...

    def invoke(
        self,
        context: ContextImplementation,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
        temperature:float | None
    ) -> NativeContent:
        ...


class LLM:
    _native: _LLMImplementation

    def __init__(
        self,
        gateway_type: GatewayType,
        config: LLMConfig,
        instruction:SystemInstruction,
    ) -> None:
        match gateway_type:
            case GatewayType.gemini:
                self._native = Gemini.from_llm_config(
                    config=config,
                    instruction=instruction,
                )

            case _:
                assert_never(gateway_type)

    def invoke(
        self,
        context: Context,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
        temperature:float | None = None
    ) -> NativeContent:
        return self._native.invoke(
            context=context.implementation,
            effort=effort,
            tool_declarations=tool_declarations,
            temperature=temperature
        )

    @property
    def gateway_type(self) -> GatewayType:
        return self._native.gateway_type

__all__ = [
    "LLM",
    "ReasoningEffort",
]
