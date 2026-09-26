---
title: Observe-only
parent: Area
grand_parent: English
nav_order: 4
lang: en
---

# Observe-only

An observe-only Area returns `None` from `tick()`. Its first tick establishes an `ObserveRange` without creating an `EffectRange`.

## `ObserverArea`

`ObserverArea` keeps the latest snapshot received through the inherited `observe()` method. Its custom `get_snapshot()` method gives the caller a copy of the observed sequence.

```python
from hydrangea.context import NativeContent
from hydrangea.context.area import Area, AreaInvokeTiming


class ObserverArea(Area):
    def __init__(self) -> None:
        super().__init__(invoke_timing=AreaInvokeTiming.deferrable)

    def tick(self) -> None:
        return None

    def get_snapshot(self) -> list[NativeContent]:
        return list(self._observe_snapshot)
```

P.S. This is a shallow copy. The provider-native elements remain shared and should be treated as read-only. To modify an element, explicitly create an independent copy of it first, including any nested data you intend to change.
