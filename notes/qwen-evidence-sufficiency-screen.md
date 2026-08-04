# ES — replay-evidence sufficiency across Qwen 27B generations

**Status: NUMERICS ACCEPTED AND FROZEN 2026-08-03 in `gate_manifest.yaml → es`.** The operator
accepted every PROPOSED value unchanged and directed the freeze; two derivation-bound fills — the
expression-depth bound and the `L_g` table — follow rules frozen in the manifest and land as dated
errata when measured. This note remains the governing protocol text; the manifest block is the
numeric authority. The protocol's own common freeze (`logs/es_common_freeze.json`, §6.2) is still
ahead and gates the first survivor set. This is a separate scientific protocol. It does not
retroactively amend `notes/vp-perception-screen.md`, its Freeze 1 contract, or its results; the
prospective ES-only governance supersession is recorded below.

**Status update — 2026-08-03, closeout: ES ends coverage-blocked before its common freeze; zero
ES-USE calls spent. See §11.** The paragraph above is retained as the frozen historical text.

Unless explicitly labelled as a measured inventory fact or prior frozen result, every numeric
choice in this note was **PROPOSED** until manifest acceptance; all were accepted unchanged on
2026-08-03.

**Operator decision — 2026-08-03.** The direction to run the full G36 experiment now and repeat its
locked model-dependent design on G38-27B prospectively supersedes GI-2 §3.4's permanent stop and
VP §2's VP4b-only reopening route **for ES only**. The justification is that ES makes grammar
coverage and replay identifiability measured prerequisites before any model claim. This decision
does not reinterpret either prior failure, alter VP Freeze 1, open reserved or one-shot games
outside the 18 selected sessions, or authorize production integration. It authorizes `ES-IDENT`,
`ES-USE`, and conditionally earned `ES-VALUE` under this separately capped protocol. Before any
ES-specific governed implementation begins, dated cross-reference addenda must be appended to the
GI-2 and VP records without rewriting their frozen historical text. A later production change has
the separate register/specification requirements in §8.

## 0. Decision context

All 288 VP1 rows are now complete and the frozen Qwen3.6 visual route fails. Pure-image I-4/I-8/I-16
reach only 0.129/0.296/0.438 marked-cell accuracy and 0.125/0.104/0.104 exact-patch accuracy. The
I-A text and I-H hybrid controls recover local detail (0.821/0.750 marked-cell and 0.782/0.743
patch-cell) but still fail global measurement (pixel-band 0.208/0.458; component-band
0.250/0.271). Global counting is therefore not rescued by any tested channel.

Those results support one narrow, model-specific conclusion: Qwen3.6 should not be asked to recover
exact global state from the current full-board image interface. They do **not** show that replay
evidence is insufficient for goal inference, and they do not pre-judge Qwen3.8 vision. The common
core therefore uses structured packets and asks only three large questions:

1. Does the recorded replay distinguish the authored goal from a bounded, evidence-blind
   hypothesis universe without using a model?
2. When it does, can Qwen use the evidence, and which structured sidecar materially helps?
3. Can the winning non-oracle packet and hypothesis generator improve an agent on an untouched
   operational evaluation?

Everything else is supporting validation, not a separate experiment.

The execution policy is deliberately two-generation:

- **G36 baseline now:** run the complete governed experiment with Qwen3.6-27B. Its result is final
  and actionable; a pass may advance through `ES-VALUE` and become eligible for an adoption
  decision without waiting for Qwen3.8.
- **G38 locked replication later:** after the announced Qwen3.8-27B checkpoint is released and
  qualifies for the same resource envelope, rerun the complete model-dependent experiment under a
  new model freeze while holding the scientific payload fixed.

“Complete” includes all predeclared routing and futility stops. A G36 failure is the measured floor,
not permission to change questions before G38; a G36 pass is sufficient success, not merely a
temporary result.

---

## 1. Scope and allowed claims

The diagnostic corpus remains the six iteration games and their 18 selected sessions:
`dc22`, `ft09`, `ls20`, `m0r0`, `tu93`, and `vc33`. Reserved and one-shot games remain sealed.
S+C conclusions initially cover frozen passive-complete query cohorts drawn from 12 sessions, two
per game; they are not claims about every query in those sessions. Extending that claim to eligible
queries drawn from all 18 selected sessions requires the predeclared mechanical R replication in
§5; R is not silently included in an earlier corpus claim.

The estimand is conditional on these six games. Games receive equal macro weight; sessions and
cases are repeated observations within a fixed game. No interval or gate estimates performance
on unseen games.

Model-free candidate coverage, identifiability, `DOSE-*`, cohorts, and oracle survivor sets are computed
once and shared by G36 and G38. Model evidence-use and representation results are reported
separately for each generation. On common arms, the paired G38−G36 difference estimates a
generation-stack effect conditional on identical semantic evidence; model-specific selected
branches are reported as separate winners and are not treated as a pure model contrast. It becomes
a pure weight-generation effect only if quantization, engine, tokenizer, processor, template, and
decoding are also identical.

G36 is “good enough” only when a non-oracle arm passes `ES-USE`, exact-stack `ES-VALUE`, and
the agent-value gate. That result becomes eligible immediately for an adoption decision; it does
not amend the deployed agent by itself. If G36 fails, G38 may advance within ES by
passing the same absolute gates. If both pass, G36 remains the incumbent unless a predeclared fresh
three-arm trial shows G38 improves normalized primary progress by at least 0.05 absolute over G36, is
positive in at least four games, has a lower 90% paired sensitivity bound above zero, and has no
material efficiency/cost regression under §5.3. The measured G36 result is an **empirical baseline/floor on
this task**, not a mathematical lower bound on G38.

This screen separates four concepts that were previously conflated:

- **candidate coverage:** whether a source-independent bounded grammar can express the authored
  rule;
- **evidence identifiability:** whether the available outcomes eliminate all non-equivalent rules;
- **model evidence use:** whether Qwen returns the same survivor set as an executable solver;
- **agent value:** whether an online, non-oracle advisor improves play enough to justify its cost.

The model endpoint is **closed-set candidate-goal discrimination**. Passing it is not open-ended
goal inference. A broader claim requires an independently validated runtime candidate generator
and the agent-value trial in §5.

Because `U_i` is instantiated per query, the offline endpoint is specifically **per-query
grounded-rule discrimination**. It does not establish recovery of one invariant session- or
game-level goal. Any such claim requires a separately frozen shared-template canonicalization and
cross-case consistency endpoint; ES-VALUE instead tests whether the per-query advisor is useful.

The grammar designer necessarily knows the six authored goals from GI-2. Per-case universe
instantiation is evidence-blind, but the universe design is not gold-naive. Every result is therefore
conditional on this six-game design corpus; coverage on a new game is unmeasured.

“Data sufficiency” means sufficiency of the recorded in-context replay evidence. It says nothing
about pretraining-data sufficiency.

## 2. Leakage boundary and source truth

### 2.1 Session-atomic partitions

Nested replay prefixes make levels and action windows invalid split units. Each whole session,
including every ancestor frame used by a later query, is assigned atomically to one role:

- **S — selection:** choose the passive evidence dose and nominate one diagnostic contrast and
  one non-oracle packet;
- **C — confirmation:** untouched for G36, then reused only as a preregistered locked G38 paired
  replication;
- **R — reserve:** sealed until the first qualifying generation reaches the runtime-generator and
  exact-stack check; any later reuse has the restricted status defined in §5.2.

