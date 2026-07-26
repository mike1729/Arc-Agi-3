"""One-time repair: undo the `game_runs[0]` mis-attribution in already-extracted episode files.

WHY THIS EXISTS
---------------
`s1d_label.py` read `benchmark.json -> game_runs[0]` and applied that single game's identity, human
baseline and terminal state to EVERY episode in the directory. On a single-game run that is correct
by coincidence. On a multi-game run it is wrong for all but one game, and it is silent.

The Kaggle reference extraction is the severe case: 25 episodes from 25 different games, every one
stamped `game=sk48-d8078629` and scored against sk48's `base_actions_per_level`. `bp35` level 2 was
recorded against a baseline of 177 when its real level-2 baseline is 48.

That file cannot be regenerated — the run directory it was extracted from (`kout`) no longer exists,
and `logs/kaggle-reference/` holds no `artifacts/`. It CAN be repaired exactly, because every field
needed is still held:

  game            recovered from `episode_id`, which is `<run>::<game>_p<N>::L<level>`
  human_baseline  `logs/kaggle-reference/benchmark.json -> game_runs[<game>].base_actions_per_level[level-1]`
  ratio           recomputed from the episode's own `actions_taken`

Nothing is invented: `actions_taken`, `level` and the evidence packet come from the event stream and
are untouched. Only the three fields the bug corrupted are rewritten.

Run:  .venv/bin/python agent/harness/s1d_repair_gamerun0.py <episodes.json> <benchmark.json>
      add --write to apply; default is a dry run.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

EPISODE_ID = re.compile(r"^(?P<run>[^:]*)::(?P<game>.+?)_p\d+::L(?P<level>\d+)$")


def repair(episodes_path: Path, benchmark_path: Path, write: bool) -> int:
    data = json.loads(episodes_path.read_text())
    bench = json.loads(benchmark_path.read_text())
    runs = {gr.get("game_id"): gr for gr in (bench.get("game_runs") or []) if gr.get("game_id")}

    changed, unmatched, rows = 0, [], []
    for ep in data.get("episodes") or []:
        m = EPISODE_ID.match(ep.get("episode_id", ""))
        if not m:
            unmatched.append(ep.get("episode_id"))
            continue
        game, level = m.group("game"), int(m.group("level"))
        gr = runs.get(game)
        if gr is None:
            unmatched.append(ep.get("episode_id"))
            continue

        bal = gr.get("base_actions_per_level") or []
        base = bal[level - 1] if 0 <= level - 1 < len(bal) else None
        acts = ep.get("actions_taken")
        ratio = round(acts / base, 2) if (base and acts is not None) else None

        before = (ep.get("game"), ep.get("human_baseline"), ep.get("action_ratio_vs_baseline"))
        after = (game, base, ratio)
        if before != after:
            changed += 1
            rows.append((game, level, acts, before[1], base, before[2], ratio))
        ep["game"], ep["human_baseline"], ep["action_ratio_vs_baseline"] = after
        ep["terminal_state"] = gr.get("state")

    # The run-level fields carried the same mis-attribution.
    data.pop("game", None)
    data.pop("state", None)
    data.pop("levels_completed", None)
    data.pop("actions_per_level", None)
    data["games"] = {g: {"state": r.get("state"), "levels_completed": r.get("levels_completed"),
                         "actions_per_level": r.get("actions_per_level")}
                     for g, r in runs.items()}
    data["n_games"] = len(data["games"])
    data["repair"] = {
        "applied": "2026-07-26",
        "defect": "s1d_label.py read game_runs[0] and applied it to every episode in the directory",
        "fields_rewritten": ["game", "human_baseline", "action_ratio_vs_baseline", "terminal_state"],
        "fields_untouched": ["actions_taken", "level", "analysis_turns", "evidence"],
        "recovered_from": "episode_id (game, level) joined to benchmark.json base_actions_per_level",
    }

    print(f"{'game':22s} {'lvl':>3} {'acts':>5} {'base OLD':>9} {'base NEW':>9} "
          f"{'ratio OLD':>10} {'ratio NEW':>10}")
    for g, lv, a, bo, bn, ro, rn in sorted(rows):
        print(f"{g:22s} {lv:>3} {str(a):>5} {str(bo):>9} {str(bn):>9} {str(ro):>10} {str(rn):>10}")
    print(f"\n{changed} of {len(data.get('episodes') or [])} episodes corrected")
    if unmatched:
        print(f"UNMATCHED (left untouched): {unmatched}")

    ratios = [e["action_ratio_vs_baseline"] for e in data["episodes"]
              if e.get("action_ratio_vs_baseline") is not None]
    if ratios:
        import statistics
        print(f"median action_ratio_vs_baseline after repair: {statistics.median(ratios):.2f}x "
              f"(n={len(ratios)})")

    if write:
        episodes_path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"\nwrote {episodes_path}")
    else:
        print("\nDRY RUN — pass --write to apply")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes")
    ap.add_argument("benchmark")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    return repair(Path(args.episodes), Path(args.benchmark), args.write)


if __name__ == "__main__":
    raise SystemExit(main())
