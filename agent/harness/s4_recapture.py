#!/usr/bin/env python3
"""Slice-4 animation recapture with endpoint and temporal-fidelity gates.

The explorer store contains settled endpoints and the number of frames returned for
recorded test transitions.  This module replays each autonomous episode through the
local engine, retains every returned frame, and admits a step only when every
historical field that exists agrees:

* a stored grid must match the replayed settled grid cell-for-cell;
* a stored ``post: null`` must replay as a legitimate zero-frame response;
* response state and completed-level count must match the performs row; and
* frame count must match the transitions row when that historical count exists.

A genuine divergence keeps the verified prefix and explicitly counts the unattempted
suffix.  Builds are staged and directory-swapped, so an interrupted rerun cannot leave
new episode files behind an old manifest.  Raw competition frames may only be written
below ``logs/`` in this repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v3"
OUT = ROOT / "logs/s4_observation_log/recapture"
PILOT_GAMES = ("ls20", "ft09", "m0r0", "sp80")
FORMAT_VERSION = 2


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def normalise_grid(value: Any, label: str) -> list[list[int]]:
    """Require an exact 64x64 integral engine observation without pixel coercion."""
    array = np.asarray(value)
    require(array.shape == (64, 64), f"{label}: grid shape {array.shape} != (64, 64)")
    require(np.issubdtype(array.dtype, np.integer),
            f"{label}: grid dtype {array.dtype} is not integral")
    require(bool(np.all((0 <= array) & (array <= 15))),
            f"{label}: grid contains a colour outside 0..15")
    return [[int(cell) for cell in row] for row in array.tolist()]


def _state_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def validate_output_root(path: Path) -> Path:
    """Refuse raw-frame destinations outside this repository's ignored logs tree."""
    resolved = path.resolve()
    logs_root = (ROOT / "logs").resolve()
    require(resolved != logs_root, "recapture output may not replace the logs root")
    require(logs_root in resolved.parents, (
        f"unsafe recapture output {resolved}: raw competition frames must stay below {logs_root}"
    ))
    return resolved


def atomic_replace_dir(staged: Path, target: Path) -> None:
    """Install a fully built directory without ever mixing old and new files."""
    require(staged.parent == target.parent, "staged and target directories must be siblings")
    backup = target.parent / f".{target.name}.backup-{os.getpid()}"
    require(not backup.exists(), f"stale atomic-build backup exists: {backup}")
    moved_old = False
    try:
        if target.exists():
            os.replace(target, backup)
            moved_old = True
        os.replace(staged, target)
    except Exception:
        if moved_old and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    else:
        if backup.exists():
            shutil.rmtree(backup)


class Engine:
    """Same deterministic local engine path as the explorer and GI replay tools."""

    def __init__(self, game: str):
        from arcengine import ActionInput, GameAction  # noqa: PLC0415
        from gi2_replay import ReplayDriver, _game_source, _plain_frames  # noqa: PLC0415

        self._input = ActionInput
        self._action = GameAction
        self._frames = _plain_frames
        self.source_path = _game_source(game)
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


def load_store(game: str) -> tuple[list[list[dict[str, Any]]], dict[str, Any], dict[int, dict]]:
    performs_path = STORE / f"{game}.performs.jsonl"
    states_path = STORE / f"{game}.states.json"
    transitions_path = STORE / f"{game}.transitions.jsonl"
    rows = []
    for index, line in enumerate(performs_path.read_text().splitlines()):
        row = json.loads(line)
        row["_store_index"] = index
        rows.append(row)
    states = json.loads(states_path.read_text())
    historical = {
        int(row["step"]): row
        for row in (json.loads(line) for line in transitions_path.read_text().splitlines())
    }

    episodes: list[list[dict[str, Any]]] = []
    for row in rows:
        require(set(row) >= {
            "step", "episode_step", "action", "post", "state", "levels",
        }, f"{game}: row {row['_store_index']} lacks a fidelity-gated field")
        require(type(row["step"]) is int and row["step"] > 0,
                f"{game}: row {row['_store_index']} has invalid global step")
        require(isinstance(row["state"], str) and bool(row["state"]),
                f"{game}: row {row['_store_index']} has invalid response state")
        require(type(row["levels"]) is int and row["levels"] >= 0,
                f"{game}: row {row['_store_index']} has invalid completed-level count")
        action = row["action"]
        require(isinstance(action, list) and len(action) == 3 and type(action[0]) is int,
                f"{game}: row {row['_store_index']} has malformed action")
        episode_step = row.get("episode_step")
        require(isinstance(episode_step, int) and episode_step >= 0, (
            f"{game}: row {row['_store_index']} has invalid episode_step {episode_step!r}"
        ))
        if episode_step == 0:
            episodes.append([])
        require(bool(episodes), f"{game}: performs does not start at episode_step 0")
        expected_step = len(episodes[-1])
        require(episode_step == expected_step, (
            f"{game}: episode step discontinuity at store index {row['_store_index']}: "
            f"expected {expected_step}, got {episode_step}"
        ))
        if episode_step > 0:
            require(row.get("pre") == episodes[-1][-1].get("post"), (
                f"{game}: causal predecessor mismatch at store index "
                f"{row['_store_index']}"
            ))
        episodes[-1].append(row)
    return episodes, states, historical


