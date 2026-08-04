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
| [`arc-agi-3-jepa-feasibility-analysis.md`](arc-agi-3-jepa-feasibility-analysis.md) | Can the design work? Source of the **Delay risk** — the central argument against reconstruction-free prediction |
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

## Reading the identifiers

Short prefixes are reused across unrelated axes. Three of them had genuinely collided by 2026-07-29
and were renamed (erratum `S1-E17`, plus the family rename the same day); the rest are distinguished
**only by their qualifier**, so the rule below is load-bearing rather than stylistic.

| Prefix | Axis | Values |
|---|---|---|
| `S0`–`S5` | screening sprint stages | S0 starter · S1 baseline · S2 suite · S3 objectives · S4 advisor · S5 audit |
| `W1`–`W8` | build weeks | Aug 24 → Oct 18 |
| `A1`–`A13` | **schedule days inside Phase A** | A1 = Tue Jul 28 … A5-G = the step-0 gate |
| `V1`–`V15` | verification items | `gate_manifest.yaml → verification` |
| `S1-E1`–`S1-E17` | errata against the frozen `s1` block | append-only |
| `D0` · `R0` · `G0` | **gates** | executive viability · belief-model viability · goal induction |
| `DEV-1`–`DEV-13` | permitted deviations from the vendored reference | *(was `D1`–`D13`; collided with gate `D0`)* |
| `REPLAY-DET`, `RESET-ACCT` | the S1 reset experiment | *(was `R1`, `R2`; collided with the branching rounds)* |
| `R1`–`R3` | **branching rounds** on the dev partition | W4 · W6 · W8 |
| `ALT-1`–`ALT-9` · `REQ-1`–`REQ-8` | design alternatives · design requirements | **local to [`architecture-alternatives`](arc-agi-3-architecture-alternatives.md)**; nothing cites them from outside |
| `Alias`, `Delay` | procedural generator families | history-required aliasing · sparse delayed causal memory |
| `Order`, `Count` | Fork G-F families, Branch A only | ordered-event-program · cumulative-counter |

### The letter axes — five different things called "A"

These are **not** renamed. They are always written with their qualifier, and that is the whole
convention:

| Written | Means |
|---|---|
| **arm** A / B / C | S3 objectives — latent · reconstructive · exact-delta |
| **Track** A / B | research architecture · deployed score-oriented agent |
| **Branch** A / B | Fork G-F — build the extra families · declare transfer untestable |
| **Phase** A / B / C | calendar — sprint remainder · build · the tail |
| **A**\<n\> | a Phase-A schedule day |

> **Never drop the qualifier outside the section that defines it.** `gate_manifest.yaml` and the
> execution schedule each carry four of these five axes. §8 of the screening document writes bare
> `A`/`B`/`C` for the S3 arms and that is fine *there*; anywhere else it is ambiguous.
>
> **One overlap has no qualifier to lean on:** S5's audit axes are `B/M/U/C`, where **B** is baseline
> readiness and **C** is feasibility — *not* the reconstructive and exact-delta arms. Always write
> the whole string `B/M/U/C`; never a bare `B` or `C` for an audit axis.

`F1` now means only the **classification metric**, and is written `F1 score`. It is no longer a
family name — see the family rename of 2026-07-29 and
[`docs/archive/README.md`](archive/README.md) for reading the pre-rename documents.

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
revisit_outcome: >
  NOT TRIGGERED — checked 2026-07-28 against the completed blind re-rate
  (logs/s1d_rerate_result.json, gate_valid). goal_unknown's primary-label kappa is
  0.7945 over 30 episodes: rating the SAME episode twice, blind, reproduces the
  primary label most of the time. That bounds the rating-noise channel and leaves
  the 75/53/27 cross-run swing pointing at real run-to-run variation, which is the
  reading the decision already assumed. It does not SETTLE the question — kappa is
  measured within one rater on one evidence slice, and goal_unknown's any-label
  kappa is a much weaker 0.5161 — but the condition for revisiting is not met and
  the decision stands unchanged.
effective_spec_sections: ["§3", "§9", "§9.7"]
approved_at: 2026-07-28
```

```yaml
decision_id: DOCS-TAXONOMY-2026-07-28
question: >
  where does the ten-class goal-predicate taxonomy live, now that its only definition
  site is archived, and what governance status does it have
evidence:
  - artifact: docs/archive/arc-agi-3-agent-architecture.md   # former §5.2, archived 2026-07-28
  - artifact: agent/harness/s2_apply_labels.py               # TAXONOMY, enforced as a closed set
  - artifact: logs/quarantine/s2-superseded-worksheet-2026-07-28/  # the pass-1 labelling that ran against it, since quarantined
