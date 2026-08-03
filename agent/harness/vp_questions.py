#!/usr/bin/env python3
"""Frozen VP1/VP2 question generation, rendering, and answerability audit.

The emitted JSON contains references and mechanical gold, never rendered image bytes.  Runtime
rendering rebuilds the selected replay frames and uses the vendored ARC palette/nearest-neighbor
renderer.  Reserved and one-shot games cannot enter through ``selected_sessions``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gi1_render import _vision_context, format_grid_ascii  # noqa: E402
from gi2_observation import Observation, Tracker, changed_regions  # noqa: E402
from gi2_traces import (  # noqa: E402
    CORPUS,
    DRAW,
    ROLE_NEXT_LEVEL_INITIAL,
    ROLE_SETTLED,
    ROLE_SOLVED_TERMINAL,
    ROOT,
    SESSIONS,
    _sha256,
    iter_trace,
    selected_sessions,
)

OUTPUT = ROOT / "logs/vp_questions.json"
FORMAT_VERSION = 1
GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")
ARMS = ("I-4", "I-8", "I-16", "I-A", "I-H", "I-C")
SCALES = {"I-4": 4, "I-8": 8, "I-16": 16, "I-H": 16, "I-C": 8}
VP1_BOARDS_PER_GAME = 8
VP2_PAIRS_PER_GAME = 24
SEMANTIC_PER_FAMILY_GAME = 6
MAX_REGIONS = 12
PALETTE_PERMUTATIONS = {
    # Rotations stay inside luminance bands; white/black anchors remain fixed.
    "perm-1": {0: 0, 1: 10, 2: 7, 3: 6, 4: 13, 5: 5, 6: 8, 7: 9,
               8: 15, 9: 12, 10: 11, 11: 1, 12: 14, 13: 4, 14: 2, 15: 3},
    "perm-2": {0: 0, 1: 11, 2: 14, 3: 15, 4: 13, 5: 5, 6: 3, 7: 2,
               8: 6, 9: 7, 10: 1, 11: 10, 12: 9, 13: 4, 14: 12, 15: 8},
}

COLOR_NAMES = {
    0: "white", 1: "light_gray", 2: "gray", 3: "dark_gray", 4: "charcoal",
    5: "black", 6: "magenta", 7: "pink", 8: "red", 9: "blue",
    10: "light_blue", 11: "yellow", 12: "orange", 13: "maroon",
    14: "green", 15: "purple",
}
PIXEL_BANDS = ((0, 0, "0"), (1, 4, "1-4"), (5, 16, "5-16"),
               (17, 64, "17-64"), (65, 256, "65-256"),
               (257, 1024, "257-1024"), (1025, 4096, "1025-4096"))
COMPONENT_BANDS = ((0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 4, "3-4"),
                   (5, 8, "5-8"), (9, 16, "9-16"), (17, 32, "17-32"),
                   (33, 4096, "33+"))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _stable_key(*parts: Any) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()


def _band(value: int, bands: tuple[tuple[int, int, str], ...]) -> str:
    return next(label for low, high, label in bands if low <= value <= high)


def _modal(grid: list[list[int]]) -> int:
    counts = Counter(cell for row in grid for cell in row)
    return min(counts, key=lambda value: (-counts[value], value))


def _component_counts(grid: list[list[int]]) -> Counter[int]:
    remaining = {(r, c) for r in range(64) for c in range(64)}
    counts: Counter[int] = Counter()
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        value = grid[start[0]][start[1]]
        stack = [start]
        while stack:
            row, col = stack.pop()
            for neighbor in ((row - 1, col), (row + 1, col),
                             (row, col - 1), (row, col + 1)):
                if neighbor in remaining and grid[neighbor[0]][neighbor[1]] == value:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        counts[value] += 1
    return counts


def _bbox(cells: Iterable[tuple[int, int]]) -> tuple[int, int, int, int]:
    cells = tuple(cells)
    return (min(r for r, _ in cells), min(c for _, c in cells),
            max(r for r, _ in cells), max(c for _, c in cells))


def _expanded(box: tuple[int, int, int, int], amount: int = 1) -> tuple[int, int, int, int]:
    return (box[0] - amount, box[1] - amount, box[2] + amount, box[3] + amount)


def _boxes_overlap(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> bool:
    return not (left[2] < right[0] or right[2] < left[0]
                or left[3] < right[1] or right[3] < left[1])


def _frame_for(step, roles: tuple[str, ...]) -> list | None:
    for role in roles:
        for frame in step.frames:
            if frame.role == role:
                return frame.grid
    return None


def _objects(observation: Observation) -> list[dict[str, Any]]:
    objects = []
    by_track = {handle.track_id: handle for handle in observation.handles}
    for handle in observation.handles:
        component = handle.component
        objects.append({
            "key": handle.track_id,
            "kind": "atomic",
            "bbox": list(component.bbox),
            "palette": [component.color],
            "signature": component.shape,
        })
    for group in observation.groups:
        members = [by_track[item] for item in group.members if item in by_track]
        if len(members) != len(group.members) or len(members) < 2:
            continue
        cells = set().union(*(member.component.cells for member in members))
        if not cells or len(cells) > 512:
            continue
        rows = [row for row, _ in cells]
        cols = [col for _, col in cells]
        min_row, min_col = min(rows), min(cols)
        height = max(rows) - min_row + 1
        width = max(cols) - min_col + 1
        normalized = sorted((row - min_row, col - min_col) for row, col in cells)
        palette = sorted({member.component.color for member in members})
        objects.append({
            "key": group.group_id,
            "kind": "group",
            "bbox": list(_bbox(cells)),
            "palette": palette,
            "signature": _digest([palette, height, width, normalized])[:16],
        })
    return objects


@dataclass
class CorpusIndex:
    frames: dict[str, list]
    pairs: dict[str, dict[str, Any]]
    session_pairs: dict[tuple[str, str], list[str]]
    session_changed_cells: dict[tuple[str, str], set[tuple[int, int]]]
    recording_hashes: dict[str, str]


def build_corpus_index() -> CorpusIndex:
    sessions_doc = json.loads(SESSIONS.read_text())
    draw_doc = json.loads(DRAW.read_text())
    frames: dict[str, list] = {}
    pairs: dict[str, dict[str, Any]] = {}
    session_pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    changed_by_session: dict[tuple[str, str], set[tuple[int, int]]] = defaultdict(set)
    recording_hashes = {}
    object_cache: dict[str, list[dict[str, Any]]] = {}

    for env in GAMES:
        for session_index, selected in enumerate(selected_sessions(env, sessions_doc, draw_doc)):
            guid = selected["guid"]
            path = CORPUS / env / f"{guid}.recording.jsonl"
            rel = str(path.relative_to(ROOT))
            recording_hashes[rel] = _sha256(path)
            tracker = Tracker()
            baseline_grid = None
            baseline_obs = None
            baseline_key = None
            baseline_level = 1
            for step in iter_trace(path):
                settled = _frame_for(step, (ROLE_SETTLED, ROLE_SOLVED_TERMINAL))
                if step.action_id == 0 or step.full_reset:
                    if settled is not None:
                        tracker.reset_level()
                        obs = tracker.update(settled, previous_grid=None,
                                             action_id=step.action_id,
                                             action_data=step.action_data)
                        key = f"{env}:{guid}:{step.index}:settled"
                        frames[key] = settled
                        object_cache[key] = _objects(obs)
                        baseline_grid, baseline_obs, baseline_key = settled, obs, key
                        baseline_level = step.levels_completed + 1
                    continue

                if step.is_completion:
                    if settled is not None and baseline_grid is not None:
                        tracker.update(settled, previous_grid=baseline_grid,
                                       action_id=step.action_id, action_data=step.action_data)
                    next_grid = _frame_for(step, (ROLE_NEXT_LEVEL_INITIAL,))
                    if next_grid is not None:
                        tracker.reset_level()
                        obs = tracker.update(next_grid, previous_grid=None,
                                             action_id=step.action_id,
                                             action_data=step.action_data)
                        key = f"{env}:{guid}:{step.index}:next"
                        frames[key] = next_grid
                        object_cache[key] = _objects(obs)
                        baseline_grid, baseline_obs, baseline_key = next_grid, obs, key
                        baseline_level = step.levels_completed + 1
                    else:
                        baseline_grid = baseline_obs = baseline_key = None
                    continue

                if settled is None:
                    continue
                after_obs = tracker.update(settled, previous_grid=baseline_grid,
                                           action_id=step.action_id,
                                           action_data=step.action_data)
                after_key = f"{env}:{guid}:{step.index}:settled"
                frames[after_key] = settled
                object_cache[after_key] = _objects(after_obs)
                if baseline_grid is not None and baseline_obs is not None and baseline_key:
                    diff = {(row, col)
                            for row in range(64) for col in range(64)
                            if baseline_grid[row][col] != settled[row][col]}
                    regions = changed_regions(baseline_grid, settled)
                    pair_id = f"{env}:{guid}:{step.index}"
                    pair = {
                        "pair_id": pair_id, "env": env, "guid": guid,
                        "session_index": session_index, "step": step.index,
                        "level": baseline_level, "before": baseline_key, "after": after_key,
                        "action_id": step.action_id, "action_data": step.action_data,
                        "changed": bool(diff), "diff": sorted([list(cell) for cell in diff]),
                        "regions": [sorted([list(cell) for cell in region]) for region in regions],
                        "before_objects": object_cache[baseline_key],
                        "after_objects": object_cache[after_key],
                    }
                    pairs[pair_id] = pair
                    session_pairs[(env, guid)].append(pair_id)
                    changed_by_session[(env, guid)].update(diff)
                baseline_grid, baseline_obs, baseline_key = settled, after_obs, after_key
                baseline_level = step.levels_completed + 1
    return CorpusIndex(frames, pairs, dict(session_pairs), dict(changed_by_session), recording_hashes)


def _select_board_pairs(env: str, index: CorpusIndex) -> list[dict[str, Any]]:
    by_session: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for pair in index.pairs.values():
        if pair["env"] == env and pair["changed"]:
            by_session[pair["session_index"]].append(pair)
    two_session = int(hashlib.sha256(env.encode("ascii")).hexdigest()[:8], 16) % 3
    quotas = {session: (2 if session == two_session else 3) for session in range(3)}
    selected = []
    for session in range(3):
        candidates = sorted(by_session[session], key=lambda p: (p["step"], p["pair_id"]))
        levels = sorted({p["level"] for p in candidates})
        wanted = []
        for level in ([levels[0], levels[-1]] if levels else []):
            if level not in wanted:
                wanted.append(level)
        for level in levels:
            if level not in wanted:
                wanted.append(level)
        chosen = []
        for level in wanted:
            options = [p for p in candidates if p["level"] == level and p not in chosen]
            if options and len(chosen) < quotas[session]:
                chosen.append(min(options, key=lambda p: (_stable_key(env, p["pair_id"]), p["step"])))
        if len(chosen) < quotas[session]:
            for pair in sorted(candidates, key=lambda p: (_stable_key(env, p["pair_id"]), p["step"])):
                if pair not in chosen and len(chosen) < quotas[session]:
                    chosen.append(pair)
        if len(chosen) != quotas[session]:
            raise ValueError(f"{env}: cannot select VP1 boards for session {session}")
        selected.extend(chosen)
    return sorted(selected, key=lambda p: (p["session_index"], p["step"]))


def _query_cells(pair: dict[str, Any], index: CorpusIndex) -> dict[str, Any]:
    grid = index.frames[pair["before"]]
    after = index.frames[pair["after"]]
    counts = Counter(cell for row in grid for cell in row)
    modal = _modal(grid)
    changed = {tuple(cell) for cell in pair["diff"]}
    stable_changed = index.session_changed_cells[(pair["env"], pair["guid"])]
    stable_bg = {(r, c) for r in range(64) for c in range(64)
                 if (r, c) not in stable_changed and grid[r][c] == modal}
    rare_values = sorted(counts, key=lambda value: (counts[value], value))
    rare_cells = {(r, c) for r in range(64) for c in range(64)
                  if grid[r][c] in rare_values[:max(1, min(3, len(rare_values)))]}
    source = {cell for cell in changed if grid[cell[0]][cell[1]] != modal
              and after[cell[0]][cell[1]] == modal}
    destination = {cell for cell in changed if grid[cell[0]][cell[1]] == modal
                   and after[cell[0]][cell[1]] != modal}
    clicked = set()
    if pair["action_id"] == 6:
        clicked.add((int(pair["action_data"].get("y", -1)),
                     int(pair["action_data"].get("x", -1))))
    components = []
    remaining = {(r, c) for r in range(64) for c in range(64)}
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        value = grid[start[0]][start[1]]
        cells = {start}
        stack = [start]
        while stack:
            row, col = stack.pop()
            for neighbor in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                if neighbor in remaining and grid[neighbor[0]][neighbor[1]] == value:
                    remaining.remove(neighbor); cells.add(neighbor); stack.append(neighbor)
        components.append(cells)
    small = set().union(*(item for item in sorted(components, key=lambda x: (len(x), min(x)))[:8]))

    patch_centers = [cell for cell in sorted(changed | rare_cells)
                     if 1 <= cell[0] <= 62 and 1 <= cell[1] <= 62]
    if not patch_centers:
        patch_centers = [(32, 32)]
    patch_center = min(patch_centers, key=lambda cell: _stable_key(pair["pair_id"], "P", *cell))
    patch_box = (patch_center[0] - 1, patch_center[1] - 1,
                 patch_center[0] + 1, patch_center[1] + 1)

    strata = [
        ("changed_next", changed), ("movement", source | destination),
        ("rare", rare_cells), ("small_component", small),
        ("background_control", stable_bg), ("human_clicked", clicked),
    ]
    chosen: list[tuple[int, int]] = []
    labels = []
    occupied = [_expanded(patch_box, 1)]
    for stratum, cells in strata * 3:
        options = [cell for cell in cells if 0 <= cell[0] < 64 and 0 <= cell[1] < 64
                   and cell not in chosen
                   and not any(_boxes_overlap(_expanded((*cell, *cell), 1), box) for box in occupied)]
        if options and len(chosen) < 5:
            cell = min(options, key=lambda x: _stable_key(pair["pair_id"], stratum, *x))
            chosen.append(cell); labels.append(stratum); occupied.append(_expanded((*cell, *cell), 1))
    if len(chosen) < 5:
        for cell in [(r, c) for r in range(64) for c in range(64)]:
            if cell not in chosen and not any(
                _boxes_overlap(_expanded((*cell, *cell), 1), box) for box in occupied
            ):
                chosen.append(cell); labels.append("fallback"); occupied.append(_expanded((*cell, *cell), 1))
                if len(chosen) == 5:
                    break
    lookup_pool = sorted((rare_cells | stable_bg) - set(chosen),
                         key=lambda x: _stable_key(pair["pair_id"], "lookup", *x))
    if len(lookup_pool) < 2:
        raise ValueError(f"{pair['pair_id']}: insufficient lookup cells")
    pixel_value = next((value for value in rare_values if value != modal), rare_values[0])
    component_counts = _component_counts(grid)
    component_value = min(component_counts, key=lambda value: (-component_counts[value], value))
    patch = [[COLOR_NAMES[grid[r][c]] for c in range(patch_box[1], patch_box[3] + 1)]
             for r in range(patch_box[0], patch_box[2] + 1)]
    return {
        "markers": [{"label": chr(65 + i), "row": r, "col": c, "stratum": labels[i],
                     "gold": COLOR_NAMES[grid[r][c]]} for i, (r, c) in enumerate(chosen)],
        "patch": {"label": "P", "box": list(patch_box), "gold": patch},
        "pixel_target": {"value": pixel_value, "color": COLOR_NAMES[pixel_value],
                         "count": counts[pixel_value], "gold": _band(counts[pixel_value], PIXEL_BANDS)},
        "component_target": {"value": component_value, "color": COLOR_NAMES[component_value],
                             "count": component_counts[component_value],
                             "gold": _band(component_counts[component_value], COMPONENT_BANDS)},
        "lookups": [{"label": f"U{i + 1}", "row": cell[0], "col": cell[1],
                     "gold": COLOR_NAMES[grid[cell[0]][cell[1]]]} for i, cell in enumerate(lookup_pool[:2])],
    }


def _region_band(pair: dict[str, Any]) -> str:
    count = len(pair["regions"])
    if count == 1: return "1"
    if count <= 3: return "2-3"
    if count <= 8: return "4-8"
    return "9-12"


def _change_kind(pair: dict[str, Any], index: CorpusIndex) -> str:
    if not pair["changed"]:
        return "none"
    before, after = index.frames[pair["before"]], index.frames[pair["after"]]
    background_before, background_after = _modal(before), _modal(after)
    appeared, disappeared, recolored = [], [], []
    for row, col in map(tuple, pair["diff"]):
        old, new = before[row][col], after[row][col]
        if old == background_before and new != background_after:
            appeared.append(new)
        elif old != background_before and new == background_after:
            disappeared.append(old)
        else:
            recolored.append((old, new))
    kinds = sum(bool(items) for items in (appeared, disappeared, recolored))
    if appeared and disappeared and not recolored and Counter(appeared) == Counter(disappeared):
        return "move"
    if kinds > 1:
        return "mixed"
    if appeared:
        return "appear"
    if disappeared:
        return "disappear"
    return "recolor"


def _allocate_noops(session_candidates: dict[int, list[dict[str, Any]]]) -> tuple[int, int, int]:
    choices = []
    for a in range(9):
        for b in range(9):
            c = 8 - a - b
            if not 0 <= c <= 8: continue
            allocation = (a, b, c)
            if all(allocation[s] <= sum(not p["changed"] for p in session_candidates[s])
                   and 8 - allocation[s] <= sum(p["changed"] and len(p["regions"]) <= MAX_REGIONS
                                                for p in session_candidates[s]) for s in range(3)):
                score = sum((value - 8 / 3) ** 2 for value in allocation)
                choices.append((score, allocation))
    if not choices:
        raise ValueError("no feasible 16/8 session allocation")
    return min(choices)[1]


def _diverse_select(candidates: list[dict[str, Any]], count: int, *, seed: str,
                    band_floor: bool = False) -> list[dict[str, Any]]:
    chosen = []
    if band_floor:
        for band in ("1", "2-3", "4-8", "9-12"):
            pool = [p for p in candidates if _region_band(p) == band]
            for pair in sorted(pool, key=lambda p: (_stable_key(seed, band, p["pair_id"]), p["step"]))[:2]:
                if pair not in chosen and len(chosen) < count:
                    chosen.append(pair)
    levels = Counter(p["level"] for p in chosen)
    while len(chosen) < count:
        options = [p for p in candidates if p not in chosen]
        if not options: break
        pair = min(options, key=lambda p: (levels[p["level"]],
                                           Counter(_region_band(x) for x in chosen)[_region_band(p)],
                                           _stable_key(seed, p["pair_id"]), p["step"]))
        chosen.append(pair); levels[pair["level"]] += 1
    if len(chosen) != count:
        raise ValueError(f"{seed}: requested {count}, found {len(chosen)}")
    return chosen


def _select_vp2_pairs(env: str, index: CorpusIndex) -> tuple[list[dict[str, Any]], list[str]]:
    sessions: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for pair in index.pairs.values():
        if pair["env"] == env:
            sessions[pair["session_index"]].append(pair)
    noops = (0, 0, 0) if env == "tu93" else _allocate_noops(sessions)
    selected = []
    relaxations = []
    for session in range(3):
        noop_n = noops[session]
        changed_n = 8 - noop_n
        changed_pool = [p for p in sessions[session]
                        if p["changed"] and len(p["regions"]) <= MAX_REGIONS]
        noop_pool = [p for p in sessions[session] if not p["changed"]]
        selected.extend(_diverse_select(changed_pool, changed_n,
                                        seed=f"{env}:{session}:changed", band_floor=True))
        selected.extend(_diverse_select(noop_pool, noop_n,
                                        seed=f"{env}:{session}:noop"))
    # Enforce the game-level two-per-band floor by same-session swaps.  Session 8-pair
    # quotas and changed/no-op totals remain hard; level caps are allowed to relax first.
    available = Counter(_region_band(p) for p in index.pairs.values()
                        if p["env"] == env and p["changed"] and len(p["regions"]) <= MAX_REGIONS)
    for wanted_band, pool_n in sorted(available.items()):
        while pool_n >= 2 and sum(p["changed"] and _region_band(p) == wanted_band
                                  for p in selected) < 2:
            realized = Counter(_region_band(p) for p in selected if p["changed"])
            swaps = []
            for session in range(3):
                replacements = [p for p in sessions[session]
                                if p["changed"] and len(p["regions"]) <= MAX_REGIONS
                                and _region_band(p) == wanted_band and p not in selected]
                removable = [p for p in selected if p["session_index"] == session and p["changed"]
                             and realized[_region_band(p)] > 2]
                for add in replacements:
                    for remove in removable:
                        swaps.append((_stable_key(env, "band-swap", wanted_band,
                                                  add["pair_id"], remove["pair_id"]), remove, add))
            if not swaps:
                break
            _, remove, add = min(swaps)
            selected.remove(remove); selected.append(add)
    # Record contract-level coverage diagnostics.  The generator fails only on hard quotas;
    # level/band relaxations are declared and frozen in the artifact.
    for session in range(3):
        rows = [p for p in selected if p["session_index"] == session]
        if any(count > 4 for count in Counter(p["level"] for p in rows).values()):
            relaxations.append(f"session-{session}:level-cap")
    game_changed = [p for p in selected if p["changed"]]
    realized = Counter(_region_band(p) for p in game_changed)
    for band, pool_n in available.items():
        if pool_n >= 2 and realized[band] < 2:
            relaxations.append(f"band-floor:{band}")
    return sorted(selected, key=lambda p: (p["session_index"], p["step"])), relaxations


def _object_map(pair: dict[str, Any], side: str) -> dict[str, dict[str, Any]]:
    return {obj["key"]: obj for obj in pair[f"{side}_objects"]}


def _identity_candidates(pair: dict[str, Any]) -> list[dict[str, Any]]:
    before, after = _object_map(pair, "before"), _object_map(pair, "after")
    out = []
    for key in sorted(set(before) & set(after)):
        target_before, target_after = before[key], after[key]
        same_kind = [obj for obj in after.values() if obj["kind"] == target_after["kind"]]
        if len(same_kind) < 4:
            continue
        visual_key = (tuple(target_after["palette"]), target_after["signature"])
        if sum((tuple(obj["palette"]), obj["signature"]) == visual_key for obj in same_kind) != 1:
            continue
        others = [obj for obj in same_kind if obj["key"] != key]
        others.sort(key=lambda obj: (_stable_key(pair["pair_id"], key, obj["key"]), obj["key"]))
        candidates = [target_after, *others[:3]]
        if len(candidates) != 4:
            continue
        candidates.sort(key=lambda obj: _stable_key(pair["pair_id"], "labels", obj["key"]))
        labels = "ABCD"
        answer = labels[next(i for i, obj in enumerate(candidates) if obj["key"] == key)]
        out.append({
            "family": "identity", "pair_id": pair["pair_id"],
            "target": target_before, "candidates": [
                {**obj, "label": labels[i]} for i, obj in enumerate(candidates)
            ], "gold": answer,
        })
    return out


def _relation(name: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    a, b = tuple(left["bbox"]), tuple(right["bbox"])
    if name == "bbox_overlap": return _boxes_overlap(a, b)
    if name == "bbox_contains": return a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]
    if name == "row_aligned": return not (a[2] < b[0] or b[2] < a[0])
    if name == "column_aligned": return not (a[3] < b[1] or b[3] < a[1])
    if name == "same_palette": return left["palette"] == right["palette"]
    raise ValueError(name)


def _relation_candidates(pair: dict[str, Any]) -> list[dict[str, Any]]:
    before, after = _object_map(pair, "before"), _object_map(pair, "after")
    persistent = sorted(set(before) & set(after))
    out = []
    relations = ("bbox_overlap", "bbox_contains", "row_aligned", "column_aligned", "same_palette")
    for left_key in persistent:
        for right_key in persistent:
            if left_key == right_key or before[left_key]["kind"] != before[right_key]["kind"]:
                continue
            for name in relations:
                old = _relation(name, before[left_key], before[right_key])
                new = _relation(name, after[left_key], after[right_key])
                gold = ("became_true" if not old and new else "became_false" if old and not new
                        else "stayed_true" if old else "stayed_false")
                out.append({
                    "family": "relation", "pair_id": pair["pair_id"], "relation": name,
                    "before_A": before[left_key], "before_B": before[right_key],
                    "after_A": after[left_key], "after_B": after[right_key], "gold": gold,
                })
    return out


def _select_semantic(env: str, pairs: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    identities, relations = [], []
    for session in range(3):
        session_pairs = [p for p in pairs if p["session_index"] == session and p["changed"]]
        identity_pool = [item for pair in session_pairs for item in _identity_candidates(pair)]
        relation_pool = [item for pair in session_pairs for item in _relation_candidates(pair)]
        identity_pool.sort(key=lambda item: _stable_key(env, session, "identity", item["pair_id"], item["target"]["key"]))
        # Prefer truth changes and diversify relation names/pairs.
        relation_pool.sort(key=lambda item: (item["gold"].startswith("stayed"),
                                             _stable_key(env, session, item["relation"], item["pair_id"], item["before_A"]["key"])))
        chosen_i = []
        for item in identity_pool:
            if item["pair_id"] not in {x["pair_id"] for x in chosen_i}:
                chosen_i.append(item)
            if len(chosen_i) == 2: break
        chosen_r = []
        for item in relation_pool:
            if item["pair_id"] in {x["pair_id"] for x in chosen_r}: continue
            if item["relation"] in {x["relation"] for x in chosen_r} and len(chosen_r) == 1:
                continue
            chosen_r.append(item)
            if len(chosen_r) == 2: break
        if len(chosen_i) != 2 or len(chosen_r) != 2:
            raise ValueError(f"{env}: semantic quota failure in session {session}: identity={len(chosen_i)} relation={len(chosen_r)}")
        identities.extend(chosen_i); relations.extend(chosen_r)
    if len({item["relation"] for item in relations}) < 2:
        raise ValueError(f"{env}: relation types <2")
    if not any(item["gold"].startswith("became") for item in relations):
        raise ValueError(f"{env}: no truth-changing relation case")
    return identities, relations


def build_questions(index: CorpusIndex | None = None) -> dict[str, Any]:
    index = index or build_corpus_index()
    games = []
    for env in GAMES:
        vp1_pairs = _select_board_pairs(env, index)
        vp1 = []
        for order, pair in enumerate(vp1_pairs):
            vp1.append({
                "question_id": f"vp1:{env}:{order:02d}", "env": env,
                "guid": pair["guid"], "session_index": pair["session_index"],
                "level": pair["level"], "step": pair["step"], "frame": pair["before"],
                **_query_cells(pair, index),
            })
        vp2_pairs, relaxations = _select_vp2_pairs(env, index)
        vp2 = []
        for order, pair in enumerate(vp2_pairs):
            regions = [{"box": list(_bbox(map(tuple, region))), "cell_count": len(region)}
                       for region in pair["regions"]]
            vp2.append({
                "question_id": f"vp2:{env}:{order:02d}", "env": env,
                "guid": pair["guid"], "session_index": pair["session_index"],
                "level": pair["level"], "step": pair["step"],
                "pair_id": pair["pair_id"], "before": pair["before"], "after": pair["after"],
                "changed": pair["changed"], "region_band": _region_band(pair) if pair["changed"] else "0",
                "gold": {
                    "changed_count": len(pair["diff"]),
                    "changed_count_band": _band(len(pair["diff"]), PIXEL_BANDS),
                    "regions": regions, "no_op": not pair["changed"],
                    "change_kind": _change_kind(pair, index),
                },
            })
        identities, relations = _select_semantic(env, vp2_pairs)
        semantic = []
        for family, items in (("identity", identities), ("relation", relations)):
            for order, item in enumerate(items):
                pair = index.pairs[item["pair_id"]]
                semantic.append({
                    "question_id": f"vp2s:{env}:{family}:{order:02d}", "env": env,
                    "guid": pair["guid"], "session_index": pair["session_index"],
                    "level": pair["level"], "step": pair["step"],
                    "before": pair["before"], "after": pair["after"], **item,
                })
        selector_rows = []
        two_session = int(hashlib.sha256((env + ":selector").encode()).hexdigest()[:8], 16) % 3
        changed_quota = {session: (2 if env != "tu93" or session == two_session else 3)
                         for session in range(3)}
        # Non-tu93: two changed/session plus one no-op in two rotated sessions.  tu93:
        # 3/3/2 changed across sessions.
        if env != "tu93":
            changed_quota = {0: 2, 1: 2, 2: 2}
        for session in range(3):
            rows = [q for q in vp2 if q["session_index"] == session]
            selector_rows.extend([q for q in rows if q["changed"]][:changed_quota[session]])
        if env != "tu93":
            noop_sessions = [(two_session + offset) % 3 for offset in (0, 1)]
            for session in noop_sessions:
                noops = [q for q in vp2 if q["session_index"] == session and not q["changed"]]
                if not noops:
                    raise ValueError(f"{env}: selector no-op unavailable in session {session}")
                selector_rows.append(noops[0])
        selector = [q["question_id"] for q in selector_rows]
        palette = [{"permutation": permutation, "family": family, "question_id": question["question_id"]}
                   for permutation in PALETTE_PERMUTATIONS
                   for family, rows in (("vp1", vp1[:2]), ("vp2", vp2[:2]))
                   for question in rows]
        games.append({"env": env, "vp1": vp1, "vp2": vp2, "vp2_selector": selector,
                      "vp2_relaxations": relaxations, "semantic": semantic, "palette": palette})
    questions = {
        "format_version": FORMAT_VERSION, "status": "emitted_pre_measurement",
        "scope": "vp_freeze_1_iteration", "games": games,
        "palette_permutations": {name: {str(k): v for k, v in mapping.items()}
                                 for name, mapping in PALETTE_PERMUTATIONS.items()},
        "inputs": {
            "draw": {"path": str(DRAW.relative_to(ROOT)), "sha256": _sha256(DRAW)},
            "sessions": {"path": str(SESSIONS.relative_to(ROOT)), "sha256": _sha256(SESSIONS)},
            "recordings": index.recording_hashes,
        },
    }
    questions["question_fingerprint"] = _digest({k: v for k, v in questions.items() if k != "question_fingerprint"})
    audit_questions(questions, index)
    return questions


def audit_questions(document: dict[str, Any], index: CorpusIndex) -> None:
    for name, mapping in PALETTE_PERMUTATIONS.items():
        if set(mapping) != set(range(16)) or set(mapping.values()) != set(range(16)):
            raise ValueError(f"{name}: palette mapping is not a bijection")
        if mapping[0] != 0 or mapping[5] != 5:
            raise ValueError(f"{name}: white/black contrast anchors drift")
    if [game["env"] for game in document["games"]] != list(GAMES):
        raise ValueError("game order/membership drift")
    ids = []
    for game in document["games"]:
        if len(game["vp1"]) != 8 or len(game["vp2"]) != 24 or len(game["semantic"]) != 12:
            raise ValueError(f"{game['env']}: question quota mismatch")
        if len(game["vp2_selector"]) != 8:
            raise ValueError(f"{game['env']}: selector quota mismatch")
        if len(game["palette"]) != 8 or Counter(item["family"] for item in game["palette"]) != Counter({"vp1": 4, "vp2": 4}):
            raise ValueError(f"{game['env']}: palette quota mismatch")
        if Counter(q["session_index"] for q in game["vp2"]) != Counter({0: 8, 1: 8, 2: 8}):
            raise ValueError(f"{game['env']}: VP2 session imbalance")
        if Counter(q["session_index"] for q in game["semantic"]) != Counter({0: 4, 1: 4, 2: 4}):
            raise ValueError(f"{game['env']}: semantic session imbalance")
        for question in game["vp1"]:
            if question["frame"] not in index.frames or len(question["markers"]) != 5:
                raise ValueError(f"{question['question_id']}: invalid VP1 reference")
            boxes = [_expanded((m["row"], m["col"], m["row"], m["col"]), 1)
                     for m in question["markers"]]
            boxes.append(_expanded(tuple(question["patch"]["box"]), 1))
            if any(_boxes_overlap(boxes[i], boxes[j]) for i in range(len(boxes)) for j in range(i)):
                raise ValueError(f"{question['question_id']}: marker footprints overlap")
        for question in game["vp2"]:
            if question["before"] not in index.frames or question["after"] not in index.frames:
                raise ValueError(f"{question['question_id']}: invalid pair reference")
            if len(question["gold"]["regions"]) > MAX_REGIONS:
                raise ValueError(f"{question['question_id']}: too many regions")
        ids.extend(q["question_id"] for family in ("vp1", "vp2", "semantic") for q in game[family])
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate question IDs")


def _png_url(image: Image.Image) -> str:
    buf = io.BytesIO(); image.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def initialize_renderer() -> None:
    """Load the vendored renderer once before concurrent packet construction."""
    _vision_context()


def _base_image(grid: list, scale: int) -> Image.Image:
    url = _vision_context().frame_to_png_data_url(SimpleNamespace(grid=grid), upscale=scale)
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def _dash_box(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], color: tuple[int, int, int], width: int = 2) -> None:
    left, top, right, bottom = box
    dash = 5
    for x in range(left, right + 1, dash * 2):
        draw.line((x, top, min(x + dash, right), top), fill=color, width=width)
        draw.line((x, bottom, min(x + dash, right), bottom), fill=color, width=width)
    for y in range(top, bottom + 1, dash * 2):
        draw.line((left, y, left, min(y + dash, bottom)), fill=color, width=width)
        draw.line((right, y, right, min(y + dash, bottom)), fill=color, width=width)


def _annotated_vp1(grid: list, question: dict[str, Any], scale: int) -> Image.Image:
    gutter = max(14, scale * 2)
    base = _base_image(grid, scale)
    out = Image.new("RGB", (base.width + 2 * gutter, base.height + 2 * gutter), "white")
    out.paste(base, (gutter, gutter)); draw = ImageDraw.Draw(out)
    colors = ((220, 0, 0), (0, 90, 220), (0, 150, 0), (190, 0, 190), (230, 120, 0), (0, 0, 0))
    marks = [(m["label"], (m["row"], m["col"], m["row"], m["col"])) for m in question["markers"]]
    marks.append(("P", tuple(question["patch"]["box"])))
    for idx, (label, box) in enumerate(marks):
        top = gutter + box[0] * scale - 2; left = gutter + box[1] * scale - 2
        bottom = gutter + (box[2] + 1) * scale + 1; right = gutter + (box[3] + 1) * scale + 1
        _dash_box(draw, (left, top, right, bottom), colors[idx], width=2)
        draw.text((max(0, left), max(0, top - 11)), label, fill=colors[idx])
    return out


def _ticked(grid: list, scale: int) -> Image.Image:
    gutter = 28
    base = _base_image(grid, scale)
    out = Image.new("RGB", (base.width + gutter, base.height + gutter), "white")
    out.paste(base, (gutter, gutter)); draw = ImageDraw.Draw(out)
    for value in range(0, 64, 8):
        x = gutter + value * scale
        y = gutter + value * scale
        draw.text((x, 4), str(value), fill="black")
        draw.line((x, gutter - 4, x, gutter), fill="black")
        draw.text((2, y), str(value), fill="black")
        draw.line((gutter - 4, y, gutter, y), fill="black")
    return out


def _contact_sheet(left: Image.Image, right: Image.Image, labels=("BEFORE", "AFTER")) -> Image.Image:
    pad, top = 12, 18
    height = max(left.height, right.height) + top + 2 * pad
    out = Image.new("RGB", (left.width + right.width + 3 * pad, height), "white")
    out.paste(left, (pad, top + pad)); out.paste(right, (left.width + 2 * pad, top + pad))
    draw = ImageDraw.Draw(out); draw.text((pad, 3), labels[0], fill="black")
    draw.text((left.width + 2 * pad, 3), labels[1], fill="black")
    return out


def _ascii_marked(grid: list, question: dict[str, Any]) -> str:
    marker = {(m["row"], m["col"]): m["label"] for m in question["markers"]}
    p = tuple(question["patch"]["box"])
    lines = []
    for row in range(64):
        tokens = []
        for col in range(64):
            label = marker.get((row, col))
            if label: tokens.append(f"[{label}:{grid[row][col]:02d}]")
            elif p[0] <= row <= p[2] and p[1] <= col <= p[3]: tokens.append(f"[P:{grid[row][col]:02d}]")
            else: tokens.append(f" {grid[row][col]:02d} ")
        lines.append("".join(tokens))
    return "\n".join(lines)


def _legend() -> str:
    return ", ".join(f"{value}={name}" for value, name in COLOR_NAMES.items())


def _mapped_grid(grid: list, palette_map: dict[int, int] | None) -> list:
    return grid if palette_map is None else [[palette_map[value] for value in row] for row in grid]


def render_vp1(question: dict[str, Any], index: CorpusIndex, arm: str,
               palette_map: dict[int, int] | None = None) -> tuple[list[dict], dict]:
    grid = _mapped_grid(index.frames[question["frame"]], palette_map)
    text = (
        "Read the board exactly. Use CLEAN for global counts and U1/U2; use ANNOTATED for A-E/P.\n"
        f"Legend: {_legend()}\n"
        "Pixel-count bands: 0, 1-4, 5-16, 17-64, 65-256, 257-1024, 1025-4096. "
        "Component-count bands: 0, 1, 2, 3-4, 5-8, 9-16, 17-32, 33+.\n"
        f"Pixel-count target: {question['pixel_target']['color']}. Component-count target: "
        f"{question['component_target']['color']} (4-connected same-value components).\n"
        f"U1=(row {question['lookups'][0]['row']}, col {question['lookups'][0]['col']}), "
        f"U2=(row {question['lookups'][1]['row']}, col {question['lookups'][1]['col']}).\n"
        "For every cell answer, copy the exact color NAME after '=' in the legend; numeric palette IDs are invalid. "
        "patch_P must be a nested array of exactly 3 row arrays, each containing exactly 3 color names. "
        "Return the strict JSON object only with keys marked_cells(A-E), patch_P, pixel_count_band, "
        "component_count_band, lookups(U1,U2). The first character must be { and the last must be }; "
        "do not use Markdown fences or add prose."
    )
    content: list[dict[str, Any]] = []
    bytes_encoded = 0
    if arm in {"I-A", "I-H"}:
        text += "\nCLEAN ASCII:\n" + format_grid_ascii(grid) + "\nANNOTATED ASCII:\n" + _ascii_marked(grid, question)
    if arm != "I-A":
        scale = SCALES[arm]
        clean = _base_image(grid, scale)
        if arm == "I-C":
            # Six fixed-size 9x9 crops, padded with value 0 at edges, rendered at 32x.
            panels = []
            marks = [(m["label"], (m["row"], m["col"], m["row"], m["col"])) for m in question["markers"]]
            marks.append(("P", tuple(question["patch"]["box"])))
            for label, box in marks:
                center_r = (box[0] + box[2]) // 2; center_c = (box[1] + box[3]) // 2
                crop = [[grid[r][c] if 0 <= r < 64 and 0 <= c < 64 else 0
                         for c in range(center_c - 4, center_c + 5)]
                        for r in range(center_r - 4, center_r + 5)]
                panel = _base_image(crop, 32); draw = ImageDraw.Draw(panel)
                local = (4 - (box[2] - box[0]) // 2, 4 - (box[3] - box[1]) // 2,
                         4 + (box[2] - box[0]) // 2, 4 + (box[3] - box[1]) // 2)
                _dash_box(draw, (local[1] * 32 - 2, local[0] * 32 - 2,
                                 (local[3] + 1) * 32 + 1, (local[2] + 1) * 32 + 1), (220, 0, 0), 2)
                draw.text((3, 3), label, fill="black"); panels.append(panel)
            sheet = Image.new("RGB", (3 * 288 + 24, 2 * 288 + 18), "white")
            for i, panel in enumerate(panels): sheet.paste(panel, ((i % 3) * 288 + (i % 3) * 8, (i // 3) * 288 + (i // 3) * 8 + 18))
            annotated = sheet
        else:
            annotated = _annotated_vp1(grid, question, scale)
        for label, image in (("CLEAN", clean), ("ANNOTATED", annotated)):
            url = _png_url(image); bytes_encoded += len(url)
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": {"url": url}})
    content.insert(0, {"type": "text", "text": text})
    messages = [{"role": "system", "content": "You are a deterministic visual perception instrument."},
                {"role": "user", "content": content if arm != "I-A" else text}]
    return messages, {"encoded_chars": bytes_encoded, "arm": arm}


def render_vp2(question: dict[str, Any], index: CorpusIndex, arm: str,
               packaging: str = "separate",
               palette_map: dict[int, int] | None = None) -> tuple[list[dict], dict]:
    before = _mapped_grid(index.frames[question["before"]], palette_map)
    after = _mapped_grid(index.frames[question["after"]], palette_map)
    text = (
        "Compare BEFORE and AFTER. Coordinates are zero-based [row_min,col_min,row_max,col_max], inclusive. "
        "Changed regions use 4-connectivity and must be row-major.\n"
        "Changed-cell count bands: 0, 1-4, 5-16, 17-64, 65-256, 257-1024, 1025-4096. "
        "Kind: appear adds foreground, disappear removes foreground, move preserves moved colors, "
        "recolor changes foreground colors in place, mixed combines mechanisms, none is no-op.\n"
        "Return strict JSON only: {\"changed_count_band\":\"<band>\",\"regions\":[...],"
        "\"no_op\":false,\"change_kind\":\"appear|disappear|move|recolor|mixed|none\"}. "
        "The first character must be { and the last must be }; do not use Markdown fences or add prose."
    )
    if arm == "I-A":
        text += "\nBEFORE ASCII:\n" + format_grid_ascii(before) + "\nAFTER ASCII:\n" + format_grid_ascii(after)
        content: Any = text; encoded = 0
    else:
        scale = SCALES.get(arm, 4)
        left, right = _ticked(before, scale), _ticked(after, scale)
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        encoded = 0
        if packaging == "contact":
            url = _png_url(_contact_sheet(left, right)); encoded += len(url)
            parts.append({"type": "image_url", "image_url": {"url": url}})
        else:
            for label, image in (("BEFORE", left), ("AFTER", right)):
                parts.append({"type": "text", "text": label})
                url = _png_url(image); encoded += len(url)
                parts.append({"type": "image_url", "image_url": {"url": url}})
        content = parts
    messages = [{"role": "system", "content": "You are a deterministic visual change-reading instrument."},
                {"role": "user", "content": content}]
    return messages, {"encoded_chars": encoded, "arm": arm, "packaging": packaging}


def _mark_objects(grid: list, objects: list[tuple[str, dict]], scale: int) -> Image.Image:
    gutter = 20; base = _base_image(grid, scale)
    out = Image.new("RGB", (base.width + 2 * gutter, base.height + 2 * gutter), "white")
    out.paste(base, (gutter, gutter)); draw = ImageDraw.Draw(out)
    colors = ((220, 0, 0), (0, 90, 220), (0, 150, 0), (190, 0, 190), (230, 120, 0))
    for idx, (label, obj) in enumerate(objects):
        box = obj["bbox"]
        pix = (gutter + box[1] * scale - 2, gutter + box[0] * scale - 2,
               gutter + (box[3] + 1) * scale + 1, gutter + (box[2] + 1) * scale + 1)
        _dash_box(draw, pix, colors[idx % len(colors)], 2)
        draw.text((pix[0], max(0, pix[1] - 11)), label, fill=colors[idx % len(colors)])
    return out


def render_semantic(question: dict[str, Any], index: CorpusIndex, arm: str,
                    packaging: str) -> tuple[list[dict], dict]:
    scale = SCALES[arm]
    before, after = index.frames[question["before"]], index.frames[question["after"]]
    if question["family"] == "identity":
        left_marks = [("TARGET", question["target"])]
        right_marks = [(obj["label"], obj) for obj in question["candidates"]]
        text = ("Which marked object A/B/C/D in AFTER is the TARGET object from BEFORE? "
                "Return only {\"identity\":\"A|B|C|D\"}; first character {, last character }, no Markdown fences or prose.")
    else:
        left_marks = [("A", question["before_A"]), ("B", question["before_B"])]
        right_marks = [("A", question["after_A"]), ("B", question["after_B"])]
        definitions = {
            "bbox_overlap": "the A and B bounding boxes have a nonempty intersection",
            "bbox_contains": "A's bounding box contains B's bounding box",
            "row_aligned": "the A and B bounding-box row intervals overlap",
            "column_aligned": "the A and B bounding-box column intervals overlap",
            "same_palette": "the visible value sets inside the authored A and B objects are equal",
        }
        text = (f"For directed relation {question['relation']} between A and B ({definitions[question['relation']]}), "
                "return its observed transition. "
                "Return only {\"transition\":\"became_true|became_false|stayed_true|stayed_false\"}; "
                "first character {, last character }, no Markdown fences or prose.")
    left, right = _mark_objects(before, left_marks, scale), _mark_objects(after, right_marks, scale)
    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    if packaging == "contact":
        url = _png_url(_contact_sheet(left, right)); parts.append({"type": "image_url", "image_url": {"url": url}}); encoded = len(url)
    else:
        encoded = 0
        for label, image in (("BEFORE", left), ("AFTER", right)):
            parts.append({"type": "text", "text": label}); url = _png_url(image); encoded += len(url)
            parts.append({"type": "image_url", "image_url": {"url": url}})
    return ([{"role": "system", "content": "You are a deterministic visual semantic-binding instrument."},
             {"role": "user", "content": parts}],
            {"encoded_chars": encoded, "arm": arm, "packaging": packaging})


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--verify", action="store_true")
    group.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    index = build_corpus_index(); document = build_questions(index)
    if args.write:
        OUTPUT.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
        print(f"vp_questions: wrote {OUTPUT.relative_to(ROOT)} {document['question_fingerprint'][:16]}")
        return 0
    if args.verify:
        existing = json.loads(OUTPUT.read_text())
        if existing != document:
            print("vp_questions: artifact differs from rebuild", file=sys.stderr); return 1
        print("vp_questions: verified"); return 0
    print("vp_questions: answerability audit passed")
    for game in document["games"]:
        print(game["env"], len(game["vp1"]), len(game["vp2"]), len(game["semantic"]), game["vp2_relaxations"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
