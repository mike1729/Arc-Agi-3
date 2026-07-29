# S1 Reference Freeze

**Status: FROZEN 2026-07-26.** Corresponding `gate_manifest.yaml → s1` block frozen the same day.

Screened per `docs/archive/arc-agi-3-s0-s1-execution.md` §4.1 (archived 2026-07-28). Selection criteria, in the order the plan fixes
them: (1) the models-and-weights bucket clears; (2) fits the accelerator at the intended quantization
with the compact models resident; (3) reports a public-game score that can be targeted; (4) the harness
is reusable — *that is where the saving comes from*; (5) legible enough to instrument.

**Accelerator decision (the pre-flight open item, now closed):** development runs **local-only on the
M5 Pro first**, escalating to hybrid (local + rented CUDA) only on the pre-registered trigger in §6
below. Decided 2026-07-26.

---

## 1. What the screen actually found

The premise S1 inherits — *"reproduce a strong public local-model agent"* — is satisfiable, but not
where the earlier docs implied. **The arXiv route is a dead end; the Kaggle leaderboard is the real
reference class.** Every strong public agent is a local open-weight model served by vLLM on an
NVIDIA RTX PRO 6000, running with `enable_internet: false`.

| Candidate | Model / backend | Reported score | License | Verdict |
|---|---|---|---|---|
| **Tufa Labs duck harness** (`jeroencottaar`) | Qwen3.6-27B-FP8 / vLLM | **LB 1.21**, Jun 30 milestone winner | see §4 | **PRIMARY** |
| **mbmmurad LB 0.86** | Gemma-4-31B-IT / vLLM | LB 0.86, 3rd-place milestone candidate | see §4 | **ALTERNATE** |
| ko0kip Gemma-4-31B Reflection Agent | Gemma-4-31B-IT / vLLM | none stated | — | rejected: no inheritable target (criterion 3) |
| AERA (`farmountain/aera-arc3-paper`) | Qwen2.5-0.5B/7B / llama.cpp | RHAE 0.2116 | CC0 (deed text only) | **rejected — see §1.1** |
| `astroseger/arc-3-agents-baseline1` | GPT-5.5/5.6-sol via Codex CLI | RHAE ~99% public | MIT | rejected: frontier-API-bound, Kaggle-ineligible |
| `ssppsy/arc-agi-3` | random + heuristic, no model | none | none declared | rejected: abandoned stub (single push, 2026-04-08) |

### 1.1 Why AERA was rejected — it fails criterion (3) on inspection, not on reputation

AERA is the only public *local-model* agent with a published ARC-AGI-3 number, it is CC0, and it runs
natively on Metal. It was still rejected, because its reported score is **not the competition metric**.
From its own `run_eval.py:108-121`:

```python
per_level = min(human_actions / agent_actions, 1.0) ** 2      # cap 1.0, applied to the RATIO
agent_per_level = result.total_actions / n_levels             # per-level actions ESTIMATED, not measured
if not result.solved: return 0.0                              # no credit for partial progress
```

Three independent departures from the official rule (§2 below): it caps the ratio at 1.0 before
squaring rather than capping the squared percentage score at 115, it reports on a 0–1 scale rather than
the core implementation's 0–100 scale, and per-level action counts are *approximated by dividing total
actions by level count* rather than measured. Its
`efficiency_score` is a local surrogate. **`0.2116` is therefore not a reproduction target**, and adopting
it would have silently corrupted the S1-g `reproduction_fidelity` verdict.

Secondary: the repo's `REPRODUCIBILITY.md` reports results for Qwen2.5-**0.5B** while every documented
command loads Qwen2.5-**7B**; its example `scorecard.json` matches neither results table; its commands
reference `competitions/arc-agi-3/` paths that do not exist in the repo. Repo health is 2 stars, 0 forks,
one author, last push 2026-05-25.

**Kept as a source, not a reference.** AERA's substantive contribution stands and is directly relevant to
S1-d: it documents that all 25 public games fall to non-intelligent strategies (10 in a single blind step,
5 after probing, 8 via repeated actions, 18 via a null-coordinate vulnerability). That is corroborating
evidence for the standing caution that public games are materially easier than hidden ones, and it feeds
the failure taxonomy. It is cited in `paper/related-work.md`, not vendored.

---

## 2. Correction to the scoring rule (V8) — core implementation governs

