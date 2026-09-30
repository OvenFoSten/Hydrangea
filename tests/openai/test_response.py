import pytest
from openai.types.responses import (
    Response,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
)

from hydrangea.openai import OpenAIResponse


def test_openai_response_exposes_summary_text_and_native_tool_calls(response: Response) -> None:
    parsed = OpenAIResponse(response)
    assert parsed.content is response
    assert parsed.thoughts == ["Use both tools."]
    assert parsed.output == "done"
    assert parsed.tool_calls == response.output[1:3]


def test_openai_response_combines_text_without_exposing_reasoning_as_output(response: Response) -> None:
    message = response.output[-1]
    assert isinstance(message, ResponseOutputMessage)
    message.content.append(ResponseOutputText(type="output_text", text="!", annotations=[]))
    message.content.append(ResponseOutputRefusal(type="refusal", refusal="refused"))
    assert OpenAIResponse(response).output == "done!"


def test_openai_response_handles_reasoning_only_turn(response: Response) -> None:
    response.output = response.output[:1]
    parsed = OpenAIResponse(response)
    assert parsed.output == ""
    assert parsed.tool_calls is None
    assert parsed.thoughts == ["Use both tools."]


def test_openai_response_handles_tool_only_turn(response: Response) -> None:
    response.output = response.output[1:3]
    parsed = OpenAIResponse(response)
    assert parsed.output == ""
    assert parsed.thoughts is None
    assert parsed.tool_calls == response.output


def test_openai_response_optional_fields_for_text_only_turn(response: Response) -> None:
    response.output = response.output[-1:]
    parsed = OpenAIResponse(response)
    assert parsed.output == "done"
    assert parsed.thoughts is None
    assert parsed.tool_calls is None


def test_openai_response_rejects_empty_output(response: Response) -> None:
    response.output = []
    with pytest.raises(ValueError, match="No output from OpenAI"):
        _ = OpenAIResponse(response)
