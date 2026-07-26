"""Per-game analysis of the Kaggle reference run — the true-reference behavioural baseline.

Erratum S1-E5 names this run as the mitigation for the model-substitution risk: it is the only data we
hold on how the ACTUAL reference model (Qwen3.6-27B FP8, RTX PRO 6000) behaves across all 25 public
games. Everything measured locally is compared against it.

Emits per-game: levels cleared, actions, action-efficiency against the human baseline, action diversity,
and the failure signature (did it stall, thrash, or run out of budget?). These are the same measures
`s1d_label.py` derives locally, so the two are directly comparable.

Run:  .venv/bin/python agent/harness/analyse_reference_run.py <kaggle_output_dir>
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import statistics
from pathlib import Path


def per_game(out_dir: Path):
    b = json.loads((out_dir / "benchmark.json").read_text())
    rows = []
    for gr in b.get("game_runs") or []:
        gid = gr.get("game_id")
        apl = gr.get("actions_per_level") or []
        bal = gr.get("base_actions_per_level") or []
        done = int(gr.get("levels_completed") or 0)
        total_a = sum(apl)

        # Efficiency on CLEARED levels only — an unfinished level has no meaningful ratio.
        ratios = [apl[i] / bal[i] for i in range(min(done, len(apl), len(bal))) if bal[i]]

        # The level it died on: first index with actions but not cleared.
        stuck_i = done if done < len(apl) else None
        stuck_actions = apl[stuck_i] if stuck_i is not None and stuck_i < len(apl) else 0
        stuck_baseline = bal[stuck_i] if stuck_i is not None and stuck_i < len(bal) else None

        # Action diversity from the event stream.
        ev = glob.glob(str(out_dir / "artifacts" / f"{gid}_p*_events.jsonl"))
        acts, distinct, top_share = 0, None, None
        if ev:
            evs = [json.loads(l) for l in open(ev[0])]
            a = [r for r in evs if r.get("type") == "action"]
            acts = len(a)
            if a:
                c = collections.Counter(str(r.get("action_display")) for r in a)
                distinct = len(c)
                top_share = round(c.most_common(1)[0][1] / len(a), 3)

        rows.append({
            "game": gid, "levels_cleared": done, "levels_total": len(bal),
            "actions_total": total_a, "actions_events": acts,
            "score": round(gr.get("final_score") or 0, 2),
            "state": gr.get("state"),
            "mean_efficiency_cleared": round(statistics.fmean(ratios), 2) if ratios else None,
            "stuck_level": (stuck_i + 1) if stuck_i is not None else None,
            "stuck_actions": stuck_actions,
            "stuck_baseline": stuck_baseline,
            "stuck_ratio": (round(stuck_actions / stuck_baseline, 1)
                            if stuck_baseline else None),
            "distinct_actions": distinct, "top_action_share": top_share,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--out", default="logs/kaggle-reference/per_game_analysis.json")
    args = ap.parse_args()
    rows = per_game(Path(args.out_dir))
    rows.sort(key=lambda r: (-r["levels_cleared"], -r["score"]))

    print(f"{'game':22s} {'lvl':>5} {'act':>5} {'score':>6} {'eff':>5} {'stuck@':>7} {'ratio':>7} {'dist':>5} {'top%':>5}")
    print("-" * 78)
    for r in rows:
        print(f"{r['game']:22s} {r['levels_cleared']:>2}/{r['levels_total']:<2} {r['actions_total']:>5} "
              f"{r['score']:>6} {str(r['mean_efficiency_cleared'] or '-'):>5} "
              f"{str(r['stuck_level'] or '-'):>7} {str(r['stuck_ratio'] or '-'):>7} "
              f"{str(r['distinct_actions'] or '-'):>5} {str(r['top_action_share'] or '-'):>5}")

    cleared = [r for r in rows if r["levels_cleared"] > 0]
    zero = [r for r in rows if r["levels_cleared"] == 0]
    effs = [r["mean_efficiency_cleared"] for r in rows if r["mean_efficiency_cleared"]]
    stuck = [r["stuck_ratio"] for r in rows if r["stuck_ratio"]]
    print(f"\ngames clearing >=1 level : {len(cleared)}/{len(rows)}")
    print(f"games clearing 0         : {len(zero)}  ({', '.join(r['game'].split('-')[0] for r in zero)})")
    if effs:
        print(f"efficiency on cleared levels: median {statistics.median(effs):.2f}x human baseline")
    if stuck:
        print(f"the level it got stuck on  : median {statistics.median(stuck):.1f}x human baseline spent "
              f"without clearing")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(rows, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