Corrected 2026-07-26 against `arc_agi.scorecard.EnvironmentScoreCalculator` and the reference's vendored
mirror in `agent/reference/taaf/src/tufa-arc-agi-framework/src/taaf/game.py`:

```python
level_score = min(115.0, (human_baseline_actions / ai_actions) ** 2 * 100)
```

The implementation squares first and caps the resulting percent-scale score at 115. On a unit scale this
is `min(1.15, (human/ai)²)`, with maximum **1.15**, not 1.3225. The game score is capped again at the
completed-level weight fraction × 100.

Also recorded from the same source: **no partial credit for incomplete levels**, and a game's maximum is
bounded by `(sum of completed level indices) / (sum of all level indices) × 100`.

**V15 narrowed.** The public leaderboard's **1.86** is on the scorer's 0–100 scale and is therefore not
a contradiction. The remaining open discrepancy is our S0 random agent's Kaggle score of **0.06** despite
the retained evidence showing zero completed levels. The LB `1.21` comparison remains reported rather
than gated because the readable notebook did not reproduce its milestone score and our DEV-1/DEV-2/DEV-4 stack
differs—not because the score scale is unknown.

---

## 3. Primary reference — Tufa Labs duck harness

| Field | Value |
|---|---|
| **Notebook** | `jeroencottaar/tufa-labs-duck-harness-june-30-milestone-winner` (id_no `122359844`) |
| **Original scoring notebook** | `jeroencottaar/taaf-duck-harness-kaggle` — scored the 1.21; author recommends against using it |
| **Source bundle** | Kaggle dataset `jeroencottaar/taaf-kaggle-source-share`, "TAAF Kaggle Source Bundle", 439 KB, updated 2026-06-12 07:57 UTC |
| **Weights (reference)** | `driessmit1/vrfai-qwen3-6-27b-fp8-hf-snapshot` — `vrfai/Qwen3.6-27B-FP8`, `model.safetensors` 33.5 GiB |
| **Weights (local substitute)** | `mlx-community/Qwen3.6-27B-4bit` — converted from `Qwen/Qwen3.6-27B` with mlx-vlm 0.4.4, 16.1 GB, image-text-to-text |
| **Wheelhouse (reference)** | `driessmit1/arc3-vllm-h100-wheelhouse-v3`, 4.8 GiB — `vllm==0.19.0 torch==2.10.0 flashinfer==0.6.6` |
| **Reference accelerator** | Kaggle `machine_shape: NvidiaRtxPro6000`; team development on B200 ×2 (from `deployment.slurm`) |
| **Our accelerator** | Apple M5 Pro, 20-core GPU, 51.84 GiB `recommendedMaxWorkingSetSize` (see `notes/s1-verification.md`) |
| **Quantization** | reference FP8 → **local MLX 4-bit** |
| **Authors** | Harold Bessis, Jeroen Cottaar, Isaiah Pressman, Andries Smit, Michal Tesnar, Stefano Viel (Tufa Labs) |
| **Writeup** | competition discussion `717133` — read on Day 2, it feeds the S1-d taxonomy |

### 3.1 Commit provenance — pin the dataset version, not the git SHA

`git_status.txt` inside the bundle:

```
ARC3-Inference            aa69123     DIRTY   add-kaggle-share-flag
tufa-arc-agi-framework    fe9f7c4     clean   submission-share-mode-bugfix
re-arc-3                  57e46d619d  pinned  master (non-editable)
```

`ARC3-Inference` was snapshotted **dirty** — there were uncommitted changes, so `aa69123` does not
reconstruct what actually ran. **The authoritative artifact is the Kaggle dataset snapshot**, vendored
byte-for-byte into `agent/reference/`. The three SHAs are recorded for provenance only and must not be
presented as a reproducible checkout.

### 3.2 Why this clears criterion (4) despite having no CUDA — the decisive finding

The solver is **not coupled to vLLM's Python API**. It is an OpenAI-compatible HTTP client. From
`configs/inference.json`:

```json
"shared": { "model_name": "vrfai/Qwen3.6-27B-FP8",
            "base_url": "http://127.0.0.1:1234/v1",
            "provider": "vllm", "context_window": 32768 }
```

and the repo ships `configs/inference.openrouter.json`, identical but for
`"base_url": "https://openrouter.ai/api/v1"`, `"provider": "openrouter"`. **The provider is already
pluggable, and the authors already use it against two different backends.** So the local swap replaces
the *server*, not the solver:

