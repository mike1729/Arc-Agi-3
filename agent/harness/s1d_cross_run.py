"""Cross-run stability of the failure-category ranking (task #8).

Answers one question: does the ranking that sets the build order survive being re-measured on further
runs of the SAME configuration? It emits three views, because they disagree and the disagreement is the
finding:

  primary_share per run   the ranking itself, stratified by band. This is what the build order reads.
  episode_share per run   whether a category is DETECTED at a stable rate. If primary_share moves while
                          episode_share holds, the drift is in the primary-assignment rule rather than
                          in what the rater sees — a distinction no single table shows.
  paired triples          same (game, level) across all runs. The only view immune to the runs having
                          stalled on different levels, which they do in 9 of 25 games.

DRIFT CHECK. `latency_or_budget` is emitted separately against the count of budget-terminated episodes,
because every admitted episode is budget-terminated by construction (S1-E9). Its episode_share is
therefore a CONSTANT of the corpus, and any movement in it measures the rater, not the runs. That makes
it a free control for drift, and it is printed whether or not it looks interesting.

Run:
  .venv/bin/python agent/harness/s1d_cross_run.py logs/s1d_corpus_pooled.json --out logs/s1d_cross_run.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def band(e):
    return "L2+" if (e.get("level") or 1) > 1 else "L1"


def _share(eps, key):
    n = len(eps)
    if not n:
        return {}
    c = collections.Counter()
    if key == "primary":
        c.update(e["primary_label"] for e in eps)
    else:
        for e in eps:
            c.update({l["category"] for l in e["labels"]})
    return {k: round(v / n, 4) for k, v in c.most_common()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("--out", default="")
    a = ap.parse_args()

    eps = [e for e in json.loads(Path(a.corpus).read_text())["episodes"] if e.get("labels")]
    runs = sorted({e["source_run"] for e in eps})

    res = {"runs": runs, "n_labelled": len(eps), "primary_share": {}, "episode_share": {}}
    for scope in ["pooled", "L1", "L2+"]:
        res["primary_share"][scope] = {
            r: _share([e for e in eps
                       if e["source_run"] == r and (scope == "pooled" or band(e) == scope)], "primary")
            for r in runs}
    res["episode_share"]["pooled"] = {
        r: _share([e for e in eps if e["source_run"] == r], "episode") for r in runs}

    # Drift control — see module docstring.
    res["drift_control"] = {
        "all_episodes_budget_terminated": all(e.get("budget_terminated") for e in eps),
        "latency_or_budget_episode_share": {
            r: res["episode_share"]["pooled"][r].get("latency_or_budget", 0.0) for r in runs},
        "note": ("every admitted episode is budget-terminated (S1-E9), so this share is a constant of "
                 "the corpus. Movement in it measures the RATER, not the runs."),
    }

    by_gl = collections.defaultdict(dict)
    for e in eps:
        by_gl[(e["game"], e["level"])][e["source_run"]] = e["primary_label"]
    trip = {k: v for k, v in by_gl.items() if len(v) == len(runs)}
    agree = sum(1 for v in trip.values() if len(set(v.values())) == 1)
    split = sum(1 for v in trip.values() if len(set(v.values())) == len(runs))
    res["paired"] = {
        "n_complete_triples": len(trip),
        "n_game_levels_total": len(by_gl),
        "all_agree": agree,
        "all_different": split,
        "agreement_rate": round(agree / len(trip), 4) if trip else None,
        "incomplete_are_not_missing_at_random": (
            "the (game, level) pairs absent from some runs are exactly the games whose outcome varied, "
            "so dropping them biases the comparison toward the stable games"),
        "triples": {f"{g}::L{l}": v for (g, l), v in sorted(trip.items())},
    }

    print(f"{len(eps)} labelled episodes across {runs}\n")
    for scope in ["L2+", "pooled"]:
        print(f"=== primary_share — {scope} ===")
        cats = sorted({k for r in runs for k in res['primary_share'][scope][r]},
                      key=lambda k: -sum(res['primary_share'][scope][r].get(k, 0) for r in runs))
        print(f"{'category':36s}" + "".join(f"{r.replace('kaggle_',''):>9s}" for r in runs))
        for k in cats:
            print(f"{k:36s}" + "".join(
                f"{res['primary_share'][scope][r].get(k,0)*100:>8.0f}%" for r in runs))
        print()
    d = res["drift_control"]
    print(f"DRIFT CONTROL — all budget-terminated: {d['all_episodes_budget_terminated']}; "
          f"latency_or_budget share per run: "
          + ", ".join(f"{r.replace('kaggle_','')}={v*100:.0f}%"
                      for r, v in d["latency_or_budget_episode_share"].items()))
    p = res["paired"]
    print(f"PAIRED — {p['all_agree']}/{p['n_complete_triples']} triples agree "
          f"({p['agreement_rate']:.0%}); {p['all_different']} split {len(runs)} ways; "
          f"{p['n_game_levels_total'] - p['n_complete_triples']} (game,level) pairs incomplete")

    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2) + "\n")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
