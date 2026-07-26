# S1 Verification Record

**Status:** S0 complete — the untouched official starter passed the visible Kaggle run and the hidden
competition rerun. The verification register is recorded, with V2 conflicted, V9 partial, and V10
remaining measurement-derived rather than promoted to platform facts.

## Pre-flight smoke test — 2026-07-25

### ARC-AGI-3 API access

- API credential issued and loaded without recording the credential in this repository.
- Authenticated `GET https://three.arcprize.org/api/games` returned **HTTP 200** from the development
  machine.
- Result: **PASS** — the machine can reach the public ARC-AGI-3 API using the issued credential.
- Source checked 2026-07-25:
  <https://docs.arcprize.org/api-reference/games/list-available-games>

### Official starter

- Repository: <https://github.com/arcprize/ARC-AGI-3-Agents.git>
- Commit: `10213de83f01df0ef4f0149ee9f8408dcc3772fb`
- Agent/game: official `random` agent on `ls20-9607627b`
- Observed completion time: `2026-07-25 22:22:28` (timezone not emitted in the supplied log)
- Configured maximum agent actions: `80`
- Scorecard-reported actions: `81`
- Runtime: `28.77 s`
- Reported average rate: `2.82 fps`
- Levels completed: `0 / 7`
- Score: `0.0`
- Scorecard ID: `8a72615c-2bdc-4d13-b099-05c4979216cf`
- Scorecard:
  <https://three.arcprize.org/scorecards/8a72615c-2bdc-4d13-b099-05c4979216cf>
- Recording:
  `/Users/michal/Workspace/ARC-AGI-3-Agents/recordings/ls20-9607627b.random.80.91a387ea-d7e0-4ee7-8d37-71eec49cb01a.recording.jsonl`
- Recording file presence verified locally on 2026-07-25.
- Scorecard closure was logged successfully before process exit.
- Result: **PASS** — the official starter initialized the environment, executed actions, produced a
  recording, and closed a scorecard. The zero score is not a failure for this execution-path smoke test.

### Observation for the reset/accounting experiment

The agent stopped at its configured `MAX_ACTIONS` of 80 while the scorecard reported 81 actions. Do not
interpret the extra action yet; it may be initialization/RESET accounting or a difference between the
agent loop counter and scorer counter. Preserve this run as evidence and resolve the discrepancy in the
pre-registered reset/action-accounting experiment rather than silently normalizing it.

---

## S0 platform constants — 2026-07-25

### V5–V7 — Competition mode

**Source:** <https://docs.arcprize.org/toolkit/competition_mode>

- **V5 verified:** only level resets are permitted; game resets are not allowed and become level resets.
- **V6 verified:** each environment may be passed to `make()` only once in competition mode.
- **V7 verified:** competition mode permits one scorecard and does not expose an in-flight scorecard.
  Kaggle is forced into this mode.

### V8 — Scoring

**Source:** <https://docs.arcprize.org/methodology>

- **Verified:** per-level score is
  `(human_baseline_actions / ai_actions)^2`, capped at `1.15`.
- Per-game aggregation is weighted by the 1-indexed level number.
- Total score is the average of all game scores.
- Only interactions that affect game state count as actions; internal reasoning and tool operations do not.

### V9 — Rate limit

**Source:** <https://docs.arcprize.org/rate_limits>

- **Partially verified:** the online ARC API is limited to `600 requests/minute`.
- No separate Kaggle-local request cap was found in the official ARC documentation. Treat that part as
  unresolved rather than promoting the online API limit to a Kaggle inference limit.

### V10 — Runtime envelope

- **Not verified:** `~8 h wall-clock` and `~10 actions/s` remain working assumptions.
- Derive the usable runtime and throughput envelope from the Kaggle starter run and the measured S1
  reference runs. Do not use either number as a platform fact.
- The untouched starter's visible Kaggle commit run completed successfully in `20.3 s` on a CPU-only
  session. This is evidence for packaging/boot latency, not a bound on a hidden multi-game rerun and not
  evidence for the `10 actions/s` assumption.
