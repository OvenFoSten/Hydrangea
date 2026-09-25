from dataclasses import dataclass
from collections.abc import Iterator
from typing import NewType

from .area import AreaLifeState, AreaInvokeTiming
from .area import ContextAreaImplementation as _Area
from .core import Context, NativeContent
from ..message import Message


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

    def __iter__(self) -> Iterator[_Area]:
        return reversed(self._areas)

    def __delitem__(self, index: int) -> None:
        del self._areas[-1 - index]

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


class AreaLane:
    areas: list[_Area]

    def __init__(self, first: _Area, *rest: _Area) -> None:
        self.areas = [first, *rest]


AreaLayout = NewType("AreaLayout", list[AreaLane | _Area])


@dataclass(slots=True, frozen=True)
class AreaLaneHandle:
    _chain_ref: _AreaChain


@dataclass(slots=True)
class _EffectRange:
    start: int
    latest: int


@dataclass(slots=True)
class _ObserveRange:
    start: int
    latest: int


@dataclass(frozen=True, slots=True)
class _CollectCandidate:
    area: _Area
    last_touched: int


@dataclass(frozen=True, slots=True)
class _CollectPlan:
    earliest: int | None
    expected_context_size: int
    candidates: tuple[_CollectCandidate, ...]


class CoopContext:
    _context: Context
    garbage: list[NativeContent]

    _area_chains: list[_AreaChain]
    _area_effect_range_mapping: dict[_Area, _EffectRange]
    _area_observe_range_mapping: dict[_Area, _ObserveRange]
    _cursor_store: _AreaChain | None

    def __init__(self, context: Context):
        self._context = context
        self.garbage = list()

        self._area_chains = list()
        self._area_effect_range_mapping = dict()
        self._area_observe_range_mapping = dict()

        self._cursor_store = None

    def _validate_area_batch(self, areas: list[_Area]) -> None:
        existing = tuple(
            area
            for chain in self._area_chains
            for area in chain
        )
        accepted: list[_Area] = list()
        for area in areas:
            try:
                _ = hash(area)
            except TypeError as exc:
                raise TypeError("Area must be hashable.") from exc
            if any(area is item for item in existing):
                raise ValueError("Area instance is already registered.")
            if any(area is item for item in accepted):
                raise ValueError("Area instance is duplicated in this operation.")
            accepted.append(area)

    def _validate_area(self, area: _Area) -> None:
        try:
            _ = hash(area)
        except TypeError as exc:
            raise TypeError("Area must be hashable.") from exc

        existing = tuple(
            area
            for chain in self._area_chains
            for area in chain
        )
        if any(area is item for item in existing):
            raise ValueError("Area instance is already registered.")

    def overlay(self, area: _Area, handle: AreaLaneHandle):
        self._validate_area(area)
        # It's better to access the protected member instead of design something complex to bypass Pyright.
        chain_ref = handle._chain_ref # pyright: ignore[reportPrivateUsage]
        if chain_ref not in self._area_chains:
            raise ValueError("Hanging Handle.")
        chain_ref.push(area)

    def append_lane(self, lane: AreaLane):
        self._validate_area_batch(lane.areas)
        areas_chain = lane.areas[::-1]
        self._area_chains.append(
            _AreaChain(*areas_chain)
        )

    def compose(self,layout:AreaLayout):
        for item in layout:
            if isinstance(item,AreaLane):
                self.append_lane(item)
            # We decide not to make protocol runtime checkable.
            # Meanwhile Area(ABC) is optional so we do not wanna couple it here.
            else:
                self.append_lane(AreaLane(item))

    def _collect(self) -> _CollectPlan | None:
        collected_areas: list[_CollectCandidate] = []
        expected_size = len(self._context)
        earliest = expected_size
        observe_barrier: int | None = max(
            (
                ob_range.start
                for area, ob_range in self._area_observe_range_mapping.items()
                if area.life_state is AreaLifeState.retain
                and area not in self._area_effect_range_mapping
            ),
            default=None
        )
        # 1. Collect observe-only areas.
        for area, ob_range in self._area_observe_range_mapping.items():
            if area.life_state is not AreaLifeState.retired:
                continue
            if self._area_effect_range_mapping.get(area) is not None:
                continue

            collected_areas.append(
                _CollectCandidate(
                    area=area,
                    last_touched=ob_range.latest,
                )
            )

        # 2. Find longest collectable tail.
        ordered = sorted(
            self._area_effect_range_mapping.items(),
            key=lambda item: item[1].latest,
            reverse=True,
        )

        if ordered:
            collecting: list[_CollectCandidate] = []
            component_left = ordered[0][1].start

            for area, ef_range in ordered:
                if ef_range.latest < component_left:
                    collected_areas.extend(collecting)
                    earliest = component_left
                    collecting.clear()

                    component_left = ef_range.start
                else:
                    component_left = min(
                        component_left,
                        ef_range.start,
                    )

                if observe_barrier is not None and component_left <= observe_barrier:
                    break

                if area.life_state is AreaLifeState.retain:
                    break

                collecting.append(
                    _CollectCandidate(
                        area=area,
                        last_touched=ef_range.latest,
                    )
                )
            else:
                collected_areas.extend(collecting)
                earliest = component_left

        # 3. Return.
        if not collected_areas:
            return None

        return _CollectPlan(
            earliest=None if earliest == expected_size else earliest,
            expected_context_size=expected_size,
            candidates=tuple(collected_areas),
        )

    def _gc(self, plan: _CollectPlan) -> None:
        if plan.expected_context_size != len(self._context):
            raise RuntimeError("Unexpected context change after collected.")

        candidates: tuple[_CollectCandidate, ...] = plan.candidates
        # 1. Sweep Mappings
        for candidate in candidates:
            area = candidate.area
            _ = self._area_effect_range_mapping.pop(area, None)
            _ = self._area_observe_range_mapping.pop(area, None)
        # 2. GC Notify & Promote & GC
        ordered = sorted(
            candidates,
            key=lambda candidate: candidate.last_touched,
        )
        promotes: list[Message] = list()
        for candidate in ordered:
            area = candidate.area
            promotes.extend(area.promote())
            area.gc_prologue()
        # 3. Sweep Context & Garbage
        if plan.earliest is not None:
            garbage_length = plan.expected_context_size - plan.earliest
            self.garbage.extend(self._context.detach_tail(garbage_length))
        # 4. Promote
        for promote in promotes:
            self._context.emplace_message(promote)
        # 5. Sweep Areas
        sweep_set: set[_Area] = set()
        for candidate in candidates:
            sweep_set.add(candidate.area)
        empty_chain_index: list[int] = list()
        for chain_index, chain in enumerate(self._area_chains):
            for area_index, area in reversed(list(enumerate(chain))):
                if area in sweep_set:
                    del chain[area_index]
            if chain.is_empty():
                empty_chain_index.append(chain_index)
        for e_i in reversed(empty_chain_index):
            del self._area_chains[e_i]

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

    def _cursor_forward(self) -> tuple[list[_Area], _AreaChain]:
        if self._cursor_store is None:
            raise RuntimeError("Unexpected Empty cursor when forwarding.")

        ret: list[_Area] = list()
        cursor_index = self._area_chains.index(self._cursor_store)
        chain_count: int = len(self._area_chains)
        visited: int = 0
        current_chain: _AreaChain = self._cursor_store
        while visited < chain_count:
            current_chain = self._area_chains[cursor_index]
            cursor_index = (cursor_index + 1) % chain_count
            visited += 1
            for area in current_chain:
                if area.life_state is not AreaLifeState.retain:
                    continue

                ret.append(area)
                match area.invoke_timing:
                    case AreaInvokeTiming.immediate:
                        return (ret, current_chain)
                    case AreaInvokeTiming.deferrable:
                        continue
                    case _:
                        raise RuntimeError(f"Unexpected declared InvokeTiming.")
        current_chain = self._area_chains[(cursor_index + 1) % chain_count]
        return (ret, current_chain)

    def unfold(self) -> Context:
        # 0. Before GC, repair cursor.
        self._cursor_repair()
        # 1. Collect & GC
        collection_plan = self._collect()
        if collection_plan is not None:
            self._gc(collection_plan)
        # 2. Return context when chains is empty.
        chain_size = len(self._area_chains)
        if chain_size == 0 and self._cursor_store is None:
            return self._context
        # 3. Update ObserveRange.latest
        """
        Q: Why we update ObserveRange here?
        A: ObserveRange is designed to observe the context before tick().
           Literaturely, observe -> have view -> make decision when tick() -> gc
        """
        expected_observe_latest = len(self._context) - 1
        for chain in self._area_chains:
            for area in chain:
                if area.life_state is not AreaLifeState.retain:
                    continue
                if self._area_observe_range_mapping.get(area) is None:
                    continue
                self._area_observe_range_mapping[area].latest = expected_observe_latest
                ob_range = self._area_observe_range_mapping[area]
                area.observe(self._context[ob_range.start:ob_range.latest + 1])
        # 4. Fast forward
        candidates, next_cursor = self._cursor_forward()
        # 5. Unfold (Taking Effect)
        for area in candidates:
            effect_range = self._area_effect_range_mapping.get(area)
            observe_range = self._area_observe_range_mapping.get(area)

            content = area.tick()
            if content is None:
                continue
            if len(content) == 0:
                raise ValueError("Area return empty content is illegal.")

            content_start: int = len(self._context)
            content_end = len(self._context) + len(content) - 1
            if effect_range is None:
                self._area_effect_range_mapping[area] = _EffectRange(
                    content_start, content_end
                )
            else:
                self._area_effect_range_mapping[area].latest = content_end

            # We need to update the ObserveRange as a handel.
            # Batch update at 3.
            if observe_range is None:
                self._area_observe_range_mapping[area] = _ObserveRange(
                    content_start, content_start
                )
            else:
                pass
            for message in content:
                self._context.emplace_message(message)
        # 5. Store Cursor
        self._cursor_store = next_cursor

        return self._context
