from collections.abc import Sequence
from enum import Enum, auto

from google.genai import types

from hydrangea.context import Context, NativeContent
from hydrangea.context.area import AreaFlowState, AreaLifeState
from hydrangea.context.coop_context import CoopContext
from hydrangea.gateway import GatewayType
from hydrangea.gemini.context import GeminiContext
from hydrangea.message import Message, Role


_SESSION_OPEN = "<working-context>codex-like task</working-context>"
_AUTHORITATIVE_STATE = (
    "<authoritative-state>repository is writable; inspect before editing"
    "</authoritative-state>"
)
_SKILL_GUIDANCE = (
    "<skill-guidance>follow the repository-review workflow</skill-guidance>"
)
_MODEL_ACTION = "ACTION: inspect repository status"
_ACTION_RESULT = (
    "<action-result>repository inspection completed</action-result>"
)
_COMPACT_REQUEST = (
    "<compact-request>summarize completed work</compact-request>"
)
_MODEL_SUMMARY = "Repository inspected; no blocking issue found."
_COMPACT_SEAL = "<compact-complete/>"
_PROMOTED_SUMMARY = (
    "<working-summary>Repository inspected; no blocking issue found."
    "</working-summary>"
)


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


def _snapshot_text(
    context: Sequence[NativeContent],
) -> tuple[str, ...]:
    return tuple(
        _content_text(content)
        for content in context
    )


def _append_model_response(
    context: Context,
    content: str,
) -> None:
    context.push_back(
        types.Content(
            role="model",
            parts=[types.Part.from_text(text=content)],
        )
    )


def _new_context() -> tuple[Context, GeminiContext]:
    native = GeminiContext()
    context = Context(
        gateway_type=GatewayType.gemini,
        native=native,
    )
    return context, native


class _AuthoritativeStateArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _events: list[str]

    def __init__(self, events: list[str]) -> None:
        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.yielded
        self._events = events

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        _ = context
        raise RuntimeError(
            "A retired authoritative Area must not be observed."
        )

    def advance(self) -> list[Message]:
        self._events.append("authority:publish")
        self._life_state = AreaLifeState.retired
        return [
            Message(
                role=Role.user,
                content=_AUTHORITATIVE_STATE,
            )
        ]

    def promote(self) -> tuple[Message, ...]:
        self._events.append("authority:promote")
        return ()

    def gc_prologue(self) -> None:
        self._events.append("authority:gc")


class _SkillInteractionArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _events: list[str]
    _guidance_published: bool
    _model_action: str | None
    observed_snapshots: list[tuple[str, ...]]

    def __init__(self, events: list[str]) -> None:
        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.exclusive
        self._events = events
        self._guidance_published = False
        self._model_action = None
        self.observed_snapshots = []

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        self.observed_snapshots.append(
            _snapshot_text(context)
        )

    def accept_model_action(self, action: str) -> None:
        if not self._guidance_published:
            raise RuntimeError(
                "Skill guidance must be published before an action."
            )
        if self._model_action is not None:
            raise RuntimeError(
                "SkillInteractionArea received more than one action."
            )

        self._model_action = action

    def advance(self) -> list[Message]:
        if not self._guidance_published:
            self._events.append("skill:guide")
            self._guidance_published = True
            return [
                Message(
                    role=Role.user,
                    content=_SKILL_GUIDANCE,
                )
            ]

        if self._model_action is None:
            raise RuntimeError(
                "SkillInteractionArea advanced before model action."
            )

        self._events.append("skill:complete-action")
        self._life_state = AreaLifeState.retired
        self._flow_state = AreaFlowState.yielded
        return [
            Message(
                role=Role.user,
                content=_ACTION_RESULT,
            )
        ]

    def promote(self) -> tuple[Message, ...]:
        self._events.append("skill:promote")
        return ()

    def gc_prologue(self) -> None:
        self._events.append("skill:gc")


class _CompactPhase(Enum):
    opening = auto()
    working = auto()
    awaiting_summary = auto()
    sealed = auto()


