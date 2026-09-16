from typing import NewType
from dataclasses import dataclass
from typing_extensions import assert_never

from .area import AreaLifeState, AreaInvokeTiming
from .area import ContextAreaImplementation as _Area
from .core import Context, NativeContent
from ..message import Message

ContextIndex = NewType("ContextIndex", int)


class _AreaChain:
    _areas: list[_Area]

    def __init__(self, first: _Area, *rest: _Area) -> None:
        self._areas = [first, *rest]

    def __len__(self) -> int:
        return len(self._areas)

    def __getitem__(self, index: int) -> _Area:
        return self._areas[-1 - index]

    def __contains__(self, x: _Area) -> bool:
        return any(existing is x for existing in self._areas)

    def is_empty(self) -> bool:
        return len(self._areas) == 0

    def top(self) -> _Area:
        if self.is_empty():
            raise RuntimeError(
                "Chain is Empty."
            )
        return self._areas[-1]

    def pop_top(self) -> None:
        if len(self._areas) == 0:
            return
        _ = self._areas.pop()

    def push(self, area: _Area) -> None:
        self._areas.append(area)


@dataclass(slots=True)
class _OwnershipRange:
    """
    The Ownership range of Message.
    """
    start: ContextIndex
    latest: ContextIndex


@dataclass(slots=True)
class _LifeScale:
    """
    When _Area first .tick(), its Lifescale started.
    """
    start: ContextIndex
    latest: ContextIndex


@dataclass(frozen=True, slots=True)
class _CollectionPlan:
    earliest: ContextIndex
    expected_context_size: int
    areas: tuple[_Area, ...]


class CoopContext:
    _context: Context
    garbage: list[NativeContent]

    _area_chains: list[_AreaChain]
    _area_ownership_mapping: dict[_Area, _OwnershipRange]
    _area_lifescale_mapping: dict[_Area, _LifeScale]
    _cursor_store: _AreaChain | None

    def __init__(self, context: Context):
        self._context = context
        self.garbage = list()

        self._area_chains = list()
        self._area_ownership_mapping = dict()
        self._area_lifescale_mapping = dict()

        self._cursor_store = None

    def _collect(self) -> _CollectionPlan | None:
        if not self._area_mapping:
            return None

        context_size = len(self._context)
        ordered_areas = sorted(
            self._area_mapping,
            key=lambda area: self._area_mapping[area].latest,
            reverse=True,
        )

        for area in ordered_areas:
            effect_range = self._area_mapping[area]
            if (
                effect_range.earliest < 0
                or effect_range.latest < effect_range.earliest
                or effect_range.latest >= context_size
            ):
                raise RuntimeError(
                    "EffectRange is outside Context: "
                    f"[{effect_range.earliest}, {effect_range.latest}], "
                    f"context_size={context_size}."
                )

        tail_area = ordered_areas[0]
        tail_effect_range = self._area_mapping[tail_area]
        component_earliest = tail_effect_range.earliest
        component: list[ContextAreaImplementation] = []

        for area in ordered_areas:
            effect_range = self._area_mapping[area]
            if effect_range.latest < component_earliest:
                break

            match area.life_state:
                case AreaLifeState.retain:
                    return None

                case AreaLifeState.retired:
                    component.append(area)

                case _:
                    assert_never(area.life_state)

            if effect_range.earliest < component_earliest:
                component_earliest = effect_range.earliest

        return _CollectionPlan(
            earliest=component_earliest,
            expected_context_size=context_size,
            areas=tuple(component),
        )

    def _gc(self, plan: _CollectionPlan) -> None:
        if plan.expected_context_size != len(self._context):
            raise RuntimeError("Unexpected context change between collector and gc.")

        areas_to_collect = set(plan.areas)
        for area in plan.areas:
            if area not in self._areas:
                raise RuntimeError(
                    "Collected Area is missing from CoopContext."
                )
            if area not in self._area_mapping:
                raise RuntimeError(
                    "Collected Area is missing from the working set."
                )

        next_cursor = self._cursor_after_collection(
            areas_to_collect
        )

        # 1. Collect Promote
        promotes: list[Message] = list()
        for area in reversed(plan.areas):
            promotes.extend(area.promote())
        # 2. GC
        for area in reversed(plan.areas):
            area.gc_prologue()

        tail_length = (
            plan.expected_context_size
            - int(plan.earliest)
        )
        detached = self._context.detach_tail(
            length=tail_length
        )
        self.garbage.extend(detached)

        for area in plan.areas:
            _ = self._area_mapping.pop(area)

        self._areas[:] = [
            area
            for area in self._areas
            if area not in areas_to_collect
        ]
        self._cursor_store = next_cursor

        # 3. emplace promotes
        for promote in promotes:
            self._context.emplace_message(promote)

    def _cursor_repair(self) -> None:
        """
        ._cursor_repair found next foldable Chain.
        """
        # cursor = None when Empty.
        chain_size: int = len(self._area_chains)
        if chain_size == 0:
            self._cursor_store = None
            return

        expected_index: int = 0
        if self._cursor_store is None:
            expected_index = 0
        else:
            expected_index = self._area_chains.index(self._cursor_store)

        visited: int = 0
        runnable: _Area | None = None
        while visited < chain_size:
            chain = self._area_chains[expected_index]
            if not chain.is_empty():
                for area in chain:
                    if area.life_state is AreaLifeState.retain:
                        runnable = area
            if runnable is not None:
                break

            visited += 1
            expected_index = (expected_index + 1) % chain_size

        if runnable is None:
            self._cursor_store = None
        else:
            self._cursor_store = self._area_chains[expected_index]


    def _cursor_forward(self)->list[_Area]:
        if self._cursor_store is None:
            raise RuntimeError("Unexpected Empty cursor when forwarding.")

        ret:list[_Area] = list()
        cursor_index = self._area_chains.index(self._cursor_store)
        chain_count:int = len(self._area_chains)
        visited:int = 0
        while visited < chain_count:
            chain = self._area_chains[cursor_index]
            cursor_index = (cursor_index + 1) % chain_count
            visited += 1
            for area in chain:
                ret.append(area)
                match area.invoke_timing:
                    case AreaInvokeTiming.immediate:
                        return ret
                    case AreaInvokeTiming.deferrable:
                        continue
                    case _ :
                        raise RuntimeError(f"Unexpected declared InvokeTiming.")
        return ret


    def unfold(self) -> Context:
        # 0. Before GC, repair cursor.
        self._cursor_repair()
        # 1. Collect & GC
        # 2. Return context when chains is empty.
        chain_size = len(self._area_chains)
        if chain_size == 0:
            return self._context
        # 3. Fast forward & Unfold

        # 4. Store Cursor
        self._cursor_store = self._areas[area_cursor_index]
        # 5. Return Context
        return self._context
