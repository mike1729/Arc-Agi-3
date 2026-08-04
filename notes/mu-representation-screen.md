# MU — mechanics-representation screen

**Date:** 2026-08-03
**Status:** DRAFT — every numeric is PROPOSED until accepted in `gate_manifest.yaml → mu`; that
block is the numeric authority. Cited outside this note, probes are `MU-T1`…`MU-T5`.

**Question.** Which live-constructible **interface bundle** over the running game lets Qwen
answer mechanics questions about it, measured per probe — and does the winning profile support a
later goal-inference design (separate protocol)? MU selects among bundles of differing computed
content (§3); it is not a pure rendering comparison. It follows the ES closeout
([qwen-evidence-sufficiency-screen.md §11](qwen-evidence-sufficiency-screen.md)) and routes its
outcomes per the decision contract in §5.1.

## 1. Scope, custody, model

- Corpus: the six iteration games and their 18 selected sessions. One-shot and reserved games
  sealed. The frozen ES session-role assignment is reused unchanged: S = selection,
  C = confirmation, R sealed and untouched by MU.
- All conclusions are conditional on the six games; no unseen-game claim.
- Measurement model `Qwen3.6-27B-8bit`; MoE 35B-A3B 4-bit is development-only and
  non-evidentiary. Deterministic guided-JSON decoding; per-probe output schemas frozen before the
  first measured call.
- MU is an offline screen. It makes no score-stack conformance claim; any deployment claim
  requires a separate exact-stack protocol.

## 2. Probe ladder

Every probe has deterministic engine- or replay-derived gold; no raters, no annotation.

| id | task | output | gold |
|---|---|---|---|
| T1 legibility | state questions whose answers are verbatim-derivable from the packet (counts, locations, colours, relations) | closed JSON | template generator over the tracker registry |
| T2 identity | match second-frame objects (ids withheld, rows ordered by frozen hash) to first-frame objects across ≤3 frames | id mapping | tracker lineage |
| T3 mechanics | (state, action) → event summary: per-object moved(Δ) / appeared / disappeared / recoloured / no-op, plus level increment | event list | observation-layer extraction |
| T4 control | (state, target condition in the referent vocabulary) → one action achieving it | action | fork tables; any satisfying action scores |
| T5 terminal-action | pre-terminal state (pre-terminality **revealed** by the prompt) + legal action set → completing action | action | terminal contrasts; fork negatives; any completing action scores |

- T3 queries take two forms: executed-action (state beyond the shown prefix; gold = recorded
  outcome) and fork-action (alternative action at a shown state; gold = fork outcome). The shown
  prefix never contains the queried outcome.
- MOUSE action sets are reduced by the bounded fork-representative policy wherever a closed
  action set is required (T4, T5).
- T5 measures **local discrimination at a known pre-terminal state**, not goal induction from
  ordinary states or long-horizon evidence; the continuation claim is narrowed accordingly
  (§5.1).
- **Anchor distribution, and what it narrows.** The reused fork corpora exist only at
  completion pre-states, so T3-fork, T4 and T5 can only anchor there — boards one action from a
  completion, which are plausibly atypical (near-solved, constrained affordances). T4 is a
  funding probe (§5.1), so this binds a funding decision: **a T4 screen-positive licenses the
  claim "the winning interface supports control near a completion", not "…supports control from
  ordinary states"**, and a continuation protocol must carry the arbitrary-state question rather
  than inherit an answer. `T3-executed` is the only mechanics evidence anchored at arbitrary
  in-level states, and at the accepted cohort it is one case per game per role — reported as a
  contrast against `T3-fork`, never pooled silently with it.
- T1 is a gate, never a selected or screen-positive cell: an arm failing T1 on S is
  **ineligible for T2–T5 selection**, and its T2–T5 results are reported but not interpreted as
  reasoning failures. On C, a verdict requires the arm's own measured T1 there.
- Parse, schema, and context failures score 0 and stay in the denominator.

## 3. Representations

