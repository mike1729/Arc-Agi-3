#!/usr/bin/env python3
"""E1 — the L1 explorer. Zero model calls.

Implements `notes/e1-explorer.md`: burn level 1 for evidence with a boring, model-free
explorer whose job is coverage, capture, and honest termination. Produces (a) the outcome
distribution E1 is defined to measure and (b) the evidence store E2 synthesizes over.

Skeleton is the ES closure engine's idea — live arcengine expansion, exact settled-frame
hashing, budgets — with the three substitutions the note specifies: candidate-reduced actions,
frontier ROUTING instead of breadth-first exhaustion, and saturation detection.

FORKING
-------
None. Routing is RESET + prefix replay (REPLAY-DET), never engine forking, so E1-pre's
`copy.deepcopy` unfaithfulness on tn36 cannot reach this code. The audit the note asks for as
step zero is discharged by construction: `copy` is not imported.

DEVIATION — the novelty signal (recorded, not silent)
-----------------------------------------------------
The note defines novelty on "the `changed`-signature layer". In E0's actual vocabulary
(`rs_e0.abstract`) the `changed` layer is ``(bool(effect),)`` — two values, so a novelty
counter built on it degenerates to counting new state hashes and would report saturation the
moment both booleans have been seen. The note's gloss "which objects react, to what" describes
E0's `moveset` layer, ``{(kind, colour)}``, not its `changed` layer.

So novelty here = **a new state hash OR a new `moveset` signature**, and BOTH component counts
are reported per game so the choice is auditable and reversible. `changed`-layer counts are
recorded too, to show the degeneracy rather than assert it.

OUTCOMES
--------
    completed            the engine advanced past level 1
    closed               frontier empty — every candidate at every reached state was tested
    closed-unreachable   frontier nonempty but no entry routable, even in suspect mode
    saturated            novelty below threshold over the window, frontier still nonempty
    saturated-by-budget  action or wall-clock budget exhausted first

V2 (notes/e1-explorer.md "v2 — the rerun")
------------------------------------------
The `v2` policy implements the rerun spec: the frontier holds TIER 1 only (advertised
actions + one representative per (colour, shape) class, admission order area desc /
members desc / colour asc / shape lex when a cap ever binds); duplicates + lattice are
tier 2, materialized per state only after every tier-1 candidate at every discovered
state is tested (`closed_t1_at` milestone; terminal `closed` needs tier 2 empty too).
Policy is advance-first — test where you stand, follow transitions into new states,
candidate order rotated by `state-hash mod n` — with dead-end routing to the nearest
clean frontier state, tie-break DEEPEST. `closed-unreachable` is declared only on a
conflict-free graph; with conflicts recorded the explorer drops to WALK MODE instead:
best-effort routes over the full graph (conflicted edges included), divergences
re-observed and kept as evidence, termination left to saturation or budget.

Run:
  .venv/bin/python agent/harness/e1_explorer.py --games dc22 --budget 400
  .venv/bin/python agent/harness/e1_explorer.py --all --jobs 8 --out logs/e1_outcomes.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from arcengine import ActionInput, GameAction  # noqa: E402

from e1_candidates import cull, segment  # noqa: E402
from e1_reach import lattice_points  # noqa: E402
from es_candidates import _Objects  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ITERATION_GAMES,
    ROOT,
    effect_signature,
)

OUTPUT = ROOT / "logs/e1_outcomes.json"
STORE = ROOT / "logs/e1_store"
FORMAT_VERSION = 1

CANDIDATE_CAP = 96  # E1-pre measured; >=96, see notes/e1-pre-recall.md
TIER2_DUP_CAP = 96  # (w) v2: per-tier cap on class-duplicate clicks
LATTICE = 8  # (w)
ACTION_BUDGET = 3000  # (w)
WALL_BUDGET = 20 * 60  # (w) seconds
WINDOW = 200  # (w) frontier test actions
SATURATION = 0.02  # (w) novelty per test action over the window
RETEST_LIMIT = 3  # (w) attempts before a conflicted edge stops being retested

SIMPLE_ACTIONS = (1, 2, 3, 4, 5, 7)
RESET = 0


def _hash(level: int, grid: list) -> str:
    payload = json.dumps([level, grid], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _act(action: tuple[int, int | None, int | None]) -> ActionInput:
    action_id, row, col = action
    data = {} if row is None else {"y": row, "x": col}
    return ActionInput(id=GameAction.from_id(action_id), data=data)


def tier1_nodes(nodes: list[dict], cap: int) -> list[dict]:
    """One representative per (colour, shape) class — v2's whole click frontier.

    Representative = top-left-most member (matches `cull`). Admission order when the cap
    binds on classes (never observed in the corpus, kept as the hidden-game determinism
    guarantee): total class area desc -> member count desc -> colour asc -> shape lex.
    """
    classes: dict[tuple, list[dict]] = {}
    for node in nodes:
        classes.setdefault((node["colour"], node["shape"]), []).append(node)
    ranked = sorted(
        classes.items(),
        key=lambda item: (
            -sum(node["size"] for node in item[1]),
            -len(item[1]),
            item[0][0],
            item[0][1],
        ),
    )
    return [
        min(members, key=lambda node: min(node["cells"]))
        for _, members in ranked[:cap]
    ]


def tier2_points(
    nodes: list[dict], tier1: list[dict], height: int, width: int
) -> list[tuple[int, int]]:
    """Class duplicates (largest-first, capped) then lattice points, deduped in order."""
    tier1_ids = {id(node) for node in tier1}
    duplicates = sorted(
        (node for node in nodes if id(node) not in tier1_ids),
        key=lambda node: (-node["size"], min(node["cells"])),
    )[:TIER2_DUP_CAP]
    seen = {node["point"] for node in tier1}
    out: list[tuple[int, int]] = []
    for point in [node["point"] for node in duplicates] + list(
        lattice_points(height, width, LATTICE)
    ):
        if point not in seen:
            seen.add(point)
            out.append(point)
    return out


class Explorer:
    def __init__(
        self, game: str, *, budget: int, wall: float, cap: int, policy: str = "shallowest"
    ):
        self.game = game
        self.policy = policy
        self.driver = ReplayDriver(game)
        self.engine = self.driver.new_game()
        self.budget = budget
        self.wall = wall
        self.cap = cap

        self.states: dict[str, list] = {}  # hash -> settled grid
        self.discovered: dict[str, int] = {}  # hash -> discovery index
        self.prefix: dict[str, list] = {}  # hash -> shortest action list from origin
        self.frontier: dict[str, list] = {}  # hash -> untested candidate actions
        self.available: dict[str, tuple] = {}  # hash -> advertised actions at discovery
        self.edges: dict[tuple[str, tuple], str] = {}
        self.conflicted: set[tuple[str, tuple]] = set()
        self.attempts: dict[tuple[str, tuple], int] = {}
        self.suspect: set[str] = set()
        self.deferred: set[tuple[str, tuple]] = set()

        # v2 bookkeeping
        self.walk_mode_at: int | None = None
        self.closed_t1_at: int | None = None
        self.tier2_states: set[str] = set()
        self.tier2_entries: set[tuple[str, tuple]] = set()
        self.reset_anomaly_count = 0

        self.signatures_moveset: set[tuple] = set()
        self.signatures_changed: set[tuple] = set()
        self.novelty: deque[int] = deque(maxlen=WINDOW)

        self.actions_used = 0
        self.test_actions = 0
        self.routing_actions = 0
        self.alias_conflicts: list[dict[str, Any]] = []
        self.anomalies: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.completed_at: int | None = None
        self.started = time.monotonic()
        self.origin: str | None = None
        self.current: str | None = None
        self.level = 1

        # -- REPEATED OBSERVATIONS (notes/e1-store-repeats.md) ---------------------------
        # The store could not previously disagree with itself. `record()` was reachable only
        # from `test()`, and `test()` pops each candidate from a state's frontier exactly
        # once, so a repeated `(pre, action)` row was unreachable BY CONSTRUCTION and every
        # aliasing census over the store read zero — which looks like "no hidden state" and
        # actually means "no ability to see any". Measured consequence: E2 found a real hidden
        # in-episode action counter in four games whose evidence the store had discarded.
        #
        # Two additions, both of which leave the explorer's TRAJECTORY untouched:
        #   `performs`      every action, routing included, with its pre/post digests. Routing
        #                   re-executes known edges constantly (sc25: 46% of the budget) and
        #                   those were free repeat observations we were throwing away.
        #   `episode_step`  the in-episode action count at the pre-state. A repeat is only
        #                   INTERPRETABLE with it: two observations of one edge at the same
        #                   count test determinism, at different counts they test aliasing.
        self.performs: list[dict[str, Any]] = []
        self.last_reset = 0  # environment creation is an implicit RESET
        self.confirm_budget = 0
        self.confirm_actions = 0
        self.confirmations: list[dict[str, Any]] = []

    def episode_step(self) -> int:
        """Actions executed since the last RESET, at the CURRENT pre-state."""
        return self.actions_used - self.last_reset

    # -- engine ---------------------------------------------------------------------
    def perform(
        self, action: tuple[int, int | None, int | None], *, source: str = "test"
    ) -> dict[str, Any]:
        source_state = self.current
        episode_step = self.episode_step()
        response = self.driver.perform(self.engine, _act(action))
        self.actions_used += 1
        frames = _plain_frames(response.frame or [])
        grid = frames[-1] if frames else None
        levels = response.levels_completed
        self.performs.append(
            {
                "step": self.actions_used,
                "episode_step": episode_step,
                "source": source,
                "pre": source_state,
                "action": list(action),
                "post": _hash(self.level, grid) if grid is not None else None,
                "levels": int(levels) if levels is not None else None,
                "state": str(getattr(response.state, "value", response.state)),
            }
        )
        if action[0] == RESET:
            self.last_reset = self.actions_used
        return {
            "grid": grid,
            "frames": len(frames),
            "levels": int(levels) if levels is not None else None,
            "state": str(getattr(response.state, "value", response.state)),
            "available": tuple(
                int(getattr(item, "value", item))
                for item in (getattr(response, "available_actions", None) or [])
            ),
        }

    def out_of_budget(self) -> bool:
        return (
            self.actions_used >= self.budget
            or time.monotonic() - self.started >= self.wall
        )

    # -- candidates -----------------------------------------------------------------
    def candidates(self, grid: list, available: tuple[int, ...]) -> list[tuple]:
        out: list[tuple] = [
            (action_id, None, None)
            for action_id in SIMPLE_ACTIONS
            if not available or action_id in available
        ]
        if not available or 6 in available:
            points = [node["point"] for node in cull(segment(grid), self.cap)]
            out.extend((6, row, col) for row, col in points)
            seen = set(points)
            out.extend(
                (6, row, col)
                for row, col in lattice_points(len(grid), len(grid[0]), LATTICE)
                if (row, col) not in seen
            )
        return out

    def _rotate(self, digest: str, items: list[tuple]) -> list[tuple]:
        """v2: start each state's candidate order at hash mod n — deterministic, spreads
        which candidate an advance-first walk tests first across states."""
        if len(items) < 2:
            return items
        pivot = int(digest, 16) % len(items)
        return items[pivot:] + items[:pivot]

    def tier1_candidates(self, digest: str, grid: list, available: tuple) -> list[tuple]:
        out: list[tuple] = [
            (action_id, None, None)
            for action_id in SIMPLE_ACTIONS
            if not available or action_id in available
        ]
        if not available or 6 in available:
            reps = tier1_nodes(segment(grid), self.cap)
            out.extend((6, row, col) for row, col in (node["point"] for node in reps))
        return self._rotate(digest, out)

    def materialize_tier2(self, digest: str) -> int:
        """Append the state's tier-2 candidates (duplicates + lattice) to its frontier."""
        self.tier2_states.add(digest)
        grid = self.states[digest]
        available = self.available.get(digest, ())
        if available and 6 not in available:
            return 0
        nodes = segment(grid)
        reps = tier1_nodes(nodes, self.cap)
        added = [
            (6, row, col)
            for row, col in tier2_points(nodes, reps, len(grid), len(grid[0]))
        ]
        added = self._rotate(digest, added)
        self.frontier.setdefault(digest, []).extend(added)
        self.tier2_entries.update((digest, action) for action in added)
        return len(added)

    # -- graph ----------------------------------------------------------------------
    def observe(self, result: dict[str, Any], prefix: list) -> str | None:
        grid = result["grid"]
        if grid is None:
            return None
        digest = _hash(self.level, grid)
        if digest not in self.states:
            self.discovered[digest] = len(self.states)
            self.states[digest] = grid
            self.prefix[digest] = list(prefix)
            self.available[digest] = tuple(result["available"])
            self.frontier[digest] = (
                self.tier1_candidates(digest, grid, result["available"])
                if self.policy == "v2"
                else self.candidates(grid, result["available"])
            )
        elif len(prefix) < len(self.prefix.get(digest, prefix)):
            self.prefix[digest] = list(prefix)
        return digest

    def _bfs(self, source: str, *, goal: str | None) -> list[tuple] | None:
        """Shortest route over never-conflicted, non-suspect edges.

        ``goal=None`` finds the nearest state with untested candidates; a hash finds that
        state specifically.
        """
        seen = {source}
        queue: deque[tuple[str, list]] = deque([(source, [])])
        while queue:
            node, path = queue.popleft()
            if node == goal if goal is not None else (
                self.frontier.get(node) and node not in self.suspect
            ):
                return path
            for (origin, action), target in self.edges.items():
                if origin != node or target in seen:
                    continue
                if (origin, action) in self.conflicted or origin in self.suspect:
                    continue
                seen.add(target)
                queue.append((target, path + [action]))
        return None

    def clean_path(self, source: str) -> list[tuple] | None:
        return self._bfs(source, goal=None)

    def _adjacency(self, *, clean: bool) -> dict[str, list[tuple[tuple, str]]]:
        adjacency: dict[str, list[tuple[tuple, str]]] = {}
        for (origin, action), target in self.edges.items():
            if clean and ((origin, action) in self.conflicted or origin in self.suspect):
                continue
            adjacency.setdefault(origin, []).append((action, target))
        return adjacency

    def _bfs_frontier(self, source: str, *, clean: bool) -> list[tuple] | None:
        """v2 routing: nearest state with untested candidates, tie-break DEEPEST.

        ``clean=False`` is walk mode — the full graph, conflicted edges and suspect
        nodes included, because a best-effort route that diverges still moves us and
        still records evidence.
        """
        adjacency = self._adjacency(clean=clean)
        seen = {source}
        layer: list[tuple[str, list]] = [(source, [])]
        while layer:
            matches = [
                (node, path)
                for node, path in layer
                if self.frontier.get(node) and (not clean or node not in self.suspect)
            ]
            if matches:
                return max(
                    matches,
                    key=lambda item: (
                        len(self.prefix.get(item[0], [])),
                        -self.discovered.get(item[0], 0),
                    ),
                )[1]
            following: list[tuple[str, list]] = []
            for node, path in layer:
                for action, target in adjacency.get(node, []):
                    if target not in seen:
                        seen.add(target)
                        following.append((target, path + [action]))
            layer = following
        return None

    def _reset_target(self, *, clean: bool) -> str | None:
        """Cheapest RESET+prefix frontier target; failed attempts rotate targets."""
        entries: list[tuple[int, int, int, str]] = []
        for digest, actions in self.frontier.items():
            if not actions:
                continue
            if clean and digest in self.suspect:
                continue
            key = (digest, ("route",))
            attempts = self.attempts.get(key, 0)
            if clean and attempts >= RETEST_LIMIT:
                self.deferred.add(key)
                continue
            entries.append(
                (
                    attempts,
                    len(self.prefix.get(digest, [])),
                    self.discovered.get(digest, 0),
                    digest,
                )
            )
        if not entries:
            return None
        return min(entries)[3]

    # -- routing --------------------------------------------------------------------
    def walk(self, path: list[tuple], *, expect: str | None = None) -> bool:
        """Execute a route step-validated. False on divergence; the bad edge is conflicted."""
        for action in path:
            source = self.current
            result = self.perform(action, source="walk")
            self.routing_actions += 1
            if result["levels"] and result["levels"] > 0:
                self.completed_at = self.actions_used
                return False
            digest = self.observe(result, self.prefix.get(source, []) + [action])
            expected = self.edges.get((source, action))
            self.current = digest
            if expected is not None and digest != expected:
                self.conflicted.add((source, action))
                self.suspect.add(source)
                self.alias_conflicts.append(
                    {"state": source, "action": list(action), "step": self.actions_used}
                )
                return False
            if self.out_of_budget():
                return False
        return expect is None or self.current == expect

    def reset_route(self, target: str) -> bool:
        result = self.perform((RESET, None, None), source="reset")
        self.routing_actions += 1
        digest = self.observe(result, [])
        if self.origin is not None and digest != self.origin:
            self.reset_anomaly_count += 1
            if self.reset_anomaly_count <= 10:  # keep the first ten; count the rest
                self.anomalies.append(
                    {"kind": "reset_not_origin", "step": self.actions_used, "got": digest}
                )
        self.current = digest
        if target == digest:
            return True
        return self.walk(list(self.prefix.get(target, [])), expect=target)

    # -- the loop -------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        result = self.perform((RESET, None, None), source="boot")
        if result["grid"] is None:
            return self.summary("no_initial_frame")
        self.origin = self.current = self.observe(result, [])

        outcome = None
        while outcome is None:
            if self.out_of_budget():
                outcome = "saturated-by-budget"
                break
            if self.completed_at is not None:
                outcome = "completed"
                break

            pending = [
                (digest, actions)
                for digest, actions in self.frontier.items()
                if actions
            ]
            if not pending:
                if self.policy == "v2":
                    missing = [
                        digest
                        for digest in self.states
                        if digest not in self.tier2_states
                    ]
                    if missing:
                        if self.closed_t1_at is None:
                            self.closed_t1_at = self.actions_used
                        if sum(self.materialize_tier2(digest) for digest in missing):
                            continue
                outcome = "closed"
                break

            if len(self.novelty) == WINDOW and sum(self.novelty) / WINDOW < SATURATION:
                outcome = "saturated"
                break

            target = self.select(pending)
            if self.out_of_budget() or self.completed_at is not None:
                continue  # the loop top names the outcome
            if target is None:
                if (
                    self.policy == "v2"
                    and self.walk_mode_at is None
                    and (self.conflicted or self.suspect)
                ):
                    # unreachable on a graph with known identity failures is not a
                    # verdict — push on best-effort instead of declaring one
                    self.walk_mode_at = self.actions_used
                    continue
                outcome = "closed-unreachable"
                break
            if not self.test(target):
                continue
        if self.confirm_budget > 0 and self.completed_at is None:
            self.confirm()
        return self.summary(outcome)

    # -- confirmation pass (repeated observations, deliberately) ------------------------
    def paths_by_length(self, max_length: int) -> dict[str, dict[int, list[tuple]]]:
        """Per state, one route from the origin of each achievable length up to `max_length`.

        The graph keeps only the SHORTEST prefix per state, which is exactly the wrong thing
        to keep for this purpose: a second route of a DIFFERENT length is what re-observes an
        edge at a different in-episode count. Routes are proposed here and verified by
        execution in `confirm` — a proposal that does not land on its state is discarded, and
        the divergence is itself recorded as evidence.
        """
        adjacency: dict[str, list[tuple[tuple, str]]] = {}
        for (origin, action), target in self.edges.items():
            adjacency.setdefault(origin, []).append((action, target))
        paths: dict[str, dict[int, list[tuple]]] = {self.origin: {0: []}}
        layer = {self.origin: []}
        for length in range(1, max_length + 1):
            following: dict[str, list[tuple]] = {}
            for node, path in layer.items():
                for action, target in adjacency.get(node, ()):
                    if length in paths.get(target, {}) or target in following:
                        continue
                    following[target] = path + [action]
            for node, path in following.items():
                paths.setdefault(node, {})[length] = path
            layer = following
            if not layer:
                break
        return paths

    def confirm(self, *, max_path: int = 12) -> None:
        """Spend `confirm_budget` actions re-observing tested edges at a DIFFERENT count.

        Routing repeats are nearly free but nearly useless on their own: RESET + prefix replay
        reproduces the SAME in-episode count the edge was first seen at, so it tests
        determinism and not aliasing. The only way to get an aliasing observation is to reach
        the state by a route of a different LENGTH, which is what this does.

        Order is deterministic and value-first: edges the explorer already caught disagreeing,
        then a spread over the rest, cheapest route first so the budget buys the most
        observations. Every instance is RESET-rooted and digest-checked before the target
        action is executed.
        """
        seen: dict[tuple[str, tuple], int] = {}
        for row in self.transitions:
            key = (row["pre"], tuple(row["action"]))
            seen.setdefault(key, row["episode_step"])
        paths = self.paths_by_length(max_path)

        candidates: list[tuple[int, int, str, tuple, list[tuple]]] = []
        for (state, action), first_count in seen.items():
            routes = paths.get(state) or {}
            alternates = sorted(
                length for length in routes if length != first_count
            )
            if not alternates:
                continue
            length = alternates[0]
            candidates.append(
                (
                    0 if (state, action) in self.conflicted else 1,  # conflicted first
                    length,  # then cheapest
                    state,
                    action,
                    routes[length],
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1], item[2], str(item[3])))

        spent = 0
        for _, length, state, action, route in candidates:
            cost = len(route) + 2  # RESET + route + the target action
            if spent + cost > self.confirm_budget:
                continue
            spent += cost
            result = self.perform((RESET, None, None), source="confirm")
            digest = self.observe(result, [])
            self.current = digest
            walked: list[tuple] = []
            for step_action in route:
                walked.append(step_action)
                result = self.perform(step_action, source="confirm")
                # the prefix handed to `observe` must be the route ACTUALLY walked -- it is
                # what `prefix` will record for a state first seen here, and a wrong one
                # would plant exactly the kind of unreplayable shortest-path this pass exists
                # to expose
                digest = self.observe(result, list(walked))
                self.current = digest
            if digest != state:
                self.confirmations.append(
                    {
                        "state": state,
                        "action": list(action),
                        "route_length": length,
                        "outcome": "route_diverged",
                        "landed": digest,
                    }
                )
                continue
            episode_step = self.episode_step()
            pre_objects = _Objects(self.states[state])
            result = self.perform(action, source="confirm")
            post = (
                _hash(self.level, result["grid"]) if result["grid"] is not None else None
            )
            if result["levels"] and post is not None:
                # same rule as `test`: retain the completion frame, it is a positive example
                self.states.setdefault(post, result["grid"])
            self.record(
                state, action, result, pre_objects,
                completed=bool(result["levels"]),
                episode_step=episode_step,
                source="confirm",
            )
            previous = self.edges.get((state, action))
            agrees = previous is None or post is None or previous == post
            if not agrees:
                self.conflicted.add((state, action))
                self.suspect.add(state)
                self.alias_conflicts.append(
                    {"state": state, "action": list(action), "step": self.actions_used}
                )
            self.confirmations.append(
                {
                    "state": state,
                    "action": list(action),
                    "route_length": length,
                    "first_seen_at_count": seen[(state, action)],
                    "reobserved_at_count": episode_step,
                    "outcome": "agrees" if agrees else "disagrees",
                    "first_post": previous,
                    "post": post,
                }
            )
            if post is not None:
                self.edges[(state, action)] = post
            self.current = post
        self.confirm_actions = spent

    def select(self, pending: list[tuple[str, list]]) -> str | None:
        if self.policy == "v2":
            return self.select_v2(pending)
        if self.policy == "shallowest":
            return self.select_shallowest(pending)
        return self.select_nearest(pending)

    def select_v2(self, pending: list[tuple[str, list]]) -> str | None:
        """Advance-first with rotated candidates; dead-end routing nearest/deepest.

        Every pass either returns a testable state, consumes >=1 action, or proves
        nothing is routable (None) — so the loop always terminates on budget.
        """
        while not self.out_of_budget() and self.completed_at is None:
            if self.current and self.frontier.get(self.current):
                return self.current  # distance 0 — the adopted DFS degeneracy
            clean = self.walk_mode_at is None
            path = (
                self._bfs_frontier(self.current, clean=clean) if self.current else None
            )
            if path:
                self.walk(path)  # divergence conflicts the edge; re-plan from landing
                continue
            target = self._reset_target(clean=clean)
            if target is None:
                return None
            if not self.reset_route(target):
                key = (target, ("route",))
                self.attempts[key] = self.attempts.get(key, 0) + 1
            # continue: either standing on the target, or re-planning from wherever
            # the divergence left us — both consumed actions
        return self.current if self.current and self.frontier.get(self.current) else None

    def select_shallowest(self, pending: list[tuple[str, list]]) -> str | None:
        """Exhaust the shallowest state with untested candidates, routing back to it.

        The note's `nearest` policy never routes: the state you are standing on is always
        new and therefore always has untested candidates, so distance 0 always wins and the
        explorer walks depth-first forever without exhausting anything. This arm restores
        what the routing-overhead metric presupposes — that returning to a state to test its
        next candidate is the dominant cost.
        """
        order = sorted(
            pending,
            key=lambda item: (len(self.prefix.get(item[0], [])), self.discovered.get(item[0], 0)),
        )
        for digest, _ in order:
            if digest == self.current:
                return digest
            path = self._bfs(self.current, goal=digest) if self.current else None
            if path is not None and self.walk(path, expect=digest):
                return digest
            if self.out_of_budget() or self.completed_at is not None:
                return self.current
            key = (digest, ("route",))
            if self.attempts.get(key, 0) >= RETEST_LIMIT:
                self.deferred.add(key)
                continue
            if self.reset_route(digest):
                return digest
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if self.out_of_budget() or self.completed_at is not None:
                return self.current
        return None

    def select_nearest(self, pending: list[tuple[str, list]]) -> str | None:
        """Nearest routable frontier state: clean walk from here, else RESET + prefix."""
        path = self.clean_path(self.current) if self.current else None
        if path is not None:
            if self.walk(path):
                return self.current
            return self.current if self.frontier.get(self.current) else None

        clean = [
            (digest, actions) for digest, actions in pending if digest not in self.suspect
        ]
        pool = clean or pending  # suspect mode: push on rather than surrender
        for digest, _ in sorted(pool, key=lambda item: len(self.prefix.get(item[0], []))):
            key = (digest, ("route",))
            if self.attempts.get(key, 0) >= RETEST_LIMIT:
                self.deferred.add(key)
                continue
            if self.reset_route(digest):
                return digest
            # only FAILED routes count against the retest limit — a state routed to
            # successfully three times must not become permanently deferred
            self.attempts[key] = self.attempts.get(key, 0) + 1
            if self.out_of_budget() or self.completed_at is not None:
                return self.current
        return None

    def test(self, digest: str) -> bool:
        actions = self.frontier.get(digest)
        if not actions:
            return False
        action = actions.pop(0)
        pre_grid = self.states[digest]
        pre_objects = _Objects(pre_grid)

        episode_step = self.episode_step()
        result = self.perform(action, source="test")
        self.test_actions += 1
        if result["levels"] and result["levels"] > 0:
            self.completed_at = self.actions_used
            if result["grid"] is not None:
                # retain the completion frame: it is the store's one positive goal
                # example, and a post hash without its grid corrupts goal mining (E2)
                self.states.setdefault(_hash(self.level, result["grid"]), result["grid"])
            self.record(
                digest, action, result, pre_objects, completed=True,
                episode_step=episode_step,
            )
            return True

        known = len(self.states)
        post = self.observe(result, self.prefix.get(digest, []) + [action])
        fresh_state = len(self.states) > known
        signature = self.record(
            digest, action, result, pre_objects, completed=False,
            episode_step=episode_step,
        )

        previous = self.edges.get((digest, action))
        if previous is not None and post is not None and previous != post:
            self.conflicted.add((digest, action))
            self.suspect.add(digest)
            self.alias_conflicts.append(
                {"state": digest, "action": list(action), "step": self.actions_used}
            )
        if post is not None:
            self.edges[(digest, action)] = post
        self.current = post
        self.novelty.append(int(bool(fresh_state or signature)))
        return True

    def record(
        self,
        digest: str,
        action: tuple,
        result: dict[str, Any],
        pre_objects: _Objects,
        *,
        completed: bool,
        episode_step: int | None = None,
        source: str = "test",
    ) -> bool:
        """Append the transition to the store. Returns True if its moveset is new.

        `episode_step` is the in-episode action count at the PRE-state and is what makes a
        repeated `(pre, action)` row interpretable: same count is a determinism check,
        different counts is an aliasing check. Defaults to the count at call time so any
        caller that does not thread it through still records something true.
        """
        grid = result["grid"]
        if grid is None:
            return False
        effect = effect_signature(pre_objects, _Objects(grid))
        moveset = tuple(sorted({(event[0], event[1]) for event in effect}))
        changed = (bool(effect),)
        fresh = moveset not in self.signatures_moveset
        self.signatures_moveset.add(moveset)
        self.signatures_changed.add(changed)
        self.transitions.append(
            {
                "pre": digest,
                "action": list(action),
                "post": _hash(self.level, grid),
                "level": self.level,
                "completed": completed,
                "effect": [list(event) for event in effect],
                "frames": result["frames"],
                "state": result["state"],
                "step": self.actions_used,
                "route_mode": (
                    "walk"
                    if self.walk_mode_at is not None
                    else "suspect"
                    if digest in self.suspect
                    else "clean"
                ),
                "tier": 2 if (digest, action) in self.tier2_entries else 1,
                "prefix": len(self.prefix.get(digest, [])),
                "episode_step": (
                    self.episode_step() - 1 if episode_step is None else episode_step
                ),
                "source": source,
            }
        )
        return fresh

    def summary(self, outcome: str | None) -> dict[str, Any]:
        elapsed = time.monotonic() - self.started
        remaining = sum(len(actions) for actions in self.frontier.values())
        return {
            "game": self.game,
            "outcome": outcome,
            "actions": self.actions_used,
            "test_actions": self.test_actions,
            "routing_actions": self.routing_actions,
            "routing_overhead": (
                self.routing_actions / self.test_actions if self.test_actions else None
            ),
            "actions_to_outcome": self.completed_at,
            "incidental_completion": self.completed_at is not None,
            "unique_states": len(self.states),
            "transitions": len(self.transitions),
            "frontier_remaining": remaining,
            "alias_conflicts": len(self.alias_conflicts),
            "alias_conflict_edges": len(self.conflicted),
            "alias_suspect_nodes": len(self.suspect),
            "deferred": len(self.deferred),
            "closed_t1_at": self.closed_t1_at,
            "walk_mode_at": self.walk_mode_at,
            "tier2_states": len(self.tier2_states),
            "reset_anomalies": self.reset_anomaly_count,
            "performs": len(self.performs),
            "confirm_actions": self.confirm_actions,
            "confirmations": len(self.confirmations),
            "confirmations_disagreeing": sum(
                1 for row in self.confirmations if row["outcome"] == "disagrees"
            ),
            "confirmations_route_diverged": sum(
                1 for row in self.confirmations if row["outcome"] == "route_diverged"
            ),
            "moveset_signatures": len(self.signatures_moveset),
            "changed_signatures": len(self.signatures_changed),
            "novelty_window": (
                sum(self.novelty) / len(self.novelty) if self.novelty else None
            ),
            "anomalies": self.anomalies,
            "wall_clock": round(elapsed, 1),
        }


