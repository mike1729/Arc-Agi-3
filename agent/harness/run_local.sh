#!/usr/bin/env bash
# Canonical local launcher — reproduces the reference Makefile's config -> environment/CLI translation.
#
# WHY THIS EXISTS. `inference.framework.run` is NOT the reference's entry point; the Makefile is. The
# Makefile reads the JSON config into LOCAL_ANALYZER_* variables, EXPORTS them (Makefile:188-202), and
# converts a few settings into CLI flags. Driving the module directly — as our first S1-b runs did —
# silently drops every config-sourced setting to its argparse/code default. That bypass caused two real
# errors:
#
#   * D6 request logging was off, because `analyzer.save_request_logs` reaches the runner only as
#     `--save-request-logs` (Makefile:153, and the flag at the end of the `_taaf-run` recipe).
#   * `analyzer.tool_steps: 0` (UNLIMITED, Makefile:145) was replaced by the code default of 12, so the
#     D9 experiment was measured against a baseline the reference never uses.
#
# `analyzer.yield_seconds` (default 60) was likewise never applied by the bypass.
#
# Use this script for every local run. Verify the effective values from the HarnessSolver(...) repr the
# runner prints at startup — do not assume the JSON took effect.
#
# Usage:
#   bash agent/harness/run_local.sh --game vc33 --run-name my-run [extra runner args...]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$REPO_ROOT/agent/work/taaf/src/ARC3-Inference"
CONFIG_PATH="${CONFIG_PATH:-configs/inference.local-mlx.json}"
PY="$REPO_ROOT/.venv/bin/python"
ENV_FILES="${ARC_ENV_FILES:-$REPO_ROOT/data/environment_files}"

[ -f "$WORK/$CONFIG_PATH" ] || { echo "config not found: $WORK/$CONFIG_PATH (run build_local.sh)"; exit 1; }

# Mirror the Makefile's CONFIG_VALUE lookups, including its fallback chain and defaults.
eval "$("$PY" - "$WORK/$CONFIG_PATH" <<'PYEOF'
import json, sys, shlex
c = json.load(open(sys.argv[1]))
shared, an, srv = c.get("shared", {}), c.get("analyzer", {}), c.get("server", {})
def g(d, k, default=None):
    v = d.get(k)
    return default if v is None else v
vals = {
    "LOCAL_ANALYZER_BASE_URL":          g(an, "base_url", g(shared, "base_url", "")),
    "LOCAL_ANALYZER_PROVIDER":          g(an, "provider", g(shared, "provider", "vllm")),
    "LOCAL_ANALYZER_MODEL_ID":          g(an, "model_id", g(srv, "served_model_name", g(shared, "model_name", ""))),
    "LOCAL_ANALYZER_CONTEXT_WINDOW":    g(an, "context_window", g(shared, "context_window", 32768)),
    "LOCAL_ANALYZER_MAX_OUTPUT":        g(an, "max_output", 0),
    "LOCAL_ANALYZER_TIMEOUT":           g(an, "timeout", 120),
    "LOCAL_ANALYZER_TEMPERATURE":       g(an, "temperature", 0.6),
    "LOCAL_ANALYZER_TOP_P":             g(an, "top_p", 0.95),
    "LOCAL_ANALYZER_TOP_K":             g(an, "top_k", 20),
    "LOCAL_ANALYZER_TOOL_STEPS":        g(an, "tool_steps", 0),      # 0 == UNLIMITED; the reference value
    "LOCAL_ANALYZER_TOOL_TIMEOUT":      g(an, "tool_timeout", 30),
    "LOCAL_ANALYZER_TOOL_OUTPUT_TOKENS":g(an, "tool_output_tokens", 1024),
    "LOCAL_ANALYZER_YIELD_SECONDS":     g(an, "yield_seconds", 60),  # never applied by the direct-module bypass
    "LOCAL_ANALYZER_ENABLE_THINKING":   str(g(an, "thinking", True)).lower(),
    "LOCAL_ANALYZER_APP_NAME":          g(an, "app_name", "ARC3 Agent Harness"),
    # Makefile:157-158,204-205 export these. vision_context.py reads MULTIMODAL_CONTEXT with an EMPTY
    # default, so omitting it silently disables multimodal grid input — and the reference config sets
    # "current_grid". A launcher that drops them changes what the model sees.
    "MULTIMODAL_CONTEXT":               g(c.get("multimodal", {}), "context", ""),
    "MULTIMODAL_UPSCALE":               g(c.get("multimodal", {}), "upscale", 16),
}
for k, v in vals.items():
    print(f"export {k}={shlex.quote(str(v))}")
save = bool(g(an, "save_request_logs", False))
flag = "--save-request-logs" if save else "--no-save-request-logs"
env = c.get("environment", {})
n_passes = g(env, "n_passes", 1)
conc = g(env, "concurrent_jobs", 1)
runtime_min = g(env, "max_runtime_minutes", 45)
model_id = shlex.quote(str(vals["LOCAL_ANALYZER_MODEL_ID"]))
print("export _SAVE_REQUEST_LOGS_FLAG=" + flag)
print("export _MODEL=" + model_id)
print("export _N_PASSES=" + str(n_passes))
print("export _CONCURRENT_JOBS=" + str(conc))
print("export _MAX_RUNTIME_MIN=" + str(runtime_min))
# Makefile:152 feeds analyzer.timeout into ANALYZER_TIMEOUT and passes it as --analyzer-timeout.
# Exporting LOCAL_ANALYZER_TIMEOUT alone is NOT enough: the --analyzer-timeout flag in run.py
# defaults to 120 and reaches HarnessSolver directly, so the CLI default silently overrides the
# config. This is what made the D10 timeout fix ineffective on its first attempt.
print("export _ANALYZER_TIMEOUT=" + str(g(an, "timeout", 120)))
PYEOF
)"

echo "==> effective analyzer settings (from $CONFIG_PATH, Makefile semantics):"
echo "    tool_steps=$LOCAL_ANALYZER_TOOL_STEPS (0 = UNLIMITED)  max_output=$LOCAL_ANALYZER_MAX_OUTPUT"
echo "    yield_seconds=$LOCAL_ANALYZER_YIELD_SECONDS  thinking=$LOCAL_ANALYZER_ENABLE_THINKING"
echo "    request logs: $_SAVE_REQUEST_LOGS_FLAG"
echo "    n_passes=$_N_PASSES concurrent_jobs=$_CONCURRENT_JOBS max_runtime_min=$_MAX_RUNTIME_MIN"
echo "    multimodal: context='$MULTIMODAL_CONTEXT' upscale=$MULTIMODAL_UPSCALE"
echo "    analyzer timeout: ${_ANALYZER_TIMEOUT}s (passed as --analyzer-timeout, NOT just env)"

cd "$WORK"
export CONFIG_PATH
exec "$PY" -m inference.framework.run \
  --model "$_MODEL" \
  --re-arc-environments-dir "$ENV_FILES" \
  --n-passes "$_N_PASSES" \
  --concurrent-jobs "$_CONCURRENT_JOBS" \
  --max-runtime-minutes "$_MAX_RUNTIME_MIN" \
  --analyzer-timeout "$_ANALYZER_TIMEOUT" \
  --experiments-dir "$REPO_ROOT/logs/runs" \
  "$_SAVE_REQUEST_LOGS_FLAG" \
  "$@"
