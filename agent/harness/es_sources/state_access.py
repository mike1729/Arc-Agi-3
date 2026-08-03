#!/usr/bin/env python3
"""Per-state source accessors and fork wiring (adapters increment 2).

Implements the two remaining SS2.2 adapter obligations over the audited GI-2 estate:

  * ``source object masks, properties, relations, identities, and lineage where
    defined`` — a resolved ``StateHandle`` holds the LIVE engine instance at a selected
    state; ``source_objects()`` extracts the gold-set sprites via
    ``gi2_grounding.semantic_sprites`` and projects display-coordinate masks;
    ``source_relations()`` derives mechanical pairwise relations from those masks.
    Identity is the engine sprite name where the game defines one (m0r0's mover family),
    else a deterministic position digest; lineage across states is identity persistence.
  * ``deterministic forks used by the oracle probe ceiling`` — ``StateHandle.fork()``
    deep-copies the live game, executes one alternative action, and reads the label from
    the ENGINE's level transition, mirroring ``gi2_forks``; the branch handle supports the
    DOSE-4 greedy-sequential continuation (probe 2 forks from the post-probe-1 state,
    never from a restored root). Pre-computed fork rows from the reused GI-2 tables
    (including vc33's erratum-regenerated corpus) are exposed through a digest-checked
    lookup and re-verified against the resolved pre-state grid.

Snapshot semantics follow ``gi2_forks`` exactly: a state keyed by step ``q`` is the
engine/tracker/grid state immediately before the recorded action ``q`` is performed —
the query pre-state of an ES transfer case whose completing action is ``q``. The
replayed settled grid is asserted equal to the recorded settled grid at every snapshot
(the accepted vc33 erratum guarantees settled equality), and to the fork table's
``pre_grid_rle`` where a row exists.

Run:
  .venv/bin/python agent/harness/es_sources/state_access.py --validate --jobs 6
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from arcengine import ActionInput, GameAction  # noqa: E402

from gi2_forks import decode_grid  # noqa: E402
from gi2_grounding import projected_sprite_cells, semantic_sprites  # noqa: E402
from gi2_observation import Tracker  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames, iter_recorded_actions  # noqa: E402
from gi2_traces import CORPUS, ROOT, frame_roles  # noqa: E402

FORK_TABLE = ROOT / "logs/gi2_fork_table.json"
AR_VC33_FORKS = ROOT / "logs/gi2_ar_vc33_forks.json"
INVENTORY = ROOT / "logs/es_inventory.json"
OUTPUT = ROOT / "logs/es_state_access.json"
FORMAT_VERSION = 1
SAMPLE_FORKS_PER_GAME = 8


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def grid_delta(before: list, after: list) -> list[tuple[int, int]]:
    """Deterministic changed-cell list between two settled grids (row-major order)."""
    return [
        (row, col)
        for row, (brow, arow) in enumerate(zip(before, after))
        for col, (left, right) in enumerate(zip(brow, arow))
        if left != right
    ]


def _bbox(cells: list[tuple[int, int]]) -> tuple[int, int, int, int]:
    rows = [row for row, _ in cells]
    cols = [col for _, col in cells]
    return min(rows), min(cols), max(rows), max(cols)


def _intervals_overlap(a_min: int, a_max: int, b_min: int, b_max: int) -> bool:
    return a_min <= b_max and b_min <= a_max


def mechanical_relations(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pairwise relations derived from masks alone; no game knowledge."""
    relations = []
    for i, a in enumerate(objects):
        cells_a = set(map(tuple, a["cells"]))
        bbox_a = _bbox(a["cells"])
        for b in objects[i + 1 :]:
            cells_b = set(map(tuple, b["cells"]))
            bbox_b = _bbox(b["cells"])
            relations.append(
                {
                    "a": a["identity"],
                    "b": b["identity"],
                    "mask_overlap": bool(cells_a & cells_b),
                    "bbox_overlap": _intervals_overlap(bbox_a[0], bbox_a[2], bbox_b[0], bbox_b[2])
                    and _intervals_overlap(bbox_a[1], bbox_a[3], bbox_b[1], bbox_b[3]),
                    "a_contains_b": cells_b <= cells_a,
                    "b_contains_a": cells_a <= cells_b,
                    "row_aligned": _intervals_overlap(bbox_a[0], bbox_a[2], bbox_b[0], bbox_b[2]),
                    "col_aligned": _intervals_overlap(bbox_a[1], bbox_a[3], bbox_b[1], bbox_b[3]),
                }
            )
    return relations