Every arm starts from the same evidence window with the same withholdings, but the arms are
**interface bundles of differing computed content**, and the estimand is **bundle selection**:
`grid` ⊂ `objects` ⊂ `events` ⊂ `card` add computed layers, `map` is deliberately lossy,
`verbal` is computed from the object registry, and `film` re-renders `grid` exactly. A
difference between adjacent nested bundles identifies the added layer (ES §4.2 precedent: only
the added information is identified); `grid` vs `film` is the only matched-information
pure-rendering contrast; `map` and `verbal` are ranked as bundles, never attributed to
formatting alone. Presentation variables (legend, coordinate order, colour naming, upscale) are
frozen per representation at manifest acceptance — one canonical form each, no per-game tuning.
Only online-constructible arms are deployment-relevant; any oracle variant is a labelled
ceiling.

| name | content |
|---|---|
| `grid` | P0: exact indexed grid text + legend + deterministic deltas |
| `objects` | P1-live: `grid` + runtime object/component table with referent aliases |
| `events` | P2-live: `objects` + relation, identity-lineage, and event tables |
| `card` | `events` + per-action effect catalogue: event-type distribution per action id / click cluster, with context splits, accumulated from the shown prefix only |
| `map` | coarse semantic map: each object one glyph on a downsampled lattice; deterministic construction rule frozen before measurement |
| `verbal` | deterministic template sentences over the event stream ("UP: blue 3×3 moved (12,4)→(11,4); nothing else changed") |
| `film` | successive delta-only frames (changed cells only) over the shown prefix window |

P0/P1-live/P2-live and the referent-alias protocol reuse `agent/harness/es_questions.py`;
extraction, lineage, forks, and terminal contrasts reuse `gi2_observation.py`, `gi2_traces.py`,
and `gi2_forks.py`. The shown-prefix window per probe is frozen at manifest acceptance.

*Correction, 2026-08-03 (review).* **`card` is a ≤4-sample catalogue, and its claim is narrowed
to that.** The catalogue accumulates from the shown prefix, so it holds at most
`prefix_window` transitions — four, or two for T2. An earlier justification in
`mu_probes.build_catalogue` called thin distributions "a fact of online construction, not a
defect to be repaired with history the deployed agent would not have"; that was **wrong**, since
a deployed agent carries its whole episode history. The real constraints are the context ceiling
and the strict `events` ⊂ `card` nesting this section's estimand argument rests on — a
session-prefix catalogue would break that nesting, because `card` would then hold evidence
`events` does not. Consequence for the read: **`card` ≈ `events` is partly a window artifact**
and may not be reported as "an effect catalogue does not help a deployed advisor". A
session-prefix catalogue is the deployment-faithful object and remains a legitimate future
bundle under this estimand, at the cost of the nesting property; it would be a new arm in a new
registration, not a redefinition of this one.

*Correction, 2026-08-03 (implementation).* `es_questions.py` builds the ES partition and dose
inventory; it contains no packet renderer, because ES's own packet builder is a later module. MU
therefore reuses from it what exists — the frozen session-role assignment, republished in
`logs/es_inventory.json` — and renders P0/P1-live/P2-live itself in `mu_render.py` to the ES §4.2
content definitions. The referent-alias protocol is MU's own, built to ES §4.1's rule (observable
descriptors, never source ids); see §8.1.

## 4. Floors

One model-free floor per probe, computed from the same packet: T1 template look-up (must be
~exact by construction), T2 greedy appearance match without the tracker, T3 modal effect from the
catalogue, T4 nearest satisfying fork by state similarity, T5 catalogue-ranked action frequency.

A confirmed cell is **screen-positive** — deliberately not "a capability": at the accepted
cohort C holds 12 cases per probe, so one binary case moves game-macro by 0.083. Both margins
were set to 0.09 — the smallest value strictly above that quantum — so a one-case gap reads as a
tie rather than as evidence (§8.3 item 4). The verdict
requires all three, on C: the arm's own measured T1 passes the legibility gate there; Qwen's
game-macro exceeds the floor's by the margin; and Qwen beats the floor's per-game mean in at
least the manifest's minimum number of games — the paired per-game comparison, so a one-game
spike cannot carry the verdict. All numerics live in the manifest.

## 5. Design and selection

- Factorial S pass: all representations × all probes; case rates averaged within game;
  game-macro with equal game weight.