decision: relocate_unchanged_as_evidentiary
detail: >
  The list was defined only in an archived document and in code, while archive/README.md
  says archived documents must not be cited — leaving a closed, pre-SPECIFIED codebook
  with no citable definition. It is relocated UNCHANGED into the screening document's
  evaluation-apparatus appendix, beside the other definitions folded out of the same
  archived file by DOCS-2026-07-28. Governance status is EVIDENTIARY, not normative: the
  specification neither defines nor references it, so it is not a spec instrument and no
  spec amendment is due. It binds S2's labelling only. A first draft of this relocation
  created a standalone document that self-declared itself "LIVE and authoritative"; that
  overstated its status and broke the one-document-per-decision-horizon rule, and was
  withdrawn in favour of the appendix.
effective_spec_sections: []          # none — deliberately not a spec change
approved_at: 2026-07-28
status_precision: >
  PRE-SPECIFIED CLOSED CODEBOOK, not a pre-registered instrument. It was fixed before any
  S2 labelling and is unchanged since. `gate_manifest.yaml -> s2` is now DRAFT, but explicitly
  lists the goal-predicate extraction as prior work not governed by that block and does not adopt
  this taxonomy. Calling the codebook "pre-registered" would therefore still credit it with
  authority the pre-registration mechanism has not conferred. An earlier draft of this entry did
  exactly that.
deviation_recorded: >
  S2 frequencies computed against this codebook inherit the DRAFT S2 pre-registration as a stated
  limitation, and must say so wherever they are reported. The codebook becomes a frozen instrument
  — with the "adding a class needs a dated erratum" rule in force — only if a frozen manifest block
  adopts it.
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
  reset posture as an open item, but S1's REPLAY-DET/RESET-ACCT measured the answer on
  2026-07-26. Which regime binds, and what does it settle about branching?
evidence:
  - experiment: S1 — REPLAY-DET knowledge preservation, RESET-ACCT action accounting
  - artifact: gate_manifest.yaml       # replay_determinism, reset_accounting
  - artifact: logs/replay_determinism.json
  - artifact: notes/s1-closeout.md
  - finding: >
      REPLAY-DET = deterministic (ft09, ls20; prefixes 10 and 40; 3 replays each;
      byte-identical, falsification check passed — grids genuinely vary within
      a replay). RESET-ACCT = accumulates, r = 2.0357, c_reset = 1 measured: wasted
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

```yaml
decision_id: BRANCH-V0-2026-07-28
question: >
  §12.1 schedules the branching primitive in step 1 (W1) and the archive's
  versioned projections in step 2 (W1-2). But §4.2 verifies a reconstruction
  over (observation hash, inferred context signature, history equivalence
  class), and the latter two are step-2 artifacts. What does a step-1 branch
  do, and may its output be trusted?
evidence:
  - artifact: docs/arc-agi-3-implementation-spec.md    # §4.2, §4.4, §12.1
  - artifact: notes/build-difficulty.md
  - finding: >
      §4.2 states that final-hash match alone is insufficient and that mismatch
      INVALIDATES the branch. A step-1 implementation has only a hash, so it
      cannot perform the check the section requires. The failure is silent:
      hash-only branches emit plausible Y_useful labels that are
      indistinguishable downstream from sound ones, and §6.8's label is the
      sole basis for any learned-gate claim.
decision: branch_v0_instrumentation_only
detail: >
  Step 1 builds branch v0: prefix recording, deterministic replay, reset,
  candidate execution and K-step outcome capture. v0 is BARRED from emitting
  training labels — its branches never enter §6.8's label set. Label-bearing
  branching (v1) requires §4.4's identity layer and is unblocked at step 2.
  v0's yield accounting is PARTIAL and is named separately for that reason.
  Two of the seven invalidity reasons — context mismatch and projection change —
  are detectable only against a projection, which is why final-hash match was
  declared insufficient in the first place. v0 therefore reports yield_mech over
  the five mechanically detectable reasons (stochasticity, animation timing,
  reset behaviour, unavailable prefix, action nondeterminism), and that figure
  is an UPPER BOUND on valid yield, never an estimate of it. yield_valid — the
  quantity §13.1's n_causal feasibility decision reads — is defined only for v1
  and measured at R1.
  This is close to free. §12.1 already places R1, the first branching round
  that produces labels, at step 6 (W4) — four steps after the identity layer
  lands. The amendment therefore makes an existing implication ENFORCEABLE
  rather than incidental, and changes no predeclared number: §13.1's 24,000
  attempted actions per game per round and the R1-R3 schedule are untouched.
  §12.1 now shows the split in the table itself — v0 in step 1, v1 admitted in
  step 2 alongside the projections — so the dependency is visible in the build
  order rather than only in §4.2's prose.
rejected:
  - move_minimal_projection_identity_into_step_1   # see below
rejected_because: >
  It front-loads the highest verification-risk component into the week that
  already carries D0 and the latency table, and a "minimal" identity that is
  revised later makes every v0 branch retroactively questionable — the same
  silent-contamination problem relocated rather than removed.
effective_spec_sections: ["§4.2", "§12.1"]
approved_at: 2026-07-28
```

