from pathlib import Path
from collections.abc import Mapping
from typing import cast

import pytest
from openai.types.responses import Response, ResponseFunctionToolCall
from pydantic import BaseModel

from hydrangea.context import Context
from hydrangea.gateway import GatewayType
from hydrangea.message import FunctionReply, Message, Role, ToolCall
from hydrangea.openai.context import OpenAIContext


class _ToolReply(BaseModel):
    value: int


def test_openai_context_converts_messages_and_function_replies() -> None:
    native = OpenAIContext()
    context = Context(GatewayType.openai, native=native)
    context.emplace_message(Message(role=Role.user, content="question"))
    context.emplace_message(Message(role=Role.assistant, content="answer"))
    context.emplace_function_replies([
        FunctionReply(call_id="call-1", name="tool_one", content=_ToolReply(value=7)),
        FunctionReply(call_id="call-2", name="tool_two", content=_ToolReply(value=9)),
    ])

    assert native.input == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
        {"type": "function_call_output", "call_id": "call-1", "output": '{"value":7}'},
        {"type": "function_call_output", "call_id": "call-2", "output": '{"value":9}'},
    ]
    assert context.latest_tool_calls() is None


def test_openai_context_validates_all_reply_ids_before_appending() -> None:
    native = OpenAIContext()
    context = Context(GatewayType.openai, native=native)
    with pytest.raises(ValueError, match="require a tool call ID"):
        context.emplace_function_replies([
            FunctionReply(call_id="call-1", name="valid", content=_ToolReply(value=1)),
            FunctionReply(call_id=None, name="invalid", content=_ToolReply(value=2)),
        ])
    assert native.contents == []


def test_openai_context_preserves_all_output_and_tool_calls(response: Response) -> None:
    native = OpenAIContext()
    context = Context(GatewayType.openai, native=native)
    context.push_back(response)

    assert native.contents[0] is response
    assert len(context) == 1
    assert native.input == [
        item.model_dump(mode="json", exclude_none=True) for item in response.output
    ]
    assert cast(Mapping[str, object], native.input[0])["encrypted_content"] == "encrypted-reasoning"
    assert cast(Mapping[str, object], native.input[-1])["phase"] == "final_answer"
    assert context.latest_tool_calls() == [
        ToolCall(call_id="call-1", name="lookup", arguments={"query": "hydrangea"}),
        ToolCall(call_id="call-2", name="count", arguments={"value": 2}),
    ]


def test_openai_reasoning_survives_disk_restore_and_context_slicing(
    response: Response, tmp_path: Path,
) -> None:
    snapshot = tmp_path / "response.json"
    _ = snapshot.write_text(response.model_dump_json(), encoding="utf-8")
    restored = Response.model_validate_json(snapshot.read_text(encoding="utf-8"))
    native = OpenAIContext([{"role": "user", "content": "question"}, restored])
    original_input = native.input
    assert native[:][1] is restored
    assert native.detach_tail(0) == ()
    tail = native.detach_tail(1)
    assert tail == (restored,)
    assert native.input == [{"role": "user", "content": "question"}]
    native.push_back(tail[0])
    assert native.input == original_input
    assert cast(Mapping[str, object], native.input[1])["encrypted_content"] == "encrypted-reasoning"
    assert native.last_tool_calls() is not None
    assert native.pop_back() is restored
    assert native.last_tool_calls() is None


@pytest.mark.parametrize("arguments", ["not json", "[]", "null", '"text"'])
def test_openai_context_rejects_invalid_tool_arguments(
    response: Response, arguments: str,
) -> None:
    call = response.output[1]
    assert isinstance(call, ResponseFunctionToolCall)
    call.arguments = arguments
    with pytest.raises(ValueError, match="tool arguments"):
        _ = OpenAIContext([response]).last_tool_calls()


def test_openai_context_rejects_invalid_content_and_tail_lengths() -> None:
    native = OpenAIContext()
    with pytest.raises(TypeError, match="requires a Response"):
        native.push_back(object())
    with pytest.raises(TypeError, match="requires a Response"):
        _ = OpenAIContext([object()])  # type: ignore[list-item]
    for length in (-1, 1):
        with pytest.raises(ValueError, match="Invalid tail length"):
            _ = native.detach_tail(length)
    assert native.last_tool_calls() is None


def test_openai_context_returns_a_shallow_contents_snapshot(response: Response) -> None:
    native = OpenAIContext([response])
    snapshot = native.contents
    snapshot.clear()
    assert native.contents == [response]