```
vLLM serving vrfai/Qwen3.6-27B-FP8  →  mlx_vlm server serving mlx-community/Qwen3.6-27B-4bit
```

Both expose `/v1` on `127.0.0.1`. The solver source — `inference/agent/{prompts,action_names,
runtime_state,python_tool_sandbox}.py` — is untouched. This is what preserves the harness saving that
criterion (4) exists to protect, and it is the reason local-only is viable at all.

The Kaggle-side CUDA assertion in `setup_commands.json` (`assert_expected_cuda_gpu`) **early-returns when
`/kaggle/input` does not exist**, so it does not fire off-Kaggle. The 27 GB FP8 snapshot and the 4.8 GiB
CUDA wheelhouse are **not needed locally** — only the 439 KB source bundle plus a 16.1 GB MLX model.

### 3.3 Expected public behaviour

Interactive "Save & Run" plays the competition's **bundled environment files offline, with no gateway**;
only a real competition rerun (`KAGGLE_IS_COMPETITION_RERUN`) waits for the Kaggle gateway and plays the
live Arcade. So local instrumented play needs neither the online API nor internet. The online API remains
reachable from the M5 Pro separately, which is what the reset experiment (REPLAY-DET/RESET-ACCT) requires.

Reference operating point: `max_runtime_minutes: 45` per game, `n_passes: 20`, `concurrent_jobs: 32`,
`context_window: 32768` (server `max_model_len` 65536), `temperature 0.6 / top_p 0.95 / top_k 20`,
thinking enabled, prefix caching on, multimodal `context: current_grid, upscale: 4`.

### 3.4 Reproduction target

**Hard (S1-b exit):** ≥1 scored public-game level completed locally with the vendored solver, transition
log on disk.

**Reported, not gated:** the gap against LB **1.21**, stated together with the stack delta that confounds
it. Two independent reasons a tolerance band on 1.21 would be false precision:

1. The author states plainly that the readable notebook did **not** reproduce the milestone score — *"we
   haven't had the same lucky result with this one."* Run-to-run variance is large and undocumented.
2. We run a different quantization (FP8 → 4-bit) on a different serving stack on a different accelerator.

Gating on a number neither of these permits us to interpret would manufacture a verdict. The gap is
quantified and explained per the manifest's `on_fail` text; it does not produce a pass/fail.

### 3.5 Permitted deviations — enumerated in advance

Anything outside this list is a logged deviation. Each lands in `agent/patches/` as a patch file; the
vendored reference itself is never edited in place.

| # | Deviation | Why | Risk it introduces |
|---|---|---|---|
| DEV-1 | vLLM server → `mlx_vlm` OpenAI-compatible server | no CUDA/Metal vLLM path | serving-side behaviour differences |
| DEV-2 | FP8 → MLX 4-bit `mlx-community/Qwen3.6-27B-4bit` | FP8 needs Hopper/Blackwell | **unquantified capability loss** |
| DEV-3 | `base_url` / `provider` / `model_name` in `inference.json` | point at the local server | none — the config is designed for this |
| DEV-4 | `concurrent_jobs: 32` → reduced | one 20-core GPU cannot serve 32 concurrent 32k-context requests | **changes the batching factor — see §5** |
| DEV-5 | Client-side tool-call / reasoning parsing shim, *if required* | `tool_call_parser: qwen3_coder` and `reasoning_parser: qwen3` are vLLM-side; MLX may not implement them | **the most likely single point of failure** |
| DEV-6 | Instrumentation hooks for the §4.2.1 transition schema | S1's whole purpose | must not alter solver control flow |
| DEV-7 | Skip the 27 GB FP8 snapshot and the CUDA wheelhouse | not loadable locally | none locally; both required again if we escalate to hybrid |

**DEV-5 is the one to test first on Day 2**, before anything else is built on top of it. If the local server
cannot emit parseable tool calls, the solver cannot act, and no amount of downstream work compensates.

---

## 4. License interpretation — four buckets, as an argument

Per V11 the buckets are independent, and only a models-and-weights or entrant-code failure changes the
Day-6 payload.

