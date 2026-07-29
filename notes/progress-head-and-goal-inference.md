# What the progress head can and cannot learn — 2026-07-29

**Scope.** A design argument about SPEC §5's `P(progress event)` head and §9's G0, raised while
walking SPEC §4.9 interface item 3 on A2. It **decides nothing** — §9 is a build-phase section and
this is not a pre-registration. Where it bears on a registered value it says so and points at the
block. New *measurements* here are reproducible; everything else is argument.

---

## 0. The question

> Can `P(progress event)` be built so that it generalizes to a game it has never seen?

Short answer: **not as a pre-action predictor, and the spec's own numbers say so.** But the
alternative — "let the local model do general goal inference" — is the configuration S1 measured,
and goal inference is that configuration's single largest failure. Neither option works alone.

---

## 1. Measured: ARC-AGI-3 reports exactly one progress signal

Key union over **all 340 replay files, 44,748 rows** (`data/human_replays/kaggle_mirror/public_games-dataset`):

| per-frame key | |
|---|---|
| `game_id` · `frame` · `guid` · `full_reset` | identity and framing |
| `action_input` · `available_actions` | action space |
| `levels_completed` (int) · `win_levels` (int) | **the only progress counter** |
| `state` ∈ {`NOT_FINISHED`, `GAME_OVER`, `WIN`} | episode status |

Plus `won` · `played` · `total_actions` · `cards` on 68 session-summary tail lines.

**There is no score field. In any of the 25 games.**

```bash
.venv/bin/python -c "
import json,glob,collections,itertools
k=collections.Counter()
for f in sorted(glob.glob('data/human_replays/kaggle_mirror/public_games-dataset/*/*.jsonl')):
    for line in itertools.islice(open(f),150):
        try: d=json.loads(line).get('data')
        except Exception: continue
        if isinstance(d,dict): k.update(d.keys())
print(sorted(k))"
```

Terminal is therefore a **metadata read**, not an inference: `levels_completed > prev`
([`s2_corpus_census.py:192`](../agent/harness/s2_corpus_census.py:192)). Measured rate **1,614 /
180,144 = 0.8959%**.

That rate is not a logging artifact. Against the 183 human level baselines in
[`logs/s2_arc_conventions.json`](../logs/s2_arc_conventions.json) — median 60 actions/level, mean
93.6, p25 32 — the reference clears a level every **112** actions, implying 0.90%, against a
human-mean-implied 1.07%. Slightly worse than human, which is what a reference agent should look
like.

---

## 2. What that does to §5's target

SPEC §5 freezes the head's target as *"a predeclared observable event class (level/score marker or
registered progress signature)"*. Three disjuncts; on an unseen game **one** survives:

| disjunct | on a game never seen |
|---|---|
| **level marker** | ✅ `levels_completed` increments. Universal, platform-reported, needs no model. Fires at **0.90%** of transitions |
| **score marker** | ❌ **does not exist in ARC-AGI-3** (§1 above) |
| **registered progress signature** | ❌ *registered* means per-game or per-family. Nothing is registered for a game you have not seen |

> **The head generalizes exactly as far as its target is platform-reported, and the platform reports
> only level completion.**

---

## 3. The data objection is correct

For the one transferable target, the supply after §13.5's 17/8 partition is **850–1,287 replay
terminals across 17 dev games ≈ 50–76 per game** (SPEC §3.2). The same table rates this artifact at
acquisition difficulty **4–5**, against **0–2** for the factual heads, which have 701M changed-cell
labels.

A *pre-action* predictor of "will this action complete the level" requires the goal. 50–76 examples
per game does not teach a goal that transfers to a different game. **Procedural positives are
unbounded but do not fix this — see §5.**

> **The count is not even the binding constraint.**
> [`training-data-master.md` → *Cross-game sample-size audit*](training-data-master.md) makes the
> sharper version of this argument: for a target that depends on a game's goal, the independent
> domain is the **game**, not the row. After the §13.5 partition that is **17 domains**, and no
> volume of replays, branches or forked successors from those games raises it. Alias and Delay add
> two procedural families, not new game semantics. This note argues the *target* does not transfer;
> that audit argues the *sample* could not support it even if it did.

---

## 4. But "let the LLM do it" is the configuration S1 measured

The S1 reference **is** an LLM doing general inference with no learned progress head: Qwen3.6-27B-FP8
on the Tufa Labs duck harness, LB 1.21 ([`s1-reference-freeze.md`](s1-reference-freeze.md)).

Measured across 75 labelled failure episodes, promoted at κ 0.7207:

| category | primary | episodes | κ (primary) | addressed by |
|---|---:|---:|---:|---|
| **`goal_unknown`** | **44/75 (58.7%)** | 63/75 (**84%**) | 0.7945 | §9 G0 + §4.6 |
| `action_semantics_unknown` | 15/75 (20%) | 37/75 | 0.6296 | §4.3, §5, §11 |
| `exploration_or_probe_selection` | 4/75 (5.3%) | 34/75 | 0.6512 | §7, §4.6 |
| `progress_signal_misinterpretation` | 1/75 (1.3%) | 8/75 | 1.0 | **§5 progress head** |

**Goal inference is the reference's #1 failure, by 3× over the next category.** Moving the job to the
local model is not a fix — it is the baseline whose failure ranks the build order. SPEC §9's own
motivating example is the failure shape: S1-d episode `sc25`, *"the agent reached the state its own
goal model called the solution and the level did not complete… the target was the wrong **type** of
object."*

Note also the split in that table: the progress head addresses
`progress_signal_misinterpretation` (**1/75 primary**), not `goal_unknown` (**44/75**). The head was
never the artifact carrying the goal problem.

---

