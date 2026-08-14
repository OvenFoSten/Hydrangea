from typing import Protocol

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
        target: str,
        context: ContextImplementation,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
    ) -> NativeContent:
        ...


class LLM:
    _native: _LLMImplementation

    def __init__(
        self,
        gateway_type: GatewayType,
        config: LLMConfig,
    ) -> None:
        candidate_type: object = gateway_type

        match candidate_type:
            case GatewayType.gemini:
                self._native = Gemini.from_aster_config(
                    config=config,
                )

            case _:
                raise TypeError(
                    "Unsupported gateway type: "
                    f"{candidate_type!r}"
                )

    def invoke(
        self,
        target: str,
        context: Context,
        effort: ReasoningEffort,
        tool_declarations: list[ToolDeclaration],
    ) -> NativeContent:
        return self._native.invoke(
            target=target,
            context=context.implementation,
            effort=effort,
            tool_declarations=tool_declarations,
        )

    @property
    def gateway_type(self) -> GatewayType:
        return self._native.gateway_type

__all__ = [
    "LLM",
    "ReasoningEffort",
]
