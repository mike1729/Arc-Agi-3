#!/usr/bin/env bash
# S1-e breadth run, scheduled BY ACTION CLASS.
#
# Why two phases rather than one uniform concurrency:
#
#   keyboard games (no ACTION6 in the candidate set) emit actions in BATCHES — one generation commits
#   several actions — and their generations are short (median ~264 completion tokens). They tolerate
#   sharing the accelerator.
#
#   ACTION6 games reason about coordinates. Their generations are ~3.3x longer (median ~871 tokens) and
#   yield ~0.3 actions per generation instead of ~5. Sharing the accelerator pushes their per-generation
#   latency past the point where a 45-minute game budget contains enough generations to matter.
#
# Concurrency is therefore a property of the phase, and it is baked into the built config, so the two
# phases cannot overlap. Keyboard runs first: it is short and yields concluded episodes soonest.
#
# CONFOUND NOTE. Action class and concurrency now covary by construction. That is acceptable ONLY
# because concurrency is a throughput setting, not an experimental arm — no contrast in the manifest is
# defined across it. Any comparison that does span the two phases must say so explicitly.
#
# Both phases require games to reach gave_up/won. run_resumable.py retries censored games and loops
# until the set concludes, so this script is unattended-safe.

set -euo pipefail
cd "$(dirname "$0")/../.."

MODEL="${MLX_MODEL_PATH:-$HOME/models/mlx/Qwen3.6-27B-4bit}"

# Measured, logs/s2_arc_conventions.json: games with no ACTION6 at reset.
KEYBOARD="g50t-5849a774,ls20-9607627b,re86-8af5384d,tr87-cd924810,tu93-0768757b,wa30-ee6fef47"
# The other 19 public games; every one exposes ACTION6.
ACTION6="tn36-ef4dde99,lf52-271a04aa,cn04-2fe56bfb,bp35-0a0ad940,lp85-305b61c3,r11l-495a7899,\
sp80-589a99af,m0r0-492f87ba,vc33-5430563c,ar25-0c556536,ka59-38d34dbb,sc25-635fd71a,sk48-d8078629,\
dc22-fdcac232,cd82-fb555c5d,ft09-0d8bbf25,s5i5-18d95033,sb26-7fbdac44,su15-1944f8ab"

phase () {   # name, games, concurrency, chunk, state, prefix
  local name="$1" games="$2" conc="$3" chunk="$4" state="$5" prefix="$6"
  echo "=============================================================="
  echo "PHASE $name — concurrency $conc, chunk $chunk"
  echo "=============================================================="
  MLX_MODEL_PATH="$MODEL" LOCAL_CONCURRENT_JOBS="$conc" bash agent/harness/build_local.sh >/dev/null
  python3 -c "
import json; c=json.load(open('agent/work/taaf/src/ARC3-Inference/configs/inference.local-mlx.json'))
assert c['environment']['concurrent_jobs'] == $conc, 'concurrency did not take'
print(f\"  verified conc={c['environment']['concurrent_jobs']} timeout={c['analyzer']['timeout']} \"
      f\"max_output={c['analyzer']['max_output']} runtime={c['environment']['max_runtime_minutes']}min\")"
  .venv/bin/python agent/harness/run_resumable.py \
      --games "$games" --chunk "$chunk" --state "$state" --run-prefix "$prefix"
}

phase KEYBOARD "$KEYBOARD" 2 2 logs/s1e_kb_state.json  s1e-kb2
phase ACTION6  "$ACTION6"  1 1 logs/s1e_a6_state.json  s1e-a6c1

echo
echo "=== S1-e complete — concluded games per phase ==="
python3 - <<'PY'
import json, os
for label, p in [('keyboard (conc 2)', 'logs/s1e_kb_state.json'),
                 ('ACTION6  (conc 1)', 'logs/s1e_a6_state.json')]:
    if not os.path.exists(p):
        continue
    st = json.load(open(p))
    fin = st.get('finished', {})
    done = {g: v for g, v in fin.items() if v.get('completed')}
    cens = {g: v for g, v in fin.items() if not v.get('completed')}
    print(f"{label}: {len(done)} concluded, {len(cens)} censored")
    for g, v in sorted(done.items()):
        print(f"   {g:20s} {v['state']:8s} levels={v['levels_completed']} {v['actions_per_level']}")
    for g, v in sorted(cens.items()):
        print(f"   {g:20s} {v['state']:8s} CENSORED — excluded from the corpus")
PY
