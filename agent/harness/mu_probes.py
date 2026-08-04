#!/usr/bin/env python3
"""MU probe machinery: evidence windows, referent aliases, gold, floors, schemas.

Implements the zero-call half of ``notes/mu-representation-screen.md`` (MU, 2026-08-03)
under the numeric authority ``gate_manifest.yaml -> mu``. Scope of this module: the
evidence side only — window extraction from the replay estate, the referent-alias
protocol, the per-action effect catalogue, the five probe gold generators (MU-T1..MU-T5),
the five model-free floors, and the frozen per-probe output schemas with their parsers and
scorers. Rendering lives in ``mu_render.py``; inventory, freeze, run, and scoring drivers
live in ``mu_screen.py``.

Estate reuse (MU SS3): frames and frame roles come from ``gi2_traces``; components,
matching, and lineage come from ``gi2_observation``; forks come from the GI-2 fork tables
(including vc33's erratum-regenerated corpus); the session-role partition is the frozen ES
assignment republished in ``logs/es_inventory.json``. Nothing here re-authors an audited
assertion, and MU never reads a source adapter: every gold is engine- or replay-derived.

Determinizations recorded here (implementation level, published before any measured call;
the MU freeze pins this file's hash):

  * Objects. A MU object on a state is a GI-2 A2 observable component
    (``gi2_observation.observable_components``: same-colour 4-connected, dropping only an
    unambiguous full-screen background component). No further filtering: the modal-colour
    convention used by ``es_questions.pre_state_complexity`` is a complexity metric, not an
    object registry, and applying it here would silently delete legible objects.
  * Referent aliases. Per state, objects of one colour are ordered by
    ``(bbox_top, bbox_left, bbox_bottom, bbox_right, -pixels, min(cells))`` and named
    ``<colour_name>#<k>``, k from 1. The ordering key is a total order because components
    are cell-disjoint. Aliases are STATE-LOCAL descriptor programs in the ES SS4.1 sense —
    the same physical object may carry different aliases on two states — and the rule, not
    the table, is what the question states. Colour names mirror ``vp_questions.COLOR_NAMES``
    (VP Freeze 1); ``tests/test_mu_probes.py`` asserts the mirror.
  * Windows. A window is the last ``prefix_window`` transitions of the CURRENT level
    ending at the query state, and never crosses a level boundary or a RESET: identity
    across a level restart is not defined. The tracker is instantiated at the window's
    first state, so a window is self-contained and its lineage is window-local; handle
    roles (controlled/autonomous/static), which need whole-session history, are therefore
    not part of any MU representation.
  * Transition outcome vocabulary. For a pre-state object with track t:
    ``disappeared`` (t absent after), ``recoloured`` (same cells, different colour),
    ``unchanged`` (same cells, same colour), ``moved`` (post cells are the pre cells
    translated by a single (dr,dc), same colour). Anything else — and any object that is a
    split parent or a merge child in that transition — is ``deformed``: NOT in the frozen
    vocabulary, and such objects are excluded from the probes that name objects rather than
    being coerced into a wrong label. Exclusion counts are published in the inventory.
    ``appeared`` is reported as a count of post-state tracks with no ancestor.
  * Forks. Fork rows are read from ``logs/gi2_fork_table.json`` and, for vc33, from
    ``logs/gi2_ar_vc33_forks.json`` (accepted 2026-07-30 settled-frame erratum). A fork row
    is usable only when its stored ``pre_grid_rle`` equals the window's query grid — a
    byte-level authentication of the reuse, not an assumption. Fork outcomes are recomputed
    with a deep copy of the window tracker, exactly as ``gi2_forks`` did.
  * Closed action sets (MU SS2, T4/T5). Candidates are the completion's fork rows plus, for
    T5, the recorded completing action. The bounded fork-representative policy applies to
    ACTION6: its rows are ordered by (y, x) and hash-reduced to ``mouse_representative_cap``
    before options are drawn. Options are presented in frozen hash order as A1..An, so the
    recorded completing action never occupies a fixed position.
  * Selection. Every per-case choice (which state, which colour, which alias, which
    condition, which options) is a frozen hash order over ``sha256("mu:" + parts)``; ties
    break on the canonical key itself. Anchors are walked in hash order and the first
    ``cases_per_probe`` ELIGIBLE anchors are kept, bounded by ``anchor_slack_factor``;
    exhausting the slack is a published shortfall, never a silent resample.
  * Three-valued discipline (ES SS3.1 precedent). A probe case is emitted only when its gold
    is two-valued on every offered option; a case whose gold would depend on a ``deformed``
    outcome is ineligible and counted, never guessed.

Run:
  .venv/bin/python agent/harness/mu_probes.py --selftest
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_forks import decode_grid  # noqa: E402
from gi2_observation import Observation, Tracker  # noqa: E402
from gi2_traces import (  # noqa: E402
    CORPUS,
    ROLE_NEXT_LEVEL_INITIAL,
    ROLE_SETTLED,
    ROLE_SOLVED_TERMINAL,
    iter_trace,
)

FORK_TABLE = ROOT / "logs/gi2_fork_table.json"
AR_VC33_FORKS = ROOT / "logs/gi2_ar_vc33_forks.json"
ES_INVENTORY = ROOT / "logs/es_inventory.json"

FORMAT_VERSION = 1
GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")
MEASURED_ROLES = ("S", "C")
SEALED_ROLE = "R"
PROBES = ("T1", "T2", "T3", "T4", "T5")

# --- frozen numeric mirrors of gate_manifest.yaml -> mu (authority: the manifest) -------
# Every value below is PROPOSED until the mu block is accepted; mu_screen refuses to freeze
# while the block is DRAFT, and asserts these mirrors against the block when it is frozen.
PREFIX_WINDOW = {"T1": 4, "T2": 2, "T3": 4, "T4": 4, "T5": 4}
CONTEXT_WINDOW_TOKENS = 32768   # the frozen S1 local serving context
OUTPUT_HEADROOM_TOKENS = 512    # ES es_use.output_headroom_tokens_min, reused
PROMPT_TOKENS_MAX = CONTEXT_WINDOW_TOKENS - OUTPUT_HEADROOM_TOKENS
CASES_PER_PROBE_PER_GAME_PER_ROLE = {"T1": 2, "T2": 2, "T3": 2, "T4": 2, "T5": 2}
T3_EXECUTED_SHARE = 1           # of T3's 2 cases, 1 executed-action and 1 fork-action; the
                                # share is bound to the T3 count — at 2 it would leave zero
                                # fork-form cases and silently drop half of T3's design
ANCHOR_SLACK_FACTOR = 6         # anchors tried per case wanted, in frozen hash order
T1_ITEMS = ("count", "bbox", "size", "relation")
T2_ROWS_MAX = 8                 # B rows offered per identity case
T3_OBJECTS_PER_CASE = 4         # named referents per mechanics case
CLOSED_ACTION_OPTIONS = 6       # offered options for T4 and T5 when the game affords them
CLOSED_ACTION_OPTIONS_MIN = 3   # ls20/tu93 advertise three actions; below this a case is void
MOUSE_REPRESENTATIVE_CAP = 16   # bounded fork-representative policy (MU SS2)
MAP_LATTICE = 16                # map arm: 64 -> 16 lattice, factor 4
CARD_CLICK_BLOCK = 8            # card arm: ACTION6 cluster = 8x8 board blocks

# Mirror of vp_questions.COLOR_NAMES (VP Freeze 1, 2026-08-02). Duplicated rather than
# imported so the MU freeze does not take a hash dependency on a frozen VP module that also
# drags in Pillow; tests/test_mu_probes.py asserts byte equality with the VP table.
COLOR_NAMES = {
    0: "white", 1: "light_gray", 2: "gray", 3: "dark_gray", 4: "charcoal",
    5: "black", 6: "magenta", 7: "pink", 8: "red", 9: "blue",
    10: "light_blue", 11: "yellow", 12: "orange", 13: "maroon",
    14: "green", 15: "purple",
}

# Visual relation vocabulary, identical to the frozen ES grammar's (es_candidates.
# VISUAL_RELATIONS / _relation_holds). Duplicated for the same freeze-independence reason;
# tests/test_mu_probes.py asserts agreement with the ES implementation.
VISUAL_RELATIONS = ("adjacent", "bbox_overlap", "bbox_contains", "row_aligned", "col_aligned")

OUTCOME_KINDS = ("moved", "disappeared", "recoloured", "unchanged")
INELIGIBLE_OUTCOME = "deformed"
STATE_ROLES = (ROLE_SETTLED, ROLE_SOLVED_TERMINAL, ROLE_NEXT_LEVEL_INITIAL)
ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ====================================================================================
# Hashing, canonical order
# ====================================================================================


def _json_default(value: Any) -> str:
    """Only YAML date/datetime scalars are coerced, and only to ISO-8601.

    The manifest carries `drafted_on` / `frozen_on` as bare dates, which PyYAML returns as
    ``datetime.date``. Coercing them keeps the manifest-block fingerprint computable and
    stable; anything else still raises, so no unserializable object is ever silently
    fingerprinted as its repr.
    """
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value: Any) -> str:
    return sha256_bytes(canonical(value))


def hash_rank(seed: str, key: Any) -> tuple[str, str]:
    """Frozen selection order: sha256('mu:'+seed+'|'+canonical(key)), ties on the key."""
    encoded = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return (sha256_bytes(f"mu:{seed}|{encoded}".encode()), encoded)


def hash_order(items: list[Any], seed: str, key=lambda item: item) -> list[Any]:
    return sorted(items, key=lambda item: hash_rank(seed, key(item)))


# ====================================================================================
# Objects and the referent-alias protocol
# ====================================================================================


@dataclass(frozen=True)
class MuObject:
    alias: str
    track_id: str
    colour: int
    pixels: int
    bbox: tuple[int, int, int, int]
    centroid: tuple[int, int]
    cells: frozenset[tuple[int, int]] = field(repr=False, compare=False)

    @property
    def colour_name(self) -> str:
        return COLOR_NAMES[self.colour]

    def table_row(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "colour": self.colour_name,
            "value": self.colour,
            "pixels": self.pixels,
            "bbox": list(self.bbox),
            "centroid": list(self.centroid),
        }


def _alias_sort_key(handle) -> tuple:
    component = handle.component
    top, left, bottom, right = component.bbox
    return (top, left, bottom, right, -component.pixels, min(component.cells))


def build_registry(observation: Observation) -> tuple[MuObject, ...]:
    """Assign state-local rank aliases to one observation's handles."""
    by_colour: dict[int, list[Any]] = {}
    for handle in observation.handles:
        by_colour.setdefault(handle.component.color, []).append(handle)
    objects: list[MuObject] = []
    for colour in sorted(by_colour):
        for index, handle in enumerate(sorted(by_colour[colour], key=_alias_sort_key), 1):
            component = handle.component
            objects.append(
                MuObject(
                    alias=f"{COLOR_NAMES[colour]}#{index}",
                    track_id=handle.track_id,
                    colour=colour,
                    pixels=component.pixels,
                    bbox=tuple(component.bbox),
                    centroid=tuple(component.centroid),
                    cells=component.cells,
                )
            )
    objects.sort(key=lambda item: (item.bbox, -item.pixels, item.alias))
    return tuple(objects)


