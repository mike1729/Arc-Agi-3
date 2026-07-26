# S1 Measurements

**Status:** S1-b in progress, 2026-07-26. Field-availability table filled from the vendored source and
the first local run; latency, hardware fit, reliability and the reset experiment are S1-c (Day 3).

## What the reference actually emits — established 2026-07-26

Per-action event stream, `logs/runs/<run>/artifacts/<game>_p<pass>_events.jsonl`, one row per step:

| Field | Note |
|---|---|
| `board` | **full 64×64 grid, not a hash** — satisfies §4.2.1's explicit requirement |
| `board_ascii` | compact symbolic view the agent is actually shown |
| `action_num`, `action_display` | the executed action |
| `analysis_step` | which reasoning turn produced it |
| `level`, `score`, `reward`, `run_status`, `state` | progress markers |

Plus `taaf.game.GameRun`: `history: list[ActionRecord]` (`action`, `generated_tokens`,
`uncached_input_tokens`, `wallclock_seconds`), `intermediate_states`, **`actions_per_level`** and
**`base_actions_per_level`** (real per-level counts and the human baseline — *measured*, not estimated,
unlike AERA), `levels_completed`, `final_score`, `solver_note`, `state ∈ {won, gave_up, cancelled,
crashed}`. Also `transcripts/<game>_p<pass>.txt` and `prompts/prompt.log`.

**`save_request_logs` (D6) is the load-bearing instrumentation flag.** Set true it writes
`requests.jsonl` carrying the full `messages` array, `tools`, `tool_choice`, `finish_reason`,
`analysis_step`, `action` and `request_index_within_turn` — i.e. the `prompt_context_snapshot` and
`raw_model_output` several categories are defined on.