## 5. The phantom-class problem *(new, and it bites the S2 draft)*

`gate_manifest.yaml → s2` proposes progress-event prevalence at **0.05**, ~5.5× the 0.90% anchor, on
the correct ground that a generated source makes prevalence a design parameter. Walking item 3 on
A2 produced a proposal that progress events be **sub-terminal markers** rather than terminals, so
that 0.05 does not imply ~20-action levels (below the human p25 of 32).

**That proposal has a cost that was not priced.** On the procedural generator you can define
sub-terminal markers because you own the goal. On a hidden game **there is no observable sub-terminal
signal at all** (§1). So a head trained at 5% sub-terminal prevalence and deployed on a hidden game
is not miscalibrated — **it is predicting a different event class.**

The registered `calibration_obligation` says to *"record the reweighting or the prior correction."*
**Reweighting fixes a prevalence mismatch. It cannot fix an event-class mismatch.**

The trilemma, stated honestly — nothing wins cleanly:

| | positive count | level length | at deployment |
|---|---|---|---|
| (a) progress = terminal @ 5% | ✅ good | ❌ ~20 actions, below human p25 of 32 | ✅ class matches |
| (b) progress = terminal @ 0.9% | ❌ thin | ✅ realistic | ✅ matches, but "wastes the one degree of freedom procedural data offers" |
| (c) progress = sub-terminal @ 5% | ✅ good | ✅ realistic | ❌ **phantom class** |

---

## 6. What survives: terminal-as-subset, plus a structured posterior

**On the head — terminal ⊂ progress.** Construct the procedural progress predicate as a *graded*
signal whose extreme case is level completion, so the terminal event is a strict subset. At
deployment the head degrades to the terminal slice rather than predicting a class with no referent,
and **only terminal-slice performance is ever claimed on real games.**

This is what SPEC §9.1 already scopes: G0-R does *"prerequisite and partial-progress grading ·
goal-family classification **where synthetic truth exists**."* Partial-progress grading was already
scoped to synthetic ground truth; the A2 draft simply did not carry the scope through.

**On the goal — neither a learned predictor nor raw LLM.** SPEC §9.3's deployment adaptation protocol
is explicitly non-gradient: backbone frozen, and each observed completion updates a **per-family goal
posterior over predicate classes** · prototype/retrieval memory of terminal transitions · ledger goal
parameters (counts, regions, orderings) · optional in-context examples for the executive.

The evidence that this hypothesis space is small enough to be tractable is **already measured** —
[`logs/s2_goal_predicates_labelled.json`](../logs/s2_goal_predicates_labelled.json), all 25 games,
blind re-rate **κ 0.947**: 7 observed classes, the top two covering 15/25 games, two classes with
zero instances.

> **The division of labour that survives both the data objection and S1's measurement:** the local
> model **proposes into a small measured hypothesis space** · the posterior **updates from observed
> completions**, which are free metadata reads · the learned head **never carries the goal**.

---

## 7. Consequence for the head's role

`P(progress event)` should be **only** what §9.1 needs it to be: the **frozen baseline** against
which G0-A's credit is measured. §5 freezes its target precisely so that baseline cannot drift. *A
baseline is allowed to be weak — that is what makes the credit interpretable.*

⚠ **The risk is §9's decision table.** If G0-A does not integrate, this head's ranking silently
becomes the deployed goal-directed signal in the fast loop — a myopic head ("does this fire a
progress event *now*", never long-term utility) carrying the load that `goal_unknown` says is
dominant. That promotion should be a declared branch, not a default.

**It is not an offline artifact.** §5 is *Tier 2 — cheap action evaluator*: one encoder pass per
step, heads dense over the spatial map, O(1) in candidate count, inside §2's fast loop. It runs on
every game including hidden ones. Only its *training* is offline, and only its terminal slice is
verifiable.

---

## 8. What settles this, and when

**D0, W1, pre-registered and frozen before inspection** (SPEC §10.1):

> first-level progress: **≥ 1 progress event on ≥ 60% of unseen tutorial levels within 200 actions**

That measures the local model on held-out environments — the claim in §4 above, directly. Declared
failure branch: *"the slow loop is explicit hypothesis search plus evaluator probe selection;
two-rate control does not depend on an LLM."*

**Cheap-evaluator retention, R1** (§1.1 decision map): decided by branched audits, fallback
**archive + guards** — no learned ranker at all. "The ranker does not earn its place" is already a
pre-declared branch.

**Fork G-F, Aug 22** — §9.6 Branch A proposes building the Order and Count goal families at ≥ 5
build-days. Those are the two the public set exercises least (Order primary in 1/25, Count in 0/25).
This note strengthens the case for weighting Fork G-F toward *adaptation machinery* over additional
families, but does not settle it: the hidden set is not the public set.

---

## 9. What this changes in registered documents

| finding | where it lands | status |
|---|---|---|
| no score field in ARC-AGI-3; §5's target names a nonexistent observable | `s2.acceptance.progress_event_prevalence.event_definition` | recorded 2026-07-29 |
| terminal ⊂ progress; claim only the terminal slice at deployment | same block | PROPOSED 2026-07-29 |
| reweighting cannot fix an event-class mismatch | same block, amends `calibration_obligation` | PROPOSED 2026-07-29 |
| progress head should stay a frozen baseline, never the deployed ranker | **SPEC §9** — build-phase, not S2 | **open; no spec amendment proposed** |
| §5's "level/score marker" wording | **SPEC §5** — factually wrong on the score half | **open; needs a dated amendment, not an implicit fix** |

The last two are deliberately left open. SPEC is normative and *"never amended implicitly by a
result"* — a note cannot amend it, and neither can a manifest block.
