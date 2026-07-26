from typing import Protocol, TypeAlias

from google.genai import types

from .gateway import GatewayType
from .gemini.context import GeminiContext
from .message import (
    AsterFunctionReply,
    AsterFunctionReplyTurn,
    AsterMessage,
    AsterRole,
    AsterToolCall,
)

AsterNativeContext: TypeAlias = GeminiContext
AsterNativeContent: TypeAlias = types.Content


class _ContextImplementation(Protocol):
    def push_back(self, content: object) -> None:
        ...

    def emplace_message(self, message: AsterMessage) -> None:
        ...

    def emplace_function_replies(
        self,
        turn: AsterFunctionReplyTurn,
    ) -> None:
        ...

    def pop_back(self) -> object:
        ...

    def last_tool_calls(self) -> list[AsterToolCall] | None:
        ...

    def __len__(self) -> int:
        ...


class AsterContext:
    _gateway_type: GatewayType
    _native: _ContextImplementation

    def __init__(
        self,
        gateway_type: GatewayType,
        native: AsterNativeContext | None = None,
    ) -> None:
        candidate_type: object = gateway_type
        candidate_native: object = native

        match candidate_type:
            case GatewayType.gemini:
                if candidate_native is None:
                    context = GeminiContext()
                elif isinstance(candidate_native, GeminiContext):
                    context = candidate_native
                else:
                    raise TypeError(
                        "Native context does not match 'gemini': "
                        "expected GeminiContext, got "
                        f"{type(candidate_native).__name__}."
                    )

                self._gateway_type = GatewayType.gemini
                self._native = context

            case _:
                raise TypeError(
                    "Unsupported gateway type: "
                    f"{candidate_type!r}"
                )

    def push_back(
        self,
        content: AsterNativeContent,
    ) -> None:
        self._native.push_back(content)

    def emplace_message(self, message: AsterMessage) -> None:
        self._native.emplace_message(message)

    def emplace_function_replies(
        self,
        turn: AsterFunctionReplyTurn,
    ) -> None:
        self._native.emplace_function_replies(turn)

    def pop_back(self) -> None:
        _ = self._native.pop_back()

    def last_tool_calls(self) -> list[AsterToolCall] | None:
        return self._native.last_tool_calls()

    @property
    def gateway_type(self) -> GatewayType:
        return self._gateway_type

    @property
    def gemini(self) -> GeminiContext:
        if not isinstance(self._native, GeminiContext):
            raise TypeError(
                "Context implementation is not GeminiContext: "
                f"{type(self._native).__name__}."
            )

        return self._native

    def __len__(self) -> int:
        return len(self._native)


__all__ = [
    "AsterContext",
    "AsterFunctionReply",
    "AsterFunctionReplyTurn",
    "AsterMessage",
    "AsterNativeContent",
    "AsterNativeContext",
    "AsterRole",
    "AsterToolCall",
]