| Bucket | Finding | Verdict |
|---|---|---|
| **Entrant-authored code and methods** | Everything we write — harness, instrumentation, labelling pipeline, patches — is ours to license CC0/MIT-0. Nothing about the reference constrains it. | **CLEAR** — a constraint on us, not a screen |
| **Third-party material** | **Unresolved.** `kaggle datasets metadata` returns `licenses: []` for all three Tufa datasets — no license is declared in the metadata for the TAAF source bundle, the FP8 snapshot, or the wheelhouse. The bundle README says only that it is "Generated by TAAF". | **OPEN — compliance step, not a disqualification.** Sufficient for local measurement now; **must be resolved before Day 6 packaging** if any TAAF code is redistributed. Ask the authors on the discussion thread. Tracked as an S1-f blocker |
| **Models and weights** | `Qwen/Qwen3.6-27B` is **Apache-2.0**; `mlx-community/Qwen3.6-27B-4bit` inherits Apache-2.0. Commercial use, modification and redistribution permitted. This is the bucket the plan calls "the real screen". | **CLEAR** |
| **Winner license (CC-BY 4.0)** | Applies to a winning submission; affects no candidate choice. | **N/A** |

> ⛔ **PUBLISHING POLICY — see [`PUBLISHING.md`](../PUBLISHING.md).** Bucket 2 is closed by *scope*:
> the reproduction is never shipped, submitted or published. This repository is **never made public**;
> entrant-authored work is released as a new clean repository. **Deleting `agent/reference/` is not
> sufficient — git history counts as redistribution.**

The **weights bucket clears**, which is criterion (1) and the gating one. The open item is bucket 2, and
it is a redistribution question with a known remedy, not a screen failure. It does **not** block S1-b
through S1-e; it blocks only the Day-6 payload if TAAF code ships inside it.

---

## 5. Consequence for the S1-c latency measurement — read before Day 3

§4.3 requires per-action latency "under the *actual* batching pattern — N parallel stateless game threads
over one shared GPU", and warns that a single-threaded number misleads by the batching factor.

DEV-4 changes that factor. The reference runs `concurrent_jobs: 32` against a datacentre GPU; one M5 Pro GPU
serving a 27B model at 32k context cannot hold 32 concurrent streams. **Whatever concurrency we actually
run is the number the latency table must be generated at, and it must be recorded beside every latency
figure.** A p50 measured at concurrency 4 is not comparable to the reference's, and any extrapolation to
the Kaggle envelope must state the factor explicitly rather than scaling silently.

This is also the most likely route to the escalation trigger in §6: if local concurrency is so low that
the Day-5 run cannot reach usable volume, that is a measurement about *our* machine, not about the agent.

---

## 6. Escalation trigger — pre-registered, so it is not decided under Day-4 pressure

The user's decision was *"local only first, and if it proves not optimal then hybrid."* "Not optimal" is
not decidable in the moment, so it is fixed here in advance. **Escalate to hybrid (local harness +
rented CUDA for the reference run) on the first of:**

1. **DEV-5 fails and no client-side shim works by end of Day 2** — the local server cannot produce parseable
   tool calls, so the solver cannot act.
2. **Day-3 end, still no scored public level locally** — this is already §7 ladder item 2, which currently
   points at `reference_alternate`. Note the correlation problem in §7 below: the alternate is *also*
   vLLM, so it does not hedge stack risk. Under a stack-shaped failure, escalate the **accelerator**, not
   the reference.
3. **Sustainable local concurrency < 4** — the Day-5 run cannot reach volume sufficient for the frequency
   ranking, and §4.6's volume caveat would swallow the result.
4. **Peak resident set > 44.06 GiB** (85% of the 51.84 GiB working set) with the compact models
   co-resident — no headroom for the instrumentation or the S3 components priced later.

Escalation cost is charged explicitly, per §1's zero-float rule, and written into the ledger at the moment
it is taken. Escalating is **not** a descope — it buys fidelity back; the day it costs is the price.

---

## 7. Alternate reference — mbmmurad LB 0.86

| Field | Value |
|---|---|
| **Notebook** | `mbmmurad/arc-agi-3-lb-0-86-3rd-place-candidate-milestone` (id_no `124697453`) |
| **Model** | Kaggle model source `google/gemma-4/Transformers/gemma-4-31b-it/1` |
| **Backend** | vLLM (`philipvonderlind/vllm-deps`, `mbmmurad/vllm-0-23-0-tf5-wheelhouse`) |
| **Accelerator** | `machine_shape: NvidiaRtxPro6000`, `enable_internet: false` |
| **Self-contained** | Yes — no external solver dataset; the notebook carries its own logic (103 KB source) |
| **Reproduction target** | LB **0.86**, reported on the scorer's 0–100 scale |
| **Local substitute weights** | a 4-bit MLX Gemma-4-31B build — **must be identified and its license checked on the day it is needed**, not assumed |
| **Permitted deviations** | DEV-1–DEV-6 as above, with the Gemma model substituted for Qwen |

