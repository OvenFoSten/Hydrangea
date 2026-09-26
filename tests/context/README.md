# CoopContext contract tests

These tests target the current AreaLane/AreaLayout runtime and do not preserve
the previous scheduling API. They import the real package normally. They never
call an LLM, use a live provider client, or patch the runtime's collector/GC.

## Run

From the repository root, in its Python 3.10+ environment:

```sh
python -m pip install -e '.[test]'
python -m pytest tests/context -q
python -m pytest tests/context -q --cov --cov-report=term-missing --cov-report=json:/tmp/coop-coverage.json
python tests/context/check_mutations.py --json /tmp/coop-mutations.json
python -m pytest -q
```

`--cov` uses the package-level source configured in pyproject.toml and reports
only CoopContext. Avoid a dotted submodule argument to `--cov`: early source
discovery can import provider dependencies before pytest has finished starting.
Coverage is a gap-finding aid, not a substitute for assertions or the mutations.

Hypothesis runs 500 interval cases and 100 state-machine examples per backend,
with at most 50 rule steps each. Cases are deterministic, deadlines and the
example database are disabled, and failures are shrunk automatically. Add
`--hypothesis-show-statistics` to inspect counts. The state-machine failure notes
include external operations and the callback event trace. Teardown drains all
remaining Areas after successful scenarios; it does not retry a failed runtime.

## Contracts fixed by these tests

- Lane declarations use natural order; overlay pushes onto the target lane's
  stack. It does not globally jump the cursor. Append does not preempt.
- Layout and cross-Area external decisions change between unfolds. Callbacks
  may update their own state. Timing is sampled before tick; changes in tick
  affect the next check. Changes in observe precede the current timing check.
- Identity, not configuration equality, identifies an Area. Inherited identity
  hash stays stable; valid structural Protocol implementations and ordinary hash
  collisions are supported. Runtime enforcement of `@final` is not promised.
- None creates/retains observation tracking without fabricating effects. An
  empty list from tick is an error. Observation includes subsequent Area output
  and model replies, not just the producing Area's messages.
- Observe.latest can be -1 for an empty Context, or point at a prospective reply
  when a range is first created. A retired Area's unused latest can be stale
  after unrelated tail reclamation. Bounds are checked at the relevant phase.
- Untouched retirement: gc_prologue once, no promote. Observe-only retirement:
  promote then gc_prologue once, no truncation of its own. Effect-owning
  retirement: both callbacks only after legal tail selection.
- Every collected Area releases its test resource once. Uncollected/blocked
  Areas retain resources. Python object destruction is not required: callers
  can still hold references to declarations, Areas, or stale handles.
- Promotion blocks with different last_touched values appear in ascending
  order. Each Area's own message order and promote-before-cleanup relation hold.
  No global cleanup ordering, untouched ordering or tie-break ordering is fixed.
- Input validation is atomic. Callback errors propagate and stop subsequent
  work; no rollback, recovery or retry semantics are required.

## Coverage map

| Module | Responsibility |
| --- | --- |
| test_coop_context.py | Identity, layout lowering, validation atomicity, handle ownership and lifetime, stack primitives |
| test_scheduling.py | Timing sampling, stable full cycles, wraparound, append/overlay and cursor repair |
| test_area_patterns.py | Observe/Effect tracking, model replies, future/empty observations and GC-before-observe |
| test_collection.py | Closed-interval geometry, transitive components, barriers and all candidate categories |
| test_retired_without_effect.py | Untouched and observe-only lifetime/resource release, including empty Context |
| test_gc.py | Exact truncation, native identity, promotion, cumulative garbage, deletion order, guards and exceptions |
| test_coop_context_workflow.py | External conditional activation, layered overlay, cancellation, compaction and reuse |
| test_properties.py | Generated geometry compared with the independent overlap-graph oracle |
| test_stateful.py | Public-operation sequences compared with independent layout, message and lifecycle ledgers |

The graph oracle uses pairwise overlap edges and connected components, not the
production collector's descending scan. Synthetic geometry tests seed private
ranges deliberately; public tests and state-machine sequences create their
ranges through unfold. State-machine expectations do not read production range
maps or production candidate lists. Promotion ties are validated as permissible
orders rather than treated as an arbitrary fixed ordering.

## Failures and mutation evidence

Core failures must remain ordinary failing tests with their minimal example;
do not skip/xfail them or modify the implementation to make this suite green.
The mutation runner first verifies its selected baseline, then changes only
temporary copies. It checks ten representative faults: extra cursor movement,
tail off-by-one, missing observation initialization, missing untouched
collection/cleanup, sentinel collision, barrier equality, transitive overlap,
partial compose insertion and forward-index deletion. Collection errors and
timeouts do not count as successful mutation detections.

## Performance microbenchmarks

```sh
PYTHONPATH=. python -B tests/context/benchmark_coop_context.py --output /tmp/coop-performance.json
```

This is a standalone Linux benchmark, not a timing assertion in the correctness
suite. It measures real `_collect`, `_gc` and `unfold` calls at 10, 100, 1,000 and
10,000 Areas, with two warmups and eleven batches per case. JSON retains every
batch, median, quartiles, environment details and runtime source hashes.
Use `--cpu` to select an available CPU (default 2), `--scales`, `--samples`,
`--only collect|gc|unfold` and `--scenario` for focused reruns.

Collect uses OpenAI because it inspects lengths/ranges only. GC and unfold cover
both actual backends, one large Lane versus one Area per Lane, and empty versus
shared-history observations. Promotion and emission include native message
conversion. No model/client/network calls, coverage or profiling are involved.

Construction, private layout/range seeding, collect-plan preparation for isolated
GC, correctness checks and Python cyclic collection are outside timing windows.
Ordinary reference counting remains enabled. Callers retain Area references;
prefilled Context entries share a valid native short-message object. The default
observe callback stores the real slice; tick/promote return prepared messages
and cleanup is a no-op. Thus these are framework microbenchmarks, not end-to-end
latencies for application callbacks, arbitrary message payloads or compose.
Record load/frequency conditions when comparing runs: CPU affinity does not make
a shared host exclusive, and no hard performance pass/fail threshold is implied.
