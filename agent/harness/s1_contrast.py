"""S1 clear-vs-stall contrast — mechanical derivation of the per-run outcome split.

Task note: notes/s1-clear-vs-stall.md. Zero model calls; reads logs/runs/*/artifacts/
*_events.jsonl plus run_config.json / deploy_meta.json only.

Two corpora exist and are NOT the same lineage (see the note's results section):
  ref   — logs/kaggle_v{2,3,4}: duck-harness on Kaggle, vLLM FP8, thinking on.
          This is the reference stack the standing S1 goal_unknown result is keyed to
          (logs/s1d_corpus_pooled.json episode ids are `kaggle_v{2,3,4}::game::L{n}`).
  local — logs/runs/: local MLX Qwen3.6-27B 4bit/8bit replication passes.

Usage:
    python3 agent/harness/s1_contrast.py split [ref|local|both]
    python3 agent/harness/s1_contrast.py clears [ref|local]
    python3 agent/harness/s1_contrast.py window CORPUS ARM GAME LO HI
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "logs" / "runs"
REF_RUNS = [REPO / "logs" / f"kaggle_v{n}" for n in (2, 3, 4)]

DROP = ("board", "board_ascii", "transcript")


def load_events(path: Path) -> list[dict]:
    with path.open() as fh:
        return [json.loads(line) for line in fh if line.strip()]


def thin(ev: dict) -> dict:
    return {k: v for k, v in ev.items() if k not in DROP}


def iter_runs(corpus: str = "local"):
    """Yield (run_dir, arm, cfg, meta) for every run dir in the chosen corpus."""
    dirs = REF_RUNS if corpus == "ref" else sorted(d for d in RUNS.iterdir() if d.is_dir())
    for run in dirs:
        cfg_p = run / "run_config.json"
        cfg = json.loads(cfg_p.read_text()) if cfg_p.exists() else {}
        meta_p = run / "deploy_meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        arm = run.name if corpus == "ref" else (
            meta.get("benchmark_label") or run.name.split("_", 2)[-1])
        yield run, arm, cfg, meta


def game_key(artifact: Path) -> tuple[str, str]:
    """('tn36-ef4dde99_p0' -> ('tn36', 'p0'))."""
    stem = artifact.name.replace("_events.jsonl", "")
    game, _, passid = stem.rpartition("_")
    return game.split("-")[0], passid


def summarize(events: list[dict]) -> dict:
    actions = [e for e in events if e.get("type") == "action"]
    clears = [e for e in events if e.get("level_completed")]
    max_score = max((e.get("score") or 0) for e in events) if events else 0
    max_level = max((e.get("level") or 0) for e in events) if events else 0
    return {
        "events": len(events),
        "actions": len(actions),
        "analysis_steps": max((e.get("analysis_step") or 0) for e in events) if events else 0,
        "max_score": max_score,
        "max_level": max_level,
        "clears": [
            {"action_num": c.get("action_num"), "level_before": (c.get("level") or 0) - 1,
             "score_after": c.get("score"), "reward": c.get("reward")}
            for c in clears
        ],
        "final_state": events[-1].get("state") if events else None,
        "run_status": events[-1].get("run_status") if events else None,
    }


def collect(corpus: str = "local") -> list[dict]:
    rows = []
    for run, arm, cfg, meta in iter_runs(corpus):
        art = run / "artifacts"
        for path in sorted(art.glob("*_events.jsonl")):
            game, passid = game_key(path)
            ev = load_events(path)
            row = {
                "run": run.name,
                "arm": arm,
                "model": cfg.get("model"),
                "runner": cfg.get("runner"),
                "game": game,
                "pass": passid,
                "host": meta.get("host"),
                "max_runtime_min": cfg.get("max_runtime_minutes_per_game"),
            }
            row.update(summarize(ev))
            rows.append(row)
    return rows


def cmd_split(corpus: str = "local") -> None:
    rows = collect(corpus)
    print(f"# corpus={corpus}  runs: {len({r['run'] for r in rows})}  "
          f"game-passes: {len(rows)}  games: {len({r['game'] for r in rows})}")

    print("\n## per game-pass")
    hdr = ("game", "arm", "pass", "acts", "evts", "score", "lvl", "clears@action")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for r in sorted(rows, key=lambda r: (-r["max_score"], r["game"], r["run"])):
        at = ",".join(str(c["action_num"]) for c in r["clears"]) or "-"
        print(f"| {r['game']} | {r['arm']} | {r['pass']} | {r['actions']} | {r['events']} | "
              f"{r['max_score']} | {r['max_level']} | {at} |")

    print("\n## per game (pooled across arms — arms listed, never silently merged)")
    games: dict[str, list[dict]] = {}
    for r in rows:
        games.setdefault(r["game"], []).append(r)
    hdr = ("game", "passes", "arms", "best score", "max actions", "cleared?")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for g, rs in sorted(games.items(), key=lambda kv: (-max(r["max_score"] for r in kv[1]), kv[0])):
        best = max(r["max_score"] for r in rs)
        arms = ",".join(sorted({r["arm"] for r in rs}))
        print(f"| {g} | {len(rs)} | {arms} | {best} | {max(r['actions'] for r in rs)} | "
              f"{'YES' if best else 'no'} |")

    print("\n## model / lineage check")
    for model in sorted({str(r["model"]) for r in rows}):
        sub = [r for r in rows if str(r["model"]) == model]
        print(f"- `{model}` — {len(sub)} game-passes, arms: "
              f"{','.join(sorted({r['arm'] for r in sub}))}")


def cmd_clears(corpus: str = "local") -> None:
    for run, arm, cfg, _ in iter_runs(corpus):
        for path in sorted((run / "artifacts").glob("*_events.jsonl")):
            ev = load_events(path)
            if not any(e.get("level_completed") for e in ev):
                continue
            game, passid = game_key(path)
            print(f"\n=== {game} {passid} arm={arm} run={run.name}")
            for i, e in enumerate(ev):
                if e.get("type") == "action":
                    mark = "  <-- CLEAR" if e.get("level_completed") else ""
                    print(f"  [{i:3d}] a{e['action_num']:<3} step{e.get('analysis_step')} "
                          f"{e.get('action_display')}{mark}")


SECTION = ("[SYSTEM PROMPT]", "[USER PROMPT]", "[MODEL RESPONSE META]", "[THINKING]",
           "[ASSISTANT]", "[ANALYZER STATUS]", "[TOOL RESULT]", "[TOOL CALL]")


def model_text(transcript: str, keep=("[THINKING]", "[ASSISTANT]")) -> str:
    """Strip the transcript down to the model's own reasoning / assistant turns."""
    import re
    marks = [(m.start(), m.group(0)) for m in
             re.finditer(r"^\[[A-Z][A-Z ]+\]", transcript, re.M)]
    out = []
    for i, (pos, name) in enumerate(marks):
        if name not in keep:
            continue
        end = marks[i + 1][0] if i + 1 < len(marks) else len(transcript)
        out.append(f"{name}\n{transcript[pos + len(name):end].strip()}")
    return "\n".join(out)


