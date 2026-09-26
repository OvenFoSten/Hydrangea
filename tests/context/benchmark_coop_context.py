"""Repeatable microbenchmarks of real CoopContext methods (not a pytest test).

Run from the repository root with the repository's Python environment:
    PYTHONPATH=. python tests/context/benchmark_coop_context.py --output /tmp/coop-perf.json

Fixture construction, validation and cyclic GC are outside measured windows.
Private layout/range seeding deliberately excludes compose's input validation.
Callbacks do minimal work; normal Context conversion and slicing remain intact.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import time

from hydrangea.context import Context
from hydrangea.context.area.core import Area, InvokeTiming, LifeState
from hydrangea.context.coop_context import (
    CoopContext, _AreaChain, _CollectPlan, _EffectRange, _ObserveRange,
)
from hydrangea.gateway import GatewayType
from hydrangea.message import Message, Role


PAYLOAD = Message(role=Role.user, content="benchmark message: 32 characters")
ROOT = Path(__file__).resolve().parents[2]
CORE_FILES = (
    "hydrangea/context/coop_context.py",
    "hydrangea/context/area/core.py",
    "hydrangea/context/core.py",
    "hydrangea/openai/context.py",
    "hydrangea/gemini/context.py",
)


class BenchArea(Area):
    def __init__(self, *, emit: bool = False, promote: bool = False) -> None:
        super().__init__(invoke_timing=InvokeTiming.deferrable)
        self.output = [PAYLOAD] if emit else None
        self.promotion = (PAYLOAD,) if promote else ()

    def tick(self) -> list[Message] | None:
        return self.output

    def promote(self) -> tuple[Message, ...]:
        return self.promotion


@dataclass(frozen=True)
class Spec:
    operation: str
    scenario: str
    backend: str
    n: int
    layout: str = "one"
    history: int = 0


@dataclass
class Fixture:
    spec: Spec
    coop: CoopContext
    areas: list[BenchArea]
    plan: _CollectPlan | None = None
    result: object = None

    def run(self) -> None:
        if self.spec.operation == "collect":
            self.result = self.coop._collect()
        elif self.spec.operation == "gc":
            assert self.plan is not None
            self.coop._gc(self.plan)
        else:
            self.result = self.coop.unfold()


def native_template(backend: str):
    context = Context(GatewayType[backend])
    context.emplace_message(PAYLOAD)
    return context[:][0]


NATIVES = {backend: native_template(backend) for backend in ("openai", "gemini")}


def build(spec: Spec) -> Fixture:
    context = Context(GatewayType[spec.backend])
    coop = CoopContext(context)
    scenario = spec.scenario
    effect = "effect" in scenario or scenario == "promote_one"
    observe = effect or "observe" in scenario or scenario in (
        "steady_empty", "immediate_first", "shared_history",
    )
    retired = spec.operation == "gc" or "retired" in scenario or scenario == "retire_effects"
    size = spec.n if effect else spec.history
    for _ in range(size):
        context.push_back(NATIVES[spec.backend])
    areas = [
        BenchArea(emit=scenario == "emit_one", promote=scenario == "promote_one")
        for _ in range(spec.n)
    ]
    if areas:
        if spec.layout == "one":
            coop._area_chains = [_AreaChain(*reversed(areas))]
        else:
            coop._area_chains = [_AreaChain(area) for area in areas]
    if retired:
        for area in areas:
            area._retire()
    if scenario == "immediate_first" and areas:
        areas[0]._invoke_timing = InvokeTiming.immediate
    indices = list(range(spec.n))
    if "shuffled" in scenario:
        random.Random(8721 + spec.n).shuffle(indices)
    if effect:
        for index in indices:
            start = 0 if "overlap" in scenario else index
            coop._area_effect_range_mapping[areas[index]] = _EffectRange(start, index)
    if observe:
        for index, area in enumerate(areas):
            start = index if effect and "overlap" not in scenario else 0
            coop._area_observe_range_mapping[area] = _ObserveRange(start, size - 1)
    fixture = Fixture(spec, coop, areas)
    if spec.operation == "gc":
        fixture.plan = coop._collect()
        assert fixture.plan is not None and len(fixture.plan.candidates) == spec.n
    return fixture


def validate(fixture: Fixture) -> None:
    spec, coop, areas = fixture.spec, fixture.coop, fixture.areas
    if spec.operation == "collect":
        if spec.scenario.startswith("live_"):
            assert fixture.result is None
        else:
            plan = fixture.result
            assert isinstance(plan, _CollectPlan)
            assert len(plan.candidates) == spec.n
            assert {candidate.area for candidate in plan.candidates} == set(areas)
            assert plan.earliest == (0 if "effect" in spec.scenario else None)
        assert sum(len(chain) for chain in coop._area_chains) == spec.n
        return
    if spec.operation == "gc" or spec.scenario == "retire_effects":
        assert not coop._area_chains
        assert not coop._area_effect_range_mapping
        assert not coop._area_observe_range_mapping
        assert len(coop._context) == (spec.n if spec.scenario == "promote_one" else 0)
        had_effect = "effect" in spec.scenario or spec.scenario == "promote_one"
        assert len(coop.garbage) == (spec.n if had_effect else 0)
        return
    assert fixture.result is coop._context
    assert sum(len(chain) for chain in coop._area_chains) == spec.n
    assert len(coop._area_observe_range_mapping) == spec.n
    assert all(area.life_state is LifeState.retain for area in areas)
    if spec.scenario == "emit_one":
        assert len(coop._context) == spec.n
        assert len(coop._area_effect_range_mapping) == spec.n
    else:
        assert len(coop._context) == spec.history
        assert not coop._area_effect_range_mapping
        assert all(len(area._observe_snapshot) == spec.history for area in areas)


def measure(spec: Spec, *, samples: int, target_ms: float) -> dict:
    # Probe and warm up with fresh state: mutating operations are never reused.
    estimate = 1
    for _ in range(2):
        fixture = build(spec)
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            start = time.perf_counter_ns()
            fixture.run()
            estimate = max(1, time.perf_counter_ns() - start)
        finally:
            if was_enabled:
                gc.enable()
        validate(fixture)
        del fixture

    # Bound memory even for long observation windows and high area counts.
    fixture_cap = max(1, 50_000 // max(1, spec.n))
    snapshot_cap = max(1, 12_500_000 // max(1, spec.n * spec.history))
    batch = min(512, fixture_cap, snapshot_cap, max(1, math.ceil(target_ms * 1e6 / estimate)))
    durations = []
    for _ in range(samples):
        fixtures = [build(spec) for _ in range(batch)]
        gc.collect()
        was_enabled = gc.isenabled()
        gc.disable()
        try:
            start = time.perf_counter_ns()
            for fixture in fixtures:
                fixture.run()
            elapsed = time.perf_counter_ns() - start
        finally:
            if was_enabled:
                gc.enable()
        durations.append(elapsed / batch)
        for fixture in fixtures:
            validate(fixture)
        del fixture, fixtures
    quartiles = statistics.quantiles(durations, n=4, method="inclusive")
    median = statistics.median(durations)
    return {
        **asdict(spec),
        "lane_count": 0 if not spec.n else 1 if spec.layout == "one" else spec.n,
        "context_messages_before": spec.n if "effect" in spec.scenario or spec.scenario == "promote_one" else spec.history,
        "samples": samples,
        "operations_per_sample": batch,
        "median_us": median / 1000,
        "q25_us": quartiles[0] / 1000,
        "q75_us": quartiles[2] / 1000,
        "min_us": min(durations) / 1000,
        "max_us": max(durations) / 1000,
        "ns_per_area": median / spec.n if spec.n else None,
        "sample_ns_per_operation": durations,
    }


def specs(scales: list[int], backends: list[str]) -> list[Spec]:
    result = []
    # Collector only consults lengths and ranges, not provider conversions.
    for n in scales:
        for scenario in (
            "live_untouched", "retired_untouched", "retired_observe",
            "retired_effects_sorted", "retired_effects_shuffled",
            "live_effects_shuffled", "retired_effects_overlap_shuffled",
        ):
            result.append(Spec("collect", scenario, "openai", n))
    for backend in backends:
        result.append(Spec("unfold", "empty", backend, 0))
        for n in scales:
            for layout in ("one", "many"):
                for scenario in ("retired_untouched", "retired_observe", "retired_effects", "promote_one"):
                    result.append(Spec("gc", scenario, backend, n, layout))
                for scenario in ("steady_empty", "immediate_first", "emit_one", "retire_effects"):
                    result.append(Spec("unfold", scenario, backend, n, layout))
            result.append(Spec("unfold", "shared_history", backend, n, "many", 100))
        for n, history in ((1000, 1000), (1000, 10_000), (10_000, 1000)):
            if n in scales:
                result.append(Spec("unfold", "shared_history", backend, n, "many", history))
    return result


def read_optional(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def source_hashes() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CORE_FILES}


def environment() -> dict:
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "python_executable": os.path.realpath(os.sys.executable),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "lscpu": subprocess.check_output(["lscpu", "--json"], text=True),
        "meminfo": read_optional("/proc/meminfo"),
        "os_release": read_optional("/etc/os-release"),
        "governor_cpu0": read_optional("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "no_turbo": read_optional("/sys/devices/system/cpu/intel_pstate/no_turbo"),
        "load_average": os.getloadavg(),
        "versions": {name: importlib.metadata.version(name) for name in ("google-genai", "openai", "pydantic")},
        "source_sha256": source_hashes(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scales", type=int, nargs="+", default=[10, 100, 1000, 10_000])
    parser.add_argument("--backends", choices=["openai", "gemini"], nargs="+", default=["openai", "gemini"])
    parser.add_argument("--samples", type=int, default=11)
    parser.add_argument("--target-ms", type=float, default=5.0)
    parser.add_argument("--cpu", type=int, default=2)
    parser.add_argument("--only", choices=["collect", "gc", "unfold"])
    parser.add_argument("--scenario", help="Optional exact scenario filter")
    args = parser.parse_args()
    if args.samples < 3 or min(args.scales) < 1 or args.target_ms <= 0:
        parser.error("Use at least 3 samples, positive scales and positive target-ms")
    os.sched_setaffinity(0, {args.cpu})
    cases = specs(args.scales, args.backends)
    cases = [case for case in cases if (not args.only or case.operation == args.only) and (not args.scenario or case.scenario == args.scenario)]
    report = {
        "environment_before": environment(),
        "method": {
            "samples": args.samples, "warmups": 2, "target_batch_ms": args.target_ms,
            "seed": 8721, "fixture_construction_timed": False,
            "python_cyclic_gc_during_timing": False,
            "layout_and_range_setup": "White-box seeding; compose validation not benchmarked",
            "native_prefill": "References to one valid native short-message object per backend",
            "callbacks": "No event logging; default observe stores real snapshot; tick/promote return prepared messages; default cleanup is no-op",
            "area_references": "Caller retains references throughout each timed operation",
            "scope": "Single-thread CPU-pinned process, no provider/network calls, no coverage or profiler",
        },
        "rows": [],
    }
    started = time.monotonic()
    for index, case in enumerate(cases, 1):
        row = measure(case, samples=args.samples, target_ms=args.target_ms)
        report["rows"].append(row)
        print(f"[{index}/{len(cases)}] {case.operation:7} {case.scenario:33} {case.backend:6} N={case.n:6} {case.layout:4} M={case.history:5} {row['median_us']:12.2f} us", flush=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    report["elapsed_seconds"] = time.monotonic() - started
    report["environment_after"] = environment()
    report["peak_rss_kib_process"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report["original_sources_unchanged"] = report["environment_before"]["source_sha256"] == report["environment_after"]["source_sha256"]
    assert report["original_sources_unchanged"]
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"DONE {len(cases)} cases in {report['elapsed_seconds']:.1f}s; original sources unchanged", flush=True)


if __name__ == "__main__":
    main()