def relation_holds(name: str, left: MuObject, right: MuObject) -> bool:
    """Frozen visual relations; identical semantics to es_candidates._relation_holds."""
    ar1, ac1, ar2, ac2 = left.bbox
    br1, bc1, br2, bc2 = right.bbox
    if name == "adjacent":
        return any(
            (row + drow, col + dcol) in right.cells
            for row, col in left.cells
            for drow, dcol in ORTHOGONAL
        )
    if name == "bbox_overlap":
        return ar1 <= br2 and br1 <= ar2 and ac1 <= bc2 and bc1 <= ac2
    if name == "bbox_contains":
        return ar1 <= br1 and ac1 <= bc1 and br2 <= ar2 and bc2 <= ac2
    if name == "row_aligned":
        return ar1 <= br2 and br1 <= ar2
    if name == "col_aligned":
        return ac1 <= bc2 and bc1 <= ac2
    raise ValueError(f"not a visual relation: {name}")


def adjacency_lists(objects: tuple[MuObject, ...]) -> dict[str, list[str]]:
    """Per-object 4-adjacency, the only relation table rendered in full.

    A full pairwise matrix is quadratic in an object count that reaches 352 on m0r0; the
    adjacency list is linear in the true instances and every other frozen relation is
    derivable from the bounding boxes already in the object table.
    """
    owner: dict[tuple[int, int], str] = {}
    for item in objects:
        for cell in item.cells:
            owner[cell] = item.alias
    out: dict[str, set[str]] = {item.alias: set() for item in objects}
    for item in objects:
        for row, col in item.cells:
            for drow, dcol in ORTHOGONAL:
                other = owner.get((row + drow, col + dcol))
                if other is not None and other != item.alias:
                    out[item.alias].add(other)
                    out[other].add(item.alias)
    return {alias: sorted(neighbours) for alias, neighbours in out.items() if out[alias]}


# ====================================================================================
# States, transitions, evidence windows
# ====================================================================================


@dataclass
class StateView:
    step: int
    frame_index: int
    role: str
    level: int
    grid: list
    objects: tuple[MuObject, ...]
    action: dict[str, Any]
    available_actions: tuple[int, ...]
    split_parents: frozenset[str]
    merge_children: frozenset[str]
    starts_window: bool

    @property
    def key(self) -> str:
        return f"{self.step}.{self.frame_index}"

    @property
    def by_track(self) -> dict[str, MuObject]:
        return {item.track_id: item for item in self.objects}

    @property
    def by_alias(self) -> dict[str, MuObject]:
        return {item.alias: item for item in self.objects}