def run_game(job: tuple[str, int, float, int, Path | None, str, int]) -> dict[str, Any]:
    game, budget, wall, cap, store_dir, policy, confirm_budget = job
    explorer = Explorer(game, budget=budget, wall=wall, cap=cap, policy=policy)
    explorer.confirm_budget = confirm_budget
    try:
        summary = explorer.run()
    except Exception as error:  # a game that breaks the driver is a result, not a crash
        return {"game": game, "outcome": "error", "error": f"{type(error).__name__}: {error}"}
    summary["policy"] = policy
    if store_dir is not None:
        store_dir.mkdir(parents=True, exist_ok=True)
        (store_dir / f"{game}.states.json").write_text(
            json.dumps(explorer.states, separators=(",", ":"))
        )
        with (store_dir / f"{game}.transitions.jsonl").open("w") as handle:
            for row in explorer.transitions:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        # Every action, routing included. This is the file an aliasing census reads; the
        # transitions log alone cannot hold a repeated (pre, action) row unless the
        # confirmation pass ran.
        with (store_dir / f"{game}.performs.jsonl").open("w") as handle:
            for row in explorer.performs:
                handle.write(json.dumps(row, separators=(",", ":")) + "\n")
        (store_dir / f"{game}.graph.json").write_text(
            json.dumps(
                {
                    "origin": explorer.origin,
                    "edges": [
                        [source, list(action), target]
                        for (source, action), target in explorer.edges.items()
                    ],
                    # SORTED. `conflicted` is a set of tuples containing strings, so its
                    # iteration order follows PYTHONHASHSEED and differed between two runs of
                    # an otherwise byte-identical trajectory. That made the graph file falsely
                    # non-reproducible and would have been read as a real divergence by any
                    # replay gate that compared it. `suspect` was already sorted.
                    "conflicted": sorted(
                        ([source, list(action)] for source, action in explorer.conflicted),
                        key=lambda item: (item[0], str(item[1])),
                    ),
                    "suspect": sorted(explorer.suspect),
                    "conflict_records": explorer.alias_conflicts,
                    "confirmations": explorer.confirmations,
                    "closed_t1_at": explorer.closed_t1_at,
                    "walk_mode_at": explorer.walk_mode_at,
                    "prefix": {k: [list(a) for a in v] for k, v in explorer.prefix.items()},
                },
                separators=(",", ":"),
            )
        )
    return summary


