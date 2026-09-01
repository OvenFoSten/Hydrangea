# pyright: reportPrivateUsage=false

from google.genai import types

from hydrangea.context import Context
from hydrangea.context.area import AreaFlowState, AreaLifeState
from hydrangea.context.coop_context import CoopContext
from hydrangea.gateway import GatewayType
from hydrangea.gemini.context import GeminiContext
from hydrangea.message import Message, Role


def _content_text(content: types.Content) -> str:
    parts = content.parts
    assert parts is not None
    assert len(parts) == 1

    text = parts[0].text
    assert text is not None
    return text


def _context_structure(
    native: GeminiContext,
) -> tuple[tuple[str, str], ...]:
    structure: list[tuple[str, str]] = []
    for content in native.contents:
        role = content.role
        assert role is not None
        structure.append(
            (role, _content_text(content))
        )

    return tuple(structure)


def _new_context() -> tuple[Context, GeminiContext]:
    native = GeminiContext()
    context = Context(
        gateway_type=GatewayType.gemini,
        native=native,
    )
    return context, native


class _AuthoritativeMessageArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _content: str
    _rendered: bool
    gc_called: bool

    def __init__(self, content: str) -> None:
        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.exclusive
        self._content = content
        self._rendered = False
        self.gc_called = False

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def render(self) -> list[Message]:
        if self._rendered:
            raise RuntimeError(
                "AuthoritativeMessageArea rendered more than once."
            )

        self._rendered = True
        self._life_state = AreaLifeState.retired
        return [
            Message(
                role=Role.user,
                content=self._content,
            )
        ]

    def promote(self) -> tuple[Message, ...]:
        return ()

    def gc_prologue(self) -> None:
        self.gc_called = True


class _CountingArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _next_value: int
    _last_value: int
    gc_called: bool

    def __init__(self, last_value: int) -> None:
        if last_value < 1:
            raise ValueError(
                f"last_value must be positive, got {last_value}."
            )

        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.exclusive
        self._next_value = 1
        self._last_value = last_value
        self.gc_called = False

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def render(self) -> list[Message]:
        if self._life_state is AreaLifeState.retired:
            raise RuntimeError(
                "CountingArea rendered after retirement."
            )

        value = self._next_value
        self._next_value += 1
        if value == self._last_value:
            self._life_state = AreaLifeState.retired

        return [
            Message(
                role=Role.user,
                content=str(value),
            )
        ]

    def promote(self) -> tuple[Message, ...]:
        return ()

    def gc_prologue(self) -> None:
        self.gc_called = True


class _ThresholdCompactArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _inner: _CountingArea
    _threshold: int
    _messages: list[Message]
    gc_called: bool

    def __init__(
        self,
        inner: _CountingArea,
        threshold: int,
    ) -> None:
        if threshold < 1:
            raise ValueError(
                f"threshold must be positive, got {threshold}."
            )

        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.exclusive
        self._inner = inner
        self._threshold = threshold
        self._messages = []
        self.gc_called = False

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def render(self) -> list[Message]:
        messages = self._inner.render()
        self._messages.extend(messages)

        if (
            len(self._messages) >= self._threshold
            or self._inner.life_state is AreaLifeState.retired
        ):
            self._life_state = AreaLifeState.retired

        return messages

    def promote(self) -> tuple[Message, ...]:
        compacted_content = ", ".join(
            message.content
            for message in self._messages
        )
        return (
            Message(
                role=Role.user,
                content=f"compacted: {compacted_content}",
            ),
        )

    def gc_prologue(self) -> None:
        self.gc_called = True
        self._inner.gc_prologue()


def test_authoritative_message_area_retires_after_publish() -> None:
    context, native = _new_context()
    area = _AuthoritativeMessageArea(
        "authoritative source",
    )
    coop_context = CoopContext(context)
    coop_context.register(area)

    rendered_context = coop_context.render()

    assert rendered_context is context
    assert area.life_state is AreaLifeState.retired
    assert _context_structure(native) == (
        ("user", "authoritative source"),
    )

    rendered_context = coop_context.render()

    assert rendered_context is context
    assert area.gc_called
    assert _context_structure(native) == ()
    assert [_content_text(item) for item in coop_context.garbage] == [
        "authoritative source"
    ]


def test_counting_area_outputs_one_through_ten() -> None:
    context, native = _new_context()
    area = _CountingArea(last_value=10)
    coop_context = CoopContext(context)
    coop_context.register(area)

    for expected_value in range(1, 11):
        rendered_context = coop_context.render()

        assert rendered_context is context
        assert _context_structure(native) == tuple(
            ("user", str(value))
            for value in range(1, expected_value + 1)
        )

    assert area.life_state is AreaLifeState.retired

    rendered_context = coop_context.render()

    assert rendered_context is context
    assert area.gc_called
    assert _context_structure(native) == ()
    assert [_content_text(item) for item in coop_context.garbage] == [
        str(value)
        for value in range(1, 11)
    ]


def test_compact_area_wraps_an_area_and_promotes_summary() -> None:
    context, native = _new_context()
    inner = _CountingArea(last_value=10)
    area = _ThresholdCompactArea(
        inner=inner,
        threshold=4,
    )
    coop_context = CoopContext(context)
    coop_context.register(area)

    for expected_value in range(1, 5):
        rendered_context = coop_context.render()

        assert rendered_context is context
        assert _context_structure(native) == tuple(
            ("user", str(value))
            for value in range(1, expected_value + 1)
        )

    assert area.life_state is AreaLifeState.retired

    rendered_context = coop_context.render()

    assert rendered_context is context
    assert area.gc_called
    assert inner.gc_called
    assert [_content_text(item) for item in coop_context.garbage] == [
        "1",
        "2",
        "3",
        "4",
    ]
    assert _context_structure(native) == (
        ("user", "compacted: 1, 2, 3, 4"),
    )
