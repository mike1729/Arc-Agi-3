#!/usr/bin/env bash
# Rebuild the local working copy of the frozen reference from the pristine vendored snapshot.
#
# agent/reference/taaf/  is the unmodified Kaggle dataset snapshot and is NEVER edited in place.
# agent/work/taaf/       is a throwaway working copy, rebuilt by this script.
# agent/patches/*.patch  is the audit trail — the diff IS the record of every deviation.
#
# ⛔ PUBLISHING: agent/reference/ is an UNLICENSED third-party snapshot. This repository is NEVER made
#    public — entrant-authored work is released as a new clean repository. Deleting the directory is not
#    sufficient; git history counts as redistribution. See PUBLISHING.md.
#
# Deviations applied here are the ones enumerated in notes/s1-reference-freeze.md §3.5. Anything not
# on that list and not applied by this script is an unlogged deviation, which is the thing the
# vendoring convention exists to prevent.
#
# Usage:  bash agent/harness/build_local.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REF="$REPO_ROOT/agent/reference/taaf"
WORK="$REPO_ROOT/agent/work/taaf"
PATCHES="$REPO_ROOT/agent/patches"

echo "==> rebuilding $WORK from $REF"
rm -rf "$WORK"
mkdir -p "$(dirname "$WORK")"
cp -R "$REF" "$WORK"

# ---------------------------------------------------------------------------
# D8 — guard the top-level `from re_arc import EnvSampler` in run.py.
#
# NOT in the original frozen deviation list (D1-D7): discovered on Day 2 and logged as a new
# deviation, per the freeze's rule that anything outside the list is a deviation to log.
#
# `re_arc` (arc-agi-3-local) is private Tufa Labs code: not on PyPI, and
# github.com/Tufalabs/re-arc-3 returns 404. It is also deliberately excluded from this very bundle
# (taaf/deploy_kaggle.py: _SHARE_EXCLUDE_REPOS = ("re-arc-3",)), and taaf/game_api.py already imports
# it lazily "so the package stays importable in deployments that ship without the re-arc-3 snapshot".
# run.py did not, which makes the shared bundle unimportable. The guard restores the authors' own
# stated intent rather than changing behaviour: re_arc is used ONLY for game-id enumeration, never
# for gameplay.
# ---------------------------------------------------------------------------
echo "==> applying D8-guard-re_arc-import.patch"
patch -s -p0 -d "$REPO_ROOT" < "$PATCHES/D8-guard-re_arc-import.patch"

# ---------------------------------------------------------------------------
# D6b — log the response payload and API rejections.
#
# The stock request logger writes only the REQUEST. Raw model output is then recoverable solely from the
# NEXT turn's accumulated history, which loses the final turn of every episode, and an API rejection is
# never captured at all. Both are evidence `invalid_output_interface` is defined on. Logging only —
# control flow is unchanged, per D6's constraint that instrumentation must not alter solver behaviour.
# ---------------------------------------------------------------------------
echo "==> applying D6b-log-response-and-rejections.patch"
patch -s -p0 -d "$REPO_ROOT" < "$PATCHES/D6b-log-response-and-rejections.patch"

# ---------------------------------------------------------------------------
# D3 + D4 — local inference config.
#
# D3: point base_url/model_name at the local MLX server. `provider` deliberately stays "vllm":
#     probing showed the MLX server accepts the vLLM payload branch unchanged (top_k,
#     chat_template_kwargs, seed), so keeping it minimises the deviation surface.
# D4: concurrency 32 -> 2 and n_passes 20 -> 1. One 20-core GPU cannot hold 32 concurrent 32k-context
#     streams. THIS CHANGES THE BATCHING FACTOR the latency budget rests on — the concurrency actually
#     used must be recorded beside every latency figure (freeze §5).
# D6: save_request_logs is written here for completeness, but BE WARNED — IT IS INERT IN THE CONFIG.
#     run.py sources it from the CLI flag `--save-request-logs` (BooleanOptionalAction, default False)
#     and never reads the JSON field. The first two ft09 runs produced no requests.jsonl because of
#     this. YOU MUST PASS `--save-request-logs` ON THE RUN COMMAND.
#     Same class of trap as analyzer.tool_steps, which is read from LOCAL_ANALYZER_TOOL_STEPS and
#     otherwise defaults to 12 in code. The JSON config is NOT a complete control surface: verify every
#     setting reaches the running object, via the HarnessSolver(...) repr the runner prints at startup.
# ---------------------------------------------------------------------------
echo "==> writing configs/inference.local-mlx.json (D3 + D4 + D6)"
MODEL_PATH="${MLX_MODEL_PATH:-$HOME/models/mlx/Qwen3.6-27B-4bit}"
CONCURRENCY="${LOCAL_CONCURRENT_JOBS:-4}"
python3 - "$WORK" "$MODEL_PATH" "$CONCURRENCY" <<'PY'
import json, os, sys, pathlib
work, model, concurrency = sys.argv[1], sys.argv[2], int(sys.argv[3])
cfgdir = pathlib.Path(work) / "src/ARC3-Inference/configs"
cfg = json.loads((cfgdir / "inference.json").read_text())
cfg["shared"]["model_name"] = model                     # D3
cfg["shared"]["base_url"] = "http://127.0.0.1:1234/v1"  # unchanged — reference is already local
cfg["shared"]["provider"] = "vllm"                      # unchanged — MLX accepts this payload branch
cfg["environment"]["concurrent_jobs"] = concurrency     # D4
cfg["environment"]["n_passes"] = 1                      # D4
# Without re_arc, tag/dataset selection is unanswerable (D8 raises on it), and the "__auto__"
# environments_dir sentinel resolves via `import re_arc` in taaf/game_api.py::_resolve_environments_dir.
# The generated config must therefore encode BOTH, or it is not runnable as written.
cfg["environment"]["include_tags"] = []                 # D8: tag selection needs re_arc
cfg["environment"]["exclude_tags"] = []
cfg["environment"]["environments_dir"] = os.environ.get(
    "ARC_ENV_FILES", str(pathlib.Path.cwd() / "data/environment_files"))
cfg["analyzer"]["save_request_logs"] = True             # D6
# D10 — analyzer timeout 120 -> 900 s. THE BUG THAT INVALIDATED EVERY EARLIER LOCAL RUN.
# The reference's 120 s is calibrated for FP8 on an RTX PRO 6000. Measured here: generation durations
# median 142 s, max 426 s, with 62% exceeding 120 s — so most requests were cut off mid-generation and
# retried, and the "analysis" events in those runs ARE the failures. 900 s is ~2x the measured max.
# (The reference hit 46 timeouts of its own at 120 s, ~1% of its generations, so 120 s is marginal even
# on reference hardware — but 1% is a retry and 62% is a harness that cannot measure anything.)
cfg["analyzer"]["timeout"] = 900                        # D10
cfg["experiments"]["root_dir"] = "logs/runs/{username}"
cfg["deployment"]["target"] = "inline"
cfg["deployment"]["slurm"]["start_local_server"] = False
(cfgdir / "inference.local-mlx.json").write_text(json.dumps(cfg, indent=2) + "\n")
print(f"    model={model}  concurrent_jobs={concurrency}  env_dir={cfg['environment']['environments_dir']}")
PY

echo "==> done. Work copy ready at $WORK"
echo "    REMINDER: pass --save-request-logs on the run command; the config field is inert."
echo "    Reference snapshot left untouched at $REF"
