"""Run focused regression mutations exclusively in disposable source copies.

Usage (from the repository root):
    python tests/context/check_mutations.py --json /tmp/coop-mutations.json

Exit 0 means the unchanged baseline passed and every mutation caused an actual
test failure. Collection/usage errors, timeouts and surviving mutants are errors,
not successful detections. The real runtime source is never written.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("hydrangea/context/coop_context.py")


@dataclass(frozen=True)
class Mutation:
    name: str
    before: str
    after: str
    test: str


MUTATIONS = (
    Mutation(
        "full_cycle_extra_forward",
        "current_chain = self._area_chains[cursor_index]\n        return (ret, current_chain)",
        "current_chain = self._area_chains[(cursor_index + 1) % chain_count]\n        return (ret, current_chain)",
        "tests/context/test_scheduling.py::test_all_deferrable_keeps_start_across_multiple_rounds",
    ),
    Mutation(
        "tail_length_off_by_one",
        "garbage_length = plan.expected_context_size - plan.earliest",
        "garbage_length = plan.expected_context_size - 1 - plan.earliest",
        "tests/context/test_gc.py::test_single_message_tail_is_not_left_behind",
    ),
    Mutation(
        "none_does_not_create_observe_range",
        "if observe_range is None:\n                self._area_observe_range_mapping[area] = _ObserveRange(",
        "if observe_range is None and content is not None:\n                self._area_observe_range_mapping[area] = _ObserveRange(",
        "tests/context/test_area_patterns.py::test_none_then_emit_then_none_keeps_observation_head_and_effect_bounds",
    ),
    Mutation(
        "untouched_retirement_not_collected",
        "collected_areas.append(_CollectCandidate(area,_INVALID_LAST_TOUCHED))",
        "pass  # mutation: dropped untouched candidate",
        "tests/context/test_retired_without_effect.py::test_cancel_before_first_tick_releases_resources_without_promotion",
    ),
    Mutation(
        "untouched_cleanup_callback_omitted",
        "for candidate in untouched_candidates:\n            area = candidate.area\n            area.gc_prologue()",
        "for candidate in untouched_candidates:\n            area = candidate.area\n            pass",
        "tests/context/test_retired_without_effect.py::test_only_untouched_candidates_do_not_edit_context_or_garbage",
    ),
    Mutation(
        "minus_one_timestamp_collides_with_sentinel",
        "_INVALID_LAST_TOUCHED:Final[int] = -2048",
        "_INVALID_LAST_TOUCHED:Final[int] = -1",
        "tests/context/test_retired_without_effect.py::test_observe_only_retirement_promotes_once_without_truncating",
    ),
    Mutation(
        "barrier_equality_not_protected",
        "component_left <= observe_barrier",
        "component_left < observe_barrier",
        "tests/context/test_collection.py::test_observe_barrier_preserves_head_including_equal_boundary",
    ),
    Mutation(
        "overlap_does_not_extend_component_left",
        "component_left = min(\n                        component_left,\n                        ef_range.start,\n                    )",
        "component_left = component_left",
        "tests/context/test_collection.py::test_overlap_can_pull_component_left_across_barrier",
    ),
    Mutation(
        "compose_loses_whole_batch_preflight",
        "self._validate_area_batch(areas)",
        "pass  # mutation: no whole-layout validation",
        "tests/context/test_coop_context.py::test_compose_rejects_duplicates_across_entire_batch_atomically",
    ),
    Mutation(
        "forward_deletion_shifts_area_indices",
        "for area_index, area in reversed(list(enumerate(chain))):",
        "for area_index, area in list(enumerate(chain)):",
        "tests/context/test_gc.py::test_gc_sweeps_adjacent_members_and_chains_without_index_drift",
    ),
)


def run_tests(directory: Path, selectors: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", "-m", "pytest", *selectors, "-q", "--tb=short", "--no-cov", "-p", "no:cacheprovider"],
        cwd=directory,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="Optional machine-readable result file")
    args = parser.parse_args()
    source = (ROOT / SOURCE).read_text()
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    for mutation in MUTATIONS:
        if source.count(mutation.before) != 1:
            raise RuntimeError(f"Mutation anchor changed or is ambiguous: {mutation.name}")
        compile(source.replace(mutation.before, mutation.after, 1), str(SOURCE), "exec")

    result = {"source": str(ROOT / SOURCE), "source_sha256": source_hash, "baseline_passed": False, "mutations": []}
    baseline = run_tests(ROOT, sorted({mutation.test for mutation in MUTATIONS}))
    result["baseline_exit_code"] = baseline.returncode
    result["baseline_output"] = baseline.stdout
    if baseline.returncode != 0:
        print(baseline.stdout, flush=True)
        print("Baseline failed; mutation results would not be meaningful.", flush=True)
        if args.json:
            args.json.write_text(json.dumps(result, indent=2) + "\n")
        return 1
    result["baseline_passed"] = True
    print("PASS unchanged baseline", flush=True)

    with tempfile.TemporaryDirectory(prefix="hydrangea-coop-mutations-") as temporary:
        base = Path(temporary)
        for mutation in MUTATIONS:
            work = base / mutation.name
            work.mkdir()
            ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".hypothesis")
            shutil.copytree(ROOT / "hydrangea", work / "hydrangea", ignore=ignore)
            shutil.copytree(ROOT / "tests" / "context", work / "tests" / "context", ignore=ignore)
            shutil.copy2(ROOT / "pyproject.toml", work / "pyproject.toml")
            (work / SOURCE).write_text(source.replace(mutation.before, mutation.after, 1))
            completed = run_tests(work, [mutation.test])
            killed = completed.returncode == 1 and "FAILED " in completed.stdout
            status = "killed" if killed else "survived" if completed.returncode == 0 else "error"
            result["mutations"].append({**asdict(mutation), "status": status, "exit_code": completed.returncode, "output": completed.stdout})
            print(f"{status.upper()} {mutation.name}", flush=True)

    unchanged = hashlib.sha256((ROOT / SOURCE).read_bytes()).hexdigest() == source_hash
    result["original_source_unchanged"] = unchanged
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n")
    succeeded = unchanged and all(item["status"] == "killed" for item in result["mutations"])
    print(f"{sum(item['status'] == 'killed' for item in result['mutations'])}/{len(MUTATIONS)} killed; original source unchanged={unchanged}", flush=True)
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
