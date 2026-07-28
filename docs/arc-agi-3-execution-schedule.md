# Execution schedule — experiments and agent build

**Written 2026-07-28. Schedule only — this document re-decides no scope.** Where it disagrees with
[`arc-agi-3-implementation-spec.md`](arc-agi-3-implementation-spec.md) or
[`arc-agi-3-screening-experiments-and-results.md`](arc-agi-3-screening-experiments-and-results.md),
**it is wrong.** It operationalizes SPEC §12 and the screening document's §4 onto real dates, and
covers the one stretch neither of them does (Phase C).

Day-level allocation inside a build week is **derived here**, not given by the specification; SPEC §12
assigns steps to weeks and nothing finer. Week assignments, gates and the slack policy are the
specification's and are reproduced, not re-decided.

Budget assumption throughout: **40–50 h/week, ~5 focused days/week.** Calendar days that are not
focused days are where overrun absorbs.

---

## 1. The spine

| Date | Day | What |
|---|---|---|
| **2026-07-28** | Tue | today — S2 begins |
| 2026-08-12 | Wed | sprint work complete on plan (12 focused days from today) |
| **2026-08-22** | Sat | **sprint hard stop** · Fork G-F decided (SPEC §9.6) |
| **2026-08-24** | Mon | **build W1 begins** |
| 2026-09-06 | Sun | end W2 — *functionally submittable agent* exists |
| 2026-09-13 | Sun | end W3 — *budget-credible two-rate agent* exists |
| 2026-10-18 | Sun | end W8 · **feature freeze** |
| 2026-10-26 | Mon | Kaggle entry + team-merge deadline *(entry already satisfied by S0)* |
| **2026-11-02** | Mon | **final submission, 23:59 UTC** |
| 2026-11-08 | Sun | paper deadline (official) |

**Three phases:** A — sprint remainder (Jul 28 → Aug 22) · B — build (Aug 24 → Oct 18) · C — the tail
(Oct 19 → Nov 8), which SPEC §12 does not reach.

---

## 2. Phase A — sprint remainder · Jul 28 → Aug 22

12 focused days of budgeted work, landing **Wed Aug 12**, leaving **7 weekdays of float** before the
Aug 22 hard stop. That float is real and already has claims on it (§6).

### Before anything: the S2 pre-registration blocker

`gate_manifest.yaml → s2` is `NOT_STARTED`. The standing convention is that numbers enter the manifest
**before** the step they govern. S2 cannot legitimately start until it carries: the value /
distance-to-goal criterion per family · the three-ceiling margins validating F1 · F3's delay length and
bit sparsity · the frame-sequence length distribution the generators emit · and the **four numeric
criteria of SPEC §12.1 step 0** — generator throughput, held-out instance count, instance diversity
per family, procedural progress-event prevalence. Step 0's acceptance reads exactly these registered
values, so writing the manifest and defining the gate are one task, not two.

This collides with **open item 1** — SPEC §13 predeclares its own constants under its own freeze rule,
so two pre-registrations currently claim the role. **Resolve the ownership question before writing s2
numbers**, or the same conflict recurs at every subsequent block.

