---
title: Minimal implementation
parent: Area
grand_parent: English
nav_order: 3
lang: en
---

# Minimal implementation

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

This Area emits one message and then retires.
