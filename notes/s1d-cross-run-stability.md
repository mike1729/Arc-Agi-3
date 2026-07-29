# S1-d — is the failure-category ranking stable across runs? — 2026-07-28

Task #8, run at last. 75 episodes labelled: 25 each from Kaggle runs v2, v3 and v4, one configuration,
byte-identical executed source, pooled under S1-E14. The question was whether the ranking that sets the
build order survives being re-measured.

**It does not survive.** The ranking flips between runs of one identical configuration. Whether that is
real variation or a rating artifact is **not yet established**: the only re-rate available (§2a) is
partial (17 of 25), not blind, and measures primary labels only. It is consistent with real variation
and cannot demonstrate it. The blind re-rate is the measurement that decides this.

---

## 1. The headline

`primary_share` in the **L2+ band** — the band `gate_manifest.yaml → s1` says the build order is ranked on.

| category | v2 (n=12) | v3 (n=15) | v4 (n=15) |
|---|---:|---:|---:|
| **`goal_unknown`** | **75%** | **53%** | **27%** |
| `action_semantics_unknown` | 8% | 27% | **33%** |
| `latency_or_budget` | 8% | 13% | 20% |
| `exploration_or_probe_selection` | — | 7% | 13% |
| `irreversible_mistake` | — | — | 7% |
| `progress_signal_misinterpretation` | 8% | — | — |

**In v4's L2+ band the ranking flips**: `action_semantics_unknown` (33%) overtakes `goal_unknown` (27%).

Pooled across all levels the top category holds in every run — 76% / 56% / 44% against a runner-up of
12% / 24% / 24% — but the *margin* collapses from 64 points to 20.

Paired comparison on the 16 `(game, level)` triples present in all three runs:

| | |
|---|---:|
| all three runs agree on the primary label | **5 / 16 = 31%** |
| two agree, one differs | 8 / 16 |
| **all three different** | **3 / 16** |

The three-way splits are `g50t` L1 (latency → exploration → hidden-state), `r11l` L2 (goal → action-semantics
→ latency) and `sp80` L2 (progress-signal → goal → action-semantics). **`g50t` and `sp80` were v2's two
headline counter-examples to `goal_unknown`** — the episodes cited as evidence that the category was not
everywhere. Neither reproduces.

---

## 2. Drift was suspected, then tested, and the suspicion was mostly wrong

**Added 2026-07-28, after the partial v2 re-rate. This section originally concluded that the decline was
rater drift. That conclusion is withdrawn; the evidence below is what it was, and §2a is what the test
returned.**

Two things in the data pointed at the rater rather than the runs.

**The decline is monotone in labelling order.** The episodes were labelled v2 first (a previous session),
then v3, then v4. `goal_unknown` falls 75 → 53 → 27 in exactly that order. Sampling noise across three
independent draws of one configuration should be non-monotone; a monotone trend aligned with the order of
work is the signature of drift.

**`latency_or_budget` episode_share went 48% → 100% → 100%.** All 75 episodes are budget-terminated —
verified, `budget_terminated: 75/75` — so the underlying fact is *identical* in every episode of every run.
A label whose ground truth is constant cannot legitimately move 48 → 100. That is a changed recording
convention, and it is measured rather than suspected.

`goal_unknown`'s **episode_share** is meanwhile roughly flat: **92% / 76% / 84%**. So the category is being
*detected* at a similar rate throughout; what moved is how often it was designated **primary**. The drift
is in the primary-assignment rule — how aggressively an earlier cause is preferred over a proximate one —
not in whether the failure is seen.

### 2a. The test — v2 re-rated on the scripted worksheet

17 of v2's 25 episodes were re-read on the **same slice as v3/v4** and re-rated under the current
convention. Result: **16 of 17 primary labels reproduce — 94% agreement.** The single change is `sb26`
(`goal_unknown` → `exploration_or_probe_selection`). `goal_unknown`'s share on those 17 moves 88% → 82%.

**This is consistent with the primary-assignment rule not having drifted — but it does not establish
it,** and three independent weaknesses all push the 94% in the same optimistic direction:

1. **Not blind** (see below): anchoring runs toward the original labels.
2. **Partial**, 17 of 25, and the 8 omitted are not a random remainder.
3. **Primary-only.** The statistic compares designated primaries and is *structurally blind to
   secondary labels* — a pass that changed every secondary label and no primary would still score
   100%. That matters precisely here, because the drift this section identifies is in
   `latency_or_budget`, which is a **secondary** label on almost every episode. The 94% is measured on
   the one axis the suspected drift does not live on.

So: `primary_share` is computed from primaries, and on primaries the two passes agree closely. What is
untested is whether the *convention* governing secondary labels changed, which is what the 75 → 53 → 27
decline was attributed to. The blind re-rate now reports agreement on full label SETS as well as on
primaries (`s1d_blind_rerate.py score`), which is the table that can settle this one.