There are three selected sessions per game, so a frozen hash assigns exactly one session per game
to each role. No recorded session row, nor an artifact derived from that row, may occur in two
roles. Equal board values that arise independently in distinct sessions are not cross-role reuse.
The current inventory gives a conservative call-budget ceiling of 35 transfer cases per role
(5/5/6/5/8/6 by game before dose-availability filtering); the exact role-by-game inventory is
published at partition freeze rather than assumed from that ceiling. Every analysis clusters at
whole-session level and reports the six game results directly; it does not manufacture a population
interval by resampling games.

The partition and case-to-evidence dependency graph are published before any survivor curve.
If a session does not contain enough eligible cases, that shortage is reported. Cases may not be
borrowed from C or R to repair S.

All common questions, semantic packets, gates, stop rules, and branch rules are sealed before G36.
Seeing G36 S/C/R results cannot change a G38 common artifact. Consequently, G38 on reused C/R is a
locked paired replication, not a second untouched confirmation. A genuinely independent G38 claim
must come from the fresh operational runs in §5.3 or a separately authorized new holdout.

### 2.2 Versioned source adapters

ES requires a versioned adapter for each game. An adapter must expose, for every selected state:

- the authored completion program;
- completion/non-completion truth;
- visible cell values and deterministic deltas;
- source object masks, properties, relations, identities, and lineage where defined;
- deterministic forks used by the oracle probe ceiling.

The adapters write role-separated immutable source-gold artifacts containing source locations,
input hashes, and independent replay assertions. A generic visual tracker may propose runtime objects,
but it cannot author source gold. `ES-IDENT` fails closed if the adapter cannot reproduce every
recorded completion or if replay and source state disagree under the accepted 2026-07-30 fidelity
erratum: equality is required on settled, solved-terminal, and next-level frames. Intermediate
`vc33` animation-frame divergence is recorded but is not a fidelity failure. The adapter reuses
GI-2's regenerated 981-fork table and its settled-frame assertions rather than constructing a new
fork corpus.

S/C gold and R gold have separate custody. The ordinary experiment process may read
`es_source_gold_sc.jsonl`; it receives only R row IDs, non-gold replay inputs, and the hash of an
access-controlled `es_source_gold_r.sealed` artifact. A separate custodian process may validate R
adapter/replay fidelity before freeze but publishes only the aggregate pass/fail and artifact
digest. The runtime generator, packet builder, and model runner cannot import the custodian module
or read the sealed path. R gold is unsealed exactly once, only after every eligible runtime universe
and live packet has been hashed; the unseal event and access log become artifacts. Any earlier read
or digest mismatch fails R closed.

### 2.3 Runtime-observable outcome signal

P0–P2-live may label an outcome only from information available online. A frozen detector reads
the environment-returned level index/reset or terminal event and a bounded settled-frame window;
it emits `complete`, `non_complete`, or `unknown`. It may not read the source adapter or offline
completion metadata. Source truth audits this detector on every S/C transition before model calls
and, after R runtime outputs are sealed, on every R transition before compatibility.

The live-path gate is 1.00 agreement on every completion/non-completion transition used by a
model packet and zero `unknown` values. If the environment exposes no reliable online signal or
the detector misses this gate, P0/P1-live/P2-live are relabelled oracle-assisted and `ES-VALUE`
is blocked. Source/oracle arms retain the same audited labels so outcome-label quality is not mixed
into a representation contrast.

---

## 3. ES-IDENT — model-free evidence identifiability

This is the primary data-sufficiency experiment. It runs before any Qwen measurement.

### 3.1 Evidence-blind bounded hypothesis universe

A single frozen grammar generates a finite universe `U_i` from the visible symbols and descriptors
available at `DOSE-0` only. It may not inspect `DOSE-1`–`DOSE-4` states or labels while
instantiating that universe. The resulting `U_i` is held byte-identical through every
`DOSE-0`–`DOSE-4` survivor calculation.
The grammar may use:

- sets defined by visible value/color, connected-component topology, size, or relative position;
- quantifiers such as none, exists, all, exactly one, and bounded counts;
- visible spatial relations such as contact, containment, alignment, connection, and overlap;
- temporal predicates such as appears, disappears, changes, persists, splits, and merges;
- at most two clauses and a frozen expression-depth/count bound.

The primary grammar may not mention source variable names, hidden roles, source IDs, the gold
rule, or which observations distinguish candidates. Candidate entity terms are frozen observable
**descriptor programs**, such as “the leftmost red component,” rather than object IDs. A term must
denote a unique object or explicit set at `DOSE-0` to enter `U_i`. Internal source roles belong only
to a separately labelled source-semantic ceiling and never enter a visual or deployable arm.

Historical evidence is not treated as backward lineage from the query. Each descriptor program is
re-evaluated independently on the pre-state of every evidence transition, including earlier levels.
Identity/lineage then runs forward only within that transition: disappearance yields the empty set,
and split/merge yields the corresponding set. A reset or level boundary starts a new identity
namespace. Missing or ambiguous state-local binding yields `unknown`; no cross-level identity is
invented. Candidate evaluators use strong three-valued logic (`true`, `false`, `unknown`). An
`unknown` prediction never contradicts an observation and therefore remains in the survivor set,
but it cannot count as confirming evidence or semantic equivalence. The gold evaluator must remain
two-valued on every selected observation. No candidate is removed or rewritten because a referent
is missing or ambiguous.

Generation is exhaustive within the frozen bounds, canonicalizes algebraically equivalent syntax,
and has a hard tractability limit of 512 candidates per case. Exceeding the limit is a tractability
failure; candidates are not outcome-ranked or silently truncated. The generator output is hashed
before source gold or any completion labels are joined.

The source adapter then tests whether `U_i` contains the authored rule or a candidate with a frozen
semantic-equivalence proof.
Missing gold is a **candidate-coverage result**, not permission to hand-author a friendlier menu or
drop the game. The source schema itself must be capable of encoding every gold before freeze, but
runtime instantiation is allowed to fail coverage after freeze.

### 3.2 Full-universe ES-IDENT versus model panels

`ES-IDENT` evaluates every candidate in `U_i`; it is never computed over four hand-picked
alternatives. Let `E_i` be the **semantic gold-equivalent set**: a candidate enters only when it is
two-valued and either has the same canonical AST as the authored rule after the frozen
semantics-preserving normalizations, or has an exact proof over a declared exhaustive finite
semantic domain. Absence of a counterexample on a bounded fork suite is not a coverage proof.

Separately report `O_i`, the candidates that are two-valued and match gold on every point in the
frozen bounded observational suite. `O_i` is a sensitivity ceiling, not the coverage target. A
candidate with any `unknown` on that suite belongs to neither `E_i` nor `O_i`; it remains an
unrefuted member of the survivor set and therefore blocks identification until definite evidence
eliminates it. Full-universe coverage and scoring target `E_i` only.

Qwen cannot practically inspect up to 512 rules in the diagnostic calls, so `ES-USE` uses
four-candidate **evidence-critical panels**. The panel-selection algorithm is frozen before
`ES-IDENT`, but panels are instantiated only after `DOSE-*` is mechanically derived. Each panel
contains the first `E_i` member in frozen canonical-serialization order (hash breaks only a byte
tie) and three rules with stored definite counterexamples against the authored rule. All other
members of `E_i` are excluded from the panel; the chosen representative is its only semantic-gold
member, while the exact model target remains the oracle survivor set at the requested dose. Every distractor
must survive `DOSE-0`, and at least two must be eliminated by the added evidence at `DOSE-*`.
If three witnessed distractors do not exist, `critical_panelable=false`. This makes correct
`DOSE-0`→`DOSE-*` survivor shrinkage the model estimand rather than `DOSE-*`-only guessing.

