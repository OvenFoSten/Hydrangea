import json
from collections.abc import Iterable, Mapping
from typing import TypeAlias, cast

from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageCustomToolCallParam,
    ChatCompletionMessageFunctionToolCall,
    ChatCompletionMessageFunctionToolCallParam,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCallUnionParam,
    ChatCompletionToolMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_custom_tool_call import (
    ChatCompletionMessageCustomToolCall,
)
from typing_extensions import assert_never

from ..message import (
    FunctionReplyTurn,
    Message,
    Role,
    ToolCall,
)


OpenAIContextContent: TypeAlias = (
    ChatCompletionMessage
    | ChatCompletionMessageParam
)


def _function_tool_call_to_param(
    tool_call: ChatCompletionMessageFunctionToolCall,
) -> ChatCompletionMessageFunctionToolCallParam:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.function.name,
            "arguments": tool_call.function.arguments,
        },
    }


def _custom_tool_call_to_param(
    tool_call: ChatCompletionMessageCustomToolCall,
) -> ChatCompletionMessageCustomToolCallParam:
    return {
        "id": tool_call.id,
        "type": "custom",
        "custom": {
            "name": tool_call.custom.name,
            "input": tool_call.custom.input,
        },
    }


def _native_message_to_param(
    message: ChatCompletionMessage,
) -> ChatCompletionAssistantMessageParam:
    result = ChatCompletionAssistantMessageParam(
        role="assistant"
    )

    if message.content is not None:
        result["content"] = message.content
    if message.refusal is not None:
        result["refusal"] = message.refusal
    if message.audio is not None:
        result["audio"] = {"id": message.audio.id}
    if message.function_call is not None:
        result["function_call"] = {
            "name": message.function_call.name,
            "arguments": message.function_call.arguments,
        }
    if message.tool_calls:
        tool_calls: list[
            ChatCompletionMessageToolCallUnionParam
        ] = []
        for tool_call in message.tool_calls:
            match tool_call:
                case ChatCompletionMessageFunctionToolCall():
                    tool_calls.append(
                        _function_tool_call_to_param(tool_call)
                    )
                case ChatCompletionMessageCustomToolCall():
                    tool_calls.append(
                        _custom_tool_call_to_param(tool_call)
                    )
                case _:
                    assert_never(tool_call)

        result["tool_calls"] = tool_calls

    return result


def _function_tool_call_to_tool_call(
    tool_call: ChatCompletionMessageFunctionToolCall,
) -> ToolCall:
    try:
        parsed_arguments = cast(
            object,
            json.loads(tool_call.function.arguments),
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "OpenAI returned invalid JSON tool arguments for "
            f"{tool_call.function.name!r}."
        ) from error

    if not isinstance(parsed_arguments, dict):
        raise ValueError(
            "OpenAI returned non-object tool arguments for "
            f"{tool_call.function.name!r}."
        )

    arguments = dict(
        cast(Mapping[str, object], parsed_arguments)
    )
    return ToolCall(
        call_id=tool_call.id,
        name=tool_call.function.name,
        arguments=arguments,
    )


def message_to_openai_param(
    message: Message,
) -> ChatCompletionMessageParam:
    match message.role:
        case Role.user:
            user_message = ChatCompletionUserMessageParam(
                role="user",
                content=message.content,
            )
            return user_message

        case Role.assistant:
            assistant_message = (
                ChatCompletionAssistantMessageParam(
                    role="assistant",
                    content=message.content,
                )
            )
            return assistant_message

        case _:
            assert_never(message.role)


def function_reply_turn_to_openai_params(
    turn: FunctionReplyTurn,
) -> tuple[ChatCompletionToolMessageParam, ...]:
    messages: list[ChatCompletionToolMessageParam] = []
    for reply in turn.replies:
        if reply.call_id is None:
            raise ValueError(
                "OpenAI function replies require a tool call ID."
            )

        messages.append(
            ChatCompletionToolMessageParam(
                role="tool",
                tool_call_id=reply.call_id,
                content=reply.content.model_dump_json(),
            )
        )

    return tuple(messages)


class OpenAIContext:
    _contents: list[OpenAIContextContent]

    def __init__(
        self,
        contents: Iterable[OpenAIContextContent] | None = None,
    ) -> None:
        self._contents = list(contents or ())

    def push_back(self, content: object) -> None:
        if isinstance(content, ChatCompletionMessage):
            self._contents.append(content)
            return

        if isinstance(content, dict):
            self._contents.append(
                cast(ChatCompletionMessageParam, content)
            )
            return

        raise TypeError(
            "OpenAIContext requires a ChatCompletionMessage or "
            "ChatCompletionMessageParam, got "
            f"{type(content).__name__}."
        )

    def emplace_message(self, message: Message) -> None:
        self._contents.append(
            message_to_openai_param(message)
        )

    def emplace_function_reply_turn(
        self,
        turn: FunctionReplyTurn,
    ) -> None:
        messages = function_reply_turn_to_openai_params(turn)
        self._contents.extend(messages)

    def detach_tail(
        self,
        length: int,
    ) -> tuple[OpenAIContextContent, ...]:
        context_size = len(self._contents)
        if length < 0 or length > context_size:
            raise ValueError(
                "Invalid tail length: "
                f"length={length}, "
                f"context_size={context_size}."
            )

        tail_begin = context_size - length
        detached = tuple(self._contents[tail_begin:])
        del self._contents[tail_begin:]
        return detached

    def __getitem__(
        self,
        selection: slice,
    ) -> tuple[OpenAIContextContent, ...]:
        return tuple(self._contents[selection])

    def pop_back(self) -> OpenAIContextContent:
        return self._contents.pop()

    def last_tool_calls(self) -> list[ToolCall] | None:
        if not self._contents:
            return None

        content = self._contents[-1]
        if not isinstance(content, ChatCompletionMessage):
            return None
        if not content.tool_calls:
            return None

        tool_calls: list[ToolCall] = []
        for tool_call in content.tool_calls:
            match tool_call:
                case ChatCompletionMessageFunctionToolCall():
                    tool_calls.append(
                        _function_tool_call_to_tool_call(tool_call)
                    )
                case ChatCompletionMessageCustomToolCall():
                    raise TypeError(
                        "OpenAI custom tool calls are not supported."
                    )
                case _:
                    assert_never(tool_call)

        return tool_calls or None

    @property
    def contents(self) -> list[OpenAIContextContent]:
        return self._contents.copy()

    @property
    def messages(self) -> list[ChatCompletionMessageParam]:
        messages: list[ChatCompletionMessageParam] = []
        for content in self._contents:
            if isinstance(content, ChatCompletionMessage):
                messages.append(
                    _native_message_to_param(content)
                )
            else:
                messages.append(content)

        return messages

    def __len__(self) -> int:
        return len(self._contents)


__all__ = [
    "OpenAIContext",
    "OpenAIContextContent",
]
