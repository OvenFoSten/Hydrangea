---
title: 最小実装
parent: Area
grand_parent: 日本語
nav_order: 3
lang: ja
---

# 最小実装

```python
from hydrangea.context.area import Area, AreaInvokeTiming
from hydrangea.message import Message, Role


class OneShotArea(Area):
    def __init__(self, text: str) -> None:
        super().__init__(
            invoke_timing=AreaInvokeTiming.immediate,
        )
        self._text = text

    def tick(self) -> list[Message] | None:
        self._retire()
        return [
            Message(
                role=Role.user,
                content=self._text,
            )
        ]
```

この Area はメッセージを 1 つ出力した後、retire します。
