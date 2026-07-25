from enum import Enum
from typing import TypeAlias

from .config import AsterLLMConfig
from .context import AsterContext, AsterNativeContent
from .gateway import GatewayType
from .gemini.config import (
    _aster_llm_config_to_gemini_config,
)
from .gemini.llm import (
    Gemini,
    ReasoningEffort as GeminiReasoningEffort,
)
from .tool import AsterTool

_AsterNativeLLM: TypeAlias = Gemini


class ReasoningEffort(Enum):
    minimal = "minimal"
    low = "low"
    medium = "medium"
    high = "high"


def _unsupported_gateway_type(gateway_type: object) -> TypeError:
    return TypeError(
        "Unsupported gateway type: "
        f"{gateway_type!r}"
    )


def _native_llm_type_for_gateway(
    gateway_type: GatewayType,
) -> type[object]:
    candidate: object = gateway_type

    match candidate:
        case GatewayType.gemini:
            return Gemini

        case _:
            raise _unsupported_gateway_type(candidate)


def _unsupported_reasoning_effort(
    effort: object,
) -> TypeError:
    return TypeError(
        "Unsupported reasoning effort: "
        f"{effort!r}"
    )


def _reasoning_effort_to_gemini_reasoning_effort(
    effort: ReasoningEffort,
) -> GeminiReasoningEffort:
    candidate: object = effort

    match candidate:
        case ReasoningEffort.minimal:
            return GeminiReasoningEffort.minimal

        case ReasoningEffort.low:
            return GeminiReasoningEffort.low

        case ReasoningEffort.medium:
            return GeminiReasoningEffort.medium

        case ReasoningEffort.high:
            return GeminiReasoningEffort.high

        case _:
            raise _unsupported_reasoning_effort(candidate)


def _native_llm_type_mismatch(
    gateway_type: GatewayType,
    native: object,
) -> TypeError:
    native_type = _native_llm_type_for_gateway(gateway_type)
    return TypeError(
        "Native LLM does not match "
        f"{gateway_type.name!r}: expected "
        f"{native_type.__name__}, got "
        f"{type(native).__name__}."
    )


def _llm_context_gateway_type_mismatch(
    llm_gateway_type: GatewayType,
    context_gateway_type: GatewayType,
) -> TypeError:
    return TypeError(
        "LLM gateway type does not match Context: "
        f"{llm_gateway_type.name!r} != "
        f"{context_gateway_type.name!r}."
    )


class AsterLLM:
    _gateway_type: GatewayType
    _native: _AsterNativeLLM
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
                gemini_config = (
                    _aster_llm_config_to_gemini_config(config)
                )
                native = Gemini(
                    config=gemini_config,
                    tools=checked_tools,
                )

                self._gateway_type = GatewayType.gemini
                self._native = native
                self._tools = checked_tools

            case _:
                raise _unsupported_gateway_type(candidate_type)

    def invoke(
        self,
        target: str,
        context: AsterContext,
        effort: ReasoningEffort,
    ) -> AsterNativeContent:
        if context.gateway_type is not self._gateway_type:
            raise _llm_context_gateway_type_mismatch(
                self._gateway_type,
                context.gateway_type,
            )

        candidate_type: object = self._gateway_type
        candidate_native: object = self._native

        match candidate_type, candidate_native:
            case GatewayType.gemini, Gemini() as gemini:
                return gemini.invoke(
                    target=target,
                    context=context.gemini,
                    effort=(
                        _reasoning_effort_to_gemini_reasoning_effort(
                            effort
                        )
                    ),
                )

            case GatewayType() as checked_gateway_type, _:
                raise _native_llm_type_mismatch(
                    checked_gateway_type,
                    candidate_native,
                )

            case _:
                raise _unsupported_gateway_type(candidate_type)

    @property
    def gateway_type(self) -> GatewayType:
        return self._gateway_type

    @property
    def tools(self) -> list[AsterTool]:
        return self._tools.copy()


__all__ = [
    "AsterLLM",
    "ReasoningEffort",
]