Eligible distractors are ordered by a frozen grammar-family/hash schedule; no model output is used.
Panel construction is intentionally outcome-aware and oracle: it creates a diagnostic evidence-use
challenge and cannot support deployment. Full-universe `ES-IDENT` remains the evidence-blind sufficiency
measurement.

Across evidence-critical cases within a game, panel-position A–D gold-candidate counts differ by at most
one; exact equality is required only when the case count is divisible by four. Grammar-edit families
and description lengths are counterbalanced where the frozen universe permits. The panel inventory
and permutation schedule are sealed after `DOSE-*` and before the first model response.

### 3.3 Fixed nested evidence doses

Evidence is chronological and nested. Passive `DOSE-1`–`DOSE-3` selection never consults which
candidate is gold or which candidate an observation eliminates. `DOSE-4` is candidate-aware but
gold-index-blind under the rule below.

| Dose | Added evidence | Status |
|---|---|---|
| `DOSE-0` | Current non-terminal query state and its label | passive baseline |
| `DOSE-1` | Earliest eligible earlier completion: pre-state, action, solved state | passive |
| `DOSE-2` | Next eligible earlier completion whose level differs from the `DOSE-1` completion level | passive |
| `DOSE-3` | Two chronologically earliest matched natural non-completions | passive replay ceiling |
| `DOSE-4` | Two fixed-budget source-simulated fork probes added to `DOSE-3` | gold-blind oracle design ceiling |

Ties use source order and a frozen hash. `DOSE-3` matches action class and pre-state complexity but
not candidate predictions. `DOSE-4` has exactly two greedy-sequential probes. Starting from the
`DOSE-3` survivor set and query state, a source simulator predicts each reachable action's label
without access to the gold index. For survivor set `V` and action `a`, define
`V_y(a)={c in V: pred_c(a) in {y, unknown}}`; `unknown` survives either observable binary outcome.
The selector maximizes deterministic worst-case reduction
`|V| - max(|V_complete(a)|, |V_non_complete(a)|)`, followed by frozen cost/action/hash tie-breaks,
then executes the action. It updates both the state and survivor set from the observed label before
recomputing reachable actions and selecting probe 2 by the same rule. If two valid probes do not
exist, `probe_complete=false`; a simultaneous or full-`U_i` selection may not substitute. In
particular, if probe 1 completes, terminates, resets, or changes level, the sequential branch ends
and the case is not probe-complete—the simulator may not restore the root merely to obtain probe 2.
`DOSE-4` therefore measures a two-probe **oracle experiment-design ceiling**; it is not evidence
that a deployable probing policy exists.

`ES-IDENT` publishes five indicators for every case: `tractable` (enumeration completes at or below
512 candidates), `covered` (`E_i` is nonempty), `passive_complete` (`DOSE-0`–`DOSE-3` exist),
`probe_complete` (`passive_complete` plus `DOSE-4`), and—after `DOSE-*` is fixed—
`critical_panelable` (the §3.2 evidence-critical panel exists). No row is silently discarded.

All `DOSE-0`–`DOSE-3` `ES-IDENT` curves, `G_X(d)`, and `DOSE-*` use the same fixed
**passive-complete cohort**, with missing coverage counted as identification failure. `DOSE-4` lift
uses the fixed **probe-complete cohort** and compares `DOSE-3` with `DOSE-4` on those identical
cases. `ES-USE` comparisons and gates use
the separately fixed evidence-critical cohort. Its P3 passive curve uses that same cohort at
`DOSE-0`–`DOSE-3`; only `DOSE-4` uses its probe-complete intersection. Missing evidence and every cohort transition
are reported separately.

S and C each require at least three passive-complete cases per game, and every such case must be
tractable and covered for the full-universe sufficiency gate. `ES-USE` uses the separately named
evidence-critical cohort and requires at least three `critical_panelable` cases per game in both S
and C; `DOSE-0`-identified cases remain in `ES-IDENT` but do not answer whether Qwen used added
replay. The S P3 curve requires at least three probe-complete cases per game for its `DOSE-4`
contrast. Falling below a
floor makes that phase infeasible/inconclusive. Easier later-dose cases may not replace a frozen
cohort.

### 3.4 Mechanical endpoint, gates, and freeze

For case `i` and dose `d`, `V_i(d)` is the set of candidates whose executable prediction either
agrees with or is `unknown` for every observed completion/non-completion label. Only a definite
contradiction eliminates a candidate. Report, for the full universe and separately for model
panels:

- gold/equivalent-set retention;
- identification rate: no surviving candidate outside the gold-equivalent set;
- survivor count and its distribution;
- per-game and per-session values;
- paired elimination from `DOSE-0`→`DOSE-1`→`DOSE-2`→`DOSE-3`→`DOSE-4`;
- semantic coverage (`E_i` nonempty), bounded observational-match-set size `|O_i|`, unrefuted
  `unknown` count, and universe size.

Conditional on `covered`, implementation preflight requires every `E_i` member to be two-valued,
`E_i ⊆ O_i`, gold/equivalent retention 1.00, monotone survivor sets, correct replay labels,
deterministic generation, and identical reruns.
These are correctness checks. Missing coverage, low `DOSE-4` identification, or a large survivor set are
scientific results and may not send the measured inventory back for easier distractors.

For a tractable case define `identified_i(d)=1` iff `E_i` is nonempty,
`V_i(d) ∩ E_i` is nonempty, and `V_i(d) ⊆ E_i`; otherwise it is 0. A coverage miss, empty universe,
tractability overflow above 512, or evaluator failure scores 0 at every dose and stays in its frozen
cohort denominator. A per-game identification rate is the arithmetic mean over every frozen
passive-complete case in that role; game-macro is the unweighted mean of the six game rates. No
failure can make a game disappear from the macro. Because the sufficiency gate additionally
requires complete coverage and tractability, any such failure makes that role read
**coverage-blocked** rather than passed.

For each passive dose define:

`G_X(d) := identification >= 0.75 game-macro, at least four games >= 0.60, and no game < 0.40`

where `X` is S, C, or the later R replication. **PROPOSED:** these exact thresholds must be accepted
in `gate_manifest.yaml → es` before implementation of any ES-specific universe/dose generator,
scorer, or gate begins; the manifest entry is the numeric authority and
`logs/es_common_freeze.json` records its digest. Before that point, work is limited to auditing and
reusing threshold-agnostic GI-2 infrastructure.
`DOSE-*` is the smallest of `DOSE-1`–`DOSE-3` satisfying `G_S(d)`. C then tests the already-fixed
`DOSE-*` using `G_C(d=DOSE-*)`. No threshold, grammar bound, panel, or dose may change after seeing S.

Interpretation is deliberately narrow:

| Result | Supported conclusion |
|---|---|
| runtime universe misses gold | the observable grammar/generator lacks coverage; no Qwen conclusion |
| S has no passive `DOSE-*` | recorded passive replay is not sufficient under the frozen universe |
| S passes but C fails at `DOSE-*` | passive sufficiency did not replicate across sessions |
| `DOSE-3` fails and fixed-budget `DOSE-4` improves | oracle counterfactual probes add information; deployable probing remains untested |
| `DOSE-4` remains low | the bounded universe is non-identifying even with two oracle probes |
| S and C pass | passive replay is mechanically sufficient for the frozen eligible query cohorts drawn from the 12 S+C sessions |

---

## 4. ES-USE — Qwen evidence use and representation loss

`ES-USE` runs once for G36 and later repeats for G38. Each generation runs only if the shared
full-universe `ES-IDENT` gate passes on S and C, coverage is complete on their passive cohorts, and the
evidence-critical cohort meets its per-game floor in both roles. Every generation receives the
same cases, doses, candidate panels, wording, action labels, underlying evidence states, arm
definitions, gates, and selection rule.

