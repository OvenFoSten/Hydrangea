from collections.abc import Sequence
from typing import Protocol, TypeAlias

from google.genai import types
from typing_extensions import assert_never

from ..gateway import GatewayType
from ..gemini.context import GeminiContext
from ..message import (
    FunctionReply,
    FunctionReplyTurn,
    Message,
    Role,
    ToolCall,
)

NativeContext: TypeAlias = GeminiContext
NativeContent: TypeAlias = types.Content


class ContextImplementation(Protocol):
    def push_back(self, content: object) -> None:
        ...

    def emplace_message(self, message: Message) -> None:
        ...

    def emplace_function_reply_turn(
        self,
        turn: FunctionReplyTurn,
    ) -> None:
        ...

    def pop_back(self) -> object:
        ...

    def last_tool_calls(self) -> list[ToolCall] | None:
        ...

    def __len__(self) -> int:
        ...


class Context:
    _gateway_type: GatewayType
    _native: ContextImplementation

    def __init__(
        self,
        gateway_type: GatewayType,
        native: NativeContext | None = None,
    ) -> None:
        match gateway_type:
            case GatewayType.gemini:
                if native is None:
                    context = GeminiContext()
                # TODO: Remove ignore when have Another Provider
                elif isinstance(native, GeminiContext):  # pyright: ignore[reportUnnecessaryIsInstance]
                    context = native
                else:
                    assert_never(native)

                self._gateway_type = GatewayType.gemini
                self._native = context

            case _:
                assert_never(gateway_type)

    def push_back(
        self,
        content: NativeContent,
    ) -> None:
        self._native.push_back(content)

    def emplace_message(self, message: Message) -> None:
        self._native.emplace_message(message)

    def emplace_function_replies(
        self,
        replies: Sequence[FunctionReply],
    ) -> None:
        turn = FunctionReplyTurn(
            replies=tuple(replies)
        )
        self._native.emplace_function_reply_turn(turn)

    def pop_back(self) -> None:
        _ = self._native.pop_back()

    def latest_tool_calls(self) -> list[ToolCall] | None:
        return self._native.last_tool_calls()

    @property
    def gateway_type(self) -> GatewayType:
        return self._gateway_type

    @property
    def implementation(self) -> ContextImplementation:
        return self._native

    def __len__(self) -> int:
        return len(self._native)


__all__ = [
    "Context",
    "FunctionReply",
    "Message",
    "NativeContent",
    "NativeContext",
    "Role",
    "ToolCall",
]
