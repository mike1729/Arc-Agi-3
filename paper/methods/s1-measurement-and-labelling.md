# Methods — measurement and failure labelling

*Written 2026-07-26, the day the harness was built (§5 standing obligation). Implementations:
`agent/harness/{s1c_measure,s1d_label,s1d_blind_rerate,analyse_reference_run}.py`.*

## Measurement units

Latency is reported at two units, because the natural one is misleading for this agent. The baseline
commits game actions in batches — it calls an action primitive with a list — so several actions can
follow from a single model decision. Deltas between consecutive action records within such a batch are
near zero and reflect environment stepping, not inference. A per-action median computed over all deltas
is therefore dominated by intra-batch zeros and understates the cost of a decision by roughly an order
of magnitude. We report per-action latency, because it is the quantity our pre-registration names, and
per-decision latency, defined as the subset of inter-action gaps exceeding a threshold chosen to exclude
intra-batch stepping; the latter is what any runtime budget should be read against. Every latency figure
carries the concurrency it was measured at, since throughput on a single accelerator trades aggregate
against per-request rate and the two are not comparable across settings.

Action reliability is read from the harness's own accounting rather than reconstructed. The environment
wrapper reports, per action call, how many actions were requested, how many executed, whether execution
stopped early, and why; these payloads are returned to the model as tool output and are therefore
captured verbatim by request logging. An earlier attempt to recover the same quantity by parsing action
calls out of the agent's emitted source failed, and failed informatively: because the agent constructs
action lists programmatically, static parsing undercounted requests and produced an executed-to-requested
ratio above one, which is impossible and revealed the method rather than the measurement to be at fault.
We record the requested and executed totals, the distribution of stop reasons as a rejection taxonomy,
and note that single actions which execute normally omit the counters and are counted implicitly.

Sustained-throughput degradation cannot be separated from task phase on an agent run. Measured over a
full episode, our baseline became *faster* over time, because it explores cautiously at first and then
emits large action batches. A thermal signal and a behavioural one are confounded, and we report the
figure as uninterpretable from agent traces rather than as evidence of no throttling; a constant-shape
synthetic workload is required to isolate it.

## Failure episodes

A failure episode is a level attempt that terminated without advancement, or was abandoned. Levels the
agent clears produce no episode. This is the denominator for every frequency we report, and it is worth
stating because the alternative — counting every level attempt — would let a strong agent's successes
dilute the failure distribution of the levels it could not solve.

Episodes are extracted by segmenting the event stream on the level marker: a segment followed by another
segment was cleared and yields nothing; a terminal segment is an episode. Each episode carries the
actions taken, the human baseline for that level and their ratio, the number of reasoning turns, the
count of distinct actions and the share taken by the most frequent one, together with an evidence packet
containing the model's reasoning and tool calls for every reasoning step in the segment.

Labels are not assigned programmatically. The extraction produces a record with an empty label set for a
rater to complete. This is a deliberate constraint rather than an omission: the frequencies derived from
these labels determine construction priorities, and a heuristic labeller would manufacture exactly the
distribution it was supposed to measure.

Two categories in our taxonomy are excluded before labelling begins, because the quantities they are
defined on do not exist for this baseline. One requires a candidate set of coordinates, and the agent's
interface exposes valid actions as names, never as enumerable coordinates. The other requires an
effective search horizon, and the agent does not search — it writes and executes code against the
observed state. Neither is recoverable by instrumentation without changing the architecture, and both
are recorded as unobservable rather than as zero-frequency, since a mechanism that silently ranks last
would divert construction away from a lever that was never measured.

## Stratification by level

Frequencies are reported separately for first levels and for later levels, and the ranking is taken from
the latter. The reason is empirical: measured across the public set, the reference baseline clears the
first level of most games and the second level of very few, and never reaches a third. Pooling the two
would let episodes describing the already-solved case dominate a ranking intended to order work on the
unsolved one. Where the pooled ranking and the later-level ranking disagree on their top category, we
surface the disagreement explicitly rather than resolving it silently.

## Blind re-rate

Agreement is measured by re-rating a stratified sample after a cooling period. The order is fixed:
label the full pass, then draw the sample, then blind it. Stratification is on the first-pass label, so
a sample set aside before labelling could not be stratified and would have nothing to be compared
against.

Blinding removes the prior judgement, not the evidence. Labels, confidences and rater notes are
stripped; the evidence packet is carried through unchanged, including the model's reasoning text.
Stripping rationale would delete the sole basis for the category concerning reasoning inconsistency and
the recorded-goal evidence for the category concerning unknown goals — the procedure would remove what
its own categories are defined on, and the two passes would be rating different material, which is not
an agreement measurement.

Two categories are oversampled. The first concerns unknown goals. The second was originally the
search-depth category, which is unobservable here; it was replaced by the exploration-selection
category, restricted to episodes whose game exposes no coordinate actions at the rated steps. That
restriction is necessary because the category is defined against a higher-yield alternative action, and
on coordinate-driven games the alternative is a coordinate rather than a named action, so the evidence
does not exist. The eligible fraction is reported alongside the agreement statistic: a number computed
on a subset must say which subset.

With a single rater, this is delayed test–retest agreement, not inter-rater reliability. Cohen's kappa
remains the appropriate statistic, but the claim it supports is weaker than the name suggests: it bounds
the stability of a label, not its correctness. A rater can reproduce a confounded judgement identically
in both passes, and the two confounded categories in our taxonomy are precisely the ones most likely to
be reproduced that way. Categories falling below the agreement floor are reported as unreliable and do
not drive construction order.

## Reference baseline

Because our development accelerator cannot run the baseline's serving stack, we additionally ran the
reference unmodified in its native environment and analysed its per-game outcomes. That run provides the
only behavioural data we hold on the baseline as published, and it is the yardstick against which local
substitutions are checked. It also supplies a control for the substitution risk: where a locally
substituted model fails in a manner qualitatively unlike the reference — for instance by expending two
orders of magnitude more actions on a level rather than halting after roughly twice the human budget —
the substitution is unsuitable for characterising failures, whatever its throughput advantage.
