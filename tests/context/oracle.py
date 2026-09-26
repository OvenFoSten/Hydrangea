"""Independent collector specification, using an overlap graph rather than a scan.

Only plain integer keys and positional data enter this model. It neither calls
the production collector nor depends on its candidate order or private helpers.
"""

from collections.abc import Mapping, Set


def expected_collection(
    registered: Set[int],
    retired: Set[int],
    effects: Mapping[int, tuple[int, int]],
    observes: Mapping[int, tuple[int, int]],
) -> tuple[set[int], int | None]:
    selected = set(registered & retired) - effects.keys()
    roots = [start for key, (start, _) in observes.items() if key not in retired and key not in effects]
    barrier = max(roots, default=None)

    # Build all overlap edges explicitly, then obtain connected components.
    neighbours = {key: set() for key in effects}
    for a, (a_start, a_end) in effects.items():
        for b, (b_start, b_end) in effects.items():
            if a != b and max(a_start, b_start) <= min(a_end, b_end):
                neighbours[a].add(b)

    remaining = set(effects)
    components: list[set[int]] = []
    while remaining:
        pending = [min(remaining)]
        component: set[int] = set()
        while pending:
            key = pending.pop()
            if key not in component:
                component.add(key)
                pending.extend(neighbours[key] - component)
        remaining.difference_update(component)
        components.append(component)

    components.sort(key=lambda keys: max(effects[key][1] for key in keys), reverse=True)
    earliest = None
    for component in components:
        left = min(effects[key][0] for key in component)
        if not component <= retired or (barrier is not None and left <= barrier):
            break
        selected.update(component)
        earliest = left
    return selected, earliest