> ⚠ **CORRECTED TWICE, 2026-07-26.**
> **(a)** The table first claimed D6 was already enabled. It was not — the first two ft09 runs produced
> no `requests.jsonl`, so the four categories marked "available with D6" had no supporting evidence.
> **(b)** The correction to (a) then over-generalised, asserting the JSON config "is not a complete
> control surface" and that `analyzer.save_request_logs` "is never read". **That was wrong.** The
> reference's `Makefile` *does* read it — `ANALYZER_SAVE_REQUEST_LOGS ?= $(CONFIG_VALUE)
> analyzer.save_request_logs false` (line 153) — and converts it into `--save-request-logs`. The same
> applies to `analyzer.tool_steps` (line 145). **The field is not inert; we bypassed the Makefile** by
> invoking `python -m inference.framework.run` directly, so nothing translated config into flags.

**The actual lesson, which is narrower and more useful:** `Makefile` is the reference's real entry
point and holds the config→CLI translation layer. Driving `inference.framework.run` directly silently
drops every config-sourced setting to its argparse/code default. **A canonical local launcher that
reproduces the Makefile's translation is needed** — until then, every run must pass the flags
explicitly, and the effective values must be verified from the `HarnessSolver(...)` repr rather than
assumed from the JSON.

**The model's reasoning is exposed.** The MLX server returns `reasoning_content` separately from
`content` (591 and 665 chars in the two D5 probes), so `reasoning_text` is available verbatim.

## Field availability — fill Day 2 (S1-b), before any labelling

A vendored agent you did not write may have no goal field, no predicted delta, no search trace. Each of
the 13 failure categories is defined on specific evidence (`gate_manifest.yaml →
s1.failure_taxonomy.categories.*.evidence`); a category whose evidence the reference does not emit cannot
be labelled at all.

**Propagation rule (§4.2) — the reason this table exists:** a category marked `unavailable` here is
marked `unavailable` in the Day-7 ranking. It is **never counted as zero-frequency.** An unobservable
failure mode that silently ranks last would steer eight weeks of construction away from what may be the
largest lever.

Where a field is missing and cheap to add, adding it is a **permitted deviation** — implement it as a
patch in `agent/patches/` and reference the patch here.

Verdicts: `available` · `partial` (say which half) · `unavailable`.

| # | Category | Evidence the category is defined on | Exposed? | Cheap to add? | Patch ref |
|---|---|---|---|---|---|
| 1 | `goal_unknown` | agent goal field + the transition that actually advanced the level | **partial** — level advancement `available` (events `level`/`state`); **no structured goal field.** The objective exists only as prose inside `reasoning_content` / transcripts | no — would need a solver-side schema change, which alters control flow | — |
| 2 | `action_semantics_unknown` | predicted delta vs observed delta | **partial** — observed delta `available` (consecutive `board`s); **no `predicted_delta` field.** Predictions appear only as prose, when the model happens to state one | no — same objection as #1 | — |
| 3 | `perception_parsing` | frame + parsed state description | **available** — `board` + `board_ascii` + the segmentation view the agent is given, against its own description in `reasoning_content` | — | — |
| 4 | `hidden_state_aliasing_or_memory` | both frames, both actions, both outcomes | **available** — full grids per step make observationally-identical states directly detectable | — | — |
| 5 | `coordinate_unreachable` | candidate set at the step + the coordinate that later worked | **UNAVAILABLE** (corrected) — `valid_actions` is *a list of action **names*** (`prompts.py`: "the current list of valid action names"; sandbox coerces with `[str(item) for item in ...]`). There is **no coordinate candidate set** anywhere, so "a required ACTION6 coordinate was never present in the candidate set" is not decidable from any log | no — would need solver-side coordinate proposal logging | — |
| 6 | `planning_depth` | shortest known successful sequence length vs the agent's effective horizon | **UNAVAILABLE** — see the callout below | no | — |
| 7 | `exploration_or_probe_selection` | action taken + its no-op/redundant outcome + the available alternative | **partial** (corrected) — no-op is `available` (board equality). Alternatives are available only at **action-name granularity**; for ACTION6 games the "higher-yield alternative" is a *coordinate*, which is not enumerable. So: usable on simple-action games, weak on click games | partly | D6 |
| 8 | `progress_signal_misinterpretation` | score/level marker vs the agent's recorded belief | **partial** — markers `available` (`score`, `level`, `reward`); belief is prose only | no | — |
| 9 | `irreversible_mistake` | the transition + the subsequent dead-end | **available** — boards plus terminal `state` | — | — |
| 10 | `invalid_output_interface` | raw agent output + the rejection | **available via D6b** — the stock logger writes only the request, so raw output was recoverable only from the *next* turn's history (losing every episode's final turn) and rejections not at all. **D6b patches the vendored core** to log `response_message` (content + `tool_calls` + `reasoning`), `usage`, and an `api_error` record (exception, status code, body). Logging only; control flow unchanged | added by patch | **D6b** |
| 11 | `retrieval_or_context` | the stored record + the context snapshot that omitted it | **available** — `requests.jsonl` stores the full `messages` array, which *is* the context snapshot | enabled via `--save-request-logs` | D6 |
| 12 | `reasoning_inconsistency` | reasoning text + action | **available** — `reasoning_content` verbatim, paired with the executed action via `analysis_step` | — | — |
| 13 | `latency_or_budget` | timing and budget counters at the terminal step | **available** — `ActionRecord.wallclock_seconds`, `generated_tokens`, `uncached_input_tokens`, against `max_actions` / `max_runtime_minutes` | — | — |

### 🔴 The stratification problem, surfaced on Day 2 as the plan requires

The measurements stub warned: *"`goal_unknown` and `planning_depth` are oversampled by the blind re-rate
and are mutually confounded by design. If either is `unavailable`, the re-rate's stratification loses the
two strata it was built around — surface that on Day 2, not on Day 7."* **Both are now degraded, and this
is that surfacing.**

- **`planning_depth` is `unavailable`, structurally.** The duck is not a search agent — it writes and runs
  Python rather than expanding a search tree — so there is no `effective_search_depth`, no search trace,
  and no representable horizon to compare a sequence length against. This is not a missing log line that a
  patch could add; the quantity the category is defined on **does not exist in this architecture**.
- **`goal_unknown` is `partial`** — the objective is recoverable only as self-reported prose.

Consequences, none of them deferrable to Day 7:

1. Per the propagation rule, `planning_depth` is marked `unavailable` in the Day-7 ranking and is
   **never counted as zero-frequency**. It does not enter `build_order`.
2. The blind re-rate cannot stratify on `planning_depth`. **The re-rate design needs amending before
   Day 5**, since Day 5 is when the sample is drawn. Options, to decide in S1-c: oversample
   `goal_unknown` alone; or re-target the second stratum onto a category that *is* available and
   contested (`exploration_or_probe_selection` is the natural candidate — it is the nearest thing to a
   planning failure this architecture can express).
3. The pre-registered `goal_unknown` / `planning_depth` confound **cannot be measured at all here.**
   That confound was the stated reason the first pass is "descriptive, not causal". With one arm
   unobservable, the confound is not resolved — it is simply invisible. Say so in the close-out rather
   than reporting a clean `goal_unknown` frequency that quietly absorbs it.

This is a property of the *reference architecture*, not of our port, and it would have applied equally on
CUDA. It is the clearest example so far of why the field-availability table exists.

Two consequences to check before Day 5, not after:

- `goal_unknown` and `planning_depth` are **oversampled by the blind re-rate** and are mutually
  confounded by design. If either is `unavailable`, the re-rate's stratification loses the two strata it
  was built around — surface that on Day 2, not on Day 7.
- `reasoning_inconsistency` is defined *solely* on agent rationale. No rationale field means the category
  is unlabelable, not rare.

## Latency

### Concurrency scaling — measured 2026-07-26 (S1-c work pulled forward into S1-b)

Script: `agent/harness/concurrency_sweep.py`. Raw: `logs/concurrency_sweep.json`,
`logs/concurrency_sweep_merged.json`. Model `mlx-community/Qwen3.6-27B-4bit` on the M5 Pro via
`mlx_vlm.server` with `--enable-thinking`; 256-token generations; two sweeps (1,2,4,8 then 3,4,5,6).

| Concurrency | Aggregate tok/s | Per-request tok/s |
|---:|---:|---:|
| 1 | 17.0 | 17.0 |
| 2 | 31.8 | 16.0 |
| 3 | 42.9 | 14.3 |
| 4 | 54.5 | 13.7 |
| **5** | **59.9** ← peak | 12.0 |
| 6 | 54.4 | 9.1 |
| 8 | 45.9 | 5.7 |

Server RSS read **15.7 GiB** at every level. ⚠ **This does NOT establish peak memory and does NOT clear
the 44.06 GiB escalation trigger.** RSS was sampled *after each concurrency batch completed*, so transient
KV-cache growth during generation is invisible to it, and RSS under unified memory is a poor proxy for
peak GPU working set in any case. The honest reading is only that *steady-state* RSS is far below the
threshold. `hardware_fit_vram` remains **unmeasured** and needs a sampler that polls during generation. The 17 tok/s at N=1 agrees
with the ~16.1–16.4 tok/s the server logged during a real game run, so the synthetic prompt is not
flattering the measurement.

**Aggregate scales ~3.5× to N=5, then regresses. Per-request throughput only ever falls.** Decode is
memory-bandwidth-bound on the weights: extra streams amortise the weight reads (aggregate rises) but no
single stream ever speeds up.

#### The consequence that matters for the build

**Concurrency buys breadth, not depth.** The duck's loop *within* one game is strictly sequential — each
model call is conditioned on the previous one — so `concurrent_jobs` parallelises *games*, never the
critical path of one game. It is therefore the right lever for the Day-5 run across 25 games and the
wrong lever for per-game wall-clock, which is what actually stalled the first ft09 attempt.

**Operating point selected: `concurrent_jobs: 4.`** N=5 is the aggregate peak but only ~10% above N=4
while costing ~12% per-request throughput, and N=4 leaves scheduling room for the Python tool sandbox and
the instrumentation processes that share the machine. Recorded in `agent/harness/build_local.sh` as the
default; every latency figure must carry the concurrency it was measured at (freeze §5).

**Escalation trigger #3 does not fire.** The freeze pre-registered "sustainable local concurrency < 4" as
a trigger to escalate to hybrid. The measured usable band is 4–5, so local-only holds — *but with no
margin above 5*, and this is the trigger to re-check after the Day-5 breadth run rather than to treat as
settled.

#### Why a single game is slow — the reference's own budgets, read from the code

Effective analyzer budgets, dumped from the installed module (`inference.agent.tool_agent`):

| Knob | Value | Meaning |
|---|---:|---|
| `_LOCAL_ANALYZER_TOOL_STEPS` | **12** | up to 12 model calls per **one** game action |
| `_LOCAL_ANALYZER_MAX_OUTPUT` | **0** | → `None`: **no cap** on output tokens per call |
| `_LOCAL_ANALYZER_ENABLE_THINKING` | True | reasoning tokens on top of the answer |
| `_LOCAL_ANALYZER_CONTEXT_WINDOW` | 32768 | |
| `_LOCAL_ANALYZER_TOOL_OUTPUT_TOKENS` | 1024 | tool result truncation |

So one game action costs **up to twelve uncapped generations**. At the measured 13.7 tok/s per stream at
concurrency 4, that is minutes per game action, and ft09 needs a 43-action level 1 (208 actions across its
six levels) — before accounting for the agent being less efficient than the human baseline.

**This is the reference's operating point, not a defect of our port.** It is affordable on an RTX PRO
6000 with FP8 weights and 32-way batching; it is not affordable at 13.7 tok/s. Note also that the
config's `analyzer.tool_steps: 0` is **not** wired to `_LOCAL_ANALYZER_TOOL_STEPS` — that constant reads
the `LOCAL_ANALYZER_TOOL_STEPS` environment variable and otherwise takes its code default of 12. Setting
the config field alone changes nothing; the env var is the real lever.

These are first-class knobs the reference already exposes, so bounding them is a *configuration*
deviation rather than a code change — but it is still a deviation with a real fidelity cost, and it must
be measured as its own contrast rather than folded in silently.

#### ⚠ D9's baseline was misidentified — correction before the result below

The D9 entry described the reference operating point as `tool_steps = 12`. **That is wrong.** The
reference's `Makefile` sources it from the config — `LOCAL_ANALYZER_TOOL_STEPS ?= $(CONFIG_VALUE)
analyzer.tool_steps 0` (line 145) — and `inference.json` sets `analyzer.tool_steps: 0`, which
`ToolAgent` interprets as **unlimited** (`self._tool_steps = None if _LOCAL_ANALYZER_TOOL_STEPS <= 0`).

So the reference operating point is **unlimited model calls per game action**, not 12. The `12` we
measured against was the *argparse/code fallback* we landed on by driving
`inference.framework.run` directly and bypassing the Makefile — the same bypass that silently disabled
D6. **D9 was therefore "unlimited → 4" against a baseline that was itself an unintended `12`, not the
clean "12 → 4" the commit message claims.**

Also unapplied by the bypass: `analyzer.yield_seconds` (Makefile default 60), which we never set at all.

**What survives this correction:** the *mechanism* is unaffected. Measured usage is **mean 1.97 calls per
turn**, so neither 4, nor 12, nor unlimited binds — the agent simply does not use many calls per turn.
The negative result stands; its framing did not.

#### D9 (analysis-budget reduction) — NEGATIVE RESULT, and the deviation was reverted

Ran `tool_steps` 12→4 and `max_output` uncapped→1024 on ft09, 4 passes at concurrency 4, 25 min.

| | Reference budgets | D9 tuned |
|---|---|---|
| rate | 284 s/action @ 28 min | 317 s/action @ 22 min, 324 @ 24 min |
| levels | 0 | 0 |

**No measurable speedup.** The request logs (D6) explain it mechanistically — neither knob binds:

| Knob | Reference | D9 cap | Actual usage |
|---|---|---|---|
| `tool_steps` | **unlimited** (`0`, via Makefile) — *not* 12 | 4 | **mean 1.97 calls/turn**; only 13% of turns reach 4 |
| `max_output` | uncapped | 1024 | **median 350 tokens**; binds only at the tail |

`tool_steps: 12` is a *ceiling the agent rarely approaches*, not a target, so cutting it to 4 could only
affect the small tail of turns near the cap. This was the mechanism predicted before the run, and the run
confirmed it.

**D9 was reverted.** A deviation that buys nothing costs fidelity for free. `tool_steps` is back to 12 and
`max_output` to uncapped; `agent/harness/local.env` is retained only as the record of what was tested.
The negative result stays; the deviation does not.

#### ⚠ Correction — the concurrency sweep was measured on an unrepresentative prompt

`agent/harness/concurrency_sweep.py` used 256-token generations on a short prompt and reported **13.7
tok/s per request at concurrency 4**. Under the real workload — a 12.4k-character system prompt plus
accumulated history — median decode is **3.3 tok/s** at the same concurrency, roughly 4× worse.

The sweep's *shape* (aggregate scales to ~5, per-request declines monotonically, memory is not the
ceiling) still holds and still selected the right operating point. Its *absolute numbers* do not transfer
to the agent workload and must not be quoted as the agent's latency. The freeze's own §5 requirement —
measure "under the *actual* batching pattern" — is what this violated, and any latency figure that gates
a threshold has to come from an agent run, not a synthetic probe.

#### Where the time actually goes

Decomposing 317 s/action at concurrency 4: ~193 s is decode (1.97 calls × 97.9 s median), leaving
**~124 s (39%) in prefill, tool execution and overhead**. The cost driver is **per-call long-context
processing**, not call count or generation length — which is precisely what neither D9 knob could touch,
and precisely what FP8 on a datacentre GPU with working prefix caching addresses.

#### Still open — the real single-game constraint

Per-game wall-clock is bounded by **tokens per action**, not by parallelism. The first ft09 attempt
generated roughly 7.6k tokens (~7.5 min at 17 tok/s) before its *first* game action, all of it in the
duck's opening analysis phase. `mlx_vlm.server --thinking-budget` caps that directly, but the reference
runs `thinking: true` and a budget cap is a **new deviation with a real fidelity cost** — to be measured
as its own contrast, not folded in silently. Not yet run.

### Per-action latency table — S1-c

**Generated by script, per §9.** `agent/harness/make_run_tables.py` reads `logs/runs/` and emits
`paper/figures/s1_run_summary.md`, `paper/figures/s1_calls_per_turn.md` and `logs/s1_run_summary.json`.
Every rate quoted below comes from that script, not from an ad-hoc shell command.

*Methodology note, because it changes the numbers:* the script measures elapsed as
`newest artifact mtime − run start`, i.e. the **active** period. The ad-hoc figures reported earlier in
this session used `now − run start`, which includes idle time after the final action and therefore
**overstated** seconds-per-action on any run inspected while mid-action. Where the two disagree, the
script governs — e.g. vc33 reads **74.1 s/action** by script versus 94–109 s/action quoted ad hoc.

Generated table (`paper/figures/s1_run_summary.md`):

| run | passes | actions | levels done | elapsed | s/action/pass |
|---|---:|---:|---:|---:|---:|
| `s1b-ep2` | 1 | 0 | 0 | 0 min | — |
| `s1b-ft09-c4` | 4 | 24 | 0 | 28 min | 280.9 |
| `s1b-ft09-d9-tuned` | 4 | 8 | 0 | 12 min | 374.3 |
| `s1b-ft09-d9-logged` | 4 | 20 | 0 | 25 min | 301.4 |
| **`s1b-vc33-single`** | 1 | 19 | **1** | 23 min | **74.1** |

The consolidated view makes two things plain that the individual runs did not:

1. **vc33 is ~4× faster per action than any ft09 run** (74 vs 281–374 s). That is *not* a property of
   the game — it is the concurrency effect measured directly on the real workload. Every ft09 run used
   concurrency 4, splitting throughput four ways; vc33 used 1. This is the clearest confirmation that
   concurrency buys breadth and costs depth.
2. **`s1b-ep2` recorded 0 actions** — the run that failed for missing environment files. It is kept in
   the table deliberately; a summary that silently dropped failed runs would misrepresent the day.

Calls per turn (`paper/figures/s1_calls_per_turn.md`) — ⚠ **corrected**. The first figures (43 turns,
mean 1.91, 13% at cap) double-counted: D6 writes a `request` **and** a `response` record sharing the same
index, so every response with index 1 looked like a new turn. Filtering to `event == "request"`:

| run | turns | mean calls/turn | max | at cap of 4 |
|---|---:|---:|---:|---:|
| `s1b-ft09-d9-logged` | 24 | **2.62** | 4 | **5/24 = 21%** |
| `s1b-vc33-single` | 15 | 2.20 | 5 | — |

So the earlier claim that the cap "did not bind" is **weaker than stated** — a fifth of turns reached it.
The D9 conclusion still stands, but for a different and now-primary reason: **the ft09 runs executed no
game actions at all**, so D9 was never comparing action throughput in the first place.

## Submission contract — read from the reference notebook, 2026-07-26 (S1-f prep)

Established without spending the 1/day submission quota, by reading the reference notebook we pushed as
a private copy. Two execution modes, switched by an environment variable:

| | Visible "Save & Run" | Hidden competition rerun |
|---|---|---|
| Selector | `KAGGLE_IS_COMPETITION_RERUN` unset/false | set to `1`/`true` |
| Games | **bundled offline env files** at `/kaggle/input/competitions/arc-prize-2026-arc-agi-3/.../environment_files` | live competition Arcade via the Kaggle **gateway** at `ARC_BASE_URL` (default `http://gateway:8001/`), `OperationMode.COMPETITION` |
| Scoring | not scored | through the gateway |
| Output | **must still write `submission.parquet`** | written by the framework |

