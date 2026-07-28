# Project index and decision register

Start here. Two primary documents plus this index; everything else is rationale or archive.

## The two primary documents

| | Document | Role | Amendment rule |
|---|---|---|---|
| **Normative** | [`arc-agi-3-implementation-spec.md`](arc-agi-3-implementation-spec.md) | What the deployed agent **is**: component definitions and interfaces · tier membership · runtime arbitration · build order and slack policy · gates and production retention · predeclared tolerances · fallback behaviour | Dated amendment, logged in the register below. **Never amended implicitly by a result** |
| **Evidentiary** | [`arc-agi-3-screening-experiments-and-results.md`](arc-agi-3-screening-experiments-and-results.md) | How uncertain choices are **tested** and what happened. **Open it for orientation** — §1 is a status board: where every sprint stands, what it decides, what is blocking it. Then S0–S5 protocols and arms · results and what they constrain downstream · what still needs pre-registering · limitations · the S5 audit. Detailed numbers live in `notes/`; day-level dates in the execution schedule | Updated freely as measurement proceeds |

**Where they conflict, the specification governs until explicitly amended.**

```
experiments produce evidence  →  decision register (below) evaluates it
                              →  implementation spec is amended  →  code implements the amendment
```

The mapping between them is a table in each: SPEC §1.1 lists *decision → evidence source*; the
screening document's §2.1 is its inverse, *sprint → decision informed*. An experiment that maps to no
row is either infrastructure or should not be run.

## Supporting documents

