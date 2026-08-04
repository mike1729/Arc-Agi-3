#!/usr/bin/env python3
"""E0 transition and object-event extraction from the human replay corpus.

Turns each recording into a sequence of typed transitions carrying the object-level effect
of the action that produced them. Nothing here mines or scores; this module only decides
WHAT a transition is, and it decides it the way the audited estate already did.

CONVENTIONS — inherited, not chosen here
----------------------------------------
Frame roles come from ``gi2_traces.frame_roles``. Per action:

    pre   the previous settled frame; ``next_level_initial`` immediately after a completion;
          the level's opening frame at the start of a level
    post  ``solved_terminal`` when the action completes a level, the settled last frame
          otherwise

A transition's LEVEL INDEX is its pre-action ``levels_completed`` + 1, so L1 is everything
played at ``levels_completed == 0``. Intermediate (animation) frames are never a transition
endpoint — the settled-frame convention is the one the vc33 erratum was written against, and
reading intermediate frames here would reintroduce exactly that defect.

A level RESET (``levels_completed`` decreasing) re-seeds ``pre`` and contributes no
transition: the action that caused it has no settled successor in the same level.

OBJECTS AND LINEAGE — one convention, shared with row C
------------------------------------------------------
Objects are 4-connected same-colour components over the state-local background (modal
colour, ties to the smaller value). Lineage inside a transition is forward-only and
SAME-COLOUR: a post-component descends from a pre-component iff they share a colour and
intersect in cells. Both come from ``es_candidates._Objects`` / ``_lineage``, reused rather
than reimplemented so that rows M and C cannot silently disagree about what an object is.

The same-colour rule has a consequence worth stating rather than discovering later: a
RECOLOUR appears as ``disappear(c1) + appear(c2)``, never as a single typed event. That is
the estate's definition, and row M's effect vocabulary inherits it.

EFFECT SIGNATURE
----------------
The canonical, position-free description of what an action did:

    ()                              no change at all
    (("move", colour, dx, dy), ...) a matched pair whose cells are a rigid translation
    (("reshape", colour), ...)      a matched pair whose cells changed non-rigidly
    (("appear", colour), ...)       a post-component with no ancestor
    (("disappear", colour), ...)    a pre-component with no descendant

Position-free is the whole point: ``move`` carries the VECTOR, not the coordinates, so a rule
mined at L1 is capable of applying to an L2 state it has never seen. An effect vocabulary
keyed on absolute position could not survive a level change even in principle, and measuring
its survival would measure the vocabulary rather than the game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_candidates import _Objects, _lineage  # noqa: E402
from gi2_traces import frame_roles, normalize_action_id  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/human_replays/kaggle_mirror/public_games-dataset"

# The six iteration games. The seal on the other nineteen was lifted for E0 — see RS-E2.
ITERATION_GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")
ALL_GAMES = (
    "ar25", "bp35", "cd82", "cn04", "dc22", "ft09", "g50t", "ka59", "lf52", "lp85", "ls20",
    "m0r0", "r11l", "re86", "s5i5", "sb26", "sc25", "sk48", "sp80", "su15", "tn36", "tr87",
    "tu93", "vc33", "wa30",
)

# ---- fidelity exclusions (RS-E5) -----------------------------------------------------
# Derived from logs/e0_fidelity.json + logs/e0_fidelity_rest.json. A recording only carries
# engine truth where the frozen source reproduces its role-bearing frames; where it does not,
# any E0 finding would be about a source/client divergence rather than about levels.
#
# s5i5 fails wholesale: all 11 sessions diverge at step 2 on ACTION6, inside the L1 window.
# The frozen source is not the build these recordings came from, so no session of it is
# usable and the game is dropped from both rows.
EXCLUDED_GAMES = {"s5i5": "role-bearing divergence at step 2 of all 11 sessions (ACTION6)"}

# Single sessions whose divergence falls INSIDE the L1/L2 window. All three are on RESET,
# consistent with GI-2's standing note that remote and local reset metadata are not assumed
# identical. Divergences after the window are harmless and are not listed.
EXCLUDED_SESSIONS = {
    ("cn04", "ce770223"): "RESET divergence at step 461, window ends 682",
    ("lf52", "72a712db"): "RESET divergence at step 67, window ends 68",
    ("sp80", "add9ed90"): "RESET divergence at step 298, window ends 344",
}

ORTHOGONAL = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}

# ---- guard vocabulary version (notes/miner-vocab-v2.md) --------------------------------
# v2 ADOPTED 2026-08-04 and is the default. It adds `clicked_adjacent_to:C` and nothing else.
# The adoption rule was pre-committed in the note and the measured deltas satisfy it: v2 has
# ZERO losses on every metric of all 24 games, and non-zero gains on a few (ft09 held-out-L1
# 0.845 -> 0.892; explorer-store floors move in 2 games). Its real effect is on the FAILURE
# TYPING, not the headline — it reclassifies 217 L1->L2 failures out of census/unpredicted
# into guard_fixable across 9 games. See notes/miner-vocab-v2-results.md.
#
# v1 is the vocabulary every EARLIER number was measured under and stays available:
# `--vocab v1` reproduces logs/e0_row_m_all.json and logs/e2_dose.json exactly, and that
# equivalence is asserted, not assumed — see the regression in the results note.
#
# The setting is read at CALL time and mirrored into the environment, because e2_dose runs
# games in a ProcessPoolExecutor: on macOS the default start method is `spawn`, so a global
# set in the parent after import would not reach a worker, while the environment is inherited.
VOCAB_ENV = "RS_GUARD_VOCAB"


def set_vocab(version: str) -> None:
    if version not in ("v1", "v2"):
        raise ValueError(f"unknown guard vocabulary: {version}")
    os.environ[VOCAB_ENV] = version


def vocab() -> str:
    return os.environ.get(VOCAB_ENV, "v2")

# Data defects met during extraction, keyed by game/guid. Reported, never swallowed.
ANOMALIES: dict[str, list[dict[str, Any]]] = {}

# Which fidelity exclusions actually fired this run. Reported alongside every result.
EXCLUDED_APPLIED: list[str] = []


def grid_digest(grid: list) -> str:
    return hashlib.sha256(
        json.dumps(grid, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass
class Transition:
    game: str
    guid: str
    step: int
    level: int
    action_id: int
    action_data: dict[str, Any]
    pre: list
    post: list
    completed: bool
    effect: tuple = field(default=())
    guards: dict[str, Any] = field(default_factory=dict)

    def key(self) -> tuple:
        """The action key a rule is mined against, before any guard refinement."""
        if self.action_id == 6:
            return ("A6", self.guards.get("click_colour"))
        return ("A", self.action_id)


# ======================================================================================
# Effect extraction
# ======================================================================================


def _rigid_translation(before: frozenset, after: frozenset) -> tuple[int, int] | None:
    """The vector taking `before` onto `after` exactly, or None if no such vector."""
    if len(before) != len(after) or not before:
        return None
    br = min(row for row, _ in before)
    bc = min(col for _, col in before)
    ar = min(row for row, _ in after)
    ac = min(col for _, col in after)
    dr, dc = ar - br, ac - bc
    if all((row + dr, col + dc) in after for row, col in before):
        return (dr, dc)
    return None


def effect_signature(pre_objects: _Objects, post_objects: _Objects) -> tuple:
    """Canonical position-free description of the object-level change."""
    events: list[tuple] = []
    colours = set(pre_objects.by_colour) | set(post_objects.by_colour)
    for colour in sorted(colours):
        pre_members = pre_objects.by_colour.get(colour, [])
        post_members = post_objects.by_colour.get(colour, [])
        descendants, ancestors = _lineage(pre_members, post_members)
        for index, member in enumerate(pre_members):
            targets = descendants[index]
            if not targets:
                events.append(("disappear", colour))
                continue
            if len(targets) == 1 and len(ancestors[targets[0]]) == 1:
                after = post_members[targets[0]]["cells"]
                if after == member["cells"]:
                    continue
                vector = _rigid_translation(member["cells"], after)
                events.append(
                    ("move", colour, vector[0], vector[1])
                    if vector is not None
                    else ("reshape", colour)
                )
            else:
                events.append(("reshape", colour))
        for index, member in enumerate(post_members):
            if not ancestors[index]:
                events.append(("appear", colour))
    return tuple(sorted(events))


# ======================================================================================
# Guard vocabulary
# ======================================================================================
#
# Bounded, mechanical, and computed from the PRE-state and the action alone — never from the
# outcome. A guard the miner could only evaluate after seeing the effect would make every
# misprediction look guard-fixable, which is precisely the number E0 exists to measure.
#
# v1:            present:C · count:C · adj:C:direction · click_colour · click_on_background
# v2 (default):  the above + clicked_adjacent_to:C   (ACTION6, in-bounds clicks only)
#
# Guards are recomputed at LOAD time from grids, here and in `e2_dose.load_store`, so v2 is a
# code-only change: no store regenerates, E1 does not rerun.


def _clicked_component(pre: list, row: int, col: int) -> tuple[int, set[tuple[int, int]]]:
    """The 4-connected same-colour component containing (row, col).

    Deliberately a local flood fill rather than a call to ``componentize``: only one
    component is ever needed, and the whole-grid version is already paid for once per state
    by ``_Objects``. It must agree with ``componentize`` on connectivity and colour, and it
    does — 4-connected, exact value equality, no background exclusion. Background-coloured
    components ARE legitimate here (clicking empty canvas is a real action in the placement
    games), which is exactly where this differs from ``_Objects``.
    """
    height = len(pre)
    width = len(pre[0]) if height else 0
    colour = int(pre[row][col])
    seen = {(row, col)}
    stack = [(row, col)]
    while stack:
        r, c = stack.pop()
        for dr, dc in ORTHOGONAL.values():
            nr, nc = r + dr, c + dc
            if (
                0 <= nr < height
                and 0 <= nc < width
                and (nr, nc) not in seen
                and int(pre[nr][nc]) == colour
            ):
                seen.add((nr, nc))
                stack.append((nr, nc))
    return colour, seen


def guard_features(pre: list, pre_objects: _Objects, action_id: int, data: dict) -> dict:
    guards: dict[str, Any] = {}
    for colour in sorted(pre_objects.by_colour):
        guards[f"present:{colour}"] = True
        guards[f"count:{colour}"] = len(pre_objects.by_colour[colour])

    # `adjacent` is the obstacle guard: for a colour denoting exactly one object, the first
    # non-background colour met stepping one cell out from its cells in each direction. This
    # is the feature a blocked-movement rule needs, and the reason a movement rule that
    # fails at a wall is repairable rather than wrong.
    height = len(pre)
    width = len(pre[0]) if height else 0
    for colour, members in pre_objects.by_colour.items():
        if len(members) != 1:
            continue
        cells = members[0]["cells"]
        for name, (dr, dc) in ORTHOGONAL.items():
            met: set[int] = set()
            edge = False
            for row, col in cells:
                nr, nc = row + dr, col + dc
                if not (0 <= nr < height and 0 <= nc < width):
                    edge = True
                    continue
                if (nr, nc) in cells:
                    continue
                value = pre[nr][nc]
                if value != pre_objects.background:
                    met.add(value)
            guards[f"adj:{colour}:{name}"] = (
                "edge" if edge and not met else (min(met) if met else None)
            )

    if action_id == 6:
        row, col = data.get("y"), data.get("x")
        if isinstance(row, int) and isinstance(col, int) and 0 <= row < height and 0 <= col < width:
            guards["click_colour"] = pre[row][col]
            guards["click_on_background"] = pre[row][col] == pre_objects.background

            # v2 — `clicked_adjacent_to:C`. The feature the E2 slice named as missing: what
            # the CLICKED object touches, as opposed to `adj:C:direction`, which describes
            # the neighbourhood of a colour that happens to denote exactly one object, from a
            # reference point the action never mentions. Per-component and per-click, so it
            # survives a level that duplicates a colour — which is where `adj:` goes silent.
            #
            # Background clicks make K the canvas and the feature near-vacuously True for
            # most C. Not special-cased: the tier-1 selection either finds it separating or
            # it does not, and the guard-quality count below reports which.
            if vocab() == "v2":
                own, cells = _clicked_component(pre, row, col)
                touched: set[int] = set()
                for r, c in cells:
                    for dr, dc in ORTHOGONAL.values():
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < height and 0 <= nc < width:
                            value = int(pre[nr][nc])
                            if value != own:
                                touched.add(value)
                for colour in sorted({int(v) for line in pre for v in line} - {own}):
                    guards[f"clicked_adjacent_to:{colour}"] = colour in touched
        else:
            guards["click_colour"] = None
            guards["click_on_background"] = None
    return guards


# ======================================================================================
# Extraction
# ======================================================================================


def iter_session_transitions(
    game: str, path: Path, *, max_level: int
) -> Iterator[Transition]:
    guid = path.name.split(".")[0]
    pre = None
    pre_objects: _Objects | None = None
    prev_levels = 0
    step = 0
    anomalies: list[dict[str, Any]] = []

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            data = json.loads(line).get("data")
            if not isinstance(data, dict) or "frame" not in data:
                continue  # the trailing session-summary object
            step += 1
            frames = data["frame"]
            levels = int(data.get("levels_completed") or 0)
            increment = levels - prev_levels
            action = data.get("action_input") or {}
            action_id = normalize_action_id(action.get("id"))

            # A zero-frame response (the client's reply to an action taken while GAME_OVER)
            # is not a transition and does not disturb the current pre-state.
            if not frames:
                prev_levels = levels
                continue

            if increment < 0:
                pre = frames[-1]
                pre_objects = None
                prev_levels = levels
                continue

            # RS-E3. `levels_completed` can INCREASE on a RESET without a level having been
            # solved: m0r0/921c2033 step 197 goes 0 -> 1 on a RESET issued out of GAME_OVER,
            # and the single frame it returns is byte-identical to the level-2 opening frame
            # every other m0r0 session reaches by completing. That is bookkeeping restoration
            # after a death, not a completion, and scoring it as one would hand row C a
            # `complete` label for a state no player solved. A RESET never completes a level.
            if increment > 0 and action_id == 0:
                pre = frames[-1]
                pre_objects = None
                prev_levels = levels
                anomalies.append({"step": step, "kind": "reset_level_restore"})
                continue
            roles = frame_roles(
                state=str(data.get("state")),
                n_frames=len(frames),
                completion_increment=increment,
            )
            post = None
            following = None
            for frame, role in zip(frames, roles):
                if role in ("settled", "solved_terminal"):
                    post = frame
                elif role == "next_level_initial":
                    following = frame
            level = prev_levels + 1
            if pre is not None and post is not None and level <= max_level:
                action_data = {
                    k: v for k, v in (action.get("data") or {}).items() if k != "game_id"
                }
                if pre_objects is None:
                    pre_objects = _Objects(pre)
                post_objects = _Objects(post)
                yield Transition(
                    game=game,
                    guid=guid,
                    step=step,
                    level=level,
                    action_id=action_id,
                    action_data=action_data,
                    pre=pre,
                    post=post,
                    completed=increment > 0,
                    effect=effect_signature(pre_objects, post_objects),
                    guards=guard_features(pre, pre_objects, action_id, action_data),
                )
                # the post state becomes the next transition's pre — reuse its components
                pre_objects = post_objects if following is None else None
            else:
                pre_objects = None
            if following is not None:
                pre = following
            elif post is not None:
                pre = post
            prev_levels = levels
    if anomalies:
        ANOMALIES.setdefault(f"{game}/{guid}", []).extend(anomalies)


def load_game(game: str, *, max_level: int = 2) -> list[Transition]:
    if game in EXCLUDED_GAMES:
        raise ValueError(f"{game}: excluded by fidelity — {EXCLUDED_GAMES[game]}")
    transitions: list[Transition] = []
    for path in sorted((CORPUS / game).glob("*.recording.jsonl")):
        guid = path.name.split(".")[0]
        if (game, guid[:8]) in EXCLUDED_SESSIONS:
            EXCLUDED_APPLIED.append(f"{game}/{guid[:8]}")
            continue
        transitions.extend(iter_session_transitions(game, path, max_level=max_level))
    return transitions


def split_half(transitions: list[Transition]) -> tuple[list[Transition], list[Transition]]:
    """Session-level split by sha256(guid) parity — fixed, and never by transition."""
    left, right = [], []
    for transition in transitions:
        digest = hashlib.sha256(transition.guid.encode()).hexdigest()
        (left if int(digest[-1], 16) % 2 == 0 else right).append(transition)
    return left, right


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--census", action="store_true")
    args = parser.parse_args()
    if not args.census:
        parser.error("nothing to do; pass --census")

    for game in args.games:
        transitions = load_game(game)
        by_level: dict[int, list[Transition]] = defaultdict(list)
        for transition in transitions:
            by_level[transition.level].append(transition)
        parts = []
        for level in sorted(by_level):
            rows = by_level[level]
            effects = {row.effect for row in rows}
            no_change = sum(1 for row in rows if not row.effect)
            parts.append(
                f"L{level} n={len(rows):5d} effects={len(effects):4d} "
                f"nochange={no_change:5d} completions={sum(r.completed for r in rows):3d}"
            )
        print(f"{game}  " + " | ".join(parts), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
