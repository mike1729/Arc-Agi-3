#!/usr/bin/env python3
"""Slice-4 blocking leakage gate: field-allowlisted export of the Kaggle v4 histories.

`notes/qwen-3.8-slice4-design.md` → review round 1, finding 4. The raw artifacts
interleave observation rows with 1,379 `analysis` rows carrying the prior model's
transcripts and goal guesses. The packet builder must never be able to open those
files — it consumes ONLY this exporter's output, and this exporter:

  - keeps rows of type `initial` and `action`; drops `analysis` rows whole;
  - keeps a strict field allowlist; ABORTS on any unknown field or row type
    (schema drift = uncertain provenance = build nothing);
  - validates every kept value against closed enums / regexes / ranges — free text
    cannot pass (`action_display` must be an action token or `MOUSE(row=R, col=C)`,
    which is parsed into structured click coordinates and discarded as text);
  - verifies the fleet against the operator-measured census (25 games; 25 initial /
    3,833 action / 1,379 analysis rows) — a count drift aborts;
  - emits canonical, key-sorted JSONL per game plus a manifest with the SHA-256 of
    every normalized output and of every source file.

Blindness by construction: imports are stdlib-only; the only path this script reads
is the artifacts directory; it imports no game, store, or human-replay code.

Run:
  .venv/bin/python agent/harness/s4_export_kaggle.py \
      --out logs/s4_observation_log/kaggle_v4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "logs/kaggle_v4/artifacts"

EXPECTED_GAMES = 25
EXPECTED_ROWS = {"initial": 25, "action": 3833, "analysis": 1379}

KEEP_TYPES = ("initial", "action")
DROP_TYPES = ("analysis",)

# Input allowlists per row type: every field must be listed as kept or dropped;
# an unlisted field aborts the export.
KEPT_FIELDS = {
    "initial": {"type", "board", "level", "score", "state", "action_num", "reward",
                "action_display"},
    "action": {"type", "board", "level", "score", "state", "action_num", "reward",
               "action_name", "action_display", "level_completed", "done",
               "game_over"},
}
DROPPED_FIELDS = {
    "initial": {"board_ascii", "title", "analysis_step", "run_status"},
    "action": {"board_ascii", "title", "analysis_step", "run_status", "run_complete",
               "batch_index", "batch_size", "board_changed", "transcript"},
}

STATE_ENUM = {"NOT_FINISHED", "NOT_PLAYED", "WIN", "GAME_OVER"}
ACTION_NAME_RE = re.compile(r"^(RESET|ACTION[1-7])$")
MOUSE_RE = re.compile(r"^MOUSE\(row=(\d{1,2}), col=(\d{1,2})\)$")
# The duck harness's UI labels for non-click actions — a closed set, validated so free
# text cannot hide in the field, then DROPPED: they are the harness's semantic
# interpretation (directions), and the ledger is semantics-free. Only MOUSE(...) rows
# contribute data (structured click coordinates).
DISPLAY_LABELS = {"UP", "DOWN", "LEFT", "RIGHT", "SPACE", "RESET"}


class ExportAbort(RuntimeError):
    """Provenance is uncertain — build nothing."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportAbort(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_board(board: Any, where: str) -> list[list[int]]:
    require(isinstance(board, list) and len(board) == 64, f"{where}: board is not 64 rows")
    for row in board:
        require(isinstance(row, list) and len(row) == 64, f"{where}: board row is not 64 wide")
        for value in row:
            require(isinstance(value, int) and 0 <= value <= 15, f"{where}: cell {value!r} outside 0..15")
    return board