def cmd_reason(corpus: str, arm: str, game: str, lo: int, hi: int, cap: int = 100000) -> None:
    """Print only the model's reasoning for events[lo:hi] of one game-pass."""
    for run, run_arm, _, _ in iter_runs(corpus):
        if run_arm != arm:
            continue
        for path in sorted((run / "artifacts").glob("*_events.jsonl")):
            if game_key(path)[0] != game:
                continue
            ev = load_events(path)
            print(f"=== {game} corpus={corpus} arm={arm} events[{lo}:{min(hi,len(ev))}] "
                  f"of {len(ev)}")
            for i in range(max(0, lo), min(hi, len(ev))):
                e = ev[i]
                if e.get("type") == "action":
                    mark = "   <<<<< LEVEL COMPLETED" if e.get("level_completed") else ""
                    print(f"\n##### [{i}] ACTION {e['action_num']} "
                          f"{e.get('action_display')} changed={e.get('board_changed')}{mark}")
                elif e.get("transcript"):
                    print(f"\n##### [{i}] {e.get('title')} (after action "
                          f"{e.get('action_num')})")
                    print(model_text(e["transcript"])[:cap])
            return
    raise SystemExit(f"no match for corpus={corpus} arm={arm} game={game}")


def _strip_tools(text: str) -> str:
    return text.split("[TOOL CALL")[0].strip()


