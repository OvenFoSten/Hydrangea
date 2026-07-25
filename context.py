from typing import TypeAlias

from .gateway import GatewayType
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

AsterNativeContext: TypeAlias = GeminiContext
AsterNativeResponse: TypeAlias = GeminiResponse


def _unsupported_gateway_type(gateway_type: object) -> TypeError:
    return TypeError(
        "Unsupported gateway type: "
        f"{gateway_type!r}"
    )


def _native_context_type_for_gateway(
    gateway_type: GatewayType,
) -> type[object]:
    candidate: object = gateway_type

    match candidate:
        case GatewayType.gemini:
            return GeminiContext

        case _:
            raise _unsupported_gateway_type(candidate)


def _unsupported_native_context(native: object) -> TypeError:
    return TypeError(
        "Unsupported native context: "
        f"{type(native).__name__}"
    )


def _native_context_type_mismatch(
    gateway_type: GatewayType,
    native: object,
) -> TypeError:
    native_type = _native_context_type_for_gateway(gateway_type)
    return TypeError(
        "Native context does not match "
        f"{gateway_type.name!r}: expected "
        f"{native_type.__name__}, got "
        f"{type(native).__name__}."
    )


def _unsupported_native_context_response_pair(
    native: object,
    response: object,
) -> TypeError:
    return TypeError(
        "Unsupported native context/response pair: "
        f"{type(native).__name__} <- "
        f"{type(response).__name__}."
    )


class AsterContext:
    _gateway_type: GatewayType
    _native: object

    def __init__(
        self,
        gateway_type: GatewayType,
        native: AsterNativeContext | None = None,
    ) -> None:
        candidate_type: object = gateway_type

        match candidate_type:
            case GatewayType() as checked_gateway_type:
                native_type = _native_context_type_for_gateway(
                    checked_gateway_type
                )
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
                native_type = _native_context_type_for_gateway(
                    checked_gateway_type
                )
                if not isinstance(
                    self._native,
                    native_type,
                ):
                    raise _native_context_type_mismatch(
                        checked_gateway_type,
                        self._native,
                    )

                return self._native

            case _:
                raise _unsupported_gateway_type(candidate_type)

    def push_back(
        self,
        response: AsterNativeResponse,
    ) -> None:
        native = self._checked_native()
        candidate_response: object = response

        match native, candidate_response:
            case (
                GeminiContext() as context,
                GeminiResponse() as gemini_response,
            ):
                context.push_back(gemini_response.content)

            case _:
                raise _unsupported_native_context_response_pair(
                    native,
                    candidate_response,
                )

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
    def gateway_type(self) -> GatewayType:
        return self._gateway_type

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
    "AsterNativeContext",
    "AsterNativeResponse",
    "AsterRole",
]