def normalize_row(row: dict[str, Any], seq: int, where: str) -> dict[str, Any]:
    rtype = row.get("type")
    require(rtype in KEEP_TYPES, f"{where}: unexpected row type {rtype!r}")
    unknown = set(row) - KEPT_FIELDS[rtype] - DROPPED_FIELDS[rtype]
    require(not unknown, f"{where}: unknown fields {sorted(unknown)} — aborting on schema drift")

    display = row.get("action_display")
    click = None
    if rtype == "initial":
        require(display == "RESET", f"{where}: initial action_display {display!r} != RESET")
        action = "RESET"
    else:
        name = row.get("action_name")
        require(isinstance(name, str) and ACTION_NAME_RE.match(name), f"{where}: bad action_name {name!r}")
        action = name
        require(isinstance(display, str), f"{where}: action_display missing")
        mouse = MOUSE_RE.match(display)
        if mouse:
            require(name == "ACTION6", f"{where}: MOUSE display on {name}")
            r, c = int(mouse.group(1)), int(mouse.group(2))
            require(0 <= r <= 63 and 0 <= c <= 63, f"{where}: click ({r},{c}) off-board")
            click = [r, c]
        else:
            require(display in DISPLAY_LABELS, (
                f"{where}: free-text action_display {display!r} rejected"
            ))
            # validated against the closed label set, then dropped — semantics-free

    state = row.get("state")
    require(state in STATE_ENUM, f"{where}: state {state!r} outside {sorted(STATE_ENUM)}")
    level = row.get("level")
    require(isinstance(level, int) and 1 <= level <= 10, f"{where}: level {level!r}")
    action_num = row.get("action_num")
    require(isinstance(action_num, int) and action_num >= 0, f"{where}: action_num {action_num!r}")
    score = row.get("score")
    require(isinstance(score, int), f"{where}: score {score!r}")
    reward = row.get("reward")
    require(isinstance(reward, (int, float)), f"{where}: reward {reward!r}")

    out: dict[str, Any] = {
        "seq": seq,
        "type": rtype,
        "action": action,
        "click": click,
        "board": validate_board(row.get("board"), where),
        "level": level,
        "score": score,
        "state": state,
        "action_num": action_num,
        "reward": float(reward),
        "level_completed": bool(row.get("level_completed", False)),
        "done": bool(row.get("done", False)),
        "game_over": bool(row.get("game_over", False)),
    }
    return out


def export_game(path: Path, out_dir: Path) -> dict[str, Any]:
    game = path.name.split("-")[0]
    kept: list[dict[str, Any]] = []
    counts = {"initial": 0, "action": 0, "analysis": 0}
    for i, line in enumerate(path.read_text().splitlines()):
        row = json.loads(line)
        rtype = row.get("type")
        where = f"{path.name}:{i}"
        if rtype in DROP_TYPES:
            counts[rtype] += 1
            continue
        require(rtype in KEEP_TYPES, f"{where}: unexpected row type {rtype!r}")
        counts[rtype] += 1
        kept.append(normalize_row(row, seq=len(kept), where=where))

    payload = "\n".join(json.dumps(r, sort_keys=True, separators=(",", ":")) for r in kept) + "\n"
    out_path = out_dir / f"{game}.observations.jsonl"
    out_path.write_text(payload)
    return {
        "game": game,
        "source": path.name,
        "source_sha256": sha256_bytes(path.read_bytes()),
        "rows": counts,
        "kept_rows": len(kept),
        "completions": sum(1 for r in kept if r["level_completed"]),
        "output": out_path.name,
        "output_sha256": sha256_bytes(payload.encode()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=ROOT / "logs/s4_observation_log/kaggle_v4")
    args = parser.parse_args()

    files = sorted(args.source.glob("*_events.jsonl"))
    require(len(files) == EXPECTED_GAMES, f"{len(files)} event files != {EXPECTED_GAMES}")
    args.out.mkdir(parents=True, exist_ok=True)

    manifests = []
    totals = {"initial": 0, "action": 0, "analysis": 0}
    try:
        for path in files:
            manifest = export_game(path, args.out)
            for key, value in manifest["rows"].items():
                totals[key] += value
            manifests.append(manifest)
            print(f"{manifest['game']:6s} kept {manifest['kept_rows']:4d} "
                  f"(dropped {manifest['rows']['analysis']:3d} analysis) "
                  f"completions {manifest['completions']}", flush=True)
        require(totals == EXPECTED_ROWS, (
            f"fleet census drift: {totals} != {EXPECTED_ROWS} — provenance uncertain"
        ))
    except ExportAbort as abort:
        # Abort must leave no partial export a downstream builder could mistake for
        # a complete one.
        for stale in args.out.glob("*.observations.jsonl"):
            stale.unlink()
        (args.out / "ABORTED.txt").write_text(str(abort) + "\n")
        print(f"EXPORT ABORTED: {abort}", file=sys.stderr)
        return 1

    document = {
        "note": "notes/qwen-3.8-slice4-design.md -> review round 1 finding 4; blocking leakage gate",
        "source_dir": str(args.source),
        "exporter_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "fleet_rows": totals,
        "games": manifests,
    }
    manifest_path = args.out / "manifest.json"
    manifest_path.write_text(json.dumps(document, indent=1, sort_keys=True))
    print(f"fleet census OK {totals}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
