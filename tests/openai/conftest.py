import pytest
from openai.types.responses import (
    Response,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
)
from openai.types.responses.response_reasoning_item import Summary


@pytest.fixture
def response() -> Response:
    return Response(
        id="resp-test",
        created_at=0,
        model="test-model",
        object="response",
        parallel_tool_calls=True,
        tool_choice="auto",
        tools=[],
        status="completed",
        output=[
            ResponseReasoningItem(
                id="rs-test",
                type="reasoning",
                summary=[Summary(type="summary_text", text="Use both tools.")],
                encrypted_content="encrypted-reasoning",
            ),
            ResponseFunctionToolCall(
                id="fc-1",
                type="function_call",
                call_id="call-1",
                name="lookup",
                arguments='{"query":"hydrangea"}',
                status="completed",
            ),
            ResponseFunctionToolCall(
                id="fc-2",
                type="function_call",
                call_id="call-2",
                name="count",
                arguments='{"value":2}',
                status="completed",
            ),
            ResponseOutputMessage(
                id="msg-test",
                type="message",
                role="assistant",
                status="completed",
                phase="final_answer",
                content=[
                    ResponseOutputText(
                        type="output_text", text="done", annotations=[],
                    )
                ],
            ),
        ],
    )
