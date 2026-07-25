# S0 + S1 — Day-by-Day Execution Plan

**Written 2026-07-25.** Operationalizes §3 and §4 of
[`arc-agi-3-decision-experiments.md`](arc-agi-3-decision-experiments.md). That document is the authority;
where this one disagrees, it is wrong. Nothing here re-decides scope — it fixes dates, deliverables, exit
criteria, and the escalation rules the sprint document leaves open.

**Covers 6.5 of the sprint's 18.5 focused days.** S0 (0.5 d) + S1 (6 d), Mon Jul 27 → Tue Aug 4.

---

## 1. Calendar and float

| Day | Date | Block | Budget |
|---|---|---|---:|
| — | Sat–Sun Jul 25–26 | **Pre-flight** (admin, off-budget) | 0 |
| 1 AM | Mon Jul 27 | **S0** — starter submission + constant verification | 0.5 |
| 1 PM | Mon Jul 27 | **S1-a** — reference freeze + pre-registration | 0.5 |
| 2 | Tue Jul 28 | **S1-b** — reproduction to first scored level | 1.0 |
| 3 | Wed Jul 29 | **S1-c** — measurement harness + reset experiment | 1.0 |
| 4 | Thu Jul 30 | **S1-d** — failure instrumentation | 1.0 |
| 5 | Fri Jul 31 | **S1-e** — the reference run, labelled | 1.0 |
| 6 | Mon Aug 3 | **S1-f** — packaging, offline bundling, baseline submission | 1.0 |
| 7 AM | Tue Aug 4 | **S1-g** — close-out memo and build order | 0.5 |
| | | **Total** | **6.5** |

**Float is zero.** 18.5 focused days at 5/week from Jul 27 lands on ~Aug 20 against a Aug 22 hard stop.
Any day lost in S0/S1 comes out of S3 (objective screening) or S4 (advisor test) — the two blocks that
carry the actual decision. Treat the §7 descope ladder as live from Day 3, not as a contingency to
consider later.

---

## 2. Pre-flight — Sat–Sun Jul 25–26, off the budget

Mostly waiting and account admin; it does not need a focused day, and front-loading it protects Day 1.