- Selection on S, T2–T5 only: contenders are the arms passing the T1 legibility gate on S; among
  them the highest game-macro wins (margins in the manifest). No S-legible arm → the probe
  records `no_legible_arm` and has no C pass — that outcome routes through §5.1, never through a
  relaxed gate.
- C runs the selected arm on every T2–T5 C case, **plus T1 on every unique selected arm** (so
  confirmation legibility is measured for every arm the profile uses), plus floors.
- Context audit before freeze: every canonical request rendered through the exact
  tokenizer/template; no silent trimming; an infeasible row is an availability failure for that
  arm.
- Call budget derived from the case inventory at partition time; enters the manifest before any
  call. The C pass depends on the number of unique selected arms (1–4), so the budget prices the
  worst case.

### 5.1 Decision contract

| outcome | condition (numerics in `gate_manifest.yaml → mu → decision`) | routing |
|---|---|---|
| stop | no arm passes the T1 gate on S for any probe, **or** no selected cell among {T3, T4} is screen-positive on C | this representation menu is exhausted for Qwen mechanics use; advisor work proceeds programmatic-only (catalogue floors); a new menu requires a new registered protocol |
| continue | at least one of {T3, T4} screen-positive on C | fund the continuation protocol — goal inference over the winning interface — as a separately registered protocol |
| adopt | never from MU | MU is offline; adoption requires a separate exact-stack protocol plus the `docs/README.md` register + dated SPEC amendment route |

T5 informs the continuation design but cannot fund it alone: it is terminal-action
discrimination at a revealed pre-terminal state, not goal induction. A probe whose C read is
`t1_unmeasured_on_C` or `arm_illegible_on_C` can never be screen-positive.

Two scope limits travel with the verdict and must be quoted with it:

- **`continue` is licensed at the anchor distribution the funding cells were measured on.**
  T4 and T3-fork sit at completion pre-states (§2), so a continuation protocol inherits the
  interface choice, not an arbitrary-state control claim; it must register that question itself.
- **`stop` means no funded goal-inference continuation** — it is not a finding that Qwen is
  useless on this interface. A T2- or T5-positive cell under a `stop` verdict is still a
  reported component result, and the "programmatic-only" routing above governs *goal inference*,
  not every possible use of an identity or terminal-action subtask. Reopening one of those as an
  advisor component needs its own registered protocol, not a re-reading of this one.

## 6. Order of work

1. Zero-call: catalogue builder, gold generators, renderers (`map`, `verbal`, `film` new; the
   rest reused), floors, output schemas, case inventory.
2. Bring-up against the live measurement stack (`--bringup`, discarded synthetic calls):
   per-call latency at MU's prompt sizes and guided-JSON validation. The freeze refuses
   without its artifact and until the manifest carries its measured numbers as accepted
   values → then manifest acceptance + freeze.
3. Measured S pass.
4. C confirmation of the selected profile (selected arms + their T1 + floors).
5. Read: apply §5.1. A continuation (goal inference over the winning interface) is a separate
   protocol with its own registration; T5 informs it but does not discharge its goal-inference
   burden.

## 7. Artifacts

- `agent/harness/mu_probes.py` — gold generators, floors, output schemas.
- `agent/harness/mu_render.py` — the seven renderers.
- `agent/harness/mu_screen.py` — inventory, freeze, run, score, summarize.
- `logs/mu_inventory.json`, `logs/mu_bringup.json`, `logs/mu_freeze.json`, `logs/mu_raw.jsonl`,
  `logs/mu_results.json`.
- Regressions: `tests/test_mu_probes.py`, `tests/test_mu_render.py`, `tests/test_mu_screen.py`.

---

## 8. Implementation — step 1 built, 2026-08-03

§6 step 1 is complete and zero-call. The three modules, the three test files, the DRAFT `mu`
manifest block, and `logs/mu_inventory.json` exist; **nothing measured has run**, and
`mu_screen.py --freeze` refuses while the block is DRAFT, so nothing measured *can* run before
acceptance. Each module's docstring carries its own determinizations; the ones that decide what
the screen measures are collected here.

### 8.1 Determinizations this note left open

