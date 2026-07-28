# Every learned artifact in the spec, and how hard its data is to get — 2026-07-28

Master index. Covers **all of `arc-agi-3-implementation-spec.md`**, not only the sprint. Detail lives
in [`evaluator-training-data.md`](evaluator-training-data.md) (the W3 evaluator) and
[`screening-training-data.md`](screening-training-data.md) (S2–S4). Corpus figures are measured —
`agent/harness/s2_corpus_census.py` → `logs/s2_corpus_census.json`.

**Difficulty is about acquiring the data, not about building the model.** A rung-5 transfer head is
hard to build and easy to feed; the learned gate is the reverse.

| | Scale |
|---:|---|
| **0** | in hand, nothing to do |
| **1–2** | one script over data already on disk |
| **3–4** | already on the calendar — comes free from work that is scheduled anyway |
| **5–6** | needs a new instrument built first (a generator, a local oracle harness) |
| **7–8** | needs environment interaction under a hard budget cap; **may not yield enough** |
| **9–10** | structurally unobtainable from any planned source, or blocked on an unresolved decision |

---

## Master table

### Tier 1 — substrate (§4)

Almost all of Tier 1 is nonparametric: harness, branching primitive, canonicalizer, delta compiler,
archive, hypothesis store, I/O contract, terminal logging. **One learned artifact:**

| § | Artifact | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 4.5 | **Click salience proposer** | (state, clicked coord) + outcome, dev partition only | **56,347** ACTION6 with coords; 12,613–55,686 after the draw | **2** | on disk. Balance the §13.5 draw — 6 games have zero ACTION6 |
| 4.5 | ├ demonstrated-coordinate recall | replay clicks | same as above | **1** | free |
| 4.5 | ├ useful-region recall | coordinate equivalence classes | none | **6** | needs region equivalence from game source or the delta compiler |
| 4.5 | └ **causal** useful-coord recall | branched audits | none | **8** | R1–R3 only: 15 slots/game-round, n=20, d ≤ 15, K=1 |

### Tier 2 — cheap action evaluator (§5), ships W3

| § | Head | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 5 | **Changed-region estimate** | exact deltas | **701M** cell labels | **0** | derivable, free |
| 5 | **P(visible change)** | settled-frame comparison | **171,199** | **0** | free |
| 5 | **P(no-op)** | settled-frame comparison | **8,945** + 1,446 agent | **1** | free; concentrated — 5 games supply <50 each |
| 5 | **P(persistent change)** | does the change survive a horizon | derivable, **not yet computed** | **2** | one pass, same shape as the reversibility pass |
| 5 | **P(progress event)** | level/score marker or registered signature | **1,614** replays + 49 agent → **850–1,287** after the draw | **4** | real positives are capped; procedural supplies more **at a chosen prevalence**, which is a calibration decision, not free volume |
| 5 | **Reversibility — *demonstrated reversible*** | return to same state, same level, ≤ 30 actions | **5,065** (counted 2026-07-28) | **1** | free |
| 5 | **Reversibility — *demonstrated irreversible*** | **verified absence** of a return route | **0, and no replay can ever supply one** | **7** | search. Local game fork (§5b of the screening note) or branching |
| 5 | **Uncertainty / OOD** | held-out + genuinely off-distribution states | none assembled | **3** | falls out of the dev/validation split + procedural held-out families |
| 5 | Candidate value (4b weak labels) | executive preferences, biased and declared | none | **3** | free from shadow mode once the agent runs — W3 |

### Tier 2 — invocation and suppression gate (§6)

| § | Artifact | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 6.2 | Adaptive threshold controller | procedural held-out calibration error, \(q_{hi}/q_{lo}\) | none | **4** | comes with the procedural suite + W3 agent runs |
| 6.8 | **Learned gate** \(P(\text{useful})\) | **≥ 800 valid branched disagreement states** with the frozen \(Y_{useful}\) label | **0** — nominal ceiling 2,040, needs ≥ 39% end-to-end validity | **8** | R1–R3 only. **The spec already predeclares this may be unfundable** and falls back to uncalibrated ordering |

### Control portfolio (§7) and verified programs (§8)

| § | Artifact | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 7 | Rows 1, 2, 5, 6 arbitration | — | deterministic | **0** | not learned |
| 7.4 | Deterministic probe selection v1 | ledger cheapest-test field | — | **0** | not learned |
| 7 | **Learned probe selection** (Tier 3) | hypotheses-resolved-per-scored-action, with active hypothesis sets | none | **7** | needs a running ledger + branching to verify resolution by exact delta |
| 8 | Verified partial programs | **not trained** — DSL search. Admission needs \(N_{prog} \ge 8\) held-out context-matched transitions each | free from play | **1** | comes with the agent running |

### Goal induction (§9), gate G0 at W7

| § | Artifact | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 9.1 | **G0-R** — post-outcome recognition | terminal transitions, dev partition + procedural; **never random splits** | 850–1,287 real, divided again by held-out level / trajectory / instance / parameter / family | **5** | same scarce pool as the progress head, split harder. Procedural is the only elastic source |
| 9.1 | G0-A — source: cheap-evaluator prediction | evaluator outputs on logged transitions | free once §5 ships | **2** | W3 |
| 9.1 | G0-A — source: belief-model prediction | belief-model outputs | free once §11 ships | **2** | W5 |
| 9.1 | G0-A — source: verified program | program predictions | free once §8 ships | **2** | W6 |
| 9.1 | **G0-A — source: exact branch** | forked successor for the candidate | **0** | **7** | branching rounds, or a local game fork |
| 9.2 | Terminal-action recall decomposition | proposal / conditional-ranking / end-to-end split | needs the candidate set logged per state | **1** | instrument it in W2, free thereafter |
| 9.6 | **Fork G-F — F4, F5 families** | two new generators, 2–3 days each | none | **6** | gated on **≥ 5 build-days slack at Aug 22** — a calendar decision, not a data problem |