`submission.parquet` schema is `["row_id", "game_id", "end_of_game", "score"]`; on the unscored visible
path the notebook writes a single placeholder row `["1_0", "1", True, 1]` purely to satisfy Kaggle's
output requirement. The notebook also forces `bm.n_passes = 1` and sets `TAAF_RUN_AS_SUBMISSION` /
`TAAF_MINIMAL_DIAGNOSTICS` so diagnostics and per-frame logging are suppressed during a real rerun.

**Confirms our local setup is on the reference's own offline path** — the competition
`environment_files` the notebook uses in visible mode are exactly the ones we downloaded with the Kaggle
CLI and pointed `--re-arc-environments-dir` at.

### 🔴 The development/submission divergence — a consequence of local-only, and a caveat on S1-d

Kaggle provides CUDA. A Day-6 payload therefore runs **vLLM + FP8 on an RTX PRO 6000** — the reference
stack unmodified. **D1 and D2 do not propagate to the submission at all**: the MLX 4-bit port is a
*local development and instrumentation vehicle*, not the submitted artifact.

That is good for the submission's fidelity, and it creates two problems that must not be discovered at
S1-g:

1. **Local latency and throughput figures do not transfer to Kaggle.** The 13.7 tok/s, the 284 s/action,
   the concurrency-4 ceiling — all are properties of MLX 4-bit on an M5 Pro and say nothing about the
   submitted agent's runtime envelope. `per_action_latency` must therefore be read against the
   *submission* stack before it can gate anything, or its verdict scoped explicitly to local development.
