---
title: English
nav_order: 1
has_children: true
lang: en
---

# Hydrangea Documentation

Hydrangea is a small, lightweight LLM gateway for applications that need explicit control over context, tools, and provider-native responses.

> Hydrangea is currently an early prototype. Its public API may change without notice.

## Area

An Area is a stateful unit that can observe Context, emit messages, and eventually retire.

[Area]({% link en/area/index.md %})

## CoopContext

`CoopContext` combines a Hydrangea `Context` with an `AreaLayout`.

[CoopContext]({% link en/coop-context/index.md %})
