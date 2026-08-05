# Miner v3 candidate — the conjunction tier (two-guard rules)

> **Executed 2026-08-05 — REJECTED. See [Results](#results--2026-08-05-rejected) at the
> bottom; the design below is what was built and measured, unamended.**

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

---

# Results — 2026-08-05. **REJECTED.**

Zero model calls. Code `agent/harness/e0_conjunction.py` (new; `rs_e0.py` untouched).
Data `logs/e0_conjunction.json`. 24 games × 2 modes × {E0 human-replay splits, e2_dose
endpoints} × tier-1.5 {off, on}. Wall clock 307 s, 8 jobs; **max mining time per game/cell
0.231 s** — the combinatorics were never the constraint and **neither cap ever bound**
(`caps_bound: []`).

## Verdict

| claim | measured |
|---|---|
| **held-out accuracy improves where `guard_fixable` dominates** | **FALSE.** Pearson(off-arm `guard_fixable` share, L1→L2 accuracy delta) = **−0.021**, n=24. The five games with a 100% fixable share span −0.3205 to +0.0345 |
| **regresses nowhere materially** | **FALSE.** sp80 L1→L2 **0.6350 → 0.3145**; sp80 explorer-store on-human-L2 **0.6924 → 0.0495**; m0r0 L1→L2 0.3514 → 0.1173; tu93 dose-125 on-human-L2 0.5431 → 0.3333 |

Adoption required both. **Not adopted; no floor moves, `unresolved key` keeps its meaning
everywhere downstream, and `notes/e2-dose.md` is not amended.** The v2 floors stand as the
floors of record. The deliberate non-coupling with the slice-2 night therefore costs nothing.

## What it actually is: a within-distribution memorizer

The mechanism works — and works only inside the distribution it was mined on. Medians over
24 games, mode `full`:

| target | off → on | W/T/L | tier-1.5 firing share | tier-1.5 acc | rule it displaced (majority) acc |
|---|---|---|---|---|---|
| E0 within-L1 (held-out sessions) | 0.3266 → **0.3686** (+0.0450) | **20/1/3** | 0.201 | **0.579** | — |
| explorer store → human **L1** | 0.3084 → **0.3655** (+0.0179) | **17/5/2** | 0.219 | **0.600** | 0.249 |
| E0 **L1→L2** | 0.1638 → 0.1550 (**0.0000**) | 9/8/7 | 0.227 | **0.033** | 0.076 |
| explorer store → human **L2** | 0.1290 → 0.1262 (**0.0000**) | 8/10/6 | 0.131 | **0.129** | 0.146 |

`moveset` behaves the same: within-L1 +0.0506 (19/2/3), L1→L2 median delta 0.0000 (9/6/9),
store→human-L2 0.0000 (8/9/7).

**Coverage is identical in every cell** (median delta 0.0000, 24/24 ties, both splits): tier
1.5 never adds a covered transition, it only takes edges away from the majority rule. So the
whole effect is a swap, and the two halves of the table are the same swap evaluated on either
side of a level change — **0.58 accuracy within distribution, 0.03 across it, against a
majority fallback that scored 0.076 on the same edges.**

sp80 is the mechanism in one row (explorer store → human L2): tier 1.5 takes **90.96%** of the
covered edges at **0.0226** accuracy, from a majority rule that was scoring **0.8009**. m0r0
on human replays: 67.4% of edges at 0.0043, displacing 0.3524. Nothing subtle is happening —
a support-1 conjunction matches far more test states than the training cell that produced it,
and it outranks the fallback by construction, so it fires wherever it matches.

## Rule-count inflation and support

| | median off | median on | median delta |
|---|---:|---:|---:|
| rules, E0 human L1, mode `full` | 11.5 | **103.0** | +92 |
| rules, explorer full store, mode `full` | 10.0 | **126.0** | +117 |

Worst: dc22 14 → 1240 (E0), bp35 11 → 5306 (store). Support distribution over all 8,512
tier-1.5 rules mined at full store: **min 1, median 2, support-1 = 3,460 (41%)**,
support ≥ 5 = 2,709. No minimum was imposed and none is proposed — the protocol, not a
threshold, was supposed to adjudicate, and it did.

## X-phase confident coverage — a hazard, not a win

Confident coverage (`e3_executor.confidence`, full store, mode `full`) rises in **23 of 24
games**, median **0.0000 → 0.3953** (+0.0599 median delta; bp35 0.0000 → 0.7953, vc33
0.0000 → 0.7163, r11l 0.0000 → 0.7154, ft09 0.8237 → 1.0000). X1's measured mean confident
coverage 0.195 with 15 games at zero would be substantially repaired.

**Read this as a warning.** The newly-`confident` edges are exactly the ones measured at 0.03
accuracy once the level changes. A larger plannable graph built from them is a planner
confidently expanding edges it cannot predict — strictly worse than the `uncovered` label it
replaced, which at least routes to a probe. Any future mechanism that grows `confident` must
report transfer accuracy on the edges it adds, not just the coverage number.

## Per-game — E0, human replays, mode `full`

`fixable` = the off-arm `guard_fixable` share of L1→L2 failures (the bucket the task targeted).

| game | fixable | within-L1 off → on | L1→L2 off → on | tier-1.5 rules | 1.5 firing share (L1→L2) |
|---|---:|---|---|---:|---:|
| ar25 | 0.653 | 0.6667 → 0.9375 (+0.2708) | 0.0581 → 0.0581 (+0.0000) | 205 | 0.413 |
| bp35 | 0.042 | 0.3256 → 0.2752 (−0.0504) | 0.4382 → 0.3740 (−0.0642) | 822 | 0.352 |
| cd82 | 0.129 | 0.3017 → 0.3719 (+0.0702) | 0.1210 → 0.1465 (+0.0255) | 327 | 0.238 |
| cn04 | 0.087 | 0.2893 → 0.2995 (+0.0102) | 0.1642 → 0.1689 (+0.0047) | 80 | 0.051 |
| dc22 | 1.000 | 0.2032 → 0.3302 (+0.1270) | 0.0592 → 0.0937 (+0.0345) | 1226 | 0.262 |
| ft09 | 0.000 | 0.8918 → 0.9415 (+0.0497) | 0.1770 → 0.1770 (+0.0000) | 206 | 0.213 |
| g50t | 0.000 | 0.2331 → 0.2285 (−0.0046) | 0.2404 → 0.2220 (−0.0184) | 14 | 0.087 |
| ka59 | 1.000 | 0.2741 → 0.3299 (+0.0558) | 0.0758 → 0.0824 (+0.0066) | 107 | 0.157 |
| lf52 | 0.175 | 0.7176 → 0.7294 (+0.0118) | 0.1945 → 0.2247 (+0.0302) | 81 | 0.199 |
| lp85 | 0.000 | 0.8374 → 0.8409 (+0.0035) | 0.0684 → 0.0684 (+0.0000) | 90 | 0.466 |
| ls20 | 0.118 | 0.4349 → 0.5651 (+0.1302) | 0.4506 → 0.3761 (**−0.0745**) | 93 | 0.631 |
| m0r0 | 0.001 | 0.2381 → 0.3016 (+0.0635) | 0.3514 → 0.1173 (**−0.2341**) | 91 | 0.674 |
| r11l | 0.126 | 0.2029 → 0.2319 (+0.0290) | 0.3333 → 0.2760 (**−0.0573**) | 122 | 0.672 |
| re86 | 0.926 | 0.1840 → 0.2160 (+0.0320) | 0.0066 → 0.0066 (+0.0000) | 267 | 0.176 |
| sb26 | 0.296 | 0.6839 → 0.6839 (+0.0000) | 0.3796 → 0.3406 (−0.0390) | 61 | 0.395 |
| sc25 | 0.000 | 0.3276 → 0.3652 (+0.0376) | 0.0268 → 0.0357 (+0.0089) | 254 | 0.570 |
| sk48 | 0.000 | 0.1950 → 0.2327 (+0.0377) | 0.0399 → 0.0399 (+0.0000) | 88 | 0.040 |
| sp80 | 1.000 | 0.6765 → 0.7353 (+0.0588) | 0.6350 → 0.3145 (**−0.3205**) | 48 | 0.542 |
| su15 | 1.000 | 0.3468 → 0.3871 (+0.0403) | 0.1635 → 0.1635 (+0.0000) | 24 | 0.000 |
| tn36 | 0.631 | 0.8148 → 0.8963 (+0.0815) | 0.8393 → 0.8428 (+0.0035) | 71 | 0.008 |
| tr87 | 1.000 | 0.2785 → 0.2694 (−0.0091) | 0.0000 → 0.0000 (+0.0000) | 5 | 0.216 |
| tu93 | 1.000 | 0.8716 → 0.9257 (+0.0541) | 0.5880 → 0.6067 (+0.0187) | 246 | 0.935 |
| vc33 | 0.097 | 0.8793 → 0.9310 (+0.0517) | 0.0966 → 0.0966 (+0.0000) | 24 | 0.151 |
| wa30 | 0.107 | 0.2329 → 0.2844 (+0.0515) | 0.0012 → 0.0061 (+0.0049) | 675 | 0.186 |

## Per-game — explorer store (e2_dose grid), full dose, mode `full`

| game | store | on-human-L1 off → on | on-human-L2 off → on | rules base+1.5 | supp-1 share | confident cov off → on |
|---|---:|---|---|---|---:|---|
| ar25 | 2972 | 0.6299 → 0.7284 (+0.0985) | 0.0639 → 0.0639 (+0.0000) | 13+157 | 0.64 | 0.7217 → 0.8331 |
| bp35 | 2873 | 0.4916 → 0.6187 (+0.1271) | 0.4757 → 0.3803 (**−0.0954**) | 11+5295 | 0.33 | 0.0000 → 0.7953 |
| cd82 | 2922 | 0.3150 → 0.3264 (+0.0114) | 0.1210 → 0.1529 (+0.0319) | 11+99 | 0.57 | 0.0000 → 0.0264 |
| cn04 | 2885 | 0.2264 → 0.2264 (+0.0000) | 0.1370 → 0.1370 (+0.0000) | 11+13 | 0.69 | 0.0000 → 0.0024 |
| dc22 | 2939 | 0.2278 → 0.2917 (+0.0639) | 0.0552 → 0.0838 (+0.0286) | 14+586 | 0.48 | 0.0000 → 0.0803 |
| ft09 | 1231 | 0.3017 → 0.5517 (+0.2500) | 0.0885 → 0.0885 (+0.0000) | 9+34 | 0.06 | 0.8237 → 1.0000 |
| g50t | 1448 | 0.1771 → 0.1577 (−0.0194) | 0.1153 → 0.1153 (+0.0000) | 5+11 | 1.00 | 0.0000 → 0.0041 |
| ka59 | 2923 | 0.2248 → 0.2646 (+0.0398) | 0.0492 → 0.0572 (+0.0080) | 11+144 | 0.69 | 0.0000 → 0.0246 |
| lf52 | 146 | 0.5769 → 0.6667 (+0.0898) | 0.2050 → 0.2615 (+0.0565) | 16+137 | 0.68 | 0.4384 → 0.7877 |
| lp85 | 42 | 0.6488 → 0.6488 (+0.0000) | 0.0594 → 0.0594 (+0.0000) | 10+0 | — | 0.8571 → 0.8571 |
| ls20 | 2877 | 0.4396 → 0.5563 (+0.1167) | 0.3466 → 0.3435 (−0.0031) | 4+58 | 0.50 | 0.0000 → 0.0309 |
| m0r0 | 2943 | 0.2624 → 0.2653 (+0.0029) | 0.3988 → 0.3694 (−0.0294) | 10+166 | 0.77 | 0.0000 → 0.0194 |
| r11l | 130 | 0.2400 → 0.2343 (−0.0057) | 0.3125 → 0.3047 (−0.0078) | 7+318 | 0.69 | 0.0000 → 0.7154 |
| re86 | 2911 | 0.1726 → 0.1773 (+0.0047) | 0.0394 → 0.0394 (+0.0000) | 5+144 | 0.76 | 0.0000 → 0.0313 |
| sb26 | 2986 | 0.5330 → 0.7244 (+0.1914) | 0.3041 → 0.4136 (+0.1095) | 13+70 | 0.07 | 0.3416 → 0.7354 |
| sc25 | 1606 | 0.1447 → 0.1691 (+0.0244) | 0.0714 → 0.0536 (−0.0178) | 18+553 | 0.40 | 0.3555 → 0.6476 |
| sk48 | 2995 | 0.2145 → 0.2168 (+0.0023) | 0.0339 → 0.0339 (+0.0000) | 15+20 | 0.85 | 0.8210 → 0.8247 |
| sp80 | 1014 | 0.6785 → 0.7363 (+0.0578) | 0.6924 → 0.0495 (**−0.6429**) | 14+101 | 0.41 | 0.0986 → 0.4773 |
| su15 | 358 | 0.4046 → 0.4046 (+0.0000) | 0.1711 → 0.1711 (+0.0000) | 7+9 | 0.00 | 0.2263 → 0.5196 |
| tn36 | 2875 | 0.7278 → 0.7278 (+0.0000) | 0.6007 → 0.6007 (+0.0000) | 7+62 | 0.10 | 0.0000 → 0.0094 |
| tr87 | 2925 | 0.2411 → 0.2411 (+0.0000) | 0.0000 → 0.0000 (+0.0000) | 4+2 | 0.00 | 0.0000 → 0.0014 |
| tu93 | 2573 | 0.7296 → 0.8741 (+0.1445) | 0.5768 → 0.6105 (+0.0337) | 4+133 | 0.53 | 0.0000 → 0.3133 |
| vc33 | 800 | 0.4891 → 0.5620 (+0.0729) | 0.2367 → 0.2464 (+0.0097) | 7+150 | 0.36 | 0.0000 → 0.7163 |
| wa30 | 2960 | 0.2221 → 0.2296 (+0.0075) | 0.0006 → 0.0025 (+0.0019) | 5+250 | 0.56 | 0.0000 → 0.0395 |

Dose-125 endpoint (same shape, in `logs/e0_conjunction.json`): on-human-L1 median +0.0064,
15W/6T/2L; on-human-L2 median 0.0000, 8W/11T/4L, largest loss tu93 0.5431 → 0.3333, largest
gain sc25 0.0089 → 0.1071. lp85's store (42 rows) is below the 125 endpoint and is skipped
there, so n=23. The `moveset` per-game cells are in the log; their medians are quoted above.

## Implementation notes, for whoever revisits this

- **New file only.** `rs_e0.py` was not edited. `e0_conjunction.py` re-implements exactly two
  things — `_fire` (one more rung: tier 1.5, both guards matching, highest support, `rid`
  tie-break) and `score` (same body, plus per-tier firing shares) — and imports the rest.
- **The baseline was proved unmoved, not assumed.** With the tier off, this file's scorer must
  equal `rs_e0.score` field for field; that is asserted on **every one of the 190 scored
  splits in this run** before the on-arm is computed, and `--regress` runs the same check
  standalone. The deltas above are against an unmoved v2 baseline.
- **Genuinely two guards.** Only features shared by all of a key's transitions AND non-constant
  across them are paired; a constant `f1` would make `(f1=v1) ∧ (f2=v2)` numerically identical
  to the single-guard cell `f2=v2` and smuggle in a different mechanism.
- **That other mechanism is measurably large and was not run.** Counted as a diagnostic:
  **544 pure single-guard cells** exist inside the unresolved keys of the 24 human-L1 stores
  (mode `full`). Tier 1 discards them because it is all-or-nothing at the KEY level — this is
  the same finding `notes/miner-vocab-v2-results.md` reached from `key_purity`. Given what
  tier 1.5 just did, the prior on it should be *lower*, not higher: it is the same
  fire-a-specific-rule-instead-of-the-fallback swap with a weaker precondition.

## What this result actually says

The task's premise was that `guard_fixable` is where the losses are and that what remains
guard-shaped is conjunction-shaped. The first half is measured and stands. **The second half
is wrong, and the reason is now measured too:** a two-guard cell that is zero-contradiction on
one level's evidence carries essentially no information about the next level (0.033 accuracy
where it fires), while the majority fallback it displaces carries a little (0.076). The
`guard_fixable` label says a separating feature *exists* among the supporters — it never said
that feature is a mechanic, and this run is a direct measurement that on transfer it usually
is not. That is the same lesson `separable_by_census` taught, now confirmed for the
mechanical-looking half of the bucket.

Consequence for the line: **richer preconditions mined from one level are not the lever.**
Anything that increases hypothesis-space richness against the same single-level evidence should
be expected to reproduce this table. The remaining levers are evidence that spans the change
(deviate-and-branch probes under REPLAY-DET) and hypotheses proposed from outside the store —
which is the Qwen brief, unchanged.

## Limits

- One corpus, one session split, one explorer run; no variance estimate. The direction is not
  marginal (sp80 −0.32/−0.64, tier-1.5 accuracy 0.03 vs 0.58) but the medians are small.
- Held-out human replays measure fit-to-competent-play, inheriting E0's semantics.
- `moveset` and dose-125 are reported as medians here and in full in the log, not tabulated
  per game — they agree with `full` in sign everywhere the medians are quoted.
- The pair search is exhaustive over the pairs it considers and neither cap bound, so "no
  conjunction was found" is never a search failure in this run.
- Arm C of `notes/e2-regrade.md` (tolerance tier) is untouched and independent, as stated. Its
  prior should be updated by this result but not settled by it: it relaxes a *different* knob
  (contradictions allowed, one guard), and its own held-out numbers decide.
