from collections.abc import Iterable

from google.genai import types

from ..message import (
    AsterFunctionReplyTurn,
    AsterMessage,
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


class GeminiContext:
    _contents: list[types.Content]

    def __init__(
        self,
        contents: Iterable[types.Content] | None = None,
    ) -> None:
        self._contents = list(
            contents if contents is not None else ()
        )

    def push_back(self, content: types.Content) -> None:
        self._contents.append(content)

    def pop_back(self) -> types.Content:
        return self._contents.pop()

    @property
    def contents(self) -> list[types.Content]:
        return self._contents.copy()

    def __len__(self) -> int:
        return len(self._contents)
