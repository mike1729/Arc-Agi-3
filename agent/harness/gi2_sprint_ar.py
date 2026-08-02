#!/usr/bin/env python3
"""Sprint A-R: the single pre-registered remediation round (note §3.4, FROZEN 2026-07-30).

Implements R-1..R-6 without modifying any measured Sprint A module or artifact:

* R-1 adjacency composites (pairs + maximal clusters of non-background objects);
* R-2 ring/containment decomposition (bbox-perimeter ring + connected interior remainder);
* R-3 DNF set descriptors: unions of at most U=4 conjunctions of at most two feature terms,
  ``role`` admissible everywhere;
* R-4 permanence: every evaluation registry derives from a maintained PermanenceTracker;
  fork registries via tracker deepcopy + one update; occlusion carryover at theta_occ=1.0;
* R-5 gates: representability >= 5/6 unchanged; identifiability >= 4/6 on the
  trajectory-only arm under the A' success predicate (gold or an observationally
  equivalent survivor in the top 3);
* R-6 fork elimination distributions (non-gating; the catalogue selection-policy numerator
  awaits Sprint C's frozen policy).

The vc33 settled-frame fidelity erratum is ACCEPTED: authoring fidelity compares only
settled / solved_terminal / next_level_initial frames, vc33 becomes fork-eligible, and this
round regenerates its forks with the same candidate policy as ``gi2_forks``.

Implementation readings declared in the freeze artifact (gaps the frozen text does not
decide): candidate-space vocabulary = stable minimal conjunction descriptors plus the
selected gold DNF descriptors; occluded objects join composites via last-known cells;
vc33's ``flanks`` conjunct and ft09's ``local_template_match`` op remain mechanically
unevaluable this round (carried from the diagnostic's declared limits).

Run:
  .venv/bin/python -u agent/harness/gi2_sprint_ar.py --freeze
  .venv/bin/python -u agent/harness/gi2_sprint_ar.py --measure
  .venv/bin/python -u agent/harness/gi2_sprint_ar.py --verify
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from arcengine import ActionInput, GameAction

from gi2_forks import decode_grid, encode_grid
from gi2_gidsl import BOOLEAN_OPS, CLASS_SKELETONS, COMPARATORS, EVENTS, RELATIONS
from gi2_gidsl_runtime import canonicalize_ast, evaluate_ast, generate_finite_candidates
from gi2_grounding import projected_sprite_cells, semantic_sprites
from gi2_observation import Tracker, _shape
from gi2_replay import ReplayDriver, iter_recorded_actions
from gi2_traces import CORPUS, DRAW, ROOT, SESSIONS, frame_roles, selected_sessions

NOTE = ROOT / "notes/gi2-grounded-binding.md"
GOLD = ROOT / "logs/gi2_gidsl_gold_iteration.json"
FORKS = ROOT / "logs/gi2_fork_table.json"
FREEZE_OUTPUT = ROOT / "logs/gi2_ar_freeze.json"
VC33_FORKS_OUTPUT = ROOT / "logs/gi2_ar_vc33_forks.json"
OUTPUT = ROOT / "logs/gi2_sprint_ar_results.json"

FORMAT_VERSION = 1
U_UNION = 4
THETA_OCC = 1.0
TOP_K = 3
TRAJECTORY_CAP_PER_SESSION = 40
REPRESENTABILITY_REQUIRED = 5
IDENTIFIABILITY_REQUIRED = 4
FEATURES = ("kind", "colors", "shapes", "pixels", "bbox_size", "role")
AUTHORING_ROLES = {"settled", "solved_terminal", "next_level_initial"}
GRID = 64
PURITY_MIN = 0.5
COVERAGE_MIN = 0.8
UNEVALUABLE_RELATIONS = {"flanks", "matches_required_attributes", "inside"}


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def frozen_section_digest() -> str:
    text = NOTE.read_text(encoding="utf-8")
    start = text.index("### 3.4 Sprint A-R pre-registration")
    end = text.index("## 4.", start)
    return hashlib.sha256(text[start:end].encode()).hexdigest()


# ---------------------------------------------------------------------------- registries


def _modal_color(grid: list) -> int:
    return Counter(
        grid[row][col] for row in range(GRID) for col in range(GRID)
    ).most_common(1)[0][0]


def _atomic_object(handle: Any) -> dict[str, Any]:
    component = handle.component
    return {
        "id": handle.track_id,
        "kind": "atomic",
        "members": [handle.track_id],
        "colors": [component.color],
        "shapes": [component.shape],
        "pixels": component.pixels,
        "bbox": list(component.bbox),
        "centroid": list(component.centroid),
        "cells": sorted(component.cells),
        "role": handle.role,
        "occluded": False,
    }


def _ring_decompose(obj: dict[str, Any]) -> list[dict[str, Any]]:
    """R-2: bbox-perimeter ring plus connected interior remainder, once, no constants."""
    top, left, bottom, right = obj["bbox"]
    if bottom - top < 2 or right - left < 2:
        return []
    cells = {tuple(cell) for cell in obj["cells"]}
    perimeter = {
        (row, col)
        for row in range(top, bottom + 1)
        for col in range(left, right + 1)
        if row in (top, bottom) or col in (left, right)
    }
    if not perimeter <= cells:
        return []
    interior = cells - perimeter
    if not interior:
        return []
    color = obj["colors"][0]

    def derived(name: str, part: set[tuple[int, int]]) -> dict[str, Any]:
        rows = [row for row, _ in part]
        cols = [col for _, col in part]
        return {
            "id": f"{obj['id']}:{name}",
            "kind": "atomic",
            "members": [f"{obj['id']}:{name}"],
            "colors": [color],
            "shapes": [_shape(part, color)],
            "pixels": len(part),
            "bbox": [min(rows), min(cols), max(rows), max(cols)],
            "centroid": [
                min(part, key=lambda c: ((c[0] - sum(rows) / len(rows)) ** 2
                                         + (c[1] - sum(cols) / len(cols)) ** 2, c))[0],
                min(part, key=lambda c: ((c[0] - sum(rows) / len(rows)) ** 2
                                         + (c[1] - sum(cols) / len(cols)) ** 2, c))[1],
            ],
            "cells": sorted(part),
            "role": obj["role"],
            "occluded": obj["occluded"],
            "derived_from": obj["id"],
        }

    out = [derived("ring", perimeter)]
    remaining = set(interior)
    part_index = 0
    while remaining:
        seed = min(remaining)
        remaining.remove(seed)
        part = {seed}
        stack = [seed]
        while stack:
            row, col = stack.pop()
            for drow, dcol in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                neighbor = (row + drow, col + dcol)
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    part.add(neighbor)
                    stack.append(neighbor)
        out.append(derived(f"int{part_index}", part))
        part_index += 1
    return out


def _composites(objects: list[dict[str, Any]], background: int) -> list[dict[str, Any]]:
    """R-1: adjacent pairs and maximal adjacency clusters of non-background objects."""
    pool = [obj for obj in objects if background not in obj["colors"]]
    cell_sets = [frozenset(tuple(cell) for cell in obj["cells"]) for obj in pool]
    boxes = [obj["bbox"] for obj in pool]
    parent = list(range(len(pool)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    pairs = []
    for i in range(len(pool)):
        top_i, left_i, bottom_i, right_i = boxes[i]
        for j in range(i + 1, len(pool)):
            top_j, left_j, bottom_j, right_j = boxes[j]
            if (
                top_j > bottom_i + 1
                or top_i > bottom_j + 1
                or left_j > right_i + 1
                or left_i > right_j + 1
            ):
                continue
            small, large = sorted((cell_sets[i], cell_sets[j]), key=len)
            if any(
                (row + drow, col + dcol) in large
                for row, col in small
                for drow, dcol in ((-1, 0), (1, 0), (0, -1), (0, 1))
            ):
                left_root, right_root = find(i), find(j)
                if left_root != right_root:
                    parent[right_root] = left_root
                pairs.append((i, j))
    clusters: dict[int, list[int]] = {}
    for index in range(len(pool)):
        clusters.setdefault(find(index), []).append(index)
    member_lists = [list(pair) for pair in pairs] + [
        members for members in clusters.values() if len(members) >= 2
    ]
    groups = []
    seen: set[str] = set()
    for members in member_lists:
        chosen = [pool[index] for index in members]
        ids = sorted(obj["id"] for obj in chosen)
        group_id = "g:" + "+".join(ids)
        if group_id in seen:
            continue
        seen.add(group_id)
        cells = set()
        for obj in chosen:
            cells.update(tuple(cell) for cell in obj["cells"])
        rows = [row for row, _ in cells]
        cols = [col for _, col in cells]
        groups.append(
            {
                "id": group_id,
                "kind": "group",
                "members": ids,
                "colors": sorted({color for obj in chosen for color in obj["colors"]}),
                "shapes": sorted(shape for obj in chosen for shape in obj["shapes"]),
                "pixels": len(cells),
                "bbox": [min(rows), min(cols), max(rows), max(cols)],
                "centroid": [sum(rows) / len(rows), sum(cols) / len(cols)],
                "cells": sorted(cells),
                "role": sorted({obj["role"] for obj in chosen}
                               if all(isinstance(obj["role"], str) for obj in chosen)
                               else {r for obj in chosen for r in obj["role"]}),
                "occluded": any(obj["occluded"] for obj in chosen),
            }
        )
    return sorted(groups, key=lambda group: group["id"])


class PermanenceTracker:
    """R-4: Tracker plus occlusion carryover at theta_occ = 1.0."""

    def __init__(self) -> None:
        self.tracker = Tracker()
        self.occluded: dict[str, dict[str, Any]] = {}
        self.last_observation: Any = None

    def reset_level(self) -> None:
        self.tracker.reset_level()
        self.occluded.clear()

    def update(
        self,
        grid: list,
        *,
        previous_grid: list | None,
        action_id: int,
        action_data: dict[str, Any],
    ) -> None:
        previous = {handle.track_id: handle for handle in self.tracker.handles}
        observation = self.tracker.update(
            grid,
            previous_grid=previous_grid,
            action_id=action_id,
            action_data=action_data,
        )
        self.last_observation = observation
        background = _modal_color(grid)
        cover: dict[tuple[int, int], int] = {}
        for handle in observation.handles:
            if handle.component.color == background:
                continue
            for cell in handle.component.cells:
                cover[cell] = handle.component.color
        for event in observation.events:
            if event["type"] == "disappear":
                old = previous.get(event["track"])
                if old is None:
                    continue
                covered = all(cell in cover for cell in old.component.cells)
                if covered:
                    record = _atomic_object(old)
                    record["occluded"] = True
                    self.occluded[old.track_id] = record
            elif event["type"] == "appear":
                new = next(
                    (
                        handle
                        for handle in observation.handles
                        if handle.track_id == event["track"]
                    ),
                    None,
                )
                if new is None:
                    continue
                for track_id, record in list(self.occluded.items()):
                    if (
                        record["colors"] == [new.component.color]
                        and record["shapes"] == [new.component.shape]
                        and set(map(tuple, record["cells"])) & new.component.cells
                    ):
                        del self.occluded[track_id]
        for track_id in [t for t in self.occluded if t in
                         {h.track_id for h in observation.handles}]:
            del self.occluded[track_id]

    def registry(self, grid: list) -> dict[str, Any]:
        background = _modal_color(grid)
        atomics = [_atomic_object(handle) for handle in self.tracker.handles]
        atomics += [copy.deepcopy(record) for record in self.occluded.values()]
        derived = []
        for obj in atomics:
            derived.extend(_ring_decompose(obj))
        base = atomics + derived
        state: dict[str, Any] = {
            "objects_base": base,
            "background": background,
            "groups": None,
        }
        return state


def _state_objects(state: dict[str, Any], *, need_groups: bool) -> list[dict[str, Any]]:
    if need_groups and state["groups"] is None:
        state["groups"] = _composites(state["objects_base"], state["background"])
    return state["objects_base"] + (state["groups"] or [] if need_groups else [])


def _feature_value(obj: dict[str, Any], feature: str) -> Any:
    if feature == "bbox_size":
        top, left, bottom, right = obj["bbox"]
        return [bottom - top + 1, right - left + 1]
    return obj[feature]


# ------------------------------------------------------------------------- descriptors


def _terms_need_groups(descriptor: dict[str, Any]) -> bool:
    return any(
        term["feature"] == "kind" and term["value"] == "group"
        for conj in descriptor["union"]
        for term in conj
    ) or not any(
        term["feature"] == "kind"
        for conj in descriptor["union"]
        for term in conj
    )


def _extension(descriptor: dict[str, Any], state: dict[str, Any]) -> list[str]:
    cache = state.setdefault("_ext", {})
    if descriptor["id"] in cache:
        return cache[descriptor["id"]]
    objects = _state_objects(state, need_groups=_terms_need_groups(descriptor))
    members: set[str] = set()
    for conjunction in descriptor["union"]:
        for obj in objects:
            if all(
                _canonical(_feature_value(obj, term["feature"]))
                == _canonical(term["value"])
                for term in conjunction
            ):
                members.add(obj["id"])
    result = sorted(members)
    cache[descriptor["id"]] = result
    return result


def _descriptor(union: list[list[dict[str, Any]]]) -> dict[str, Any]:
    canonical_union = sorted(
        (sorted(conj, key=_canonical) for conj in union), key=_canonical
    )
    key = _canonical(canonical_union)
    return {
        "id": "d" + hashlib.sha256(key.encode()).hexdigest()[:12],
        "union": [list(conj) for conj in canonical_union],
        "n_terms": sum(len(conj) for conj in canonical_union),
    }


def enumerate_conjunctions(
    annotated: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """All distinct-extension conjunction descriptors (arity <= 2), minimal per signature."""
    values: dict[str, dict[str, Any]] = {}
    for state in annotated:
        for obj in _state_objects(state["registry"], need_groups=True):
            for arity in (1, 2):
                for names in itertools.combinations(FEATURES, arity):
                    terms = [
                        {"feature": name, "value": _feature_value(obj, name)}
                        for name in names
                    ]
                    values.setdefault(_canonical(terms), {"terms": terms})
    signatures: dict[str, dict[str, Any]] = {}
    for definition in values.values():
        descriptor = _descriptor([definition["terms"]])
        extensions = [_extension(descriptor, state["registry"]) for state in annotated]
        if not any(extensions):
            continue
        signature = _canonical(extensions)
        incumbent = signatures.get(signature)
        if incumbent is None or (
            descriptor["n_terms"],
            _canonical(descriptor["union"]),
        ) < (incumbent["n_terms"], _canonical(incumbent["union"])):
            descriptor = dict(descriptor)
            descriptor["extensions"] = extensions
            signatures[signature] = descriptor
    return sorted(
        signatures.values(),
        key=lambda item: (item["n_terms"], _canonical(item["union"])),
    )


def select_gold_descriptor(
    conjunctions: list[dict[str, Any]],
    annotated: list[dict[str, Any]],
    set_name: str,
) -> dict[str, Any] | None:
    """R-3: exact conjunction, else greedy exact DNF union of at most U conjunctions."""
    gold = [sorted(state["gold_extensions"][set_name]) for state in annotated]
    for descriptor in conjunctions:
        if descriptor["extensions"] == gold:
            return descriptor
    gold_sets = [set(extension) for extension in gold]
    eligible = [
        descriptor
        for descriptor in conjunctions
        if all(
            set(extension) <= gold_state
            for extension, gold_state in zip(descriptor["extensions"], gold_sets)
        )
        and any(descriptor["extensions"])
    ]
    chosen: list[dict[str, Any]] = []
    covered = [set() for _ in gold_sets]
    for _ in range(U_UNION):
        if all(cover == gold_state for cover, gold_state in zip(covered, gold_sets)):
            break
        best = None
        best_gain = 0
        for descriptor in eligible:
            gain = sum(
                len((set(extension) - cover))
                for extension, cover in zip(descriptor["extensions"], covered)
            )
            if gain > best_gain or (
                best is not None
                and gain == best_gain
                and (descriptor["n_terms"], _canonical(descriptor["union"]))
                < (best["n_terms"], _canonical(best["union"]))
            ):
                best, best_gain = descriptor, gain
        if best is None or best_gain == 0:
            break
        chosen.append(best)
        covered = [
            cover | set(extension)
            for cover, extension in zip(covered, best["extensions"])
        ]
    if chosen and all(
        cover == gold_state for cover, gold_state in zip(covered, gold_sets)
    ):
        merged = _descriptor([conj for item in chosen for conj in item["union"]])
        merged["extensions"] = [
            sorted(set().union(*(set(item["extensions"][index]) for item in chosen)))
            for index in range(len(annotated))
        ]
        return merged
    return None


# ------------------------------------------------------------------ grounding (gate 1)


def _map_sprite(game: Any, sprite: Any, grid: list, state: dict[str, Any]) -> dict[str, Any]:
    """Sprint A mapping semantics first; R-2 derived objects only as a rescue.

    A component that already grounds a sprite keeps doing so exactly as in Sprint A; ring
    and interior parts enter the mapping only when the undecomposed vocabulary fails, so
    R-2 cannot silently re-ground entities that never needed it.
    """
    projected = projected_sprite_cells(game, sprite)
    visible = {
        (row, col)
        for row, col, colour in projected
        if 0 <= row < GRID and 0 <= col < GRID and int(grid[row][col]) == colour
    }
    objects = _state_objects(state, need_groups=True)

    def attempt(include_derived: bool) -> dict[str, Any]:
        hits = []
        covered: set[tuple[int, int]] = set()
        for obj in objects:
            if obj["kind"] != "atomic":
                continue
            # Grounding compares VISIBLE sprite pixels to the frame's components;
            # occluded carryovers are not visible and are evaluation-side objects only
            # (R-4 "sets and relations"), never grounding targets.
            if obj["occluded"]:
                continue
            if bool(obj.get("derived_from")) != include_derived:
                continue
            cells = {tuple(cell) for cell in obj["cells"]}
            overlap = visible & cells
            if not overlap:
                continue
            purity = len(overlap) / len(cells)
            if purity < PURITY_MIN:
                continue
            hits.append(obj["id"])
            covered |= overlap
        coverage = len(covered) / len(visible) if visible else 0.0
        groups = sorted(
            obj["id"]
            for obj in objects
            if obj["kind"] == "group" and set(obj["members"]) == set(hits)
        )
        mapped_id = None
        if coverage >= COVERAGE_MIN:
            if len(hits) == 1:
                mapped_id = hits[0]
            elif groups:
                mapped_id = groups[0]
        return {
            "visible": len(visible),
            "coverage": round(coverage, 6),
            "handles": sorted(hits),
            "groups": groups,
            "mapped": mapped_id is not None,
            "mapped_id": mapped_id,
        }

    primary = attempt(include_derived=False)
    if primary["mapped"]:
        return primary
    rescue = attempt(include_derived=True)
    return rescue if rescue["mapped"] else primary


# ----------------------------------------------------------------------- session walk


def _role_frame_fidelity(replayed: list, recorded_frames: list, roles: tuple) -> bool:
    """Erratum fidelity: settled / solved / next-level frames only."""
    if len(replayed) != len(recorded_frames):
        return False
    for index, role in enumerate(roles):
        if role in AUTHORING_ROLES and replayed[index] != recorded_frames[index]:
            return False
    return True


def _plain(frames: list) -> list:
    return [frame.tolist() if hasattr(frame, "tolist") else frame for frame in frames]


def _candidate_actions_ar(available, representatives, recorded):
    candidates = []
    for action_id in sorted(set(available)):
        if action_id == 0:
            continue
        if action_id == 6:
            for row, col in representatives:
                data = {"x": col, "y": row}
                if recorded.action_id == 6 and recorded.action_data == data:
                    continue
                candidates.append({"action_id": 6, "action_data": data})
        else:
            if recorded.action_id == action_id and not recorded.action_data:
                continue
            candidates.append({"action_id": action_id, "action_data": {}})
    return candidates


def walk_game(env: str, fork_table: dict[str, Any]) -> dict[str, Any]:
    draw = json.loads(DRAW.read_text())
    sessions_doc = json.loads(SESSIONS.read_text())
    gold_record = next(
        row for row in json.loads(GOLD.read_text())["records"] if row["env"] == env
    )
    set_names = gold_record["vocabulary"]["sets"]
    table_game = next(
        (game for game in fork_table["games"] if game["env"] == env), None
    )
    table_forks: dict[tuple[str, int], list[dict[str, Any]]] = {}
    if table_game and table_game.get("fork_eligible"):
        for session in table_game["sessions"]:
            for completion in session["completions"]:
                table_forks[(session["guid"], completion["step"])] = completion["forks"]

    annotated: list[dict[str, Any]] = []
    solved: list[dict[str, Any]] = []
    trajectory: list[dict[str, Any]] = []
    fork_states: list[dict[str, Any]] = []
    vc33_generated: list[dict[str, Any]] = []
    groundings: dict[tuple[str, str], dict[str, Any]] = {}
    authoring_stopped: list[str] = []
    generate_vc33 = env == "vc33"

    for selected in selected_sessions(env, sessions_doc, draw):
        path = CORPUS / env / f"{selected['guid']}.recording.jsonl"
        driver = ReplayDriver(env)
        game = driver.new_game()
        tracker = PermanenceTracker()
        previous_grid = None
        previous_levels = 0
        previous_available: tuple[int, ...] = ()
        pending_trajectory: list[dict[str, Any]] = []
        authoring = True
        for action in iter_recorded_actions(path):
            increment = action.levels_completed - previous_levels
            if increment and authoring:
                if previous_grid is None:
                    raise ValueError(f"{env}: completion lacks pre-state")
                pre_state = tracker.registry(previous_grid)
                extensions: dict[str, list[str]] = {}
                all_mapped = True
                for set_name in set_names:
                    ids = []
                    for index, sprite in enumerate(
                        semantic_sprites(env, game)[set_name]
                    ):
                        digest = hashlib.sha256(
                            f"{game.level_index}:{set_name}:{index}:{sprite.name}".encode()
                        ).hexdigest()[:16]
                        mapping = _map_sprite(game, sprite, previous_grid, pre_state)
                        key = (set_name, digest)
                        incumbent = groundings.get(key)
                        if incumbent is None or (
                            mapping["mapped"],
                            mapping["coverage"],
                        ) > (incumbent["mapped"], incumbent["coverage"]):
                            groundings[key] = mapping
                        if mapping["mapped"]:
                            ids.append(mapping["mapped_id"])
                        else:
                            all_mapped = False
                    extensions[set_name] = ids
                if all_mapped:
                    annotated.append(
                        {
                            "_session": selected["guid"],
                            "registry": pre_state,
                            "gold_extensions": extensions,
                        }
                    )
                recorded_forks = table_forks.get((selected["guid"], action.step), [])
                if generate_vc33:
                    representatives = (
                        tracker.last_observation.mouse_representatives
                        if tracker.last_observation
                        else []
                    )
                    generated = []
                    for candidate in _candidate_actions_ar(
                        previous_available,
                        representatives,
                        action,
                    ):
                        branch = copy.deepcopy(game)
                        response = driver.perform(
                            branch,
                            ActionInput(
                                id=GameAction.from_id(candidate["action_id"]),
                                data=candidate["action_data"],
                            ),
                        )
                        completed = int(response.levels_completed or 0) > previous_levels
                        frames = _plain(response.frame or [])
                        if not frames:
                            continue
                        state_name = str(
                            getattr(response.state, "value", response.state)
                        )
                        terminal = (
                            frames[-2]
                            if completed and state_name != "WIN" and len(frames) >= 2
                            else frames[-1]
                        )
                        generated.append(
                            {
                                **candidate,
                                "completed": completed,
                                "state": state_name,
                                "terminal_grid_rle": encode_grid(terminal),
                            }
                        )
                    vc33_generated.append(
                        {
                            "guid": selected["guid"],
                            "step": action.step,
                            "level": action.levels_completed,
                            "pre_grid_rle": encode_grid(previous_grid),
                            "forks": generated,
                        }
                    )
                    recorded_forks = generated
                for fork in recorded_forks:
                    if fork.get("terminal_grid_rle") is None:
                        continue
                    branch_tracker = copy.deepcopy(tracker)
                    fork_grid = decode_grid(fork["terminal_grid_rle"])
                    branch_tracker.update(
                        fork_grid,
                        previous_grid=previous_grid,
                        action_id=fork["action_id"],
                        action_data=fork.get("action_data") or {},
                    )
                    fork_states.append(
                        {
                            "registry": branch_tracker.registry(fork_grid),
                            "completed": bool(fork["completed"]),
                        }
                    )

            response = driver.perform(
                game,
                ActionInput(
                    id=GameAction.from_id(action.action_id),
                    data=action.action_data or {},
                ),
            )
            replayed = _plain(response.frame or [])
            roles = frame_roles(
                state=action.state,
                n_frames=len(action.frames),
                completion_increment=increment,
            )
            if authoring and not _role_frame_fidelity(replayed, action.frames, roles):
                authoring_stopped.append(
                    f"{selected['guid'][:8]}@step{action.step}"
                )
                authoring = False
            for index, (grid, role) in enumerate(zip(action.frames, roles)):
                if role not in AUTHORING_ROLES:
                    continue
                if role == "next_level_initial":
                    tracker.reset_level()
                    previous_grid = None
                tracker.update(
                    grid,
                    previous_grid=previous_grid,
                    action_id=action.action_id,
                    action_data=action.action_data,
                )
                previous_grid = grid
                if role == "solved_terminal":
                    solved.append({"registry": tracker.registry(grid)})
                elif role == "settled" and not increment:
                    pending_trajectory.append({"registry": tracker.registry(grid)})
            previous_levels = action.levels_completed
            previous_available = action.available_actions
        stride = max(1, -(-len(pending_trajectory) // TRAJECTORY_CAP_PER_SESSION))
        trajectory.extend(pending_trajectory[::stride])

    by_entity: dict[str, list[dict[str, Any]]] = {}
    for (set_name, digest), mapping in groundings.items():
        by_entity.setdefault(set_name, []).append(mapping)
    entity_summary = {
        set_name: {
            "entities": len(items),
            "mapped_entities": sum(item["mapped"] for item in items),
        }
        for set_name, items in sorted(by_entity.items())
    }
    representable = bool(by_entity) and all(
        item["mapped"]
        for items in by_entity.values()
        for item in items
    )
    return {
        "env": env,
        "gold_record": gold_record,
        "annotated": annotated,
        "solved": solved,
        "trajectory": trajectory,
        "fork_states": fork_states,
        "vc33_generated": vc33_generated,
        "entity_summary": entity_summary,
        "representable": representable,
        "authoring_stopped": authoring_stopped,
    }


# ------------------------------------------------------------- candidates + evaluation


def iter_candidates(set_ids: list[str]) -> Iterator[dict[str, Any]]:
    """Lazy pass over the finite GIDSL space (mirrors generate_finite_candidates)."""
    if len(set_ids) <= 6:
        yield from generate_finite_candidates(set_handles=set_ids)
        return
    for left, right in itertools.permutations(sorted(set_ids), 2):
        yield from generate_finite_candidates(set_handles=[left, right])
    for single in sorted(set_ids):
        yield from generate_finite_candidates(set_handles=[single])


def _weakened_gold(record: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    used: set[str] = set()

    def scan(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("op") == "relation":
                used.add(node["name"])
            if node.get("op") == "local_template_match":
                used.add("local_template_match")
            for value in node.values():
                scan(value)
        elif isinstance(node, list):
            for item in node:
                scan(item)

    scan(record["ast"])
    if "local_template_match" in used:
        return None, False
    if not used & UNEVALUABLE_RELATIONS:
        return record["ast"], False

    def prune(node: Any) -> Any:
        if isinstance(node, dict):
            if node.get("op") == "and":
                kept = [
                    prune(child)
                    for child in node["args"]
                    if not (
                        child.get("op") == "relation"
                        and child["name"] in UNEVALUABLE_RELATIONS
                    )
                ]
                return kept[0] if len(kept) == 1 else {"op": "and", "args": kept}
            return {k: prune(v) if k != "op" else v for k, v in node.items()}
        if isinstance(node, list):
            return [prune(item) for item in node]
        return node

    return prune(record["ast"]), True


def _holds(ast: dict[str, Any], state: dict[str, Any], set_descriptors) -> bool:
    sets = {
        name: _extension(descriptor, state["registry"])
        for name, descriptor in set_descriptors.items()
    }
    need_groups = any(
        _terms_need_groups(descriptor) for descriptor in set_descriptors.values()
    )
    cache_key = "_objects_g" if need_groups else "_objects_a"
    objects_cache = state["registry"].get(cache_key)
    if objects_cache is None:
        objects = _state_objects(state["registry"], need_groups=need_groups)
        objects_cache = {
            obj["id"]: {
                "cells": obj["cells"],
                "colors": obj["colors"],
                "centroid": obj["centroid"],
            }
            for obj in objects
        }
        state["registry"][cache_key] = objects_cache
    try:
        return bool(
            evaluate_ast(ast, sets=sets, objects=objects_cache, events={})
        )
    except (NotImplementedError, KeyError, TypeError):
        return False


def _candidate_key(candidate: dict[str, Any]) -> str:
    return _canonical(
        {
            "class": candidate["class"],
            "skeleton": candidate["skeleton"],
            "ast": canonicalize_ast(candidate["ast"]),
        }
    )


def identify(walked: dict[str, Any]) -> dict[str, Any]:
    env = walked["env"]
    gold_record = walked["gold_record"]
    annotated = walked["annotated"]
    conjunctions = enumerate_conjunctions(annotated)
    gold_descriptors: dict[str, Any] = {}
    for set_name in gold_record["vocabulary"]["sets"]:
        gold_descriptors[set_name] = select_gold_descriptor(
            conjunctions, annotated, set_name
        )
    result: dict[str, Any] = {
        "gold_descriptors": {
            name: (
                {"union": item["union"], "n_terms": item["n_terms"]}
                if item
                else None
            )
            for name, item in gold_descriptors.items()
        },
        "n_conjunction_descriptors": len(conjunctions),
    }
    if any(item is None for item in gold_descriptors.values()):
        result["identifiable"] = False
        result["reason"] = "gold set not expressible as a U<=4 DNF descriptor"
        return result

    gold_ast, weakened = _weakened_gold(gold_record)
    if gold_ast is None:
        result["identifiable"] = False
        result["reason"] = "gold predicate mechanically unevaluable (declared limit)"
        return result

    stable = [
        descriptor
        for descriptor in conjunctions
        if all(descriptor["extensions"])
    ]
    vocabulary = {descriptor["id"]: descriptor for descriptor in stable}
    for item in gold_descriptors.values():
        vocabulary[item["id"]] = item
    set_lookup = dict(vocabulary)
    result["n_stable_sets"] = len(stable)
    result["n_vocabulary_sets"] = len(vocabulary)

    solved = walked["solved"]
    trajectory = walked["trajectory"]
    forks = walked["fork_states"]
    negatives = [state for state in forks if not state["completed"]]
    positives = [state for state in forks if state["completed"]]

    def holds_with(candidate_ast, state, referenced: dict[str, Any]) -> bool:
        return _holds(candidate_ast, state, referenced)

    def referenced_sets(ast: Any) -> dict[str, Any]:
        names: set[str] = set()

        def scan(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("op") == "set":
                    names.add(node["name"])
                for value in node.values():
                    scan(value)
            elif isinstance(node, list):
                for item in node:
                    scan(item)

        scan(ast)
        return {name: set_lookup[name] for name in names if name in set_lookup}

    gold_sets = {name: item for name, item in gold_descriptors.items()}
    gold_key = _candidate_key(
        {
            "class": gold_record["class"],
            "skeleton": gold_record["skeleton"],
            "ast": _substitute_sets(gold_ast, {name: item["id"] for name, item in gold_descriptors.items()}),
        }
    )

    survivors: dict[str, dict[str, Any]] = {}
    n_seen = 0
    for candidate in iter_candidates(sorted(vocabulary)):
        n_seen += 1
        referenced = referenced_sets(candidate["ast"])
        alive = True
        for state in solved:
            if not holds_with(candidate["ast"], state, referenced):
                alive = False
                break
        if not alive:
            continue
        key = _candidate_key(candidate)
        if key in survivors:
            continue
        trajectory_bits = [
            holds_with(candidate["ast"], state, referenced) for state in trajectory
        ]
        rate = (
            sum(trajectory_bits) / len(trajectory_bits) if trajectory_bits else None
        )
        if rate is None or rate >= 1.0:
            continue
        negative_bits = [
            holds_with(candidate["ast"], state, referenced) for state in negatives
        ]
        positive_bits = [
            holds_with(candidate["ast"], state, referenced) for state in positives
        ]
        survivors[key] = {
            "candidate": candidate,
            "key": key,
            "trajectory_rate": rate,
            "vector": tuple(trajectory_bits) + tuple(negative_bits) + tuple(positive_bits),
            "fork_survives": not any(negative_bits) and all(positive_bits),
            "complexity": len(key),
        }
    result["candidates_seen"] = n_seen
    result["survivors_trajectory"] = len(survivors)

    gold_vector = None
    gold_row = survivors.get(gold_key)
    if gold_row is None:
        referenced = gold_sets
        gold_solved = all(
            holds_with(_substitute_sets(gold_ast, {n: i["id"] for n, i in gold_descriptors.items()}), state, referenced)
            for state in solved
        )
        result["gold_solved_all_true"] = gold_solved
    else:
        result["gold_solved_all_true"] = True
        gold_vector = gold_row["vector"]

    ranked = sorted(
        survivors.values(),
        key=lambda row: (row["trajectory_rate"], row["complexity"], row["key"]),
    )
    equivalence_keys = (
        {row["key"] for row in survivors.values() if row["vector"] == gold_vector}
        if gold_vector is not None
        else set()
    )
    trajectory_rank = next(
        (
            index + 1
            for index, row in enumerate(ranked)
            if row["key"] == gold_key or row["key"] in equivalence_keys
        ),
        None,
    )
    fork_ranked = [row for row in ranked if row["fork_survives"]]
    fork_rank = next(
        (
            index + 1
            for index, row in enumerate(fork_ranked)
            if row["key"] == gold_key or row["key"] in equivalence_keys
        ),
        None,
    )
    result.update(
        {
            "gold_weakened": weakened,
            "gold_in_survivors": gold_row is not None,
            "equivalence_class_size": len(equivalence_keys),
            "trajectory_rank": trajectory_rank,
            "fork_survivors": len(fork_ranked),
            "fork_rank": fork_rank,
            "identifiable": trajectory_rank is not None and trajectory_rank <= TOP_K,
            "top": [
                {
                    "class": row["candidate"]["class"],
                    "skeleton": row["candidate"]["skeleton"],
                    "trajectory_rate": row["trajectory_rate"],
                    "is_gold_or_equivalent": row["key"] == gold_key
                    or row["key"] in equivalence_keys,
                }
                for row in ranked[:5]
            ],
        }
    )

    # R-6: elimination distribution per fork action over solved-surviving candidates.
    eliminations = []
    for state in forks:
        eliminated = 0
        for row in survivors.values():
            referenced = referenced_sets(row["candidate"]["ast"])
            true_here = holds_with(row["candidate"]["ast"], state, referenced)
            if (true_here and not state["completed"]) or (
                not true_here and state["completed"]
            ):
                eliminated += 1
        eliminations.append(eliminated)
    result["r6_elimination"] = {
        "n_fork_outcomes": len(eliminations),
        "mean": (sum(eliminations) / len(eliminations)) if eliminations else None,
        "max": max(eliminations) if eliminations else None,
        "note": (
            "distribution over all fork actions; the catalogue selection-policy "
            "numerator awaits Sprint C's frozen policy"
        ),
    }
    return result


def _substitute_sets(node: Any, mapping: dict[str, str]) -> Any:
    if isinstance(node, dict):
        if node.get("op") == "set":
            return {"op": "set", "name": mapping.get(node["name"], node["name"])}
        return {k: _substitute_sets(v, mapping) if k != "op" else v for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute_sets(item, mapping) for item in node]
    return node


# ------------------------------------------------------------------------------ build


def _current_freeze() -> dict[str, Any]:
    return {
        "format_version": FORMAT_VERSION,
        "status": "ar_frozen",
        "frozen_values": {
            "U": U_UNION,
            "theta_occ": THETA_OCC,
            "top_k": TOP_K,
            "trajectory_cap_per_session": TRAJECTORY_CAP_PER_SESSION,
            "gates": {
                "representability": REPRESENTABILITY_REQUIRED,
                "identifiability_trajectory_only": IDENTIFIABILITY_REQUIRED,
            },
            "vc33_settled_frame_erratum": "accepted 2026-07-30",
        },
        "section_digest": frozen_section_digest(),
        "module_sha256": _sha256_path(Path(__file__).resolve()),
        "inputs": {
            "gold_sha256": _sha256_path(GOLD),
            "fork_table_sha256": _sha256_path(FORKS),
            "draw_sha256": _sha256_path(DRAW),
            "sessions_sha256": _sha256_path(SESSIONS),
        },
        "declared_readings": [
            "candidate vocabulary = stable minimal conjunction descriptors plus gold DNF",
            "occluded objects join composites via last-known cells",
            "vc33 flanks conjunct dropped (unevaluable); ft09 local_template_match "
            "unevaluable — ft09 counts for representability, not identifiability",
            "R-6 reports elimination distributions only; catalogue policy is Sprint C's",
            "authoring fidelity under the erratum compares settled/solved/next frames",
        ],
    }


def build_results() -> dict[str, Any]:
    freeze = json.loads(FREEZE_OUTPUT.read_text())
    expected = _current_freeze()
    for field in ("frozen_values", "section_digest", "module_sha256", "inputs"):
        if freeze.get(field) != expected[field]:
            raise ValueError(
                f"freeze drift on {field!r}: re-run --freeze only via a dated erratum"
            )
    fork_table = json.loads(FORKS.read_text())
    draw = json.loads(DRAW.read_text())
    games = []
    representable_count = 0
    identifiable_count = 0
    vc33_forks_document = None
    for env in draw["iteration"]:
        print(f"[{env}] walking sessions", flush=True)
        walked = walk_game(env, fork_table)
        print(
            f"[{env}] representable={walked['representable']} "
            f"annotated={len(walked['annotated'])} solved={len(walked['solved'])} "
            f"trajectory={len(walked['trajectory'])} forks={len(walked['fork_states'])}",
            flush=True,
        )
        row: dict[str, Any] = {
            "env": env,
            "representable": walked["representable"],
            "entity_summary": walked["entity_summary"],
            "authoring_stopped": walked["authoring_stopped"],
            "state_counts": {
                "annotated": len(walked["annotated"]),
                "solved": len(walked["solved"]),
                "trajectory": len(walked["trajectory"]),
                "fork_negatives": sum(
                    1 for s in walked["fork_states"] if not s["completed"]
                ),
                "fork_positives": sum(
                    1 for s in walked["fork_states"] if s["completed"]
                ),
            },
        }
        if walked["representable"]:
            representable_count += 1
        if walked["representable"] and walked["annotated"]:
            identification = identify(walked)
            row["identification"] = identification
            print(
                f"[{env}] vocab={identification.get('n_vocabulary_sets')} "
                f"seen={identification.get('candidates_seen')} "
                f"survivors={identification.get('survivors_trajectory')} "
                f"rank={identification.get('trajectory_rank')} "
                f"identifiable={identification.get('identifiable')}",
                flush=True,
            )
            if identification.get("identifiable"):
                identifiable_count += 1
        else:
            row["identification"] = None
        if env == "vc33":
            vc33_forks_document = {
                "format_version": FORMAT_VERSION,
                "status": "ar_erratum_regenerated",
                "erratum": "vc33 settled-frame fidelity, accepted 2026-07-30",
                "completions": walked["vc33_generated"],
                "totals": {
                    "completions": len(walked["vc33_generated"]),
                    "forks": sum(
                        len(item["forks"]) for item in walked["vc33_generated"]
                    ),
                    "negatives": sum(
                        1
                        for item in walked["vc33_generated"]
                        for fork in item["forks"]
                        if not fork["completed"]
                    ),
                },
            }
        games.append(row)
    if vc33_forks_document is not None:
        VC33_FORKS_OUTPUT.write_text(
            json.dumps(vc33_forks_document, indent=2) + "\n"
        )
    return {
        "format_version": FORMAT_VERSION,
        "status": "sprint_ar_measured",
        "scope": "iteration",
        "freeze_sha256": _sha256_path(FREEZE_OUTPUT),
        "vc33_forks_sha256": (
            _sha256_path(VC33_FORKS_OUTPUT) if VC33_FORKS_OUTPUT.exists() else None
        ),
        "games": games,
        "gates": {
            "representability": {
                "games": representable_count,
                "required": REPRESENTABILITY_REQUIRED,
                "passed": representable_count >= REPRESENTABILITY_REQUIRED,
            },
            "identifiability_trajectory_only": {
                "games": identifiable_count,
                "required": IDENTIFIABILITY_REQUIRED,
                "passed": identifiable_count >= IDENTIFIABILITY_REQUIRED,
            },
        },
        "second_failure_rule": (
            "a failure of either gate here is the second failure: permanent stop, "
            "budget routes to the action-semantics artifact"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--measure", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        if FREEZE_OUTPUT.exists() and OUTPUT.exists():
            print(
                "freeze exists and results are measured; changes require a dated erratum"
            )
            return 1
        if FREEZE_OUTPUT.exists():
            print("re-freezing during bring-up (no measured results exist yet)")
        FREEZE_OUTPUT.write_text(json.dumps(_current_freeze(), indent=2) + "\n")
        print(f"wrote {FREEZE_OUTPUT.relative_to(ROOT)}")
        return 0
    if args.measure:
        document = build_results()
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        for game in document["games"]:
            identification = game["identification"] or {}
            print(
                f"{game['env']}: representable={game['representable']} "
                f"identifiable={identification.get('identifiable')} "
                f"rank={identification.get('trajectory_rank')}",
                flush=True,
            )
        print(json.dumps(document["gates"], indent=2), flush=True)
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
        return 0
    if args.verify:
        try:
            current = json.loads(OUTPUT.read_text())
            rebuilt = json.loads(json.dumps(build_results()))
            problems = [] if current == rebuilt else ["artifact differs from rebuild"]
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            problems = [f"verification failed: {exc}"]
        if problems:
            print("Sprint A-R FAILED")
            for problem in problems:
                print("  " + problem)
            return 1
        print("Sprint A-R OK")
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