def cmd_clearctx(corpus: str, cap: int = 1800, only_first: bool = True) -> None:
    """For every clearing action in a corpus, print the three diagnostic turns.

    Event ordering in these logs: the action event is emitted BEFORE the transcript
    event of the turn that issued it. So for a clear at index i:
      PRIOR   — last transcript before i (the goal state going in)
      ISSUER  — first transcript after i (the turn whose tool call fired the clear)
      REACT   — next transcript after that (how the model read the completion)

    `cap` truncates the [THINKING] block ONLY. The [ASSISTANT] block is always printed
    in full: it carries the turn's explicit World/Goal/Plan summary, and truncating it
    misreads deliberate clears as accidental ones. Five of 42 ref clears were
    misclassified that way on 2026-08-05 before this was fixed — see the note's
    results §1 correction.
    """
    for run, arm, _, _ in iter_runs(corpus):
        for path in sorted((run / "artifacts").glob("*_events.jsonl")):
            ev = load_events(path)
            game, _ = game_key(path)
            idxs = [i for i, e in enumerate(ev) if e.get("level_completed")]
            if only_first:
                idxs = idxs[:1]
            for ci in idxs:
                lvl = (ev[ci].get("level") or 2) - 1
                print(f"\n\n{'='*78}\n=== {game} {arm} L{lvl} clear at event {ci}, "
                      f"action {ev[ci]['action_num']} ({ev[ci].get('action_display')})")
                prior = [i for i in range(ci) if ev[i].get("transcript")]
                after = [i for i in range(ci + 1, len(ev)) if ev[i].get("transcript")]
                slots = [("PRIOR", prior[-1] if prior else None),
                         ("ISSUER", after[0] if after else None),
                         ("REACT", after[1] if len(after) > 1 else None)]
                for name, i in slots:
                    if i is None:
                        print(f"\n--- {name}: (none)")
                        continue
                    t = ev[i]["transcript"]
                    think = _strip_tools(model_text(t, keep=("[THINKING]",)))
                    asst = _strip_tools(model_text(t, keep=("[ASSISTANT]",)))
                    print(f"\n--- {name} [{i}] a{ev[i].get('action_num')} "
                          f"step{ev[i].get('analysis_step')}\n{think[:cap]}")
                    if asst:
                        print(asst)  # never truncated — carries World/Goal/Plan


def cmd_goals(corpus: str, arm: str, game: str, cap: int = 900) -> None:
    """Per-turn [ASSISTANT] summaries for one game-pass: the goal-articulation trajectory.

    The harness prompt asks for a world-model/goal/plan summary each turn, so this block
    is the model's own statement of what it currently thinks the goal is.
    """
    for run, run_arm, _, _ in iter_runs(corpus):
        if run_arm != arm:
            continue
        for path in sorted((run / "artifacts").glob("*_events.jsonl")):
            if game_key(path)[0] != game:
                continue
            ev = load_events(path)
            print(f"=== {game} corpus={corpus} arm={arm} ({len(ev)} events)")
            for i, e in enumerate(ev):
                if e.get("type") == "action" and e.get("level_completed"):
                    print(f"\n>>>>> [{i}] ACTION {e['action_num']} {e.get('action_display')} "
                          f"-- LEVEL {(e.get('level') or 2) - 1} COMPLETED\n")
                if not e.get("transcript"):
                    continue
                txt = model_text(e["transcript"], keep=("[ASSISTANT]",)).strip()
                if not txt:
                    continue
                print(f"[{i}] a{e.get('action_num')} step{e.get('analysis_step')}: "
                      f"{txt[len('[ASSISTANT]'):].strip()[:cap]}")
            return
    raise SystemExit(f"no match for corpus={corpus} arm={arm} game={game}")


def cmd_window(corpus: str, arm: str, game: str, lo: int, hi: int) -> None:
    """Print thinned events plus full transcripts for events[lo:hi] of one game-pass."""
    for run, run_arm, _, _ in iter_runs(corpus):
        if run_arm != arm:
            continue
        for path in sorted((run / "artifacts").glob("*_events.jsonl")):
            if game_key(path)[0] != game:
                continue
            ev = load_events(path)
            lo2, hi2 = max(0, lo), min(len(ev), hi)
            print(f"=== {game} corpus={corpus} arm={arm} run={run.name} "
                  f"events[{lo2}:{hi2}] of {len(ev)}")
            for i in range(lo2, hi2):
                e = ev[i]
                print(f"\n----- [{i}] {json.dumps(thin(e))}")
                if e.get("transcript"):
                    print(e["transcript"])
            return
    raise SystemExit(f"no match for corpus={corpus} arm={arm} game={game}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "split"
    if cmd == "split":
        for c in (["local", "ref"] if len(sys.argv) < 3 or sys.argv[2] == "both"
                  else [sys.argv[2]]):
            cmd_split(c)
            print()
    elif cmd == "clears":
        cmd_clears(sys.argv[2] if len(sys.argv) > 2 else "local")
    elif cmd == "clearctx":
        cmd_clearctx(sys.argv[2] if len(sys.argv) > 2 else "ref",
                     int(sys.argv[3]) if len(sys.argv) > 3 else 1800)
    elif cmd == "goals":
        cmd_goals(sys.argv[2], sys.argv[3], sys.argv[4],
                  int(sys.argv[5]) if len(sys.argv) > 5 else 900)
    elif cmd == "reason":
        cmd_reason(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6]),
                   int(sys.argv[7]) if len(sys.argv) > 7 else 100000)
    elif cmd == "window":
        cmd_window(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6]))
    else:
        raise SystemExit(__doc__)