**Selection rationale.** Chosen over ko0kip's Gemma reflection agent because it reports a concrete
leaderboard score, which criterion (3) requires and ko0kip's does not supply. Chosen for **decorrelation**
from the primary: a different model family (Gemma vs Qwen), a different code lineage (self-contained
notebook vs Tufa's multi-repo framework), and no shared source bundle — so a solver-specific failure in
the primary says nothing about the alternate. Its self-containedness also makes it materially faster to
vendor on Day 4, which is the point at which the alternate gets used at all.

**Stated limitation of this alternate — the honest part.** It shares the primary's vLLM/CUDA serving
stack. It therefore hedges **solver-specific** failure and hedges **nothing** about the DEV-1/DEV-2/DEV-5 stack
risk, which is the likeliest local failure mode. There is no available alternate that hedges stack risk,
because *every* strong public reference uses this stack. The hedge against stack risk is the §6
accelerator escalation, not this alternate. §7 of the execution plan sends a Day-4 miss to the alternate;
that instruction is correct only when the failure is solver-shaped. **Diagnose which before switching** —
switching references to fix a stack problem would cost a day and change nothing.

---

## 8. What is vendored on Day 2

```
agent/reference/taaf/          # Kaggle dataset snapshot, byte-for-byte, unmodified
agent/patches/                 # DEV-1–DEV-7, one patch file each; the diff is the audit trail
```

Local prerequisites to confirm before S1-b starts: `mlx-vlm` installed and serving
`mlx-community/Qwen3.6-27B-4bit` on `127.0.0.1:1234/v1`; PyTorch/MLX present (neither was installed at
pre-flight — see `notes/s1-verification.md`, accelerator inventory, "Software stack present"); `arc-agi`
runtime installed (reference pins `arc-agi==0.9.8`; our S0 starter resolved `arcengine==0.9.3` — **record
which version the local play actually uses**, the skew is a real reproduction variable).

---

## Target hardware, read from the reference's own deployment code — 2026-07-27

```python
# agent/reference/taaf/src/tufa-arc-agi-framework/src/taaf/deploy_kaggle.py
COMPETITION_SLUG    = "arc-prize-2026-arc-agi-3"
DEFAULT_ACCELERATOR = "NvidiaRtxPro6000"
```

The competition accelerator is the **NVIDIA RTX PRO 6000 (Blackwell, 96 GB)** — not the RTX A6000
(Ampere) and not the RTX 6000 Ada. Both share the "6000" name and neither is the right target; the
three differ by roughly 6× in rental price and 2× in VRAM.

Reference run configuration, from `configs/inference.json` and `Makefile:kaggle-duck`:

| | |
|---|---|
| accelerator | NVIDIA RTX PRO 6000, 96 GB |
| `gpu_count` | **2** |
| `tensor_parallel_size` | 1 — one model instance per GPU, not sharded across them |
| `gpu_memory_utilization` | 0.92 (~88 GB usable per card) |
| `CONCURRENT_JOBS` | **28** |
| `MAX_RUNTIME_MINUTES` | 132 |
| `ANALYZER_TIMEOUT` | 900 |

**Correction.** Earlier notes and my own summaries state the reference ran at **concurrency 32**. It is
**28**. The figure was never measured, only assumed.

**Why this matters beyond bookkeeping.** ~88 GB of usable VRAM per card is what let the reference hold
28 concurrent long-context games. The local machine has 69 GB of *unified* memory shared with the OS and
everything else, so concurrency 28 was never reachable locally at any precision — the gap is structural,
not a tuning oversight.

Rental, if the hybrid escalation is taken (RunPod, checked 2026-07-27): RTX PRO 6000 at **$1.69/hr**
community, **$1.99/hr** secure. A single card reproduces the architecture and the memory envelope; the
second is needed only to reproduce 28-way concurrency exactly. Storage is billed separately and
continues while the pod is stopped.
