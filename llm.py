from enum import Enum
from typing import TypeAlias

from .context import AsterContext, AsterNativeResponse
from .gemini.config import GeminiConfig
from .gemini.llm import Gemini, ReasoningEffort
from .tool import AsterTool

AsterNativeLLM: TypeAlias = Gemini


class LLMType(Enum):
    gemini = Gemini


def _unsupported_llm_type(llm_type: object) -> TypeError:
    return TypeError(
        "Unsupported LLM type: "
        f"{llm_type!r}"
    )


def _unsupported_native_llm(native: object) -> TypeError:
    return TypeError(
        "Unsupported native LLM: "
        f"{type(native).__name__}"
    )


def _native_llm_type_mismatch(
    llm_type: LLMType,
    native: object,
) -> TypeError:
    return TypeError(
        "Native LLM does not match "
        f"{llm_type.name!r}: expected "
        f"{llm_type.value.__name__}, got "
        f"{type(native).__name__}."
    )


def _gemini_config_required() -> TypeError:
    return TypeError(
        "Gemini LLM requires config when native is not provided."
    )


class AsterLLM:
    _type: LLMType
    _native: object

    def __init__(
        self,
        llm_type: LLMType,
        native: AsterNativeLLM | None = None,
        *,
        config: GeminiConfig | None = None,
        tools: list[AsterTool] | None = None,
    ) -> None:
        candidate_type: object = llm_type

        match candidate_type:
            case LLMType() as checked_type:
                native_type = checked_type.value
                candidate_native: object

                match checked_type:
                    case LLMType.gemini:
                        if native is None:
                            if config is None:
                                raise _gemini_config_required()
                            candidate_native = native_type(
                                config,
                                tools,
                            )
                        else:
                            candidate_native = native

                    case _:
                        raise _unsupported_llm_type(checked_type)

                if not isinstance(
                    candidate_native,
                    native_type,
                ):
                    raise _native_llm_type_mismatch(
                        checked_type,
                        candidate_native,
                    )

                self._type = checked_type
                self._native = candidate_native

            case _:
                raise _unsupported_llm_type(candidate_type)

    def _checked_native(self) -> object:
        candidate_type: object = self._type

        match candidate_type:
            case LLMType() as checked_type:
                native_type = checked_type.value
                if not isinstance(
                    self._native,
                    native_type,
                ):
                    raise _native_llm_type_mismatch(
                        checked_type,
                        self._native,
                    )

                return self._native

            case _:
                raise _unsupported_llm_type(candidate_type)

    def invoke(
        self,
        target: str,
        context: AsterContext,
        effort: ReasoningEffort,
    ) -> AsterNativeResponse:
        native = self._checked_native()

        match native:
            case Gemini() as gemini:
                return gemini.invoke(
                    target,
                    context.gemini,
                    effort,
                )

            case _:
                raise _unsupported_native_llm(native)

    @property
    def llm_type(self) -> LLMType:
        return self._type

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
    "LLMType",
    "ReasoningEffort",
]