def episodes(game: str) -> list[list[dict[str, Any]]]:
    """Compatibility wrapper used by diagnostics and tests."""
    return load_store(game)[0]


def recapture_episode(
    engine: Engine,
    states: dict[str, Any],
    episode: list[dict[str, Any]],
    index: int,
    historical: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    historical = historical or {}
    handle = engine.new()
    kept: list[dict[str, Any]] = []
    attempted = 0
    divergence: dict[str, Any] | None = None

    for row in episode:
        attempted += 1
        response = engine.perform(handle, tuple(row["action"]))
        frames = [
            normalise_grid(
                frame,
                f"episode {index} store index {row['_store_index']} raw frame {frame_index}",
            )
            for frame_index, frame in enumerate(engine.frames(response))
        ]
        settled = frames[-1] if frames else None
        expected_digest = row.get("post")
        expected = states.get(expected_digest) if expected_digest is not None else None
        expected_grid = (
            normalise_grid(expected, f"store digest {expected_digest}")
            if expected is not None else None
        )
        expected_digest_known = expected_digest is None or expected is not None
        grid_match = (
            settled is None
            if expected_digest is None
            else expected_digest_known and settled == expected_grid
        )

        actual_state = _state_text(getattr(response, "state", None))
        actual_levels_raw = getattr(response, "levels_completed", None)
        actual_levels = int(actual_levels_raw) if actual_levels_raw is not None else None
        expected_state = row.get("state")
        expected_levels = row.get("levels")
        state_match = expected_state is None or actual_state == str(expected_state)
        levels_match = expected_levels is None or actual_levels == int(expected_levels)

        old = historical.get(int(row["step"]))
        expected_frame_count = old.get("frames") if old is not None else None
        frame_count_match = expected_frame_count is None or len(frames) == int(expected_frame_count)
        historical_state_match = (
            old is None or old.get("state") is None or actual_state == str(old["state"])
        )
        historical_identity_match = bool(
            old is None
            or all(
                old[field] == row.get(field)
                for field in ("action", "post", "episode_step", "source")
                if field in old
            )
        )
        verified = all((
            expected_digest_known,
            grid_match,
            state_match,
            levels_match,
            frame_count_match,
            historical_state_match,
            historical_identity_match,
        ))

        step = {
            "episode_step": int(row["episode_step"]),
            "store_index": int(row["_store_index"]),
            "store_step": int(row["step"]),
            "source": row.get("source"),
            "action": row["action"],
            "expected_store_digest": expected_digest,
            "frame_count": len(frames),
            "expected_frame_count": expected_frame_count,
            "frames": frames,
            "settled_grid_sha256": canonical_sha256(settled) if settled is not None else None,
            "response_state": actual_state,
            "expected_state": expected_state,
            "levels_completed": actual_levels,
            "expected_levels_completed": expected_levels,
            "checks": {
                "expected_digest_known": expected_digest_known,
                "grid_or_absence": grid_match,
                "state": state_match,
                "levels_completed": levels_match,
                "historical_frame_count": frame_count_match,
                "historical_state": historical_state_match,
                "historical_identity": historical_identity_match,
            },
            "verified": bool(verified),
        }
        if not verified:
            divergence = {
                "store_index": step["store_index"],
                "store_step": step["store_step"],
                "episode_step": step["episode_step"],
                "failed_checks": [name for name, ok in step["checks"].items() if not ok],
                "observed": {k: step[k] for k in (
                    "frame_count", "settled_grid_sha256", "response_state", "levels_completed"
                )},
                "expected": {
                    "store_digest": expected_digest,
                    "frame_count": expected_frame_count,
                    "state": expected_state,
                    "levels_completed": expected_levels,
                },
            }
            break
        kept.append(step)

    skipped = len(episode) - attempted
    return {
        "format_version": FORMAT_VERSION,
        "episode_index": index,
        "store_start_index": int(episode[0]["_store_index"]),
        "store_end_index": int(episode[-1]["_store_index"]),
        "actions_expected": len(episode),
        "actions_attempted": attempted,
        "actions_replayed": attempted,
        "steps_verified": len(kept),
        "steps_skipped_after_divergence": skipped,
        "diverged_at_step": None if divergence is None else divergence["episode_step"],
        "divergence": divergence,
        "total_frames": sum(s["frame_count"] for s in kept),
        "animation_steps": sum(1 for s in kept if s["frame_count"] > 1),
        "zero_frame_steps": sum(1 for s in kept if s["frame_count"] == 0),
        "steps": kept,
    }


def _package_versions() -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for package in ("arc-agi", "arcengine", "numpy", "Pillow"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def _input_provenance(game: str, engine: Engine) -> dict[str, Any]:
    store_files = {}
    for suffix in ("performs.jsonl", "states.json", "transitions.jsonl", "graph.json"):
        path = STORE / f"{game}.{suffix}"
        require(path.is_file(), f"missing recapture input: {path}")
        store_files[suffix] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    engine_files = {
        "game_source": {
            "path": str(engine.source_path),
            "bytes": engine.source_path.stat().st_size,
            "sha256": sha256_file(engine.source_path),
        },
        "gi2_replay": {
            "path": str(HARNESS / "gi2_replay.py"),
            "sha256": sha256_file(HARNESS / "gi2_replay.py"),
        },
        "recapture_script": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
    }
    try:
        import arcengine  # noqa: PLC0415

        arc_path = Path(arcengine.__file__).resolve()
        engine_files["arcengine_module"] = {"path": str(arc_path), "sha256": sha256_file(arc_path)}
    except Exception as exc:  # provenance records absence; replay itself already imported it
        engine_files["arcengine_module"] = {"error": repr(exc)}
    return {"store": store_files, "engine": engine_files, "versions": _package_versions()}


def _build_game(game: str, game_dir: Path) -> dict[str, Any]:
    episode_rows, states, historical = load_store(game)
    engine = Engine(game)
    game_dir.mkdir(parents=True, exist_ok=False)
    summaries = []
    for index, episode in enumerate(episode_rows):
        record = recapture_episode(engine, states, episode, index, historical)
        path = game_dir / f"episode_{index:03d}.json"
        path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")))
        summaries.append({
            "episode_index": index,
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "actions_expected": record["actions_expected"],
            "actions_attempted": record["actions_attempted"],
            "actions_replayed": record["actions_replayed"],
            "steps_verified": record["steps_verified"],
            "steps_skipped_after_divergence": record["steps_skipped_after_divergence"],
            "diverged_at_step": record["diverged_at_step"],
            "total_frames": record["total_frames"],
            "animation_steps": record["animation_steps"],
            "zero_frame_steps": record["zero_frame_steps"],
        })

    expected = sum(s["actions_expected"] for s in summaries)
    attempted = sum(s["actions_attempted"] for s in summaries)
    verified = sum(s["steps_verified"] for s in summaries)
    manifest = {
        "format_version": FORMAT_VERSION,
        "status": "complete" if verified == expected else "verified_prefixes_only",
        "game": game,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "provenance": _input_provenance(game, engine),
        "episodes": summaries,
        "episode_count": len(summaries),
        "steps_expected": expected,
        "steps_attempted": attempted,
        "steps_replayed": attempted,
        "steps_verified": verified,
        "steps_skipped_after_divergence": sum(
            s["steps_skipped_after_divergence"] for s in summaries
        ),
        "verification_rate": round(verified / expected, 8) if expected else None,
        "animation_steps": sum(s["animation_steps"] for s in summaries),
        "zero_frame_steps": sum(s["zero_frame_steps"] for s in summaries),
        "total_frames": sum(s["total_frames"] for s in summaries),
    }
    manifest_path = game_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def recapture_game(game: str, out_dir: Path) -> dict[str, Any]:
    require(re.fullmatch(r"[A-Za-z0-9_-]+", game) is not None,
            f"unsafe game id {game!r}")
    out_dir = validate_output_root(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / game
    staged = Path(tempfile.mkdtemp(prefix=f".{game}.staging-", dir=out_dir))
    # mkdtemp creates the directory; _build_game deliberately requires a new child.
    build_dir = staged / game
    ready = staged.parent / f".{game}.ready-{os.getpid()}"
    require(not ready.exists(), f"stale recapture ready directory exists: {ready}")
    try:
        manifest = _build_game(game, build_dir)
        os.replace(build_dir, ready)
        shutil.rmtree(staged)
        atomic_replace_dir(ready, target)
        return manifest
    except Exception:
        if staged.exists():
            shutil.rmtree(staged)
        if ready.exists():
            shutil.rmtree(ready)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(PILOT_GAMES))
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    validate_output_root(args.out)
    for game in args.games:
        manifest = recapture_game(game, args.out)
        print(
            f"{game:5s} episodes {manifest['episode_count']:3d} "
            f"steps {manifest['steps_verified']}/{manifest['steps_expected']} verified "
            f"({manifest['verification_rate']}) "
            f"animation steps {manifest['animation_steps']} "
            f"frames {manifest['total_frames']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