G36 is the absolute baseline experiment. G38 is both an independently gated result and a locked
paired replication on the common arms. G38 performs its own S-only contrast/live-arm nomination
and follows the corresponding pre-emitted C branch; it does not inherit the G36 winner.

The model returns the surviving labels rather than guessing a singleton:

```json
{"survivors":["A","C"]}
```

Primary decoding uses a guided JSON grammar; first-pass operational formatting is tested later on
the real score stack. Exact survivor-set accuracy is primary. Gold retention, set F1 score, and top-one
accuracy on oracle-singleton panels are secondary.

### 4.1 Common referent protocol

Candidate language contains only observable descriptor terms from §3.1. It never contains source
IDs or hidden roles. Every table row and mask uses the same descriptor alias. A sidecar may add
exactly one declared mapping—from an existing descriptor alias to a runtime/source object row or
mask—but may not rename the candidate term or reveal candidate truth. The shared mapping schema
has an explicit `matched`, `missing`, or `ambiguous` status; runtime failures remain in paired
scoring and are never filtered away. Oracle arms use the same field and may resolve them.
Automated tests prove that candidate wording is byte-identical across arms and that every alias is
defined in the base packet, even when its runtime mapping is missing.

### 4.2 Structured packet ladder

The historical GI-1 packet is a report-only anchor; it is not an adjacent causal rung because it
contains less evidence. Pixel-only packets are excluded from the **common** G36/G38 core so that
the generation comparison holds representation fixed. For G36 that exclusion follows from the
measured Freeze-1 failure; for G38 it is a design choice that keeps the common core fixed,
revisitable only through the canary below.

Before G38 `ES-USE`, a separate successor-transfer canary may run 4 hash-selected frozen
boards/game on I-16, I-A, and I-H (72 calls). It reuses the Freeze-1 task and gates but is never
pooled with `ES-USE`. A G38 pure-image pass may open a separately frozen successor-only visual
extension; it cannot alter or replace the common-core replication.

All measured arms retain the same base packet:

| Arm | Added representation | Interpretable comparison |
|---|---|---|
| P0 | Every state in the requested dose prefix `d`, and no later state, as an exact indexed grid with explicit value/color legend, deterministic cell delta, action, and outcome label; current image retained as context only | non-oracle evidence-complete base |
| P1-live | P0 + runtime component/object table and descriptor→row/mask mapping | runtime object extraction |
| P1-oracle | P0 + the same table/mapping schema from source truth | source object ceiling |
| P2-live | P1-live + runtime relation, identity/lineage, and event table | deployable semantic state construction |
| P2-oracle | P1-oracle + the same relation/lineage/event schema from source truth | source semantic ceiling |
| P3 | P2-oracle + each candidate's truth value at every state in the requested dose prefix `d` | explicit-predicate integration diagnostic |

P1-live/P1-oracle and P2-live/P2-oracle are paired siblings, not consecutive rungs. Their schemas
are byte-for-byte identical apart from values and provenance. P1-oracle, P2-oracle, and P3 are
diagnostic ceilings and can never become deployment candidates. P0, P1-live, and P2-live are the
only eligible online packets.

The only selectable ordered contrasts, always scored as first arm minus second arm, are:

1. ES-CMP-1 = P1-live − P0;
2. ES-CMP-2 = P1-oracle − P1-live;
3. ES-CMP-3 = P2-live − P1-live;
4. ES-CMP-4 = P2-oracle − P1-oracle;
5. ES-CMP-5 = P2-oracle − P2-live;
6. ES-CMP-6 = P3 − P2-oracle.

P0 grids and deltas are produced only from the runtime observation payload by the same isolated
non-oracle path used online. Source grids may check them after generation but may not supply or
repair them. Any mismatch is a runtime-representation failure, not an opportunity to substitute
source truth into P0.

Before the common freeze, every possible canonical `ES-USE` request is rendered through the exact
G36 tokenizer, processor, chat wrapper, guided-output schema, and tool envelope. The audit records
text/vision/input tokens and verifies the **PROPOSED** minimum 512-token output headroom, including
the largest P3 `DOSE-4` and P2-oracle `DOSE-*` packets. The same audit is repeated during G38 stack
qualification on the unchanged semantic packets. No request may be silently trimmed, crop a grid,
drop a state, or lose an arm because of context. If any request is infeasible before the common
freeze, the design returns to pre-freeze; the only permitted repair is a frozen exact encoding with
a full first state plus indexed sparse deltas for every later state, applied uniformly to all arms
and both generations. After freeze, a context-infeasible row is retained as an availability failure
and that arm/generation cannot pass. Tokenizer differences cannot authorize a payload edit.

### 4.3 Per-generation selection and confirmation

For each generation independently:

1. Run P3 at `DOSE-0`–`DOSE-3` on every evidence-critical S case and at `DOSE-4` on its probe-complete intersection.
   A deterministic solver over the supplied truth matrix must score 1.00. P3 is a diagnostic, not
   a futility gate: extra truth rows can increase the model's integration burden, so P3 failure says
   nothing mechanically about a simpler arm.
2. Run the common P0 anchor on S at `DOSE-0` and the already-fixed passive `DOSE-*`.
3. Run P1-live, P1-oracle, P2-live, and P2-oracle on the evidence-critical S cohort at both
   `DOSE-0` and `DOSE-*`, regardless of the Qwen P3 result; reuse the completed P0 anchor.
4. Using only S, nominate one confirmatory representation contrast: the largest signed
   `DOSE-*` exact-set game-macro lift among ES-CMP-1–ES-CMP-6, with numeric order as tie-break.
   The signed rule is deliberate: the single confirmatory slot is reserved for the largest claimed
   benefit. A materially negative live-arm contrast is therefore not confirmable here by design;
   it is reported descriptively, and its practical consequence flows through step 5, whose
   least-cost rule already drops a representation that does not earn its cost.
5. Also using only S, nominate the least-cost arm among P0/P1-live/P2-live that passes the
   deployable packet floor. Cost order and latency/token limits are fixed before calls.
6. On the evidence-critical C cohort, run P3 and both selected-contrast arms at `DOSE-0` and
   `DOSE-*`. If no live arm passes S, record **no deployment nominee**. Otherwise also run the
   nominated live arm at both doses. Duplicate arms are called once. A Qwen P3 miss affects only
   the P3 diagnostic; it cannot invalidate another arm or contrast. A packet/solver validity failure
   invalidates only comparisons containing that arm. No C result may select a fallback arm; a new
   candidate requires a new protocol rather than a stack rerun.

All possible G36 and G38 C **semantic** branches are emitted before the first G36 response. G38
selection may read only G38 S responses. Analyst knowledge of G36 C results cannot change a G38
prompt, semantic packet, gate, arm, or branch; only the checkpoint-required processor/template
envelope may be bound later under §6.2.

For every panel case and requested dose `d`, let `V_i^panel(d)` be the executable oracle survivor
set, `Vhat_i^panel(d)` the labels returned by Qwen, and `g_i` the selected semantic-gold
representative. Exact-set accuracy is
`1[Vhat_i^panel(d)=V_i^panel(d)]`; set F1 score compares those two sets; gold retention is
`1[g_i in Vhat_i^panel(d)]`. Each case-level rate is averaged within game, then the
six game rates are averaged with equal weight. All S and C thresholds below use that game-macro;
“no game below” applies to the corresponding per-game mean.
Any request, context, schema, or parse failure remains in the cohort with exact-set, set F1 score,
gold retention, and critical-elimination success all scored 0; it is never dropped as missing.