```yaml
decision_id: S2-GATE-2026-07-28
question: >
  §4.9 makes a working procedural suite a build step-1 precondition — §10.1
  measures D0 on held-out procedural environments — yet §12 opens W1 with no
  check that the suite exists or works, and §12.2's slack policy governs only
  later features. What happens if S2 delivers late or degraded?
evidence:
  - artifact: docs/arc-agi-3-implementation-spec.md    # §4.9, §10.1, §12.1, §12.2
  - artifact: docs/arc-agi-3-screening-experiments-and-results.md   # §7
  - artifact: notes/build-difficulty.md
  - finding: >
      D0 plus FOUR of the seven Tier 2 components depend on the suite: the
      evaluator (§5's progress supervision), the gate and envelope (§6.4's ECE
      clause and §6.3's acceptance region — both belong to this one component),
      the adaptive controller (§13.1's tau bounds and q_hi/q_lo) and the
      paired-run estimators (§6.6). An earlier count said five by listing the
      gate's two dependencies as separate components. Four of the five quantities an
      acceptance check would read are already listed as UNREGISTERED in §4.9.
      Separately, S2's 3.5-day budget predates three interface requirements
      added by §4.9 on 2026-07-28 and has not been re-examined.
decision: build_step_0_at_w0
detail: >
  S2 is a pre-build Tier 1 phase and §12.1 did not show it. The build order
  gains **step 0 at W0** — the procedural suite built and accepted during S2 —
  rather than a milestone hanging off the side of W1, because the suite is a
  Tier 1 component that is genuinely BUILT there, not merely checked. Nothing
  else deployable exists before W0: the rest of what the sprint leaves behind is
  measurement scaffolding around the vendored reference, which never ships.
  SIX acceptance criteria in two kinds. Four are NUMERIC and are exactly the
  quantities §4.9 lists as unregistered — throughput, held-out instance count,
  instance diversity per family, progress-event prevalence — so acceptance and
  pre-registration are ONE piece of work, both landing in gate_manifest.yaml
  -> s2 before S2 runs. Two are STRUCTURAL with stated pass conditions:
  generator correctness (Alias's three-ceiling pattern on the registered margins;
  Delay's causal delay verified by construction) and observation fidelity (every row of
  the measured convention table, including the frame-length distribution).
  An earlier draft listed five criteria that did not match the table it claimed
  to read: progress prevalence was in the table and not in acceptance, and the
  two structural criteria had no pass definition.
  Step 0 sits OUTSIDE §12's "the calendar guarantees steps 1-5" — it is
  delivered by the sprint, so a slip arrives as a W1 problem and §12.2's
  deletions cannot absorb it.
  On failure the response is reporting, not improvisation: the unmet criteria
  are named, and every D0 threshold that depends on held-out procedural
  environments is recorded as UNTESTED rather than passed — consistent with
  §10.1 freezing thresholds before results are inspected, and with §13.5's
  habit of reporting rather than silently backfilling.
open: >
  FAILURE BRANCH, binding: reporting a failure does not discharge the
  dependency, so the response is declared rather than improvised. W1's
  non-dependent substrate continues — harness, accounting, replay, terminal
  logging, the §13.5 partition — while D0 and every procedural-dependent item
  are BLOCKED. Blocked means not attempted: a D0 threshold reading held-out
  procedural environments is recorded UNTESTED, never passed.
  What that blockage costs the calendar is open item 6, its own item — it is
  not the October calendar tail of open item 2, and an earlier draft wrongly
  deferred it there.
revisit_if: >
  S2's budget is re-priced against the §4.9 interface, which may change what
  step 0 can reasonably demand.
effective_spec_sections: ["§4.9", "§12.1", "§12.2"]
approved_at: 2026-07-28
```

