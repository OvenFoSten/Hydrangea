from enum import Enum
from typing import TypeAlias

from .context import AsterContext, AsterNativeResponse
from .gateway import GatewayType
from .gemini.config import GeminiConfig
from .gemini.llm import (
    Gemini,
    ReasoningEffort as GeminiReasoningEffort,
)
from .tool import AsterTool

AsterNativeLLM: TypeAlias = Gemini


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


def _unsupported_native_llm(native: object) -> TypeError:
    return TypeError(
        "Unsupported native LLM: "
        f"{type(native).__name__}"
    )


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


def _gemini_config_required() -> TypeError:
    return TypeError(
        "Gemini LLM requires config when native is not provided."
    )


class AsterLLM:
    _gateway_type: GatewayType
    _native: object

    def __init__(
        self,
        gateway_type: GatewayType,
        native: AsterNativeLLM | None = None,
        *,
        config: GeminiConfig | None = None,
        tools: list[AsterTool] | None = None,
    ) -> None:
        candidate_type: object = gateway_type

        match candidate_type:
            case GatewayType() as checked_gateway_type:
                native_type = _native_llm_type_for_gateway(
                    checked_gateway_type
                )
                candidate_native: object

                match checked_gateway_type:
                    case GatewayType.gemini:
                        if native is None:
                            if config is None:
                                raise _gemini_config_required()
                            candidate_native = Gemini(
                                config,
                                tools,
                            )
                        else:
                            candidate_native = native

                    case _:
                        raise _unsupported_gateway_type(
                            checked_gateway_type
                        )

                if not isinstance(
                    candidate_native,
                    native_type,
                ):
                    raise _native_llm_type_mismatch(
                        checked_gateway_type,
                        candidate_native,
                    )

                self._gateway_type = checked_gateway_type
                self._native = candidate_native

            case _:
                raise _unsupported_gateway_type(candidate_type)

    def _checked_native(self) -> object:
        candidate_type: object = self._gateway_type

        match candidate_type:
            case GatewayType() as checked_gateway_type:
                native_type = _native_llm_type_for_gateway(
                    checked_gateway_type
                )
                if not isinstance(
                    self._native,
                    native_type,
                ):
                    raise _native_llm_type_mismatch(
                        checked_gateway_type,
                        self._native,
                    )

                return self._native

            case _:
                raise _unsupported_gateway_type(candidate_type)

    def invoke(
        self,
        target: str,
        context: AsterContext,
        effort: ReasoningEffort,
    ) -> AsterNativeResponse:
        native = self._checked_native()

        if context.gateway_type is not self._gateway_type:
            raise _llm_context_gateway_type_mismatch(
                self._gateway_type,
                context.gateway_type,
            )

        match native:
            case Gemini() as gemini:
                return gemini.invoke(
                    target,
                    context.gemini,
                    _reasoning_effort_to_gemini_reasoning_effort(
                        effort
                    ),
                )

            case _:
                raise _unsupported_native_llm(native)

    @property
    def gateway_type(self) -> GatewayType:
        return self._gateway_type

    @property
    def gemini(self) -> Gemini:
        native = self._checked_native()

        match native:
            case Gemini() as gemini:
                return gemini

            case _:
                raise _unsupported_native_llm(native)


__all__ = [
    "AsterLLM",
    "AsterNativeLLM",
    "ReasoningEffort",
]