**PROPOSED P3 diagnostic success criterion at `DOSE-*`:**

- exact survivor-set accuracy >= 0.80 game-macro;
- gold retention >= 0.95;
- critical-elimination recall from `DOSE-0`→`DOSE-*` >= 0.80 and no game below 0.60;
- no game below 0.60 exact-set accuracy;
- deterministic solver exactly 1.00.

**PROPOSED deployable packet floor on both S and C:**

- exact survivor-set accuracy >= 0.70 game-macro;
- gold retention >= 0.90;
- critical-elimination recall from `DOSE-0`→`DOSE-*` >= 0.70 and positive shrinkage in at least four games;
- no game below 0.50 exact-set accuracy.

Critical-elimination recall is computed only over distractors that the executable oracle retains at
`DOSE-0` and eliminates by `DOSE-*`. A success requires the model to include that distractor at
`DOSE-0`, exclude it at `DOSE-*`, and retain the gold at both doses. This paired transition—not
`DOSE-*`-only accuracy—is the evidence-use claim. It is computed per game over all such distractors,
then game-macro averaged. “Positive shrinkage” means positive within-game mean of
`|Vhat_i^panel(DOSE-0)| - |Vhat_i^panel(DOSE-*)|` over paired cases with gold retained at both doses.

A representation contrast is material only if its paired game-macro lift is at least 0.10 and has
the same sign in at least four games. S only nominates. The nominated ES-CMP contrast **confirms**
only if that rule holds independently on C, in the predeclared first-minus-second direction, with
no S+C pooling and valid rows for both arms. With only one session per game in each role, no case
bootstrap or pseudo-population confidence bound enters the gate. The six per-game effects and all
raw paired case outcomes are reported.

The single primary offline stack comparison is **G38−G36 critical-elimination recall from
`DOSE-0`→`DOSE-*`**
on the identical P0 S evidence-critical cohort. A lift is material at >=0.10 game-macro with the
same sign in at least four games. P3, exact-set accuracy, other doses, and C comparisons are
secondary/descriptive. Selected-winner scores are never substituted for the primary paired anchor.

The routing language is descriptive:

| Confirmed comparison | Supported conclusion |
|---|---|
| Qwen fails P3 while solver passes | Qwen fails panel consistency/selection even when predicate truth is explicit |
| ES-CMP-6 confirms | supplying candidate truth is material; exact semantic tables were insufficient |
| ES-CMP-4 confirms | supplying source relations/lineage/events is material |
| ES-CMP-5 confirms | the complete runtime semantic pipeline loses information relative to source truth |
| ES-CMP-2 confirms | runtime object extraction loses information relative to source truth |
| ES-CMP-1 confirms | runtime object extraction is useful relative to grids alone |
| ES-CMP-3 confirms | runtime relations/lineage/events add value beyond runtime object tables |
| a G36 non-oracle arm passes | four-candidate discrimination is confirmed for G36 and may advance immediately to `ES-VALUE`; G38 is not a prerequisite |
| G38 materially exceeds G36 on the primary P0 endpoint | the successor generation stack materially improves evidence use under the fixed semantic packet |
| G38 selects a different live arm | the best representation is generation-specific; this is not a pure model-effect estimate |

No single contrast licenses the stronger phrase “the failure lies in X”; packet differences can
interact, and only the added information is identified.

---

## 5. ES-VALUE — non-oracle deployment test

`ES-VALUE` is mandatory for any advisor claim and is gated separately by generation. A confirmed
G36 live arm advances immediately within ES; neither compatibility nor agent value waits for G38. A later
confirmed G38 live arm follows the same contract under its own deployment fingerprint.

### 5.1 Runtime candidate-generator gate

The same bounded grammar must have a frozen runtime generator. As in `ES-IDENT`, it instantiates one full
universe from `DOSE-0`-visible symbols only and holds that universe fixed while accumulated history is
supplied as evidence; history may not prune or reorder candidates by predicted correctness. An R
query is compatibility-eligible only when its non-gold runtime history can construct the complete
fixed `DOSE-*` passive prefix. Every other query remains in the published inventory as
`dose_unavailable`; it is not silently replaced by an easier row. Before source labels for R are
opened:

1. run it on every eligible R query;
2. generate, hash, and seal the ordered candidate sets plus P0/P1-live/P2-live packet inputs so a
   later generation cannot construct a new R packet after seeing G36 results;
3. audit that no source adapter, completion metadata, gold-selected crop, fork outcome, or answer
   key was reachable by the process;
4. only then join source gold and executable-equivalence labels.

**PROPOSED generator gate:**

- gold/equivalent recall >= 0.90 game-macro and no game below 0.75;
- no universe above the frozen 512-rule tractability limit;
- the candidate set sent to Qwen fits the predeclared context envelope without gold-aware pruning;
- source-independence audit passes every row.

The complete runtime candidate batch must fit in one predeclared request per query. If it does not,
the generator fails the context/tractability gate; multi-call panels may not hide the true online
cost or escape the 35-call cap. A source-authored shortlist may not substitute. Without this gate,
the only allowed deployment claim is “ranking conditional on an oracle candidate menu,” and no
advisor trial may open.

### 5.2 Exact score-stack compatibility

After the runtime candidate outputs and every eligible live packet are sealed and source truth is
joined, first reapply the §2.3 outcome-detector gate to every R transition. Any disagreement or
`unknown` relabels the live packet oracle-assisted and stops `ES-VALUE`. If it passes, run the
fixed full-universe `G_R(d=DOSE-*)` gate on one R passive-complete cohort with at least three cases per
game. R failure blocks a sufficiency claim over eligible queries from all 18 sessions and stops
compatibility. If it passes, run the confirmed packet and runtime candidate generator on every
eligible R case, at most 35 primary
calls per generation. The stack is that generation's frozen submission artifact and engine from
§6.1. `tool_choice` is forced to `none`; emitted tool calls are invalid and never executed.

Before each generation's first R call, every sealed request is rendered through its exact score
stack. The preflight includes the largest legal 512-candidate input, tool/chat/thinking allowance,
and an output containing all 512 survivor labels, and must leave the manifest's output headroom.
No output truncation, candidate pagination, or parser repair may lower the apparent survivor count;
a context, timeout, schema, or truncation failure remains in the denominator with gold retention
and set F1 score 0 and false-survivor rate 1. A generation that cannot fit this envelope fails
compatibility rather than changing the semantic payload.

The R row rule, retained-history construction, output limit, timeout, retry policy, and latency/
token envelope are frozen before the first G36 S model call. `ES-VALUE` does not reuse the
balanced-panel metric: the model returns survivors from the entire runtime universe in one call,
and the executable evaluator supplies its full-universe target set. For case `i`, let
`V_i=V_i(DOSE-*)` be the executable oracle survivors and `Vhat_i` the model-returned survivors.
Set F1 score compares `Vhat_i` with `V_i`; gold retention is `1[Vhat_i ∩ E_i != empty]`; and
false-survivor rate is `|Vhat_i ∖ V_i| / max(1, |U_i ∖ V_i|)`, the fraction of oracle-eliminated
candidates incorrectly retained. Case metrics are averaged within game and then equally across the
six games. Report request success, image
acceptance, context fit, trimming, output headroom, first-pass schema validity, candidate coverage,
gold/equivalent retention, full-universe set F1 score, false-survivor rate, bytes, tokens, latency,
and cost.

**PROPOSED semantic gate:** gold/equivalent retention >= 0.90 game-macro with no game below 0.75,
full-universe set F1 score >= 0.70 with no game below 0.50, and false-survivor rate <= 0.25. Operational
floors must be copied from the score-run budget into the common freeze. These thresholds are not
described as comparable to `ES-USE`'s four-candidate exact-set score.

