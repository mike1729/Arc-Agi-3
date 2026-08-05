# E2 probe channel — execute Qwen's probes, measure their information value

**2026-08-05. Task note for agent execution. Zero model calls** — this scores outputs Qwen
already produced; no GPU, no instrument rules, runs in daytime alongside anything.

## What and why

Both slices judged the probe channel the strongest output in the run (slice 1.1: 21/24
discriminating; consistent with slice 1) and neither scored it. This task turns the judged
channel into a measured one. Two questions, in order of importance:

1. **Does executing the model's probe resolve the unresolved key it targets — and does it
   beat random probing at equal action cost?** (The causal question. Without the control,
   "probe resolved the key" may just be "any new evidence resolves the key.")
2. **Can NL probes be executed mechanically at all** — how often are they translatable,
   reachable, already answered by evidence the model was holding? (The feasibility read
   that decides whether an X-phase directive executor is worth building.)

## Inputs

- **Probes**: `cells[].next_probe` in `logs/e2_slice.json` (slice 1, seed 20260804),
  `logs/e2_slice_seed1.json`, `logs/e2_slice_seed2.json` — 36 cells across the six
  iteration games × 2 doses. Traces in `logs/e2_slice_traces/` for context only.
- **Store**: `logs/e1_store_v2/` — **frozen, never mutate.** Replay support is built in:
  each game's `graph.json` has `prefix`, mapping every state hash → the action list that
  reaches it from reset (verified: tu93 1202/1202 states covered). Transition rows carry
  `step`/`route_mode`/`tier`.
- **Games**: same interface `e1_explorer.py` uses — reuse its game-loading and `test()`
  machinery by import, do not duplicate. REPLAY-DET licenses replay-and-deviate.
- **Miner**: `rs_e0` (`mine`/`score`), `rs_transitions` (`guard_features`, `set_vocab`).
  **Primary scoring under v1 vocabulary** (`set_vocab("v1")`) — the probes were designed
  from v1 digests and target v1 unresolved keys. Also report per-game accuracy deltas
  under v2 (the floor of record); both runs cost seconds.
- ⚠ `e2_probe.py` is the UNRELATED thinking-instrument gate. Do not touch it. New code:
  `agent/harness/e2_probe_channel.py`. Outputs: `logs/e2_probe_specs.json` (committed,
  see step 1), `logs/e2_probe_channel.json` (committed), probe transitions under
  `logs/e2_probe_channel_store/` (local-only — confirm with `git check-ignore` before
  assuming).

## Step 1 — collect and formalize (pre-register before executing anything)

Extract all 36 probes verbatim. Classify at the NL level:

- **executable-as-stated** — names a precondition and an action in (or resolvable to) the
  guard vocabulary;
- **out-of-band** — requests instrumentation, logging, or anything that is not a game
  action (slice 1.1 had 3);
- **untranslatable** — executing it would require the translator to invent content. Name
  the minimal missing piece.

For each executable probe write a formal spec: `{probe_id, source (game/dose/seed),
verbatim_text, precondition (feature=value conjunction in guard vocabulary), action
(id; for A6 the click-target rule as written, e.g. "any cell of colour 8" — resolving a
colour to cells via the census is reading, not inventing), predicted_contrast (what
outcomes distinguish what), targeted_key (if identifiable from the cell's digest)}`.

**The translator adds nothing.** Translate what is written; ambiguity → untranslatable.
Dedupe identical specs across seeds, keeping multiplicity (cross-seed agreement is itself
a stability datum). **Commit `logs/e2_probe_specs.json` before running any probe** — that
commit is the pre-registration; lean mode, no manifest entry.

## Step 2 — determinism gate before any probe

For each of the 6 games: replay 3 stored prefixes end-to-end and confirm the reached grid
matches the store's state for that hash. Any mismatch → stop on that game, report it, do
not execute probes there. Always reach states by **full prefix replay** — never treat two
states with equal hash as interchangeable (m0r0 aliases: the latent parity is fixed by the
prefix, not the hash).

## Step 3 — execute

Per spec, evaluate the precondition mechanically over stored grids to find satisfying
(state, prefix) pairs. Then:

- **No satisfying state in the store** → category `unreachable-in-store`. Report; do not
  go exploring for one (bounded task).
- **Check the FULL store first for the requested contrast** (both arms + action present) →
  category `already-answered`: score the predicted contrast on stored evidence, no
  execution. For dose-125 probes this also measures "the model asked for evidence the
  explorer later collected anyway" — count it.
- **Else execute** the missing arm(s): replay prefix, apply action, record. Cap ≤ 8
  executed transitions per spec (w); log when the cap binds. Record into
  `logs/e2_probe_channel_store/` tagged with `probe_id` — never into `e1_store_v2`.

