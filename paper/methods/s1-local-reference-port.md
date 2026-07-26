# Methods — baseline reference and its local instantiation

*Written 2026-07-26, the day it was built (§5 standing obligation). Evidence:
`notes/s1-reference-freeze.md`, `notes/s1-measurements.md`, `gate_manifest.yaml → s1`.*

## Baseline selection

We take as baseline the strongest publicly released agent for ARC-AGI-3 that is *eligible* for the
competition, which is a narrower class than the strongest published agent. Competition evaluation runs
without network access, so any system that requires a call to a hosted model is excluded by construction.
This removes the highest-scoring published systems — coding agents driving frontier APIs, which report up
to ~99% mean per-game Relative Human Action Efficiency on the 25 public games — and leaves agents that
serve open-weight models locally.

Within that class we adopt the Tufa Labs "duck harness" (Qwen3.6-27B, served via vLLM), the winner of the
competition's first milestone. Its released artifact is a source snapshot rather than a git checkout: the
bundle's own `git_status.txt` records the primary repository as snapshotted with uncommitted changes, so
the commit hash does not reconstruct what ran. We therefore pin the released snapshot itself and treat
the recorded hashes as provenance only.

A survey of the alternatives is given in `paper/related-work.md`. One is worth noting here because it
bears on measurement rather than on ranking: the only other local-model agent with a published
ARC-AGI-3 number computes that number with a scoring function that differs from the competition's in
three ways — it caps the efficiency ratio before squaring rather than capping the squared score, reports
on a unit rather than percentage scale, and estimates per-level action counts by dividing total actions
by the number of levels rather than measuring them. Its reported figure is consequently not comparable
to a competition score, and we do not treat it as a reproduction target.

## Scoring

We take the scoring rule from the shipped implementation
(`arc_agi.scorecard.EnvironmentScoreCalculator`) rather than from its prose description, whose phrasing
is ambiguous about where the cap applies. Per level,

    level_score = min(115, (human_baseline_actions / agent_actions)² × 100)

on a 0–100 scale — the ratio is squared first and the *resulting score* is capped, giving a per-level
maximum of 115 (1.15 unit-scale). The game score is the level-index-weighted mean of level scores,
capped again at the fraction of level weight actually completed; the reported total is the unweighted
mean across games. Incomplete levels score zero.

Recording the scale explicitly matters: leaderboard values are on the 0–100 scale, and reading them as
unit-scale quantities manufactures apparent contradictions with the per-level ceiling.

## Local instantiation

The reference targets a datacentre GPU (NVIDIA RTX PRO 6000; the authors develop on B200s) with FP8
weights served by vLLM. Our development accelerator is an Apple M5 Pro with no CUDA, so neither the
serving stack nor the quantisation transfers.

The port is nevertheless confined to the *serving* layer, because the solver communicates with its model
over an OpenAI-compatible HTTP endpoint rather than through a framework-specific Python API — the
released configuration points at `127.0.0.1` and the bundle ships a second configuration pointing at a
hosted OpenAI-compatible provider, so the backend is already an interchangeable component in the original
design. We substitute an `mlx_vlm` server hosting a 4-bit MLX conversion of the same base model
(`Qwen/Qwen3.6-27B`, Apache-2.0) at the same endpoint. The agent source is unmodified.

Two server-side behaviours had to survive the substitution, since the solver depends on them and neither
is part of the OpenAI wire format: parsing of the model's tool-call syntax, and separation of reasoning
tokens from answer content. Both do: the MLX server infers the same `qwen3_coder` tool-call parser that
the reference configuration names, by matching markers in the model's chat template, and returns
reasoning separately as `reasoning_content`. We verified this by issuing requests built with the
reference's own payload builder and tool schema, and confirming a parsed tool call with syntactically
valid arguments. The reference's vendor-specific request fields (`top_k`, template kwargs, sampling seed)
are accepted unchanged, so the configuration delta reduces to the endpoint and model identifier.

All deviations are held as patch files against an unmodified vendored snapshot and applied by script, so
the diff is the record. Beyond the serving substitution the only code change guards a module-level import
of a package that is private to the reference's authors and is deliberately excluded from their own
released bundle; the surrounding framework already imports it lazily for exactly that reason, and it is
used only to enumerate game identifiers, never during play.

## Throughput characterisation

Because the batching pattern differs from the reference's, per-action latency is characterised under the
batching actually used rather than single-threaded. Decode on this accelerator is bandwidth-bound on the
weights, so concurrent requests amortise weight reads: aggregate throughput rises from 17 tokens/s at
concurrency 1 to a peak of ~60 tokens/s at concurrency 5, then regresses. Per-request throughput declines
monotonically across the same range (17 → 12 tokens/s), and resident memory is flat, indicating a
compute and scheduling ceiling rather than a memory one.

The operational consequence is that concurrency increases the number of games in flight but cannot
shorten any single game, whose model calls are strictly sequential. Per-game wall-clock is therefore
governed by tokens generated per action, not by parallelism. We report every latency figure together with
the concurrency at which it was measured, and do not extrapolate across concurrency levels.

## Instrumentation

Per-step records carry the full grid before and after each action rather than a hash, together with the
executed action, the reasoning turn that produced it, and the level, score and run-state markers. The
framework separately retains per-level action counts and the corresponding human baselines — measured
rather than inferred — which is what makes locally computed scores commensurable with the official rule.
Enabling the harness's request logging additionally captures the full prompt context, the tool schema
offered at each step, and the finish reason, which supplies the context-snapshot and raw-output evidence
that several failure categories are defined on.

One category in our taxonomy cannot be populated from this reference at all. Planning depth is defined as
the length of the shortest successful action sequence measured against the agent's effective search
horizon, and this agent does not search: it writes and executes Python against the observed state. There
is no horizon to measure, and no instrumentation can create one without changing the architecture. We
therefore mark the category unobservable rather than infrequent, and exclude it from the frequency
ranking instead of recording it as zero — a distinction that matters because a silently zero-ranked
category would direct construction effort away from a mechanism that was never measured.
