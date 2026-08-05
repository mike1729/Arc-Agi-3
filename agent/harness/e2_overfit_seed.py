#!/usr/bin/env python3
"""E2 slice 1.1 — seed-aware overfit re-verification.

Identical logic to e2_overfit.py; only the input paths are parameterised by seed so the
variance/display-repair arm can be read the same way slice 1 was. Zero model calls.

The full store is a strict superset of the 125-transition prefix, so this check can only
REFUTE a dose-125 survivor, never confirm one. Dose-full survivors were already verified
against the full store by the run itself and are reported here for the honest total.

Run:
  .venv/bin/python agent/harness/e2_overfit_seed.py --seed 1
"""

import sys, json, argparse
sys.path.insert(0, 'agent/harness')
from e2_slice import MODE, store_for, to_rules, verify, parse_json

ap = argparse.ArgumentParser()
ap.add_argument("--seed", type=int, required=True)
args = ap.parse_args()
S = args.seed

d = json.load(open(f'logs/e2_slice_seed{S}.json'))
print(f"=== seed {S}: dose-125 survivors re-verified against the FULL store ===")
print(f"{'game':6s} {'rule':34s} {'sup@125':>8s} {'sup@full':>9s} {'contra@full':>12s} {'verdict':>10s}")

held = refuted = 0
for c in d['cells']:
    if c['dose'] != 125 or c['verified'] == 0:
        continue
    game = c['game']
    full = store_for(game)
    tr = json.load(open(f"logs/e2_slice_traces/{game}_125_s{S}.extract0.json"))
    payload = parse_json(tr['answer'])
    vocab = {n for t in store_for(game)[:125] for n in t.guards}
    rules, _ = to_rules(payload, vocab)
    kept125 = {r['rule'] for r in c['verification'] if r['kept']}
    survivors = {k: v for k, v in rules.items() if v.rid() in kept125}
    _, report = verify(dict(survivors), full)
    for row in report:
        sup125 = next(r['support_on_store'] for r in c['verification'] if r['rule'] == row['rule'])
        overfit = row['contradicted_on_store'] > 0
        held += (not overfit); refuted += overfit
        verdict = "OVERFIT" if overfit else "holds"
        print(f"{game:6s} {row['rule']:34s} {sup125:8d} {row['support_on_store']:9d} "
              f"{row['contradicted_on_store']:12d} {verdict:>10s}")

full_survivors = sum(c['verified'] for c in d['cells'] if c['dose'] != 125)
print(f"\ndose-125 survivors: {held} hold / {refuted} refuted by fuller evidence")
print(f"dose-full survivors (already full-evidence): {full_survivors}")
print(f"HONEST survives-full-evidence count, seed {S}: {held + full_survivors}"
      f"  (of {sum(c['proposed'] for c in d['cells'])} proposed)")