- The hidden rerun later succeeded. Kaggle showed `Succeeded · 3h ago` when checked at
  `2026-07-26 05:20 UTC`; relative-time rounding bounds the submission-to-result interval to roughly
  `4 h 42 min`–`5 h 41 min`. This is one workload measurement, not verification of an `~8 h` platform
  limit.

### V12 — ACTION7 parity

**Source for the standardized interface:** <https://docs.arcprize.org/actions>

- The official interface defines `ACTION7` as Undo when the game advertises it.
- **Verified at the action-enum/interface boundary:** the local starter lock resolves `arcengine==0.9.3`;
  the installed local enum contains `RESET` and `ACTION1` through `ACTION7`, with `ACTION7.value == 7`.
  The untouched Kaggle starter imports the same `GameAction` interface from `arcengine` and chooses
  dynamically from the enum rather than hard-coding a reduced action list.
- This establishes local/Kaggle exposure parity for the agent interface. It does **not** mean every game
  advertises Undo; per-game availability remains governed by the observation returned by that game.
- Local evidence: official starter commit `10213de83f01df0ef4f0149ee9f8408dcc3772fb`,
  `uv.lock`, and a direct enum dump from its `.venv`.
- Kaggle evidence: official pinned notebook V13,
  <https://www.kaggle.com/code/inversion/arc3-sample-submission-random-agent?scriptVersionId=306264908>
  (inspected and copied unchanged 2026-07-25).

---

## S0 Kaggle starter path proof — 2026-07-25

### Provenance and unchanged-copy check

- Official pinned source: `inversion/arc3-sample-submission-random-agent`, Version 13,
  `scriptVersionId=306264908`.
- Source URL:
  <https://www.kaggle.com/code/inversion/arc3-sample-submission-random-agent?scriptVersionId=306264908>
- Private copy: `michalswietek/arc3-sample-submission-random-agent-1b8360`.
- Copy URL:
  <https://www.kaggle.com/code/michalswietek/arc3-sample-submission-random-agent-1b8360>
- Kaggle displayed `Copied from inversion (+0, -0)`. The four copied cells were inspected before the
  run and matched the pinned source; no code or title edit was made.
- Inherited runtime settings were preserved: no accelerator, Internet off, no persistence, Python, and
  `Pin to original environment (2026-03-20)`.

### Visible validation

- Version 1 run ID: `337941208`.
- Result: **PASS** — `20.3 second run - successful`.
- Output contract: the untouched non-rerun branch produced `submission.parquet`.

### Competition submission and hidden rerun

- Submitted notebook version: Version 2, `scriptVersionId=337941384`.
- Submission description:
  `Notebook ARC3 Sample Submission - Random Agent 1b8360 | Version 2`.
- Kaggle confirmed one submission remaining immediately before submission; this consumed the day's
  only slot.
- Visible Version 2 notebook run: **PASS**.
- Hidden rerun: **PASS** — Kaggle status `Succeeded`.
- Public score: `0.06`.
- Terminal result observed: `2026-07-26 05:20 UTC`; Kaggle displayed `Succeeded · 3h ago`, so the
  wall-clock interval is bounded to approximately `4 h 42 min`–`5 h 41 min` rather than asserted to
  false precision.
- Warning text: none reported.
- **S0 exit verdict: PASS** — the untouched starter passed both required execution paths and the
  submission is recorded in `submissions/ledger.md`.

---

## Pre-flight accelerator inventory — 2026-07-25

Pre-flight §2 item 4. Measured on the development machine, not asserted. This is the **development**
accelerator; Kaggle's runtime is a separate target and is *not* characterized here. S1-a
(`reference_primary.accelerator` / `reference_alternate.accelerator`) cites this section.

### Host

