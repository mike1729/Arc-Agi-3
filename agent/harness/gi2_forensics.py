#!/usr/bin/env python3
"""Forensic characterization of the Sprint A representability and fidelity failures.

Exploratory diagnostic, commissioned 2026-07-30 after the predeclared 5/6 representability
gate failed.  This module changes no gate verdict: it classifies the four unmapped entities
and the vc33 replay divergence so the routing decision (remediate once vs. stop) is made on
measured causes rather than summaries.

Run:
  .venv/bin/python agent/harness/gi2_forensics.py --build
  .venv/bin/python agent/harness/gi2_forensics.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from gi2_grounding import projected_sprite_cells, semantic_sprites
from gi2_observation import Tracker
from gi2_replay import ReplayDriver, iter_recorded_actions
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, frame_roles, selected_sessions

GROUNDING = ROOT / "logs/gi2_grounding_annotations_iteration.json"
FIDELITY = ROOT / "logs/gi2_replay_fidelity.json"
OUTPUT = ROOT / "logs/gi2_grounding_forensics.json"
FORMAT_VERSION = 1
GRID = 64


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entity_digest(game: Any, set_name: str, index: int, sprite: Any) -> str:
    return hashlib.sha256(
        f"{game.level_index}:{set_name}:{index}:{sprite.name}".encode()
    ).hexdigest()[:16]


def unmapped_entities(grounding: dict[str, Any]) -> dict[str, tuple[str, set[str]]]:
    """(env -> (set_name, digests)) for entities never mapped in any session."""
    result: dict[str, tuple[str, set[str]]] = {}
    for game in grounding["games"]:
        by_entity: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for session in game["sessions"]:
            for item in session["track_groundings"]:
                by_entity.setdefault(
                    (item["set"], item["source_object_digest"]), []
                ).append(item)
        failing: dict[str, set[str]] = {}
        for (set_name, digest), items in by_entity.items():
            if not any(item["mapped"] for item in items):
                failing.setdefault(set_name, set()).add(digest)
        if failing:
            if len(failing) != 1:
                raise ValueError(f"{game['env']}: expected one failing set, got {failing}")
            set_name, digests = next(iter(failing.items()))
            result[game["env"]] = (set_name, digests)
    return result


def _flood_nonbackground(grid: list, seeds: set, background: int) -> set:
    seen: set[tuple[int, int]] = set()
    stack = [cell for cell in seeds if grid[cell[0]][cell[1]] != background]
    while stack:
        row, col = stack.pop()
        if (row, col) in seen or not (0 <= row < GRID and 0 <= col < GRID):
            continue
        if grid[row][col] == background:
            continue
        seen.add((row, col))
        stack.extend([(row + 1, col), (row - 1, col), (row, col + 1), (row, col - 1)])
    return seen


def entity_forensics(env: str, set_name: str, digests: set[str]) -> list[dict[str, Any]]:
    """Characterize each unmapped entity at its first observed state (rank-0 session)."""
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    selected = selected_sessions(env, sessions_doc, draw)[0]
    path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
    driver = ReplayDriver(env)
    game = driver.new_game()
    tracker = Tracker()
    previous_grid = None
    previous_observation = None
    previous_levels = 0
    reports: dict[str, dict[str, Any]] = {}
    for action in iter_recorded_actions(path):
        if previous_grid is not None and previous_observation is not None:
            for index, sprite in enumerate(semantic_sprites(env, game)[set_name]):
                digest = _entity_digest(game, set_name, index, sprite)
                if digest not in digests or digest in reports:
                    continue
                grid = previous_grid
                background = Counter(
                    grid[row][col] for row in range(GRID) for col in range(GRID)
                ).most_common(1)[0][0]
                projected = projected_sprite_cells(game, sprite)
                visible = {
                    (row, col)
                    for row, col, colour in projected
                    if int(grid[row][col]) == colour
                }
                intersecting = []
                pure_union: set[tuple[int, int]] = set()
                for handle in previous_observation.handles:
                    cells = handle.component.cells
                    overlap = visible & cells
                    if not overlap:
                        continue
                    purity = len(overlap) / len(cells)
                    intersecting.append(
                        {
                            "color": handle.component.color,
                            "component_pixels": len(cells),
                            "overlap": len(overlap),
                            "purity": round(purity, 6),
                        }
                    )
                    if purity >= 0.5:
                        pure_union |= cells
                region = _flood_nonbackground(grid, visible, background)
                reports[digest] = {
                    "entity": digest,
                    "level_index": game.level_index,
                    "projected_pixels": len(projected),
                    "visible_pixels": len(visible),
                    "background_color": background,
                    "intersecting_components": sorted(
                        intersecting,
                        key=lambda item: (-item["overlap"], item["color"]),
                    ),
                    "pure_components_partition_sprite": pure_union == visible
                    and bool(visible),
                    "connected_nonbackground_region_pixels": len(region),
                    "region_equals_sprite": region == visible,
                    "region_colors": {
                        str(colour): count
                        for colour, count in sorted(
                            Counter(grid[r][c] for r, c in region).items()
                        )
                    },
                }
        roles = frame_roles(
            state=action.state,
            n_frames=len(action.frames),
            completion_increment=action.levels_completed - previous_levels,
        )
        driver.perform(game, action)
        for grid, role in zip(action.frames, roles):
            if role not in {"settled", "solved_terminal", "next_level_initial"}:
                continue
            if role == "next_level_initial":
                tracker.reset_level()
                previous_grid = None
            previous_observation = tracker.update(
                grid,
                previous_grid=previous_grid,
                action_id=action.action_id,
                action_data=action.action_data,
            )
            previous_grid = grid
        previous_levels = action.levels_completed
        if set(reports) == digests:
            break
    if set(reports) != digests:
        raise ValueError(f"{env}: did not observe all unmapped entities")
    return [reports[digest] for digest in sorted(digests)]


def vc33_divergence() -> list[dict[str, Any]]:
    """Replay all vc33 sessions and characterize every divergent action row."""
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    driver = ReplayDriver("vc33")
    sessions = []
    for selected in selected_sessions("vc33", sessions_doc, draw):
        path = CORPUS / "vc33" / f"{selected['guid']}.recording.jsonl"
        game = driver.new_game()
        divergent_rows = []
        previous_levels = 0
        for action in iter_recorded_actions(path):
            response = driver.perform(game, action)
            replayed = [
                frame.tolist() if hasattr(frame, "tolist") else frame
                for frame in (response.frame or [])
            ]
            roles = frame_roles(
                state=action.state,
                n_frames=len(action.frames),
                completion_increment=action.levels_completed - previous_levels,
            )
            previous_levels = action.levels_completed
            if replayed == action.frames:
                continue
            if len(replayed) != len(action.frames):
                divergent_rows.append(
                    {"step": action.step, "kind": "frame_count_mismatch"}
                )
                continue
            frame_reports = []
            colour_pairs: Counter[str] = Counter()
            role_mismatches = []
            for frame_index, (got, want) in enumerate(zip(replayed, action.frames)):
                cells = [
                    (row, col)
                    for row in range(GRID)
                    for col in range(GRID)
                    if got[row][col] != want[row][col]
                ]
                if not cells:
                    continue
                for row, col in cells:
                    colour_pairs[f"{want[row][col]}->{got[row][col]}"] += 1
                frame_reports.append(
                    {"frame_index": frame_index, "changed_cells": len(cells)}
                )
                role = roles[frame_index] if frame_index < len(roles) else "?"
                if role != "intermediate":
                    role_mismatches.append(role)
            divergent_rows.append(
                {
                    "step": action.step,
                    "action_id": action.action_id,
                    "completion_increment_to": action.levels_completed,
                    "n_frames": len(action.frames),
                    "divergent_frames": frame_reports,
                    "colour_substitutions": dict(colour_pairs),
                    "non_intermediate_roles_divergent": role_mismatches,
                }
            )
        sessions.append(
            {
                "guid": selected["guid"],
                "divergent_rows": divergent_rows,
                "n_divergent_rows": len(divergent_rows),
                "all_divergence_intermediate_only": all(
                    not row.get("non_intermediate_roles_divergent", True)
                    for row in divergent_rows
                ),
            }
        )
    return sessions


def metadata_mismatch_summary(fidelity: dict[str, Any]) -> dict[str, Any]:
    summary = {}
    for game in fidelity["games"]:
        rows = {}
        for session in game["sessions"]:
            for name, count in (session.get("metadata_mismatches") or {}).items():
                rows[name] = rows.get(name, 0) + count
        if rows:
            summary[game["env"]] = rows
    return summary


def build() -> dict[str, Any]:
    grounding = json.loads(GROUNDING.read_text())
    fidelity = json.loads(FIDELITY.read_text())
    failing = unmapped_entities(grounding)
    entity_reports = {
        env: {
            "set": set_name,
            "entities": entity_forensics(env, set_name, digests),
        }
        for env, (set_name, digests) in sorted(failing.items())
    }
    return {
        "format_version": FORMAT_VERSION,
        "status": "exploratory_forensics",
        "scope": "iteration",
        "commissioned": "operator, 2026-07-30, after the representability stop",
        "inputs": {
            "grounding_sha256": _sha256(GROUNDING),
            "fidelity_sha256": _sha256(FIDELITY),
        },
        "unmapped_entity_forensics": entity_reports,
        "vc33_divergence": vc33_divergence(),
        "metadata_mismatches": metadata_mismatch_summary(fidelity),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.build:
        document = build()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        for env, report in document["unmapped_entity_forensics"].items():
            for entity in report["entities"]:
                print(
                    f"{env}/{report['set']}/{entity['entity']}: "
                    f"region_equals_sprite={entity['region_equals_sprite']} "
                    f"partitioned_by_pure_components="
                    f"{entity['pure_components_partition_sprite']} "
                    f"components={len(entity['intersecting_components'])}"
                )
        for session in document["vc33_divergence"]:
            print(
                f"vc33/{session['guid'][:8]}: divergent_rows={session['n_divergent_rows']} "
                f"intermediate_only={session['all_divergence_intermediate_only']}"
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            current = json.loads(OUTPUT.read_text())
            problems = [] if current == build() else ["artifact differs from rebuild"]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 forensics FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 forensics OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