def classify_fork_response(response: Any, previous_levels: int) -> dict[str, Any]:
    """Engine-derived label and DOSE-4 sequential-continuation indicators."""
    levels = int(response.levels_completed or 0)
    state = str(getattr(response.state, "value", response.state))
    completed = levels > previous_levels
    terminal = state in {"WIN", "GAME_OVER"}
    full_reset = bool(response.full_reset)
    return {
        "label": "complete" if completed else "non_complete",
        "completed": completed,
        "state": state,
        "levels_completed": levels,
        "full_reset": full_reset,
        "terminal": terminal,
        "sequential_continuable": not (completed or terminal or full_reset),
    }


def enumerate_candidates(
    available: tuple[int, ...], representatives: list[tuple[int, int]]
) -> list[dict[str, Any]]:
    """Deterministic reachable-action enumeration in gi2_forks' candidate format.

    RESET is excluded: executing it ends a DOSE-4 sequential branch by definition. The
    ES-IDENT freeze governs whether further exclusions apply; this is the substrate."""
    candidates: list[dict[str, Any]] = []
    for action_id in sorted(set(available)):
        if action_id == 0:
            continue
        if action_id == 6:
            candidates.extend(
                {"action_id": 6, "action_data": {"x": col, "y": row}}
                for row, col in representatives
            )
        else:
            candidates.append({"action_id": action_id, "action_data": {}})
    return candidates


@dataclass
class StateHandle:
    """A live engine state immediately before recorded step ``step`` (or a fork branch)."""

    env: str
    guid: str
    step: int
    game: Any
    tracker: Tracker
    settled_grid: list
    available_actions: tuple[int, ...]
    levels_completed: int
    mouse_representatives: list[tuple[int, int]]
    provenance: str = "recorded_prefix"
    probes_applied: list[dict[str, Any]] = field(default_factory=list)

    def source_objects(self) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for set_name, sprites in semantic_sprites(self.env, self.game).items():
            records = []
            for index, sprite in enumerate(sprites):
                cells3 = sorted(projected_sprite_cells(self.game, sprite))
                cells = sorted({(row, col) for row, col, _ in cells3})
                name = getattr(sprite, "name", None)
                identity = (
                    str(name)
                    if name
                    else hashlib.sha256(
                        f"{self.env}:{set_name}:{index}:{getattr(sprite, 'x', '?')}:"
                        f"{getattr(sprite, 'y', '?')}".encode()
                    ).hexdigest()[:16]
                )
                records.append(
                    {
                        "set": set_name,
                        "identity": identity,
                        "name": str(name) if name else None,
                        "x": int(getattr(sprite, "x", 0)),
                        "y": int(getattr(sprite, "y", 0)),
                        "cells": cells,
                        "colours": sorted({colour for _, _, colour in cells3}),
                        "pixels": len(cells),
                    }
                )
            out[set_name] = records
        return out

    def source_relations(self) -> list[dict[str, Any]]:
        objects = [record for records in self.source_objects().values() for record in records]
        return mechanical_relations([o for o in objects if o["cells"]])

    def reachable_actions(self) -> list[dict[str, Any]]:
        return enumerate_candidates(self.available_actions, self.mouse_representatives)

    def fork(self, action_id: int, action_data: dict[str, Any] | None = None):
        """Execute one alternative on a deep copy; return (outcome, branch handle)."""
        branch_game = copy.deepcopy(self.game)
        response = branch_game.perform_action(
            ActionInput(id=GameAction.from_id(action_id), data=dict(action_data or {})),
            raw=True,
        )
        outcome = classify_fork_response(response, self.levels_completed)
        frames = _plain_frames(response.frame or [])
        if not frames:
            branch_settled = self.settled_grid
        elif outcome["completed"] and outcome["state"] != "WIN" and len(frames) >= 2:
            branch_settled = frames[-1]  # next-level initial board is the new current state
        else:
            branch_settled = frames[-1]
        # Evaluation frame of the forked transition (es_candidates DOSE-4): the state
        # the advance check saw — solved_terminal for a completion, settled otherwise.
        if not frames:
            outcome["eval_grid"] = self.settled_grid
        elif outcome["completed"] and outcome["state"] != "WIN" and len(frames) >= 2:
            outcome["eval_grid"] = frames[-2]
        else:
            outcome["eval_grid"] = frames[-1]
        branch_tracker = copy.deepcopy(self.tracker)
        observation = None
        if frames:
            if outcome["completed"] and outcome["state"] != "WIN":
                branch_tracker.reset_level()
                observation = branch_tracker.update(
                    branch_settled, previous_grid=None,
                    action_id=action_id, action_data=dict(action_data or {}),
                )
            else:
                observation = branch_tracker.update(
                    branch_settled, previous_grid=self.settled_grid,
                    action_id=action_id, action_data=dict(action_data or {}),
                )
        available = tuple(
            int(getattr(item, "value", item)) for item in (response.available_actions or [])
        )
        branch = StateHandle(
            env=self.env,
            guid=self.guid,
            step=self.step,
            game=branch_game,
            tracker=branch_tracker,
            settled_grid=branch_settled,
            available_actions=available or self.available_actions,
            levels_completed=outcome["levels_completed"],
            mouse_representatives=(
                list(observation.mouse_representatives) if observation else []
            ),
            provenance="recorded_prefix+probes",
            probes_applied=self.probes_applied
            + [{"action_id": action_id, "action_data": dict(action_data or {})}],
        )
        return outcome, branch


