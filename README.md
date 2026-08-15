# Hydrangea

English | [日本語](README.ja.md)

Hydrangea is a small, lightweight LLM gateway.

> [!WARNING]
> Hydrangea is currently an early prototype. Its public API may change without notice.

## Current support

- Google Gemini via `google-genai` 2.10.0
- OpenAI-compatible embedding endpoints

## Development installation

```bash
python -m pip install -e .
```

This keeps the installed package linked to the current source tree.

## Why Hydrangea?

Hydrangea began as an internal module built for Aster. I wanted to manage LLM context myself instead of handing that responsibility to a larger framework. When another project needed the same code, extracting it into a small package was cleaner than maintaining multiple copies.

## Why not just use LangChain?

Honestly, you probably should. ;)

Hydrangea is not intended to replace a full-featured framework. It is simply the small gateway my projects needed: explicit control over context, lightweight provider adaptation, and access to provider-native responses.

## The name

Hydrangeas are flowering plants known for their large, round clusters of blossoms, whose colors can change with the acidity of the soil. Hydrangea is named after these flowers. [Wikipedia](https://en.wikipedia.org/wiki/Hydrangea)
