from typing import Protocol

from .config import AsterLLMConfig
from .context import (
    AsterContext,
    AsterNativeContent,
    ContextImplementation,
)
from .gateway import GatewayType
from .gemini.llm import Gemini
from .reasoning import ReasoningEffort
from .tool import AsterToolDeclaration


class _LLMImplementation(Protocol):
    @property
    def gateway_type(self) -> GatewayType:
        ...

    def invoke(
        self,
        target: str,
        context: ContextImplementation,
        effort: ReasoningEffort,
        tool_declarations: list[AsterToolDeclaration],
    ) -> AsterNativeContent:
        ...


class AsterLLM:
    _native: _LLMImplementation

    def __init__(
        self,
        gateway_type: GatewayType,
        config: AsterLLMConfig,
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
        context: AsterContext,
        effort: ReasoningEffort,
        tool_declarations: list[AsterToolDeclaration],
    ) -> AsterNativeContent:
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
    "AsterLLM",
    "ReasoningEffort",
]