@dataclass
class Transition:
    pre: StateView
    post: StateView
    action: dict[str, Any]
    level_increment: int
    outcomes: dict[str, dict[str, Any]]   # pre alias -> {"kind", "delta"?}
    appeared: int
    no_op: bool
    changed_cells: int


@dataclass
class EvidenceWindow:
    env: str
    guid: str
    role: str
    probe: str
    states: list[StateView]
    transitions: list[Transition]
    tracker: Tracker

    @property
    def query(self) -> StateView:
        return self.states[-1]

    @property
    def anchor(self) -> str:
        return f"{self.env}:{self.guid}:{self.query.key}"


def _stub_records(path: Path) -> list[dict[str, Any]]:
    """Cheap skeleton pass: every state a session settles into, with no componentization."""
    stubs: list[dict[str, Any]] = []
    previous_levels = 0
    previous_key: str | None = None
    for step in iter_trace(path):
        for frame in step.frames:
            if frame.role not in STATE_ROLES:
                continue
            starts = (
                frame.role == ROLE_NEXT_LEVEL_INITIAL
                or previous_key is None
                or step.action_id == 0
                or step.full_reset
            )
            stubs.append(
                {
                    "step": step.index,
                    "frame_index": frame.index,
                    "role": frame.role,
                    "level": step.levels_completed,
                    "action": {"id": step.action_id, "data": dict(step.action_data)},
                    "available_actions": list(step.available_actions),
                    "starts_window": starts,
                    "level_increment": step.levels_completed - previous_levels
                    if frame.role == ROLE_SOLVED_TERMINAL
                    else 0,
                }
            )
            previous_key = f"{step.index}.{frame.index}"
        previous_levels = step.levels_completed
    return stubs


def window_members(stubs: list[dict[str, Any]], index: int, span: int) -> list[int] | None:
    """Indexes of the states forming a ``span``-transition window ending at ``index``."""
    members = [index]
    cursor = index
    while len(members) <= span:
        if stubs[cursor]["starts_window"]:
            break
        cursor -= 1
        if cursor < 0:
            return None
        members.append(cursor)
    members.reverse()
    return members if len(members) >= 2 else None


def _transition_outcomes(
    pre: StateView, post: StateView
) -> tuple[dict[str, dict[str, Any]], int]:
    post_by_track = post.by_track
    outcomes: dict[str, dict[str, Any]] = {}
    for item in pre.objects:
        if item.track_id in post.split_parents:
            outcomes[item.alias] = {"kind": INELIGIBLE_OUTCOME, "reason": "split"}
            continue
        after = post_by_track.get(item.track_id)
        if after is None:
            outcomes[item.alias] = {"kind": "disappeared"}
            continue
        if after.track_id in post.merge_children:
            outcomes[item.alias] = {"kind": INELIGIBLE_OUTCOME, "reason": "merge"}
            continue
        if after.cells == item.cells:
            outcomes[item.alias] = (
                {"kind": "unchanged"}
                if after.colour == item.colour
                else {"kind": "recoloured", "to": after.colour_name}
            )
            continue
        if after.colour == item.colour and len(after.cells) == len(item.cells):
            drow = after.bbox[0] - item.bbox[0]
            dcol = after.bbox[1] - item.bbox[1]
            if {(row + drow, col + dcol) for row, col in item.cells} == set(after.cells):
                outcomes[item.alias] = {"kind": "moved", "delta": [drow, dcol]}
                continue
        outcomes[item.alias] = {"kind": INELIGIBLE_OUTCOME, "reason": "reshaped"}
    pre_tracks = {item.track_id for item in pre.objects}
    appeared = sum(1 for item in post.objects if item.track_id not in pre_tracks)
    return outcomes, appeared


def _changed_cells(before: list, after: list) -> int:
    return sum(
        left != right
        for brow, arow in zip(before, after)
        for left, right in zip(brow, arow)
    )


def make_transition(
    pre: StateView, post: StateView, *, level_increment: int
) -> Transition:
    outcomes, appeared = _transition_outcomes(pre, post)
    changed = _changed_cells(pre.grid, post.grid)
    return Transition(
        pre=pre,
        post=post,
        action=post.action,
        level_increment=level_increment,
        outcomes=outcomes,
        appeared=appeared,
        no_op=changed == 0,
        changed_cells=changed,
    )


def _observe(tracker: Tracker, grid: list, previous_grid: list | None, stub: dict) -> tuple:
    observation = tracker.update(
        grid,
        previous_grid=previous_grid,
        action_id=stub["action"]["id"],
        action_data=stub["action"]["data"],
    )
    split_parents = frozenset(
        event["parent"] for event in observation.events if event["type"] == "split"
    )
    merge_children = frozenset(
        observation.handles[event["child_local"]].track_id
        for event in observation.events
        if event["type"] == "merge"
    )
    return observation, split_parents, merge_children


def build_window(
    env: str,
    guid: str,
    role: str,
    probe: str,
    stubs: list[dict[str, Any]],
    grids: dict[str, list],
    members: list[int],
) -> EvidenceWindow:
    """Self-contained window: the tracker starts at the window's first state."""
    tracker = Tracker()
    states: list[StateView] = []
    previous_grid: list | None = None
    for position, index in enumerate(members):
        stub = stubs[index]
        grid = grids[f"{stub['step']}.{stub['frame_index']}"]
        observation, split_parents, merge_children = _observe(
            tracker, grid, previous_grid, stub
        )
        states.append(
            StateView(
                step=stub["step"],
                frame_index=stub["frame_index"],
                role=stub["role"],
                level=stub["level"],
                grid=grid,
                objects=build_registry(observation),
                action=stub["action"],
                available_actions=tuple(stub["available_actions"]),
                split_parents=split_parents if position else frozenset(),
                merge_children=merge_children if position else frozenset(),
                starts_window=stub["starts_window"],
            )
        )
        previous_grid = grid
    transitions = [
        make_transition(
            states[position - 1],
            states[position],
            level_increment=stubs[members[position]]["level_increment"],
        )
        for position in range(1, len(states))
    ]
    return EvidenceWindow(
        env=env,
        guid=guid,
        role=role,
        probe=probe,
        states=states,
        transitions=transitions,
        tracker=tracker,
    )


def _branch_state(
    window: EvidenceWindow, grid: list, stub: dict[str, Any], role: str
) -> StateView:
    """Advance a DEEP COPY of the window tracker onto one successor state.

    The window itself is never advanced: the shown prefix must not acquire the state whose
    outcome a probe is about to ask for (MU SS2).
    """
    branch = copy.deepcopy(window.tracker)
    observation, split_parents, merge_children = _observe(
        branch, grid, window.query.grid, stub
    )
    return StateView(
        step=stub.get("step", window.query.step),
        frame_index=stub.get("frame_index", -1),
        role=role,
        level=stub.get("level", window.query.level),
        grid=grid,
        objects=build_registry(observation),
        action=stub["action"],
        available_actions=tuple(stub.get("available_actions", window.query.available_actions)),
        split_parents=split_parents,
        merge_children=merge_children,
        starts_window=False,
    )


