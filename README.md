# Hydrangea

English | [日本語](README.ja.md)

Hydrangea is a small, lightweight LLM gateway.

> [!WARNING]
> Hydrangea is currently an early prototype. Its public API may change without notice.

## Feature

Cooperative Context (`CoopContext`) allows caller-defined Context Areas to contribute temporary messages with explicit scheduling, lifetime, and reclamation semantics.

## Current support

- Google Gemini via `google-genai` 2.10.0
- OpenAI via the Responses API using `openai` 2.x
- OpenAI-compatible embedding endpoints

## Development installation

```bash
python -m pip install -e .
```

This keeps the installed package linked to the current source tree.

## OpenAI responses and reasoning

OpenAI `LLM.invoke()` returns the SDK's complete `Response`. Append it with
`context.push_back(response)` to keep all output items, including encrypted
reasoning and function calls, together as one native context entry. Requests use
`store=False` and replay the history locally, without `previous_response_id`.
Function replies use `function_call_output` items with the original `call_id`.
The configured endpoint must support `/v1/responses`.

Like `GeminiResponse`, `hydrangea.openai.OpenAIResponse(response)` exposes
`output`, `thoughts` (reasoning summaries), `tool_calls`, and the original
`content`. To save and restore a native response, use
`response.model_dump_json()` and `openai.types.responses.Response.model_validate_json(snapshot)`.
Restoring the complete object preserves encrypted reasoning for the next call.
`OpenAIContext.input` provides the replayable items; this replaces the previous
Chat Completions `messages` property and `ChatCompletionMessage` return type.

## Why Hydrangea?

Hydrangea began as an internal module built for Aster. I wanted to manage LLM context myself instead of handing that responsibility to a larger framework. When another project needed the same code, extracting it into a small package was cleaner than maintaining multiple copies.

## Why not just use LangChain?

Honestly, you probably should. ;)

Hydrangea is not intended to replace a full-featured framework. It is simply the small gateway my projects needed: explicit control over context, lightweight provider adaptation, and access to provider-native responses.

## The name

Hydrangeas are flowering plants known for their large, round clusters of blossoms, whose colors can change with the acidity of the soil. Hydrangea is named after these flowers. [Wikipedia](https://en.wikipedia.org/wiki/Hydrangea)
