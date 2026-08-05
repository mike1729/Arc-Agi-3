#!/usr/bin/env python3
"""E3 stages X1 and X2 — the forward model over mined rules, and search over it.

Design note: `notes/e3-executor.md`; task note: `notes/e3-x1-x2.md`. Zero model calls, zero
game contact: everything here reads the frozen explorer store `logs/e1_store_v2/` and the
E0 miner, and writes numbers. X3 (live execution) and X4 (E3 proper) are out of scope.

WHAT A FORWARD STEP IS
----------------------
    state          a grid (the store's own state representation), plus its object
                   catalogue `_Objects` — a step is O(objects), never O(64x64)
    step           action -> guard features -> the rule that fires -> a predicted EFFECT
                   SIGNATURE -> a predicted POST GRID
    confidence     `confident`  a zero-contradiction rule fires (miner tiers `tier0` and
                                `tier1`: an unguarded key with one effect, or a key one
                                guard partitions into single-effect cells)
                   `weak`       only a `majority`-tier rule fires — the key is unresolved
                                in the guard vocabulary and the rule predicts the modal
                                effect, so it can be wrong on its own training evidence
                   `uncovered`  no rule for the key

    NAMING COLLISION, stated once: the design note's "tier-1 = confident" means the top
    trust tier, which in `rs_e0`'s vocabulary is tier0 AND tier1 — both are mined
    zero-contradiction. `weak` is exactly `rs_e0`'s `majority`.

THE TAUTOLOGY GUARD
-------------------
Rules are mined on the same store they are replayed against, so `confident` EFFECT accuracy
is 1.0 by construction and proves nothing. The numbers that are not tautological, and are
what X1 reports:

  * coverage per confidence class — how much of the graph is plannable, at what trust;
  * `weak`-class effect accuracy — majority rules genuinely can be wrong;
  * RECONSTRUCTION FIDELITY — predicting an effect signature is not producing a next state.
    The signature is position-free by design (`rs_transitions`), which is what lets a rule
    transfer across levels and is exactly what a planner cannot consume directly. X1 applies
    the predicted events to the pre-grid and compares the result to the recorded post-grid,
    cell for cell. Where the grammar cannot pin a next state it is reported as
    UNDERDETERMINED by kind, which is a finding about the effect vocabulary, not a bug:
      `appear`         no position or extent for the new component
      `reshape`        the new cell set is not described at all
      `assignment`     k events for m > k same-colour components: which ones is not said
      `over_assignment` more consuming events than components (only reachable if the
                       predicted effect came from a different board than the one it fires on)
      `collision`      two placements land differing colours on one cell — z-order unsaid
      `out_of_bounds`  a predicted translation leaves the grid
    Reported twice: against the RECORDED effect (a property of the grammar alone) and
    against the PREDICTED effect (the property a planner has).
  * moveset-level match as the coarser second view.

X2 — PLANNER ON KNOWN GROUND
----------------------------
For each cohort game (lp85, r11l, lf52, sp80 — the four L1 completions the E1 v2 explorer
found autonomously) search from the L1 origin over the forward model for the store's own
recorded completion pre-state, then append the recorded completion action. Cost = actions
(the scorer's currency), closed set on state hash, expansion policy per the design:
confident edges first, relax to weak only if no plan is found, never through uncovered.

Run:
  .venv/bin/python agent/harness/e3_executor.py --stage x1 --out logs/e3_x1.json
  .venv/bin/python agent/harness/e3_executor.py --stage x2 --out logs/e3_x2.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from es_candidates import _Objects  # noqa: E402
from rs_e0 import Rule, _fire, abstract, mine  # noqa: E402
from rs_transitions import (  # noqa: E402
    ROOT,
    Transition,
    effect_signature,
    guard_features,
    set_vocab,
    vocab,
)

STORE = ROOT / "logs/e1_store_v2"
AUDIT = ROOT / "logs/e1_prefix_audit.json"
METADATA = ROOT / "data/environment_files"
FORMAT_VERSION = 1

# The four games the E1 v2 explorer completed L1 on autonomously (notes/e3-executor.md).
COHORT = ("lp85", "r11l", "lf52", "sp80")
MODES = ("full", "moveset")

# (w) search caps. A timeout is a result about branching, reported with the progress at cap.
NODE_CAP = 400_000
TIME_CAP = 600.0


def _hash(level: int, grid: list) -> str:
    """The explorer's own state digest (`e1_explorer._hash`), reproduced so a PREDICTED
    grid is comparable with a stored one. Any other hash would make the goal test vacuous."""
    return hashlib.sha256(
        json.dumps([level, grid], separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _tupleize(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tupleize(item) for item in value)
    return value


# ======================================================================================
# Store loading — the e2_dose.load_store pattern, with the digests retained
# ======================================================================================


def load_store(game: str) -> dict[str, Any]:
    """Explorer store -> canonical Transitions plus everything the planner needs.

    Effects and guards are RECOMPUTED through the canonical pipeline, never parsed from the
    store, wherever both grids exist; completion rows — whose post frame the explorer hashes
    but never retains as a state — fall back to the stored effect signature and are marked,
    so no consumer reads a placeholder `post` as a real frame.
    """
    states: dict[str, list] = json.loads((STORE / f"{game}.states.json").read_text())
    graph = json.loads((STORE / f"{game}.graph.json").read_text())
    transitions: list[Transition] = []
    rows: list[dict[str, Any]] = []
    post_missing: set[int] = set()
    with (STORE / f"{game}.transitions.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            pre = states.get(row["pre"])
            if pre is None:  # cannot score or guard without the pre frame
                continue
            post = states.get(row["post"])
            if post is None:
                post_missing.add(row["step"])
            action_id, click_row, click_col = row["action"]
            data = {"y": click_row, "x": click_col} if action_id == 6 else {}
            pre_objects = _Objects(pre)
            effect = (
                effect_signature(pre_objects, _Objects(post))
                if post is not None
                else _tupleize(row["effect"])
            )
            transitions.append(
                Transition(
                    game=game,
                    guid="e1v2",
                    step=row["step"],
                    level=1,
                    action_id=action_id,
                    action_data=data,
                    pre=pre,
                    post=post if post is not None else pre,
                    completed=bool(row["completed"]),
                    effect=effect,
                    guards=guard_features(pre, pre_objects, action_id, data),
                )
            )
            rows.append(row)
    order = sorted(range(len(transitions)), key=lambda i: transitions[i].step)
    return {
        "game": game,
        "transitions": [transitions[i] for i in order],
        "rows": [rows[i] for i in order],
        "states": states,
        "graph": graph,
        "post_missing": post_missing,
    }


def confidence(rule: Rule | None) -> str:
    if rule is None:
        return "uncovered"
    return "weak" if rule.tier == "majority" else "confident"


# ======================================================================================
# Reconstruction — effect signature + pre-grid -> post-grid
# ======================================================================================


def reconstruct(
    pre: list, objects: _Objects, effect: tuple
) -> tuple[list | None, tuple[str, ...]]:
    """Apply an effect signature to a pre-grid. Returns (grid, ()) or (None, reasons).

    The grid is rebuilt as background canvas + painted components, which is exactly the
    decomposition `_Objects` performs, so an empty effect reproduces the pre-grid bit for
    bit (asserted per game as `identity_check`). Every way the signature fails to pin a
    next state is returned as a named reason rather than guessed at.
    """
    by_colour: dict[int, list[tuple]] = defaultdict(list)
    for event in effect:
        by_colour[event[1]].append(event)

    reasons: set[str] = set()
    placements: list[tuple[int, frozenset]] = []
    for colour in set(objects.by_colour) | set(by_colour):
        members = objects.by_colour.get(colour, [])
        events = by_colour.get(colour, [])
        if any(event[0] == "appear" for event in events):
            reasons.add("appear")
        if any(event[0] == "reshape" for event in events):
            reasons.add("reshape")
        consuming = [event for event in events if event[0] in ("move", "disappear")]
        if not consuming:
            placements.extend((colour, member["cells"]) for member in members)
            continue
        if len(consuming) > len(members):
            reasons.add("over_assignment")
            continue
        if len(consuming) < len(members) or len(set(consuming)) != 1:
            # k events, m > k components of that colour (or several distinct events): the
            # signature says WHAT happened, never TO WHICH — the position-free vocabulary's
            # cost, paid here.
            reasons.add("assignment")
            continue
        event = consuming[0]
        if event[0] == "disappear":
            continue
        _, _, drow, dcol = event
        for member in members:
            placements.append(
                (colour, frozenset((r + drow, c + dcol) for r, c in member["cells"]))
            )
    if reasons:
        return None, tuple(sorted(reasons))

    height = len(pre)
    width = len(pre[0]) if height else 0
    grid = [[objects.background] * width for _ in range(height)]
    painted: dict[tuple[int, int], int] = {}
    for colour, cells in placements:
        for row, col in cells:
            if not (0 <= row < height and 0 <= col < width):
                reasons.add("out_of_bounds")
                continue
            if painted.get((row, col), colour) != colour:
                reasons.add("collision")
            painted[(row, col)] = colour
            grid[row][col] = colour
    if reasons:
        return None, tuple(sorted(reasons))
    return grid, ()


# ======================================================================================
# X1 — forward-model self-check
# ======================================================================================


def x1_game(game: str) -> dict[str, Any]:
    loaded = load_store(game)
    transitions: list[Transition] = loaded["transitions"]
    post_missing: set[int] = loaded["post_missing"]
    row: dict[str, Any] = {
        "game": game,
        "store_transitions": len(transitions),
        "store_completions": sum(t.completed for t in transitions),
        "post_frame_missing": len(post_missing),
    }
    if not transitions:
        row["skipped"] = "empty store"
        return row

    rules_by_mode: dict[str, dict[str, Rule]] = {}
    for mode in MODES:
        rules, mining = mine(transitions, mode)
        rules_by_mode[mode] = rules
        classes: Counter = Counter()
        correct: Counter = Counter()
        for transition in transitions:
            rule = _fire(rules, transition)
            cls = confidence(rule)
            classes[cls] += 1
            if rule is not None and rule.effect == abstract(transition.effect, mode):
                correct[cls] += 1
        cell = {
            "rules": len(rules),
            "rule_tiers": dict(Counter(rule.tier for rule in rules.values())),
            "unresolved_keys": len(mining["unresolved_keys"]),
            "coverage": {
                cls: round(classes[cls] / len(transitions), 4)
                for cls in ("confident", "weak", "uncovered")
            },
            "edges": {cls: classes[cls] for cls in ("confident", "weak", "uncovered")},
            "effect_accuracy": {
                cls: (round(correct[cls] / classes[cls], 4) if classes[cls] else None)
                for cls in ("confident", "weak")
            },
        }
        row[mode] = cell

    # ---- reconstruction, mode `full` only: `moveset` drops the movement vectors and cannot
    # produce a next state even in principle, which is itself the reason the planner runs on
    # `full`.
    rules = rules_by_mode["full"]
    recon: dict[str, Counter] = {
        "grammar": Counter(),  # against the RECORDED effect — a property of the vocabulary
        "model": Counter(),  # against the PREDICTED effect — what a planner would get
    }
    # The same counters over STATE-CHANGING edges only (recorded effect non-empty). A no-op
    # edge is trivially reconstructible — the pre-grid is the answer — and equally trivially
    # useless to a planner, which sees a self-loop the closed set discards. Search can only
    # move on state-changing edges, so this subset, not the aggregate, is the plannable number.
    changing: dict[str, Counter] = {"grammar": Counter(), "model": Counter()}
    reasons: dict[str, Counter] = {"grammar": Counter(), "model": Counter()}
    by_class: dict[str, Counter] = defaultdict(Counter)
    identity_ok = identity_n = 0
    for transition in transitions:
        if transition.step in post_missing:
            continue  # `post` is a placeholder here; comparing against it would be a lie
        objects = _Objects(transition.pre)
        if identity_n < 25:  # the canvas-and-paint decomposition must be lossless
            grid, _ = reconstruct(transition.pre, objects, ())
            identity_n += 1
            identity_ok += int(grid == transition.pre)
        rule = _fire(rules, transition)
        cls = confidence(rule)
        moved = bool(transition.effect)
        for source, effect in (
            ("grammar", transition.effect),
            ("model", rule.effect if rule is not None else None),
        ):
            if effect is None:
                recon[source]["no_rule"] += 1
                continue
            recon[source]["considered"] += 1
            if moved:
                changing[source]["considered"] += 1
                changing[source]["predicted_noop"] += int(not effect)
            grid, why = reconstruct(transition.pre, objects, effect)
            if grid is None:
                recon[source]["underdetermined"] += 1
                reasons[source]["|".join(why)] += 1
                if source == "model":
                    by_class[cls]["underdetermined"] += 1
                continue
            recon[source]["determinate"] += 1
            hit = grid == transition.post
            recon[source]["exact"] += hit
            if moved:
                changing[source]["determinate"] += 1
                changing[source]["exact"] += hit
            if source == "model":
                by_class[cls]["determinate"] += 1
                by_class[cls]["exact"] += hit

    out: dict[str, Any] = {}
    for source in ("grammar", "model"):
        counts = recon[source]
        considered = counts["considered"]
        out[source] = {
            "edges_with_post_frame": considered + counts["no_rule"],
            "no_rule": counts["no_rule"],
            "considered": considered,
            "determinate": counts["determinate"],
            "determinate_rate": round(counts["determinate"] / considered, 4)
            if considered
            else None,
            "exact": counts["exact"],
            "exact_over_determinate": round(counts["exact"] / counts["determinate"], 4)
            if counts["determinate"]
            else None,
            "exact_over_considered": round(counts["exact"] / considered, 4)
            if considered
            else None,
            "underdetermined_kinds": dict(reasons[source].most_common()),
            # The same mass counted per KIND rather than per combination: an edge blocked by
            # both `reshape` and `appear` counts once under each, so this names which parts
            # of the vocabulary would have to be repaired, not how they co-occur.
            "underdetermined_kind_edges": dict(
                Counter(
                    {
                        kind: sum(
                            n
                            for combo, n in reasons[source].items()
                            if kind in combo.split("|")
                        )
                        for combo in reasons[source]
                        for kind in combo.split("|")
                    }
                ).most_common()
            ),
            "state_changing": {
                "considered": changing[source]["considered"],
                "determinate": changing[source]["determinate"],
                "determinate_rate": round(
                    changing[source]["determinate"] / changing[source]["considered"], 4
                )
                if changing[source]["considered"]
                else None,
                "exact": changing[source]["exact"],
                "exact_over_considered": round(
                    changing[source]["exact"] / changing[source]["considered"], 4
                )
                if changing[source]["considered"]
                else None,
                # A model that answers "nothing happens" to an edge that did change the board
                # is determinate and useless: the planner sees a self-loop and the state stays
                # unreachable through it. Counted apart from a wrong-but-moving prediction.
                "predicted_noop": changing[source]["predicted_noop"],
            },
        }
    out["model_by_confidence"] = {
        cls: {
            "determinate": by_class[cls]["determinate"],
            "underdetermined": by_class[cls]["underdetermined"],
            "exact": by_class[cls]["exact"],
            "exact_over_determinate": round(
                by_class[cls]["exact"] / by_class[cls]["determinate"], 4
            )
            if by_class[cls]["determinate"]
            else None,
        }
        for cls in ("confident", "weak")
    }
    out["identity_check"] = {"sampled": identity_n, "lossless": identity_ok}
    row["reconstruction"] = out
    return row


# ======================================================================================
# X2 — planner on known ground
# ======================================================================================


def _predict(
    rules: dict[str, Rule], grid: list, objects: _Objects, action: tuple
) -> tuple[Rule | None, str]:
    action_id, click_row, click_col = action
    data = {"y": click_row, "x": click_col} if action_id == 6 else {}
    probe = Transition(
        game="",
        guid="",
        step=0,
        level=1,
        action_id=action_id,
        action_data=data,
        pre=grid,
        post=grid,
        completed=False,
        guards=guard_features(grid, objects, action_id, data),
    )
    rule = _fire(rules, probe)
    return rule, confidence(rule)


def _search(
    rules: dict[str, Rule],
    origin: str,
    origin_grid: list,
    goal: str,
    actions: list[tuple],
    allow_weak: bool,
    node_cap: int,
    time_cap: float,
) -> dict[str, Any]:
    """Breadth-first over predicted states. Cost is one action per edge and every edge costs
    the same, so BFS is optimal here and iterative deepening would only re-expand; the design
    note's IDA* buys nothing without an admissible heuristic, and no heuristic exists that
    was not invented for this run."""
    start = time.monotonic()
    parent: dict[str, tuple[str, tuple, str] | None] = {origin: None}
    grids: dict[str, list] = {origin: origin_grid}
    queue: deque[str] = deque([origin])
    depth: dict[str, int] = {origin: 0}
    expanded = 0
    edges_by_class: Counter = Counter()
    hit_cap: str | None = None

    while queue:
        if expanded >= node_cap:
            hit_cap = "nodes"
            break
        if time.monotonic() - start > time_cap:
            hit_cap = "time"
            break
        digest = queue.popleft()
        expanded += 1
        grid = grids[digest]
        objects = _Objects(grid)
        for action in actions:
            rule, cls = _predict(rules, grid, objects, action)
            if cls == "uncovered" or (cls == "weak" and not allow_weak):
                continue
            post, _ = reconstruct(grid, objects, rule.effect)
            if post is None:
                continue  # not plannable: the model cannot name the next state
            target = _hash(1, post)
            if target == digest or target in parent:
                continue
            edges_by_class[cls] += 1
            parent[target] = (digest, action, cls)
            grids[target] = post
            depth[target] = depth[digest] + 1
            if target == goal:
                queue.clear()
                break
            queue.append(target)
        if goal in parent:
            break

    found = goal in parent
    path: list[dict[str, Any]] = []
    if found:
        node = goal
        while parent[node] is not None:
            source, action, cls = parent[node]
            path.append({"pre": source, "action": list(action), "class": cls, "post": node})
            node = source
        path.reverse()
    return {
        "found": found,
        "path": path,
        "nodes_expanded": expanded,
        "states_seen": len(parent),
        "max_depth_reached": max(depth.values()) if depth else 0,
        "edges_by_class": dict(edges_by_class),
        "hit_cap": hit_cap,
        "seconds": round(time.monotonic() - start, 2),
        "closed_set": set(parent),
    }


def _store_path(graph: dict, origin: str, goal: str) -> list[dict[str, Any]] | None:
    """Shortest path using RECORDED transitions only — replay-verified by construction."""
    adjacency: dict[str, list[tuple[tuple, str]]] = defaultdict(list)
    for source, action, target in graph["edges"]:
        adjacency[source].append((tuple(action), target))
    parent: dict[str, tuple[str, tuple] | None] = {origin: None}
    queue = deque([origin])
    while queue:
        node = queue.popleft()
        if node == goal:
            break
        for action, target in adjacency[node]:
            if target not in parent:
                parent[target] = (node, action)
                queue.append(target)
    if goal not in parent:
        return None
    path: list[dict[str, Any]] = []
    node = goal
    while parent[node] is not None:
        source, action = parent[node]
        path.append({"pre": source, "action": list(action), "post": node})
        node = source
    path.reverse()
    return path


def _baseline_l1(game: str) -> int | None:
    for path in sorted(METADATA.glob(f"{game}/*/metadata.json")):
        actions = json.loads(path.read_text()).get("baseline_actions") or []
        if actions:
            return int(actions[0])
    return None


def x2_game(game: str, node_cap: int = NODE_CAP, time_cap: float = TIME_CAP) -> dict[str, Any]:
    loaded = load_store(game)
    transitions: list[Transition] = loaded["transitions"]
    rows: list[dict[str, Any]] = loaded["rows"]
    states = loaded["states"]
    graph = loaded["graph"]

    completions = [row for row in rows if row["completed"]]
    if len(completions) != 1:
        return {"game": game, "skipped": f"{len(completions)} completion rows, expected 1"}
    completion = completions[0]
    goal = completion["pre"]
    origin = graph["origin"]
    if goal not in states or origin not in states:
        return {"game": game, "skipped": "origin or completion pre-state absent from store"}

    rules, _ = mine(transitions, "full")
    # (w) The action repertoire is the store's own: every distinct action the explorer
    # actually issued on this game, RESET excluded (a plan never resets). Enumerating all
    # 64x64 clicks would invent an action space the evidence never touched.
    actions = sorted({tuple(row["action"]) for row in rows if row["action"][0] != 0})
    store_edges = {(source, tuple(action)) for source, action, _ in graph["edges"]}

    audit = json.loads(AUDIT.read_text())["games"].get(game, {})
    flagged = {item["state"] for item in audit.get("shallowest_failures", [])}

    result: dict[str, Any] = {
        "game": game,
        "origin": origin,
        "goal_pre_state": goal,
        "goal_action": completion["action"],
        "explorer_actions_to_completion": completion["step"],
        "human_baseline_l1": _baseline_l1(game),
        "store_states": len(states),
        "action_repertoire": len(actions),
        "prefix_verified_rate": audit.get("verified_rate"),
    }

    # Why the search does or does not move, at the one state every plan starts from. Without
    # this a "no plan" reading is unattributable: an exhausted search and a search with no
    # legal first move are the same line of output otherwise.
    origin_objects = _Objects(states[origin])
    census: Counter = Counter()
    for action in actions:
        rule, cls = _predict(rules, states[origin], origin_objects, action)
        if rule is None:
            census[("uncovered", "no_rule")] += 1
            continue
        post, why = reconstruct(states[origin], origin_objects, rule.effect)
        if post is None:
            census[(cls, "underdetermined")] += 1
        elif _hash(1, post) == origin:
            census[(cls, "self_loop")] += 1
        else:
            census[(cls, "successor")] += 1
    result["origin_forward_step_census"] = {
        f"{cls}/{outcome}": n for (cls, outcome), n in sorted(census.items())
    }

    store_only = _store_path(graph, origin, goal)
    result["store_only_plan"] = (
        {"actions": len(store_only) + 1, "path_edges": len(store_only)}
        if store_only is not None
        else None
    )

    searches: dict[str, Any] = {}
    plan: dict[str, Any] | None = None
    for level, allow_weak in (("confident_only", False), ("confident_plus_weak", True)):
        found = _search(
            rules, origin, states[origin], goal, actions, allow_weak, node_cap, time_cap
        )
        closed = found.pop("closed_set")
        path = found.pop("path")
        found["closed_set_touched_flagged_states"] = sorted(closed & flagged)
        found["closed_set_states_not_in_store"] = len(closed - set(states))
        searches[level] = found
        if found["found"] and plan is None:
            recorded = sum(
                1 for edge in path if (edge["pre"], tuple(edge["action"])) in store_edges
            )
            plan = {
                "relaxation": level,
                "actions": len(path) + 1,  # + the recorded completion action
                "path_edges": len(path),
                "edges_store_recorded": recorded,
                "edges_model_novel": len(path) - recorded,
                "edge_classes": dict(Counter(edge["class"] for edge in path)),
                "states_not_in_store": sum(1 for edge in path if edge["post"] not in states),
                "path": path,
            }
            break
    result["searches"] = searches
    result["plan"] = plan
    if plan is not None:
        baseline = result["human_baseline_l1"]
        result["comparison"] = {
            "plan_actions": plan["actions"],
            "explorer_actions": completion["step"],
            "human_baseline_l1": baseline,
            "vs_explorer": round(plan["actions"] / completion["step"], 4),
            "vs_human": round(plan["actions"] / baseline, 4) if baseline else None,
        }
    return result


# ======================================================================================
# Runner
# ======================================================================================


def _games() -> list[str]:
    return sorted({path.name.split(".")[0] for path in STORE.glob("*.transitions.jsonl")})


def _job_x1(game: str) -> dict[str, Any]:
    try:
        return x1_game(game)
    except Exception as error:  # a failing game is reported, never silently dropped
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


def _job_x2(game: str, node_cap: int, time_cap: float) -> dict[str, Any]:
    try:
        return x2_game(game, node_cap, time_cap)
    except Exception as error:
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("x1", "x2"), required=True)
    parser.add_argument("--games", nargs="*")
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--vocab", choices=("v1", "v2"), default="v2")
    parser.add_argument("--node-cap", type=int, default=NODE_CAP)
    parser.add_argument("--time-cap", type=float, default=TIME_CAP)
    args = parser.parse_args()

    set_vocab(args.vocab)  # before the pool: workers spawn and inherit the environment
    games = args.games or (_games() if args.stage == "x1" else list(COHORT))
    out = args.out or ROOT / f"logs/e3_{args.stage}.json"

    results: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        if args.stage == "x1":
            futures = {pool.submit(_job_x1, game): game for game in games}
        else:
            futures = {
                pool.submit(_job_x2, game, args.node_cap, args.time_cap): game
                for game in games
            }
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results.append(row)
            print(_line(args.stage, row), flush=True)
    results.sort(key=lambda row: games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "stage": args.stage,
        "store": str(STORE.relative_to(ROOT)),
        "guard_vocabulary": vocab(),
        "effect_mode": "full",
        "caps": {"nodes": args.node_cap, "seconds": args.time_cap}
        if args.stage == "x2"
        else None,
        "games": {row["game"]: row for row in results},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {out}")
    return 0


def _line(stage: str, row: dict[str, Any]) -> str:
    if "error" in row:
        return f"{row['game']:5s} ERROR {row['error']}"
    if "skipped" in row:
        return f"{row['game']:5s} skipped: {row['skipped']}"
    if stage == "x1":
        full = row["full"]
        recon = row["reconstruction"]
        return (
            f"{row['game']:5s} n={row['store_transitions']:5d} "
            f"conf={full['coverage']['confident']:.3f} "
            f"weak={full['coverage']['weak']:.3f} "
            f"unc={full['coverage']['uncovered']:.3f} "
            f"weakacc={full['effect_accuracy']['weak']} | "
            f"recon det={recon['model']['determinate_rate']} "
            f"exact/det={recon['model']['exact_over_determinate']} "
            f"exact/all={recon['model']['exact_over_considered']}"
        )
    plan = row.get("plan")
    searches = row.get("searches", {})
    tail = " ".join(
        f"{level}:{'FOUND' if cell['found'] else 'no'}"
        f"({cell['nodes_expanded']}n,{cell['seconds']}s,cap={cell['hit_cap']})"
        for level, cell in searches.items()
    )
    head = (
        f"plan={plan['actions']} ({plan['relaxation']}, "
        f"novel={plan['edges_model_novel']}/{plan['path_edges']})"
        if plan
        else "plan=NONE"
    )
    store_only = row.get("store_only_plan")
    return (
        f"{row['game']:5s} {head} store_only="
        f"{store_only['actions'] if store_only else 'none'} "
        f"explorer={row['explorer_actions_to_completion']} "
        f"human={row['human_baseline_l1']} | {tail}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
