#!/usr/bin/env python3
"""GI-2 A3 source-authored gold to observable-handle grounding.

The environment source is used only to identify the semantic objects named by the frozen
GIDSL gold.  A source sprite is projected into display coordinates and then matched to A2
same-colour components in the *recorded* pre-completion frame.  The output contains only
observable track IDs and measured coverage/purity; source names and tags never enter the
candidate generator.

Run:
  .venv/bin/python agent/harness/gi2_grounding.py --build
  .venv/bin/python agent/harness/gi2_grounding.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from gi2_observation import Observation, Tracker, local_compact_groups
from gi2_replay import ReplayDriver, iter_recorded_actions
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, frame_roles, selected_sessions

GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
FIDELITY = ROOT / "logs/gi2_replay_fidelity.json"
OUTPUT = ROOT / "logs/gi2_grounding_annotations_iteration.json"
FORMAT_VERSION = 1

M0R0_MOVERS = {
    "pikgci-toljda-leklkn",
    "pikgci-toljda-rivmdg",
    "pikgci-boweok-leklkn",
    "pikgci-boweok-rivmdg",
}

# Gold-authoring selectors.  They are deliberately isolated from the measured descriptor
# registry in gi2_version_space.py.
SOURCE_SELECTORS = {
    "dc22": {
        "players": "attribute:qnnpcoyzd",
        "goal_tiles": "attribute:hfuqkxulm",
    },
    "ft09": {"clues": "attribute:gig"},
    "ls20": {
        "goal_tiles": "attribute:plrpelhym",
        "avatars": "attribute:gudziatsk",
    },
    "m0r0": {"active_movers": "active sprite names in frozen four-name family"},
    "tu93": {
        "movers": "tag:0017unajnymcki",
        "exits": "tag:0015msvpvzxhqf",
    },
    "vc33": {
        "falling_items": "tag:0016uciqlhjlom",
        "receptacles": "tag:0010gnulkywfpz",
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value is not None else []


def semantic_sprites(env: str, game: Any) -> dict[str, list[Any]]:
    if env == "dc22":
        return {
            "players": _as_list(game.qnnpcoyzd),
            "goal_tiles": _as_list(game.hfuqkxulm),
        }
    if env == "ft09":
        return {"clues": list(game.gig)}
    if env == "ls20":
        return {
            "goal_tiles": list(game.plrpelhym),
            "avatars": _as_list(game.gudziatsk),
        }
    if env == "m0r0":
        consumed = set(game.okpvcjupabr)
        return {
            "active_movers": [
                sprite
                for sprite in game.current_level.get_sprites()
                if sprite.name in M0R0_MOVERS and sprite.name not in consumed
            ]
        }
    if env == "tu93":
        return {
            "movers": game.current_level.get_sprites_by_tag("0017unajnymcki"),
            "exits": game.current_level.get_sprites_by_tag("0015msvpvzxhqf"),
        }
    if env == "vc33":
        return {
            "falling_items": game.current_level.get_sprites_by_tag("0016uciqlhjlom"),
            "receptacles": game.current_level.get_sprites_by_tag("0010gnulkywfpz"),
        }
    raise ValueError(f"unsupported iteration game {env!r}")


def projected_sprite_cells(game: Any, sprite: Any) -> set[tuple[int, int, int]]:
    """Return visible-capable (row, col, colour) cells in 64x64 display coordinates."""
    camera = game.camera
    pixels = sprite.render()
    scale, x_offset, y_offset = camera._calculate_scale_and_offset()
    cells: set[tuple[int, int, int]] = set()
    for local_row in range(pixels.shape[0]):
        for local_col in range(pixels.shape[1]):
            colour = int(pixels[local_row, local_col])
            if colour < 0:
                continue
            world_col = sprite.x + local_col
            world_row = sprite.y + local_row
            view_col = world_col - camera.x
            view_row = world_row - camera.y
            if not (0 <= view_col < camera.width and 0 <= view_row < camera.height):
                continue
            for drow in range(scale):
                for dcol in range(scale):
                    cells.add(
                        (
                            y_offset + view_row * scale + drow,
                            x_offset + view_col * scale + dcol,
                            colour,
                        )
                    )
    return cells


def _map_sprite(
    game: Any,
    sprite: Any,
    grid: list,
    observation: Observation,
    *,
    identity: str | None = None,
) -> dict[str, Any]:
    projected = projected_sprite_cells(game, sprite)
    # Only pixels that survive layer composition are observable in this frame.
    visible = {
        (row, col)
        for row, col, colour in projected
        if 0 <= row < len(grid)
        and 0 <= col < len(grid[row])
        and int(grid[row][col]) == colour
    }
    overlaps = []
    covered: set[tuple[int, int]] = set()
    for handle in observation.handles:
        intersection = visible & handle.component.cells
        if not intersection:
            continue
        purity = len(intersection) / len(handle.component.cells)
        # A component mostly outside the sprite is a coincident background region, not a
        # grounding.  This threshold is fixed before inspecting A3 results.
        if purity < 0.5:
            continue
        overlaps.append(
            {
                "handle": handle.track_id,
                "intersection": len(intersection),
                "component_pixels": handle.component.pixels,
                "purity": round(purity, 6),
            }
        )
        covered.update(intersection)
    handle_ids = sorted(item["handle"] for item in overlaps)
    group_ids = sorted(
        group.group_id
        for group in observation.groups
        if set(group.members) == set(handle_ids)
    )
    coverage = len(covered) / len(visible) if visible else 0.0
    source_object_digest = hashlib.sha256(
        (identity or f"{sprite.name}:{sprite.x}:{sprite.y}").encode()
    ).hexdigest()[:16]
    has_object_handle = len(handle_ids) == 1 or bool(group_ids)
    return {
        "source_object_digest": source_object_digest,
        "projected_pixels": len(projected),
        "observable_pixels": len(visible),
        "covered_pixels": len(covered),
        "coverage": round(coverage, 6),
        "handles": handle_ids,
        "matching_groups": group_ids,
        "mapped": has_object_handle and coverage >= 0.8,
        "component_covered": bool(handle_ids) and coverage >= 0.8,
    }


def _observable_registry(observation: Observation) -> list[dict[str, Any]]:
    by_id = {handle.track_id: handle for handle in observation.handles}
    objects = []
    for handle in observation.handles:
        component = handle.component
        objects.append(
            {
                "id": handle.track_id,
                "kind": "atomic",
                "members": [handle.track_id],
                "colors": [component.color],
                "shapes": [component.shape],
                "pixels": component.pixels,
                "bbox": list(component.bbox),
                "centroid": list(component.centroid),
                "cells": [list(cell) for cell in sorted(component.cells)],
                "role": handle.role,
            }
        )
    for group in observation.groups:
        members = [by_id[member] for member in group.members]
        cells = set().union(*(member.component.cells for member in members))
        rows = [row for row, _ in cells]
        cols = [col for _, col in cells]
        objects.append(
            {
                "id": group.group_id,
                "kind": "group",
                "members": list(group.members),
                "colors": sorted({member.component.color for member in members}),
                "shapes": sorted(member.component.shape for member in members),
                "pixels": len(cells),
                "bbox": [min(rows), min(cols), max(rows), max(cols)],
                "centroid": list(group.representative),
                "role": sorted({member.role for member in members}),
            }
        )
    return objects


def _observable_registry_summary(observation: Observation) -> dict[str, Any]:
    concise = [
        {
            "id": handle.track_id,
            "color": handle.component.color,
            "shape": handle.component.shape,
            "pixels": handle.component.pixels,
            "bbox": handle.component.bbox,
            "role": handle.role,
        }
        for handle in observation.handles
    ] + [
        {"id": group.group_id, "members": group.members}
        for group in observation.groups
    ]
    return {
        "atomic_handles": len(observation.handles),
        "group_handles": len(observation.groups),
        "registry_sha256": hashlib.sha256(
            json.dumps(concise, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _checkpoint_mapping(
    env: str,
    game: Any,
    grid: list,
    observation: Observation,
) -> tuple[dict[str, list[dict[str, Any]]], Observation]:
    semantic = semantic_sprites(env, game)
    initial_sets = {
        set_name: [
            _map_sprite(
                game,
                sprite,
                grid,
                observation,
                identity=f"{game.level_index}:{set_name}:{index}:{sprite.name}",
            )
            for index, sprite in enumerate(sprites)
        ]
        for set_name, sprites in semantic.items()
    }
    needs_checkpoint_groups = any(
        item["component_covered"] and len(item["handles"]) > 1
        for members in initial_sets.values()
        for item in members
    )
    checkpoint_groups = {group.members: group for group in observation.groups}
    if needs_checkpoint_groups:
        checkpoint_groups.update(
            {
                group.members: group
                for group in local_compact_groups(observation.handles)
            }
        )
    checkpoint = Observation(
        handles=observation.handles,
        groups=list(checkpoint_groups.values()),
        events=observation.events,
        changed_regions=observation.changed_regions,
        mouse_representatives=observation.mouse_representatives,
    )
    sets = {
        set_name: [
            _map_sprite(
                game,
                sprite,
                grid,
                checkpoint,
                identity=f"{game.level_index}:{set_name}:{index}:{sprite.name}",
            )
            for index, sprite in enumerate(sprites)
        ]
        for set_name, sprites in semantic.items()
    }
    return sets, checkpoint


def annotate_session(env: str, selected: dict[str, Any]) -> dict[str, Any]:
    path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
    driver = ReplayDriver(env)
    game = driver.new_game()
    tracker = Tracker()
    previous_grid = None
    previous_observation = None
    previous_levels = 0
    rows = []
    track_groundings: dict[tuple[str, str], dict[str, Any]] = {}
    for action in iter_recorded_actions(path):
        if previous_grid is not None and previous_observation is not None:
            semantic = semantic_sprites(env, game)
            new_identity = any(
                (
                    set_name,
                    hashlib.sha256(
                        f"{game.level_index}:{set_name}:{index}:{sprite.name}".encode()
                    ).hexdigest()[:16],
                )
                not in track_groundings
                for set_name, sprites in semantic.items()
                for index, sprite in enumerate(sprites)
            )
            if new_identity:
                first_sets, _ = _checkpoint_mapping(
                    env, game, previous_grid, previous_observation
                )
                for set_name, members in first_sets.items():
                    for item in members:
                        track_groundings.setdefault(
                            (set_name, item["source_object_digest"]), item
                        )
        if action.levels_completed > previous_levels:
            if previous_grid is None or previous_observation is None:
                raise ValueError(f"{env}/{selected['guid']}: completion lacks pre-state")
            sets, checkpoint_observation = _checkpoint_mapping(
                env, game, previous_grid, previous_observation
            )
            for set_name, members in sets.items():
                for item in members:
                    key = (set_name, item["source_object_digest"])
                    incumbent = track_groundings.get(key)
                    if incumbent is None or (
                        item["mapped"],
                        item["coverage"],
                    ) > (
                        incumbent["mapped"],
                        incumbent["coverage"],
                    ):
                        track_groundings[key] = item
            extensions = {
                set_name: [
                    (
                        item["handles"][0]
                        if len(item["handles"]) == 1
                        else item["matching_groups"][0]
                    )
                    for item in members
                    if item["mapped"]
                ]
                for set_name, members in sets.items()
            }
            rows.append(
                {
                    "step": action.step,
                    "level": action.levels_completed,
                    "sets": sets,
                    "gold_extensions": extensions,
                    "observable_registry": _observable_registry_summary(
                        checkpoint_observation
                    ),
                    "all_objects_mapped": all(
                        item["mapped"]
                        for members in sets.values()
                        for item in members
                    ),
                }
            )

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
        # Once a prefix diverges, source state is no longer a valid authoring oracle.  Keep
        # tracking the recorded frames, but do not author later completion annotations.
        frames_match = replayed == action.frames
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
        if not frames_match:
            break
    return {
        **selected,
        "recording": str(path.relative_to(ROOT)),
        "completion_states": rows,
        "annotated_completions": len(rows),
        "track_groundings": [
            {"set": set_name, **item}
            for (set_name, _), item in sorted(track_groundings.items())
        ],
    }


def _set_summary(session_rows: Iterable[dict[str, Any]], set_name: str) -> dict[str, Any]:
    observations = [
        item
        for session in session_rows
        for completion in session["completion_states"]
        for item in completion["sets"].get(set_name, [])
    ]
    by_entity: dict[str, list[dict[str, Any]]] = {}
    for session in session_rows:
        for item in session["track_groundings"]:
            if item["set"] == set_name:
                by_entity.setdefault(item["source_object_digest"], []).append(item)
    return {
        "observations": len(observations),
        "mapped_observations": sum(item["mapped"] for item in observations),
        "entities": len(by_entity),
        "mapped_entities": sum(
            any(item["mapped"] for item in items) for items in by_entity.values()
        ),
        "min_observed_coverage": min(
            (item["coverage"] for item in observations), default=None
        ),
        "all_mapped": bool(by_entity)
        and all(any(item["mapped"] for item in items) for items in by_entity.values()),
    }


def build() -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    gold = {row["env"]: row for row in json.loads(GOLD.read_text())["records"]}
    games = []
    for env in draw["iteration"]:
        sessions = [
            annotate_session(env, selected)
            for selected in selected_sessions(env, sessions_doc, draw)
        ]
        set_names = gold[env]["vocabulary"]["sets"]
        summaries = {
            set_name: _set_summary(sessions, set_name) for set_name in set_names
        }
        games.append(
            {
                "env": env,
                "source_selectors": SOURCE_SELECTORS[env],
                "sessions": sessions,
                "sets": summaries,
                "representable": all(item["all_mapped"] for item in summaries.values()),
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a3_gold_authored",
        "scope": "iteration",
        "inputs": {
            "gold_sha256": _sha256(GOLD),
            "fidelity_sha256": _sha256(FIDELITY),
        },
        "mapping_rule": {
            "source_use": "answer-key authoring only",
            "observable_target": "A2 same-colour component handles",
            "component_purity_min": 0.5,
            "sprite_visible_coverage_min": 0.8,
            "multi_component": "exact A2 group recorded when available",
        },
        "games": games,
        "summary": {
            "representable_games": sum(game["representable"] for game in games),
            "total_games": len(games),
        },
    }


def verify(document: dict[str, Any]) -> list[str]:
    problems = []
    if document.get("format_version") != FORMAT_VERSION:
        problems.append("format_version mismatch")
    if document.get("status") != "a3_gold_authored":
        problems.append("status mismatch")
    if document.get("inputs", {}).get("gold_sha256") != _sha256(GOLD):
        problems.append("gold digest mismatch")
    envs = [game.get("env") for game in document.get("games", [])]
    expected = json.loads(DRAW.read_text())["iteration"]
    if envs != expected:
        problems.append(f"game order mismatch: expected {expected}, got {envs}")
    rebuilt = build()
    if document != rebuilt:
        problems.append("artifact differs from deterministic rebuild")
    return problems


def compact_legacy_document(document: dict[str, Any]) -> dict[str, Any]:
    for game in document["games"]:
        for session in game["sessions"]:
            for state in session["completion_states"]:
                registry = state["observable_registry"]
                if isinstance(registry, dict):
                    continue
                concise = []
                atomic = 0
                groups = 0
                for item in registry:
                    if item["kind"] == "atomic":
                        atomic += 1
                        concise.append(
                            {
                                "id": item["id"],
                                "color": item["colors"][0],
                                "shape": item["shapes"][0],
                                "pixels": item["pixels"],
                                "bbox": item["bbox"],
                                "role": item["role"],
                            }
                        )
                    else:
                        groups += 1
                        concise.append({"id": item["id"], "members": item["members"]})
                state["observable_registry"] = {
                    "atomic_handles": atomic,
                    "group_handles": groups,
                    "registry_sha256": hashlib.sha256(
                        json.dumps(
                            concise, sort_keys=True, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                }
    return document


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--compact-legacy", action="store_true")
    args = parser.parse_args()
    if args.compact_legacy:
        document = compact_legacy_document(json.loads(OUTPUT.read_text()))
        OUTPUT.write_text(json.dumps(document, separators=(",", ":")) + "\n")
        print(f"compacted {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.build:
        document = build()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        for game in document["games"]:
            print(
                f"{game['env']}: representable={game['representable']} "
                + ", ".join(
                    f"{name}={value['mapped_entities']}/{value['entities']} entities"
                    for name, value in game["sets"].items()
                )
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            document = json.loads(OUTPUT.read_text())
            problems = verify(document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 grounding annotations FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 grounding annotations OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