- **Objects.** A MU object is a GI-2 A2 observable component (`gi2_observation`): same-colour
  4-connected, dropping only an unambiguous full-screen background. The modal-colour convention
  of `es_questions.pre_state_complexity` is a complexity metric, not an object registry, and
  filtering by it would delete legible objects.
- **Referent aliases** are state-local descriptor programs, not ids: `<colour>#<k>`, where `k`
  ranks that colour's objects by bounding-box top-left in reading order. The question states the
  *rule*, so every arm — including `grid`, which carries no object table — can resolve a
  referent, and an arm that cannot is failing legibility, which is what T1 measures.
- **Prefix windows** (transitions): T1 4, T2 2, T3 4, T4 4, T5 4. A window never crosses a level
  boundary or a RESET, and its tracker starts at the window's first state, so identity is
  window-local and every window is self-contained.
- **T2** relabels *every* query-state object `B1..Bm` in one frozen hash order and asks about
  ≤8 of them, each introduced by an anchor cell so the arms without an object table can still
  resolve it. The last transition's derived tables — identity, events, catalogue, verbal
  narration — are withheld in every arm, because they are the answer; its cell-level evidence is
  always shown.
- **T3 names a bounded set of referents** (4 per case) rather than asking for a complete event
  list. Measured reason: `logs/gi2_observation_catalogue.json` records ~21.8k splits and ~22.1k
  merges over 10,018 analysed frames — about two of each per frame. A complete per-object event
  summary is therefore neither answerable nor expressible in this note's vocabulary
  (moved/appeared/disappeared/recoloured/no-op). Objects whose outcome falls outside that
  vocabulary — split parents, merge children, reshaped components — are excluded from the named
  set rather than coerced into a label, and the exclusions are counted.
- **T3's `moved`** requires the post cells to be the pre cells translated by one exact (dr,dc).
  A drifting centroid is not a move.
- **T4's target-condition vocabulary** is `moves`/`disappears`/`recolours` over one referent,
  plus `appears` and `no_change`. A condition is used only when it is two-valued on every
  offered option and satisfied by at least one but not all of them.
- **T4/T5 option sets** are labelled `A1..An` in frozen hash order, so the recorded completing
  action never sits in a fixed position. Six options where the game affords them; ls20 and tu93
  advertise three actions, so there the offered set is the whole legal set and is never padded.
- **T1 is a gate, not a selectable cell.** Its floor is a template look-up over the registry and
  is exact by construction (verified: every T1 floor scores 1.00), so no arm can exceed it. Per
  §2 it gates *selection eligibility* on S and *interpretation* on both roles: an arm whose T1
  game-macro falls below `mu → floors.t1_legibility_gate` on S is ineligible for T2–T5
  selection, and its T2–T5 rates carry an explicit not-interpreted flag, since a low rate under
  a failed T1 is an illegibility result. On C, the screen-positive verdict requires the arm's
  own measured T1 there; the legibility flag is three-state (`True`/`False`/unmeasured), so an
  arm without T1 rows in a role is labelled unmeasured, never illegible.
- **Context feasibility is an anchor eligibility condition**, checked through the exact
  measurement tokenizer and chat template. An anchor is admissible only where all seven arms fit
  32,768 − 512 tokens. Screening at selection rather than discarding afterwards keeps the
  factorial matched: every arm sees exactly the same cases, which is what makes an arm
  difference an interface difference on identical evidence (§3's estimand — bundle selection,
  not rendering attribution).

### 8.2 What the zero-call build measured

Numbers below are at the **operator-reduced cohort** (`cases_per_probe_per_game_per_role`
3/3/4/3/3 → 2/2/2/2/2, 2026-08-03, after bring-up priced the pass). `t3_executed_share` moved
3→1 with it: the share is bound to the T3 count, and at 2 it would have left zero fork-form
cases and silently dropped half of T3's design.

