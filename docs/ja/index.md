---
title: 日本語
nav_order: 2
has_children: true
lang: ja
---

# Hydrangea ドキュメント

Hydrangea は、Context、Tool、およびプロバイダー固有のレスポンスを明示的に制御したいアプリケーション向けの、小規模で軽量な LLM ゲートウェイです。

> Hydrangea は現在、初期プロトタイプの段階にあります。公開 API は予告なく変更される可能性があります。

## Area

Area は、Context を観察し、メッセージを出力し、最終的に retire する、状態を持つ単位です。

[Area]({% link ja/area/index.md %})

## CoopContext

`CoopContext` は、Hydrangea の `Context` と `AreaLayout` を組み合わせます。

[CoopContext]({% link ja/coop-context/index.md %})
