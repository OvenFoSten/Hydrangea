from typing_extensions import override

from ..core import Area, FlowState, LifeState
from ....message import Message, Role

"""
Pin would pin the message temporarily.
eg. pin<message> -> LLM.invoke() -> collect(pin)
"""


class Pin(Area):
    _message: str

    def __init__(self, message: str):
        super().__init__(flow_state=FlowState.exclusive)
        self._message = message

    """
    When Pin.tick(), it would return self.message and mark itself retired.
    .tick() -> retired -> gc
    """
    @override
    def tick(self) -> list[Message]:
        self._life_state: LifeState = LifeState.retired
        return [
            Message(
                role=Role.user,
                content=self._message
            )
        ]
