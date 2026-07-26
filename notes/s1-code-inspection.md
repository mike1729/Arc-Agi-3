# S1 code inspection — 2026-07-26

Findings from a full read of the harness written on 2026-07-26, conducted while the S1-e breadth run
was in flight. Recorded the same day, with the configuration that produced them (§5).

Every defect below shares one property: **it is invisible on a single-game run directory.** S1-b and
every measurement before S1-e ran one game per directory, so the whole class survived until chunked
multi-game runs made it reachable.

---

## 1. `game_runs[0]` mis-attribution — HIGH, corrupted a shipped artifact

`s1c_measure.py` and `s1d_label.py` both did:

```python
gr = (b.get("game_runs") or [{}])[0]
```

and then applied that one game's `game_id`, `base_actions_per_level`, `state`, `levels_completed` and
`actions_per_level` to **every** episode and measurement in the directory. A chunk directory holds N
games. `game_runs` is not ordered like the event files, so it was not even reliably "the first game".

**What it corrupted.** `logs/s1d_episodes_kaggle_reference.json` — the Kaggle reference baseline, the
yardstick for all of S1. Twenty-five episodes drawn from twenty-five different games, every one stamped
`game=sk48-d8078629` and scored against sk48's baselines:

| episode | actions | baseline used | true baseline | ratio recorded | true ratio |
|---|---:|---:|---:|---:|---:|
| `bp35` L2 | 11 | 177 | 48 | 0.06× | 0.23× |
| `cn04` L1 | 87 | 61 | 29 | 1.43× | 3.00× |
| `ls20` L1 | 142 | 61 | 22 | 2.33× | 6.45× |
| `sb26` L2 | 159 | 177 | 28 | 0.90× | 5.68× |

Median `action_ratio_vs_baseline` moved **0.90× → 2.03×**. 24 of 25 episodes were wrong; only sk48,
the game it borrowed from, was right.

**Knock-on effect, silent:** the S1-E4 stratum was structurally empty. `s1d_blind_rerate.py` tests
eligibility for the `exploration_or_probe_selection` oversample with `ep["game"] in
SIMPLE_ACTION_GAMES`. With every episode reading `sk48-d8078629`, eligibility was **0 of 25**. The
erratum written specifically to give that stratum a valid definition would have selected nothing, and
reported it as a legitimate zero. After repair: **6 of 25**.

**No reported number was wrong.** The figures quoted during S1 (median 2.1× on the stalled level,
mean 0.4× on cleared levels) come from `logs/kaggle-reference/per_game_analysis.json`, produced by
`analyse_reference_run.py`, which reads `benchmark.json` per game and never had the defect. The
repaired episodes file now independently agrees with it (2.03× vs 2.1×) — that agreement is the
check that the repair is right, not an assumption.

**Repair.** `agent/harness/s1d_repair_gamerun0.py`, dry-run by default, idempotent. The source
directory (`kout`) no longer exists and `logs/kaggle-reference/` holds no `artifacts/`, so the file
cannot be regenerated — but it is exactly recoverable: `episode_id` encodes the true game and level,
and `benchmark.json` holds every game's baselines. Only the four corrupted fields are rewritten;
`actions_taken`, `level`, `analysis_turns` and the evidence packet come from the event stream and are
untouched.

## 2. Request logs pooled across games — HIGH, would have corrupted labelling

`s1d_label.py::load_requests` globbed `run_dir/*requests.jsonl` and bucketed rows by `analysis_step`
alone. The harness writes **one request log per pass** (`<game>_p<N>_requests.jsonl`), so on a 4-game
chunk every `analysis_step` bucket pooled four games' reasoning:

```
analysis_step 3: reasoning from ['bp35-0a0ad940', 'cn04-2fe56bfb', 'lf52-271a04aa']
```

An episode's evidence packet is the **sole** basis for a rater's label, and those labels rank eight
weeks of construction. A rater reading `bp35`'s episode would have been shown three other games'
reasoning interleaved with it. The glob also swept in the run-level `requests.jsonl`, a different
stream. Now scoped to the pass.