```yaml
decision_id: ES-GOV-2026-08-03
question: >
  GI-2 §3.4 (frozen 2026-07-30) permanently stopped goal-inference-from-replay-evidence
  after its second gate failure, and VP §2 made a VP4b pass the only route that prices
  reopening. The completed VP1 measurement (288/288 rows; best pure-image marked-cell
  game-macro 0.438 against the 0.90 gate, global counting failed in every tested channel)
  forecloses the conditional VP3/VP4 stages and with them the VP4b pricing case. May the
  ES protocol — closed-set candidate-goal discrimination plus a conditional advisor
  trial, across Qwen 27B generations — run anyway?
evidence:
  - artifact: notes/gi2-grounded-binding.md          # §3.4/§3.5 — the stop and what forced it
  - artifact: notes/vp-perception-screen.md          # §2 governance; Freeze 1 VP1 result
  - artifact: notes/qwen-evidence-sufficiency-screen.md   # the ES protocol
decision: prospective_es_only_supersession
detail: >
  Operator decision of 2026-08-03, recorded in the ES note's header: the §3.4 stop and
  VP §2's VP4b-only route are prospectively superseded FOR ES ONLY. Grounds: both prior
  failures were failures of a frozen observation grammar's coverage and of unmeasured
  identifiability, and ES makes grammar coverage and replay identifiability measured,
  gated prerequisites before any model claim. The decision does not reinterpret either
  prior result, does not amend VP Freeze 1, opens no sealed game, and authorizes no
  production integration. Numeric authority for ES is gate_manifest.yaml -> es (DRAFT;
  acceptance precedes any ES-specific implementation). Dated cross-reference addenda
  are appended to both prior records (gi2-grounded-binding.md §10,
  vp-perception-screen.md §15) without rewriting their frozen text.
prospective_mapping: >
  ES evidence maps to SPEC §9.7 only as grounds for RECONSIDERING the scope of the
  committed goal artifact — §9.7 currently reads "executable predicate induction
  remains unscheduled Tier 4". An ES pass changes nothing by itself: adoption into
  Track B requires a new entry in this register plus a dated amendment to §9.7, and
  ES evidence does not satisfy or override G0-R/G0-A.
effective_spec_sections: []   # none — deliberately not a spec change; the §9.7 mapping is prospective
approved_at: 2026-08-03
```

```yaml
decision_id: SCHED-2026-08-03
question: >
  The Stage 0 sprint carries a hard stop of 2026-08-22 (gate_manifest.yaml -> meta.hard_stop;
  execution-schedule Phase A -> B boundary). ES ended coverage-blocked on 2026-08-03 with zero
  model calls spent (ES note §11), and its successor MU is a screen that selects an interface —
  it cannot itself establish a deployable capability. Does the Aug 22 hard stop still bind?
evidence:
  - artifact: notes/qwen-evidence-sufficiency-screen.md   # §11 — ES ends coverage-blocked
  - artifact: notes/mu-representation-screen.md           # the successor screen and its §5.1 contract
decision: hard_stop_lifted
detail: >
  Operator decision of 2026-08-03: the 2026-08-22 sprint hard stop NO LONGER BINDS. The
  screening line (VP -> GI-2 -> ES -> MU) has not yet established that any local-model
  capability usable by the agent exists; the binding objective is now to discover whether
  anything is possible at all, and ending discovery on a calendar boundary would decide that
  feasibility question by default rather than by measurement. Recorded in the manifest as
  errata META-E1 (meta.hard_stop keeps its frozen value, superseded); dated status notes in
  the execution schedule, the screening document §1, and CLAUDE.md; the mu block's
  cost_disclosure (DRAFT) updated in place.
unchanged: >
  Official external dates still bind: Oct 26 entry + team-merge, Nov 2 23:59 UTC final
  submission, Nov 8 paper deadline. The 1/day + 2 final submission quota is unaffected. The
  Oct 18 feature-freeze target and ~Nov 5 paper target are project-internal and are NOT
  re-decided here. The utility ordering (score primary) is unchanged — this reorders work,
  not objectives.
consequences: >
  The Phase A -> B boundary (Aug 22 / Aug 24) floats, so every figure derived from the
  Aug 24 -> Oct 18 build window (~8.4 weeks; "~59 submissions") compresses day-for-day as
  discovery extends — accepted knowingly: a build on a substrate with no demonstrated
  capability would spend that window on nothing. Fork G-F loses its calendar anchor: SPEC
  §9.6 "decided Aug 22" and §13.4 "≥ 5 slack days at Aug 22" were defined against the hard
  stop and now read "at sprint end", with the Branch-A slack criterion awaiting re-anchoring
  once a sprint end exists — re-anchoring (or defaulting to Branch B) is a separate decision,
  not made here. No re-anchored schedule exists yet; producing one is a schedule act pending
  the MU §5.1 outcome. Open items 2 and 6 keep their content; their calendar arithmetic
  floats with the boundary.
effective_spec_sections: ["§9.6", "§13.4"]   # calendar anchors only; decision rules unchanged
approved_at: 2026-08-03
```