| fact | value |
|---|---|
| cases | 120 — 60 S, 60 C, over 6 games × 2 roles × 5 probes; T3 splits 12 executed / 12 fork |
| shortfall | none (the reduction cleared the m0r0 S T4 shortfall) |
| anchors rejected | 11 context-infeasible (**all m0r0**), 8 probe-ineligible |
| median prompt tokens | map 1.4k · verbal 4.0k · film 6.2k · grid 6.4k · objects 9.1k · events 12.6k · card 12.7k |
| max prompt tokens | card 23.8k, against a 32.3k ceiling |
| call budget | 516 worst case (420 S + 48 C selected arms + 48 C/T1 × unique arms), 568 with the 10% reserve |
| S-pass prompt tokens | 3,253,873 |

m0r0 is the binding constraint: one of its levels carries **879** observable components, which
is what the feasibility rule exists for. The fork-bearing probes (T3-fork, T4, T5) can only
anchor at completion pre-states, since that is where the reused fork corpora exist.

### 8.3 What acceptance still owes

1. Every numeric in `gate_manifest.yaml → mu` is PROPOSED and needs acceptance or replacement.
2. ~~Per-call latency is unmeasured~~ — **measured 2026-08-03** (`logs/mu_bringup.json`, 12
   discarded calls). The stack is **prefill-bound at ~276 tok/s**: thinking is off and guided
   JSON emits ~8 tokens, so latency is `prompt_tokens / 276 + ~1 s` — 15–19 s at 5.0k tokens,
   54–63 s at 14.9k, 85–91 s at 24.7k. The VP-derived ~29 h lower bound previously carried here
   **does not describe this workload** and is withdrawn: VP's p50 came from thinking-enabled
   decodes. The reduced S pass is ~2.6 h serial, and because rows are ordered by `case_id` a
   resumable run completes T1 (the legibility gate, all seven arms) at ~0.7 h, T2 at ~1.3 h, T3
   at ~2.0 h, T4 at ~2.7 h. Staged reads therefore need no protocol change, and `--score`
   still refuses to select off an incomplete pass.
3. ~~Guided JSON unexercised~~ — **validated 12/12 live**, so the frozen `model.decoding`
   stands and `--freeze`'s `guided_json_validated` precondition is met.
4. **What the reduction costs, recorded because it binds the read:** each role now holds 12
   cases per probe, so one binary case moves a game-macro by 0.083. Both margins were raised to
   **0.09** in the same decision — derived as the smallest value strictly above one quantum,
   `1 / (6 games × 2 cases)`, not chosen — because a margin under one quantum is cleared by any
   nonzero difference and is therefore not a margin. Effect: a one-case gap is a tie, so the
   cheaper arm wins it in selection, and a screen-positive needs more than one case of
   separation *and* `screen_positive_min_games` (4 of 6, paired per game). §4's refusal to call
   a confirmed cell a capability rests on the cohort size, not on the margins. Enlarging the
   cohort after the freeze is a dated erratum, and recomputes both margins from the same rule.

## 9. Review revisions — 2026-08-03

Applied from the six-finding review; each is wired into code and manifest, not only prose:
(1) §5.1 decision contract added and the ES closeout recorded in
[qwen-evidence-sufficiency-screen.md §11](qwen-evidence-sufficiency-screen.md), with the
transition pinned in `mu → predecessor`. The contract is **computed**, not left to a reader:
`mu_screen.decision_verdict` publishes `stop`/`continue`/`pending` with its reason and routing
into `logs/mu_results.json`, `mu → decision.funding_probes` and
`decision.min_screen_positive_cells` are mirror-checked like every other applied number, and
`adopt` is unreachable by construction. An unfinished S or C pass reads `pending`, never `stop`:
an incomplete pass is not evidence of absence, the same rule that already forbids selecting off
a half-finished S pass; (2) estimand rewritten as interface-bundle selection
(§3, `mu → representations.estimand`); (3) T1 now filters S selection eligibility, C runs T1
for every unique selected arm, and the verdict requires the arm's own C T1
(`mu_screen.select_profile` / `plan_rows` / `screen_positive_verdict`); (4) "capability"
renamed **screen-positive** with a paired per-game consistency requirement
(`mu → floors.screen_positive_min_games`); (5) bring-up (latency + guided JSON) is a freeze
precondition (`mu → bringup`, `--bringup`, enforced in `build_freeze`); (6) T5 renamed
terminal-action discrimination and barred from funding the continuation alone (§2, §5.1).
