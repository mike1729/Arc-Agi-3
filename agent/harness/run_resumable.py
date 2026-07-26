"""Resumable supervisor for long S1-e runs.

The reference runner has no resume: kill it and the whole set restarts. For a 5+ hour breadth run that
is the difference between losing 20 minutes and losing everything. Games are INDEPENDENT, so this
supervisor drives them in chunks, records what finished, and on restart runs only what is outstanding.

Design notes, because the obvious alternatives are wrong:

  * Each chunk gets its OWN run directory. Reusing one directory via --experiment-dir would let each
    chunk's benchmark.json overwrite the previous one, silently discarding earlier games.
  * Completion is recorded from benchmark.json's terminal states, not from "the process exited".
    A chunk can exit having finished only some of its games.
  * The state file is the resume contract. It is written after every chunk, so a kill loses at most
    the chunk in flight.

Resume is simply re-running the same command: finished games are skipped.

Run:
  .venv/bin/python agent/harness/run_resumable.py --state logs/s1e_state.json --chunk 4 \\
      [--games a,b,c | --all-public] [--run-prefix s1e-dense]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TERMINAL = {"won", "gave_up", "cancelled", "crashed"}

# The 25 public games, from the bundle's own DUCK_HARNESS_PUBLIC_GAME_IDS.
PUBLIC = [
    "tn36-ef4dde99", "lf52-271a04aa", "cn04-2fe56bfb", "bp35-0a0ad940", "wa30-ee6fef47",
    "lp85-305b61c3", "r11l-495a7899", "tu93-0768757b", "sp80-589a99af", "m0r0-492f87ba",
    "vc33-5430563c", "ar25-0c556536", "ka59-38d34dbb", "sc25-635fd71a", "sk48-d8078629",
    "dc22-fdcac232", "cd82-fb555c5d", "ft09-0d8bbf25", "g50t-5849a774", "ls20-9607627b",
    "re86-8af5384d", "s5i5-18d95033", "sb26-7fbdac44", "su15-1944f8ab", "tr87-cd924810",
]


def load_state(p: Path) -> dict:
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"finished": {}, "chunks": [], "started_at": datetime.now(timezone.utc).isoformat()}


def save_state(p: Path, st: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2) + "\n")
    tmp.replace(p)          # atomic: a kill mid-write must not corrupt the resume contract


def harvest(run_dir: Path) -> dict:
    """Terminal game states from a chunk's benchmark.json."""
    bj = run_dir / "benchmark.json"
    if not bj.exists():
        return {}
    try:
        b = json.loads(bj.read_text())
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for gr in b.get("game_runs") or []:
        if gr.get("state") in TERMINAL:
            out[gr.get("game_id")] = {
                "state": gr.get("state"),
                "levels_completed": gr.get("levels_completed"),
                "actions_per_level": gr.get("actions_per_level"),
                "run_dir": run_dir.name,
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="logs/s1e_state.json")
    ap.add_argument("--chunk", type=int, default=4, help="games per chunk; match concurrent_jobs")
    ap.add_argument("--games", default="")
    ap.add_argument("--all-public", action="store_true")
    ap.add_argument("--run-prefix", default="s1e-dense")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    games = ([g.strip() for g in args.games.split(",") if g.strip()] if args.games
             else PUBLIC if args.all_public else [])
    if not games:
        print("give --games or --all-public")
        return 2

    state_path = REPO / args.state
    st = load_state(state_path)
    todo = [g for g in games if g not in st["finished"]]

    print(f"total {len(games)} games | finished {len(st['finished'])} | outstanding {len(todo)}")
    if not todo:
        print("nothing to do — the set is complete.")
        return 0
    if args.dry_run:
        print("outstanding:", ", ".join(todo))
        return 0

    chunks = [todo[i:i + args.chunk] for i in range(0, len(todo), args.chunk)]
    for i, chunk in enumerate(chunks, 1):
        name = f"{args.run_prefix}-c{len(st['chunks']) + 1:02d}"
        print(f"\n=== chunk {i}/{len(chunks)}: {', '.join(chunk)}  -> run-name {name}", flush=True)
        t0 = time.monotonic()
        cmd = ["bash", str(REPO / "agent/harness/run_local.sh"),
               "--game", ",".join(chunk), "--run-name", name]
        log = REPO / f"logs/{name}.log"
        with open(log, "w") as fh:
            rc = subprocess.call(cmd, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT)
        dt = time.monotonic() - t0

        run_dirs = sorted((REPO / "logs/runs").glob(f"*_{name}"))
        got = harvest(run_dirs[-1]) if run_dirs else {}
        st["finished"].update(got)
        st["chunks"].append({"name": name, "games": chunk, "returncode": rc,
                             "elapsed_s": round(dt, 1), "harvested": sorted(got),
                             "at": datetime.now(timezone.utc).isoformat()})
        save_state(state_path, st)

        print(f"    rc={rc} elapsed={dt/60:.1f}m harvested={len(got)}/{len(chunk)} "
              f"| total finished {len(st['finished'])}/{len(games)}", flush=True)
        missed = [g for g in chunk if g not in got]
        if missed:
            print(f"    NOT harvested (will be retried on resume): {', '.join(missed)}", flush=True)

    print(f"\ndone. finished {len(st['finished'])}/{len(games)}. state: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
