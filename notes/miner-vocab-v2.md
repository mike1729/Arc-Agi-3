# Miner vocabulary v2 — the named feature + census-scoped firing

**Task note 2026-08-04, lean mode. Zero model calls.** Self-contained; execute without
further context. Working numbers labelled (w).

## Why (all measured)

1. **The dose curve is flat in the median** (`notes/e2-dose.md`): the E0 miner's quality
   is bottlenecked on vocabulary, not evidence volume.
2. **The E2 slice's one keepable output is a missing word** (`notes/e2-slice.md`): on ft09
   Qwen proposed zero rules and named why — `adj:C:direction` only tracks neighbours of
   *single-object* colours from a fixed reference, and the vocabulary "lacks a
   `clicked_adjacent_to:C` or per-component neighbor feature".
3. **E0's largest transfer-failure bucket is `separable_by_census`** (~10 games; lp85,
   g50t, sk48 the largest counts): failures where a `count:`/`present:` feature is
   constant across the rule's supporters and differs on the failing transition. The
   separator is ALREADY in the vocabulary — the rule was simply mined in a census context
   it silently assumed. That is a rule-scoping gap, not a feature gap.

Hence two independent mechanisms, measured separately and together.

## Mechanism 1 — `clicked_adjacent_to:C` (new guard feature, ACTION6 only)

In `rs_transitions.guard_features`: let K = the 4-connected same-colour component of the
pre frame containing the clicked cell (same componentization the segmentation uses —
`gi2_observation.componentize`; background-coloured components are legitimate K). For each
colour C present in the pre frame, emit `clicked_adjacent_to:C` = True iff any cell of K
is 4-adjacent to a cell of a component of colour C (C ≠ K's own colour), else False.
Emitted only when `action_id == 6` and the click is in bounds — same convention as
`click_colour`. ≤16 boolean features; tier-1 search cost is linear and negligible.
Background clicks make K the canvas and the feature near-vacuously True for many C —
accepted, not special-cased; the measurement decides.

**No store regeneration is needed**: guards are computed at load time from grids
(`rs_transitions.iter_session_transitions`, `e2_dose.load_store`) — this is a code-only
change. E1 does not rerun.

## Mechanism 2 — census-scoped firing (rule applicability, existing features)

At mine time, attach to each rule its **census scope**: the values of `count:C` /
`present:C` features constant across all its supporters, restricted (w) to **effect-local
colours** — the colours appearing in the rule's effect, plus `click_colour` for A6 keys.
At fire time (`_fire`), a rule whose scope does not match the transition **abstains**
(transition becomes uncovered) instead of firing.

Effect-locality is the (w) design choice: scoping on ALL constant features would make L1
rules abstain on nearly every L2 transition (everything is constant in one level's
evidence) and collapse coverage. Run **three arms** on the same data — {unscoped (=v1),
effect-local scope, full-constancy scope} — and report all three; the third arm exists to
show the collapse, not to win. If effect-local moves nothing, that is the reported result.

The intended trade is explicit: this converts census-separable WRONG predictions into
ABSTENTIONS. For X-phase planning a wrong prediction costs a misprediction-repair cycle
while an abstention triggers a probe, but no utility number for that trade is invented
here — report `accuracy_over_all`, `accuracy_over_covered`, `coverage`, and the
`failure_split` shift (census bucket should shrink; uncovered should grow) and let the
X-phase design consume the numbers.

## Measurement (all zero-model, existing harnesses)

1. **E0 rerun** (`rs_e0.py`, human replays, all 24 games): v1 vs v2 vocabulary, `full` +
   `moveset` modes — held-out-L1 and L1→L2 tables, failure splits.
2. **Floor rerun** (`e2_dose.py`, explorer store): same doses, same targets — the floors
   every future slice compares against. Note in the output that floors moved and why.
3. **Focus rows:** ft09 (does the A6 split the missing word was named for resolve — 
   unresolved-key count and the specific key), and lp85/g50t/sk48 (E0's census bucket).
4. **Guard-quality check for Mechanism 1**: count how often `clicked_adjacent_to:*` is the
   selected tier-1 partition feature; a feature that never partitions anything is reported
   as dead weight, not silently kept.

Adoption rule: no invented thresholds — the deltas decide, per mechanism, and a mechanism
that helps nowhere is dropped with its numbers recorded. If v2 is adopted, `notes/e2-dose.md`
gets a dated addendum saying the floor definition changed as of this commit.

## Non-goals

The verification repair bar (tu93's 97.8% rule) — that is the pre-committed slice-2
amendment, decided before slice 2 runs, not here · any model call · any change to the
explorer or stores · feature-pair (conjunctive) tier-1 search — out of scope this pass;
revisit only if census-scoped firing leaves the census bucket standing.
