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
