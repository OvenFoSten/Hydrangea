---
title: CoopContext
parent: English
nav_order: 2
has_children: true
lang: en
---

# CoopContext

## What is CoopContext & why

`CoopContext` stands for **Cooperate Context**. It uses Areas to give developers control over how input information interacts with an LLM: when to introduce information, how to respond to model output, and what to retain in Context.

## Structure

`CoopContext` coordinates a Hydrangea `Context` with a layout of Areas.

### `Context`

The Hydrangea `Context` stores the conversation content for the selected provider.

### `AreaLayout`

The `AreaLayout` organizes the Areas that observe and contribute to that Context. A layout can contain individual Areas and `AreaLane` objects.

```python
from hydrangea.context.coop_context import AreaLane, AreaLayout


layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])

coop_context.compose(layout)
```

Assuming all four Areas are retained and deferrable, the expected `tick()` order is `area_a -> area_b -> area_c -> area_d`.

The same Area instance cannot appear more than once in the registered layout. Duplicate registration raises `ValueError`.

`CoopContext` keeps both parts together and advances the layout against the same `Context` instance.

## Public methods

### `overlay()`

`overlay()` pushes a new Area onto an existing `AreaLane`. The lane is identified by an `AreaLaneHandle`, which can be fetched through any Area currently in that lane.

Start with this layout:

```python
layout = AreaLayout([
    area_a,
    AreaLane(area_b, area_c),
    area_d,
])

coop_context.compose(layout)
```

Before overlay, assuming all four Areas are retained and deferrable, the expected `tick()` order is `area_a -> area_b -> area_c -> area_d`.

Add `area_e` to the top of the lane containing `area_b` and `area_c`:

```python
handle = coop_context.fetch_handle(area_b)
assert handle is not None

coop_context.overlay(area_e, handle)
```

After overlay, assuming every Area is retained and deferrable, the expected `tick()` order is `area_a -> area_e -> area_b -> area_c -> area_d`.

Only the target lane changes. `overlay()` does not move the current cursor to that lane.

A handle belongs to one `CoopContext` and remains valid while its lane exists, even if the Area used to fetch it is removed. Using a handle from another `CoopContext` or a removed lane raises `ValueError`.

### Other public methods

| Method | Purpose |
| --- | --- |
| `CoopContext(context)` | Create a `CoopContext` around an existing Hydrangea `Context`. |
| `compose(layout)` | Append an `AreaLayout` to the current layout. |
| `append_lane(lane)` | Append one `AreaLane`. |
| `fetch_handle(area)` | Get the handle for the lane containing an Area, or `None` if it is absent. |
| `unfold()` | Advance the current Area layout and return the underlying `Context`. |

## Minimal usage

Given a configured Hydrangea `LLM` named `llm` and an Area instance named `area`, one model turn is:

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