| Day | Date | Work | Done means |
|---|---|---|---|
| A1 | Tue Jul 28 | Resolve pre-registration ownership (open item 1). Write and freeze `s2`. Draw the **blind re-rate** sample from the 75-episode corpus | `s2` block `frozen`; re-rate sample drawn and blinded |
| A2 | Wed Jul 29 | S2 — F1 generator: aliasing mechanic, **variable-length frame sequences**, ARC conventions (64×64, values 0–15, per-game action availability) | F1 emits, conventions asserted in a test |
| A3 | Thu Jul 30 | S2 — F1 three ceilings: observation-only · history-oracle · hidden-state-oracle | required pattern observed, or task declared not history-resolvable |
| A4 | Fri Jul 31 | S2 — F3 generator: sparse delayed causal memory at the pre-registered delay and bit sparsity | F3 emits; delay verified by construction |
| A5 | Mon Aug 3 | S2 — generator interface complete **to SPEC §4.9, which governs**: legal actions · exact successor · terminal predicate · **evaluation-only** value criterion · hidden state · causal-relevance labels · recoloured/relaid variants with colour roles permuted · **ground-truth state IDs** · **instance seed + random-stream control, CRN declared not assumed** · **on-demand generation**. Methods prose | every §4.9 interface item present; S4 needs no re-engineering |
| **A5-G** | Mon Aug 3 | **SPEC §12.1 step 0 — procedural-suite acceptance.** Six criteria (§4.9): throughput · held-out instance count · instance diversity · progress prevalence — each against its registered value — plus generator correctness (F1's three-ceiling pattern on registered margins; F3's delay verified by construction) and observation fidelity (every row of the measured convention table, including the frame-length distribution) | **pass recorded, or unmet criteria named** — on failure, W1's non-dependent substrate continues while **D0 and all procedural-dependent work are blocked**, recorded untested, never passed |
| A6–A10 | Tue Aug 4 – Mon Aug 10 | **S3 — objective screening.** Six configurations (A/B/C × rollout), two paired seeds, matched information and matched ranking interface. Symmetric degeneracy monitoring | five screening questions answered with pre-registered metrics |
| A11–A12 | Tue Aug 11 – Wed Aug 12 | **S4 — ARC advisor test.** Held-out games, frozen advisor interfaces. **Local paired control** (advisor on/off), **replicates mandatory** | retention verdict on rungs, stated at local-public scope only |
| — | Thu Aug 13 – Fri Aug 21 | **float, 7 weekdays** — see §6 for its claims | |
| A13 | Fri Aug 21 | **S5 — decision audit.** B/M/U/C. Stop implementing | four axes recorded; SPEC §3/§12 amended via the decision register |
| — | **Sat Aug 22** | **Fork G-F decided.** Branch A if ≥ 5 build-days slack → build F4 ordered-event-program and F5 cumulative-counter families. Branch B otherwise → family transfer declared untestable and reported | one branch recorded in the register |

**S3 is the long pole and it is compute-bound, not thinking-bound.** Measured locally: 21.2M parameters
at 7.22 steps/s, 7.54 GB; twelve runs at 100k steps ≈ **46.2 h** against a 120 h budget. Over five
focused days that is ~9 h/day of GPU, so it must run unattended overnight and cannot contend with other
local GPU work. **Start the first training runs on A5, not A6** — the generators are ready a day before
S3 formally opens — but **only once A5-G passes.** Training on an unaccepted generator spends GPU
hours that step 0 may invalidate, and S3 has no slack to repeat them.

---

## 3. Phase B — the build · Aug 24 → Oct 18

Steps, week assignments and gates are SPEC §12.1's. The "focus" column is derived.

| W | Dates | SPEC step | Focus | Gate / milestone |
|---|---|---|---|---|
| **W1** | Aug 24–30 | 1, 2 (start) | harness · deterministic replay · scored-action accounting · **latency table — environment-step row only; the evaluator row waits for W3 and the executive row for D0, so the table is partial by construction and completed later** · **branching v0 — instrumentation only, emits no labels; reports \(yield_{mech}\), not \(yield_{valid}\) (SPEC §4.2)** · terminal-transition logging | **D0 — blocked if step 0 failed** · **public-game partition frozen (17 dev / 8 validation)** · reset-accounting confirmation on a second game (§4.1) |
| **W2** | Aug 31–Sep 6 | 2, 3 | canonicalizer + delta compiler · archive (immutable evidence + versioned projections, atomic single-active swap) · **branching v1 admitted once projections exist — first version permitted to emit labels (SPEC §4.2)** · ACTION6 generators + three recall metrics · minimal hypothesis store · direct executive policy with full I/O contract | **→ functionally submittable agent.** First entrant-authored payload; closes the DEGRADED branch |
| **W3** | Sep 7–13 | 4, 5 | evaluator 4a factual heads (incl. three-valued reversibility) · 4b weak value · two-stage gate · pre-R1 autonomy envelope · adaptive τ · portfolio arbitration v1 · shadow instrumentation | **→ budget-credible two-rate agent.** Step-5 target: ≥ 40% executive-call reduction. **This is the ablation baseline for W8** |
| **W4** | Sep 14–20 | 6, 7 (start) | full ledger · contradiction-triggered projection splitting · probes · **R1 branching round on dev partition** | **R1** · \(n_{causal}\) feasibility decision (≥ 800 valid states, or causal tier declared unfundable and logged) · cost-side re-anchoring window |
| **W5** | Sep 21–27 | 7, 8 (start) | R1 analysis → evaluator v2 → **envelope retired** · deterministic-gate calibration · complete procedural τ sweep, two operating points selected · belief rungs 1–3 | **R0** · G0-R runs opportunistically and **may not delay R0 or gate work** |
| **W6** | Sep 28–Oct 4 | 8, 9 | **verified partial programs** · portfolio rows 1–2 armed · rungs 4–5 each gated · portfolio row 3 · **R2** | **R2** (continuation v2 = evaluator-only, for ranker attribution) |
| **W7** | Oct 5–11 | 10 | **G0-A** with declared outcome sources · G0 decision per §9.7 · **public-validation paired runs** at both operating points, veto-only | **G0** — integrate recognizer + ranker / recognizer only / neither |
| **W8** | Oct 12–18 | 11 | ablation of every component **against the step-5 agent**, both regimes · **R3** · removal of what does not pay · freeze the thin fallback | **Feature freeze Oct 18** |