No labelled data existed yet, so nothing needs re-rating — the defect was caught before the first pass,
not after.

## 3. `legal_action_reliability` — content-keyed dedup, accepted with its cost stated

Each prompt replays the whole conversation, so every earlier tool result reappears in every later
request; the dedup is necessary. But keying on content means two genuinely distinct calls with
byte-identical results collapse into one, undercounting both sides of the ratio. Measured on the c01
chunk: 20 distinct payloads across 124 occurrences, all 20 recurring — consistent with replay being
the dominant cause, but it does not separate the two. Kept, with the limitation written into the code
rather than left implicit.

Per-game reporting immediately surfaced what pooling had hidden: validity **0.57 / 1.00 / 0.40** across
three games in one chunk. The pooled figure was arithmetically a correct weighted mean (0.74) — the
defect was that it described no game and could not be attributed to one.

## 4. A claimed defect that was not one — recorded so it is not "fixed" again

While inspecting, I asserted that `model` was `None` in every `s1c_*` output because `run_config.json`
nests it under `deployment`. **That was wrong.** `run_config.json` has a working top-level `model` key
and every existing output records it correctly. The error came from reading a key listing I had
truncated to the first eight names alphabetically; `model` sorts past the cutoff, and I inferred
absence from a display limit.

`concurrency` was likewise already correct. `concurrent_jobs` and `effective_concurrent_jobs` agree in
all 18 runs to date. Reading `effective_` first is kept as a guard for the case where the harness clamps
a requested value, not as a correction.

The general lesson is the one this whole inspection keeps producing: **a truncated or filtered view read
as if it were complete.** That is also what produced the concurrency-4 confound below.

## 5. Dead code

`_ACTION_CALL` / `_ACTION_DICT` in `s1c_measure.py` — regexes from the abandoned source-parsing approach
to action accounting, which the docstring already documents as superseded. Removed.

---

## The concurrency-4 confound — a design error, not a code defect

Recorded here because it is the same failure mode as the code above: a conclusion that looked measured
but rested on an untested assumption.

Chunk 1 ran at concurrency 4 and produced ~7 actions/game with 3 timeouts. I attributed that to
concurrency and dropped to concurrency 2. **All four games in that chunk were ACTION6-capable**
(`bp35`, `cn04`, `lf52`, `tn36`). Concurrency and action class changed together, and the result was
assigned to concurrency alone — a violation of the project's own *matched information or nothing* rule,
committed in my own experiment design while I was applying it to the reference docs.

Concurrency 4 has **never** been tested on keyboard-only games. The evidence points the other way:

| | keyboard | ACTION6 |
|---|---:|---:|
| median completion tokens | 264 | 871 |
| actions per generation | ~5 (batched) | ~0.3 |
| `wa30` at concurrency 2 | 201 actions (ref 255) | — |

The six keyboard games (`g50t`, `ls20`, `re86`, `tr87`, `tu93`, `wa30`) are running at concurrency 4 to
settle it by measurement. The conclusion to draw is not "concurrency 4 is fine" but "the earlier
comparison could not support either answer".

---

---

## The finding that outranks all of the above: the local corpus is censored, not failed

Found while smoke-testing the fixes across all 18 run directories. This is not a code defect — the code
reported it faithfully. It is a **data** finding, and it governs whether S1-d can run at all.

The reference harness defines completion explicitly (`inference/tools/eval.py`):

```python
COMPLETED_GAME_RUN_STATES = {"gave_up", "won"}
FINALIZED_SCORING_STATES  = {"gave_up", "won", "cancelled"}
```

Terminal states actually held:

| corpus | episodes | `gave_up` | `playing` | `cancelled` | none |
|---|---:|---:|---:|---:|---:|
| Kaggle reference | 25 | **25** | 0 | 0 | 0 |
| local, all runs | 47 | **0** | 23 | 13 | 11 |