This phase establishes exact-stack compatibility on fixed games. It does not establish value.

R has two possible statuses for G38:

- If G36 never opens R, G38 receives the original untouched reserve.
- If G36 opens R first, G38 may reuse only the already-sealed rows and packets as a **locked paired
  compatibility replication**. It is not called an untouched G38 holdout. An independent G38
  deployment claim then requires the new-run agent-value trial below.

### 5.3 Paired agent-value trial

Compatibility passing activates the already conditionally frozen operational trial on new
seeds/runs. The **PROPOSED** inventory is six hash-selected matched `(seed, start_state)` blocks per
game. G36 therefore uses 36 blocks/72 game-runs across advisor and no-advisor arms. The base agent's
executable, model stack, prompts, tools, history compaction, action parser, and action/time/token
budgets are byte-frozen; the same playing-agent stack is used for G36- and G38-advisor trials, and
the sole treatment difference is the goal-advice block below. Replacing the playing model itself
requires a separate factorial protocol and is outside ES.

Advisor opportunities inherit VP's score-stack cadence: level entry or three consecutive executed
environment actions that leave the board unchanged, hard-capped at eight opportunities per game-
run. At each opportunity the old active advice is cleared. The turn is usable only if runtime
history constructs `DOSE-*`, the candidate universe is tractable, the live outcome path is valid,
and the exact request/response fits. A valid response injects, immediately before the next analyzer
decision, one canonical block containing `status=active`, dose, candidate-set hash, and every model-
returned survivor as `(candidate_id, canonical_rule)` in generator order. The frozen base-agent
instruction calls these unresolved hypotheses, never facts; the base agent alone chooses actions.
The block remains active only until the next scheduled opportunity and is replaced, never
accumulated in the active prompt.

Before the trial, the exact next-analyzer prompt is preflighted at the largest permitted retained
history with tools plus a 512-survivor `(candidate_id, canonical_rule)` block and the base agent's
own output headroom. No history, rule, or tool schema may be trimmed to make treatment fit. Failure
blocks `ES-VALUE` rather than abbreviating, ranking, or paginating the survivor set.
This worst-case, all-or-nothing preflight is intentional. Downgrading to per-turn abstention on
oversize blocks would make advice availability correlate with universe size — a silently biased
availability profile — and a channel that cannot carry its own frozen worst case is not the
channel this contract gates. Blocking on a worst case that never occurs in play is the accepted
cost.

Missing dose history, empty survivors, timeout, context/schema failure, or oversize output produces
an `abstain` event and no advice block; the prior block has already been cleared. Every scheduled
opportunity stays in the availability denominator. Attempted advisor calls charge their full
tokens and elapsed time but no environment action; the ordinary action/time budget is identical in
all arms. Cache state, active-block hashes, abstention reasons, budget exhaustion, and the exact
insertion bytes are logged. **PROPOSED availability gate:** active advice on at least 0.80 of
opportunities game-macro and no game below 0.60. A value claim must pass this gate as well as the
endpoint gate.

The scientific contract is immutable before the first G36 response:

- advisor versus no advisor on identical game, seed, start state, and action/time/token budget;
- candidate generation and packets use only information available at that turn;
- one primary normalized-progress endpoint on `[0,1]`. **PROPOSED definition:** normalized
  progress is `distinct_levels_completed / L_g`, measured at the earlier of budget exhaustion or
  game termination. `L_g` is the game's authored level count, read from its source adapter; the
  six `L_g` values are pinned in the common freeze before any run. A level counts once, at its
  first completion event, so level resets cannot double-count. There is no partial-level credit:
  no mechanical within-level progress measure exists, and a learned one would place an
  unvalidated model inside the endpoint;
- secondary endpoints: action efficiency, no-op streaks, wall time, advisor calls, availability,
  abstentions, and token cost;
- the cadence, eight-opportunity cap, treatment serialization, failure fallback, and six-block
  inventory above.

**PROPOSED value gate:** at least +0.10 absolute normalized progress over no advisor, positive paired
effect in at least four of six games, the lower endpoint of the central 90% fixed-game paired
sensitivity interval above zero, and no material action-efficiency regression. Action efficiency is
normalized progress divided by `max(1, charged_environment_actions)`; noninferiority requires
`efficiency_advisor >= 0.90 * efficiency_no_advisor`, which remains defined when the control is
zero. Generalization beyond these games requires a separately authorized independent-game
evaluation; sealed games may not be opened to rescue a failed result.

The sensitivity calculation jointly resamples matched `(seed, start_state)` run blocks within each
game 10,000 times, preserves the same sampled blocks across all two or three arms, computes one
paired effect per game, and gives the six games equal weight. Games are never resampled. The bound
is the fifth percentile of that fixed-game bootstrap distribution and is explicitly conditional on
these six games. Sample size and the 10,000-draw rule enter `gate_manifest.yaml → es` before calls.
For G38-versus-G36 adoption, the paired run inventory must also satisfy all three inequalities:
`efficiency_G38 >= 0.90 * efficiency_G36`; `tokens_per_decision_G38 <= 1.10 *
tokens_per_decision_G36`; and `p95_latency_G38 <= 1.10 * p95_latency_G36`.

G36 may run advisor-versus-no-advisor immediately. A later G38 trial uses a fresh run set not used
to select or confirm G36. If G36 qualified, replacement requires a mandatory fresh six-block-per-
game trial with three arms—no advisor, G36 advisor, and G38 advisor on identical seeds—giving 108
game-runs. In that trial G38 replaces G36 only under the §1 adoption rule: at least +0.05 absolute
normalized primary progress over the G36 advisor, positive in at least four of six games, the
fixed-game paired sensitivity bound above zero, and the three efficiency/cost inequalities above.
If no G36 advisor qualified, a two-arm G38-versus-no-advisor trial may establish absolute
G38 value but cannot make a G38-over-G36 claim. Thus a successful G36 advisor remains eligible for
an adoption decision even if G38 is delayed or fails qualification.

There is no outcome-dependent attrition. A verified common infrastructure failure that occurs
before any arm-specific work invalidates the whole matched block and consumes the next pre-sealed
replacement block; two replacements per game are frozen. Any arm-specific model, advisor, or agent
failure remains in its original block: advisor failures follow the abstention rule, and a playing-
agent failure scores zero normalized progress with its full incurred cost. Exhausting replacements
makes that game's trial incomplete rather than changing the sample.

---

## 6. Exact execution and conformance

### 6.1 Model stacks

Each generation may use at most 12 discarded **exact-stack qualification** calls on the same frozen
synthetic fixtures outside S/C/R. Their hashes and expected parses are part of its stack freeze;
their responses may not select or edit a measured prompt. Local MLX development is non-evidentiary,
does not consume this pool, and cannot establish FP8/vLLM conformance. Any semantic content/parser
change after the common freeze requires a new protocol; any stack-only change after qualification
requires a new stack fingerprint and regenerated canonical requests.

**G36 baseline:** `ES-USE` measurement uses `vrfai/Qwen3.6-27B-FP8` on vLLM with the exact
score-run processor, tokenizer, chat template, and tool schema. Local
`Qwen3.6-27B-8bit`/MLX is development only. G36 `ES-VALUE` uses thinking enabled,
`temperature=0.6`, `top_p=0.95`, `top_k=20`, a 32,768-token analyzer context, and representative
concurrency.

