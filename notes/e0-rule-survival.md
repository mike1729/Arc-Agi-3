# E0 — offline L1 → L2 rule survival

**Run 2026-08-04. Zero model calls.** Pre-registered as `gate_manifest.yaml → rs` (frozen
2026-08-04, errata RS-E1…RS-E4). Six iteration games; the remaining nineteen stay sealed —
see RS-E2, which is an open conflict, not a settled decision.

Artifacts: `logs/e0_row_m.json`, `logs/e0_row_c.json`, `logs/e0_fidelity.json`.
Harness: `agent/harness/rs_transitions.py`, `rs_e0.py`, `rs_completion.py`, `rs_fidelity.py`.

## Engine truth — passed

Every session of all six games replayed through the frozen game source via `ReplayDriver` over
`arcengine`, comparing frames.

| game | all-frame sessions exact | role-bearing sessions exact |
|---|---|---|
| dc22 | 11/11 | 11/11 |
| ft09 | 10/10 | 10/10 |
| ls20 | 13/13 | 13/13 |
| m0r0 | 10/11 | 10/11 |
| tu93 | 12/13 | 12/13 |
| vc33 | **3/10** | **9/10** |

vc33's all-frame failure is the accepted settled-frame erratum: the divergence is confined to
intermediate animation frames, which E0 never reads. Role-bearing frames — settled,
solved_terminal, next_level_initial — are the ones a transition endpoint can come from.

The three residual role-bearing divergences are all on `RESET` and all fall at steps **after**
the L1/L2 window E0 reads (m0r0 step 535 vs window end 290; tu93 120 vs 62; vc33 103 vs 62) —
consistent with GI-2's standing note that remote and local reset metadata are not assumed
identical. **Over every frame E0 actually uses, all six games reproduce byte-exactly.**

## What was asked

Whether a rule induced from level-1 evidence is still true at level 2 — the standing objection
to spending the evidence budget on L1. It has been an assumption on both sides; this is the
first measurement of it.

## Headline

**The objection is right about the dynamics and wrong about the goal, and the split is sharp.**

Which actions do anything at all transfers nearly intact. What those actions *do* collapses,
and it collapses hardest precisely on the games where L1 supported a good model in the first
place. Where the goal is expressible at all, it transfers essentially perfectly.

## Row M — mechanics

Rules are `action [+ one guard] → effect` over object events, mined at three granularities.
Accuracy is over all test transitions. `within-L1` trains on half the L1 sessions and tests on
the other half — it is the ceiling this game's evidence supports, and the **gap** between it
and L1 → L2 is the part attributable to the level change rather than to thin evidence.

| game | full: within-L1 → L1→L2 | changed: within-L1 → L1→L2 |
|---|---|---|
| dc22 | 0.203 → 0.059 | 0.832 → **0.890** |
| ft09 | 0.845 → **0.177** | 0.903 → **0.867** |
| ls20 | 0.435 → 0.451 | 0.949 → **0.979** |
| m0r0 | 0.238 → 0.351 | 0.913 → **0.935** |
| tu93 | 0.872 → **0.588** | 1.000 → **0.929** |
| vc33 | 0.879 → **0.097** | 1.000 → **0.990** |

`moveset` (movement vectors dropped) tracks `full` almost exactly on four of six games, so the
collapse is not about *how far* things move — it is about *which objects* change at all.

**The perverse pattern.** The three games with a good L1 model — ft09, vc33, tu93 — are the
three that lose the most. The three that transfer flat (ls20, m0r0, dc22) do so because their
L1 model was already poor; there was nothing to lose. Reading a flat line as "transfer works"
would invert the finding.

**Memorizer floor: 0.000 on every game, both splits.** Exact 64×64 pre-states essentially never
recur across sessions or levels, so nothing here is memorization. Any accuracy above zero is
generalization by the rule model.

### The failure split

Mispredictions, `full` granularity, L1 → L2:

| game | guard-fixable (`adj`) | separable by census | unpredicted |
|---|---:|---:|---:|
| dc22 | 884 | 0 | 0 |
| ft09 | 0 | 69 | 0 |
| ls20 | 127 | 745 | 206 |
| m0r0 | 0 | 87 | **1026** |
| tu93 | 91 | 0 | 0 |
| vc33 | 8 | 177 | 0 |

