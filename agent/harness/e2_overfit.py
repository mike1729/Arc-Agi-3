#!/usr/bin/env python3
"""E2 slice — re-verify dose-125 survivors against the same game's FULL store.

The slice's only improvements are all at dose 125, which invites the reading that thinner
evidence synthesizes better. It does not: a proposal passes zero-tolerance verification at
125 transitions when those 125 simply do not contain its counterexample. This asks the
cheap, decisive question — does the survivor still hold against the fuller evidence of the
same game? — with zero model calls.

The full store is a strict superset of the 125-transition prefix, so this check can only
REFUTE a survivor, never confirm one.

Run:
  .venv/bin/python agent/harness/e2_overfit.py
"""

import sys, json
sys.path.insert(0,'agent/harness')
from e2_slice import MODE, store_for, to_rules, verify, parse_json
from rs_e0 import abstract

d=json.load(open('logs/e2_slice.json'))
print("dose-125 SURVIVORS re-verified against the FULL store of the same game")
print(f"{'game':6s} {'rule':34s} {'sup@125':>8s} {'sup@full':>9s} {'contra@full':>12s} {'verdict':>10s}")
for c in d['cells']:
    if c['dose']!=125 or c['verified']==0: continue
    game=c['game']
    full=store_for(game)
    # rebuild the survivor rules from the recorded verification report
    tr=json.load(open(f"logs/e2_slice_traces/{game}_125.extract0.json"))
    payload=parse_json(tr['answer'])
    vocab={n for t in store_for(game)[:125] for n in t.guards}
    rules,_=to_rules(payload, vocab)
    kept125={r['rule'] for r in c['verification'] if r['kept']}
    survivors={k:v for k,v in rules.items() if v.rid() in kept125}
    _, report = verify(dict(survivors), full)
    for row in report:
        sup125=next(r['support_on_store'] for r in c['verification'] if r['rule']==row['rule'])
        verdict = "holds" if row['contradicted_on_store']==0 else "OVERFIT"
        print(f"{game:6s} {row['rule']:34s} {sup125:8d} {row['support_on_store']:9d} {row['contradicted_on_store']:12d} {verdict:>10s}")