- [x] Kaggle account, competition rules accepted, team registered. *(Rules acceptance is yours to click.)*
- [x] **Kaggle CLI installed and authenticated** — `kaggle competitions list` returns without an auth
      error. Not only for submitting: Day 6's offline bundling publishes the weights as a Kaggle
      dataset/model artifact (§4.7), so the CLI is on the critical path before S1-f, not just S0.
      *(CLI 2.2.4, `auth_method: ACCESS_TOKEN`; see `notes/s1-verification.md`, "Pre-flight Kaggle CLI
      access". The Kaggle MCP server was evaluated and not adopted — reasons recorded there.)*
- [x] ARC-AGI-3 API credentials issued and a `GET` against a public game returns 200 from your machine.
- [x] Clone the official starter, run it locally once, confirm it plays at least one action.
- [x] Inventory the accelerator you will actually develop on — model, VRAM, driver, CUDA. Write it down;
      Day 1's reference freeze depends on it. *(`notes/s1-verification.md`, "Pre-flight accelerator
      inventory". Apple M5 Pro / 64 GB unified / Metal 4 / **no CUDA** — the no-CUDA finding is a screen
      on Day 1's reference candidates, not a footnote.)*
- [x] Create the repo scaffold (§8).

**Exit:** you can reach the API and run the starter locally. Nothing else.

---

## 3. S0 — Starter submission — Day 1 AM (0.5 d)

The purpose is not a score. It is to prove the external execution path — Kaggle's validation pass *and*
its hidden rerun — before any of it is entangled with your own agent. On Day 6 you drop the reproduced
baseline into a path already known to work, and any failure there has one cause instead of two.

### 3.1 Submit

1. Submit the official starter **untouched**, or with the single smallest edit required to run.
2. Wait for validation *and* the hidden rerun to both report. A green validation with a failed rerun is
   the exact failure mode this step exists to catch.
3. Record in `submissions/ledger.md` (§8): submission ID, commit hash, wall-clock to result, any warning
   text, and the score if one is returned.

**If the rerun fails:** diagnose and fix, but **do not serialize the week behind it.** The quota is
**1 submission/day** (V13), so each retry costs a calendar day — blocking all other work on a
one-attempt-per-day loop would burn the sprint. Fix on Day 1, resubmit Day 2 AM, and let S1-a and S1-b
proceed in parallel: the starter path and the reproduction are independent, and waiting on a rerun is
wall-clock, not focused work.

**The one hard interlock:** do not package the *baseline* (Day 6) until the starter path is green.
That is the point where two unknown failures would actually get conflated, and it is the reason S0
exists. Escalation in §7 item 0.

### 3.2 Verify the constants — same block

`decision-experiments.md` §2 marks these as unverified. Record every answer in
`notes/s1-verification.md` with the URL and date you read it, because several are load-bearing for
decisions made later this week.

**Six are already resolved** (checked 2026-07-25 against the Kaggle overview, Kaggle rules, and the
official Paper Prize page) and are recorded as verified in `gate_manifest.yaml`. Day 1 covers the
remainder. Three of the resolved ones **changed the plan** and are marked ⚠.

| # | Item | Consequence if different than assumed |
|---|---|---|
| V1 | ✅ Final submission Nov 2, 23:59 UTC — confirmed | Whole-sprint calendar |
| V2 | ✅⚠ **Nov 8 is the official paper deadline.** ~Nov 5 is an *internal* tie-break buffer, never cite it as official; ties favour the earlier entry | §9 paper cadence |
| V3 | ✅ Oct 26 entry **and** team-merge — now publicly listed, no longer notes-only | Registration deadline |
| V4 | Feature freeze Oct 18 — project-internal target, not official; nothing to verify | The ~8.4 construction weeks |
| V5 | ✅ **Competition mode: level resets only; game resets become level resets** | Reset experiment design (§4.4) |
| V6 | ✅ **One `make()` call per environment in competition mode** | You get one shot per game per scorecard — the reset experiment must be designed around this, not discover it |
| V7 | ✅ **One scorecard; in-flight scorecards are hidden** | You cannot read score during play. Materially constrains exploration strategy *and* forces the reset experiment to be close-then-read |
| V8 | ✅ Scoring: (human actions / agent actions)², cap 1.15, level-position weighted, equal across games | Reverse-engineering the action denominator in §4.4 |
| V9 | ◐ **600 req/min confirmed for the online API; no separate Kaggle-local cap found** | Per-action latency budget |
| V10 | ⚠ Runtime envelope — ~8 h wall-clock and ~10 actions/s remain *working assumptions*, not verified constants | The viability threshold on latency must be derived from the starter and reference runs |
| V11 | ✅⚠ **Licensing is four buckets, not one.** Entrant-authored code/methods → CC0/MIT-0 · third-party material → its own separate sharing requirements · models and weights → Kaggle's specific rules · winner license → CC-BY 4.0 | Day 1 PM license screen. **Weights that are not CC0/MIT-0 no longer disqualify a reference** — the earlier flat reading would have wrongly eliminated candidates |
| V12 | ✅ **ACTION7 is present in the local enum and the untouched Kaggle starter uses the same dynamic `arcengine.GameAction` interface; per-game availability remains observation-dependent** | Action-space parity between the two |
| V13 | ✅⚠ **1 submission/day, 2 final submissions** — not 5/day | Rewrites §4.7's repair branch and §7 item 0: no same-day retry, so a failed submission costs a day |
| V14 | ✅ **Confirmed: a reproduced baseline does *not* discharge the Paper Prize requirement** — the submission must demonstrate the paper's approach | §9's method-bearing submission path is a requirement, not a contingency. Under 1/day, warming it late is expensive |

**Exit S0:** starter submission accepted through *both* passes; V1–V14 recorded with sources; ledger row
written.

---

## 4. S1 — Baseline reproduction

**The question, kept in view all week:** *how far are we from a competitive working baseline, and which
failures look improvable?* A template that packages cleanly answers neither. The named failure mode is
that the reproduction proves painful, you quietly fall back to the template, and S1 gets marked done
without answering its question — §7 exists to make that a decision rather than a drift.

### 4.1 S1-a — Reference freeze and pre-registration — Day 1 PM (0.5 d)

**Freeze before starting.** Into `notes/s1-reference-freeze.md`, and into `gate_manifest.yaml`:

- repository URL and **exact commit hash**
- exact model and weights, with the weights' own license
- **license interpretation across all four buckets** (V11), written as an argument, not a verdict
- quantization
- accelerator and the batching pattern you will run it under
- expected public behaviour
- known score or explicit reproduction target
- **permitted deviations** — enumerated in advance; anything outside the list is a deviation to log

**Freeze two, not one.** Name a primary and a ranked alternate under the same criteria. §7's escalation
sends you to the alternate, not to the template, and choosing the alternate on Day 4 under time pressure
is choosing badly.

**Screen license first — but screen the right thing.** V11 resolved this into four independent buckets,
and the earlier flat "must be CC0/MIT-0" reading would have wrongly eliminated usable candidates:

| Bucket | Requirement | Effect of a failure |
|---|---|---|
| Entrant-authored code and methods | CC0 / MIT-0 | Yours to control — a constraint on what you write, not a screen on the reference |
| Third-party material | Its own separate sharing requirements | Usually a **compliance step**, not a disqualification |
| Models and weights | Kaggle's specific rules for models/weights | **The real screen.** A failure here means the reference is local-measurement-only and Day 6 needs a different payload |
| Winner license | CC-BY 4.0 | Applies to the winning submission; affects nothing about candidate choice |

Only a models-and-weights failure changes Day 6's payload. Record *which bucket* any concern falls in —
"the license is a problem" is not an actionable finding.

**Selection criteria, in order:** (1) the models-and-weights bucket clears; (2) fits your accelerator at the intended
quantization with the compact models resident; (3) reports a public-game score you can target; (4) the
harness is reusable — you are accepting its harness rather than building one, and that is where the
saving comes from; (5) code is legible enough to instrument.

**Also this block — pre-register S1 into `gate_manifest.yaml`** (§10 of the sprint doc requires it, with
numbers, before the step). The file is scaffolded with `PROPOSED` values; your job is to accept or
replace each one, then set `status: frozen` and commit. Specifically: frozen baseline specification ·
viability thresholds · operational definitions for all 13 failure categories · the blind re-rate
sampling rule.

**Exit:** freeze document written; `gate_manifest.yaml` S1 block frozen and committed; alternate named.

---

### 4.2 S1-b — Reproduction to first scored level — Day 2 (1.0 d)

Get the frozen reference running locally against the live API on public games.

1. Vendor the reference at the frozen commit, unmodified, in `agent/reference/`. Keep every change as a
   patch file, never an in-place edit — the diff *is* the "permitted deviations" audit.
2. Weights resident, quantization as frozen, first end-to-end episode on a public game.
3. **Log against the Day-4 taxonomy, not against convenience** — §4.2.1. Day 4 promises retrospective
   labelling of Day 2–3 logs; a row of hashes and timings cannot support it, and the evidence is
   unrecoverable once the episode is gone.
4. **Determinism check** — same seed, same action sequence, twice: identical observation sequence?
   Everything on Day 3 and Day 5 assumes you can replay.

**Exit (hard):** ≥1 scored public-game level completed locally; the transition log for it on disk; the
field-availability table (§4.2.1) filled.

**Miss this and you are behind.** Day 3 can absorb a half-day slip. Day 4 cannot — see §7.

#### 4.2.1 Transition schema — fixed before the first run

Every field below is required by at least one failure category. Write the schema now; the taxonomy is
already frozen in `gate_manifest.yaml` from Day 1, so this is a mechanical cross-map, not a design task.

| Field | Required by |
|---|---|
| `frame_before`, `frame_after` — **full grids, not hashes** | perception/parsing · hidden-state aliasing (needs both frames side by side) |
| `observation_hash` | aliasing detection · dedup key into the frame store |
| `action`, `coordinates`, `observed_delta` | baseline; action semantics |
| `candidate_action_set` at the step | coordinate unreachable · exploration/probe selection |
| `predicted_delta` (agent's own prediction, if exposed) | action semantics unknown |
| `agent_goal` / objective field | goal unknown |
| `agent_belief` — progress, reversibility, novelty | progress-signal misinterpretation |
| `reasoning_text` — raw, verbatim | reasoning inconsistency |
| `raw_model_output` (pre-parse) + `api_rejection` payload | invalid output/interface |
| `prompt_context_snapshot` + `retrieval_set` | retrieval or context |
| `effective_search_depth` / search trace | planning depth |
| `latency_breakdown`, `budget_counters` (wall-clock, tokens, actions remaining) | latency or budget |
| `metadata`, `level_markers`, `wall_clock` | baseline; progress attribution |

**Store frames content-addressed** by `observation_hash` in a side store, with the row carrying only the
hash. Rows stay small, frames dedup across repeated states, and nothing is lost.

**Record what the reference does not expose.** A vendored agent you did not write may have no goal field,
no predicted delta, no search trace. Fill a **field-availability table** on Day 2, and propagate it: a
category whose required evidence is unavailable is marked `unavailable` in the Day-7 ranking — **never
counted as zero-frequency.** An unobservable failure mode that silently ranks last would steer eight weeks
of construction away from a lever that may be the largest one. Where a field is missing and cheap to add,
adding it is a *permitted deviation* and goes in the patch file.

---

### 4.3 S1-c — Measurement harness — Day 3 (1.0 d)

Everything S1 promises to *measure*, instrumented and read once.

**Itemized per-action latency**, under the *actual* batching pattern — N parallel stateless game threads
over one shared GPU, not a single-threaded loop. A single-threaded number will mislead you by the
batching factor and it is the number the whole latency budget rests on. Break out: preprocess · encoder ·
branching × depth · ensemble · verification · policy · synchronization. Report median and p95, not mean.

**Hardware fit** — peak VRAM with the compact models co-resident, headroom, thermal/throughput
degradation over a full-length run.

**Legal-action reliability** — fraction of emitted actions the API accepts, and the rejection taxonomy.
This is threshold-gated in the manifest; below the threshold, interface work becomes the first build item
after Aug 22 regardless of what anything else shows.

**Reset and action accounting** — §4.4, run in this block.

**Public-game progress** against the frozen reproduction target.

**Exit:** `notes/s1-measurements.md` with every number above; the latency table generated by script from
logs, not typed by hand (§9).

---

### 4.4 The reset experiment — Day 3, inside S1-c

> *Gates nothing and configures everything.* It selects between two different agents; build the wrong one
> and eight weeks go into the wrong controller.

Two sub-questions, ordered. **R1 runs first and R2 depends on it** — if the level re-randomizes across
reset, arm B's "same scripted completion" is not the same completion and R2's estimator is invalid.

**R1 — Does a level reset preserve knowledge?**

One prefix replayed once establishes that *one prefix was repeatable once*. It does not establish that the
level is deterministic, still less that games generally are, and "everything learned transfers" does not
follow from it at all. R1 picks the global controller, so its sampling is preregistered rather than
improvised:

| Parameter | Value |
|---|---|
| Games | **≥2 distinct public games** — one game cannot support a claim about the environment class |
| Prefixes per game | **≥2 distinct**, one short (~10 actions) and one longer (~40), so a divergence that only appears with depth is reachable |
| Replays per prefix | **3** (i.e. 1 original + 2 replays) |
| Comparison criterion | **Exact frame-sequence equality at every step.** Record the first-divergence step index when it fails — *where* it diverges distinguishes a re-randomized initial state from stochastic dynamics, and those imply different agents |

**Four outcomes, not two:**

| Outcome | Meaning | Consequence |
|---|---|---|
| **deterministic** — every prefix, every game, every replay identical | Replay determinism holds across what was tested | Speedrun is available. Claim only what was tested: *tested prefixes replay exactly*, not "everything learned transfers" |
| **mixed** — deterministic in some games, not others | The property is per-game, not global | **No global controller is correct.** The agent must *detect* determinism per game at runtime and switch — itself a build item for §11, and one that would not have been discovered by a single-prefix test |
| **re-randomizes** — divergence everywhere | Only structural knowledge transfers | Speedrun off the table regardless of R2; exploration must generalize |
| **inconclusive** — divergence not reproducible across replays | Something else is varying (server state, timing, version) | Do not proceed to R2 on an unstable base; diagnose or record `blocked` |

**R2 runs only under `deterministic`.** Under `mixed`, R2 may be run *on a game that tested deterministic*
and its result reported as game-specific, never as a global finding.

Use a **scripted** sequence, not the agent. A stochastic policy makes the two arms incomparable and the
result uninterpretable.

**R2 — Does the scored action count accumulate across resets, or restart?**

#### Identifiability — the constraint that fixes the design

The arms must differ in **exactly one** thing: whether a reset preceded the scored completion. Running
them on *different games* breaks that. Each game has its own human-action baseline `H` and its own
level-position weights, so a score difference between two games confounds reset accounting with those two
unknowns and the experiment is not identifiable. **Same game, same level, independent scorecards.**

With game and level held fixed, `H` and the weight are identical across arms and cancel:

```
score = min(1.15, (H / N)²) × weight        →        √(score_A / score_B) = N_B / N_A
```

`H` never needs to be known. That is the point of holding the game fixed.

#### Preconditions — check before running, not after

| Precondition | If it fails |
|---|---|
| **Per-level score is exposed** at scorecard close | Level-position weighting mixes levels into one number and the ratio is underdetermined. Restrict both arms to level 1 only and close immediately; if even that is not separable, R2 cannot be run against the live scorer — record `blocked` |
| **V6 permits repeating a game across independent scorecards** | If one environment creation per game is a per-*scorecard* limit, this design works. If it is per-team-ever, no same-game design exists: fall back to **practice / non-competition mode**, and record explicitly that the result may not transfer to competition mode |
| **Neither arm saturates the 1.15 cap** | The ratio collapses. Choose `a ≈ 1.5 H` so arm A scores ≈0.44, well clear. Verify from the arm-A score before running arm B |
| R1 returned *deterministic* | See above — do not run R2 |

#### Arms

- **Arm A (clean):** scripted sequence completing level 1 in `a` actions. No reset. Close, read.
- **Arm B (wasteful):** `w` deliberately wasted actions → RESET → the *same* scripted completion. Close,
  read.

So `N_B = a + w + c_reset`, where **`c_reset ∈ {0,1}` is whether RESET is itself a scored action** — which
is unknown, and is one of the things being measured. It is absorbed rather than resolved: set **`a ≥ 20`**
so `1/a ≤ 0.05`, comfortably inside the tolerance band, and the accumulate hypothesis sits at
`(a+w+c_reset)/a` ∈ `[2.00, 2.05]` at `w = a`. Do not run this with a small `a`.

**Set `w = a`**, so the hypotheses sit at 1.0 versus ~2.0 — separated far beyond any plausible tolerance.
There is no reason to make this measurement subtle.

#### The confound that would invert the answer

If the `w` wasted actions are **rejected as illegal, or are no-ops the scorer does not count**, arm B
scores like arm A and R2 reads **restarts** when the truth is **accumulates**. That is the worst available
error: it selects the aggressive explore-then-speedrun controller in a world where every probe costs
score, and eight weeks go into the wrong agent.

**Validate before reading any score**, from arm B's own transition log: each of the `w` actions must be
**accepted by the API** *and* **produce an observable state change**. Wasted must mean *spent*, not
*ignored*. If any of the `w` fail either test, the arm is void — rebuild the waste sequence from actions
already observed to change state, and rerun. Record the accepted-and-changed count as evidence.

#### Classification — preregistered, with tolerance and repetition

Repeat each arm **3×** on independent scorecards.

- **Within-arm spread** = `(max − min) / median` over that arm's three per-repetition scores. **Both arms
  must satisfy spread ≤ 0.10**, else `inconclusive` — a noisy arm makes the ratio meaningless.
- **The statistic is a ratio of medians, not a median of paired ratios.** The three repetitions per arm
  are independent scorecards with no natural pairing, so pairing them would be arbitrary:
  `r = √(median(score_A) / median(score_B))`.

| Condition | Verdict |
|---|---|
| `r ∈ [0.85, 1.15]` | **restarts** — the count resets, or only the successful attempt is scored |
| `r ∈ [1.85, 2.20]` — i.e. `(a+w+c_reset)/a ± 0.15` at `w = a`, `a ≥ 20` | **accumulates** |
| anything else, **or** either arm's spread > 0.10, **or** the waste-validity check failed | **inconclusive** — do not force a reading |

*Restarts* and *only-the-successful-attempt-is-scored* are indistinguishable here and need not be
separated: they imply the same controller. They diverge only with multiple *completions* in one episode,
which is out of scope for S1 — note it and move on.

**The fork it decides:**

| R1 | R2 | Controller |
|---|---|---|
| deterministic | restarts | **Aggressive identify-then-execute.** Explore freely, then speedrun. Information is nearly free. Best case |
| deterministic | accumulates | **Surgical information-per-action.** Every probe costs score directly |
| **mixed** | game-specific | **No single controller is correct.** Runtime determinism detection plus a switch between the two above — a §11 build item in its own right |
| re-randomizes | either | Speedrun unavailable. Exploration must generalize; R2 sets how expensive probing is |
| inconclusive / blocked | — | **Default to surgical.** The conservative branch is the one that is merely suboptimal if wrong; the aggressive branch is catastrophic if wrong. Re-run the probe at the first slack in S2 |

Record the outcome in `gate_manifest.yaml` as a **result**, not a note — §11's build order branches on it.

---

### 4.5 S1-d — Failure instrumentation — Day 4 (1.0 d)

Explicitly restored to the plan because it is score-relevant: it produces the **build order** for §11 —
which lever to attack first, ranked by observed frequency on real games.

Build the labelling pipeline against the 13 categories, whose operational definitions are already frozen
in `gate_manifest.yaml` from Day 1.

**Schema, per failure episode:**

```
episode_id · game · level · terminal_step · labels[] (multi-label) · primary_label
  each label: category · confidence ∈ {low, med, high} · evidence_ref
evidence_ref → transition indices, frames, raw agent output, prompt/context snapshot
```

**`primary_label` — exactly one per episode, and it must exist**, because the re-rate sample is stratified
on it and the build order is ranked by it. Rater-designated: the label judged **causally earliest** in the
chain that produced the failure — the one that, had it not occurred, would have made the rest moot. If the
rater genuinely cannot choose, the tie is broken by highest confidence, then by the fixed category order
as listed in the manifest, so the rule is always decidable and never a judgement call left open.

**A "failure episode" is** a level attempt that terminated without level advancement, or was abandoned.
Successful levels produce no episode. This is the denominator for everything below.

#### Two frequency measures — they answer different questions

`count` and `share` are ambiguous with multi-label data, and the ambiguity changes the build order, so
both are computed and reported:

| Measure | Definition | Sums to |
|---|---|---|
| `primary_share` | episodes where the category is `primary_label` ÷ total failure episodes | 1.0 |
| `episode_share` | episodes carrying the label *at all*, any confidence ÷ total failure episodes | > 1.0 (expected — multi-label) |

**`primary_share` ranks the build order.** `episode_share` is reported beside it because the gap between
them is informative: a category that is rarely primary but frequently present is a *contributing* factor,
not a root cause, and building for it first would fix something that was never the bottleneck.

**Multi-label with confidence, evidence stored per label.** A single forced label discards the common
case where perception failure and goal ignorance co-occur, and a label with no stored evidence cannot be
re-rated blind.

**Categories** (definitions in the manifest): goal unknown · action semantics unknown · perception/parsing
· hidden-state aliasing or memory · coordinate unreachable · planning depth · exploration or probe
selection · progress-signal misinterpretation · irreversible mistake · invalid output/interface ·
retrieval or context · reasoning inconsistency · latency or budget.

**The known confound, pre-registered.** *Goal-unknown* and *planning-depth* are not separable from
behaviour alone — an agent that never finds the goal and an agent that cannot search deep enough look
identical from outside. The first pass is therefore descriptive, not causal. The blind re-rate rule
(manifest, `blind_rerate`) works in this order — **label first, then blind**, because stratification needs
the first-pass labels that blinding removes:

1. First-pass label the full Day-5 run.
2. Draw a sample **stratified by `primary_label`**, oversampling goal-unknown and planning-depth.
3. Produce a **blinded copy**: strip labels, confidences, and rater notes; **preserve the complete
   evidence packet unchanged, including `reasoning_text`.** Blinding removes the *prior judgement*, never
   the evidence — stripping rationale would delete the sole basis for `reasoning_inconsistency` and would
   make the two passes rate different material, which is not an agreement measurement at all.
4. Re-rate after the cooling period; report per-category agreement.

**Categories that fail the agreement floor do not drive build order.** Note what this bounds: with a
single rater it is delayed test–retest agreement, so it measures label *stability*, not correctness — a
rater can reproduce the goal-unknown/planning-depth confound identically in both passes.

**Exit:** pipeline runs end-to-end over Day 2–3 logs; ≥1 episode labelled per category the logs contain;
label export is machine-readable for the Day 7 ranking.

---

### 4.6 S1-e — The reference run — Day 5 (1.0 d)

The measurement day. Run the frozen reference across the public game set, at scale, fully instrumented.

- Every failure episode labelled through the Day 4 pipeline.
- Progress recorded per game against the reproduction target.
- Transition log volume sufficient to support Day 7's frequency ranking — target the same order the
  earlier plan set for its harness gate (~10⁵ transitions); if the API rate limit (V9) makes that
  infeasible in a day, record the number you got and note it as a limit on the ranking's resolution.
- Latency and reliability re-read at scale; single-episode numbers from Day 3 do not survive contact with
  a full run.

**Label the full run today, then draw the stratified re-rate sample and blind it** (§4.5) — labelling
precedes sampling, since the stratification is on `primary_label`. Setting the sample aside *unlabelled*
would make the stratum assignment impossible and leave nothing to re-rate against. Blinding today starts
the cooling period so it has elapsed by Day 7.

**Exit:** full labelled pass on disk; per-category frequency computable; reproduction target hit or the
gap quantified and explained.

---

### 4.7 S1-f — Packaging and baseline submission — Day 6 (1.0 d)

Establishes the leaderboard reference every later change is measured against. S0 proved the path; this
drops a real payload into it.

- [ ] Weights bundled offline as a Kaggle dataset/model artifact — no network at runtime, sandboxed.
- [ ] Dependencies vendored; a full offline install reproduces the environment from scratch.
- [ ] **Grep the runtime path for network calls.** One `huggingface_hub` cache check will fail the hidden
      rerun and cost a day.
- [ ] License compliance **per bucket** (V11): your own code under CC0/MIT-0 · third-party material
      carrying its own required attribution and sharing terms · weights compliant with Kaggle's
      models-and-weights rules. Do not collapse these into one checkbox.
- [ ] Tensor shapes and toolkit padding confirmed against the submitted-agent contract. If the API always
      pads to 64×64, record that as *verified serialization*, not as the environment definition.
- [ ] ACTION7 exposure identical on the local and Kaggle paths (V12) — if it differs, the local
      measurements do not transfer and you must say so.
- [ ] **Exhaust local validation before spending the day's one submission.** At 1/day (V13) the quota is
      the scarce resource and the notebook is not — dry-run the submission entrypoint in a
      network-disabled container against the bundled weights and deps, and confirm it produces actions
      end-to-end. Every class of failure caught here costs minutes; the same failure caught by Kaggle
      costs a calendar day.
- [ ] Submit. Wait for validation **and** hidden rerun.
- [ ] Ledger row with the ablation it represents (§9).

**Note for the record:** this submission establishes the score reference. Per §4 of the sprint document it
does **not** discharge the Paper Prize submission requirement — a reproduced baseline does not demonstrate
the paper's approach. V14 confirms or corrects that wording; either way §9 keeps one method-bearing
submission path warm rather than building it in the last fortnight.

**Exit — two branches, not one.** A diagnosed failure is useful, but it is not a leaderboard reference,
and S1's whole purpose is to establish the reference every later change is measured against.

| Branch | Condition | Consequence |
|---|---|---|
| **PASS** | Accepted through validation **and** hidden rerun; hidden score recorded | Reference established. Proceed to S1-g |
| **REPAIR** | Rejected, cause diagnosed | **The quota is 1/day (V13) — there is no same-day retry.** Diagnose Day 6, resubmit Day 7 AM, close-out moves to Day 7 PM. **There is no float to charge it to** (§1) — name the source: the 0.5 d comes out of **S3 or S4**, decided and written into the ledger at the moment it is taken, not reconciled later. One retry is what the calendar affords |
| **DEGRADED** | Still no accepted submission after Day 7 | S1 exits without a leaderboard reference. Stop repairing; the cost is now larger than the reference is worth this week |

**What DEGRADED actually costs — record it, do not absorb it.** No hidden score means S5's **B axis**
(baseline readiness) has no score to read, and more seriously, S4's **closed-loop advisor run has no
baseline to measure a delta against**. That reduces S4 to offline probes, and the sprint document is
explicit that offline probes cannot establish control utility — which is S4's retention criterion. So a
degraded S1 does not merely lose a number; it weakens the only measurement that can retain or kill JEPA on
operational grounds. If this branch is taken, write into the close-out what S4's retention decision will
now rest on, and re-run the submission attempt at the first slack in S2.

---

### 4.8 S1-g — Close-out — Day 7 AM (0.5 d)

Stop implementing. Write `notes/s1-closeout.md`:

1. **Distance to competitive.** Hidden score vs the reference class. Standing caveat: public games are
   materially easier than hidden ones — 13.33% public against 7.78% semi-private for the frontier
   reference — so a public number is not evidence of hidden generalization.
2. **The build order.** Failure categories ranked by observed frequency, each annotated with the §11
   candidate component that would address it: goal induction over terminal transitions · object/delta
   modelling · active probing · ACTION6 candidate recall · context-conditioned archive with node
   splitting · verified search · belief ledger. Mark which rankings rest on categories that survived the
   agreement floor and which do not.
3. **Controller fork resolved** — R1/R2 outcome and which controller it selects.
4. **Viability verdict** — pass/fail **per threshold**, keyed, each with an evidence reference, written
   into `gate_manifest.yaml → s1.results.threshold_verdicts`. One aggregate verdict hides which threshold
   failed, and the build order depends on knowing that. No hedging.
5. **What S2 inherits** — the ARC-compatible conventions the generators must match (cell-value range,
   action-set structure, padding) so S4 needs no re-engineering. This is cheap now and expensive on
   Aug 12.
6. **Paper deposit** — methods prose for the harness and instrumentation, written while fresh (§9).

**Exit:** memo committed; `gate_manifest.yaml` S1 results block filled; S2 pre-registration started.

---

## 5. Standing daily obligations (§9)

Not a separate work block — ~30 min/day, off the critical path. Deferring the paper to September
forecloses it; this preserves the *option*.

| Cadence | Obligation |
|---|---|
| Every submission | A row in `submissions/ledger.md`: ID · commit · config diff vs previous · the ablation it represents · hypothesis · result. **This is what turns routine iteration into a component ablation table for free** |
| Same day | Negative results logged with the configuration that produced them. Not at the end of the week |
| From Day 3 | Every figure generated by script from logged results into `paper/figures/`. Never hand-assembled. Once one figure is hand-made the habit is gone |
| Day of implementation | Methods prose for what you just built, into `paper/methods/` |
| Daily, 30 min | `paper/hypotheses.md` and `paper/related-work.md` — written now, not later |

---

## 6. Decisions this week produces

| Decision | Made | Configures |
|---|---|---|
| External execution path works | Day 1 | Everything downstream |
| Reference agent, license-cleared | Day 1 | S1's entire content |
| Controller: aggressive vs surgical | Day 3 | The agent built after Aug 22 |
| Per-action latency budget | Day 3 | S3 question 5; every component's affordability |
| Failure-frequency build order | Day 7 | §11 construction order |
| Baseline viability verdict, per threshold | Day 7 | §11 build order; S4's baseline for the closed-loop delta |
| ARC-compatible conventions for generators | Day 7 | S2 and S4 |

**S2 starts on schedule regardless of the viability verdict.** The generators are synthetic and have no
dependency on a working baseline. What a failed verdict changes is what S1 hands *forward* — the build
order for §11, and whether S4 has a baseline to measure its closed-loop delta against (§4.7, DEGRADED).
S2's only real inheritance from S1 is item 5 of the close-out, the ARC-compatible conventions, and those
survive a degraded S1 intact.

---

## 7. Descope ladder — live from Day 3

Zero float means slippage must be paid for deliberately. In order:

0. **S0 fails — starter rejected, or validation passes and the hidden rerun does not.** At **1
   submission/day** this is a *calendar* problem, not an effort problem: one attempt per day, so the fix
   is fast and the feedback is slow. Diagnose Day 1, resubmit Day 2 AM, and **run S1-a/S1-b in parallel**
   rather than serializing — they are independent, and three serialized retries would cost three days for
   perhaps two hours of actual work. **There is no float** (§1): if diagnosis displaces planned S1 work,
   name S3 or S4 as the source at the time and record it. Waiting on a rerun costs nothing and is charged
   to nothing.
   **Interlock:** Day 6 baseline packaging does not begin until the starter path is green. **Three
   attempts (through Day 3) without a green rerun → stop, and treat the external path itself as the
   sprint's first finding** — a submission path that cannot be made to work is a larger result than
   anything S1 was going to measure.
1. **Day 2 exit missed (no scored level).** Day 3 absorbs a half-day. Do not extend past that silently.
2. **Day 3 end, still no scored public level.** Day 4 AM is a **hard re-decision point**, pre-registered:
   switch to the frozen alternate reference. Not to the template.
3. **Alternate also failing by Day 5.** The template fallback is permitted only with an explicit written
   note in the close-out that **S1's question was not answered**, and that the build order derives from a
   degraded source. Marking S1 complete without that note is the failure mode §4 names.
4. **Behind but reproduction working.** Cut the Day 5 run's *breadth* (fewer games, full instrumentation)
   before cutting Day 4's instrumentation. The instrumentation is what ranks the levers; a broader run
   with no labels ranks nothing.
5. **Never cut:** S0, the reference freeze, the reset experiment, the Day 6 submission. Each is cheap and
   each configures something expensive.

**Overrun beyond Day 7 comes out of S3 or S4.** Decide which explicitly and record it — S4 is the only
measurement that can retain or kill JEPA on operational grounds, so cutting it silently changes what the
sprint can conclude.

---

## 8. Repo scaffold

```
gate_manifest.yaml           # pre-registration; append-only, dated errata
agent/
  reference/                 # vendored at frozen commit, unmodified
  patches/                   # every deviation as a patch — this is the audit trail
  harness/
  instrumentation/
logs/                        # gitignored: transitions.jsonl, failures.jsonl
notes/
  s1-verification.md         # V1–V14 answers with sources and dates
  s1-reference-freeze.md
  s1-measurements.md
  s1-closeout.md
submissions/
  ledger.md                  # the ablation ledger (§9)
paper/
  hypotheses.md
  related-work.md
  methods/
  figures/                   # script-generated only
  make_figures.py
```

---

## 9. Open risks

| Risk | Handling |
|---|---|
| **No suitable public reference exists that is both license-clear and reproducible** | Day 1 screening surfaces it immediately. If both candidates fail the license screen, S1's shape changes on Day 1 — the reference becomes local-measurement-only and Day 6 packages the starter with your own harness instead. Decide it Day 1, not Day 6 |
| Reference reproduces but at a much lower score than reported | Quantify the gap before using the baseline as a reference point. An unexplained gap means you reproduced something else |
| API rate limit (V9) makes the Day 5 run's volume infeasible | Report the achieved volume as a stated limit on the ranking's resolution rather than extrapolating |
| Reset experiment inconclusive because of cap saturation | Pre-compute `a` and `w` against the cap before running; V6 may deny you a retry on the same game |
| Hidden rerun fails on Day 6 for a reason S0 did not surface | The delta between S0's payload and Day 6's is weights + deps; bisect that, not the whole path |
| Zero float | §7, applied from Day 3 rather than at the point of failure |