**Every local episode is censored.** `playing` means the run was still going when it was killed;
`cancelled` means the harness cancelled it. The manifest defines a failure episode as one that
*terminated* without advancement or was *abandoned* — a killed run did neither.

Counting them would rank the build order on the operator's kill decisions rather than the agent's
competence, and would load that mass onto `latency_or_budget` specifically, because "ran out of time" is
what an interrupted run looks like. That category would then appear to be the top build priority as a
direct artifact of my 45-minute chunk budget.

The reference corpus is the mirror image: 25/25 completed, so it *is* labelable as failure — but it
carries no reasoning evidence (`--save-request-logs` defaulted off), so three categories cannot be rated
on it. Between the two corpora, the local one has evidence but no valid episodes, and the reference one
has valid episodes but no evidence. **Neither is currently sufficient on its own.**

**What this requires.** A game must reach `gave_up` for its episode to count. The harness bounds a run
at `environment.max_runtime_minutes: 45` with `max_steps: null`, so a game left alone terminates itself
and reaches `gave_up`. The S1-e chunks must therefore be allowed to run to their own budget rather than
harvested at a supervisor deadline. Chunks stopped early yield nothing labelable, whatever they cost in
wall-clock.

Guarded in `s1d_build_corpus.py`: censored episodes are excluded by default and the exclusion is
reported by state, so a corpus can never quietly consist of interrupted runs.

---

## Actions taken, 2026-07-26 evening

**Quarantined 17 run directories and 7 derived artifacts** to `logs/quarantine/` with a manifest giving
a reason per run: 7 under the D10 120-second timeout, 2 with confirmed D13 truncation
(`finish_reason=length`), 3 under a pre-D13 config, 2 conc-4 confounded chunks, 3 empty or killed early.
Moved, not deleted — `logs/` is gitignored, so deletion would be permanent, and this project keeps
negative results with the configuration that produced them. One run survives:
`20260726_195515_s1e-d13c2-c02`, correct config at concurrency 2, 204 actions — but `cancelled`, so
censored and not corpus-eligible under S1-E8.

**`run_resumable.py` treated `cancelled` and `crashed` as finished.** A censored game would have been
retired rather than retried, so a breadth run could report 25/25 complete while holding unusable
episodes for the games that were cancelled. Only `gave_up`/`won` now count as concluded; censored games
return to the queue with a 3-attempt cap, and the supervisor loops until the set concludes instead of
requiring re-invocation. Without this an unattended overnight run could finish looking complete and be
worth nothing.

**S1-e re-scheduled by action class** (`run_s1e_by_action_class.sh`): keyboard 6 games at concurrency 2,
ACTION6 19 games at concurrency 1, keyboard first. ~16.5 h against ~9.75 h uniform; the cost buys
undivided accelerator for the games where truncation and timeouts actually occurred. Concurrency and
action class now covary by construction — acceptable only because concurrency is a throughput setting
that no manifest contrast is defined across, and recorded in the script so a later comparison spanning
the phases cannot make the mistake silently.

**Pre-registered as S1-E8** before any corpus existed: a failure episode must come from a run that
reached `gave_up` or `won`. Filed while the breadth run was still in flight, because an inclusion
criterion chosen after seeing labels is not a pre-registration.

---

## Still open

- **Chunk 1 is contaminated** and must be re-run or excluded before labelling: `bp35`, `cn04`, `lf52`,
  `tn36` at concurrency 4 with 3 timeouts, mean 9 actions, all `cancelled`.
- **S1-E7 is unresolved** — `blind_rerate.sample_size: 30` is unachievable at ≤1 episode/game/pass
  (measured: exactly 25). Needs a decision: reduce the sample, run multiple passes, or accept fewer
  with the power loss stated. **No re-rate sample should be drawn until it is resolved.**