| Field | Value | Source |
|---|---|---|
| Model | MacBook Pro, `Mac17,9` | `system_profiler SPHardwareDataType` |
| Chip | Apple M5 Pro | `system_profiler SPHardwareDataType` |
| CPU cores | 18 physical / 18 logical — 6 `Super` + 12 `Performance` | `sysctl hw.perflevel{0,1}.name`, `hw.physicalcpu` |
| Unified memory | 64 GB (`68719476736` B) | `sysctl hw.memsize` |
| Storage free | 703 GiB on `/System/Volumes/Data` | `df -h` |
| Power | AC attached at time of inventory | `pmset -g batt` |

### Accelerator

| Field | Value | Source |
|---|---|---|
| GPU | Apple M5 Pro integrated, 20 cores | `system_profiler SPDisplaysDataType` |
| GPU architecture | `applegpu_g17s` | `MTLDevice.architecture.name` |
| Memory model | Unified (`hasUnifiedMemory = true`) — no discrete VRAM | `MTLDevice` |
| `recommendedMaxWorkingSetSize` | `55662788608` B = **51.84 GiB** | `MTLDevice` |
| `maxBufferLength` | **38.88 GiB** — cap on a *single* allocation | `MTLDevice` |
| `iogpu.wired_limit_mb` | `0` (system default; not raised) | `sysctl` |
| API / driver | Metal 4, macOS 26.5.2 build `25F84`, Darwin 25.5.0, SDK 26.5 | `sw_vers`, `uname -a`, `xcrun --show-sdk-version` |
| **CUDA** | **None — not applicable.** No NVIDIA hardware; `nvidia-smi` and `nvcc` absent | `which` |