### Belief model (§11), R0 at W5

| § | Artifact | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 11.1 | Spatial encoder · context transformer · forward model \(f(z_t,h_t,a_t)\) | transitions with matched history | **180,144** replay + 12,475 agent + unbounded procedural | **2** | on disk. **Epoch-limited, not volume-limited** — 284 epochs at a 100k-step budget |
| 11.1 | Multi-horizon heads 1/2/4 + composition-consistency loss | multi-step windows from the same trajectories | same | **2** | free from the same corpus |
| 11.1 | Detached-auxiliary control | a training-configuration variant | — | **0** | not a data problem |
| 11.2 | Rung 1 predictive sufficiency · rung 2 system identification | as above + hidden-state labels for probes | procedural only | **3** | procedural suite supplies hidden state; replays never do |
| 11.2 | **Rung 3 counterfactual discrimination** | (state, action A, action B, which was better) | **23,032** pairs, of which **204** involve progress | **8** | replays structurally cannot supply this. Local game fork, or branching |
| 11.2 | Rung 4 composition | k-step windows | free | **1** | same corpus |
| 11.2 | Rung 5 relational transfer | held-out layout + colour-permutation variants | none yet | **3** | the S2 generator interface already promises recoloured/relaid variants |
| 11.2 | Rung 6 mechanism retrieval | archive + ANN index | free from play | **2** | **Tier 4, unscheduled** |
| 11.2 | Auxiliary heads (persistent · changed region · event class · reversible · no-op · novelty · coord salience · OOD) | same as the §5 heads | see §5 rows | **0–7** | inherits each §5 row's difficulty |

### Gate evidence (§10, §13)

| § | Evidence | Data it needs | Have now | ⬛ | Path |
|---|---|---|---|:-:|---|
| 10.1 | **D0** executive viability | latency table, measured actions/s, always-call cost | S1 measured 2.09 s/action vs ~2.9 s budget | **1** | re-measured W1 |
| 10.2 | **R0** belief-model viability | rung results under matched information | from S3/W5 | **3** | scheduled |
| 13.1 | \(n_{val}\) — 150 stratified suppression-harmless checks | strata: uncertainty/margin deciles, risk, ACTION6, OOD, game, level, τ | none | **6** | needs the W3 agent running with the §6.9 decision record |
| 13.2 | Paired runs — procedural | 20 instances × 3 seeds × 5–7 τ points per condition | none | **4** | procedural suite |
| 13.2 | Paired runs — public validation | 8 validation games × 2 seeds × 2 operating points | free | **1** | veto-only, W7 |

---

## What the ratings actually say

**Nothing scores 9–10.** There is no artifact in the spec whose data is structurally unobtainable —
the two that *replays* cannot supply (rung 3 counterfactual discrimination, demonstrated-irreversible)
both have a source, it is just not the replay archive.

**Everything at 7–8 traces to one root cause: counterfactuals.** Six rows — §4.5 causal recall,
§5 irreversible, §6.8 learned gate, §7 learned probe selection, §9.1 G0-A exact-branch, §11.2 rung 3 —
all need *what a different action would have done*, and all currently point at the same scarce
instrument: the branching rounds, capped at 24,000 attempted actions per game per round with a
nominal ceiling of 2,040 valid disagreement states against a requirement of 800.

**That single instrument carries six artifacts and the spec already predeclares it may fail.** §13.1's
\(n_{causal}\) feasibility decision at R1 says: if yield projects under 800, the causal tier is
unfundable and the learned gate falls back. What is *not* written down is that the same shortfall also
hits G0-A's exact-branch source, rung 3's retention test, learned probe selection, and §4.5's third
recall metric. **They share a failure mode and are not currently priced as sharing one.**

**The local game fork is the only alternative source, and it is unscheduled.** All 25 public games ship
as runnable Python (`data/environment_files/`, on disk) and `arcengine` is on PyPI. Forking dev-partition
game state produces exact successors for every candidate — which is precisely the 7–8 rows' missing
input. Constraints in [`screening-training-data.md` §5b](screening-training-data.md): licensing
(bucket 2), version fidelity vs the platform, and above all **leakage** — this is oracle data on the
public set, so §13.5's dev-only rule binds and evaluation-only uses are far safer than training uses.

**The 3–4 band is not free, it is scheduled.** Nine artifacts depend on the procedural suite that gets
written Jul 29 – Aug 3. If S2 slips or ships a narrow generator, those nine degrade together.

---

## The three actions this table argues for

1. **Price the counterfactual budget once, across all six consumers** — not per component. Today
   §13.1 allocates branching slots to disagreement audits, ACTION6, and irreversible/OOD, and the
   learned gate's \(n_{causal}\) is the only requirement stated against it. Rung 3, G0-A's exact
   source, probe selection and causal coordinate recall draw on the same pool without a stated share.
2. **Decide the local-fork question before W1**, because it is the only lever that changes the 7–8
   band, and because deciding it late means the branching budget was designed against the wrong
   alternative set.
3. **Run the P(persistent change) pass** — it is the one remaining rating-2 row that is still
   uncounted, and it costs one pass over data already on disk.
