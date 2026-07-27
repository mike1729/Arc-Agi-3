# Local compute options — what each is good for

Written 2026-07-27, after a full day of S1-e runs made the trade-offs measurable rather than assumed.

---

## The distinction that reframes everything: two compute profiles, not one

Almost every difficulty in S1 — 45-minute games, 80-second generations, concurrency schedules, swap
thrash, quantisation arms — comes from one property of the **reference baseline**: it is an LLM agent
where *every action is a model generation*. A 27B model is in the inner loop.

**The research this project exists to do has the opposite profile.**

| | reference / Track B agent | Track A, SHiP-JEPA-X |
|---|---|---|
| model | Qwen3.6-**27B** | **~20M** trainable parameters |
| ratio | — | **1,350× smaller** |
| inner loop | one LLM generation per action | forward pass of a compact encoder/predictor |
| bound by | tokens/second, VRAM for KV cache | gradient steps, data generation |
| local viability | marginal — the whole of S1 is the evidence | **plausible, not yet measured** — see the caveat below |

Track A's parameter budget (`docs/arc-agi-3-ship-jepa-x-architecture.md` §20): spatial grid encoder
4.0M, sequential context transformer 5.5M, local predictive model 3.5M, multi-horizon and event heads
2.0M, reachability and action-cost 1.5M, goal and exploration heads 1.0M, coordinate proposal 0.8M,
adapters 0.7M, reserve 1.0M — **20.0M total**. The archive, graph algorithms, delta parser, verifier
and search are nonparametric.

At 20M parameters, weights are ~80 MB in fp32; with Adam states and activations a training step is
comfortably under a gigabyte on a machine with **69 GB unified memory**.

> **Caveat added 2026-07-27: 20M is itself a guess, and it is not pre-registered.** The figure appears
> nowhere in `gate_manifest.yaml`. Its sources are the architecture doc — "a compact implementation *can
> target approximately* 20 million", in a document marked *candidate design, not committed* — and the
> frozen, partly-superseded executive summary, which calls it a "fixed budget". Nor is any **training**
> budget registered: "matched optimization budget" is required with no number attached, so the arms could
> be trained to different budgets without violating anything written down. The claim that local is
> "comfortable" therefore rests on a guessed model size and an absent step count. `bench_training.py`
> sweeps parameter counts rather than assuming 20M, so the size can be chosen against measured
> throughput instead of the reverse.

### Measured, 2026-07-27 — `bench_training.py`

Forward + backward + Adam step, steady state after warm-up. K = 16 transitions, 64×64 grid, batch 32,
6 layers / 8 heads, MLX on the 69 GB machine.

| params | steps/s | ms/step | peak mem |
|---:|---:|---:|---:|
| 5.3M | 15.07 | 66 | 3.66 GB |
| 10.0M | 10.08 | 99 | 5.10 GB |
| **21.2M** | **7.22** | **138** | **7.54 GB** |
| 51.7M | 3.79 | 264 | 12.20 GB |
| 84.6M | 3.09 | 323 | 16.04 GB |

Wall-clock for the ~12 runs S3 needs (3 objectives × rollout on/off × 2 seeds):

| params | 10k steps | 50k | 100k | 500k |
|---:|---:|---:|---:|---:|
| 5.3M | 2.2 h | 11.1 h | 22.1 h | 110.6 h |
| **21.2M** | **4.6 h** | **23.1 h** | **46.2 h** | 230.8 h |
| 51.7M | 8.8 h | 43.9 h | 87.9 h | 439.3 h |
| 84.6M | 10.8 h | 53.9 h | **107.7 h** | 538.7 h |

**S3 allows 5 days — 120 h — for those runs plus controls.** At the guessed 20M, a 100k-step budget
costs 46 h: comfortably inside, with room for the controls and a rerun. Even **50M at 100k steps fits**
(88 h), and 85M at 100k just fits (108 h) with no slack.

So the honest answer to "is local viable for the training work" is **yes, and the parameter budget is
not the binding constraint** — 20M is conservative by roughly 4×. Memory is nowhere near binding either:
7.5 GB of 69 GB at 20M.

**The binding constraint is the step budget, and it is the number nobody has registered.** At 500k steps
nothing above 5M fits in 120 h. The table converts a missing pre-registration into wall-clock, which is
the form in which it has to be decided.

*Limits:* not the real model — a heavier decoder in arm B or a different attention pattern moves this;
MLX only, no torch/MPS comparison available; single process, so the figures assume no LLM server is
resident.

S2's F1/F3 generators are synthetic sequence producers, and S3 screens three objectives (A latent /
B reconstructive / C exact-delta) over them. **None of that touches an LLM.** That part does not depend
on the parameter budget at all — whatever size is chosen, no 27B model is in the loop.

So the honest summary is: **the LLM throughput problem is a property of the baseline we are measuring
against, not of the work we are doing.** S3 and S4 are what retain or kill JEPA, and S3 is local-native.