**G38 successor:** the target is the released Qwen3.8-27B checkpoint at a quantization and runtime
that fit the same submission memory, context, latency, and concurrency envelope. Before any G38 S
call, its model/revision, weight digest, license, quantizer, vLLM support, processor, chat template,
vision tokenization, thinking controls, context use, and throughput must pass a release-
qualification manifest. Until those fields exist, G38 is planned but not frozen. Failure to fit the
envelope makes it a diagnostic reference rather than a deployment candidate; it does not erase the
G36 result. G38 model-bound settings may be chosen only from the released model contract and frozen
synthetic qualification fixtures, never from G36 S/C/R performance.

Both generations use deterministic guided-JSON decoding in `ES-USE` (`temperature=0`, or the
predeclared `0.01, top_p=1` fallback only if that server rejects zero). The semantic user/system
content, images, candidate order, and output schema are identical. A model-required chat wrapper or
processor may differ and is fully recorded. If G38 cannot use equivalent deterministic decoding or
requires a semantic prompt change, its result is labelled a **successor-stack comparison**, not a
pure weight-generation effect. `ES-VALUE` uses each generation's frozen deployment sampling.

For every generation, the server must attest the model revision/weight digest, tokenizer and
processor config, chat-template hash, grammar mode, rendered resize, vision/input tokens, context
accounting, and generation parameters for every request. If it cannot, the result is labelled
**unattested stack compatibility**, not exact-stack confirmation.

### 6.2 Common and per-generation freezes

1. **ES-IDENT freeze:** before ES-specific governed implementation begins, accept the ES block in
   `gate_manifest.yaml`, append the required GI-2/VP cross-references, add the prospective
   ES→SPEC §9.7 mapping to `docs/README.md`, and then pin the
   grammar/enumerator, source-adapter code, partition, dependency graph,
   dose construction, `DOSE-4` policy and budget, equivalence test, thresholds, all S/C inputs,
   non-gold R inputs, and the sealed R-gold digest/custody rule
   before computing any survivor set. Acceptance changes the draft's **PROPOSED** numerics into
   governed values; `logs/es_common_freeze.json` snapshots that manifest digest and is not a second
   numeric authority.
2. Generate and seal all S/C universes and doses. Run `ES-IDENT` once on S, derive `DOSE-*`, then
   evaluate the same fixed mechanical gate on C. R remains sealed. G38 later verifies these artifacts by hash;
   it does not recompute a new `DOSE-*`, cohort, universe, or panel.
3. **Common experiment freeze:** apply the evidence-critical panel rule and seal every semantic
   P0–P3 S/C packet, every possible C branch, thresholds, parsers, scoring, stop/selection rules,
   the primary P0 stack comparison and secondary comparisons, adoption rule, per-generation
   budgets, exact R eligibility/row rules, runtime-generator algorithm/code and thresholds,
   all-live-packet construction, and the conditional agent-trial arms, endpoint, seed schedule,
   cadence, sample size, call budget, and gates before the first G36 response.
4. **G36 stack freeze:** pin the G36 stack manifest and canonical requests derived from the
   common semantic packets. Give every row `model_run_id=G36` and a G36 stack fingerprint, then run
   the complete §4 procedure and any earned §5 procedure without waiting for G38.
5. **G38 stack freeze:** after release qualification, pin only the G38-bound fields—weights,
   revision, quantizer, engine, tokenizer, processor, chat wrapper, and compatible decoding. Derive
   canonical requests from the unchanged common semantic packets, give every row
   `model_run_id=G38`, and traverse the same stop/selection rules independently. A G36 stop never
   forces a G38 stop, and G36 outcomes cannot select a G38 branch.
6. **Per-generation deployment instantiation:** bind only the already-permitted stack-specific
   execution fields and hash the concrete run IDs produced by the common seed schedule. On first
   blind R unseal, apply the frozen generator/row/packet rules and seal every eligible
   P0/P1-live/P2-live packet before joining source truth or making a model call. Later G38 reuse
   follows §5.2 and cannot manufacture new R inputs or alter the trial contract.

After the common freeze, low identifiability, missing candidate coverage, model failure, or
all-live-arm failure is a result. Any semantic change requires a dated new protocol rather than a
G38 replication. Responses and reserves are never pooled across `model_run_id`; each generation
has its own append-only raw log, summary, call accounting, and status.

### 6.3 Required validation

The implementation must provide:

- per-game source adapters and role-separated source-gold provenance with independent replay assertions;
- tests that the runtime generator cannot import or read source/gold artifacts;
- deterministic candidate enumeration, semantic-evaluator tests, and monotone survivor sets;
- complete packet rendering/processor audits, including exact grid legends and referent aliases;
- an end-to-end synthetic run covering branch selection, de-duplication, parsing, scoring,
  aggregation, and final routing;
- append-only rows preserving canonical request/response hashes, model/server attestation, usage,
  dimensions, latency, retry lineage, phase, `model_run_id`, common-freeze fingerprint, and stack
  fingerprint.

Every summary filters immutable phase and `model_run_id` fields. Selection, report-only, retry, or
compatibility rows cannot enter confirmation aggregates, and one generation's rows cannot enter
the other's absolute score.

---

## 7. Call budget

No new G36 perception-screen calls are planned; VP Freeze 1 supplies its interface-exclusion result.
The optional G38 successor-transfer canary in §4.2 has a separate 72-call cap and cannot consume
`ES-USE` reserve.

The current session inventory permits at most 35 S cases and 35 C cases before cohort filtering.
**PROPOSED `ES-USE` cap: 900 calls per generation.**

| Phase | Worst-case calls |
|---|---:|
| exact-stack synthetic qualification | 12 |
| P3 dose curve on S: at most 35 × `DOSE-0`–`DOSE-4` | 175 |
| S representation screen: 35 × 5 arms × `DOSE-0`/`DOSE-*` | 350 |
| C confirmation: at most 35 × 4 de-duplicated arms × `DOSE-0`/`DOSE-*` | 280 |
| **Planned worst case** | **817** |
| **PROPOSED retry/operational reserve** | **83** |

Duplicate C arms are called once and saved calls are not reassigned. A failed P3 diagnostic does not
cancel the predeclared representation ladder or turn its calls into reserve. G36 and G38 each
receive the same independent 900-call cap: planned two-generation core worst case is
1,634 calls under a combined 1,800 cap. No unused G36 call or retry allowance transfers to G38.

`ES-VALUE` has a separate **PROPOSED** 45-call compatibility cap per generation (35 primary plus at
most 10 predeclared retries), for a 90-call two-generation maximum. The G36 value trial plans 288
advisor calls with a 96-call matched-block replacement reserve, cap 384. A mandatory three-arm G38
replacement trial plans 576 advisor calls plus 192 replacement reserve, cap 768; a two-arm absolute
G38 trial instead has the same 384-call cap as G36. No-advisor arms make no advisor calls. All game-
run counts and replacements remain governed by §5.3.

## 8. Reuse, calendar, and production route

ES extends the audited GI-2 estate rather than re-authoring it: `gi2_replay.py`, `gi2_forks.py`,
`gi2_traces.py`, `gi2_observation.py`, `gi2_grounding.py`, `gi2_gidsl.py`, and
`gi2_gidsl_runtime.py`, including the accepted `vc33` 981-fork digests and settled-frame tests.
The six ES source adapters are thin versioned wrappers over that estate; any replacement of a
reused assertion or digest is a disclosed deviation, not routine implementation.

**Planning estimate, not an acceptance gate:** 7–11 focused development days for adapters,
enumeration/equivalence, packets, context audits, validation, freeze, and the G36 `ES-USE` read;
then 3–5 additional days for the conditional runtime-generator, R compatibility, and agent trial,
plus model wall time. Before `ES-IDENT` freeze, the operator must publish owners, dated milestones,
the agent-trial run/call budget, and which existing Stage-0 work this displaces. The repository's
Aug 22 screening hard stop is not relaxed by this draft. If the full G36 contract cannot fit, record
a schedule slip or stop after `ES-IDENT`; do not shrink cohorts, gates, validation, or reserves to
manufacture an on-time result.

