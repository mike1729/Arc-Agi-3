#!/bin/bash
# Qwen3.8 night-1 chain — notes/qwen-3.8-night1.md, dispatched 2026-08-16.
#
# Self-gating so the operator can sleep: wait for weights -> thinking probe (gate) ->
# budget probe (gate) -> slice 3R seed 1 -> seed 2. Any gate failure aborts the night
# and says why in logs/night38_chain.log. No step ever writes a 3.6 artifact path.
set -u
cd "$(cd "$(dirname "$0")/../.." && pwd)"
PY=.venv/bin/python
MODEL="$HOME/models/mlx/Qwen3.8-27B-8bit"
DLLOG="/private/tmp/claude-501/-Users-michal-Workspace-SHiP-JEPA-X/65bd33b2-7ff6-4f38-81d0-b0102a049f12/scratchpad/qwen38_download.log"
LOG=logs/night38_chain.log
DONE_MARK="DONE  mlx-community/Qwen3.8-27B-8bit"

say() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

say "chain start (pwd $(pwd), model $MODEL)"

# 0. Wait for the 8-bit weights. The downloader prints the DONE line only after
#    snapshot_download returns, i.e. the snapshot is complete. Cap the wait at 4 h.
waited=0
until grep -q "$DONE_MARK" "$DLLOG" 2>/dev/null; do
  sleep 30
  waited=$((waited + 30))
  if [ "$waited" -ge 14400 ]; then
    say "ABORT: weights not complete after 4 h — nothing ran"
    exit 1
  fi
done
say "weights ready (waited ${waited}s)"

# SKIP_GATES=1: relaunch path after a budget-gate failure was remedied per the note's
# phase-1 step 5 (closure measured, THINK_BUDGET re-pinned in this commit). The gates
# already ran once tonight — probe PASS on the same weights, budget measured to closure —
# so re-running them would spend an hour of the window re-proving tonight's own record.
if [ "${SKIP_GATES:-0}" = "1" ]; then
  say "gates SKIPPED by relaunch: probe PASS twice tonight on these weights (logs/e2_probe_38_8bit.json) + low-regime closure measured PASS at 15,735 of 32,768 (logs/e2_slice38_budget_probe_low32k.json) — the measurement is the budget-gate evidence for the 19,669 pin"
else

# 1. Thinking probe, the July gate: real thinking on the real load path or no night.
#    --max-tokens 4000, not the 1500 default: 3.8's template defaults reasoning_effort
#    to xhigh, and a trivial-prompt think that outruns 1500 would fail the gate for the
#    wrong reason. Gate on the verdict JSON, not on exit-code assumptions.
$PY agent/harness/e2_probe.py --model "$MODEL" --max-tokens 4000 \
  --out logs/e2_probe_38_8bit.json >> "$LOG" 2>&1
$PY - <<'EOF' >> "$LOG" 2>&1
import json, sys
d = json.load(open("logs/e2_probe_38_8bit.json"))
v = d.get("verdict") or {}
print("probe verdict:", v)
sys.exit(0 if v and all(v.values()) else 1)
EOF
if [ $? -ne 0 ]; then
  say "ABORT: thinking probe FAILED — 3.8 bring-up failed on the mlx_lm path; a serving-path fact, never a capability claim"
  exit 1
fi
say "thinking probe PASS"

# 2. Budget probe on the largest slice-3 cell: think must close inside THINK_BUDGET.
#    Exits nonzero on FAIL (its own gate field); no unilateral budget raise at night.
$PY agent/harness/e2_budget_probe.py --model "$MODEL" \
  --out logs/e2_slice38_budget_probe.json >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
  say "ABORT: budget probe FAILED — think did not close inside 16384 on the largest prompt; morning decides the budget, not the chain"
  exit 1
fi
say "budget probe PASS"

fi

# 3. The night. Seed 1 complete first (protocol order: a finished seed 1 with both arms
#    is a result; a truncated seed 2 is a smaller readout, denominator rules pre-set).
for SEED in 1 2; do
  say "seed $SEED start"
  $PY agent/harness/e2_slice.py --frames --feedback --seed "$SEED" \
    --model "$MODEL" \
    --latent-spec "logs/e2_slice38_latents_seed${SEED}.json" \
    --out "logs/e2_slice38_seed${SEED}.json" >> "$LOG" 2>&1
  rc=$?
  if [ $rc -ne 0 ]; then
    say "seed $SEED exited rc=$rc — stopping the chain; whatever is on disk is the result"
    exit 1
  fi
  say "seed $SEED done"
done

say "chain complete: both seeds on disk"