def executed_transition(
    window: EvidenceWindow, stub: dict[str, Any], grid: list
) -> Transition:
    """The recorded next action at the query state — its outcome lies beyond the prefix."""
    post = _branch_state(window, grid, stub, stub["role"])
    return make_transition(window.query, post, level_increment=stub["level_increment"])


def fork_view(window: EvidenceWindow, terminal_grid: list, action: dict[str, Any]) -> StateView:
    """Outcome of one alternative action at the query state, via a branch tracker."""
    return _branch_state(window, terminal_grid, {"action": action}, "fork_terminal")


def fork_transition(
    window: EvidenceWindow, terminal_grid: list, action: dict[str, Any], *, completed: bool
) -> Transition:
    post = fork_view(window, terminal_grid, action)
    return make_transition(window.query, post, level_increment=1 if completed else 0)


# ====================================================================================
# Per-action effect catalogue (the `card` arm and the T3/T5 floors)
# ====================================================================================


def action_label(action: dict[str, Any]) -> str:
    identifier = int(action["id"])
    if identifier == 0:
        return "RESET"
    if identifier == 6:
        data = action.get("data") or {}
        return f"ACTION6(x={int(data.get('x', -1))},y={int(data.get('y', -1))})"
    return f"ACTION{identifier}"


def click_cluster(action: dict[str, Any]) -> str | None:
    if int(action["id"]) != 6:
        return None
    data = action.get("data") or {}
    return (
        f"r{int(data.get('y', 0)) // CARD_CLICK_BLOCK}"
        f"c{int(data.get('x', 0)) // CARD_CLICK_BLOCK}"
    )


def transition_kinds(transition: Transition) -> list[str]:
    kinds = sorted(
        {
            outcome["kind"]
            for outcome in transition.outcomes.values()
            if outcome["kind"] not in {"unchanged", INELIGIBLE_OUTCOME}
        }
    )
    if transition.appeared:
        kinds.append("appeared")
    if transition.level_increment:
        kinds.append("completed")
    if transition.no_op:
        kinds = ["no_op"]
    return sorted(set(kinds))


def build_catalogue(window: EvidenceWindow) -> dict[str, Any]:
    """Per-action effect distribution accumulated from the shown prefix ONLY (MU SS3).

    Context split = the level the action was taken in.

    WHAT THIS DOES AND DOES NOT MEASURE (corrected 2026-08-03 after review). The catalogue
    is built from the window's transitions, so it holds at most ``prefix_window`` samples —
    four, or two for T2. An earlier note here claimed thin distributions were "a fact of
    online construction, not a defect to be repaired with history the deployed agent would
    not have". That was WRONG: a deployed agent carries its whole episode history, so a
    session-prefix catalogue is the deployment-faithful object and this one is not. The
    real constraints on the window are the context ceiling and the strict ``events`` subset
    ``card`` nesting that MU SS3's estimand argument rests on — a session-prefix catalogue
    would break that nesting, since card would then hold evidence events does not.
    Consequence for the read, recorded rather than hidden: the card-vs-events contrast
    measures the value of a <=4-sample catalogue, NOT of an accumulated one, so
    ``card ~= events`` is partly a window artifact and cannot be read as "the effect
    catalogue does not help a deployed advisor".
    """
    entries: dict[str, dict[str, Any]] = {}
    for transition in window.transitions:
        key = (
            f"ACTION6@{click_cluster(transition.action)}"
            if int(transition.action["id"]) == 6
            else action_label(transition.action)
        )
        entry = entries.setdefault(
            key, {"n": 0, "kinds": Counter(), "by_level": {}, "changed_cells": []}
        )
        entry["n"] += 1
        entry["kinds"].update(transition_kinds(transition))
        level = str(transition.pre.level)
        entry["by_level"].setdefault(level, Counter()).update(transition_kinds(transition))
        entry["changed_cells"].append(transition.changed_cells)
    return {
        key: {
            "n": entry["n"],
            "kinds": dict(sorted(entry["kinds"].items())),
            "by_level": {
                level: dict(sorted(counter.items()))
                for level, counter in sorted(entry["by_level"].items())
            },
            "median_changed_cells": sorted(entry["changed_cells"])[
                len(entry["changed_cells"]) // 2
            ],
        }
        for key, entry in sorted(entries.items())
    }


# ====================================================================================
# Fork tables
# ====================================================================================


class ForkTables:
    """Digest-checked lookup over the two reused GI-2 fork corpora."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, int], dict[str, Any]] = {}
        self.inputs: dict[str, str] = {}
        main = json.loads(FORK_TABLE.read_text())
        self.inputs["logs/gi2_fork_table.json"] = sha256_file(FORK_TABLE)
        for game in main["games"]:
            for session in game["sessions"]:
                guid = session["guid"]
                for completion in session["completions"]:
                    self.rows[(game["env"], guid, completion["step"])] = {
                        "pre_grid_rle": completion["pre_grid_rle"],
                        "recorded_action": completion["recorded_action"],
                        "forks": completion["forks"],
                        "source": "gi2_fork_table",
                    }
        vc33 = json.loads(AR_VC33_FORKS.read_text())
        self.inputs["logs/gi2_ar_vc33_forks.json"] = sha256_file(AR_VC33_FORKS)
        for completion in vc33["completions"]:
            self.rows[("vc33", completion["guid"], completion["step"])] = {
                "pre_grid_rle": completion["pre_grid_rle"],
                "recorded_action": None,
                "forks": completion["forks"],
                "source": "gi2_ar_vc33_forks",
            }

    def completions(self, env: str, guid: str) -> list[int]:
        return sorted(step for (e, g, step) in self.rows if e == env and g == guid)

    def get(self, env: str, guid: str, step: int) -> dict[str, Any] | None:
        return self.rows.get((env, guid, step))


def authenticate_forks(row: dict[str, Any], query_grid: list) -> list[dict[str, Any]]:
    """Reuse is authenticated byte-for-byte: a fork row whose stored pre-state is not the
    window's query state is discarded, never repaired."""
    if decode_grid(row["pre_grid_rle"]) != query_grid:
        raise ValueError("fork row pre-state does not equal the window query state")
    return row["forks"]


def bounded_fork_candidates(
    forks: list[dict[str, Any]], seed: str
) -> list[dict[str, Any]]:
    """Bounded fork-representative policy (MU SS2): ACTION6 rows are hash-reduced."""
    simple = [row for row in forks if int(row["action_id"]) != 6]
    mouse = sorted(
        (row for row in forks if int(row["action_id"]) == 6),
        key=lambda row: (int(row["action_data"].get("y", 0)), int(row["action_data"].get("x", 0))),
    )
    if len(mouse) > MOUSE_REPRESENTATIVE_CAP:
        kept = hash_order(mouse, f"{seed}|mouse", key=lambda row: row["action_data"])
        mouse = sorted(
            kept[:MOUSE_REPRESENTATIVE_CAP],
            key=lambda row: (
                int(row["action_data"].get("y", 0)),
                int(row["action_data"].get("x", 0)),
            ),
        )
    return simple + mouse


