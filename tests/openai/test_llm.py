# pyright: reportPrivateUsage=false

import json
from collections.abc import Mapping
from typing import cast

import httpx
from openai import OpenAI as OpenAIClient
from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel

from hydrangea.config import LLMConfig
from hydrangea.context import Context
from hydrangea.gateway import GatewayType
from hydrangea.instruction import SystemInstruction
from hydrangea.llm import LLM
from hydrangea.message import Message, Role
from hydrangea.openai.llm import OpenAI
from hydrangea.reasoning import ReasoningEffort
from hydrangea.tool import ToolDeclaration


class _ToolArgs(BaseModel):
    query: str


class _ToolReply(BaseModel):
    result: str


def _request_payload(
    request: httpx.Request,
) -> dict[str, object]:
    parsed = cast(object, json.loads(request.content))
    assert isinstance(parsed, dict)
    return dict(cast(Mapping[str, object], parsed))


def test_openai_llm_builds_chat_completion_request() -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(_request_payload(request))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 0,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "logprobs": None,
                        "message": {
                            "role": "assistant",
                            "content": "done",
                        },
                    }
                ],
            },
        )

    llm = LLM(
        gateway_type=GatewayType.openai,
        config=LLMConfig(
            api_key="test-key",
            model_name="test-model",
            base_url="https://example.test/v1",
        ),
        instruction=SystemInstruction("Follow the instruction."),
    )
    native = llm._native
    assert isinstance(native, OpenAI)
    native._client = OpenAIClient(
        api_key="test-key",
        base_url="https://example.test/v1",
        http_client=httpx.Client(
            transport=httpx.MockTransport(handler)
        ),
    )

    context = Context(GatewayType.openai)
    context.emplace_message(
        Message(role=Role.user, content="Run the tool.")
    )
    declaration = ToolDeclaration(
        name="lookup",
        description="Look up a value.",
        args_schema=_ToolArgs,
        reply_schema=_ToolReply,
    )

    content = llm.invoke(
        context=context,
        effort=ReasoningEffort.high,
        tool_declarations=[declaration],
    )

    assert isinstance(content, ChatCompletionMessage)
    assert content.content == "done"
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["model"] == "test-model"
    assert payload["reasoning_effort"] == "high"
    assert "temperature" not in payload

    messages = cast(
        list[dict[str, object]],
        payload["messages"],
    )
    assert messages == [
        {
            "role": "developer",
            "content": "Follow the instruction.",
        },
        {
            "role": "user",
            "content": "Run the tool.",
        },
    ]

    tools = cast(
        list[dict[str, object]],
        payload["tools"],
    )
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    function = cast(
        dict[str, object],
        tools[0]["function"],
    )
    assert function["name"] == "lookup"
    assert function["description"] == "Look up a value."
    assert isinstance(function["parameters"], dict)

    _ = llm.invoke(
        context=context,
        effort=ReasoningEffort.low,
        tool_declarations=[],
        temperature=0.25,
    )

    explicit_payload = payloads[1]
    assert explicit_payload["temperature"] == 0.25
    assert "tools" not in explicit_payload