**The decline is therefore best read as an open question with run-to-run variation as the leading
explanation, not as a settled finding.** Three independent runs of one configuration do not agree about
how the agent fails; whether a rater would reproduce those disagreements is what the gate measures.

*Contamination, stated rather than hidden:* this re-rate was **not blind**. The rater had already seen
v2's aggregate result and several episode characterisations in `notes/s1d-failure-frequencies.md`.
Anchoring therefore runs **toward** the original labels — that is, against the drift hypothesis, in the
same direction as the result. A 94% agreement obtained under pro-original anchoring is weak evidence for
"no drift" and would be worth far more from a fresh context. **8 of 25 episodes remain un-re-rated**
(`sk48`, `sp80`, `su15`, `tn36`, `tr87`, `tu93`, `vc33`, `wa30`), and they are not a random remainder:
at least three carried non-`goal_unknown` primaries in the first pass.

---

## 3. What this does and does not change

**It does not overturn the build order.** `goal_unknown` is still the top pooled category in all three
runs, still by roughly a factor of two, and is still present in 76–92% of every run's episodes. Nothing
here promotes a different component to first place.

**It does destroy the 67-point margin** that `notes/s1d-failure-frequencies.md` used to argue the ranking
was robust. That note's robustness claim — "four episodes would have to relabel, all to the same
alternative" — was computed on v2 alone. Four episodes did effectively relabel, in v3 and again in v4.
The claim should be read as withdrawn rather than merely qualified.

**It makes the blind re-rate the load-bearing measurement, and changes its design.** The pre-registered
re-rate (`blind_rerate`, `sample_size: 30`, `agreement_floor: 0.40`) was scoped to measure rater
agreement. It must now also **re-rate v2 episodes on the scripted worksheet**, because the v2 labels were
produced under a different evidence slice and a demonstrably different convention. Without that, the
three runs are not comparable and no cross-run statement is available at all.

**Practical consequence for §2 of the sprint document.** Tier 2 (goal induction, belief ledger, probe
controller) stays ahead of Tier 3 on the pooled evidence. But `action_semantics_unknown` at 24–33% in the
later runs is a materially stronger second than v2's 8% suggested, and `action_semantics_unknown` is a
**Tier 3 rung-2 capability** (system identification). The gap between the two tiers is narrower than the
first pass implied.

---

## 4. Secondary observations worth keeping

- **Three categories acquired their first primary label** in v3/v4: `exploration_or_probe_selection`
  (4 episodes), `irreversible_mistake` (1), `hidden_state_aliasing_or_memory` (1). All three were
  present-but-never-primary in v2.
- **`hidden_state_aliasing_or_memory` finally has direct evidence** — `g50t` v4, where hashing the maze at
  each chamber yields eight distinct values and the agent concludes the maze reconfigures as it moves;
  and `r11l` v3, where it tabulates transitions to find why an identical click stopped working. This is
  the Alias mechanism, and until now the corpus barely evidenced it (S2's Alias family targets a category that
  was 0% primary in v2).
- **`reasoning_inconsistency` has its first evidence at all** (`re86` v4), at low confidence, and it is a
  correct self-retraction rather than an unresolved contradiction.
- **The same-game quality spread is very wide.** `wa30` L1: v3 spent 381 actions and reported "I don't
  know the exact movement mechanics"; v4 solved the pick-up/drop mechanic and was activating targets when
  the clock stopped. Same game, same configuration, same budget.
- **`sc25` L1 is the corpus's most stable result** — three runs, three times reaching the state its own
  goal model called the solution and not completing the level.

---

## 5. Limits

- **Single rater, an LLM, across all three runs** (S1-E10). Section 2 shows the rater is not stationary,
  which is a stronger statement than S1-E10's original caution.
- **The evidence slice differs between v2 and v3/v4** — ad hoc versus
  `s1d_worksheet.py`'s fixed first-1 + last-2 steps at 1000/700/350 characters. This is the confound.
- **The opening-and-closing slice under-counts mid-episode categories**, `hidden_state_aliasing_or_memory`
  most of all, in v3/v4 by construction and in v2 by the earlier note's own admission.
- **No agreement statistic yet.** `agreement_floor: 0.40` still has not been applied to anything.
- **18 of the 34 (game, level) pairs are not present in all three runs**, because the runs stalled on
  different levels. The paired analysis in §1 uses the 16 complete triples, and the 18 unpaired are not
  missing at random — they are the games whose outcome varied most.

## Provenance

`logs/s1d_corpus_pooled.json` — 75 episodes, all labelled, per-episode `labelling` block recording rater,
pass, worksheet slice and source file. Labels in `logs/s1d_labels_v3v4_pass1/`. Worksheet regenerated by
`agent/harness/s1d_worksheet.py`; labels applied and validated by `agent/harness/s1d_apply_labels.py`;
every table on this page regenerates from `agent/harness/s1d_cross_run.py` into
`logs/s1d_cross_run.json`. No number here was typed by hand.
