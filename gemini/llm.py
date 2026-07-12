from dataclasses import dataclass
from pydantic import BaseModel
from enum import Enum
from typing import Callable

from google import genai
from google.genai import types


from .config import GeminiConfig
from ..tool import AsterTool
from ..prompt import AsterPrompt
from .response import GeminiResponse


_TEMP_PROMPT:str = """
You are an agent that can think and take actions to achieve a target.
"""

#TODO: For Temp USE. Need to use config + adapter -> GenAIConfig
_TEMP_CONFIG:GeminiConfig = GeminiConfig(
    api_key = "AQ.Ab8RN6IY_DYij6ButOlm77Hf7HX5pBczhgprpr-I3Rh6BvOr5w",
    model_name = "gemini-3.5-flash"
)

class ReasoningEffort(Enum):
    minimal = types.ThinkingLevel.MINIMAL
    low = types.ThinkingLevel.LOW
    medium = types.ThinkingLevel.MEDIUM
    high = types.ThinkingLevel.HIGH

def _gemini_aster_tool_to_declaration(tool:AsterTool)->types.FunctionDeclaration:
    return types.FunctionDeclaration(
            name=tool.name,
            description=tool.description,
            parameters_json_schema=(
                tool.args_schema.model_json_schema()
            ),
            response_json_schema=(
                tool.return_schema.model_json_schema()
            ),
        )

class Gemini:
    _prompt:AsterPrompt
    _config:GeminiConfig
    _client:genai.Client
    _tool_declarations: list[types.FunctionDeclaration]
    
    def __init__(
        self,
        config: GeminiConfig,
        tools: list[AsterTool] | None = None,
    ) -> None:
        self._prompt = AsterPrompt(_TEMP_PROMPT)
        self._config = config
        self._client = genai.Client(
            api_key=self._config.api_key
        )

        self._tool_declarations = [
            _gemini_aster_tool_to_declaration(tool)
            for tool in tools or []
        ]
        
    #TODO: The Context need further design
    def invoke(self, 
               target:str, 
               context:list[types.ContentUnionDict],
               effort:ReasoningEffort
               )->GeminiResponse:
        prompt = self._prompt.render({
            "target":target
        })
        response = self._client.models.generate_content(
            model=self._config.model_name,
            contents=context,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                thinking_level=effort.value,
                include_thoughts=True,
                ),
                system_instruction=prompt,

                tools=(
                [
                    types.Tool(function_declarations=(
                            self._tool_declarations
                        )
                    )
                ]
                if self._tool_declarations
                else None
                ),

                temperature=0.7
            ),
        )
        
        if not response.candidates:
            raise ValueError("No candidates from Google, please check the API availability.")
        
        if not response.candidates[0].content:
            raise ValueError("No content from Google, please check the API availability.")
        
                
        return GeminiResponse(response.candidates[0].content)
    

if __name__ == "__main__":
    class _SmokeArguments(BaseModel):
        left: int
        right: int

    class _SmokeResult(BaseModel):
        total: int

    def _smoke_add(arguments: _SmokeArguments) -> _SmokeResult:
        return _SmokeResult(
            total=arguments.left + arguments.right
        )

    smoke_tool = AsterTool(
        name="smoke_add",
        description="Add two integers and return their total.",
        func=_smoke_add,
        args_schema=_SmokeArguments,
        return_schema=_SmokeResult,
    )

    smoke_response = Gemini(
        config=_TEMP_CONFIG,
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

    if not isinstance(smoke_result, _SmokeResult):
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

    