Every G38 phase — the successor canary, stack qualification, locked replications, and any G38
trial — is calendar-subordinate: none may displace Track B build work or scheduled submissions,
and none holds a protected slot before the Oct 18 feature freeze. If Qwen3.8 releases too late to
run them, that is a recorded non-result; the G36 outcome stands on its own and is not reopened.

An ES pass informs a possible reconsideration of the implementation specification's §9.7
executable-predicate induction path. It does not satisfy or override the existing G0-R/G0-A rules.
Any Track B integration requires an entry in the `docs/README.md` decision register and a dated
amendment to the normative implementation specification; ES evidence alone never changes the
deployed architecture.

## 9. Planned artifacts

1. `agent/harness/es_sources/{game}.py` — versioned source adapters.
2. `agent/harness/es_candidates.py` — bounded runtime grammar, enumerator, executable evaluator,
   equivalence test, panels, and survivor curves.
3. `agent/harness/es_questions.py` — session-atomic split, evidence dependency graph, doses,
   referent protocol, and deterministic P0–P3 packets.
4. `agent/harness/es_screen.py` — freeze, verify, measure, summarize, stop, and route commands.
5. `logs/es_source_gold_sc.jsonl`, access-controlled `logs/es_source_gold_r.sealed`,
   `logs/es_r_unseal.json`, `logs/es_inventory.json`, `logs/es_candidates.jsonl`,
   `logs/es_questions.jsonl`, and `logs/es_common_freeze.json`.
6. `logs/es_stack_g36.json`, `logs/es_raw_g36.jsonl`, `logs/es_results_g36.json`, plus later
   `logs/es_stack_g38.json`, `logs/es_raw_g38.jsonl`, and `logs/es_results_g38.json`.
7. `logs/es_stack_comparison.json` — the primary paired P0 G38−G36 endpoint plus labelled
   secondary paired results; it never pools rows.
8. Conditional `logs/es_runtime_generator.jsonl`, per-generation
   `logs/es_score_stack_compatibility_{model_run_id}.json`, and separately frozen paired-agent
   artifacts.

The authoritative numeric preregistration is `gate_manifest.yaml → es`; the common-freeze artifact
contains its digest and concrete payload hashes.

The final report must keep these conclusions distinct: observable candidate coverage, passive
evidence identifiability, G36 panel discrimination, G38 panel discrimination, paired generation-
stack effects, runtime generator viability, per-generation score-stack compatibility, agent value,
and unseen-game generalization. Passing one never silently promotes the next.

---

## 10. Dated amendment — 2026-08-03: OC out-of-corpus expressibility probe

Registered as `ES-E1` in `gate_manifest.yaml → errata`; that entry is binding and this section is
its summary. After the ES-IDENT freeze — never before — the authored completion program of each of
the **15 one-shot games** is encoded in the same source-schema forms as the six iteration golds and
tested against the frozen grammar bounds. Zero model calls; source-reading only; the one-shot games
remain model-sealed; the four reserved games are not opened at all. Per game one of three outcomes:
`schema_inexpressible`, `bounds_overflow`, `expressible_within_bounds`
(`logs/es_oc_expressibility.json`).

Two binding rules: outside golds may not be traced before the grammar freeze (exposure, not only
editing, consumes the measurement), and no grammar/bound/vocabulary/schema change may respond to
an OC outcome — a miss is a result. OC is report-only for ES: it gates nothing and informs only
the operator's §8 decisions and the final report's generalization claim boundary.

Disclosed limits: S2's goal-predicate extraction already exposed all 25 games at the
mechanical-evidence and class level, so OC measures **out-of-design-corpus expressibility under
disclosed prior exposure**, not design-naive generalization — that resource was spent before ES
existed. OC also measures expressibility only: descriptor groundability, enumeration within the
512 limit, and identifiability stay unmeasured out-of-corpus, so §1's "coverage on a new game is
unmeasured" narrows rather than closes once OC runs.

---

## 11. Dated closeout — 2026-08-03: route-2 closure infeasible; ES ends coverage-blocked

The §3.2 route-2 equivalence proof — "an exact proof over a declared exhaustive finite semantic
domain" — was implemented as extensional equivalence over the game's fully closed reachable
transition graph (`agent/harness/es_sources/domain_closure.py`; frozen budgets 1,200,000 edges,
20,000 frontier), the only mechanical object with that status once bounded fork suites are ruled
out. Measured result (`logs/es_domain_closure.json`; full graphs in the local
`logs/es_domain_{env}.json.gz`, digests pinned):

| game | budget hit | states found | expanded | frontier left | levels reached | completion edges |
|---|---|---:|---:|---:|---:|---:|
| tu93 | `max_edges` | 242,625 | 200,000 | 15,822 | 7 | 516 |
| ls20 | `max_frontier` | 220,854 | 199,149 | 20,002 | 3 | 220 |
| vc33 | `max_edges` | 955 | 293 | 662 | 1 | 192 |
| ft09 | `max_edges` | 1,051 | 293 | 758 | 1 | 216 |
| m0r0 | `max_edges` | 534 | 293 | 241 | 0 | 0 |
| dc22 | `max_edges` | 645 | 293 | 352 | 0 | 0 |

*(Table completed 2026-08-04 when the last three runs reported; the section was first written
after tu93/m0r0/vc33. All six domain graphs and digests are in the summary artifact.)*

Two independent blowup modes, one conclusion, now measured on all six games. The keyboard games
explode in state count: tu93's space is still growing when the edge budget dies at 242k states,
and ls20 — the only run to hit the frontier cap — is at 220k states with 20,002 live branches
after three of seven levels. The click games exhaust the same budget after exactly 293 expanded
states because their effective alphabets carry the full 64×64 click expansion (~4,100 edges per
state); m0r0 and dc22 never reach a single completion at that depth, while vc33 and ft09 clear
only level 1. Closure is not near-missed anywhere; raising the budget is not a repair. No
route-2 proof therefore exists for any case of any game — all 105 cases read
`covered_route2: false`, `E_size_route2: 0` — and coverage could only arrive via route-1
canonical-AST identity, for which no measured coverage exists.

Under the frozen coverage rule (`gate_manifest.yaml → es → es_ident_gate → coverage_rule`), the
S role reads **coverage-blocked**: no `DOSE-*` is derivable, and `ES-USE`/`ES-VALUE` never open. Per
§3.4, missing coverage is a scientific result and may not send the inventory back for a
friendlier universe. **Operator decision (2026-08-03): ES ends here as a measured negative
result** — the frozen bounded grammar with exact-identification obligations cannot cover the
six-game corpus, and the proof obligation itself (closure) is what fails, before any model
question can be asked. Zero ES-USE calls were spent; the G36/G38 program does not run; OC (§10)
is moot for gating and remains unrun. The successor protocol is the MU
mechanics-representation screen (`notes/mu-representation-screen.md`), which drops
identifiability obligations and measures interface legibility and usability instead; the
transition is pinned in `gate_manifest.yaml → mu → predecessor`. **Accepted 2026-08-04: the
operator directed that this session's complete six-game record be folded into this section and
committed — that direction, following the operator's 2026-08-03 election to record failure
without a raised-budget rerun, is the closeout acceptance.** No `docs/README.md` register entry
is required for the closeout itself: it proposes no spec change, and its schedule consequence is
separately registered as `SCHED-2026-08-03`. Nothing above §10 is modified by this section.
