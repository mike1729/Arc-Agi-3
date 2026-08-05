# Miner v3 candidate — the conjunction tier (two-guard rules)

**2026-08-05. Task note for agent execution. Zero model calls, 3–5 h.** Pure mechanism,
vocab-v2-style acceptance. Surfaced by external review; adopted because it attacks the
**dominant measured failure bucket**, not because the review said so.

## What and why

The miner's tier-1 rules are `action key [+ ONE guard] → effect`. A mechanic needing a
conjunction (`feature1 = a ∧ feature2 = b`) is inexpressible — the key stays unresolved
no matter how much evidence arrives. The measured failure splits say this is where the
losses are: `guard_fixable` is the largest bucket on most games (e.g. ls20 human-L1 341
guard-fixable vs 0 census-separable vs 146 unpredicted; sp80 human-L2 174/0/0), and by
construction anything single-guard-separable was already found — the exhaustive tier-1
search saw every single guard. What remains guard-shaped is conjunction-shaped (or
worse). One trace-level corroboration, for color only: the model's dc22 full-dose think
attributed its unresolved keys to needing *combinations* of adjacency features.

**This is a mechanical question with a mechanical answer.** No model anywhere.

## Design

- **New module `agent/harness/e0_conjunction.py`** — do NOT edit `rs_e0.py`
  (hot shared file, multiple live agents; folding in happens only on acceptance, later,
  coordinated). Wrapper mines on top of `rs_e0` primitives.
- **Tier-1.5**: for each key left unresolved by tier-1, search guard **pairs**
  `(f1=v1) ∧ (f2=v2)` over the v2 vocabulary, zero-contradiction on the store, support
  ≥ 1 (report the support distribution; no invented minimum). Pair count per key is
  bounded (features × small value sets, squared) — if a cap is needed, set it, label it
  (w), and report when it binds.
- **Merged scoring**: tier-1 rules + tier-1.5 rules + majority fallback, same
  arbitration order (specific before majority). Score with the standard machinery.
- **Overfit is self-controlled by the protocol**: acceptance is scored on **held-out
  human replays** (external test set) — conjunctions that fit explorer noise lower
  held-out accuracy and reject themselves. Additionally report rule-count inflation and
  per-tier firing shares, so a win isn't a thicket.

## Acceptance (exactly the vocab-v2 pattern)

Rerun the E0-style scoring and the `e2_dose` grid (both targets, both modes, dose
endpoints, all 24 games) with tier-1.5 on vs off. **Measured deltas decide**: adopt if
held-out accuracy improves where `guard_fixable` dominates and regresses nowhere
materially; reject otherwise. Either way, append the full per-game table here.

If adopted: floors of record move v2 → v3 by dated addendum in `notes/e2-dose.md` (the
established pattern), and `unresolved key` changes meaning everywhere downstream —
digests, channel C targeting, X-phase confidence classes.

## Deliberate non-coupling with the slice-2 night

**The night runs on v2 floors regardless of this task's outcome** — comparability with
slices 1/1.1 is worth more than a fresher floor, and the digest generator reads the
default miner, which this task does not touch. If tier-1.5 is accepted, it applies from
slice 3 / X-phase onward with the floor-version stated on every number (the v1→v2
precedent already handles mixed-floor reporting).

## Interactions, stated

- `notes/e2-regrade.md` arm C (tolerance tier) is a *different* mechanism (one guard,
  few contradictions) than this (two guards, zero contradictions). Run independently;
  if both win, the combination (two guards + tolerance) is a follow-up, not smuggled
  into either task.
- X-phase: a larger `confident` class directly grows the plannable graph (X1 measured
  mean confident coverage 0.195 with 15 games at zero — much of that zero is exactly
  the all-keys-unresolved case this attacks). Report the would-be confident-coverage
  change per game as part of the acceptance table.

## Cautions

- Concurrent agents: new files only (`e0_conjunction.py`, `logs/e0_conjunction.json`);
  `git status` before committing; stage only this task's files.
- No invented thresholds; support distributions and caps reported, not tuned.
- Wall-clock: pair search is combinatorial — measure and report mining time per game;
  if any game exceeds minutes, cap and report rather than silently subsample.

## Estimate

3–5 h agent time; compute minutes-to-tens-of-minutes (pair search on 24 stores).
