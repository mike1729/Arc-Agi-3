"""Work out what a killed run still owes, and print the command to finish it.

The reference runner has NO resume: `Benchmark.from_json` can reload a snapshot (and even the games /
solver payloads) but it is only called from `inference/tools/eval.py` for analysis — `run.py` exposes no
`--resume` and no skip-completed logic. Re-running would start the whole set over.

What saves this is that games are INDEPENDENT and run in batches of `concurrent_jobs`. A kill loses only
the in-flight batch; every finished game keeps its artifacts. So "resume" is really "re-run the games
that did not finish", into a SEPARATE run directory, and merge at analysis time.

Classification per game:
  finished    terminal state in benchmark.json (won / gave_up / cancelled / crashed)
  incomplete  has artifacts but no terminal state — was in flight at the kill
  missing     never started

Run:  .venv/bin/python agent/harness/resume_helper.py <run_dir>
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

TERMINAL = {"won", "gave_up", "cancelled", "crashed"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--expected", type=int, default=25, help="games the run was launched with")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)

    bj = run_dir / "benchmark.json"
    b = json.loads(bj.read_text()) if bj.exists() else {}
    runs = b.get("game_runs") or []

    finished, incomplete = {}, {}
    for gr in runs:
        gid = gr.get("game_id")
        st = gr.get("state")
        rec = {"state": st, "levels": gr.get("levels_completed"),
               "actions": sum(gr.get("actions_per_level") or [])}
        (finished if st in TERMINAL else incomplete)[gid] = rec

    # Games with artifacts on disk but absent from the (possibly stale) benchmark.json snapshot.
    on_disk = {Path(f).name.split("_p")[0]
               for f in glob.glob(str(run_dir / "artifacts" / "*_events.jsonl"))}
    for gid in sorted(on_disk):
        if gid not in finished and gid not in incomplete:
            incomplete[gid] = {"state": "in_flight_at_kill (not in snapshot)", "levels": None, "actions": None}

    print(f"run       : {run_dir.name}")
    print(f"snapshot  : {'closed' if b.get('end_time') else 'OPEN (killed or still running)'}")
    print(f"expected  : {args.expected} games")
    print(f"finished  : {len(finished)}")
    print(f"incomplete: {len(incomplete)}")
    print(f"not started: {max(0, args.expected - len(finished) - len(incomplete))}")

    if finished:
        print("\nfinished:")
        for gid, r in sorted(finished.items()):
            print(f"   {gid:20s} {str(r['state']):10s} levels={r['levels']} actions={r['actions']}")
    if incomplete:
        print("\nincomplete — these need re-running:")
        for gid, r in sorted(incomplete.items()):
            print(f"   {gid:20s} {r['state']}")

    todo = sorted(incomplete)
    if todo:
        print("\nto finish the set (into a SEPARATE run dir; merge at analysis time):")
        print(f"  bash agent/harness/run_local.sh --game '{','.join(todo)}' \\")
        print(f"    --run-name {run_dir.name}-resume")
        print("\nNOTE: artifacts already written for these games stay in the ORIGINAL run dir and will")
        print("be re-created in the new one. When analysing, prefer the resumed copy for these game ids")
        print("and the original for the finished ones, or the same episode is counted twice.")
    else:
        print("\nnothing outstanding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
