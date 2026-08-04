# E1-pre — click-candidate recall: result

**2026-08-04. Zero model calls.** Gate on the E1 explorer per `notes/e1-explorer.md` §2 and its
E1-pre section. Scope: every human **L1 ACTION6** in the replay corpus, 24 public games (s5i5
excluded by E0's fidelity rule RS-E5), 4,161 clicks over 18 games — six games
(g50t, ls20, re86, tr87, tu93, wa30) contain **no L1 click at all** and are unmeasurable here.

Code: `agent/harness/e1_candidates.py` · `e1_equiv.py` · `e1_reach.py`.
Data: `logs/e1_pre_all.json` · `logs/e1_equiv_all.json` · `logs/e1_reach_all.json` ·
`logs/e1_reach_tn36_exact.json`.

## Verdict

**The explorer is not blocked. Three of its declared §2 parameters change.**

1. **Cap 64 → 96.** At 64 the cap costs completion-path clicks (ft09 0.943, one of its eight
   completing clicks). At 96, node recall is **1.000 on 17 of 18 games**, bp35 0.986.
2. **Duplicate fill: smallest-first → largest-first.** §2 spends leftover slots on the smallest
   class-duplicates; measured, that fills the budget with single-cell dust and is what actually
   costs bp35 its recall (**0.610 → 0.986** at cap 96, nothing made worse). Class
   representatives are unaffected, so a legitimate one-cell target still enters the pool.
3. **The 8×8 background lattice is adopted, not held contingent.** It is load-bearing for r11l,
   where 2 of 10 L1 completions are unreachable without it.

And one measured rejection: **a blanket minimum-node-size filter.** It fixes bp35 as cheaply as
the fill change (192 → 14 candidates/state) but breaks six games whose humans genuinely click
single pixels — ka59 0.200 of targets, su15 0.194, r11l 0.164, ar25 0.150, dc22 0.070. Recall
falls to 0.800–0.961 there. Not adopted.

**Segmentation never loses a click.** Every miss at every cap is attributed `cap_culled`; zero
`absent`, zero unsegmented. The failure mode was budget allocation, not vision.

## Part 1 — is the click in the pool?

Node recall = the human's cell falls inside a retained candidate's component. Cell recall = the
human's exact cell IS a candidate point. Both under the adopted cull.

| | cap 32 | cap 64 | **cap 96** | cap 128 | cap 192 |
|---|---|---|---|---|---|
| games at node recall 1.000 (of 18) | 10 | 14 | **17** | 17 | 18 |
| worst game | ft09 0.239 | tn36 0.812 | **bp35 0.986** | bp35 0.993 | — |

**Cell recall is uniformly poor — 0.035 (cn04) to 0.379 (su15), median ≈ 0.17.** The centroid
almost never lands on the human's exact cell. Whether that matters is Part 2's question, and it
is why Part 2 exists rather than being left as declared uncertainty.

## Part 2 — is a centroid click the *same* click?

Fork the engine at the pre-click state, click the owning node's candidate point instead of the
human's cell, compare the settled outcome (last frame · state · levels_completed).

| band | games | settled-equivalence |
|---|---|---|
| equivalent | ar25, cd82, dc22, ft09, ka59, m0r0, sk48, sp80, vc33 | 1.000 |
| near | lp85 0.995 · bp35 0.990 · lf52 0.979 · cn04 0.964 · sb26 0.936 | ≥ 0.936 |
| **not equivalent** | sc25 0.884 · tn36 0.851 · **su15 0.466** · **r11l 0.218** | ≤ 0.884 |

r11l and su15 are exactly the games the design note predicted: the two highest background-click
fractions in the corpus (r11l 107/171, su15 127/335). **Placement games click locations, and a
location has no centroid.** Node recall genuinely overstates coverage for them — the honest
uncertainty resolves against the optimistic reading, and Part 3 settles the consequence.

**Deep-copy forking is not universally faithful.** On tn36, replaying the recorded action on a
`copy.deepcopy` of the engine diverges from the same action on the engine itself once state has
accumulated — 130 of 433 clicks. Every fork now carries a per-click control and unfaithful
clicks are excluded, not scored; tn36's uncorrected pair (0.878 settled / 0.596 all-frame) was
partly this artifact, and its corrected pair is 0.851 / 0.851. Where the control fails
wholesale, `e1_reach.py --exact` forks by prefix replay instead.

## Part 3 — can the alphabet reach the completion?

The operational bar, and a strictly weaker one: standing where the human stood at an L1
completing click, does **any** point the explorer would have tried complete the level? A
*different* winning click is a win. Cap 96 + 8×8 lattice; the human's own cell is replayed as a
control, and a game whose control fails is not reported as a result.

| game | L1 completions | control ok | by candidates | + lattice | unreachable |
|---|---:|---:|---:|---:|---:|
| ft09 | 8 | 8 | 8 | 8 | 0 |
| lf52 | 10 | 10 | 10 | 10 | 0 |
| lp85 | 40 | 40 | 40 | 40 | 0 |
| r11l | 10 | 10 | **8** | 10 | 0 |
| su15 | 13 | 13 | 13 | 13 | 0 |
| tn36 | 10 | 10 | 10 | 10 | 0 |
| vc33 | 9 | 9 | 9 | 9 | 0 |

*(tn36 by prefix-replay forking — its deep-copy control fails 0/10.)*

**100 of 100 L1 completions are reachable.** su15's 0.466 point-equivalence does not cost it a
single completion; r11l's 0.218 costs it two, and the lattice recovers both.

The gap between Parts 2 and 3 is the useful finding: **point-equivalence and completion
reachability are different properties, and the explorer only needs the second.** Reporting
Part 2 alone would have condemned r11l and su15; reporting Part 1 alone would have declared them
fine. Neither is the answer.

## What the cap is actually buying

Distinct (colour, shape) classes per state **never exceed 22** anywhere in the corpus
(medians 5–21, max 22 on sb26). One representative per class therefore always fits, at any cap
down to ~24, and §2(ii)'s class-admission tie-break order never fires — it is untested here
because it is unreachable at these node counts, not because it was verified.

So the entire cap-64-vs-96 question is about the **duplicate fill**: the extra ~72 slots exist
solely to decide *which instance* of an already-represented class to click. That is where the
explorer's branching factor comes from, and it is why the fill order — not the cap, and not the
class ordering — is the parameter that moved bp35 by 0.376.

## bp35 — the one game still short of 1.000

0.986 at cap 96, 1.000 only at 192 (median 192 nodes/state, max 235). **91.8% of bp35's
components are single cells** while its human targets have median size 21; the largest-first
fill is what recovers it. bp35 also carries the settled-frame erratum shared with vc33
(intermediate-frame divergence, found in E0's fidelity pass), so its frames are among the least
trustworthy in the corpus. It has no L1 completion by click, so Part 3 cannot adjudicate it.
Left as measured, not repaired further.

## Limits — read before citing

- **Six games have no L1 click and are unmeasured.** Nothing here licenses a claim about their
  candidate coverage.
- **Reachability is measured only at states a human reached on a completing path.** It says the
  winning click is in the alphabet at the winning state; it says nothing about whether the
  explorer's routing gets there.
- **11 of 18 games have no L1 click completion at all**, so Part 3's 100/100 rests on 7 games.
- Human clicks are competent play, not a uniform sample of useful clicks. Recall against them
  bounds coverage of *good* clicks, not of the action space.
- The cap-96 median candidate count is 7–89 per state depending on game, and that is the
  explorer's branching factor — E1's budget arithmetic should use the measured per-game number,
  not the cap.
- No threshold was pre-registered and none is invented here; the measured numbers decide.