2. **Failure frequencies labelled locally are labelled on a different model.** The Day-5 run at MLX 4-bit
   produces the taxonomy that ranks the build order, but the agent that gets submitted is FP8. D2's
   "unquantified capability loss" was recorded as a fidelity risk; this is where it bites — a quantization
   that changes *which* failures dominate would misrank §11's construction order. The gap is not
   currently measured in either direction.

Neither is fatal and neither is a reason to abandon local-only, but both must be stated in the close-out
rather than absorbed. The cheapest mitigation available is the Kaggle reference run already in flight: it
produces FP8-on-RTX-6000 numbers for the *same solver*, which bounds the size of gap (1) directly and
gives a first handle on (2) via per-game outcomes.

## Hardware fit

- Peak VRAM:
- VRAM headroom:
- Throughput degradation:

## Legal-action reliability

- Accepted actions:
- Emitted actions:
- Validity:
- Rejection taxonomy:

## Public-game progress

### ✅ S1-b hard exit MET — 2026-07-26

> ⚠ **CORRECTED.** First recorded as "14 actions, score 25.00". That counted **event rows**, which
> interleave `analysis` reasoning snapshots with executed `action` records. `benchmark.json`'s
> `actions_per_level` is authoritative. The score was **understated by 2.4×**.

| | |
|---|---|
| Game | `vc33-5430563c` |
| Level 1 cleared in | **9 actions** (not 14) |
| Human baseline | 7 → agent used **1.29× baseline** |
| Level-1 score | `min(115, (7/9)² × 100)` = **60.49** (not 25.00) |
| Evidence | `benchmark.json`: `actions_per_level [9, 11, …]` vs `base_actions_per_level [7, 18, …]` |

