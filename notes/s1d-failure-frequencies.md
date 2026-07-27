# S1-d — failure frequencies and the build order — 2026-07-27

The output S1 exists to produce. 25 reference episodes (Kaggle v2, FP8, 132-minute budget), all with
reasoning evidence, first-pass labelled against `gate_manifest.yaml → s1.failure_taxonomy`.

**Rater: claude-opus-5, not a human.** That is a deviation from the pre-registration, filed as
erratum **S1-E10**, and it bounds what follows. Read that erratum before using these numbers.

---

## The result

`primary_share` — one label per episode, the one judged causally earliest. **This ranks the build order.**

| category | **L2+ (n=12)** | L1 (n=13) | pooled (n=25) |
|---|---:|---:|---:|
| **`goal_unknown`** | **75.0%** | **76.9%** | **76.0%** |
| `action_semantics_unknown` | 8.3% | 15.4% | 12.0% |
| `latency_or_budget` | 8.3% | 7.7% | 8.0% |
| `progress_signal_misinterpretation` | 8.3% | — | 4.0% |

**`band_divergence: null`.** The pooled ranking and the L2+ ranking agree on the top category, so the
stratification rule that S1-E2 exists to enforce does not bite here. That is a result, not a formality:
it means level 1 and level 2+ fail the same way, and the pre-registered worry — that a pooled ranking
would optimise the already-solved case — does not apply to this corpus.

`episode_share` — the category present at any confidence. Sums above 1 by design; a category often
present but rarely primary is a **contributing factor, not a root cause**.

| category | L2+ | L1 | pooled |
|---|---:|---:|---:|
| `goal_unknown` | 83.3% | **100%** | 92.0% |
| `latency_or_budget` | 50.0% | 46.2% | 48.0% |
| `action_semantics_unknown` | 50.0% | 30.8% | 40.0% |
| `exploration_or_probe_selection` | 16.7% | 61.5% | 40.0% |
| `irreversible_mistake` | 33.3% | 7.7% | 20.0% |
| `perception_parsing` | 16.7% | 15.4% | 16.0% |
| `retrieval_or_context` | 16.7% | 7.7% | 12.0% |
| `hidden_state_aliasing_or_memory` | 16.7% | — | 8.0% |
| `invalid_output_interface` | 8.3% | — | 4.0% |
| `progress_signal_misinterpretation` | 8.3% | — | 4.0% |
| `reasoning_inconsistency` | — | — | — |

**`goal_unknown` is present in 100% of L1 episodes and 92% overall.** Nothing else comes close.

---

## What the corpus actually shows

The reference agent is **good at mechanics and bad at objectives**, and the gap is not close.

Across 25 episodes it repeatedly derived correct, non-obvious transition rules from a handful of
observations — that clicking a G diamond swaps it with the white one (`r11l`), that SPACE removes the
vertical stem of whichever L-shape the dots overlap (`ar25`), that the X collects on its horizontal bar
and not only its diagonals (`re86`), that a level's danger zone rotated from horizontal to vertical
between levels (`tu93`). This is competent world-model construction from sparse evidence.

It then had nothing to aim that model at. Three episodes make the point sharply:

- **`sc25`** reached the state its own goal model called the solution — W tiles on the four purple-dot
  cross positions — and the level did not complete. *"Current state matches the purple dot pattern
  (cross). But level doesn't complete."* Execution succeeded; the target was wrong.
- **`ls20`** enumerated all six legal block positions and found none completes the level, correctly
  concluding *"the goal is not about positioning the blocks in the G room"* — with no replacement
  hypothesis and no way to generate one.
- **`cd82`** proved its own action set forms a closed cycle — *"That's a loop"* — and kept issuing moves
  inside it.

The action-economy statistics separate the two abilities cleanly. `r11l` spent **32 actions against a
33-action human baseline** — a 0.97 ratio, near-perfect economy — and cleared nothing. `ka59` came in at
0.72. Meanwhile `cn04` burned **354 actions, 12.21× human**, on a goal it never identified. Efficiency
and progress are uncorrelated in this corpus, because the binding constraint is upstream of action
choice.

### The two counter-examples, and why they matter

`goal_unknown` is not everywhere, and the exceptions are informative rather than noise.

- **`g50t` is the one episode with a correct, explicit, stable goal** — *"Goal model: Reach target at
  (52,46)"* — held across the whole episode. It failed on `latency_or_budget`, and it is the reason that
  category is not purely an artifact of the uniform 7920 s cut: the terminal steps show monotonic
  progress, a new reachable node discovered at every step. It was genuinely still working when time ran
  out. Its secondary label is the real cost: it mapped the corridor graph **by physically walking it**,
  205 actions to enumerate roughly seven nodes, with backtracking charged to the same action budget the
  score is computed from.
- **`sk48` and `wa30`** had stable goal hypotheses and were blocked on transition semantics — which
  blocks move with the trail, when a frame can be absorbed. These are the episodes an
  action-semantics component would actually help.