- **The reference run carries no reasoning evidence.** It was launched unmodified, so
  `--save-request-logs` defaulted off: 0/25 episodes support `reasoning_inconsistency`, `goal_unknown`
  or `retrieval_or_context`. `goal_unknown` is an oversampled re-rate stratum. This bounds what the
  reference episodes can be used for regardless of the repair above.

---

## S1-E8 rests on a distinction that does not exist — found 2026-07-26, late

**S1-E8, which I pre-registered this evening, is mechanically wrong.** It admits episodes from runs
reaching `gave_up`/`won` and excludes `cancelled` as censored, on the reasoning that the first means the
agent concluded and the second means something cut it off. That distinction does not survive contact
with the data.

### What the states actually mean

`solver.py::_finish_if_needed` → `game.py::finish_game`:

```python
if self.stop_event.is_set() and run.state == "playing":
    run.state = "cancelled"
...
self.game_run.state = "cancelled" if cancelling else "gave_up"
```

`cancelled` is assigned when a stop/cancel is outstanding *at the moment the game finishes*. Both states
are reached through the **same clean exit path** — both our runs and all 25 reference runs carry
`solver_note='tokens=...'`, which is written only on that path.

### The measurement that settles it

| | budget | wall-clock | early? | state |
|---|---:|---:|---:|---|
| reference, 25 games | 7920 s (132 min) | 7920.8–7921.3 s | **0 of 25** | `gave_up` |
| local `s1e-kb2-c01` | 2700 s (45 min) | 2700.8–2700.9 s | 0 of 2 | `cancelled` |

**No reference game finished early.** All 25 were terminated by their budget, exactly as ours were. The
reference did not "halt rather than thrash" by choice — it ran out of time.

### Why the same event was recorded differently

`request_timeout_seconds()` uses `min(analyzer_timeout, time_remaining)`, so the per-request timeout
shrinks as the deadline approaches. From our own chunk log:

```
analyzer request failed at action 6:  Read timed out. (read timeout=6.852964)
analyzer request failed at action 40: Read timed out. (read timeout=431.437778)
```

Our generations run for minutes, so one is almost always in flight at the deadline; it is killed by the
shrinking timeout and that path sets `stop_event` → `cancelled`. The reference's generations ran in
seconds, so its last request completed inside the shrinking window and the loop exited cleanly via
`runtime_limit_reached()` → `gave_up`.

**The state records generation length, not agent behaviour.** Raising the local budget to 132 minutes
would not change it.

### Consequences

1. **S1-E8 as written makes the local corpus permanently empty.** Not slow to fill — empty, at any
   budget. The stopped run would have spent **49.5 h** across `MAX_ATTEMPTS=3` retries without producing
   one admissible episode.
2. **H4 is refuted in its stated form.** "The reference halts rather than thrashes" was read off
   `gave_up` plus a median ~2× human budget. The reference did not halt; it was cut off. The efficiency
   ratio stands; the halting claim does not.
3. **`--max-actions` is not plumbed.** `run_local.sh` never forwards `environment.max_steps`, so
   `max_actions_per_game=None` and wall-clock was the only stop condition available. Same omission class
   as the `--analyzer-timeout` bug: the launcher reproduces the Makefile's config→CLI translation
   incompletely.

### The rule that would be defensible

Admissibility should turn on **whether the termination was uniform and pre-registered**, not on which
label the harness happened to record:

- **admissible** — terminated by a fixed budget applied identically to every game, whatever the recorded
  state. Episodes are then *right-censored at a known, uniform bound*, which is a stated experimental
  condition and is comparable across games.
- **inadmissible** — terminated by an ad-hoc operator action (my mid-chunk `pkill`s), which is
  non-uniform and correlates with nothing but my attention.

This preserves S1-E8's actual intent — keep the operator's decisions out of the build-order ranking —
while dropping a mechanism that does not distinguish what it claimed to. It must also be recorded that
`latency_or_budget` frequency is then partly a property of the budget, and every reported episode must
carry the bound it was censored at.

**Not applied.** Amending a pre-registration is the operator's call, not mine.
