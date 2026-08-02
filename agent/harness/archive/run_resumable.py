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
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# S1-E9. The recorded state does NOT distinguish "the agent concluded" from "the budget expired":
# 0 of 25 reference games finished early, yet all recorded `gave_up`, while our identically
# budget-terminated games record `cancelled`. The difference is generation length — a long generation is
# in flight when the deadline lands, gets killed, and that path sets stop_event.
#
# So conclusion is decided by WALL-CLOCK, not by the label. A game that ran its full uniform budget was
# terminated by a pre-registered experimental condition. A game that stopped EARLY was killed or crashed.
# Both record `cancelled`; only the wall-clock separates them.
AGENT_FINISHED = {"won", "gave_up"}
TERMINAL = AGENT_FINISHED | {"cancelled", "crashed"}
BUDGET_TOLERANCE = 0.98  # ran >= 98% of the budget => budget-terminated, not killed

# Retrying a budget-terminated game is pointless: it terminates identically every time. Retries exist
# for crashes and early stops only. The earlier value of 3, applied to budget termination, would have
# turned a 16.5 h breadth run into 49.5 h without producing anything new.
MAX_ATTEMPTS = 2

# A chunk cannot legitimately outlive the harness's own per-game budget by much: games in a chunk run
# concurrently, so a chunk is one budget plus start-up and teardown. Anything far past that is wedged
# (an unresponsive server holding an open connection, a hung child), not slow. Without this the
# supervisor blocks forever on subprocess.call and an unattended run dies silently.
CHUNK_TIMEOUT_FACTOR = 1.5
CHUNK_TIMEOUT_SLACK_S = 900.0


def _chunk_timeout_s() -> float:
    """Derived from the built config, so it tracks the budget instead of being a second hardcoded copy."""
    cfg = REPO / "agent/work/taaf/src/ARC3-Inference/configs/inference.local-mlx.json"
    minutes = 45.0
    try:
        minutes = float(json.loads(cfg.read_text())["environment"]["max_runtime_minutes"])
    except Exception:  # noqa: BLE001
        pass
    return minutes * 60.0 * CHUNK_TIMEOUT_FACTOR + CHUNK_TIMEOUT_SLACK_S


