---
title: English
nav_order: 1
has_children: true
lang: en
---

# Hydrangea Documentation

<p><strong>English</strong> · <a href="{% link ja/index.md %}">日本語</a></p>

Hydrangea is a small, lightweight LLM gateway for applications that need explicit control over context, tools, and provider-native responses.

> Hydrangea is currently an early prototype. Its public API may change without notice.

## Context Areas

A Context Area contributes caller-constructed messages to a `CoopContext` and declares when those messages may be reclaimed.

[Declare a Context Area]({% link en/context-areas.md %})
