---
title: Invocation timing
parent: Area
grand_parent: 日本語
nav_order: 2
lang: ja
---

# Invocation timing

| `AreaInvokeTiming` | 意味 |
| --- | --- |
| `immediate` | この tick の直後にモデル呼び出しを要求します。 |
| `deferrable` | 他の Area が進行する間、モデル呼び出しの延期を許可します。 |

Area は自身の状態変化に合わせて invocation timing を変更できます。

## `immediate`：前提となるタスクを完了する

A は、作業を続ける前にタスク E を完了する必要があると判断します。E は `immediate` を使って、そのタスクに取り組みます。

`retain` かつ `deferrable` の Area A、B、C、D を配置します。

```python
from hydrangea.context.coop_context import AreaLane, AreaLayout, CoopContext


coop_context = CoopContext(context)
layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])
coop_context.compose(layout)
```

overlay 前の `tick()` の順序は、`area_a -> area_b -> area_c -> area_d` です。

A が前提となるタスクの必要性を判断したら、`unfold()` の呼び出しの間に `area_e` を A の lane に overlay します。E は `retain` 状態で、`invoke_timing` は `AreaInvokeTiming.immediate` です。

```python
handle = coop_context.fetch_handle(area_a)
assert handle is not None

coop_context.overlay(area_e, handle)
```

overlay 後、次のモデル呼び出しまでに tick するのは `area_e` だけです。E が `retain` かつ `immediate` の間はこれが続き、A が再び tick する前に E がタスクを完了できるようにします。

E は完了すると retire し、`tick()` の順序は `area_a -> area_b -> area_c -> area_d` に戻ります。回収後も結果を Context に残すため、E は `promote()` からその結果を返す必要があります。

## `deferrable`：受信した情報を提供する

E はポートでメッセージを受信し、Context に渡します。`tick()` は受信済みのメッセージを返し、何も届いていなければ `None` を返します。`deferrable` を使うことで、E の情報と A の出力を同じモデル呼び出しに含められます。

`retain` かつ `deferrable` の Area A、B、C、D を配置します。

```python
from hydrangea.context.coop_context import AreaLane, AreaLayout, CoopContext


coop_context = CoopContext(context)
layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])
coop_context.compose(layout)
```

overlay 前の `tick()` の順序は、`area_a -> area_b -> area_c -> area_d` です。

`unfold()` の呼び出しの間に、`area_e` を A の lane に overlay します。E は `retain` 状態で、`invoke_timing` は `AreaInvokeTiming.deferrable` です。

```python
handle = coop_context.fetch_handle(area_a)
assert handle is not None

coop_context.overlay(area_e, handle)
```

overlay 後の `tick()` の順序は、`area_e -> area_a -> area_b -> area_c -> area_d` です。

このターンでは、E のメッセージが A の出力より先に Context に追加されます。そのため、LLM は同じ呼び出しの中で E の情報を利用して A の出力を処理できます。