def _emit(row: dict[str, Any]) -> None:
    if row.get("outcome") == "error":
        print(f"{row['game']:5s} ERROR  {row['error']}", flush=True)
        return
    overhead = row["routing_overhead"]
    print(
        f"{row['game']:5s} {str(row['outcome']):20s} {row['actions']:5d} "
        f"{row['test_actions']:5d} {row['routing_actions']:6d} "
        f"{'  n/a' if overhead is None else f'{overhead:5.2f}'} "
        f"{row['unique_states']:6d} {row['transitions']:6d} "
        f"{row['frontier_remaining']:7d} {row['alias_conflicts']:5d} "
        f"{row['moveset_signatures']:5d} {row['wall_clock']:6.1f} "
        f"{row.get('confirmations', 0):5d} {row.get('confirmations_disagreeing', 0):4d}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=list(ITERATION_GAMES))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--budget", type=int, default=ACTION_BUDGET)
    parser.add_argument("--wall", type=float, default=WALL_BUDGET)
    parser.add_argument("--cap", type=int, default=CANDIDATE_CAP)
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument(
        "--policy",
        choices=("v2", "shallowest", "nearest"),
        default="v2",
        help=(
            "`v2` is the rerun spec (tier-1 frontier, advance-first, walk mode); "
            "`nearest` is SS3 as written (never routes); `shallowest` the v1 correction"
        ),
    )
    parser.add_argument(
        "--confirm-budget",
        type=int,
        default=0,
        help=(
            "extra actions spent AFTER the main loop re-observing already-tested edges at a "
            "different in-episode count. 0 (default) leaves the trajectory byte-identical to "
            "the v2 store; this is the only knob here that costs actions"
        ),
    )
    parser.add_argument("--no-store", action="store_true")
    parser.add_argument("--store-dir", type=Path, default=STORE)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    games = (
        [game for game in ALL_GAMES if game not in EXCLUDED_GAMES]
        if args.all
        else list(args.games)
    )
    jobs = [
        (
            game,
            args.budget,
            args.wall,
            args.cap,
            None if args.no_store else args.store_dir,
            args.policy,
            args.confirm_budget,
        )
        for game in games
    ]
    print(
        f"{'game':5s} {'outcome':20s} {'act':>5s} {'test':>5s} {'route':>6s} {'ovh':>5s} "
        f"{'states':>6s} {'trans':>6s} {'front':>7s} {'alias':>5s} {'msig':>5s} {'sec':>6s} "
        f"{'confm':>5s} {'dis':>4s}",
        flush=True,
    )
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_game, job): job[0] for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            game = futures[future]
            try:
                row = future.result()
            except Exception as error:
                row = {"game": game, "outcome": "error", "error": f"{type(error).__name__}: {error}"}
            results.append(row)
            _emit(row)
    results.sort(key=lambda row: games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "budget": {"actions": args.budget, "wall_seconds": args.wall},
        "cap": args.cap,
        "policy": args.policy,
        "confirm_budget": args.confirm_budget,
        "novelty": {"window": WINDOW, "threshold": SATURATION, "signal": "moveset|state"},
        "games": {row["game"]: row for row in results},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
