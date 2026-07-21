from enum import Enum

from .gemini.context import (
    GeminiContext,
    aster_function_reply_turn_to_gemini_content,
    aster_message_to_gemini_content,
)
from .gemini.response import GeminiResponse
from .message import (
    AsterFunctionReply,
    AsterFunctionReplyTurn,
    AsterMessage,
    AsterRole,
)


class ContextType(Enum):
    gemini = GeminiContext


def _unsupported_context_type(context_type: object) -> TypeError:
    return TypeError(
        "Unsupported context type: "
        f"{context_type!r}"
    )


def _unsupported_native_context(native: object) -> TypeError:
    return TypeError(
        "Unsupported native context: "
        f"{type(native).__name__}"
    )


def _native_context_type_mismatch(
    context_type: ContextType,
    native: object,
) -> TypeError:
    return TypeError(
        "Native context does not match "
        f"{context_type.name!r}: expected "
        f"{context_type.value.__name__}, got "
        f"{type(native).__name__}."
    )


class AsterContext:
    _type: ContextType
    _native: object

    def __init__(
        self,
        context_type: ContextType,
        native: GeminiContext | None = None,
    ) -> None:
        candidate_type: object = context_type

        match candidate_type:
            case ContextType() as checked_type:
                native_type = checked_type.value
                candidate_native: object = (
                    native_type()
                    if native is None
                    else native
                )
                if not isinstance(
                    candidate_native,
                    native_type,
                ):
                    raise _native_context_type_mismatch(
                        checked_type,
                        candidate_native,
                    )

                self._type = checked_type
                self._native = candidate_native

            case _:
                raise _unsupported_context_type(candidate_type)

    def _checked_native(self) -> object:
        candidate_type: object = self._type

        match candidate_type:
            case ContextType() as checked_type:
                native_type = checked_type.value
                if not isinstance(
                    self._native,
                    native_type,
                ):
                    raise _native_context_type_mismatch(
                        checked_type,
                        self._native,
                    )

                return self._native

            case _:
                raise _unsupported_context_type(candidate_type)

    def push_back(self, response: GeminiResponse) -> None:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                context.push_back(response.content)

            case _:
                raise _unsupported_native_context(native)

    def emplace_message(self, message: AsterMessage) -> None:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                context.push_back(
                    aster_message_to_gemini_content(message)
                )

            case _:
                raise _unsupported_native_context(native)

    def emplace_function_replies(
        self,
        turn: AsterFunctionReplyTurn,
    ) -> None:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                context.push_back(
                    aster_function_reply_turn_to_gemini_content(
                        turn
                    )
                )

            case _:
                raise _unsupported_native_context(native)

    def pop_back(self) -> None:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                _ = context.pop_back()

            case _:
                raise _unsupported_native_context(native)

    @property
    def context_type(self) -> ContextType:
        return self._type

    @property
    def gemini(self) -> GeminiContext:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                return context

            case _:
                raise _unsupported_native_context(native)

    def __len__(self) -> int:
        native = self._checked_native()

        match native:
            case GeminiContext() as context:
                return len(context)

            case _:
                raise _unsupported_native_context(native)


__all__ = [
    "AsterContext",
    "AsterFunctionReply",
    "AsterFunctionReplyTurn",
    "AsterMessage",
    "AsterRole",
    "ContextType",
]
