# Related Work

**Status:** Working document. Sources are recorded as they become relevant to implementation decisions.

---

## ARC-AGI-3 agents — the state of the public field as of 2026-07-26

Surveyed during the S1-a reference screen (`notes/s1-reference-freeze.md`). The survey itself is a
result worth stating: **the public field splits cleanly into frontier-API coding agents that score highly
but cannot enter the competition, and local open-weight agents that can.** Kaggle evaluation runs with no
internet, so an agent requiring a hosted-model call is ineligible by construction.

### Frontier-API coding agents — strong, ineligible

- **Rodionov, *Executable World Models for ARC-AGI-3 in the Era of Coding Agents*** (arXiv:2605.05138;
  also Springer). A coding agent maintains an **executable Python world model**, verifies it by exact
  replay against recorded observations, refactors it toward simpler abstractions, and plans through it
  before acting. No game-specific code. GPT-5.5 solves 15/25 public games at 58.12% mean RHAE; GPT-4.5
  reaches 41.29%. Follow-up: *Do Coding Agents Need Executable World Models, Simplification, and
  Verification to Solve ARC-AGI-3?* (arXiv:2607.15439). Code: `astroseger/arc-3-agents-baseline1` (MIT).
  With GPT-5.6-sol the `ewma_sv_v1.6` agent **fully solves all 25 public games at ~99% mean RHAE** — which
  the authors themselves read as *saturation of the public set*, not as ARC-AGI-3 being solved.

  **Relevance to this project.** This is the closest published relative of the Track A thesis and the
  sharpest available contrast: an *explicit, executable, exactly-verified* world model, i.e. the extreme
  end of the reconstruction/exact-delta axis that arm **C** occupies in S3. Its success is evidence that
  in this environment class an exactly-verifiable model is a strong strategy, which is precisely why
  **arm C is mandatory** and why "JEPA vs reconstruction" would be the wrong framing. Its verification
  step — replay the model against recorded observations and reject on mismatch — is also the mechanism a
  latent predictor structurally *cannot* perform, and is the concrete form of the Delay concern.

### Local open-weight agents — the eligible reference class

The Kaggle leaderboard, not arXiv, is where these live. Every strong one serves an open-weight model with
**vLLM on an NVIDIA RTX PRO 6000**, fully offline:

- **Tufa Labs "duck harness"** (Bessis, Cottaar, Pressman, Smit, Tesnar, Viel) — Qwen3.6-27B-FP8, winner
  of the June 30 milestone at LB 1.21. **Frozen as this project's S1 primary reference.** Architecturally
  it is also a world-model-maintaining agent with a Python tool sandbox, so the executable-world-model
  family currently occupies both the API and the open-weight ends of the field.
- **Gemma-4-31B agents** — `mbmmurad` (LB 0.86, frozen as this project's alternate) and `ko0kip`'s
  reflection agent.

### Benchmark-validity work

- **Liew, *Explore Before You Solve: The Speed–Depth Trade-off in Epistemic Agents for ARC-AGI-3***
  (arXiv:2605.25931; code `farmountain/aera-arc3-paper`, CC0). Presents AERA, an EXPLORE-before-PLAN
  agent on Qwen2.5, but its more consequential claim is a **benchmark-validity result**: all 25 public
  games are reachable by non-intelligent strategies — 10 in a single blind step, 5 after probing, 8 via
  repeated actions given budget, and 18 via a null-coordinate vulnerability. The conclusion is that the
  public set cannot discriminate intelligent exploration from trivial heuristics, and only the private
  55-game set tests what the benchmark claims to.

  **Relevance.** This is independent corroboration of this project's standing caution that public games
  are materially easier than hidden ones, and it sharpens it from a score gap into a *mechanism*: the
  public set is not merely easier, it is solvable by strategies that carry no world-modelling content at
  all. Any positive result measured only on public games is therefore weak evidence for the JEPA thesis
  specifically, because the thing being tested need not have been used.

  **Do not cite AERA's `0.2116` as an ARC score.** Its `run_eval.py` caps the ratio at 1.0 before
  squaring and reports on a 0–1 scale; the official core implementation squares the ratio on a 0–100
  scale and then caps the result at 115. AERA also estimates per-level action counts as
  `total_actions / n_levels`. The figure is a local surrogate metric. This was the finding that removed
  AERA from reference consideration (`notes/s1-reference-freeze.md` §1.1).

- **ARC Prize Foundation, *ARC-AGI-3: A New Challenge for Frontier Agentic Intelligence***
  (arXiv:2603.24621). The benchmark paper.

### The gap this project sits in

Every agent above is a **prompted or coding-agent architecture over a general-purpose LLM**. None learns a
*compact, history-conditioned latent world model* from interaction. The published successes come from
externalizing the world model as inspectable, executable code and verifying it exactly — the opposite
design choice from a reconstruction-free latent predictor. That contrast is the S3 question, and the
field's current evidence sits on the far side of it, which is the honest starting position for the paper.
