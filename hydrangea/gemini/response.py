from google.genai import types



class GeminiResponse:
    content: types.Content
    thoughts: list[str] | None
    tool_calls: list[types.FunctionCall] | None
    output: str

    def __init__(self, content: types.Content) -> None:
        self.content = content
        self.thoughts = None

        self.output = ""
        self.tool_calls = None
        if not content.parts:
            raise ValueError("No content from Google, please check the API availability.")

        response_thoughts: list[str] = []
        response_tool_calls: list[types.FunctionCall] = []
        for part in content.parts:
            if part.thought and part.text:
                response_thoughts.append(part.text)
                continue

            if part.function_call:
                response_tool_calls.append(part.function_call)
                continue

            if part.text:
                self.output += part.text
                continue

        if response_thoughts:
            self.thoughts = response_thoughts
        if response_tool_calls:
            self.tool_calls = response_tool_calls