def option_action(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": int(row["action_id"]), "data": dict(row.get("action_data") or {})}


# ====================================================================================
# Probe construction — MU-T1 .. MU-T5
# ====================================================================================


def _case_id(probe: str, window: EvidenceWindow, suffix: str = "") -> str:
    tail = f":{suffix}" if suffix else ""
    return f"mu:{probe}:{window.env}:{window.guid}:{window.query.key}{tail}"


def _full_reveal(window: EvidenceWindow) -> dict[str, Any]:
    """Default: the whole shown prefix is rendered; the queried outcome lies outside it."""
    return {
        "object_tables_through": len(window.states) - 1,
        "derived_through": len(window.transitions) - 1,
        "relabel_query_state": False,
    }


def build_t1(window: EvidenceWindow) -> dict[str, Any] | None:
    """MU-T1 legibility: closed state look-ups whose gold is the tracker registry."""
    objects = window.query.objects
    if len(objects) < 2:
        return None
    case_id = _case_id("T1", window)
    colours = sorted({item.colour for item in objects})
    colour = hash_order(colours, f"{case_id}|colour")[0]
    ordered = hash_order(list(objects), f"{case_id}|alias", key=lambda item: item.alias)
    first, second = ordered[0], ordered[1]
    relation = hash_order(list(VISUAL_RELATIONS), f"{case_id}|relation")[0]
    return {
        "case_id": case_id,
        "probe": "T1",
        "env": window.env,
        "guid": window.guid,
        "role": window.role,
        "anchor": window.anchor,
        "query_state": window.query.key,
        "window": [state.key for state in window.states],
        "reveal": _full_reveal(window),
        "question": {
            "count_colour": COLOR_NAMES[colour],
            "bbox_alias": first.alias,
            "size_alias": second.alias,
            "relation": {"name": relation, "left": first.alias, "right": second.alias},
        },
        "gold": {
            "count": sum(1 for item in objects if item.colour == colour),
            "bbox": list(first.bbox),
            "size": second.pixels,
            "relation": relation_holds(relation, first, second),
        },
    }


def _t2_eligible_rows(transition: Transition) -> list[MuObject]:
    """B rows need an unambiguous ancestor or none at all (ES SS3.1 lineage discipline)."""
    pre_by_track = transition.pre.by_track
    rows = []
    for item in transition.post.objects:
        if item.track_id in transition.post.merge_children:
            continue
        ancestor = pre_by_track.get(item.track_id)
        if ancestor is not None and ancestor.track_id in transition.post.split_parents:
            continue
        rows.append(item)
    return rows


def build_t2(window: EvidenceWindow) -> dict[str, Any] | None:
    """MU-T2 identity: hash-ordered second-frame rows mapped back to first-frame aliases."""
    transition = window.transitions[-1]
    if transition.no_op:
        return None
    case_id = _case_id("T2", window)
    eligible = _t2_eligible_rows(transition)
    if len(eligible) < 2:
        return None
    pre_by_track = transition.pre.by_track
    pre_by_alias = transition.pre.by_alias
    changed_track_ids = {
        pre_by_alias[alias].track_id
        for alias, outcome in transition.outcomes.items()
        if outcome["kind"] in {"moved", "recoloured"} and alias in pre_by_alias
    }
    novel = [item for item in eligible if item.track_id not in pre_by_track]
    changed = [item for item in eligible if item.track_id in changed_track_ids]
    rest = [item for item in eligible if item not in changed and item not in novel]
    priority = (
        hash_order(changed, f"{case_id}|changed", key=lambda item: item.track_id)
        + hash_order(novel, f"{case_id}|novel", key=lambda item: item.track_id)
        + hash_order(rest, f"{case_id}|rest", key=lambda item: item.track_id)
    )
    selected = priority[:T2_ROWS_MAX]
    if not any(item in changed or item in novel for item in selected):
        return None
    # Every object of the query state is relabelled B1..Bm in one frozen hash order — the
    # "ids withheld, rows ordered by frozen hash" rule of MU SS2. The question asks about a
    # subset; the whole relabelled table is what the arms render.
    label_order = hash_order(
        list(transition.post.objects), f"{case_id}|labels", key=lambda item: item.alias
    )
    labels = {item.alias: f"B{index}" for index, item in enumerate(label_order, 1)}
    rows = []
    gold = {}
    for item in sorted(selected, key=lambda entry: int(labels[entry.alias][1:])):
        label = labels[item.alias]
        ancestor = pre_by_track.get(item.track_id)
        rows.append({"label": label, "anchor": list(min(item.cells))})
        gold[label] = ancestor.alias if ancestor is not None else "new"
    return {
        "case_id": case_id,
        "probe": "T2",
        "env": window.env,
        "guid": window.guid,
        "role": window.role,
        "anchor": window.anchor,
        "query_state": window.query.key,
        "window": [state.key for state in window.states],
        "label_order": [item.alias for item in label_order],
        "reveal": {"object_tables_through": len(window.states) - 2,
                   "derived_through": len(window.transitions) - 2,
                   "relabel_query_state": True},
        "question": {"rows": [row["label"] for row in rows], "row_detail": rows},
        "gold": gold,
    }


def _t3_named_objects(transition: Transition, case_id: str) -> list[str] | None:
    eligible = [
        alias
        for alias, outcome in transition.outcomes.items()
        if outcome["kind"] in OUTCOME_KINDS
    ]
    if len(eligible) < T3_OBJECTS_PER_CASE:
        return None
    changed = [
        alias
        for alias in eligible
        if transition.outcomes[alias]["kind"] != "unchanged"
    ]
    stable = [alias for alias in eligible if alias not in changed]
    ordered = (
        hash_order(changed, f"{case_id}|changed")
        + hash_order(stable, f"{case_id}|stable")
    )
    return ordered[:T3_OBJECTS_PER_CASE]


def _t3_case(
    window: EvidenceWindow, transition: Transition, form: str, case_id: str
) -> dict[str, Any] | None:
    named = _t3_named_objects(transition, case_id)
    if named is None:
        return None
    return {
        "case_id": case_id,
        "probe": "T3",
        "form": form,
        "env": window.env,
        "guid": window.guid,
        "role": window.role,
        "anchor": window.anchor,
        "query_state": window.query.key,
        "window": [state.key for state in window.states],
        "reveal": _full_reveal(window),
        "question": {
            "action": action_label(transition.action),
            "action_raw": transition.action,
            "objects": named,
        },
        "gold": {
            "no_op": transition.no_op,
            "level_increment": int(bool(transition.level_increment)),
            "objects": {
                alias: {
                    "kind": transition.outcomes[alias]["kind"],
                    "delta": transition.outcomes[alias].get("delta"),
                }
                for alias in named
            },
        },
        "audit": {
            "queried_post_state": f"{transition.post.step}.{transition.post.frame_index}",
            "appeared": transition.appeared,
            "changed_cells": transition.changed_cells,
            "ineligible_objects": sum(
                1
                for outcome in transition.outcomes.values()
                if outcome["kind"] == INELIGIBLE_OUTCOME
            ),
        },
    }


def build_t3_executed(window: EvidenceWindow, executed: Transition) -> dict[str, Any] | None:
    """Executed-action form: the queried outcome lies beyond the shown prefix."""
    return _t3_case(window, executed, "executed", _case_id("T3", window, "executed"))


def build_t3_fork(
    window: EvidenceWindow, forks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Fork-action form: an alternative action at the shown query state."""
    case_id = _case_id("T3", window, "fork")
    usable = [row for row in forks if row.get("terminal_grid_rle")]
    if not usable:
        return None
    for row in hash_order(
        usable,
        f"{case_id}|fork",
        key=lambda item: {"id": item["action_id"], **(item.get("action_data") or {})},
    ):
        transition = fork_transition(
            window,
            decode_grid(row["terminal_grid_rle"]),
            option_action(row),
            completed=bool(row["completed"]),
        )
        case = _t3_case(window, transition, "fork", case_id)
        if case is not None:
            case["question"]["action"] = action_label(option_action(row))
            case["question"]["action_raw"] = option_action(row)
            return case
    return None


def _condition_value(condition: dict[str, Any], transition: Transition) -> bool | None:
    kind = condition["kind"]
    if kind == "no_change":
        return transition.no_op
    if kind == "appears":
        return transition.appeared > 0
    outcome = transition.outcomes.get(condition["object"])
    if outcome is None or outcome["kind"] == INELIGIBLE_OUTCOME:
        return None
    return outcome["kind"] == {"moves": "moved", "disappears": "disappeared",
                              "recolours": "recoloured"}[kind]


def condition_text(condition: dict[str, Any]) -> str:
    kind = condition["kind"]
    if kind == "no_change":
        return "leave the board completely unchanged"
    if kind == "appears":
        return "make at least one new object appear"
    verb = {"moves": "move", "disappears": "remove", "recolours": "recolour"}[kind]
    return f"{verb} {condition['object']}"


def _draw_options(
    window: EvidenceWindow,
    forks: list[dict[str, Any]],
    case_id: str,
    *,
    extra: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    pool = bounded_fork_candidates(forks, case_id)
    pool = [row for row in pool if row.get("terminal_grid_rle")]
    extra = list(extra or [])
    # The offered set is the whole legal set when the game advertises fewer actions than
    # CLOSED_ACTION_OPTIONS (ls20 and tu93 advertise three); it is never padded.
    wanted = min(CLOSED_ACTION_OPTIONS - len(extra), len(pool))
    if wanted + len(extra) < CLOSED_ACTION_OPTIONS_MIN:
        return None
    drawn = hash_order(
        pool, f"{case_id}|options", key=lambda row: {"id": row["action_id"], **row["action_data"]}
    )[:wanted]
    options = extra + drawn
    return hash_order(
        options,
        f"{case_id}|present",
        key=lambda row: {"id": row["action_id"], **(row.get("action_data") or {})},
    )


def build_t4(
    window: EvidenceWindow, forks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """MU-T4 control: reach a target condition stated in the referent vocabulary."""
    case_id = _case_id("T4", window)
    options = _draw_options(window, forks, case_id)
    if options is None:
        return None
    transitions = [
        fork_transition(
            window,
            decode_grid(row["terminal_grid_rle"]),
            option_action(row),
            completed=bool(row["completed"]),
        )
        for row in options
    ]
    candidates: list[dict[str, Any]] = [{"kind": "no_change"}, {"kind": "appears"}]
    touched = {
        alias
        for transition in transitions
        for alias, outcome in transition.outcomes.items()
        if outcome["kind"] in {"moved", "disappeared", "recoloured"}
    }
    for alias in sorted(touched):
        for kind in ("moves", "disappears", "recolours"):
            candidates.append({"kind": kind, "object": alias})
    eligible = []
    for condition in candidates:
        values = [_condition_value(condition, transition) for transition in transitions]
        if any(value is None for value in values):
            continue
        satisfying = [index for index, value in enumerate(values) if value]
        if not satisfying or len(satisfying) == len(values):
            continue
        eligible.append((condition, satisfying))
    if not eligible:
        return None
    condition, satisfying = hash_order(
        eligible, f"{case_id}|condition", key=lambda item: item[0]
    )[0]
    labelled = [
        {"label": f"A{index}", **option_action(row)}
        for index, row in enumerate(options, 1)
    ]
    return {
        "case_id": case_id,
        "probe": "T4",
        "env": window.env,
        "guid": window.guid,
        "role": window.role,
        "anchor": window.anchor,
        "query_state": window.query.key,
        "window": [state.key for state in window.states],
        "reveal": _full_reveal(window),
        "question": {
            "condition": condition,
            "condition_text": condition_text(condition),
            "options": labelled,
        },
        "gold": {"accepting": [labelled[index]["label"] for index in satisfying]},
    }


def build_t5(
    window: EvidenceWindow,
    forks: list[dict[str, Any]],
    recorded: dict[str, Any],
) -> dict[str, Any] | None:
    """MU-T5 terminal-action discrimination: which offered action completes the level (any
    completing action scores). The pre-terminality of the state is REVEALED by the prompt:
    T5 measures local discrimination at a known pre-terminal state, not goal induction from
    ordinary states — the continuation claim is narrowed accordingly (MU SS2, SS5.1)."""
    case_id = _case_id("T5", window)
    recorded_row = {
        "action_id": recorded["id"],
        "action_data": dict(recorded.get("data") or {}),
        "completed": True,
        "terminal_grid_rle": None,
        "recorded": True,
    }
    pool = [
        row
        for row in bounded_fork_candidates(forks, case_id)
        if not (
            int(row["action_id"]) == int(recorded_row["action_id"])
            and dict(row.get("action_data") or {}) == recorded_row["action_data"]
        )
    ]
    wanted = min(CLOSED_ACTION_OPTIONS - 1, len(pool))
    if wanted + 1 < CLOSED_ACTION_OPTIONS_MIN:
        return None
    drawn = hash_order(
        pool, f"{case_id}|options", key=lambda row: {"id": row["action_id"], **row["action_data"]}
    )[:wanted]
    options = hash_order(
        [recorded_row] + drawn,
        f"{case_id}|present",
        key=lambda row: {"id": row["action_id"], **(row.get("action_data") or {})},
    )
    labelled = [
        {"label": f"A{index}", **option_action(row)}
        for index, row in enumerate(options, 1)
    ]
    accepting = [
        labelled[index]["label"]
        for index, row in enumerate(options)
        if bool(row["completed"])
    ]
    if not accepting or len(accepting) == len(options):
        return None
    return {
        "case_id": case_id,
        "probe": "T5",
        "env": window.env,
        "guid": window.guid,
        "role": window.role,
        "anchor": window.anchor,
        "query_state": window.query.key,
        "window": [state.key for state in window.states],
        "reveal": _full_reveal(window),
        "question": {"options": labelled},
        "gold": {"accepting": accepting},
    }


# ====================================================================================
# Model-free floors (MU SS4)
# ====================================================================================


def floor_t1(case: dict[str, Any], window: EvidenceWindow) -> dict[str, Any]:
    """Template look-up over the registry — exact by construction; validates the gold."""
    objects = window.query.objects
    by_alias = window.query.by_alias
    question = case["question"]
    inverse = {name: value for value, name in COLOR_NAMES.items()}
    left = by_alias[question["relation"]["left"]]
    right = by_alias[question["relation"]["right"]]
    return {
        "count": sum(1 for item in objects if item.colour == inverse[question["count_colour"]]),
        "bbox": list(by_alias[question["bbox_alias"]].bbox),
        "size": by_alias[question["size_alias"]].pixels,
        "relation": relation_holds(question["relation"]["name"], left, right),
    }


def floor_t2(case: dict[str, Any], window: EvidenceWindow) -> dict[str, Any]:
    """Greedy appearance match without the tracker: colour, then nearest centroid."""
    transition = window.transitions[-1]
    presented = {row["label"]: row for row in case["question"]["row_detail"]}
    candidates = list(transition.pre.objects)
    answer = {}
    for label in case["question"]["rows"]:
        anchor = tuple(presented[label]["anchor"])
        target = next(
            (item for item in transition.post.objects if anchor in item.cells), None
        )
        if target is None:
            answer[label] = "new"
            continue
        same_colour = [item for item in candidates if item.colour == target.colour]
        if not same_colour:
            answer[label] = "new"
            continue
        best = min(
            same_colour,
            key=lambda item: (
                abs(item.centroid[0] - target.centroid[0])
                + abs(item.centroid[1] - target.centroid[1]),
                abs(item.pixels - target.pixels),
                item.alias,
            ),
        )
        answer[label] = best.alias
    return {"mapping": answer}


def floor_t3(case: dict[str, Any], window: EvidenceWindow) -> dict[str, Any]:
    """Modal effect from the shown-prefix catalogue; unseen actions predict no-op."""
    catalogue = build_catalogue(window)
    action = case["question"]["action_raw"]
    key = (
        f"ACTION6@{click_cluster(action)}"
        if int(action["id"]) == 6
        else action_label(action)
    )
    entry = catalogue.get(key)
    kinds = entry["kinds"] if entry else {}
    modal = max(kinds.items(), key=lambda item: (item[1], item[0]))[0] if kinds else "no_op"
    mapped = {"moved": "moved", "disappeared": "disappeared", "recoloured": "recoloured"}
    kind = mapped.get(modal, "unchanged")
    return {
        "no_op": modal == "no_op",
        "level_increment": 1 if modal == "completed" else 0,
        "objects": {
            alias: {"kind": kind, "delta": [0, 0] if kind == "moved" else None}
            for alias in case["question"]["objects"]
        },
    }


def floor_t4(case: dict[str, Any], window: EvidenceWindow) -> dict[str, Any]:
    """Nearest satisfying prefix transition by state similarity, mapped onto the options."""
    condition = case["question"]["condition"]
    options = case["question"]["options"]
    satisfying = [
        transition
        for transition in window.transitions
        if _condition_value(condition, transition) is True
    ]
    if satisfying:
        best = max(
            satisfying,
            key=lambda transition: (
                4096 - _changed_cells(transition.pre.grid, window.query.grid),
                transition.pre.step,
            ),
        )
        wanted = best.action
        for option in options:
            if option["id"] == int(wanted["id"]) and option["data"] == (wanted.get("data") or {}):
                return {"choice": option["label"]}
        for option in options:
            if option["id"] == int(wanted["id"]):
                return {"choice": option["label"]}
    return {"choice": options[0]["label"]}


def floor_t5(case: dict[str, Any], window: EvidenceWindow) -> dict[str, Any]:
    """Catalogue-ranked action frequency over the shown prefix."""
    counts = Counter(int(transition.action["id"]) for transition in window.transitions)
    options = case["question"]["options"]
    best = max(options, key=lambda option: (counts.get(option["id"], 0), -option["id"]))
    return {"choice": best["label"]}


FLOORS = {"T1": floor_t1, "T2": floor_t2, "T3": floor_t3, "T4": floor_t4, "T5": floor_t5}


# ====================================================================================
# Frozen output schemas, parsing, scoring
# ====================================================================================


def output_schema(case: dict[str, Any]) -> dict[str, Any]:
    """Guided-JSON schema for one case; the TEMPLATE is what freezes, per MU SS1."""
    probe = case["probe"]
    if probe == "T1":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(T1_ITEMS),
            "properties": {
                "count": {"type": "integer", "minimum": 0},
                "bbox": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 63},
                    "minItems": 4,
                    "maxItems": 4,
                },
                "size": {"type": "integer", "minimum": 1},
                "relation": {"type": "boolean"},
            },
        }
    if probe == "T2":
        rows = case["question"]["rows"]
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["mapping"],
            "properties": {
                "mapping": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(rows),
                    "properties": {row: {"type": "string"} for row in rows},
                }
            },
        }
    if probe == "T3":
        aliases = case["question"]["objects"]
        event = {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "delta"],
            "properties": {
                "kind": {"type": "string", "enum": list(OUTCOME_KINDS)},
                "delta": {
                    "type": ["array", "null"],
                    "items": {"type": "integer"},
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["no_op", "level_increment", "objects"],
            "properties": {
                "no_op": {"type": "boolean"},
                "level_increment": {"type": "integer", "minimum": 0, "maximum": 1},
                "objects": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(aliases),
                    "properties": {alias: event for alias in aliases},
                },
            },
        }
    labels = [option["label"] for option in case["question"]["options"]]
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["choice"],
        "properties": {"choice": {"type": "string", "enum": labels}},
    }


def strict_json(text: Any) -> dict[str, Any]:
    if not isinstance(text, str) or not text or text[0] != "{" or text[-1] != "}":
        raise ValueError("response must be a bare JSON object")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("response must decode to an object")
    return value


def parse_answer(case: dict[str, Any], text: Any) -> dict[str, Any]:
    """Schema failures raise; the caller scores them 0 and keeps them in the denominator."""
    value = strict_json(text)
    probe = case["probe"]
    if probe == "T1":
        if set(value) != set(T1_ITEMS):
            raise ValueError("T1 keys differ from schema")
        if not isinstance(value["count"], int) or isinstance(value["count"], bool):
            raise ValueError("count must be an integer")
        bbox = value["bbox"]
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or any(isinstance(item, bool) or not isinstance(item, int) for item in bbox)
        ):
            raise ValueError("bbox must be four integers")
        if not isinstance(value["size"], int) or isinstance(value["size"], bool):
            raise ValueError("size must be an integer")
        if not isinstance(value["relation"], bool):
            raise ValueError("relation must be a boolean")
        return value
    if probe == "T2":
        if set(value) != {"mapping"}:
            raise ValueError("T2 keys differ from schema")
        mapping = value["mapping"]
        if not isinstance(mapping, dict) or set(mapping) != set(case["question"]["rows"]):
            raise ValueError("mapping must answer exactly the offered rows")
        if any(not isinstance(item, str) or not item for item in mapping.values()):
            raise ValueError("mapping values must be non-empty strings")
        return value
    if probe == "T3":
        if set(value) != {"no_op", "level_increment", "objects"}:
            raise ValueError("T3 keys differ from schema")
        if not isinstance(value["no_op"], bool):
            raise ValueError("no_op must be a boolean")
        if value["level_increment"] not in (0, 1) or isinstance(value["level_increment"], bool):
            raise ValueError("level_increment must be 0 or 1")
        objects = value["objects"]
        if not isinstance(objects, dict) or set(objects) != set(case["question"]["objects"]):
            raise ValueError("objects must answer exactly the named referents")
        for entry in objects.values():
            if not isinstance(entry, dict) or set(entry) != {"kind", "delta"}:
                raise ValueError("each object needs kind and delta")
            if entry["kind"] not in OUTCOME_KINDS:
                raise ValueError("unknown outcome kind")
            delta = entry["delta"]
            if entry["kind"] == "moved":
                if (
                    not isinstance(delta, list)
                    or len(delta) != 2
                    or any(isinstance(item, bool) or not isinstance(item, int) for item in delta)
                ):
                    raise ValueError("moved needs an integer delta pair")
            # MU-E1 (2026-08-03): a non-null delta on a non-moved outcome is IGNORED, not
            # refused. `delta` is `required` in the guided schema and typed
            # ["array","null"] with no conditional, so `{"kind":"unchanged","delta":[0,0]}`
            # is exactly what the model was asked to produce. Refusing it scored compliant
            # answers 0 — on 41% of T3 rows, unequally by arm. The field carries no
            # information unless the outcome is `moved`, so scoring simply does not read it
            # there (`score_case` already compares delta only for `moved`).
        return value
    if set(value) != {"choice"}:
        raise ValueError("choice keys differ from schema")
    labels = {option["label"] for option in case["question"]["options"]}
    if value["choice"] not in labels:
        raise ValueError("choice is not an offered option")
    return value


def score_case(case: dict[str, Any], answer: dict[str, Any] | None) -> dict[str, Any]:
    """Case rate in [0,1] plus the strict all-or-nothing indicator.

    A parse, schema, or context failure arrives as ``answer is None`` and scores 0 while
    staying in the denominator (MU SS2).
    """
    probe = case["probe"]
    gold = case["gold"]
    if probe == "T1":
        if answer is None:
            items = {name: False for name in T1_ITEMS}
        else:
            items = {
                "count": answer["count"] == gold["count"],
                "bbox": answer["bbox"] == gold["bbox"],
                "size": answer["size"] == gold["size"],
                "relation": answer["relation"] == gold["relation"],
            }
        return {
            "rate": sum(items.values()) / len(items),
            "exact": all(items.values()),
            "items": items,
        }
    if probe == "T2":
        rows = case["question"]["rows"]
        if answer is None:
            items = {row: False for row in rows}
        else:
            items = {row: answer["mapping"][row] == gold[row] for row in rows}
        return {
            "rate": sum(items.values()) / len(items),
            "exact": all(items.values()),
            "items": items,
        }
    if probe == "T3":
        fields: dict[str, bool] = {}
        if answer is None:
            fields["no_op"] = False
            fields["level_increment"] = False
            for alias in case["question"]["objects"]:
                fields[alias] = False
        else:
            fields["no_op"] = answer["no_op"] == gold["no_op"]
            fields["level_increment"] = answer["level_increment"] == gold["level_increment"]
            for alias, expected in gold["objects"].items():
                got = answer["objects"][alias]
                fields[alias] = got["kind"] == expected["kind"] and (
                    expected["kind"] != "moved" or got["delta"] == expected["delta"]
                )
        return {
            "rate": sum(fields.values()) / len(fields),
            "exact": all(fields.values()),
            "items": fields,
        }
    correct = answer is not None and answer["choice"] in gold["accepting"]
    return {"rate": 1.0 if correct else 0.0, "exact": correct, "items": {"choice": correct}}


# ====================================================================================
# Session driver
# ====================================================================================


def recording_path(env: str, guid: str) -> Path:
    return CORPUS / env / f"{guid}.recording.jsonl"


def session_stubs(env: str, guid: str) -> list[dict[str, Any]]:
    return _stub_records(recording_path(env, guid))


def collect_grids(env: str, guid: str, wanted: set[str]) -> dict[str, list]:
    """One streaming pass that materializes only the states a selection needs."""
    grids: dict[str, list] = {}
    for step in iter_trace(recording_path(env, guid)):
        for frame in step.frames:
            key = f"{step.index}.{frame.index}"
            if key in wanted:
                grids[key] = frame.grid
    missing = wanted - set(grids)
    if missing:
        raise ValueError(f"{env}/{guid}: could not materialize states {sorted(missing)}")
    return grids


def es_partition() -> dict[str, list[dict[str, str]]]:
    """The frozen ES session-role assignment, reused unchanged (MU SS1)."""
    document = json.loads(ES_INVENTORY.read_text())
    partition = {}
    for env, block in document["partition"].items():
        partition[env] = [
            {"guid": row["guid"], "role": row["role"], "session_start": row["session_start"]}
            for row in block["sessions"]
        ]
    if sorted(partition) != sorted(GAMES):
        raise ValueError("ES partition does not cover the frozen MU corpus")
    return partition


def _selftest() -> int:
    partition = es_partition()
    tables = ForkTables()
    env = "ls20"
    row = next(item for item in partition[env] if item["role"] == "S")
    stubs = session_stubs(env, row["guid"])
    print(f"{env}/{row['guid'][:8]} role=S states={len(stubs)}")
    index = next(
        position
        for position in range(len(stubs) - 1, -1, -1)
        if window_members(stubs, position, PREFIX_WINDOW["T1"]) is not None
    )
    members = window_members(stubs, index, PREFIX_WINDOW["T1"])
    grids = collect_grids(
        env,
        row["guid"],
        {f"{stubs[i]['step']}.{stubs[i]['frame_index']}" for i in members},
    )
    window = build_window(env, row["guid"], "S", "T1", stubs, grids, members)
    print(f"  window states={len(window.states)} objects={len(window.query.objects)}")
    case = build_t1(window)
    print(f"  T1 gold: {json.dumps(case['gold'])}")
    floor = floor_t1(case, window)
    print(f"  T1 floor score: {score_case(case, floor)['rate']:.2f}")
    print(f"  catalogue keys: {sorted(build_catalogue(window))}")
    print(f"  fork completions: {len(tables.completions(env, row['guid']))}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return _selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