Where an LLM *is* required: reproducing the reference baseline (S1), the deployed Track B agent, and
S4's advisor test to whatever extent the advisor guides an LLM-driven agent. Those are the cases the
table below is for.

---

## Options, measured

### 1. Local MLX 4-bit — `mlx-community/Qwen3.6-27B-4bit`

15 GB · ~12.1 tok/s · currently the largest S1 corpus

**Good for:** harness development, pipeline debugging, anything where behaviour fidelity does not
matter.

**Not good for:** anything behavioural. Measured 2026-07-27: acting rate is *erratic* — 12%, 18%, 50%
across three games — and it failed to clear levels that both 8-bit and the reference clear. On `vc33`
it spent 23 and 51 actions across two runs without solving a level the reference solves in 8.

**Verdict: unsuitable as a behavioural baseline.** The 17-episode 4-bit corpus is substantially a
measurement of the quantisation.

### 2. Local MLX 8-bit — `mlx-community/Qwen3.6-27B-8bit`

29.5 GB · ~8.3 tok/s (⅔ of 4-bit) · matched pair with 4-bit (same converter, `group_size 64`, affine;
only `bits` differs)

**Good for:** the closest local approximation to reference behaviour. Cleared `vc33` L1 in **8 actions,
the same count the reference needed**, and `tn36` L1 in 11 where 4-bit never cleared it. Acting rate is
*stable* at 25–32% across games where 4-bit ranged 12–50%.

**Costs:** ⅔ the token throughput, so fewer generations per wall-clock hour; and on games where 4-bit
happened to act often (`r11l`, 50%) it produces *fewer* actions.

**Verdict: the local agent vehicle of choice**, with the caveat that it is a different artifact lineage
from the reference's `vrfai/Qwen3.6-27B-FP8`, so it is not a precision-controlled comparison to it.

### 3. Local MLX MoE — `Qwen3.6-35B-A3B-4bit`

19 GB · roughly 5× faster than dense

**Rejected**, and the reason is worth keeping: it failed a level by expending ~100× the human action
budget **without halting** — a qualitatively different failure mode from the reference's. Speed is
irrelevant if the failure profile is wrong, since failure profile is exactly what S1-d measures.

### 4. Kaggle notebook — RTX PRO 6000, 96 GB

**Free** (GPU quota) · 25 games in 2 h 12 m · FP8 + vLLM, concurrency 28

**Good for:** the *exact* target stack — `DEFAULT_ACCELERATOR = "NvidiaRtxPro6000"`, the competition's
own accelerator, running the reference's own model and engine. Nothing local reproduces this.

**Costs:** notebook turnaround, no interactive iteration, quota. Existing private kernel
`michalswietek/s1b-tufa-duck-reference-measurement` re-runs with a one-cell edit.

**Verdict: use for anything that must be faithful to the reference.** It is free and it is the target
hardware; renting is redundant while quota lasts.

### 5. Rented RTX PRO 6000 — RunPod

$1.69/hr community, $1.99/hr secure · 96 GB

**Good for:** interactive work on the target stack, or when Kaggle quota is exhausted. Also the only
way to run the reference's exact artifact (`vrfai/Qwen3.6-27B-FP8` on vLLM) under a debugger.

**Verdict: not needed today.** Kaggle gives the same card free. Keep as the escape hatch.

### 6. Local, no LLM at all — Track A training

**Good for:** everything S2 and S3 require. ~20M parameters, synthetic F1/F3 sequence generators, three
objective arms, two seeds. This is ordinary small-model training on a 69 GB machine.

**Verdict: this is where the actual research lives, and local is not a compromise for it.**

---

## Mapping to the work

| work item | needs an LLM? | where it should run |
|---|---|---|
| S1 reference reproduction | yes, faithfully | **Kaggle** (free, exact stack) |
| S1-d failure labelling | evidence only, no new runs | local analysis |
| S2 — F1/F3 generators | **no** | **local** |
| S3 — objective screening A/B/C | **no** | **local** |
| S4 — ARC advisor test | partly, if the advisor drives an LLM agent | local 8-bit, escalate to Kaggle for headline numbers |
| Track B deployed agent | yes | Kaggle / competition |
| harness + pipeline development | no | local, any model |

---

## What this changes

The escalation trigger in the freeze — "sustainable local concurrency < 4 ⇒ escalate to hybrid" — was
written when the plan assumed an LLM in the inner loop throughout. Measured local concurrency is
1–2 for useful LLM work, which *reads* as a trigger. But the trigger is scoped to the wrong thing: it
should govern **LLM-driver work only**, which is the baseline and Track B, not S2/S3.

Read literally it would push the whole project to rented hardware to serve a component that is a
yardstick rather than a contribution. **Local remains viable for the research; only the baseline
reproduction needs the target hardware, and Kaggle supplies that free.**
