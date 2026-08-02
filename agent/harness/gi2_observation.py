#!/usr/bin/env python3
"""GI-2 A2 observable components, tracks, groups, lineage, roles, and effect catalogue.

This layer uses only rendered 64x64 frames and recorded actions.  Equal-color four-connected
components are atomic observations, not assumed semantic objects.  Stable handles are inferred
by overlap first and translation-invariant color/shape matching second.  Split, merge, recolor,
appearance, disappearance, and co-moving adjacent groups are explicit events.

The output is a compact measurement artifact; raw frames and crops are not embedded.  Crops can
be rendered on demand with :func:`render_crop`.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from gi2_replay import iter_recorded_actions
from gi2_traces import (
    CORPUS,
    DRAW,
    ROOT,
    SESSIONS,
    frame_roles,
    selected_sessions,
)

OUTPUT = ROOT / "logs/gi2_observation_catalogue.json"
REPLAY_FIDELITY = ROOT / "logs/gi2_replay_fidelity.json"
FORMAT_VERSION = 1
ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))


@dataclass(frozen=True)
class Component:
    local_id: int
    color: int
    cells: frozenset[tuple[int, int]]
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    boundary: tuple[tuple[int, int], ...]
    shape: str

    @property
    def pixels(self) -> int:
        return len(self.cells)


@dataclass
class Handle:
    track_id: str
    component: Component
    role_counts: collections.Counter[str] = field(default_factory=collections.Counter)

    @property
    def role(self) -> str:
        if self.role_counts["click_responsive"] > 0:
            return "click_responsive"
        if self.role_counts["controlled"] >= 2:
            return "controlled"
        if self.role_counts["autonomous"] >= 2:
            return "autonomous"
        return "static"


@dataclass(frozen=True)
class Group:
    group_id: str
    members: tuple[str, ...]
    representative: tuple[int, int]


@dataclass
class Observation:
    handles: list[Handle]
    groups: list[Group]
    events: list[dict[str, Any]]
    changed_regions: list[frozenset[tuple[int, int]]]
    mouse_representatives: list[tuple[int, int]]


def _shape(cells: Iterable[tuple[int, int]], color: int) -> str:
    cells = list(cells)
    min_row = min(row for row, _ in cells)
    min_col = min(col for _, col in cells)
    normalized = sorted((row - min_row, col - min_col) for row, col in cells)
    return hashlib.sha1(repr((color, normalized)).encode()).hexdigest()[:16]


def _nearest_member(
    cells: Iterable[tuple[int, int]], row: float, col: float
) -> tuple[int, int]:
    return min(
        cells,
        key=lambda cell: (
            (cell[0] - row) ** 2 + (cell[1] - col) ** 2,
            cell[0],
            cell[1],
        ),
    )


def componentize(grid: list) -> list[Component]:
    height = len(grid)
    width = len(grid[0]) if height else 0
    seen: set[tuple[int, int]] = set()
    out = []
    for start_row in range(height):
        for start_col in range(width):
            if (start_row, start_col) in seen:
                continue
            color = int(grid[start_row][start_col])
            stack = [(start_row, start_col)]
            seen.add((start_row, start_col))
            cells = set()
            while stack:
                row, col = stack.pop()
                cells.add((row, col))
                for drow, dcol in ORTHOGONAL:
                    nrow, ncol = row + drow, col + dcol
                    if (
                        0 <= nrow < height
                        and 0 <= ncol < width
                        and (nrow, ncol) not in seen
                        and int(grid[nrow][ncol]) == color
                    ):
                        seen.add((nrow, ncol))
                        stack.append((nrow, ncol))
            boundary = sorted(
                cell
                for cell in cells
                if any(
                    (cell[0] + drow, cell[1] + dcol) not in cells
                    for drow, dcol in ORTHOGONAL
                )
            )
            rows = [row for row, _ in cells]
            cols = [col for _, col in cells]
            centroid = _nearest_member(
                cells, sum(rows) / len(rows), sum(cols) / len(cols)
            )
            frozen = frozenset(cells)
            out.append(
                Component(
                    local_id=len(out),
                    color=color,
                    cells=frozen,
                    bbox=(min(rows), min(cols), max(rows), max(cols)),
                    centroid=centroid,
                    boundary=tuple(boundary),
                    shape=_shape(frozen, color),
                )
            )
    return out


def observable_components(grid: list) -> list[Component]:
    """Drop only a component that is unambiguously the full-screen background."""
    all_components = componentize(grid)
    return [
        component
        for component in all_components
        if not (
            component.pixels > 2048
            and component.bbox == (0, 0, len(grid) - 1, len(grid[0]) - 1)
        )
    ]


def changed_regions(before: list, after: list) -> list[frozenset[tuple[int, int]]]:
    changed = {
        (row, col)
        for row, (left, right) in enumerate(zip(before, after))
        for col, (a, b) in enumerate(zip(left, right))
        if a != b
    }
    regions = []
    while changed:
        start = min(changed)
        changed.remove(start)
        region = {start}
        stack = [start]
        while stack:
            row, col = stack.pop()
            for drow, dcol in ORTHOGONAL:
                neighbor = (row + drow, col + dcol)
                if neighbor in changed:
                    changed.remove(neighbor)
                    region.add(neighbor)
                    stack.append(neighbor)
        regions.append(frozenset(region))
    return regions


def _translation(before: Component, after: Component) -> tuple[int, int]:
    return (
        after.centroid[0] - before.centroid[0],
        after.centroid[1] - before.centroid[1],
    )


def _touching(left: Component, right: Component) -> bool:
    return any(
        (row + drow, col + dcol) in right.cells
        for row, col in left.cells
        for drow, dcol in ORTHOGONAL
    )


def _group_from_members(members: list[Handle]) -> Group:
    ids = tuple(sorted(member.track_id for member in members))
    medoid = min(
        members,
        key=lambda candidate: (
            sum(
                math.dist(
                    candidate.component.centroid,
                    other.component.centroid,
                )
                for other in members
            ),
            candidate.track_id,
        ),
    )
    return Group(
        group_id="g:" + "+".join(ids),
        members=ids,
        representative=medoid.component.centroid,
    )


def compact_groups(handles: list[Handle]) -> list[Group]:
    """Generate observable dense multicolour groups without a pixel/size cap.

    Connected components of the cross-colour contact graph are admitted only when their
    union is at least 75% dense in its bounding rectangle.  The density rule is scale-free
    and prevents a sparse adjacency chain from swallowing the board.
    """
    neighbors: dict[int, list[int]] = collections.defaultdict(list)
    cell_owner = {
        cell: index
        for index, handle in enumerate(handles)
        for cell in handle.component.cells
    }
    edge_set = set()
    for left_index, left in enumerate(handles):
        for row, col in left.component.cells:
            for drow, dcol in ORTHOGONAL:
                right_index = cell_owner.get((row + drow, col + dcol))
                if right_index is not None and right_index != left_index:
                    edge_set.add(tuple(sorted((left_index, right_index))))
    for left_index, right_index in sorted(edge_set):
        neighbors[left_index].append(right_index)
        neighbors[right_index].append(left_index)

    member_sets: set[tuple[int, ...]] = set()
    unseen = set(neighbors)
    while unseen:
        seed = min(unseen)
        unseen.remove(seed)
        members = {seed}
        stack = [seed]
        while stack:
            current = stack.pop()
            for neighbor in neighbors.get(current, []):
                if neighbor not in members:
                    members.add(neighbor)
                    unseen.discard(neighbor)
                    stack.append(neighbor)
        if len(members) < 2:
            continue
        cells = set().union(*(handles[index].component.cells for index in members))
        rows = [row for row, _ in cells]
        cols = [col for _, col in cells]
        bbox_area = (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)
        if len(cells) / bbox_area >= 0.75:
            member_sets.add(tuple(sorted(members)))
    return [
        _group_from_members([handles[index] for index in indexes])
        for indexes in sorted(member_sets)
    ]


def local_compact_groups(handles: list[Handle]) -> list[Group]:
    """Enumerate dense local contact groups for a checkpoint registry.

    Unlike :func:`compact_groups`, this retains every dense prefix grown around every seed.
    It is intentionally an on-demand checkpoint operation rather than a per-frame tracker
    operation: its quadratic worst case is acceptable for 123 completion checkpoints, not
    for the full 9,913-action catalogue.
    """
    cell_owner = {
        cell: index
        for index, handle in enumerate(handles)
        for cell in handle.component.cells
    }
    neighbors: dict[int, set[int]] = collections.defaultdict(set)
    for left_index, left in enumerate(handles):
        for row, col in left.component.cells:
            for drow, dcol in ORTHOGONAL:
                right_index = cell_owner.get((row + drow, col + dcol))
                if right_index is not None and right_index != left_index:
                    neighbors[left_index].add(right_index)
                    neighbors[right_index].add(left_index)
    member_sets: set[tuple[int, ...]] = set()
    for seed in range(len(handles)):
        members = {seed}
        cells = set(handles[seed].component.cells)
        frontier = set(neighbors.get(seed, set()))
        rejected = set()
        while frontier:
            seed_row, seed_col = handles[seed].component.centroid
            candidate = min(
                frontier,
                key=lambda index: (
                    math.dist(
                        (seed_row, seed_col), handles[index].component.centroid
                    ),
                    handles[index].track_id,
                ),
            )
            frontier.remove(candidate)
            proposed_cells = cells | set(handles[candidate].component.cells)
            rows = [row for row, _ in proposed_cells]
            cols = [col for _, col in proposed_cells]
            bbox_area = (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)
            if len(proposed_cells) / bbox_area < 0.75:
                rejected.add(candidate)
                continue
            members.add(candidate)
            cells = proposed_cells
            if len(members) >= 2:
                member_sets.add(tuple(sorted(members)))
            frontier.update(
                neighbor
                for index in members
                for neighbor in neighbors.get(index, set())
                if neighbor not in members and neighbor not in rejected
            )
    groups = []
    for indexes in sorted(member_sets):
        members = [handles[index] for index in indexes]
        ids = tuple(sorted(member.track_id for member in members))
        groups.append(
            Group(
                group_id="g:" + "+".join(ids),
                members=ids,
                # Checkpoint groups do not enter the MOUSE representative set.
                representative=min(members, key=lambda item: item.track_id).component.centroid,
            )
        )
    return groups


def _match_components(
    previous: list[Handle], current: list[Component]
) -> tuple[dict[int, int], list[dict[str, Any]]]:
    """current index -> previous index plus explicit lineage events."""
    candidates = []
    cell_owner = {
        cell: current_index
        for current_index, component in enumerate(current)
        for cell in component.cells
    }
    shape_index: dict[tuple[str, int, int], list[int]] = collections.defaultdict(list)
    for current_index, component in enumerate(current):
        shape_index[
            (component.shape, component.centroid[0] // 8, component.centroid[1] // 8)
        ].append(current_index)
    for previous_index, handle in enumerate(previous):
        old = handle.component
        candidate_indexes = {
            cell_owner[cell] for cell in old.cells if cell in cell_owner
        }
        old_row_bin = old.centroid[0] // 8
        old_col_bin = old.centroid[1] // 8
        for row_bin in range(old_row_bin - 2, old_row_bin + 3):
            for col_bin in range(old_col_bin - 2, old_col_bin + 3):
                candidate_indexes.update(
                    shape_index.get((old.shape, row_bin, col_bin), [])
                )
        for current_index in candidate_indexes:
            new = current[current_index]
            overlap = len(old.cells & new.cells)
            union = len(old.cells | new.cells)
            jaccard = overlap / union if union else 0.0
            same_shape = old.shape == new.shape
            distance = math.dist(old.centroid, new.centroid)
            if overlap or same_shape:
                candidates.append(
                    (
                        1 if overlap else 0,
                        jaccard,
                        1 if same_shape else 0,
                        -distance,
                        previous_index,
                        current_index,
                    )
                )
    matches: dict[int, int] = {}
    used_previous: set[int] = set()
    for _, _, _, _, previous_index, current_index in sorted(candidates, reverse=True):
        if previous_index in used_previous or current_index in matches:
            continue
        matches[current_index] = previous_index
        used_previous.add(previous_index)
    events = []
    for previous_index, handle in enumerate(previous):
        overlapping = sorted(
            {cell_owner[cell] for cell in handle.component.cells if cell in cell_owner}
        )
        if len(overlapping) > 1:
            events.append(
                {
                    "type": "split",
                    "parent": handle.track_id,
                    "children_local": overlapping,
                }
            )
    previous_cell_owner = {
        cell: previous_index
        for previous_index, handle in enumerate(previous)
        for cell in handle.component.cells
    }
    for current_index, component in enumerate(current):
        overlapping = [
            previous[previous_index].track_id
            for previous_index in sorted(
                {previous_cell_owner[cell] for cell in component.cells if cell in previous_cell_owner}
            )
        ]
        if len(overlapping) > 1:
            events.append(
                {"type": "merge", "parents": overlapping, "child_local": current_index}
            )
    return matches, events


class Tracker:
    def __init__(self):
        self.handles: list[Handle] = []
        self.next_track = 0
        self.frame_index = 0

    def reset_level(self) -> None:
        self.handles = []

    def update(
        self,
        grid: list,
        *,
        previous_grid: list | None,
        action_id: int,
        action_data: dict[str, Any],
    ) -> Observation:
        components = observable_components(grid)
        matches, events = _match_components(self.handles, components)
        new_handles = []
        matched_previous = set(matches.values())
        for current_index, component in enumerate(components):
            if current_index in matches:
                old = self.handles[matches[current_index]]
                handle = Handle(old.track_id, component, old.role_counts.copy())
                displacement = _translation(old.component, component)
                if old.component.color != component.color and old.component.cells == component.cells:
                    events.append({"type": "recolor", "track": handle.track_id})
                if displacement != (0, 0):
                    event = {
                        "type": "move",
                        "track": handle.track_id,
                        "delta": displacement,
                    }
                    events.append(event)
                    if action_id in (1, 2, 3, 4, 5, 7):
                        handle.role_counts["controlled"] += 1
                    else:
                        handle.role_counts["autonomous"] += 1
                if action_id == 6:
                    click = (
                        int(action_data.get("y", -1)),
                        int(action_data.get("x", -1)),
                    )
                    if click in old.component.cells and (
                        old.component.cells != component.cells
                        or old.component.color != component.color
                    ):
                        handle.role_counts["click_responsive"] += 1
            else:
                handle = Handle(f"o{self.next_track}", component)
                self.next_track += 1
                events.append({"type": "appear", "track": handle.track_id})
            new_handles.append(handle)
        for previous_index, old in enumerate(self.handles):
            if previous_index not in matched_previous:
                events.append({"type": "disappear", "track": old.track_id})
        self.handles = new_handles
        self.frame_index += 1

        move_by_track = {
            event["track"]: tuple(event["delta"])
            for event in events
            if event["type"] == "move"
        }
        grouped: set[str] = set()
        groups = compact_groups(new_handles)
        group_members = {group.members for group in groups}
        for index, left in enumerate(new_handles):
            if left.track_id in grouped or left.track_id not in move_by_track:
                continue
            members = [left]
            for right in new_handles[index + 1 :]:
                if (
                    right.track_id not in grouped
                    and move_by_track.get(right.track_id) == move_by_track[left.track_id]
                    and _touching(left.component, right.component)
                ):
                    members.append(right)
            if len(members) >= 2:
                ids = tuple(sorted(member.track_id for member in members))
                grouped.update(ids)
                if ids not in group_members:
                    groups.append(_group_from_members(members))
                    group_members.add(ids)
        regions = changed_regions(previous_grid, grid) if previous_grid is not None else []
        representatives = mouse_representatives(new_handles, groups, regions)
        return Observation(new_handles, groups, events, regions, representatives)


def mouse_representatives(
    handles: list[Handle],
    groups: list[Group],
    regions: list[frozenset[tuple[int, int]]],
) -> list[tuple[int, int]]:
    points = set()
    for handle in handles:
        points.add(handle.component.centroid)
        if handle.component.boundary:
            points.add(min(handle.component.boundary))
    points.update(group.representative for group in groups)
    for region in regions:
        if region:
            row = sum(cell[0] for cell in region) / len(region)
            col = sum(cell[1] for cell in region) / len(region)
            points.add(_nearest_member(region, row, col))
    return sorted(points)


def effect_signature(observation: Observation, *, completed: bool) -> str:
    counts = collections.Counter(event["type"] for event in observation.events)
    payload = {
        "move": counts["move"],
        "appear": counts["appear"],
        "disappear": counts["disappear"],
        "recolor": counts["recolor"],
        "split": counts["split"],
        "merge": counts["merge"],
        "changed_regions": len(observation.changed_regions),
        "completed": completed,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def analyze_session(env: str, selected: dict[str, Any]) -> dict[str, Any]:
    path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
    tracker = Tracker()
    previous_grid = None
    previous_levels = 0
    catalogue: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    totals = collections.Counter()
    role_counts = collections.Counter()
    representative_counts = []
    completion_snapshots = []
    for action in iter_recorded_actions(path):
        increment = action.levels_completed - previous_levels
        roles = frame_roles(
            state=action.state,
            n_frames=len(action.frames),
            completion_increment=increment,
        )
        selected_frames = [
            (frame, role)
            for frame, role in zip(action.frames, roles)
            if role in {"settled", "solved_terminal", "next_level_initial"}
        ]
        terminal_observation = None
        for grid, role in selected_frames:
            if role == "next_level_initial":
                tracker.reset_level()
                previous_grid = None
            observation = tracker.update(
                grid,
                previous_grid=previous_grid,
                action_id=action.action_id,
                action_data=action.action_data,
            )
            totals["analyzed_frames"] += 1
            totals["components"] += len(observation.handles)
            totals["groups"] += len(observation.groups)
            totals.update(event["type"] for event in observation.events)
            role_counts.update(handle.role for handle in observation.handles)
            previous_grid = grid
            if role == "solved_terminal":
                terminal_observation = observation
                representative_counts.append(len(observation.mouse_representatives))
                if len(completion_snapshots) < 3:
                    completion_snapshots.append(
                        {
                            "step": action.step,
                            "level": action.levels_completed,
                            "handles": [
                                {
                                    "id": handle.track_id,
                                    "color": handle.component.color,
                                    "pixels": handle.component.pixels,
                                    "bbox": handle.component.bbox,
                                    "centroid": handle.component.centroid,
                                    "role": handle.role,
                                }
                                for handle in observation.handles
                            ],
                            "groups": [
                                {
                                    "id": group.group_id,
                                    "members": group.members,
                                    "representative": group.representative,
                                }
                                for group in observation.groups
                            ],
                            "mouse_representatives": observation.mouse_representatives,
                        }
                    )
            if role != "next_level_initial":
                catalogue[str(action.action_id)][
                    effect_signature(observation, completed=bool(increment))
                ] += 1
        previous_levels = action.levels_completed
    return {
        **selected,
        "recording": str(path.relative_to(ROOT)),
        "totals": dict(totals),
        "roles": dict(role_counts),
        "mouse_representatives": {
            "n_completion_states": len(representative_counts),
            "min": min(representative_counts) if representative_counts else None,
            "median": (
                sorted(representative_counts)[len(representative_counts) // 2]
                if representative_counts
                else None
            ),
            "max": max(representative_counts) if representative_counts else None,
        },
        "catalogue": {
            action_id: dict(counter) for action_id, counter in sorted(catalogue.items())
        },
        "completion_snapshots": completion_snapshots,
    }


def build_catalogue(jobs: int = 1) -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    fidelity = json.loads(REPLAY_FIDELITY.read_text())
    fork_eligible = {
        game["env"] for game in fidelity["games"] if game["frame_fidelity"]
    }
    work = [
        (env, selected)
        for env in draw["iteration"]
        for selected in selected_sessions(env, sessions_doc, draw)
    ]
    if jobs < 1:
        raise ValueError("jobs must be positive")
    if jobs == 1:
        analyzed = [analyze_session(env, selected) for env, selected in work]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
            analyzed = list(
                pool.map(
                    _analyze_session_args,
                    work,
                )
            )
    games = []
    for env in draw["iteration"]:
        rows = sorted(
            [row for row in analyzed if f"/{env}/" in row["recording"]],
            key=lambda row: row["rank"],
        )
        aggregate_catalogue: dict[str, collections.Counter[str]] = collections.defaultdict(
            collections.Counter
        )
        for row in rows:
            for action_id, signatures in row["catalogue"].items():
                aggregate_catalogue[action_id].update(signatures)
        games.append(
            {
                "env": env,
                "fork_eligible": env in fork_eligible,
                "sessions": rows,
                "catalogue": {
                    action_id: {
                        "n": sum(counter.values()),
                        "effects": dict(counter.most_common()),
                    }
                    for action_id, counter in sorted(aggregate_catalogue.items())
                },
            }
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "a2_measured",
        "scope": "iteration",
        "inputs": {
            "replay_fidelity": str(REPLAY_FIDELITY.relative_to(ROOT)),
            "replay_fidelity_sha256": hashlib.sha256(
                REPLAY_FIDELITY.read_bytes()
            ).hexdigest(),
        },
        "policy": {
            "atomic": "same-color four-connected components",
            "background_exclusion": "only >2048px full-screen component",
            "matching": "overlap then translation-invariant color/shape",
            "groups": "adjacent components with identical nonzero displacement",
            "mouse": (
                "atomic centroid + lexicographic boundary; group medoid; "
                "changed-region centroid; all snapped to member cells and deduplicated"
            ),
        },
        "games": games,
    }


def _analyze_session_args(args: tuple[str, dict[str, Any]]) -> dict[str, Any]:
    return analyze_session(*args)


def render_crop(grid: list, component: Component, output: Path, scale: int = 4) -> None:
    from PIL import Image

    top, left, bottom, right = component.bbox
    padding = 1
    top, left = max(0, top - padding), max(0, left - padding)
    bottom, right = min(len(grid) - 1, bottom + padding), min(
        len(grid[0]) - 1, right + padding
    )
    colors = [
        (255, 255, 255),
        (220, 220, 220),
        (160, 160, 160),
        (100, 100, 100),
        (60, 60, 60),
        (0, 0, 0),
        (255, 0, 255),
        (255, 120, 180),
        (255, 0, 0),
        (0, 0, 255),
        (80, 180, 255),
        (255, 255, 0),
        (255, 140, 0),
        (140, 0, 0),
        (120, 255, 120),
        (150, 60, 180),
    ]
    image = Image.new(
        "RGB",
        (right - left + 1, bottom - top + 1),
    )
    pixels = image.load()
    for row in range(top, bottom + 1):
        for col in range(left, right + 1):
            pixels[col - left, row - top] = colors[int(grid[row][col])]
    image.resize(
        (image.width * scale, image.height * scale),
        resample=Image.Resampling.NEAREST,
    ).save(output)


def first_difference(left: Any, right: Any, path: str = "artifact") -> str | None:
    if type(left) is not type(right):
        return f"{path}: type {type(left).__name__} != {type(right).__name__}"
    if isinstance(left, dict):
        if set(left) != set(right):
            return f"{path}: keys differ"
        for key in sorted(left):
            problem = first_difference(left[key], right[key], f"{path}.{key}")
            if problem:
                return problem
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: length {len(left)} != {len(right)}"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            problem = first_difference(
                left_item, right_item, f"{path}[{index}]"
            )
            if problem:
                return problem
        return None
    return None if left == right else f"{path}: {left!r} != {right!r}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    if args.measure:
        document = build_catalogue(args.jobs)
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        for game in document["games"]:
            components = sum(
                row["totals"].get("components", 0) for row in game["sessions"]
            )
            groups = sum(row["totals"].get("groups", 0) for row in game["sessions"])
            reps = [
                row["mouse_representatives"]["median"] for row in game["sessions"]
            ]
            print(
                f"{game['env']}: fork={'yes' if game['fork_eligible'] else 'no'}, "
                f"components={components}, groups={groups}, median mouse reps={reps}"
            )
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            document = json.loads(OUTPUT.read_text())
            # Normalize tuples emitted by dataclasses to their JSON representation before
            # comparing with the deserialized artifact.
            current = json.loads(json.dumps(build_catalogue(args.jobs)))
            difference = first_difference(document, current)
            problems = [] if difference is None else [difference]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("GI-2 observation catalogue FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("GI-2 observation catalogue OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