Agent advanced to level 2.

### 🔴 The ft09 runs executed ZERO game actions — the whole ft09 narrative was wrong

The corrected table (`paper/figures/s1_run_summary.md`) reports **0 executed actions** for all three
ft09 runs. Their event streams contain only `initial` and `analysis` records — **not one `action`**.

Everything previously said about ft09 was therefore measuring the wrong quantity:

| Claim made earlier | Reality |
|---|---|
| "284 s per game action" | there were **no game actions**; that was seconds per *analysis snapshot* |
| "6.5 actions per pass projected" | 0 actions in 65 minutes across three runs |
| "level 1 needs ~3.4 h per pass at this rate" | unsupported — no action rate was ever measured on ft09 |
| "the constraint is per-action cost" | the constraint is that **the agent never committed to an action at all** |

**This is a qualitatively different failure and a more interesting one.** The duck spent 65 minutes
across three runs analysing ft09 and never executed a single game action, while on vc33 it acted 20
times in the same order of wall-clock. That is not a throughput problem — it is the agent failing to
converge on a decision. It plausibly belongs to `exploration_or_probe_selection` or `goal_unknown` in the
taxonomy, and it should be labelled on the Day-5 run rather than treated as a latency observation.

**Consequently the D9 comparison compared analysis throughput, not action throughput**, and every
seconds-per-action figure quoted for ft09 in this file and in commit messages is withdrawn.

