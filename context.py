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


def _unsupported_native_context(native: object) -> TypeError:
    return TypeError(
        "Unsupported native context: "
        f"{type(native).__name__}"
    )


class AsterContext:
    _native: object

    def __init__(self, native: GeminiContext) -> None:
        self._native = native

    def push_back(self, response: GeminiResponse) -> None:
        match self._native:
            case GeminiContext() as context:
                context.push_back(response.content)

            case _:
                raise _unsupported_native_context(self._native)

    def emplace_message(self, message: AsterMessage) -> None:
        match self._native:
            case GeminiContext() as context:
                context.push_back(
                    aster_message_to_gemini_content(message)
                )

            case _:
                raise _unsupported_native_context(self._native)

    def emplace_function_replies(
        self,
        turn: AsterFunctionReplyTurn,
    ) -> None:
        match self._native:
            case GeminiContext() as context:
                context.push_back(
                    aster_function_reply_turn_to_gemini_content(
                        turn
                    )
                )

            case _:
                raise _unsupported_native_context(self._native)

    def pop_back(self) -> None:
        match self._native:
            case GeminiContext() as context:
                _ = context.pop_back()

            case _:
                raise _unsupported_native_context(self._native)

    @property
    def gemini(self) -> GeminiContext:
        match self._native:
            case GeminiContext() as context:
                return context

            case _:
                raise _unsupported_native_context(self._native)

    def __len__(self) -> int:
        match self._native:
            case GeminiContext() as context:
                return len(context)

            case _:
                raise _unsupported_native_context(self._native)


__all__ = [
    "AsterContext",
    "AsterFunctionReply",
    "AsterFunctionReplyTurn",
    "AsterMessage",
    "AsterRole",
]
