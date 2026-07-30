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
from .tool import AsterTool


class _LLMImplementation(Protocol):
    @property
    def gateway_type(self) -> GatewayType:
        ...

    def invoke(
        self,
        target: str,
        context: ContextImplementation,
        effort: ReasoningEffort,
    ) -> AsterNativeContent:
        ...


class AsterLLM:
    _native: _LLMImplementation
    _tools: list[AsterTool]

    def __init__(
        self,
        gateway_type: GatewayType,
        config: AsterLLMConfig,
        tools: list[AsterTool] | None = None,
    ) -> None:
        candidate_type: object = gateway_type
        checked_tools: list[AsterTool] = list(tools or [])

        match candidate_type:
            case GatewayType.gemini:
                self._native = Gemini.from_aster_config(
                    config=config,
                    tool_declarations=[
                        tool.declaration
                        for tool in checked_tools
                    ],
                )
                self._tools = checked_tools

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
    ) -> AsterNativeContent:
        return self._native.invoke(
            target=target,
            context=context.implementation,
            effort=effort,
        )

    @property
    def gateway_type(self) -> GatewayType:
        return self._native.gateway_type

    @property
    def tools(self) -> list[AsterTool]:
        return self._tools.copy()


__all__ = [
    "AsterLLM",
    "ReasoningEffort",
]