#### Preliminary mechanism — one observed instance, NOT a frequency claim

During a four-turn stall on vc33 (actions static at 25 while analysis went 17→20), the D6 request log
shows the agent issuing a segmentation inspection and then **repeating the byte-identical inspection**
before eventually acting. A redundant probe with zero information yield.

**Precision that matters for the taxonomy:** these are *tool* calls, not game actions. Under the surgical
controller (R2 = `accumulates`, `c_reset` = 1), wasted **game** actions cost score directly; wasted
**tool** calls cost only wall-clock. So this instance is a **latency** pathology, not a scoring one, and
labelling it `exploration_or_probe_selection` — a category defined on *actions* — would be a category
error unless the definition is read as covering tool-level probing too. **Resolve that scoping question
before Day-5 labelling**, or the frequency table will mix two different costs.

This is `n = 1`. It is recorded as a hypothesis for the mechanism behind the ft09 zero-action stall
(loop on identical inspections, never converge, never act), to be tested against the full Day-5 run —
not as a measured frequency.

### Reproduction target

- Frozen target:
- Observed result:
- Gap:

## Reset and action accounting

### R1 — knowledge preservation across RESET. **Result: `deterministic`** (2026-07-26)

Script `agent/harness/r1_determinism.py`; raw `logs/r1_determinism.json`. Sampling exactly as
pre-registered: 2 distinct public games (`ft09-0d8bbf25`, `ls20-9607627b`), 2 prefixes each (10 and 40
scripted actions), 3 replays per prefix, exact frame-sequence equality.

