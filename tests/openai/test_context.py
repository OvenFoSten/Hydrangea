# pyright: reportPrivateUsage=false

from pydantic import BaseModel
import pytest
from openai.types.chat import (
    ChatCompletionMessage,
    ChatCompletionMessageFunctionToolCall,
)
from openai.types.chat.chat_completion_message_function_tool_call import (
    Function as OpenAIFunctionCall,
)

from hydrangea.context import Context
from hydrangea.gateway import GatewayType
from hydrangea.message import (
    FunctionReply,
    Message,
    Role,
    ToolCall,
)
from hydrangea.openai.context import OpenAIContext


class _ToolReply(BaseModel):
    value: int


def test_openai_context_converts_messages_and_function_replies() -> None:
    native = OpenAIContext()
    context = Context(
        gateway_type=GatewayType.openai,
        native=native,
    )

    context.emplace_message(
        Message(role=Role.user, content="question")
    )
    context.emplace_message(
        Message(role=Role.assistant, content="answer")
    )
    context.emplace_function_replies(
        [
            FunctionReply(
                call_id="call-1",
                name="tool_one",
                content=_ToolReply(value=7),
            ),
            FunctionReply(
                call_id="call-2",
                name="tool_two",
                content=_ToolReply(value=9),
            ),
        ]
    )

    assert native.messages == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": '{"value":7}',
        },
        {
            "role": "tool",
            "tool_call_id": "call-2",
            "content": '{"value":9}',
        },
    ]


def test_openai_context_requires_function_reply_call_id() -> None:
    native = OpenAIContext()
    context = Context(
        gateway_type=GatewayType.openai,
        native=native,
    )

    with pytest.raises(
        ValueError,
        match="require a tool call ID",
    ):
        context.emplace_function_replies(
            [
                FunctionReply(
                    call_id=None,
                    name="tool",
                    content=_ToolReply(value=1),
                )
            ]
        )

    assert native.contents == []


def test_openai_context_preserves_native_message_and_tool_calls() -> None:
    native = OpenAIContext()
    context = Context(
        gateway_type=GatewayType.openai,
        native=native,
    )
    message = ChatCompletionMessage(
        role="assistant",
        content=None,
        tool_calls=[
            ChatCompletionMessageFunctionToolCall(
                id="call-1",
                type="function",
                function=OpenAIFunctionCall(
                    name="lookup",
                    arguments='{"query":"hydrangea"}',
                ),
            ),
            ChatCompletionMessageFunctionToolCall(
                id="call-2",
                type="function",
                function=OpenAIFunctionCall(
                    name="count",
                    arguments='{"value":2}',
                ),
            ),
        ],
    )

    context.push_back(message)

    assert native.contents == [message]
    assert native.messages == [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup",
                        "arguments": '{"query":"hydrangea"}',
                    },
                },
                {
                    "id": "call-2",
                    "type": "function",
                    "function": {
                        "name": "count",
                        "arguments": '{"value":2}',
                    },
                },
            ],
        }
    ]
    assert context.latest_tool_calls() == [
        ToolCall(
            call_id="call-1",
            name="lookup",
            arguments={"query": "hydrangea"},
        ),
        ToolCall(
            call_id="call-2",
            name="count",
            arguments={"value": 2},
        )
    ]
