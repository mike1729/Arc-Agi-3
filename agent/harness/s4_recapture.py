#!/usr/bin/env python3
"""Slice-4 animation recapture — every frame the engine returns, for stored episodes.

`notes/qwen-3.8-slice4-design.md` → Autonomous sources. The v3 store keeps settled
endpoint grids only; animations expose movement, rotation, recolouring and
consumption. This module replays the explorer's own episodes (reconstructed from
`e1_store_v3/*.performs.jsonl`) through the live engine and keeps EVERYTHING each
action returns.

Soundness follows the `e3_completion_capture` precedent: the engine is deterministic,
so a replayed episode is the same episode — and the gate makes that a check, not an
assumption. After every action, the replayed SETTLED grid must equal the store's
recorded post grid CELL FOR CELL (resolved through `states.json`, compared as grids,
never as digests). A step that diverges fails the episode from that step on: frames
captured before the divergence are kept and marked `verified`, everything after is
discarded, and the episode is recorded `diverged_at_step`. Nothing is ever "captured
with a warning".

Leakage note: rev 2 explicitly permits the CAPTURE process to use the engine ("the
capture process may use the engine to replay autonomous histories"); the packet
builder never imports this module — it reads only the emitted observation files.
Output is local-only (`logs/s4_observation_log/recapture/`, under the `/logs/*/*`
gitignore rule; frames are competition-game boards and never enter a commit).

Run:
  .venv/bin/python agent/harness/s4_recapture.py --games ls20 ft09 m0r0 sp80
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v3"
OUT = ROOT / "logs/s4_observation_log/recapture"
PILOT_GAMES = ("ls20", "ft09", "m0r0", "sp80")


class Engine:
    """Same wrapping as e3_completion_capture: deterministic local engine."""

    def __init__(self, game: str):
        from arcengine import ActionInput, GameAction  # noqa: PLC0415
        from gi2_replay import ReplayDriver, _plain_frames  # noqa: PLC0415

        self._input = ActionInput
        self._action = GameAction
        self._frames = _plain_frames
        self.driver = ReplayDriver(game)

    def new(self):
        return self.driver.new_game()

    def perform(self, handle, action: tuple) -> Any:
        action_id, row, col = action
        return self.driver.perform(
            handle,
            self._input(
                id=self._action.from_id(action_id),
                data={} if row is None else {"y": row, "x": col},
            ),
        )

    def frames(self, response: Any) -> list:
        return self._frames(response.frame or [])


def episodes(game: str) -> list[list[dict[str, Any]]]:
    """Episodes reconstructed from performs rows; a row with episode_step == 0
    starts a new one. Order within the file is the explorer's own order."""
    rows = [json.loads(line) for line in open(STORE / f"{game}.performs.jsonl")]
    out: list[list[dict[str, Any]]] = []
    for row in rows:
        if row.get("episode_step") == 0:
            out.append([])
        if not out:  # defensive: file must start at an episode boundary
            raise RuntimeError(f"{game}: performs does not start at episode_step 0")
        out[-1].append(row)
    return out


def grid_digest(grid: list[list[int]]) -> str:
    payload = json.dumps(grid, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def recapture_episode(
    engine: Engine,
    states: dict[str, Any],
    episode: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    handle = engine.new()
    steps: list[dict[str, Any]] = []
    diverged_at: int | None = None
    for row in episode:
        response = engine.perform(handle, tuple(row["action"]))
        frames = [list(map(list, frame)) for frame in engine.frames(response)]
        settled = frames[-1] if frames else None
        expected_digest = row.get("post")
        expected = states.get(expected_digest) if expected_digest else None
        verified = (
            expected is not None
            and settled is not None
            and settled == [list(r) for r in expected]
        )
        steps.append(
            {
                "episode_step": row["episode_step"],
                "store_step": row["step"],
                "action": row["action"],
                "frame_count": len(frames),
                "frames": frames,
                "settled_digest": grid_digest(settled) if settled else None,
                "verified": bool(verified),
            }
        )
        if not verified:
            diverged_at = row["episode_step"]
            break
    kept = steps if diverged_at is None else steps[:-1]
    return {
        "episode_index": index,
        "actions_replayed": len(steps),
        "steps_verified": len(kept),
        "diverged_at_step": diverged_at,
        "total_frames": sum(s["frame_count"] for s in kept),
        "animation_steps": sum(1 for s in kept if s["frame_count"] > 1),
        "steps": kept,
    }


def recapture_game(game: str, out_dir: Path) -> dict[str, Any]:
    states = json.loads((STORE / f"{game}.states.json").read_text())
    engine = Engine(game)
    game_dir = out_dir / game
    game_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for i, episode in enumerate(episodes(game)):
        record = recapture_episode(engine, states, episode, i)
        path = game_dir / f"episode_{i:03d}.json"
        path.write_text(json.dumps(record, separators=(",", ":")))
        summaries.append(
            {
                "episode_index": i,
                "file": path.name,
                "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "actions_replayed": record["actions_replayed"],
                "steps_verified": record["steps_verified"],
                "diverged_at_step": record["diverged_at_step"],
                "total_frames": record["total_frames"],
                "animation_steps": record["animation_steps"],
            }
        )
    verified_steps = sum(s["steps_verified"] for s in summaries)
    replayed = sum(s["actions_replayed"] for s in summaries)
    manifest = {
        "game": game,
        "episodes": summaries,
        "episode_count": len(summaries),
        "steps_replayed": replayed,
        "steps_verified": verified_steps,
        "verification_rate": round(verified_steps / replayed, 4) if replayed else None,
        "animation_steps": sum(s["animation_steps"] for s in summaries),
        "total_frames": sum(s["total_frames"] for s in summaries),
    }
    (game_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(PILOT_GAMES))
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    for game in args.games:
        manifest = recapture_game(game, args.out)
        print(
            f"{game:5s} episodes {manifest['episode_count']:3d} "
            f"steps {manifest['steps_verified']}/{manifest['steps_replayed']} verified "
            f"({manifest['verification_rate']}) "
            f"animation steps {manifest['animation_steps']} "
            f"frames {manifest['total_frames']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
