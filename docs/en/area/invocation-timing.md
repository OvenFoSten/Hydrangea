---
title: Invocation timing
parent: Area
grand_parent: English
nav_order: 2
lang: en
---

# Invocation timing

| `AreaInvokeTiming` | Meaning |
| --- | --- |
| `immediate` | Request model invocation immediately after this tick. |
| `deferrable` | Allow model invocation to be deferred while other Areas advance. |

An Area may change its invocation timing as its state changes.

## `immediate`: completing a prerequisite

A discovers that it needs task E to finish before it can continue. E uses `immediate` timing to work on that task.

Start with retained, deferrable Areas A, B, C and D:

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

Before overlay, the expected `tick()` order is `area_a -> area_b -> area_c -> area_d`.

After A identifies the prerequisite, overlay `area_e` onto A's lane between `unfold()` calls. E is retained and its `invoke_timing` is `AreaInvokeTiming.immediate`:

```python
handle = coop_context.fetch_handle(area_a)
assert handle is not None

coop_context.overlay(area_e, handle)
```

After overlay, only `area_e` ticks before the next model invocation. This continues while E remains retained and immediate, allowing E to complete its task before A ticks again.

When E finishes, it retires and the expected `tick()` order returns to `area_a -> area_b -> area_c -> area_d`. E should return its result from `promote()` so that the result remains in Context after collection.

## `deferrable`: supplying incoming information

E listens on a port and forwards incoming messages into Context. Its `tick()` returns the pending messages, or `None` if nothing has arrived. Using `deferrable` lets E supply that information alongside A's output in the same model invocation.

Start with retained, deferrable Areas A, B, C and D:

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

Before overlay, the expected `tick()` order is `area_a -> area_b -> area_c -> area_d`.

Between `unfold()` calls, overlay `area_e` onto A's lane. E is retained and its `invoke_timing` is `AreaInvokeTiming.deferrable`:

```python
handle = coop_context.fetch_handle(area_a)
assert handle is not None

coop_context.overlay(area_e, handle)
```

After overlay, the expected `tick()` order is `area_e -> area_a -> area_b -> area_c -> area_d`.

In that turn, E's messages are appended before A's output. The LLM can therefore use E's information when processing A's output in the same invocation.