def resolve_session_states(env: str, guid: str, steps: set[int]) -> dict[int, StateHandle]:
    """Single replay pass; snapshot the pre-state of every requested recorded step.

    Mirrors the gi2_forks main loop: tracker updates on settled / solved-terminal /
    next-level frames only, level reset at next-level boundaries, and the recording's
    advertised available_actions preferred over the local source's (ft09 discrepancy).
    Asserts replayed settled == recorded settled at every snapshot.
    """
    path = CORPUS / env / f"{guid}.recording.jsonl"
    driver = ReplayDriver(env)
    game = driver.new_game()
    tracker = Tracker()
    previous_grid: list | None = None
    recorded_previous_grid: list | None = None
    previous_observation = None
    previous_available: tuple[int, ...] = ()
    previous_levels = 0
    snapshots: dict[int, StateHandle] = {}
    wanted = set(steps)

    for action in iter_recorded_actions(path):
        if action.step in wanted:
            if previous_grid is None or previous_observation is None:
                raise ValueError(f"{env}:{guid}: step {action.step} has no pre-state")
            if previous_grid != recorded_previous_grid:
                raise ValueError(
                    f"{env}:{guid}: replayed settled pre-state of step {action.step} "
                    "differs from the recorded settled frame"
                )
            snapshots[action.step] = StateHandle(
                env=env,
                guid=guid,
                step=action.step,
                game=copy.deepcopy(game),
                tracker=copy.deepcopy(tracker),
                settled_grid=copy.deepcopy(previous_grid),
                available_actions=previous_available,
                levels_completed=previous_levels,
                mouse_representatives=list(previous_observation.mouse_representatives),
            )
            wanted.discard(action.step)

        response = driver.perform(game, action)
        replayed_frames = _plain_frames(response.frame or [])
        roles = frame_roles(
            state=action.state,
            n_frames=len(action.frames),
            completion_increment=action.levels_completed - previous_levels,
        )
        for replayed_grid, recorded_grid, role in zip(replayed_frames, action.frames, roles):
            if role not in {"settled", "solved_terminal", "next_level_initial"}:
                continue
            if role == "next_level_initial":
                tracker.reset_level()
                previous_grid = None
            previous_observation = tracker.update(
                replayed_grid,
                previous_grid=previous_grid,
                action_id=action.action_id,
                action_data=action.action_data,
            )
            previous_grid = replayed_grid
            recorded_previous_grid = recorded_grid
        previous_available = tuple(
            int(getattr(item, "value", item)) for item in (response.available_actions or [])
        )
        if action.available_actions:
            previous_available = action.available_actions
        previous_levels = action.levels_completed
        if not wanted:
            break

    if wanted:
        raise ValueError(f"{env}:{guid}: steps never reached: {sorted(wanted)}")
    return snapshots