The manifest schema asks for "VRAM, driver, CUDA". On this machine the honest mapping is: VRAM →
`recommendedMaxWorkingSetSize` (51.84 GiB, shared with the OS and with the harness's own processes);
driver → macOS build + Metal version; CUDA → not applicable. Do not record a CUDA version.

### Software stack present

- Python 3.14.3 (Homebrew, `/opt/homebrew/bin/python3`); `uv` 0.10.11; no conda.
- **No PyTorch, no MLX installed.** MPS availability therefore **not yet measured** — `torch.backends.mps`
  was not probed because `torch` is absent. Install and confirm before S1-b.
- Ollama 0.32.3, with `qwen3.6:35b-mlx` (21 GB) already pulled.
- No `llama.cpp` binaries (`llama-cli` / `llama-server`) and no LM Studio CLI on `PATH`.

### Consequences for the Day-1 reference freeze — flagged, not resolved

These are inputs to S1-a selection criterion (2) ("fits your accelerator at the intended quantization
with the compact models resident"). None of them is decided here.

1. **No CUDA is the binding screen on reference candidates.** A public local-model agent whose harness
   assumes vLLM, `bitsandbytes`, or FlashAttention has no native path on this machine. Criterion (4) —
   "the harness is reusable, and that is where the saving comes from" — is where a CUDA-only reference
   costs the most: the saving evaporates before the model does. Screen the *harness's* backend
   assumptions on Day 1, alongside the four license buckets.
2. **`peak_vram_headroom: 0.15` is written against a discrete-VRAM model** and does not transfer as
   written. There is no fixed device budget here — the pool is shared with the OS and with the agent
   harness's own memory. Restate the threshold against `recommendedMaxWorkingSetSize` (51.84 GiB) on
   Day 1, and note that `iogpu.wired_limit_mb` can be raised if headroom binds. The `s1` manifest block
   is still `status: DRAFT`, so this is an edit, not an erratum — but it is S1-a's edit to make.
3. **`maxBufferLength` (38.88 GiB) is below the working set (51.84 GiB).** Sharded runtimes (MLX,
   llama.cpp) are unaffected; anything that allocates weights as one buffer is capped well under the
   apparent memory. Relevant only if a candidate does the latter.
4. **This is a laptop, and `throughput_degradation_max: 0.20` is measured over a full-length run.**
   Sustained multi-hour load on an actively-cooled portable will throttle. Under the ~8 h wall-clock
   working assumption (V10, unverified) this threshold is the one most likely to fail for a reason that
   is about the machine rather than about the reference. Measure it on the Day-5 full run, not on a
   short one, and record ambient/power state alongside.

### Open item — must be resolved at or before S1-a

Whether S1–S3 development actually happens on this machine, or on a rented CUDA box, is **not decided**
and changes finding 1 completely. If a rented accelerator is in scope, it needs its own inventory in this
same schema before the reference is frozen — the freeze names one accelerator, and Day 4's escalation to
the alternate is not the moment to discover the alternate assumed a different one.

**Result: COMPLETE for the pre-flight item** (the accelerator is inventoried and written down). The
inventory is not itself a pass/fail gate; `hardware_fit` is measured at S1-g against a frozen reference.

---

## Pre-flight Kaggle CLI access — 2026-07-25

Added as a pre-flight item because the CLI is on the critical path for **Day 6's offline bundling**
(§4.7 publishes the weights as a Kaggle dataset/model artifact), not only for S0's submission.

- Kaggle CLI `2.2.4`, installed via `uv tool install kaggle` → `~/.local/bin/kaggle`.
- Authenticated as `michalswietek`, `auth_method: ACCESS_TOKEN`.
- Credential lives at `~/.config/kaggle/access_token`, mode `600`. **Not** the legacy
  `~/.kaggle/kaggle.json`; no `KAGGLE_USERNAME` / `KAGGLE_KEY` in the environment. Nothing credential-
  bearing is stored in this repository.
- `kaggle competitions list` returned a populated result set without an auth error.
- Result: **PASS** — the submission and artifact-publishing path is reachable from the command line.

The Kaggle MCP server (`https://www.kaggle.com/mcp`) was evaluated on 2026-07-25 and **not adopted**.
Its advertised flow is a file-upload submit, which is the wrong shape for a notebook code competition;
and under a 1/day quota (V13) an agent-invocable submit tool puts a calendar-day-scarce resource behind
tool-call discretion. The CLI is also scriptable, which the `submissions/ledger.md` convention needs.

### Incidental confirmations from the same probe

- `arc-prize-2026-arc-agi-3` reports `userHasEntered: True` — independently confirms pre-flight item 1
  (account registered and entered), from a source other than the web UI.
- `arc-prize-2026-arc-agi-3` deadline `2026-11-02 23:59:00` — consistent with **V1**.

### ⚠ Conflict on V2 — paper deadline — UNRESOLVED, do not silently pick one

`kaggle competitions list -s "arc-prize-2026"` reports the paper track as:

    https://www.kaggle.com/competitions/arc-prize-2026-paper-track   2026-11-09 23:59:00

`gate_manifest.yaml → verification.items.V2_paper_deadline` currently records `verified: true`,
claim **"OFFICIAL deadline is Nov 8"**, sourced to <https://arcprize.org/competitions/2026/paper>.

**Nov 8 (ARC Prize site) vs Nov 9 23:59 (Kaggle API) — two official-looking sources disagree.** Note
that the same API call renders the main competition as `2026-11-02 23:59:00`, which matches V1's
"Nov 2, 23:59 UTC" exactly, so the API's rendering appears to be UTC and consistent; that makes the
Nov 9 reading hard to dismiss as a timezone artifact.

Not resolved here, and V2 is **not** edited on the strength of a CLI listing. To resolve: read both the
Kaggle paper-track overview page and the ARC Prize paper page on Day 1 and record which governs. Until
then V2's `verified: true` is **overstated** — the claim has a contradicting source of comparable
standing. `verification.status` is still `DRAFT`, so correcting it is an edit rather than an erratum.

Practical exposure is small either way: the internal ~Nov 5 target sits ahead of both dates, and ties
favour the earlier entry. The reason to fix it is that a constant marked `verified: true` with a known
contradiction is the failure mode the manifest exists to prevent.