class _AutomaticCompactArea:
    _life_state: AreaLifeState
    _flow_state: AreaFlowState
    _events: list[str]
    _phase: _CompactPhase
    _summary: str | None
    observed_snapshots: list[tuple[str, ...]]

    def __init__(self, events: list[str]) -> None:
        self._life_state = AreaLifeState.retain
        self._flow_state = AreaFlowState.yielded
        self._events = events
        self._phase = _CompactPhase.opening
        self._summary = None
        self.observed_snapshots = []

    @property
    def life_state(self) -> AreaLifeState:
        return self._life_state

    @property
    def flow_state(self) -> AreaFlowState:
        return self._flow_state

    def observe(
        self,
        context: Sequence[NativeContent],
    ) -> None:
        self.observed_snapshots.append(
            _snapshot_text(context)
        )

    def accept_summary(self, summary: str) -> None:
        if self._phase is not _CompactPhase.awaiting_summary:
            raise RuntimeError(
                "Compact summary arrived outside its request phase."
            )
        if self._summary is not None:
            raise RuntimeError(
                "AutomaticCompactArea received more than one summary."
            )

        self._summary = summary

    def advance(self) -> list[Message]:
        if self._phase is _CompactPhase.opening:
            self._events.append("compact:open")
            self._phase = _CompactPhase.working
            return [
                Message(
                    role=Role.user,
                    content=_SESSION_OPEN,
                )
            ]

        if self._phase is _CompactPhase.working:
            self._events.append("compact:request-summary")
            self._phase = _CompactPhase.awaiting_summary
            self._flow_state = AreaFlowState.exclusive
            return [
                Message(
                    role=Role.user,
                    content=_COMPACT_REQUEST,
                )
            ]

        if self._phase is _CompactPhase.awaiting_summary:
            if self._summary is None:
                raise RuntimeError(
                    "AutomaticCompactArea advanced before summary."
                )

            self._events.append("compact:seal")
            self._phase = _CompactPhase.sealed
            self._life_state = AreaLifeState.retired
            self._flow_state = AreaFlowState.yielded
            return [
                Message(
                    role=Role.user,
                    content=_COMPACT_SEAL,
                )
            ]

        raise RuntimeError(
            "AutomaticCompactArea advanced after sealing."
        )

    def promote(self) -> tuple[Message, ...]:
        if self._summary is None:
            raise RuntimeError(
                "AutomaticCompactArea promoted without a summary."
            )

        self._events.append("compact:promote")
        return (
            Message(
                role=Role.user,
                content=(
                    "<working-summary>"
                    f"{self._summary}"
                    "</working-summary>"
                ),
            ),
        )

    def gc_prologue(self) -> None:
        self._events.append("compact:gc")


def test_authority_skill_and_compaction_workflow() -> None:
    context, native = _new_context()
    events: list[str] = []
    compact = _AutomaticCompactArea(events)
    authority = _AuthoritativeStateArea(events)
    skill = _SkillInteractionArea(events)

    coop_context = CoopContext(context)
    for area in (compact, authority, skill):
        coop_context.register(area)

    first_model_context = coop_context.advance()

    assert first_model_context is context
    assert authority.life_state is AreaLifeState.retired
    assert skill.flow_state is AreaFlowState.exclusive
    assert _context_structure(native) == (
        ("user", _SESSION_OPEN),
        ("user", _AUTHORITATIVE_STATE),
        ("user", _SKILL_GUIDANCE),
    )

    _append_model_response(context, _MODEL_ACTION)
    skill.accept_model_action(_MODEL_ACTION)

    second_model_context = coop_context.advance()

    assert second_model_context is context
    assert skill.life_state is AreaLifeState.retired
    assert compact.flow_state is AreaFlowState.exclusive
    assert skill.observed_snapshots == [
        (_SKILL_GUIDANCE,)
    ]
    assert compact.observed_snapshots == [
        (_SESSION_OPEN,)
    ]
    assert _context_structure(native) == (
        ("user", _SESSION_OPEN),
        ("user", _AUTHORITATIVE_STATE),
        ("user", _SKILL_GUIDANCE),
        ("model", _MODEL_ACTION),
        ("user", _ACTION_RESULT),
        ("user", _COMPACT_REQUEST),
    )

    _append_model_response(context, _MODEL_SUMMARY)
    compact.accept_summary(_MODEL_SUMMARY)

    sealed_context = coop_context.advance()

    assert sealed_context is context
    assert compact.life_state is AreaLifeState.retired
    assert compact.observed_snapshots == [
        (_SESSION_OPEN,),
        (
            _SESSION_OPEN,
            _AUTHORITATIVE_STATE,
            _SKILL_GUIDANCE,
            _MODEL_ACTION,
            _ACTION_RESULT,
            _COMPACT_REQUEST,
        ),
    ]
    assert _context_structure(native) == (
        ("user", _SESSION_OPEN),
        ("user", _AUTHORITATIVE_STATE),
        ("user", _SKILL_GUIDANCE),
        ("model", _MODEL_ACTION),
        ("user", _ACTION_RESULT),
        ("user", _COMPACT_REQUEST),
        ("model", _MODEL_SUMMARY),
        ("user", _COMPACT_SEAL),
    )

    compacted_context = coop_context.advance()

    assert compacted_context is context
    assert _context_structure(native) == (
        ("user", _PROMOTED_SUMMARY),
    )
    assert [
        _content_text(content)
        for content in coop_context.garbage
    ] == [
        _SESSION_OPEN,
        _AUTHORITATIVE_STATE,
        _SKILL_GUIDANCE,
        _MODEL_ACTION,
        _ACTION_RESULT,
        _COMPACT_REQUEST,
        _MODEL_SUMMARY,
        _COMPACT_SEAL,
    ]
    assert events == [
        "compact:open",
        "authority:publish",
        "skill:guide",
        "skill:complete-action",
        "compact:request-summary",
        "compact:seal",
        "authority:promote",
        "skill:promote",
        "compact:promote",
        "authority:gc",
        "skill:gc",
        "compact:gc",
    ]

    assert coop_context.advance() is context
    assert _context_structure(native) == (
        ("user", _PROMOTED_SUMMARY),
    )
