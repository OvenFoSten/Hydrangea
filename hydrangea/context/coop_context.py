from dataclasses import dataclass
from collections.abc import Iterator


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
        return iter(self._areas)

    def __delitem__(self, index: int):
        del self._areas[index]

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

    def _collect(self) -> _CollectPlan | None:
        collected_areas: list[_CollectCandidate] = []
        expected_size = len(self._context)
        earliest = expected_size
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

                if area.life_state is AreaLifeState.retain:
                    break

                component_left = min(
                    component_left,
                    ef_range.start,
                )
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

            if earliest == expected_size:
                return _CollectPlan(
                    None,
                    expected_size,
                    tuple(collected_areas),
                )

            return _CollectPlan(
                earliest,
                expected_size,
                tuple(collected_areas),
            )

    def _gc(self, plan: _CollectPlan) -> None:
        if plan.expected_context_size != len(self._context):
            raise RuntimeError("Unexpected context change after collected.")

        candidates = plan.candidates
        promotes: list[Message] = list()
        ordered = sorted(
            candidates,
            key=lambda candidate: candidate.last_touched,
        )
        # 1. GC Notify & Promote
        for candidate in ordered:
            area = candidate.area
            promotes.extend(area.promote())
            area.gc_prologue()
        # 2. Sweep Context & Garbage
        if plan.earliest is not None:
            garbage_length = plan.expected_context_size - 1 - plan.earliest
            self.garbage.extend(self._context.detach_tail(garbage_length))
        # 3. Promote
        for promote in promotes:
            self._context.emplace_message(promote)
        # 4. Sweep Areas
        sweep_set: set[_Area] = set()
        for candidate in candidates:
            sweep_set.add(candidate.area)
        empty_chain_index: list[int] = list()
        for chain_index, chain in enumerate(self._area_chains):
            for area_index, area in enumerate(chain):
                if area in sweep_set:
                    del chain[area_index]
            if chain.is_empty():
                empty_chain_index.append(chain_index)
        for e_i in empty_chain_index:
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
        if chain_size == 0:
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