| Game | Prefix | Replays | Verdict |
|---|---:|---:|---|
| ft09-0d8bbf25 | 10 | 3 | identical |
| ft09-0d8bbf25 | 40 | 3 | identical |
| ls20-9607627b | 10 | 3 | identical |
| ls20-9607627b | 40 | 3 | identical |

No divergence anywhere, so no first-divergence index to record.

**Falsification check — required, because "identical" is trivially true if nothing ever changes.**
Distinct observations *within* each replay: ft09 **11/11** steps at prefix 10 and **34/41** at prefix 40;
ls20 **9/11** and **31/41**. The grids genuinely change step to step, so agreement across replays is a
real property and not an artefact of a static board. (ls20's repeats are no-op actions — incidentally
useful evidence for `exploration_or_probe_selection` later.)

**Scope — do not overclaim.** This ran against the **OFFLINE competition environment files**, the same
game implementations Kaggle's *visible* path uses. It is evidence about the **game code**. It is **not** a
test of competition mode, whose scorecard and one-`make()` restrictions (V5–V7) differ. The supported
claim is exactly: *these tested prefixes replay exactly, offline.* Not "everything learned transfers".

#### ⚠ A bug that would have inverted this result, caught before it was recorded

The first implementation hashed `FrameDataRaw.model_dump()`. That method **silently omits the `frame`
field holding the numpy grids**, so the digest compared metadata only and never looked at a single pixel.
It also included `full_reset` — `True` on the first reset after `make()`, `False` on every later one —
which made the first replay of each prefix "diverge at step 0" for a reason with nothing to do with
determinism. That run reported **`inconclusive`**, and it was wrong in both directions at once: a false
divergence on the short prefixes, and a meaningless "identical" on the long ones.