```yaml
decision_id: MU-2026-08-03
question: >
  MU screened seven live-constructible interface bundles over the running game against five
  probes, on the six iteration games. Does any bundle let Qwen3.6-27B-8bit demonstrate mechanics
  understanding well enough to fund a goal-inference continuation?
evidence:
  - artifact: notes/mu-representation-screen.md          # protocol, §5.1 decision contract
  - artifact: notes/mu-representation-screen-results.md  # the measurement and its diagnostics
  - artifact: logs/mu_results.json                       # computed verdict, decision.verdict
  - artifact: logs/mu_freeze.json                        # 40fc3c5f34d72fe2… (MU-E1 supersedes a3e1f859…)
decision: stop
detail: >
  MU returns `stop` under its pre-registered §5.1 contract: no funding cell among {T3, T4} is
  screen-positive on the confirmation cohort. 492 measured calls, zero request errors, first-pass
  schema validity 1.000, 3.55 h GPU. The T1 legibility gate split the menu cleanly and
  unanimously across all six games — `verbal`/`card`/`events`/`objects` pass (0.896-1.000),
  `grid`/`film`/`map` fail (0.229-0.292) with `bbox` at 0.00 on 48 items each: the model cannot
  perform connected-component analysis on a 64x64 character grid, though it answers the same
  board almost perfectly once a computed object table accompanies it. Selection took `verbal`
  for T2/T3/T4 and `objects` for T5 — every legible arm sat inside the 0.09 margin, so the
  cheaper-arm rule decided it. On C each funding probe failed a DIFFERENT one of the two
  screen-positive requirements: T3 met per-game consistency (4/6) and missed the margin
  (+0.056 < 0.09); T4 met the margin (+0.167) and missed consistency (3/6). Either criterion
  alone would have returned `continue`; requiring both, fixed before any call, produced the stop.
  A reported diagnostic added after the S pass (and therefore deciding nothing) sharpens it:
  on T3 the selected arm scores 0.736, EXACTLY what a constant "unchanged" reply scores.
consequence: >
  No goal-inference continuation is funded. Advisor work on the mechanics axis proceeds
  programmatic-only (catalogue floors). Per §5.1's scope limits this is NOT a finding that Qwen
  is useless on this interface: a T2 or T5 component result remains reportable, and reopening one
  needs its own registered protocol. Adoption was never reachable from MU — it is offline and
  makes no score-stack claim.
limitations: >
  Conditional on the six iteration games; no unseen-game claim. §3's only matched-information
  pure-rendering contrast (`grid` vs `film`) died at the T1 gate, so MU says nothing about
  whether rendering format alone matters. T3-fork, T4 and T5 anchor only at completion
  pre-states (`mu -> decision.anchor_scope`), so control near a completion is what was measured.
  `card` was a <=4-sample catalogue, not the accumulated one a deployed advisor would carry.
  One methodological defect is recorded rather than repaired: the frozen T3 and T4 floors are
  WEAKER than the trivial constant-answer baseline, so the screen-positive test was easier to
  pass than it reads — conservative here, since the gate failed anyway. A future protocol should
  define each floor as the strongest trivial strategy available.
errata: ["MU-E1 (scorer/guided-schema contradiction, caught mid-pass; 214 rows re-scored, not
  re-collected, after 214/214 stimulus hashes reproduced)", "MU-E2 (post-measurement test edit)"]
effective_spec_sections: []   # none — MU is a screen; it defines no deployed component
approved_at: 2026-08-03
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
| 6 | **What a blocked D0 costs the calendar.** `S2-GATE-2026-07-28` fixes what *happens* on a failed step 0 — substrate continues, D0 and procedural-dependent work are blocked and recorded untested. It deliberately does not fix what that does to the schedule: D0 chooses the executive, which sizes the per-action budget and completes the latency table, so blocking it stalls more than step 1. Two options are available under the branch as written: **slip W1**, or **accept a late model choice** and carry the consequences into W3. A third is tempting and is *not* available — running a reduced D0 on its non-procedural parts (§10.1's licensing and GPU fit/throughput do not read procedural environments, only its capability thresholds do). Taking it means **amending `S2-GATE-2026-07-28`** to block D0's capability gate rather than D0 as a whole, because the branch currently says blocked means not attempted. That is a decision, not a clarification. **Distinct from item 2**, which is the October tail | any S2 overrun; the W1–W3 effort gap in SPEC §3.1 |
