---
title: CoopContext
parent: 日本語
nav_order: 2
has_children: true
lang: ja
---

# CoopContext

## CoopContext とは

`CoopContext` は **Cooperate Context** の略です。Area を使って、入力情報と LLM のやり取りを開発者が制御します。いつ情報を導入するか、モデル出力にどう対応するか、何を Context に残すかを指定できます。

## 構成

`CoopContext` は、Hydrangea の `Context` と Area の配置を組み合わせます。

### `Context`

Hydrangea の `Context` は、選択したプロバイダー向けの会話内容を保持します。

### `AreaLayout`

`AreaLayout` は、Context を観察し、メッセージを追加する Area の配置を定義します。個別の Area と `AreaLane` オブジェクトを含められます。

```python
from hydrangea.context.coop_context import AreaLane, AreaLayout


layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])

coop_context.compose(layout)
```

4 つの Area がすべて `retain` かつ `deferrable` である場合、`tick()` の順序は `area_a -> area_b -> area_c -> area_d` です。

同じ Area インスタンスを、登録済みの配置に複数回含めることはできません。重複登録は `ValueError` になります。

`CoopContext` は両者を保持し、同じ `Context` インスタンスに対して配置を進めます。

## 公開メソッド

### `overlay()`

`overlay()` は、新しい Area を既存の `AreaLane` の先頭に積みます。対象の lane は `AreaLaneHandle` で指定します。この handle は、その lane に現在含まれる任意の Area から取得できます。

次の配置から始めます。

```python
layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])

coop_context.compose(layout)
```

4 つの Area がすべて `retain` かつ `deferrable` である場合、overlay 前の `tick()` の順序は `area_a -> area_b -> area_c -> area_d` です。

`area_b` と `area_c` を含む lane の先頭に `area_e` を追加します。

```python
handle = coop_context.fetch_handle(area_b)
assert handle is not None

coop_context.overlay(area_e, handle)
```

すべての Area が `retain` かつ `deferrable` である場合、overlay 後の `tick()` の順序は `area_a -> area_e -> area_b -> area_c -> area_d` です。

変更されるのは対象の lane だけです。`overlay()` は現在の cursor をその lane に移動しません。

handle は 1 つの `CoopContext` に属し、取得に使った Area が削除されても、lane が存在する間は有効です。別の `CoopContext` の handle や、削除済みの lane の handle を使うと `ValueError` になります。

### その他の公開メソッド

| メソッド | 用途 |
| --- | --- |
| `CoopContext(context)` | 既存の Hydrangea `Context` を使って `CoopContext` を作成します。 |
| `compose(layout)` | 現在の配置に `AreaLayout` を追加します。 |
| `append_lane(lane)` | `AreaLane` を 1 つ追加します。 |
| `fetch_handle(area)` | Area を含む lane の handle を取得します。Area が存在しない場合は `None` を返します。 |
| `unfold()` | 現在の Area の配置を進め、内部の `Context` を返します。 |

## 最小の使用例

設定済みの Hydrangea `LLM` を `llm`、Area のインスタンスを `area` とすると、モデルを 1 回呼び出す流れは次のようになります。

```python
from hydrangea.context import Context
from hydrangea.context.coop_context import AreaLayout, CoopContext
from hydrangea.reasoning import ReasoningEffort


context = Context(llm.gateway_type)
coop_context = CoopContext(context)
coop_context.compose(AreaLayout([area]))

model_context = coop_context.unfold()
response = llm.invoke(
    context=model_context,
    effort=ReasoningEffort.medium,
    tool_declarations=[],
)
context.push_back(response)
```
