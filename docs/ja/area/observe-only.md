---
title: Observe-only
parent: Area
grand_parent: 日本語
nav_order: 4
lang: ja
---

# Observe-only

observe-only の Area は `tick()` から `None` を返します。最初の tick で `ObserveRange` が作られますが、`EffectRange` は作られません。

## `ObserverArea`

`ObserverArea` は、継承した `observe()` が受け取った最新のスナップショットを保持します。独自の `get_snapshot()` メソッドは、観察した内容のシーケンスをコピーして呼び出し側に返します。

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

P.S. これは浅いコピーです。プロバイダー固有の要素は共有されたままなので、読み取り専用として扱ってください。要素を変更する場合は、変更するネストしたデータも含めて、先に明示的に独立したコピーを作成してください。
