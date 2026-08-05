# Slice-2 build bundle — DSL, prior library, latent verifier, digest v3

**2026-08-05. Task note for agent execution. Zero model calls — build and verify only;
running slice 2 is NOT this task.** One agent owns all four sub-tasks: they share the
DSL and two of them touch `e2_slice.py`-adjacent code, so single ownership serializes
the file access that burned a night agent once already. The governing spec is
**`notes/e2-slice2.md`** (as amended same day, `cd924b3`) — read it first; this note is
the implementation order and acceptance checks.

**Build order: 1 → 2 → 3 → 4.** The DSL comes first because the other three consume it.

## 1. The expression DSL (`agent/harness/e2_dsl.py`, new)

One small module, two grammars, both with parse-or-reject semantics:

- **Predicates** (channel A + the prior library): over census handles and the object
  catalogue. Define the *minimal* grammar that covers (a) everything the row-C goal
  grammar expresses and (b) the five prior shapes — count comparisons, co-location,
  colour/shape matching between object sets, "all X satisfy R(Y)". That alignment is
  load-bearing: the control and the channel must share expressiveness, or the
  comparison is rigged in either direction.
- **Counter expressions** (channel B): base ∈ {`actions_since_reset`, `actions_total`,
  per-action-id counts}, transform ∈ {identity, `mod k` (k ≤ 8), `≥ n` threshold},
  explicit RESET convention flag. Nothing else — the grammar being small is the point;
  the hidden-state task showed one prose sentence hides four operational readings.

**Extraction-side prose rejection is part of this module:** a proposal that does not
parse is recorded `prose_rejected` (a scored category, like slice 1's parse-rejected —
kept, counted, never silently repaired).

**Acceptance:** evaluator agrees with `rs_completion` on every row-C-expressible
predicate (property-test over the existing universes); counter DSL reproduces
`c2_episode` / `c1_global` / the mod arms byte-for-byte against
`logs/e2_hidden_state.json` inputs.

## 2. Prior-library control (`agent/harness/e2_prior_library.py`, new)

The five stock shapes from the corrected S1 read (`aca2d47`): avatar→salient target ·
every X into/onto its Y · clear/collect all X · copy the displayed template · align the
two matching objects. Instantiate each **mechanically from the census alone** — for
each shape, enumerate its concrete bindings (each movable class × each salient static,
each colour class for clear-all, …), expressed **in the task-1 DSL** so scoring is
symmetric with channel A. A shape with no valid binding on a game yields none —
recorded, not padded.

Then filter by store consistency (same check channel A scoring uses: consistent with
every store transition; own completion positive where one exists — sp80 and lf52 have
one).

**Methodological hard rule: the library is built blind.** Census + store only; no game
source is read during this sub-task. Source adjudication of the library (and of channel
A) happens at slice-2 scoring time, not at build time.

**Output:** `logs/e2_prior_library.json` — per game (all 8 slice-2 games), per shape:
bindings before/after the consistency filter, each as a DSL string. Acceptance: runs on
all 8, counts reported, spot-render 3 games' surviving candidates for sanity.

## 3. Latent verifier, spec-driven (`agent/harness/e2_latent_verify.py`, new)

A driver that takes a spec file of task-1 counter expressions and runs each through the
existing hidden-state machinery: injection as a guard feature, half A (aliasing
separation where the census has volume), half B (mining vs the v2 floor, both targets,
both modes, dose 125 + full, ceiling arm), against 5 seeded random controls (seeds 1–5,
**never 20260804**).

**Import `e2_hidden_state.py`; do not edit it** — its author is still landing
follow-ups (cn04, sc25). If an internal is unreachable by import, the minimal refactor
needs a `git status` check and a same-day coordination note in the commit message, not
a silent edit.

**Acceptance:** a spec file containing `c2_episode` for m0r0 reproduces the committed
verdict numbers from `logs/e2_hidden_state.json` exactly.

## 4. Digest v3 + request schemas (edits `agent/harness/e2_slice.py`)

Keep everything slice 1.1 and the cap-lift added (complete value sets, witness, guard
grammar, declared truncations, honest majority text). **Remove** the rule-proposal
request, `support_claim`/`refuter`-for-rules, and `next_probe` — those channels are
dead by measurement. **Add**, per the slice-2 note:

1. **Coverage ledger** — per object (colour/shape class): which actions have been
   tried on it and how often, with explicit `never tried` marks; per unresolved key:
   stratum counts. Compact rendering is the implementer's choice; the never-tried marks
   are not.
2. **Inert-object inventory** — objects appearing in no effect signature anywhere in
   the store (never moved, recolored, appeared, disappeared), with colour/shape/
   position. Channel A's primary seed.
3. **Negative-evidence section** — null-effect runs as counts (data only, no
   elicitation claim), and **satisfied-but-not-advanced lines**: evaluate the row-C
   survivors against the store (the `e2_dose.goal_curve` machinery pattern) and render
   "candidate ⟨paraphrase⟩ satisfied at step t — level did not advance". These feed the
   contradiction-respect readout.
3b. **Observed invariants** (added 2026-08-05 after external review — see the slice-2
   note's digest item 5): joint constraints among count features holding in every stored
   state (constant sums / differences / complements; mine mechanically, seconds). One
   compact digest line per invariant.
   ⚠ **Also check `notes/e2-regrade.md`'s result before implementing this sub-task**:
   the preamble's "remove the rule-proposal request" is conditional on it — if the
   re-grade moved floors, keep a rule request with repair-bar wording per the slice-2
   note's channel D conditional; if it hasn't run yet when you get here, the default
   (removed) stands and a positive result becomes an addendum later.
4. **Three request schemas** in PROMPT and EXTRACT, exactly as the slice-2 note
   specifies: channel A `{predicate, refuter, test_action}` (test_action =
   precondition + action id + click-target rule, guard vocabulary); channel B ≤ 3
   latents `{name, definition}` in the counter DSL, grammar printed in the prompt;
   channel C ≤ 2 vocabulary proposals `{name, computable definition sketch, targeted
   keys, expected direction}`. Extraction validates A and B through task 1;
   non-parsing → `prose_rejected`.

Instrument rules unchanged and non-negotiable: two-phase decode, first token never
constrained, `THINK_BUDGET = 16384`.

**Acceptance:** all 8 slice-2 games' digests render (both the six + sp80, lf52, full
dose); char counts reported per game **against the current lengths** (dc22/full is
28,742 today — if v3 growth is large, say so; a budget re-probe is a named follow-up,
not this task); `--help` runs; no model calls.

## Cautions

- Concurrent agents: `git status` before every commit; stage only files this bundle
  owns; **one commit per sub-task** with the sub-task number in the message, so a
  mid-bundle interruption leaves main coherent.
- Competition source under `data/` is never quoted into committed artifacts
  (PUBLISHING.md; labels/paraphrases only). Sub-task 2 does not read it at all.
- No invented numbers; working choices labelled (w).
- Store and floors are frozen inputs (`logs/e1_store_v2/`, `logs/e2_dose_vocab_v2.json`).

## Non-goals

Running slice 2 (needs the GPU night and the operator's go) · any model call · touching
`e2_hidden_state.py`, `e1_explorer.py`, `rs_*` · prefix repair (separate task, in
flight) · X-phase work (separate task, in flight).

## Done means

All four acceptance checks pass, four commits on main, and `notes/e2-slice2.md`'s
protocol is runnable as written — the operator can schedule the night with no further
build work.

## Estimate

10–14 h agent time across the four sub-tasks (DSL 2–3 h · library 3–4 h · verifier
2–3 h · digest 4–5 h incl. renders); compute negligible throughout.
