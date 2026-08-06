from collections.abc import Iterable
from collections.abc import Mapping
from typing import cast

from google.genai import types

from ..message import (
    AsterFunctionReplyTurn,
    AsterMessage,
    AsterToolCall,
    AsterRole,
)


_GEMINI_ROLE_MAPPING: dict[AsterRole, str] = {
    AsterRole.user: "user",
    AsterRole.assistant: "model",
}


def aster_message_to_gemini_content(
    message: AsterMessage,
) -> types.Content:
    return types.Content(
        role=_GEMINI_ROLE_MAPPING[message.role],
        parts=[types.Part.from_text(text=message.content)],
    )


def aster_function_reply_turn_to_gemini_content(
    turn: AsterFunctionReplyTurn,
) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=reply.call_id,
                    name=reply.name,
                    response=reply.content.model_dump(mode="json"),
                )
            )
            for reply in turn.replies
        ],
    )


def gemini_function_call_to_aster_tool_call(
    function_call: types.FunctionCall,
) -> AsterToolCall:
    if function_call.name is None:
        raise ValueError("Gemini returned a function call without a name.")

    arguments: dict[str, object] = {}
    if function_call.args is not None:
        arguments = dict(
        cast(
            Mapping[str, object],
            function_call.args,
        ))

    return AsterToolCall(
        call_id=function_call.id,
        name=function_call.name,
        arguments=arguments,
    )


class GeminiContext:
    _contents: list[types.Content]

    def __init__(
        self,
        contents: Iterable[types.Content] | None = None,
    ) -> None:
        self._contents = []
        for content in contents if contents is not None else ():
            self.push_back(content)

    def push_back(self, content: object) -> None:
        if not isinstance(content, types.Content):
            raise TypeError(
                "GeminiContext requires types.Content, got "
                f"{type(content).__name__}."
            )

        self._contents.append(content)

    def emplace_message(self, message: AsterMessage) -> None:
        self.push_back(
            aster_message_to_gemini_content(message)
        )

    def emplace_function_reply_turn(
        self,
        turn: AsterFunctionReplyTurn,
    ) -> None:
        self.push_back(
            aster_function_reply_turn_to_gemini_content(turn)
        )

    def pop_back(self) -> types.Content:
        return self._contents.pop()

    def last_tool_calls(self) -> list[AsterToolCall] | None:
        if not self._contents:
            return None

        parts = self._contents[-1].parts
        if not parts:
            return None

        tool_calls: list[AsterToolCall] = []
        for part in parts:
            function_call = part.function_call
            if function_call is not None:
                tool_calls.append(
                    gemini_function_call_to_aster_tool_call(
                        function_call
                    )
                )

        return tool_calls or None

    @property
    def contents(self) -> list[types.Content]:
        return self._contents.copy()

    def __len__(self) -> int:
        return len(self._contents)