**The guarantee, restated from SPEC §12.1:** the calendar guarantees steps 1–5. Tier-3 maturation is
best-effort, governed by the component gates and the slack policy. *Degrade by deleting components,
never by compressing the submission.*

---

## 4. Phase C — the tail · Oct 19 → Nov 8

**SPEC §12 stops at Oct 18 and calls it "submission"; the competition's final submission is Nov 2.**
That is 15 days with no owner — [open item 2](README.md) in the index. This phase is **proposed, not
binding**, and needs an operator decision before it means anything.

| Window | Dates | Proposed |
|---|---|---|
| **C1 — tuning** | Oct 19–25 | No new components. Operating-point selection, τ, candidate budgets, governor thresholds. Every submission an ablation row (~5 slots at 1/day) |
| **C2 — hardening** | Oct 26–Nov 1 | Offline bundle verification, sandbox rehearsal, failure-path rehearsal (rejected submission, timeout, OOM). **Kaggle entry/team-merge deadline Oct 26 — already satisfied by S0, verify nothing has lapsed** |
| **C3 — submit** | **Nov 2** | Final submission, 23:59 UTC. **Two final submissions available** — plan both, do not discover the second slot on the day |
| **C4 — paper** | Nov 3–8 | Assemble from `paper/methods/` written throughout, plus the ablation table accumulated from the ledger. **Nov 8 official deadline; ties favour the earlier entry** |

The two readings to choose between: *(a)* Oct 18 is feature freeze and C1–C2 are tuning as the project's
other dates assume, or *(b)* SPEC §12 absorbed the tuning window and Oct 18 is the real submission with
Nov 2 as reserve. **(a) is the reading the rest of the project is written against**, and the
"reserve the final ~3 weeks for tuning" line predates the spec. Recommend adopting (a) explicitly and
amending SPEC §12's header to say its scope ends at freeze.

---

## 5. Compute and submission — the two hard resources

### GPU

| When | Load | Note |
|---|---|---|
| Aug 3–10 | **S3 ≈ 46.2 h** — 12 runs × 100k steps, 21.2M params, measured 7.22 steps/s | against a 120 h budget; must run unattended, cannot contend with other local GPU work |
| Aug 11–12 | S4 paired replicates, advisor on/off | replicate count is unregistered — **set it before S4 starts** (§6) |
| W4, W6, W8 | R1 / R2 / R3 branching rounds, dev partition | budget caps **attempted** actions: 24,000/game/round, 3 rounds |
| W7 | public-validation paired runs | 8 validation games × 2 seeds × 2 operating points, veto-only |

### Kaggle submissions — 1/day, 2 final

Roughly **59 slots** between Aug 24 and Oct 18, plus ~11 in Phase C. Under a 1/day quota a rejected
submission costs a **day**, not an hour. Load-bearing dates:

| When | Submission | Why it cannot slip |
|---|---|---|
| End W2 | first entrant-authored payload | closes the DEGRADED branch and restores S5's B axis; every later submission is measured against it |
| End W3 | step-5 agent | this is the **ablation baseline** for W8 — it must exist on the leaderboard, not only locally |
| W7 | both operating points | G0 and the gate calibration both read from these |
| Nov 2 | **both final slots** | plan two distinct payloads; do not spend the second on a retry of the first |