Three categories, not two, and the third is the correction that matters (RS-E4). A first pass
scored 100% guard-fixable on four of six games; the separating feature was per-colour *count*
in essentially every case. That is an artifact of vocabulary width — every supporter of a rule
shares its effect by construction, so once counts are in the vocabulary almost any unseen state
"separates". Requiring the feature to be constant across supporters, and counting only `adj`
(something is in the way) as a repair, gives the table above.

Read straight: **repairable mispredictions are the minority.** dc22 and tu93 are genuinely
guard-repairable. ft09 and vc33 fail in a way that is only distinguishable by "L2 has a
different census of objects" — true, but not a precondition anything could act on. m0r0 is the
hard case: 1026 mispredictions where the transition is *indistinguishable from the rule's
supporters in the entire guard vocabulary and still behaves differently*. That is hidden state,
and no local repair addresses it. m0r0 also fails within L1 (0.238), so this is a property of
the game, not of the level change.

## Row C — completion conditions

Frozen ES visual grammar, hash asserted at run time. Outcomes are three-way; `vacuous` (never
definite at L2, terms unbound) is kept separate from `survived` so that grammar silence cannot
be reported as goal stability.

| game | universe | L1 survivors | L1→L2 survived / falsified / vacuous | rate |
|---|---:|---:|---|---|
| dc22 | 177 | 13 | 12 / 1 / 0 | **0.923** |
| tu93 | 150 | 12 | 12 / 0 / 0 | **1.000** |
| ft09 | 70 | 0 | — | UNDEFINED |
| ls20 | 168 | 0 | — | UNDEFINED |
| m0r0 | 43 | 0 | — | UNDEFINED |
| vc33 | 70 | 0 | — | UNDEFINED |

**Where the goal is expressible, it transfers.** dc22 loses one hypothesis of thirteen over 1014
L2 transitions; tu93 loses none. Within-L1 rate is 1.000 for both, so there is no gap to
explain. Nothing here is vacuous survival — every surviving candidate made definite correct
predictions at L2.

**Four of six games are UNDEFINED, and that is the real limit on this row.** An empty L1
survivor set means the visual grammar cannot express that game's completion condition *at all* —
0/0, not 0%. This independently reproduces the ES screen's coverage-blocked closeout (six of six
unproven) from a different direction, which is worth something as corroboration and worth
nothing as reassurance: row C's positive result rests on two games.

## What this licenses, and what it does not

- **L1 as an evidence budget buys the action inventory, not the dynamics.** Liveness — which
  actions do anything — is the part that survives, across all six games including the ones where
  everything else falls apart. An explorer that spends L1 to learn *what the buttons do* is
  buying something durable. One that spends L1 to build a detailed forward model for planning at
  L2 is, on three of six games, buying something that expires.
- **The X phase's plan-then-execute assumption is the exposed one.** BFS/A* over a mined
  forward model needs `full`-granularity dynamics, and that is the row that collapses.
- **Repair-vs-invalidate defaults cannot be set from this yet.** The honest repairable fraction
  is much smaller than the first pass suggested, and on m0r0 it is zero for reasons no guard
  vocabulary fixes.
- **This says nothing about whether anything can FIND these rules.** It measures only whether
  rules that are true at L1 stay true. A miner with perfect L1 evidence was assumed throughout.

## Known limits

1. **n = 6, and row C is n = 2.** RS-E2.
2. **One guard, not conjunctions.** Deliberate — a richer hypothesis space fits any split and
   destroys the survival number — but it means "unpredicted" is relative to this vocabulary.
3. **L1 → L2 only.** Whether the L2 → L3 gap looks like the L1 → L2 gap is untested, and the
   levels are not obviously exchangeable.
4. **Human replays are not explorer trajectories.** Humans do not sweep the action space; the
   evidence an actual E phase collects will have different coverage, probably better for
   liveness and worse for rare events.
5. **Row C's `survived` is not `correct`.** A surviving candidate is one never definitely
   contradicted; it need not be the true completion condition. dc22 ends with twelve mutually
   distinct survivors, so the goal is *stable* under level change, not *identified*.