| Document | Role |
|---|---|
| [`arc-agi-3-ship-jepa-x-architecture.md`](arc-agi-3-ship-jepa-x-architecture.md) | **Track A.** The belief model's internals — SPEC §11 specifies it only to admission level and defers the rest here. Also what S3's arms instantiate, and what the paper describes |
| [`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md) | Can the design work? Source of the **F3 risk** — the central argument against reconstruction-free prediction |
| [`arc-agi-3-architecture-alternatives.md`](arc-agi-3-architecture-alternatives.md) | What would work better. Ordinal judgments, not measurements |
| [`arc-agi-3-execution-schedule.md`](arc-agi-3-execution-schedule.md) | **Operational.** SPEC §12 and the sprint budgets on real dates, day-level for Phase A. Re-decides no scope — where it disagrees with the spec or the screening document, it is wrong. Phase C (Oct 19 – Nov 8) is proposed, not binding, pending open item 2 |
| [`archive/`](archive/) | Superseded or spent. **Not authoritative, do not cite** |

Pre-registration lives in [`../gate_manifest.yaml`](../gate_manifest.yaml) (append-only; changes need
a dated erratum). Session output and working analysis live in [`../notes/`](../notes/), never in a new
document here.

> **One document per decision horizon. New thinking amends an existing document or lands in
> `notes/`.** The doc count reached nine because each thinking session produced a file; that is the
> failure mode this rule exists to prevent.

---

## Decision register

One entry per binding change to the specification. A result becomes binding **only** by appearing
here and in a dated spec amendment — never by being written down in the screening document.

Entry format:

```yaml
decision_id: R0-2026-09-04
question: predictive objective for the belief model
evidence:
  - experiment: S3
  - artifact: results/s3-summary.json
decision: exact_sparse_delta
rejected:
  - reconstruction_free_latent
  - reconstructive_next_state
effective_spec_sections: ["§10.2", "§11"]
approved_at: 2026-09-04
```

### Entries

```yaml
decision_id: DOCS-2026-07-28
question: which document is authoritative now that a binding implementation spec exists
evidence:
  - artifact: docs/arc-agi-3-implementation-spec.md   # v1.2, self-declared binding
decision: split_authority_by_phase
detail: >
  Implementation spec is normative for the deployed agent and governs on conflict.
  The screening document is re-scoped to evidence and results; its component
  inventory (former §2) is withdrawn in favour of SPEC §3, and its claim to
  supersede architecture build orders is withdrawn. agent-architecture.md is
  archived; its four derivations are folded into SPEC §§2, 4.4, 4.5, 9, and its
  evaluation-apparatus definitions into the screening document's §16 appendix.
effective_spec_sections: ["§1.1"]
approved_at: 2026-07-28
```

```yaml
decision_id: G0-SCOPE-2026-07-28
question: >
  goal induction was ranked first among build targets on S1-d's single-run
  primary_share of 75%; the spec places G0 experiments in Tier 3 and production
  integration in Tier 4. Which ordering binds?
evidence:
  - experiment: S1-d, three runs of one byte-identical configuration
  - artifact: notes/s1d-cross-run-stability.md
  - finding: >
      goal_unknown primary_share (L2+) fell 75% -> 53% -> 27%; only 5 of 16
      (game, level) triples agree across all three runs. Real variation vs rating
      artifact is NOT yet established: the only re-rate is partial (17 of 25), not
      blind, primary labels only — consistent with real variation, cannot demonstrate
      it. goal_unknown remains the top POOLED category in all three runs (76/56/44%)
      with flat episode_share 76-92%.
decision: gate_not_build_order
detail: >
  The spec's ordering binds. A build order pinned to an unstable statistic is the
  failure mode; a gate with predeclared margins and a non-inferiority floor is the
  correct instrument, and this holds whichever explanation the blind re-rate supports.
  Goal inference remains the largest single lever — that is not in dispute — but it
  earns integration through G0 rather than inheriting priority.
revisit_if: the blind re-rate shows the instability is a rating artifact, not the agent.
effective_spec_sections: ["§3", "§9", "§9.7"]
approved_at: 2026-07-28
```

```yaml
decision_id: EVAL-SCOPE-2026-07-28
question: >
  SPEC §5 says "a modest shared grid encoder scoring only the common candidate
  set" without saying (a) whether the encoder runs per step or per candidate, or
  (b) what "shared" is shared with. Both change what gets built.
evidence:
  - artifact: docs/arc-agi-3-ship-jepa-x-architecture.md  # §5 config, §14 factorization, §20 budget
  - artifact: notes/evaluator-training-data.md
decision: per_step_dense_heads__separate_encoder_from_belief_model
detail: >
  (a) One encoder pass per STEP with dense heads over the spatial map; the
  coordinate head scores all locations at once per Track A §14's factorization.
  Evaluator cost is O(1) in candidate count; §2's (candidates x passes) product
  governs the belief model's rollout, not this component. Per-candidate encoding
  is non-conforming — ~40x cost at a typical budget.
  (b) "Shared" means across this component's own heads. The evaluator and the
  belief model have SEPARATE encoders. Forced by measurement integrity, not
  modularity: the evaluator ships at W3 trained on exact factual targets, and R0
  at W5 compares latent/reconstructive/exact-delta arms. A shared encoder would
  give every arm exact supervision and confound the comparison — the failure that
  arm C and S5's "auxiliaries carry the result" case exist to prevent.
effective_spec_sections: ["§5"]
approved_at: 2026-07-28
```

```yaml
decision_id: PARTITION-2026-07-28
question: >
  SPEC §5 and notes/evaluator-training-data.md both recommend drawing the §13.5
  17/8 public-game partition stratified by terminal-transition count. Is one
  criterion sufficient?
evidence:
  - artifact: logs/s2_corpus_census.json          # agent/harness/s2_corpus_census.py, full pass
  - artifact: notes/screening-training-data.md
  - finding: >
      the 17/8 draw moves five signals independently, and terminal count is the
      LEAST volatile of them. Dev-partition share, worst draw to best: no-op
      positives 21%-97%, ACTION6 transitions 22%-99%, discrete counterfactual
      pairs 32%-96%, total transitions 44%-87%, terminal transitions 53%-80%.
      Six games contain zero ACTION6 (g50t, ls20, re86, tr87, tu93, wa30) and
      five contain fewer than 50 no-ops, so a draw balanced perfectly on
      terminals can still strip four-fifths of the coordinate or no-op
      supervision.
decision: multi_criterion_balance_constraint
detail: >
  Draw under a joint constraint rather than one stratifier: terminal count,
  no-op count, ACTION6 count and total transitions each within a declared
  tolerance of the 17/8 proportional share, reject-sampled until all four hold,
  realized shares recorded. The tolerance itself is a pre-registered number and
  belongs in gate_manifest.yaml, not in the spec or a note.
effective_spec_sections: ["§5", "§13.5"]
approved_at: 2026-07-28
```

```yaml
decision_id: RESET-CASE-2026-07-28
question: >
  SPEC §4.1 offered three reset-accounting regimes and §14 still listed the
  reset posture as an open item, but S1's R1/R2 measured the answer on
  2026-07-26. Which regime binds, and what does it settle about branching?
evidence:
  - experiment: S1 — R1 knowledge preservation, R2 action accounting
  - artifact: gate_manifest.yaml       # r1_knowledge_preservation, r2_action_accounting
  - artifact: logs/r1_determinism.json
  - artifact: notes/s1-closeout.md
  - finding: >
      R1 = deterministic (ft09, ls20; prefixes 10 and 40; 3 replays each;
      byte-identical, falsification check passed — grids genuinely vary within
      a replay). R2 = accumulates, r = 2.0357, c_reset = 1 measured: wasted
      actions carry across resets AND RESET is itself a scored action.
decision: everything_scores__no_online_branching
detail: >
  c_reset = 1 falsifies both cheap-reset regimes — "reset free / scored only on
  a successful attempt" and "reset costs runtime, not score". The everything-
  scores regime binds: counterfactual data comes from procedural environments,
  replay reconstruction and development runs exclusively.
  Confirmatory for the predeclared numbers rather than a change — §13.1's
  branching budget is already written against the dev partition. It also
  ratifies the controller fork taken 2026-07-26 (surgical
  information-per-action, because every deployed probe costs score).
  §14's open item shrinks rather than closing: the regime is selected, its
  scope is not.
  Per the same-day cleanup, §4.1 now states only the surviving regime and no
  longer numbers the three; this entry is the record of what was rejected.
scope_limits:
  - offline competition environment files, NOT competition mode — V5-V7's
    hidden scorecard and one-make() restrictions are unexercised
  - the accounting rule rests on ONE game (tu93), single-game by design so the
    level weight cancels; cross-game generalisation untested, not asserted
revisit_if: >
  competition-mode accounting differs from offline, or step 1's re-scoped
  confirmation finds a second game accounting differently.
effective_spec_sections: ["§1.1", "§4.1", "§14"]
approved_at: 2026-07-28
```

---

## Open items requiring a decision

| # | Item | Blocking |
|---|---|---|
| 1 | **Two pre-registrations coexist.** `gate_manifest.yaml` has `s2`–`s5` as `NOT_STARTED` while SPEC §13 predeclares ~30 constants under its own freeze rule (§13.6: loss-side frozen now, cost-side re-anchorable once). Either the spec's numbers migrate into the manifest, or the manifest yields build-phase authority to the spec — but both currently claim the role | anything that cites a pre-registered number |
| 2 | **Calendar tail.** *(schedule §4 proposes a resolution — adopt reading (a), Oct 18 = feature freeze, and amend SPEC §12's header to say its scope ends there.)*  SPEC §12 ends at "submission Oct 18" with W8 closing Oct 16; the project's other dates treat Oct 18 as *feature freeze* with ~3 weeks of tuning before the Nov 2 final submission. Either the spec's scope ends at freeze, or the tuning window has been absorbed | S5 audit, and the final-submission plan |
| 4 | **Public-game partition — balance tolerance.** *(Draw method resolved by `PARTITION-2026-07-28`: multi-criterion, not one stratifier.)* What remains is the **tolerance** — how close to the 17/8 proportional share each of the four criteria must land before a draw is accepted. Frozen at build step 1, never backfilled | evaluator progress head · no-op head · G0 training data · click salience |
| 5 | **Replay redistribution.** `paper/methods/s2-human-replay-corpus.md` records the archive carries no licence and mirror declarations come from non-rights-holders. Training locally is not redistribution; **shipping weights trained on it inside a submission may be** — unanswered, and it touches the progress head, §4.5 click salience, and G0 | W3 onward |
| 3 | **The DEGRADED submission branch.** No entrant-authored payload exists, so S5's B axis has no score to read. SPEC step 3 (W2) produces one; until then the branch stands | S5's B axis |
