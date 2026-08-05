# E3 follow-up — grounded-delta feasibility: is a cell-level forward model learnable?

**2026-08-05. Task note for agent execution. Zero model calls, 4–6 h.** The X1 gate
failed: the position-free effect grammar pins the next state on 0 of 35,568
board-changing edges, so no planner can step. The proposed fix is a second, grounded
layer — but *"whether the delta can be predicted at all is an open question this stage
did not ask"* (`notes/e3-executor.md` results). This task asks it, with three
measurements of increasing strength. It decides whether the executor line continues,
and in what form.

## Inputs

Store `logs/e1_store_v2/` (all 24 games; loader = `e2_dose.load_store` pattern —
completion rows lack post frames, skip them here). Human replays via
`rs_transitions.load_game` as the held-out set for step 3. Known latents for the
augmentation arm: in-episode action count (m0r0, g50t, cn04 — from the hidden-state
results; join via the rerun logs or `step` field per that task's method).

## Step 1 — grounded determinism

For repeated `(pre_grid, action)` observations (use the rerun census, which includes
routing actions — the store alone has no repeats): fraction with **identical post
grids**. Report per game; expect failures exactly on the counter games — run the
**latent-augmentation arm** there: determinism of `(pre_grid, action, in-episode
count)`. This bounds what any grounded model can achieve and quantifies how much the
known latents buy at the grounded level (they bought nothing at the signature level —
half B — so this is their second chance to matter).

## Step 2 — locality radius (the load-bearing measurement)

For every changed cell in every transition: the smallest radius r such that the
(2r+1)² pre-grid patch around it, plus the action (and click position relative to the
cell, for ACTION6), **determines the cell's change** across the whole store — group by
(patch hash, action, relative click), flag groups with divergent outcomes, increase r
until convergence or a cap (r ≤ 8, (w); report when the cap binds). Also the converse:
unchanged cells whose patch matches a changed cell's patch (false-positive pressure).

Report per game: the r distribution, the fraction of changes determined at r ≤ 2 /
≤ 4 / ≤ 8 / never, and the same **per event kind** (`reshape` / `appear` /
`assignment` / `move` — the kinds that blocked X1, 31,988 / 18,387 / 12,475 edges).
Small r dominating → cellular-automaton-style local rules are learnable and the
grounded layer is a mining problem. r unbounded on the mass of edges → the dynamics
are global (gravity columns, counters, whole-board maps) and the grounded layer needs
structured mechanisms, not patches — a different, harder build.

## Step 3 — patch-rule generalization (the feasibility number)

At the measured dominant radius: mine patch→delta rules on a train split of each
store, score **exact grounded next-state accuracy** on (a) the held-out store split
and (b) human replays — the external test. Report alongside a **memorizer floor**
(exact (pre,action) lookup) per the house convention. This number — grounded held-out
accuracy vs its floor — is what the X-phase redesign consumes.

## Report (append here)

1. Determinism table (with and without latent augmentation).
2. Locality distributions per game and per event kind.
3. Grounded held-out accuracy vs memorizer floor, store and human.
4. Verdict, two sentences: is a grounded layer learnable from this store, and is it a
   patch-mining problem or a structured-mechanism problem? Feeds the X-phase redesign
   directly.

## Cautions

- Compute: patch hashing over ~50k transitions × changed cells is fine; report timing;
  cap radii, not games.
- Concurrent agents: new files only (`agent/harness/e3_grounded.py`,
  `logs/e3_grounded.json`); no edits to shared harness files; `git status` before
  commits, stage only own files.
- No invented thresholds — the r cap and split fractions are (w) and reported.
- Everything here is model-free and survives the Qwen 3.8 transition untouched.