Every submission gets a ledger row: ID · commit · config diff · **the ablation it represents** ·
hypothesis · result. A row with an empty ablation cell is a lapse, not an exception.

---

## 6. Float, and what has a claim on it

**7 weekdays** exist between Aug 12 and Aug 22. Claims, in priority order:

1. **Replicate counts for S3 and S4.** The measured 36% run-to-run noise floor makes single-run
   per-episode comparisons uninterpretable. An unreplicated S4 yields a retention decision
   indistinguishable from a coin flip — **worse than no measurement, because it would be reported as
   one.** The count is still unregistered; register it, then buy it with float.
2. **The blind re-rate**, scheduled A1. The three-run instability (75% → 53% → 27%) is currently
   unexplained — real variation or rating artifact is undecided, and the re-rate is what decides it. If
   it slips, S1-d's ranking carries no agreement statistic into S5.
3. **Fork G-F Branch A** needs ≥ 5 build-days of slack measured at Aug 22. Float spent in Phase A does
   not count toward that; the fork reads *build* slack.
4. **Entrant-authored payload** brought forward from W2, if a submission slot is otherwise idle.

If float is absorbed by overrun rather than by 1–3, that is a **descope of decision quality**, and it
should be recorded as one in the register rather than noticed later.

---

## 7. Descope ladder — SPEC §12.2, mapped to dates

Any slip ≥ 1 week deletes, **in this order**:

| # | Deleted | Realistic trigger date |
|---:|---|---|
| 1 | Tier-4 production integration (G0-R diagnostic always continues — it is analysis of logged data) | W7 |
| 2 | G0-A evaluation | W7 |
| 3 | Rungs 4–5 | W6 |
| 4 | Fork G-F Branch A → falls to Branch B | Aug 22 |
| 5 | R3 | W8 |
| 6 | Public validation reduced to one operating point | W7 |

**Verified partial programs are never deleted before rungs 4–5** — they offload the executive with less
scientific uncertainty, which is why SPEC §3 orders them first inside Tier 3. **Steps 1–5 are never
compressed; they are the submission.**

---

## 8. Long-lead items — start before they are due

| Item | Needed by | Start by |
|---|---|---|
| Pre-registration ownership (open item 1) | S2 Day 1 | **today** |
| Blind re-rate sample + rating | S5's B/M axes | **today** (A1) |
| S3/S4 replicate counts registered | A6 / A11 | A1–A2 |
| Public-game partition (17 dev / 8 validation) | W1 step 1, frozen | before W1 — **drawn before step 4, never backfilled** |
| **Procedural-suite acceptance (SPEC §12.1 step 0)** | **A5-G, Mon Aug 3** | **gates D0; its four numeric criteria are the `s2` pre-registration, so they land on A1** |
| Entrant-authored payload | W2 | may be pulled into Phase A float |
| Offline bundle + sandbox rehearsal | C2 | W6 — do not first attempt this in November |
| `paper/methods/` prose | Nov 3 | continuous — written the day each thing is built |

---

## 9. Critical path

```
S2 generators ──► step 0 acceptance ──► S3 objective screening ──► S4 advisor test ──► S5 audit ──► SPEC amendment
   (A2–A5)            (A5-G)   │              (A6–A10, 46 h GPU)      (A11–A12)      (A13)        (Aug 22)
                               └──► gates D0 in W1
                                                                                    │
                                              ┌─────────────────────────────────────┘
                                              ▼
  W1 substrate + D0 ──► W2 archive + executive ──► W3 evaluator + gate ──► [SUBMISSION FLOOR]
                              │                          │
                              └── submittable agent       └── budget-credible agent, ablation baseline
                                                                     │
                        W4 R1 ──► W5 R0 ──► W6 programs + R2 ──► W7 G0 ──► W8 ablate + freeze
                                                                                    │
                                                        C1 tune ──► C2 harden ──► Nov 2 submit
```

**Nothing after W3 is on the critical path for having a runtime-viable submission.** That is the
property the whole ordering exists to preserve, and it is what makes the descope ladder safe to use.