class ForkTableLookup:
    """Digest-checked access to the reused GI-2 fork rows, keyed (env, guid, step)."""

    def __init__(self, expected_digests: dict[str, str] | None = None):
        self.digests = {
            str(FORK_TABLE.relative_to(ROOT)): _sha256_file(FORK_TABLE),
            str(AR_VC33_FORKS.relative_to(ROOT)): _sha256_file(AR_VC33_FORKS),
        }
        if expected_digests:
            for path, expected in expected_digests.items():
                if self.digests.get(path) != expected:
                    raise ValueError(
                        f"fork table {path} hash {self.digests.get(path)} != pinned {expected}"
                    )
        self.rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        main = json.loads(FORK_TABLE.read_text())
        for game in main["games"]:
            for session in game.get("sessions", []):
                for row in session.get("completions", []):
                    self.rows[(game["env"], session["guid"], int(row["step"]))] = row
        ar = json.loads(AR_VC33_FORKS.read_text())
        for row in ar.get("completions", []):
            self.rows[("vc33", row["guid"], int(row["step"]))] = row

    def row(self, env: str, guid: str, step: int) -> dict[str, Any] | None:
        return self.rows.get((env, guid, step))

    def verify_pre_state(self, row: dict[str, Any], handle: StateHandle) -> bool:
        encoded = row.get("pre_grid_rle")
        if not encoded:
            return False
        return decode_grid(encoded) == handle.settled_grid


def _validate_worker(job: dict[str, Any]) -> dict[str, Any]:
    env, guid = job["env"], job["guid"]
    cases = job["cases"]
    handles = resolve_session_states(env, guid, {case["step"] for case in cases})
    lookup = ForkTableLookup()
    results = []
    for case in cases:
        handle = handles[case["step"]]
        outcome, _ = handle.fork(case["action_id"], case["action_data"])
        objects = handle.source_objects()
        row = lookup.row(env, guid, case["step"])
        sample_checked = sample_agreed = 0
        if job["sample"] and case["step"] == job["sample_step"] and row is not None:
            for fork in row["forks"][:SAMPLE_FORKS_PER_GAME]:
                fresh, _ = handle.fork(fork["action_id"], dict(fork["action_data"]))
                sample_checked += 1
                sample_agreed += fresh["completed"] == bool(fork["completed"])
        results.append(
            {
                "case_id": case["case_id"],
                "completing_action_completes": outcome["completed"],
                "source_object_counts": {
                    name: len(records) for name, records in objects.items()
                },
                "relations": len(handle.source_relations()),
                "reachable_actions": len(handle.reachable_actions()),
                "table_row": row is not None,
                "table_pre_state_verified": (
                    lookup.verify_pre_state(row, handle) if row is not None else None
                ),
                "sample_forks_checked": sample_checked,
                "sample_forks_agreed": sample_agreed,
            }
        )
    return {"env": env, "guid": guid, "results": results}