## Step 4 — score (all mechanical)

Per executed (or already-answered) probe:
- **discriminated**: did outcomes differ across arms as predicted — realized / partial /
  not?
- **targeted-key resolution**: re-mine store + this probe's transitions (v1): does the
  targeted key go unresolved → resolved with a surviving rule, and at what support? Plus
  per-key accuracy delta on human L1/L2 (same scoring as `e2_dose`).

Per game: union of all executed probe transitions + store → re-mine → human-L1/L2
accuracy vs the floor (v1 primary, v2 reported).

**Random control — the load-bearing contrast.** For each executed probe: same number of
transitions obtained by replaying to a uniformly-random stored state and applying an
untried tier-1 candidate there (untried = that (state, action) absent from the store;
reuse `e1_explorer`'s tier-1 candidate machinery by import). 5 replicates, seeds 1–5
(**never 20260804**). Compare targeted-key resolution rate and accuracy deltas: model
probe vs the control distribution, per probe and pooled.

## Report (append a results section to this note)

1. Funnel: 36 → NL classes → specs → unreachable / already-answered / executed, per
   slice and seed.
2. Determinism gate per game.
3. Discrimination: fraction realized as predicted.
4. Targeted keys: resolved fraction with supports — vs the control's resolved fraction.
5. Per-game accuracy deltas (v1 and v2), probes-union vs floor, vs control distribution.
6. Cost: total probe transitions vs store sizes.
7. One verdict sentence: **does the channel, executed mechanically, deliver information
   the explorer's own policy did not — and does it beat random deviation at equal cost?**

## Cautions

- Competition source under `data/` must never be quoted into committed artifacts
  (PUBLISHING.md; git history counts). Games by label only.
- No invented thresholds — the ≤8 cap and 5 replicates are working choices, labelled (w);
  everything else is a measured number.
- Concurrent agents share the tree: `git status` before committing, stage only files this
  task created, never touch other agents' uncommitted files.
- Do not modify `e1_explorer.py`, `e2_slice.py`, `e2_probe.py`, or the store. New files
  plus this note's results section only.

## Non-goals

No Qwen calls. No new digests. No exploration beyond the capped probe deviations. No
X-phase executor design and no slice-2 decisions — this measures whether those are worth
building, it does not build them.

## Estimate

4–6 h agent time; compute negligible (game steps are milliseconds, each re-mine seconds;
~30 specs × (1 + 5 controls) re-mines ≈ minutes). No GPU — the night slot stays free.

---

# Results — 2026-08-05

Executed as specified. Zero model calls. Specs pre-registered in `55f8286`
(`logs/e2_probe_specs.json`) before any probe ran; measurements in
`logs/e2_probe_channel.json`; harness `agent/harness/e2_probe_channel.py`.

**Headline: the channel could not be measured, because it could barely be executed.
One probe of 36 reached the engine.** It changed nothing, and neither did its random
control — so the load-bearing contrast is 0 vs 0 and settles nothing. The run's real
product is elsewhere: **the E1 v2 store's `prefix` map is unsound on two of six games**,
and **the probes overwhelmingly ask for evidence the explorer already had**.

## 1. Funnel

36 probes = 6 games × 2 doses × 3 seeds (s0 = 20260804, s1/s2 = the slice-1.1 reruns).

| Stage | n | |
|---|---:|---|
| probes collected | 36 | |
| — out-of-band | 2 | ask for logging, not a game action |
| — untranslatable | 3 | minimal missing piece named per probe |
| — **executable-as-stated** | **31** | formal specs written |
| of the 31: blocked by the determinism gate | 9 | dc22 ×3, m0r0 ×6 |
| of the 31: unreachable-in-store | 8 | no state satisfies the precondition |
| of the 31: already-answered | 11 | the store already ran the probe |
| of the 31: mixed (one arm each way) | 2 | |
| of the 31: **executed** | **1** | tu93_125_s0, 8 transitions |

Per seed the classes are near-identical (s0: 1 executed, 2 already-answered, 2 mixed,
2 unreachable, 2 blocked, 1 out-of-band, 1 untranslatable · s1: 4 already-answered,
2 unreachable, 3 blocked, 1 out-of-band, 2 untranslatable · s2: 5 already-answered,
4 unreachable, 3 blocked). No seed produces a materially more executable probe than
another; the slice-1.1 display repair did not change executability either.

The three untranslatable probes fail for the same kind of reason — a named condition with
no named action: dc22_125_s1 requests "ACTION6 validity" without a click target;
tu93_full_s1 says "in the click direction" without a click; ls20_full_s0 asks to *place*
objects at coordinates, a primitive the action set does not have. Both out-of-band probes
ask the harness to log; one of them (ls20_full_s1) asks for `target_cell_colour`, which is
`click_colour` — already in the v1 vocabulary and already in the digest it was written
from.

## 2. Determinism gate — the run's most consequential number

Three stored prefixes per game (shortest / median / longest), replayed end-to-end from
RESET, grid compared to the store's state for that hash.

| Game | Gate | First divergence |
|---|---|---|
| ft09 | 3/3 | — |
| ls20 | 3/3 | — |
| tu93 | 3/3 | — |
| vc33 | 3/3 | — |
| **dc22** | **1/3** | step 3, `ACTION6(4,32)` from `3f85bfda`: store edge → `8c0df9a2`, replay → `3f85bfda` (no change) |
| **m0r0** | **0/3** | step 0, `ACTION1` from the origin: store edge → `a6bba1fd`, replay → `b79fe5d1` |

Replay is **self-consistent**: three independent replays of each failing prefix give
byte-identical results every time. The engine is deterministic. What is not sound is the
store's `prefix` map — E1 composes it from edges observed at different moments
(`prefix[new] = prefix[source] + [action]`), and on a game whose settled frame does not
identify the latent state, a composed path is not a walked path.

Both divergent edges were observed **exactly once** by the explorer and never re-tested.
m0r0 at least records `(origin, ACTION1)` in its `conflicted` list. **dc22's `conflicted`
list is empty** — its alias is entirely unrecorded, and the E2 digest dc22 was synthesized
from therefore printed "ALIAS CONFLICTS: none recorded", which is false in substance. Two
of the six iteration games cannot be branch-and-deviate probed from the store as it
stands.

This is a limit on REPLAY-DET as the line uses it. REPLAY-DET holds for *re-executing a
walked action sequence*; it does not hold for *reaching a stored state by its recorded
prefix*, and `notes/l1-evidence-first.md`'s licence for branch-and-deviate rests on the
second reading. The store's own verification ("tu93 1202/1202 states covered") checked
coverage of the prefix map, not its correctness.

Per the note, no probe was executed on dc22 or m0r0. Classification that needs only store
lookups (already-answered, unreachable) was still performed there, since it costs no game
action; that is why dc22 shows 3 blocked rather than 6.

## 3. Discrimination

Only 4 of 36 probes state a differential prediction that could be evaluated at all
(the rest are `single_outcome`, or lost an arm to unreachability/one-stratum collapse):

| Probe | Basis | Verdict |
|---|---|---|
| tu93_125_s0 | executed | **partial** — ACTION1 arms give one effect, ACTION4 arms give two |
| tu93_125_s1 | stored | **partial** |
| ls20_full_s2 | stored | **partial** |
| vc33_125_s0 | stored | **not** — both arms produce identical effect sets |

**Realized as predicted: 0 of 4.** Six further probes are `not-evaluable` for a reason
worth naming: the variation they ask for does not exist. Four of them say "systematically
vary X" and X takes exactly **one** value across every state satisfying the precondition
(`tu93_full_s2` count:0, `vc33_125_s1` adj:0:right, `vc33_125_s2` the colour-0 horizontal
gap, `vc33_full_s2` colour-0-touches-4). Two lose one of two arms to unreachability.

ft09 is the sharpest case of unreachability being *structural*: three probes (ft09_full_s1,
ft09_125_s2, ft09_full_s2) all request count:8 and count:9 in combinations that never
co-occur, because count:8 + count:9 = 36 in every stored ft09 state. ft09_full_s2 was
explicitly written to break that conjunction; the conjunction is an identity.

## 4. Targeted keys — and the control

One probe executed, so one comparison exists. tu93_125_s0, 8 transitions, targeting the
unresolved keys `ACTION1` and `ACTION4`.

| | key A1 | key A4 | human L1 | human L2 |
|---|---|---|---|---|
| floor (store alone) | unresolved (majority, support 338) | unresolved (majority, 316) | 0.7296 | 0.5768 |
| store + probe | unresolved (majority, 340) | unresolved (majority, 316) | 0.7296 | 0.5768 |
| store + control, seeds 1–5 | unresolved in 5/5 | unresolved in 5/5 | 0.7296 ×5 | 0.5768 ×5 |

**Resolved fraction: probe 0/2, control 0/2 in every replicate.** Accuracy deltas are
exactly zero on both sides, to four decimals, at v1 and at v2. Eight transitions against a
2,573-transition store move nothing — which is the expected result at this dose and is why
the contrast is uninformative rather than negative for the model.

## 5. Per-game accuracy, v1 primary / v2 reported

Probes-union vs floor. Only tu93 has any probe transitions.

| Game | store | probe | v1 L1 | v1 L2 | v2 L1 | v2 L2 |
|---|---:|---:|---|---|---|---|
| dc22 | 2939 | 0 | 0.2278 → 0.2278 | 0.0552 → 0.0552 | 0.2278 → 0.2278 | 0.0552 → 0.0552 |
| ft09 | 1231 | 0 | 0.2522 → 0.2522 | 0.0885 → 0.0885 | 0.3017 → 0.3017 | 0.0885 → 0.0885 |
| ls20 | 2877 | 0 | 0.4396 → 0.4396 | 0.3466 → 0.3466 | 0.4396 → 0.4396 | 0.3466 → 0.3466 |
| m0r0 | 2943 | 0 | 0.2624 → 0.2624 | 0.3988 → 0.3988 | 0.2624 → 0.2624 | 0.3988 → 0.3988 |
| tu93 | 2573 | 8 | 0.7296 → 0.7296 | 0.5768 → 0.5768 | 0.7296 → 0.7296 | 0.5768 → 0.5768 |
| vc33 | 800 | 0 | 0.4891 → 0.4891 | 0.2367 → 0.2367 | 0.4891 → 0.4891 | 0.2367 → 0.2367 |

Every delta is zero. The v1/v2 gap is the vocabulary's, not the probes' — v2's only
non-zero effect anywhere is ft09's L1 floor (0.2522 → 0.3017), consistent with
`notes/miner-vocab-v2-results.md`.

## 6. Already-answered — the answer to question 2

26 arms across 11 probes were already answered by the store. Split by whether the answer
was inside the **dose window the model was actually shown**:

* dose-125 probes: 16 already-answered arms, **14 had ≥1 matching transition inside the
  first 125 store transitions** — the model asked for evidence it was holding while it
  wrote the probe. The two exceptions are ls20_125_s1 and one arm of vc33_125_s0.
* full-dose probes: 10 already-answered arms, all 10 answered by definition; supports run
  from 1 to 476 transitions.

Support counts are often large (tu93_125_s1's nine arms are backed by 9–340 stored
transitions each; ls20_full_s2's five strata by 1–196). This is not a near-miss: the
probes name conditions the explorer's own undirected policy had already exercised dozens
to hundreds of times.

## 7. Cost

8 executed probe transitions against 13,363 store transitions across the six games
(0.06%; 0.31% of tu93 alone). Control: 5 replicates × 8 = 40 transitions. Total game
actions spent, including all prefix replays and the determinism gate: minutes of
wall-clock, no GPU. The cap of ≤8 transitions per spec never bound — nothing came close.

## 8. Verdict

**No.** Executed mechanically, the probe channel delivered no information the explorer's
own policy had not already delivered: 26 of the 31 executable probes' arms were already in
the store (14 of 16 dose-125 arms inside the model's own context window), 8 named states
the game cannot reach, and the single probe that ran moved neither key resolution nor
accuracy — exactly like its random control, so the comparison at equal cost is 0 vs 0 and
decides nothing.

The judged quality of this channel (slice 1.1: 21/24 discriminating) does not survive
execution. What the probes are good at is *naming a plausible unresolved condition in the
vocabulary*; what they are not good at is naming one that is **new** (already-answered),
**reachable** (unreachable-in-store), or **variable** (one-stratum collapse). An X-phase
directive executor built on this channel would spend its budget re-collecting evidence the
explorer already has. Before any such executor is worth building, the model needs to be
told what the store already contains — the digest currently shows mined rules and
unresolved keys, never coverage — and the probe request needs a mechanical
already-answered check in the loop rather than after it.

## 9. Deviations from the task note

1. **`MAX_STATES_PER_ARM = 12` (pre-registered) was not applied to planning.** As written
   it capped how many satisfying states were scanned for a click target, which produced a
   spurious `unreachable-in-store` on ft09_125_s0's first pass. The scan is unbounded in
   the run of record; the constant survives only inside `_match_adj`. This loosens the
   procedure in the probes' favour and is recorded rather than re-registered.
2. **Gate-failed games were still classified, never executed.** The note says stop on a
   gate failure; store-lookup classification costs no game action and is reported for
   dc22/m0r0 so the funnel is complete.
3. **`answered_at_dose` was added after the specs were committed** — the dose-window split
   in §6. It is a read of the frozen store, not a change to any spec.

## 10. What this hands the next step

* **The store defect is the priority, not the probe channel.** dc22 and m0r0 need their
  `prefix` maps re-derived by *verified* replay (walk the path, keep it only if it lands
  where it claims) before any branch-and-deviate work touches them, and the same check
  should run over all 24 games — the two failures here were found by three samples each.
  Until then, "REPLAY-DET licenses branch-and-deviate" is true only for prefixes that have
  been individually verified.
* **The digest is missing a coverage channel.** Every already-answered probe is a request
  the model would not have made if it could see what the store already covers.
* **No slice-2 or X-phase decision is taken here**, per the note's non-goals.