- **`sp80`** is its own case and the most interesting single episode: it could not tell success from
  failure. *"pressing SPACE resulted in done=True. But the timer was 38, not 0, so this could be either
  level_completed or game_over."* It had the solving position in hand and could not recognise it. One
  episode, but it is a distinct failure — reading the environment's feedback, not choosing an action.

---

## Robustness — does the 36% run-to-run noise threaten this?

`notes/s1-reference-variance.md` measures the reference disagreeing with its own rerun on 36% of games,
which puts a question mark over any frequency computed from single-run episodes. Here it does not bite,
for a reason that is arithmetic rather than hopeful:

- **The margin is 67 points.** In the L2+ band `goal_unknown` has 9 primary labels; the runner-up has 1.
- **Four episodes — 33% of the band — would have to relabel, all to the same alternative category**, to
  unseat it. Not four episodes changing; four changing *in the same direction*.
- **Dropping the two thin episodes strengthens it.** `ft09` (0 actions) and `tu93` (11) sit below any
  reasonable behavioural-evidence floor. Excluding them: **`goal_unknown` 9/10 = 90%** of the L2+ band.

Run-to-run variance changes *which level* an episode lands on and *how many actions* it spends. For it
to overturn this ranking it would have to change *what kind of failure* the agent has, systematically,
in one direction. Nothing in the two reference runs suggests that.

**This is a much stronger position than a close ranking would be**, and it substantially defuses task #8:
the stability check is still worth running, but the build order no longer hangs on it.

---

## What this implies for the build

Read against `docs/arc-agi-3-ship-jepa-x-architecture.md`, the ranking says the components that matter
are the ones that **propose and test objectives**, not the ones that predict transitions.

That is uncomfortable for the project's own framing, and the discomfort should be recorded rather than
smoothed over. SHiP-JEPA-X's parameter budget is dominated by transition prediction — spatial grid
encoder, sequential context transformer, local predictive model, multi-horizon heads. The reference is
*already competent* at exactly that, using no learned world model at all, just an LLM reading ASCII and
writing Python. The measured bottleneck is goal inference, which in that architecture is a **1.0M
parameter "goal and exploration head"** — 5% of the budget against a failure mode carrying 75-92% of the
episodes.

Three honest readings, and choosing between them is a decision for the operator, not for this note:

1. **The build order should follow the measurement** — goal inference first, transition prediction later.
2. **A latent world model is instrumental to goal inference** — you cannot hypothesise a win condition
   over a representation you do not have. Defensible, but it is an argument, not a measurement, and it
   is exactly the kind of argument that survives any result.
3. **The reference's bottleneck is not ours.** It has a 27B LLM doing perception and a nonparametric
   archive; a 20M model may fail somewhere else entirely. Also defensible, and it implies this corpus
   ranks *the reference's* build order rather than ours — which S4's advisor test is what actually
   settles.

What is not defensible is proceeding as though the measurement came out the other way.

---

## Limits

- **Single rater, and not a human** (S1-E10). `goal_unknown` is diagnosed largely from the agent's own
  self-report of its objective, which the manifest already flags as weak, anchoring evidence. An LLM
  rating an LLM's self-report may share a blind spot here. One human-rated sample of 8-10 episodes would
  bound it.
- **No blind re-rate *for the numbers on this page*.** These frequencies were computed before any
  re-rate existed, so `agreement_floor: 0.40` has not been applied to them and no per-category
  agreement statistic backs them. Under the pre-registration's own terms **this table drove the build
  order with no stability check** — exactly what the floor exists to prevent — and that stands as a
  limitation of *this* first pass however the re-rate turns out.

  S1-E7 itself is no longer open: resolved 2026-07-27 by **S1-E11**, operator choosing `multiple_passes`.
  A 3-pass kernel is running (75 episodes), which makes the original pre-registered `sample_size: 30`
  achievable without amending it. When it lands, the re-rate can be drawn and the agreement floor
  applied — to the enlarged corpus. Per **S1-E10** the second pass will be *independent*, not delayed
  test-retest, because the rater has no memory between sessions.
- **Reference, not local.** These are FP8 reference episodes at a 132-minute budget. The local 4-bit
  corpus has 17 episodes, 16 of them L1, and 0 labelled. The local agent's failure profile may differ;
  the quantisation arm suggests it does.
- **Every episode is right-censored at 7920 s**, so `latency_or_budget` is partly a property of the
  budget rather than of the agent, as S1-E9 requires be stated.
- **The worksheet showed early and terminal reasoning**, not every step. Categories defined on mid-episode
  behaviour — `hidden_state_aliasing_or_memory` especially — are likelier to be under-counted than
  over-counted.

## Provenance

`logs/s1d_corpus_refv2.json` — 25 episodes, all labelled, evidence per label, `labelling` block records
rater and pass. Frequencies computed by `agent/harness/s1d_label.py :: frequencies()`, never by hand.