def validate(jobs: int) -> dict[str, Any]:
    inventory = json.loads(INVENTORY.read_text())
    by_session: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for case in inventory["cases"]:
        by_session.setdefault((case["env"], case["guid"]), []).append(
            {
                "case_id": case["case_id"],
                "step": case["query"]["step"],
                "action_id": case["query"]["action_class"],
                "action_data": {},
            }
        )
    # recover exact recorded action data (ACTION6 coordinates) from the recordings
    for (env, guid), cases in by_session.items():
        steps = {case["step"]: case for case in cases}
        path = CORPUS / env / f"{guid}.recording.jsonl"
        for recorded in iter_recorded_actions(path):
            case = steps.get(recorded.step)
            if case is not None:
                case["action_id"] = recorded.action_id
                case["action_data"] = dict(recorded.action_data)

    sample_sessions = {}
    for (env, guid), cases in sorted(by_session.items()):
        marker = hashlib.sha256(f"es-state-sample:{env}:{guid}".encode()).hexdigest()
        sample_sessions.setdefault(env, []).append((marker, guid))
    sample_pick = {
        env: min(entries)[1] for env, entries in sample_sessions.items()
    }

    jobs_list = []
    for (env, guid), cases in sorted(by_session.items()):
        sample = sample_pick[env] == guid
        jobs_list.append(
            {
                "env": env,
                "guid": guid,
                "cases": sorted(cases, key=lambda case: case["step"]),
                "sample": sample,
                "sample_step": min(case["step"] for case in cases) if sample else None,
            }
        )

    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        worker_results = list(pool.map(_validate_worker, jobs_list))

    per_game: dict[str, Any] = {}
    all_ok = True
    for chunk in worker_results:
        env = chunk["env"]
        game = per_game.setdefault(
            env,
            {
                "cases": 0,
                "completing_action_completes": 0,
                "table_rows": 0,
                "table_pre_state_verified": 0,
                "sample_forks_checked": 0,
                "sample_forks_agreed": 0,
                "min_reachable_actions": None,
                "source_sets": {},
            },
        )
        for result in chunk["results"]:
            game["cases"] += 1
            game["completing_action_completes"] += result["completing_action_completes"]
            game["table_rows"] += bool(result["table_row"])
            game["table_pre_state_verified"] += bool(result["table_pre_state_verified"])
            game["sample_forks_checked"] += result["sample_forks_checked"]
            game["sample_forks_agreed"] += result["sample_forks_agreed"]
            reach = result["reachable_actions"]
            if game["min_reachable_actions"] is None or reach < game["min_reachable_actions"]:
                game["min_reachable_actions"] = reach
            for name, count in result["source_object_counts"].items():
                bounds = game["source_sets"].setdefault(name, [count, count])
                bounds[0] = min(bounds[0], count)
                bounds[1] = max(bounds[1], count)
            if not result["completing_action_completes"]:
                all_ok = False
        if game["sample_forks_checked"] != game["sample_forks_agreed"]:
            all_ok = False

    lookup = ForkTableLookup()
    document = {
        "format_version": FORMAT_VERSION,
        "generated_by": "agent/harness/es_sources/state_access.py",
        "inputs": {
            "logs/es_inventory.json": inventory["fingerprint"],
            **lookup.digests,
        },
        "per_game": per_game,
        "totals": {
            "cases": sum(g["cases"] for g in per_game.values()),
            "completing_action_completes": sum(
                g["completing_action_completes"] for g in per_game.values()
            ),
            "table_rows": sum(g["table_rows"] for g in per_game.values()),
            "table_pre_state_verified": sum(
                g["table_pre_state_verified"] for g in per_game.values()
            ),
            "sample_forks_checked": sum(
                g["sample_forks_checked"] for g in per_game.values()
            ),
            "sample_forks_agreed": sum(
                g["sample_forks_agreed"] for g in per_game.values()
            ),
        },
        "all_ok": all_ok,
    }
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--jobs", type=int, default=6)
    args = parser.parse_args()
    if not args.validate:
        parser.error("state_access is a library; run with --validate")
    document = validate(args.jobs)
    OUTPUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    totals = document["totals"]
    print(
        f"cases {totals['cases']}: completing-action completes "
        f"{totals['completing_action_completes']}/{totals['cases']}; table rows "
        f"{totals['table_rows']} (pre-state verified {totals['table_pre_state_verified']}); "
        f"sample forks {totals['sample_forks_agreed']}/{totals['sample_forks_checked']} agree"
    )
    print(f"all_ok={document['all_ok']}; wrote {OUTPUT.relative_to(ROOT)}")
    return 0 if document["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
