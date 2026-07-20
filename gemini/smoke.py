import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from ..context import (
    AsterContext,
    AsterFunctionReply,
    AsterFunctionReplyTurn,
    AsterMessage,
    AsterRole,
)
from ..tool import AsterTool
from .config import GeminiConfig
from .context import GeminiContext
from .llm import Gemini, ReasoningEffort


class SmokeArguments(BaseModel):
    left: int
    right: int


class SmokeResult(BaseModel):
    total: int


def smoke_add(arguments: SmokeArguments) -> SmokeResult:
    return SmokeResult(total=arguments.left + arguments.right)


def main() -> None:
    _ = load_dotenv(Path(__file__).resolve().parents[2] / ".env")

    smoke_config = GeminiConfig(
        api_key=os.environ["ASTER_GEMINI_API_KEY"],
        model_name=os.environ["ASTER_GEMINI_MODEL_NAME"],
    )
    smoke_tool = AsterTool(
        name="smoke_add",
        description="Add two integers and return their total.",
        func=smoke_add,
        args_schema=SmokeArguments,
        return_schema=SmokeResult,
    )

    smoke_gemini = Gemini(
        config=smoke_config,
        tools=[smoke_tool],
    )
    smoke_context = AsterContext(GeminiContext())
    smoke_context.emplace_message(
        AsterMessage(
            role=AsterRole.user,
            content="Use the provided tool to complete the target.",
        )
    )
    smoke_target = (
        "Call smoke_add exactly once with left=20 and right=22. "
        "After receiving the function response, state the returned total."
    )

    smoke_response = smoke_gemini.invoke(
        target=smoke_target,
        context=smoke_context.gemini,
        effort=ReasoningEffort.minimal,
    )

    if not smoke_response.tool_calls:
        raise AssertionError(
            "Smoke test failed: Gemini returned no function call."
        )

    smoke_call = next(
        (
            call
            for call in smoke_response.tool_calls
            if call.name == smoke_tool.name
        ),
        None,
    )
    if smoke_call is None:
        raise AssertionError(
            "Smoke test failed: Gemini did not call smoke_add."
        )
    if smoke_call.args is None:
        raise AssertionError(
            "Smoke test failed: smoke_add received no arguments."
        )
    if smoke_call.id is None:
        raise AssertionError(
            "Smoke test failed: smoke_add function call has no ID."
        )

    smoke_arguments: dict[str, object] = {
        name: value
        for name, value in smoke_call.args.items()
    }
    expected_arguments: dict[str, object] = {
        "left": 20,
        "right": 22,
    }
    if smoke_arguments != expected_arguments:
        raise AssertionError(
            "Smoke test failed: unexpected smoke_add arguments: "
            f"{smoke_arguments}."
        )

    smoke_result = smoke_tool.invoke(smoke_arguments)

    if not isinstance(smoke_result, SmokeResult):
        raise AssertionError(
            "Smoke test failed: AsterTool returned an unexpected model."
        )
    if smoke_result.total != 42:
        raise AssertionError(
            f"Smoke test failed: expected 42, got {smoke_result.total}."
        )

    smoke_context.push_back(smoke_response)
    smoke_context.emplace_function_replies(
        AsterFunctionReplyTurn(
            replies=(
                AsterFunctionReply(
                    call_id=smoke_call.id,
                    name=smoke_tool.name,
                    content=smoke_result,
                ),
            )
        )
    )

    second_request_context = smoke_context.gemini.contents
    context_roles = [content.role for content in second_request_context]
    if context_roles != ["user", "model", "user"]:
        raise AssertionError(
            "Smoke test failed: unexpected context roles: "
            f"{context_roles}."
        )
    if second_request_context[1] is not smoke_response.content:
        raise AssertionError(
            "Smoke test failed: model Content was reconstructed."
        )

    reply_parts = second_request_context[2].parts
    if not reply_parts or reply_parts[0].function_response is None:
        raise AssertionError(
            "Smoke test failed: no Gemini FunctionResponse in context."
        )
    sent_reply = reply_parts[0].function_response
    if sent_reply.id != smoke_call.id:
        raise AssertionError(
            "Smoke test failed: FunctionResponse call ID was not preserved."
        )
    if sent_reply.name != smoke_tool.name:
        raise AssertionError(
            "Smoke test failed: FunctionResponse name was not preserved."
        )
    if sent_reply.response != {"total": 42}:
        raise AssertionError(
            "Smoke test failed: FunctionResponse payload was not preserved."
        )

    final_response = smoke_gemini.invoke(
        target=smoke_target,
        context=smoke_context.gemini,
        effort=ReasoningEffort.minimal,
    )
    if final_response.tool_calls:
        raise AssertionError(
            "Smoke test failed: Gemini called the tool more than once."
        )
    if "42" not in final_response.output:
        raise AssertionError(
            "Smoke test failed: final response did not contain 42: "
            f"{final_response.output!r}."
        )

    print("Gemini function call:", smoke_call)
    print("AsterTool result:", smoke_result.model_dump(mode="json"))
    print("Gemini final response:", final_response.output)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
