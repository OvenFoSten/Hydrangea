import os
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types
from pydantic import BaseModel

from ..tool import AsterTool
from .config import GeminiConfig
from .llm import Gemini, ReasoningEffort


class SmokeArguments(BaseModel):
    left: int
    right: int


class SmokeResult(BaseModel):
    total: int


def smoke_add(arguments: SmokeArguments) -> SmokeResult:
    return SmokeResult(total=arguments.left + arguments.right)


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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

    smoke_response = Gemini(
        config=smoke_config,
        tools=[smoke_tool],
    ).invoke(
        target=(
            "Call smoke_add exactly once with left=20 and right=22. "
            "Do not calculate the answer yourself."
        ),
        context=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text="Use the provided tool to complete the target."
                    )
                ],
            )
        ],
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

    smoke_arguments: dict[str, object] = {
        name: value
        for name, value in smoke_call.args.items()
    }
    smoke_result = smoke_tool.invoke(smoke_arguments)

    if not isinstance(smoke_result, SmokeResult):
        raise AssertionError(
            "Smoke test failed: AsterTool returned an unexpected model."
        )
    if smoke_result.total != 42:
        raise AssertionError(
            f"Smoke test failed: expected 42, got {smoke_result.total}."
        )

    print("Gemini function call:", smoke_call)
    print("AsterTool result:", smoke_result.model_dump(mode="json"))
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