It was caught only because the pattern was internally contradictory — diverging at step 0 on a 10-action
prefix while a 40-action prefix on the same environment matched. **A metadata-only digest that had
happened to agree everywhere would have produced a confident `deterministic` with no pixel ever
compared.** The falsification check above now exists to make that failure mode impossible to repeat.

### R2 — action accounting

**Unblocked**: R2's precondition is `r1 == deterministic`, which now holds. Not yet run — it needs live
scorecards (close-then-read, forced by V7) and the three preconditions checked before any score is read.

**Result: `accumulates`** (2026-07-26). Script `agent/harness/r2_action_accounting.py`; raw
`logs/r2_action_accounting.json`. Game `tu93-0768757b`, H(level 1) = 19, `a = max(20, round(1.5×19)) = 28`,
`w = a = 28`, 3 repetitions per arm on independent scorecards.

| Arm | Score | `actions` | `resets` |
|---|---:|---:|---:|
| A (clean) | 1.02324 | 28 | 0 |
| B (waste → RESET → same completion) | 0.24691 | **57** | 1 |

`r = √(median_A / median_B) = 2.0357`, inside the pre-registered `accumulates` band `[1.85, 2.20]`.
Within-arm spread 0.0 for both.

**Waste validity — checked before any score was read**, as the pre-registration demands: **84/84** wasted
actions accepted *and* **84/84** produced an observable state change. This is the check that prevents R2
reading `restarts` when the truth is `accumulates`; had the wasted actions been no-ops the two arms would
have scored alike and the answer would have inverted.

#### Two independent measurements agree to four decimal places

- pre-registered estimator: `√(1.0232 / 0.2469)` = **2.0357**
- direct action counts: `(a + w + c_reset)/a` = `57/28` = **2.0357**

And the scores reproduce the V8 formula exactly — arm A `(19/28)²×100 / 45 = 1.0232`, arm B
`(19/57)²×100 / 45 = 0.2469`, where 45 is the sum of tu93's nine level weights. The scorer, the formula
as V8 corrects it, and both estimators are mutually consistent.

#### `c_reset` resolved, not absorbed

The pre-registration treated `c_reset ∈ {0,1}` as unknown and absorbed it by requiring `a ≥ 20`. The
scorer exposes `actions` directly, so it was measured instead: **57 = 28 + 28 + 1**, so

> **RESET is itself a scored action. `c_reset = 1`.**

#### Preconditions

| Precondition | Outcome |
|---|---|
| per-level score exposed | **Not exposed** — `level_scores` returned empty. Satisfied via the pre-registered *fallback*: both arms restricted to level 1 and closed immediately, so the level weighting is identical across arms and cancels |
| V6 permits same-game repeat | satisfied offline — independent scorecards, one `make()` each. Not evidence about competition mode |
| cap not saturated | satisfied, verified from arm A **before** arm B ran: 46.0 per-level against a cap of 115 |

That last one nearly went wrong. The BFS-shortest completion is **18 actions — shorter than the human
baseline of 19** — which would have scored 111.4 against the 115 cap and failed the precondition outright.
Holding `a` to the pre-registered 28 rather than using the shortest sequence found is what kept arm A
clear, and it is exactly what the `a ≈ 1.5H` rule exists for.

#### Scope limits

- **Offline environment files, not competition mode** (V5–V7 differ) — same caveat as R1.
- **One game.** R2's design is deliberately single-game, because identifiability requires `H` and the
  level weight to cancel. So this is not a design flaw — but generalisation of the accounting rule across
  games is untested and must not be asserted.
- **Spread was 0.0 trivially**, because the offline environment is deterministic. The `spread ≤ 0.10`
  criterion therefore did no real work: the three repetitions checked reproducibility, not sampling noise.
  The pre-registration anticipated live-API variance, which this run does not exercise.

### 🎯 Controller fork — RESOLVED

`R1 = deterministic` + `R2 = accumulates` → **surgical information-per-action**.

Replay is reliable, but **every probe costs score directly**: wasted actions accumulate across resets, and
the RESET itself is scored. Information is not free, so the aggressive explore-then-speedrun controller
would bleed score on every probe. This is also the conservative branch the pre-registration says to
default to under doubt — but here it is not a default, it is the measured outcome.

- R1 result: `deterministic` — see above
- R2 result: `accumulates`
- Controller selected: **surgical information-per-action**
- R2 result:
- Controller selected:
