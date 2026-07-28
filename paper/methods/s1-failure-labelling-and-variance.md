# Methods — S1 failure labelling, and the variance floor it sits on

Written 2026-07-27, the day the measurements were made.

---

## 1. The reference agent and its stochasticity

The baseline is the Tufa Labs ARC-AGI-3 harness ("duck"), an LLM agent that inspects each frame through
a segmentation API and writes Python to choose actions. We ran it unmodified on Kaggle — the
competition's own accelerator (NVIDIA RTX PRO 6000, 96 GB), the reference's own model
(`vrfai/Qwen3.6-27B-FP8`) and serving stack (vLLM), 25 public games, a 7920-second per-game budget,
concurrency 28.

The agent samples at **temperature 0.6, top-p 0.95, top-k 20, with no seed** (`LOCAL_ANALYZER_SEED = -1`).
Every generation is an independent draw and each conditions the next through the conversation history,
so the trajectory is chaotic by construction. This is a property of the reference as published, not a
configuration we chose.

## 2. The variance measurement

We ran the same kernel twice, 2026-07-26 and 2026-07-27. The only difference between the two runs was
enabling request logging, which writes files and does not touch the control path.

| | run 1 | run 2 |
|---|---:|---:|
| mean score | 2.19 | 1.14 |
| median score | 0.13 | 0.00 |
| levels cleared (25 games) | 18 | 15 |
| total actions | 3806 | 3866 |
| duration | 2 h 12 m 42 s | 2 h 12 m 06 s |

Exactly one of 25 games reproduced identically. **Nine games (36%) changed their cleared-level count**
and eight (32%) changed their action count by more than a factor of two in one direction or the other
(extremes: 69 → 394 actions, and 183 → 31). The median action-count ratio was 0.99, so there is no
systematic drift — the distribution is simply wide.

The environment itself is deterministic: an earlier experiment replayed identical action prefixes
byte-identically across two games, two prefix lengths and three replays each. Both facts hold. The
environment replays; the agent does not produce replayable action sequences.

**Consequence for the method.** Per-episode outcome comparisons from single runs are uninterpretable at
this noise floor: two configurations differing on 37% of games are indistinguishable from one
configuration differing from a rerun of itself. We therefore report per-episode outcomes only with
replicates, and prefer within-run rate statistics — which average over tens of generations — wherever a
question can be posed that way.

## 3. Episode extraction

A **failure episode** is one level attempt that did not advance. A level the agent cleared yields no
episode, so a 25-game run produces at most 25 episodes and each game contributes exactly one — the level
it stalled on.

Admissibility is decided by wall-clock, not by the recorded terminal state. The harness records
`gave_up` or `cancelled` depending on whether a generation happened to be in flight when the budget
expired, which is a function of generation length rather than of agent behaviour: all 25 reference games
ran 7920.8–7921.3 s against a 7920 s budget and all recorded `gave_up`, while our local runs at a 2700 s
budget recorded `cancelled` from the same clean exit path. An episode is therefore admitted if the agent
finished **or** the uniform pre-registered budget expired, operationally
`final_wallclock_seconds ≥ 0.98 × budget`. Every episode carries `censored_at_seconds`, and all 25 are
right-censored at 7920 s.

Per-level action counts are read from the benchmark record rather than counted from the event stream.
The action that clears a level is stamped with the *new* level in the event stream while the benchmark
counts it toward the level it completed; deriving counts from the event field alone makes a cleared
level's total one low and the next level's one high.

## 4. Evidence packets

Each episode carries the agent's reasoning, tool code and finish reasons, grouped by analysis step.

Two serving stacks log differently and this had to be handled explicitly. The local MLX server records a
`response_message` field on each response row. The vLLM server used on Kaggle does not: the model's
output appears only as `assistant` messages inside the **replayed conversation** of subsequent requests,
because every request resends the whole history. Reading only `response_message` therefore yields empty
evidence for every vLLM-side episode while a naive count of response rows still reports evidence
present. We recover assistant turns from the replay, deduplicating by content, and attribute each newly
appearing turn to the analysis step of the *preceding* row — which is exact, since a turn first appears
in the replay of the request immediately after it. After the fix the 25 episodes carry 2.5 M characters
of reasoning, median 110 k per episode, none empty.

## 5. Labelling

Labels are multi-label with confidence in {low, med, high} and **evidence stored per label**, so that
every label can be re-rated independently. Exactly one label per episode is designated **primary** —
the one judged causally earliest, "the one that, had it not occurred, would have made the rest moot" —
with ties broken by confidence and then by a fixed category order.

Two of the thirteen pre-registered categories are structurally unobservable for this agent and are
never recorded, not even as zero frequencies: `coordinate_unreachable` (no coordinate candidate set
exists) and `planning_depth` (the agent writes and executes Python rather than expanding a search tree,
so it has no effective search horizon to measure).

Every episode terminates on the budget, so `latency_or_budget` is a terminal fact everywhere. Its
definition excludes decision error, so it is assigned as **primary** only where the agent was on a
correct trajectory and simply ran out; elsewhere it is secondary and the budget was consumed *by* the
primary failure.

Two frequency measures are reported. **`primary_share`** — episodes where a category is primary, over
total episodes — sums to 1 and ranks the build order. **`episode_share`** — episodes carrying the label
at any confidence — sums above 1 and is reported beside it, because a category often present but rarely
primary is a contributing factor rather than a root cause.

Frequencies are stratified by level band and reported pooled. The ranking is taken from the L2+ band:
the reference clears level 1 in 15 of 25 games and level 2 in 3, so level-1 episodes describe the case
that is already solved rather than the bottleneck. Where the two bands disagree on the top category the
disagreement is itself reported.

**The rater was an LLM (claude-opus-5), not a human.** The pre-registration assumes a human throughout —
it names the agreement statistic "delayed test-retest (same rater)" over a 48-hour cooling period. Both
assume continuous memory. The cooling period is therefore inapplicable and is not reported as satisfied,
and a second pass in a fresh context is *independent* rather than test-retest: blinder than the
pre-registered procedure, but measuring a different quantity, and it must not be compared against a
literature expecting human test-retest.
The specific risk is correlated bias: `goal_unknown` is diagnosed largely from the agent's own statement
of its objective, which is self-report, and an LLM reading another LLM's self-report may share a blind
spot on exactly the category that dominates the result. One human-rated sample of 8–10 episodes would
bound this and has not been run.

No blind re-rate was performed **for the figures reported in this section**, so no per-category agreement
statistic backs them and the pre-registered agreement floor was not applied to them. That limitation is
permanent for these numbers, which were computed from a single run before any re-rate existed.

The sample size of 30 was briefly judged unachievable, on the reasoning that one run yields at most one
failure episode per game and so at most 25. That reasoning held only for a single run. The corpus is now
built from three separate runs of a byte-identical configuration — verified equal on model, sampling
parameters, context window, budget and solver settings before pooling — giving **75 episodes**, against
which 30 is a 40% sample. The pre-registered size was never amended; the corpus grew to meet it.

## 6. Robustness of the ranking against the variance floor

Section 2's noise floor threatens any frequency computed from single-run episodes, so the margin was
checked rather than assumed. In the L2+ band the top category holds 9 of 12 primary labels and the
runner-up holds 1. **Four episodes — a third of the band — would have to relabel, all to the same
alternative category**, to unseat it. Excluding the two episodes below any reasonable
behavioural-evidence floor (one with zero actions, one with eleven) raises the top category to 9 of 10.

Run-to-run variance changes which level an episode lands on and how many actions it spends. To overturn
this ranking it would have to change what *kind* of failure occurs, systematically and in one direction.
Neither reference run suggests that. The ranking is reported as robust to the measured noise; the
underlying single-rater limitation in section 5 is the binding uncertainty, not the sampling noise.