def _run_chunk(cmd, log_path: Path) -> tuple[int, bool]:
    """Run a chunk, killing it if it wedges. Returns (returncode, timed_out).

    start_new_session puts the harness in its own process group so the whole tree can be signalled;
    killing only the direct child would leave the inference subprocesses holding the GPU.
    """
    timeout = _chunk_timeout_s()
    with open(log_path, "w") as fh:
        proc = subprocess.Popen(cmd, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            return proc.wait(timeout=timeout), False
        except subprocess.TimeoutExpired:
            print(f"    WEDGED: no exit after {timeout/60:.0f}m — killing the process group", flush=True)
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(os.getpgid(proc.pid), sig)
                except ProcessLookupError:
                    break
                try:
                    proc.wait(timeout=30)
                    break
                except subprocess.TimeoutExpired:
                    continue
            return -1, True

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


def _budget_seconds(run_dir: Path) -> float | None:
    """The uniform per-game budget this run was launched with, from its own run_config.json."""
    rc = run_dir / "run_config.json"
    if not rc.exists():
        return None
    try:
        m = json.loads(rc.read_text()).get("max_runtime_minutes_per_game")
        return float(m) * 60.0 if m else None
    except Exception:  # noqa: BLE001
        return None


def harvest(run_dir: Path) -> dict:
    """Per-game outcome, with conclusion decided by wall-clock rather than by the recorded label."""
    bj = run_dir / "benchmark.json"
    if not bj.exists():
        return {}
    try:
        b = json.loads(bj.read_text())
    except Exception:  # noqa: BLE001
        return {}
    budget = _budget_seconds(run_dir)
    out = {}
    for gr in b.get("game_runs") or []:
        if gr.get("state") in TERMINAL:
            wall = gr.get("final_wallclock_seconds")
            ran_full_budget = bool(
                budget and wall is not None and wall >= BUDGET_TOLERANCE * budget)
            out[gr.get("game_id")] = {
                "state": gr.get("state"),
                # S1-E9: concluded = the agent finished, OR the uniform budget expired.
                "completed": (gr.get("state") in AGENT_FINISHED) or ran_full_budget,
                "budget_terminated": ran_full_budget,
                "censored_at_seconds": budget if ran_full_budget else None,
                "final_wallclock_seconds": wall,
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
    st.setdefault("attempts", {})

    # Outstanding = not yet CONCLUDED, and still within the retry budget. A game recorded as
    # `cancelled` is censored data, so it goes back in the queue rather than counting as done.
    def outstanding(g):
        rec = st["finished"].get(g)
        if rec and rec.get("completed"):
            return False
        return st["attempts"].get(g, 0) < MAX_ATTEMPTS

    todo = [g for g in games if outstanding(g)]
    done = [g for g in games if (st["finished"].get(g) or {}).get("completed")]
    exhausted = [g for g in games if not outstanding(g) and g not in done]

    print(f"total {len(games)} games | concluded {len(done)} | outstanding {len(todo)}"
          + (f" | retry-exhausted {len(exhausted)}: {', '.join(exhausted)}" if exhausted else ""))
    if not todo:
        print("nothing to do — the set is complete.")
        return 0
    if args.dry_run:
        print("outstanding:", ", ".join(todo))
        return 0


    # Outer loop: a censored game returns to the queue, so an unattended overnight run retries it
    # itself instead of waiting for someone to re-invoke the command.
    while True:
        todo = [g for g in games if outstanding(g)]
        if not todo:
            break
        chunks = [todo[i:i + args.chunk] for i in range(0, len(todo), args.chunk)]
        for i, chunk in enumerate(chunks, 1):
            name = f"{args.run_prefix}-c{len(st['chunks']) + 1:02d}"
            print(f"\n=== chunk {i}/{len(chunks)}: {', '.join(chunk)}  -> run-name {name}", flush=True)
            t0 = time.monotonic()
            cmd = ["bash", str(REPO / "agent/harness/run_local.sh"),
                   "--game", ",".join(chunk), "--run-name", name]
            log = REPO / f"logs/{name}.log"
            rc, timed_out = _run_chunk(cmd, log)
            dt = time.monotonic() - t0

            run_dirs = sorted((REPO / "logs/runs").glob(f"*_{name}"))
            got = harvest(run_dirs[-1]) if run_dirs else {}
            st["finished"].update(got)
            for g in chunk:
                st["attempts"][g] = st["attempts"].get(g, 0) + 1
            st["chunks"].append({"name": name, "games": chunk, "returncode": rc,
                                 "timed_out": timed_out,
                                 "elapsed_s": round(dt, 1), "harvested": sorted(got),
                                 "concluded": sorted(g for g, v in got.items() if v["completed"]),
                                 "at": datetime.now(timezone.utc).isoformat()})
            save_state(state_path, st)

            concluded = [g for g, v in got.items() if v["completed"]]
            total = sum(1 for g in games if (st["finished"].get(g) or {}).get("completed"))
            print(f"    rc={rc} elapsed={dt/60:.1f}m concluded={len(concluded)}/{len(chunk)} "
                  f"| total {total}/{len(games)}", flush=True)
            censored = [f"{g}({got[g]['state']})" for g in chunk
                        if g in got and not got[g]["completed"]]
            if censored:
                print(f"    CENSORED, will retry: {', '.join(censored)}", flush=True)
            missed = [g for g in chunk if g not in got]
            if missed:
                print(f"    NOT harvested, will retry: {', '.join(missed)}", flush=True)

    total_done = sum(1 for g in games if (st["finished"].get(g) or {}).get("completed"))
    never = [g for g in games if not (st["finished"].get(g) or {}).get("completed")]
    print(f"\ndone. CONCLUDED {total_done}/{len(games)}. state: {state_path}")
    if never:
        print(f"never concluded after {MAX_ATTEMPTS} attempts: {', '.join(never)}")
        print("Their episodes are censored and must NOT enter the labelling corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
