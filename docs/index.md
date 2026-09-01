---
title: Home
nav_order: 1
---

# Hydrangea Documentation

English | [日本語]({% link ja/index.md %})

Hydrangea is a small, lightweight LLM gateway for applications that need explicit control over context, tools, and provider-native responses.

> Hydrangea is currently an early prototype. Its public API may change without notice.

## Context Areas

A Context Area contributes caller-constructed messages to a `CoopContext` and declares when those messages may be reclaimed.

[Declare a Context Area](context-areas.md)
