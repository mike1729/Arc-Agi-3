#!/usr/bin/env python3
"""Route-2 semantic domains: reachability closure and extensional equivalence.

Governing note SS3.2 route 2 demands "an exact proof over a declared exhaustive finite
semantic domain" and explicitly rules out bounded fork suites. The one mechanical object
with that status is the game's own reachable transition graph: breadth-first search from
the authored start state through the game's full effective action alphabet until the
frontier is empty. On a CLOSED graph, a candidate that is two-valued and equal to the
engine's completion label on EVERY reachable transition is extensionally identical to
the authored rule over the rule's entire semantic domain — the advance check never sees
any other state. If the frozen budget is exhausted first, closure fails and no route-2
proof exists for that game; that result is recorded, never approximated.

State identity (soundness-critical — a wrong exclusion would merge distinct states and
forge closure):

  * canonical recursive encoding of the live game object: primitives; enums by value;
    numpy arrays by shape/dtype/bytes; lists and tuples in order; dicts sorted by key;
    sets by sorted element encodings; objects by sorted ``vars()``; cycles marked at
    back-references.
  * ``_action`` is excluded: ``base_game.perform_action`` calls ``_set_action`` before
    any game logic runs, so the previous value is dead state with no future effect.
  * ``_action_count`` is quotiented to the engine's only dynamics read, the
    ``handle_reset`` zero test (full vs level reset) — except for m0r0, whose source
    reads the raw count (renders it and enforces a 150-action limit), so m0r0 keys on
    the raw value. Verified by grep: no other iteration game mentions action_count.

Effective alphabet (per-game declaration, cited to the source dispatch):

  * ``perform_action`` never checks ``available_actions``; every id runs the step loop,
    except that non-RESET actions in WIN/GAME_OVER return empty frames without stepping
    (true no-ops — excluded from the domain because the advance check never runs).
  * Ids the game's dispatch never reads are uniform "pass turns": ambient dynamics
    advance identically regardless of id or coordinates (data reads occur only inside
    ACTION6 guards; grep-verified per game). The alphabet therefore contains every
    HANDLED id (ACTION6 expanded to all 64x64 coordinates — sampling clicks would turn
    the proof back into a bounded suite) plus ONE pass representative where unhandled
    ids exist. Every 512th expanded state, a second unhandled id is executed and its
    canonical post-key asserted equal to the representative's — a standing spot check
    of the declared uniformity.

Artifacts: the full domain graph is written locally to ``logs/es_domain_{env}.json.gz``
(too large for git; digest pinned in the committed summary), and closure plus
equivalence results merge into ``logs/es_domain_closure.json``.

Run:
  .venv/bin/python agent/harness/es_sources/domain_closure.py --run --env tu93
  .venv/bin/python agent/harness/es_sources/domain_closure.py --equivalence --env tu93
"""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import os
import sys
import time
from collections import OrderedDict, deque
from enum import Enum
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parents[1]
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import numpy as np  # noqa: E402

from arcengine import ActionInput, GameAction  # noqa: E402

from es_candidates import (  # noqa: E402
    FALSE,
    TRUE,
    _Objects,
    enumerate_universe,
    evaluate,
    serialize,
)
from es_questions import canonical_payload  # noqa: E402
from gi2_forks import decode_grid, encode_grid  # noqa: E402
from gi2_replay import ReplayDriver, _plain_frames  # noqa: E402
from gi2_traces import ROOT, iter_trace, CORPUS  # noqa: E402

INVENTORY = ROOT / "logs/es_inventory.json"
SUMMARY_OUTPUT = ROOT / "logs/es_domain_closure.json"

FORMAT_VERSION = 1
GRID_SIZE = 64

# Frozen closure budgets: exceeding either fails closure for that game.
MAX_EDGES = 1_200_000
MAX_FRONTIER = 20_000
PASS_CHECK_STRIDE = 512

# Per-game effective alphabets, cited to the source dispatch sites (grep-verified
# 2026-08-03; sources pinned by sha256 in the ES gold artifacts).
ALPHABETS: dict[str, dict[str, Any]] = {
    "dc22": {
        "handled_keys": [1, 2, 3, 4, 5],
        "handles_click": True,
        "pass_ids": [],
        "citation": "dc22.py:10543,10627-10641 — dispatch reads RESET, ACTION1-5, ACTION6",
    },
    "ft09": {
        "handled_keys": [],
        "handles_click": True,
        "pass_ids": [1, 2, 3, 4, 5],
        "citation": "ft09.py:2329,2347 — dispatch reads only RESET and ACTION6",
    },
    "ls20": {
        "handled_keys": [1, 2, 3, 4],
        "handles_click": False,
        "pass_ids": [5, 6],
        "citation": "ls20.py:1921-1930 — dispatch reads ACTION1-4; no action-data reads",
    },
    "m0r0": {
        "handled_keys": [1, 2, 3, 4],
        "handles_click": True,
        "pass_ids": [5],
        "citation": "m0r0.py:714-716,756-765 — dispatch reads ACTION1-4 and ACTION6",
    },
    "tu93": {
        "handled_keys": [1, 2, 3, 4],
        "handles_click": False,
        "pass_ids": [5, 6],
        "citation": "tu93.py:1180-1216 — dispatch reads ACTION1-4; no action-data reads",
    },
    "vc33": {
        "handled_keys": [],
        "handles_click": True,
        "pass_ids": [1, 2, 3, 4, 5],
        "citation": "vc33.py:2085-2088 — dispatch reads only ACTION6",
    },
}

ACTION_COUNT_KEY_MODE = {env: "zero_flag" for env in ALPHABETS} | {"m0r0": "raw"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ====================================================================================
# Canonical state identity
# ====================================================================================

# Excluded at EVERY level of the object graph, not only the top: games hold interface
# objects with back-references to the game, and a top-level-only exclusion would leak
# the excluded fields back into the encoding through that path (caught by test).
# ``_action_count`` is excluded here and re-appended as the per-mode quotient tag.
_EXCLUDED_FIELDS = {"_action", "_action_count"}


def _encode_value(obj: Any, seen: frozenset[int]) -> bytes:
    if id(obj) in seen:
        return b"CYCLE"
    if obj is None:
        return b"N"
    if isinstance(obj, bool):
        return b"B" + bytes([obj])
    if isinstance(obj, int):
        return b"I" + str(obj).encode()
    if isinstance(obj, float):
        return b"F" + repr(obj).encode()
    if isinstance(obj, str):
        return b"S" + obj.encode()
    if isinstance(obj, bytes):
        return b"Y" + obj
    if isinstance(obj, Enum):
        return b"E" + type(obj).__name__.encode() + b":" + str(obj.value).encode()
    if isinstance(obj, np.ndarray):
        return b"A" + str(obj.shape).encode() + str(obj.dtype).encode() + obj.tobytes()
    inner = seen | {id(obj)}
    if isinstance(obj, (list, tuple)):
        return b"L[" + b",".join(_encode_value(item, inner) for item in obj) + b"]"
    if isinstance(obj, dict):
        items = sorted(obj.items(), key=lambda kv: repr(kv[0]))
        return (
            b"D{"
            + b",".join(
                _encode_value(k, inner) + b":" + _encode_value(v, inner) for k, v in items
            )
            + b"}"
        )
    if isinstance(obj, (set, frozenset)):
        return b"Z{" + b",".join(sorted(_encode_value(item, inner) for item in obj)) + b"}"
    if hasattr(obj, "__dict__"):
        items = sorted(vars(obj).items())
        return (
            b"O<"
            + type(obj).__name__.encode()
            + b">"
            + b",".join(
                key.encode() + b"=" + _encode_value(value, inner)
                for key, value in items
                if key not in _EXCLUDED_FIELDS
            )
        )
    raise TypeError(f"state encoding met an unsupported type: {type(obj)!r}")


def canonical_state_key(game: Any, count_mode: str) -> str:
    body = _encode_value(
        {
            key: value
            for key, value in vars(game).items()
            if key not in _EXCLUDED_FIELDS
        },
        frozenset(),
    )
    count = int(game._action_count)
    if count_mode == "raw":
        tag = b"count=" + str(count).encode()
    else:
        tag = b"count0" if count == 0 else b"count+"
    return _sha256(body + tag)


# ====================================================================================
# Closure BFS
# ====================================================================================


def _alphabet_actions(env: str) -> list[tuple[int, dict[str, int] | None]]:
    """Deterministic effective alphabet; ACTION6 expands to all 64x64 coordinates."""
    declaration = ALPHABETS[env]
    actions: list[tuple[int, dict[str, int] | None]] = [(0, None)]
    actions.extend((key, None) for key in declaration["handled_keys"])
    if declaration["pass_ids"]:
        actions.append((declaration["pass_ids"][0], None))
    if declaration["handles_click"]:
        actions.extend(
            (6, {"x": x, "y": y}) for y in range(GRID_SIZE) for x in range(GRID_SIZE)
        )
    return actions


def _perform(game: Any, action_id: int, data: dict[str, int] | None) -> Any:
    return game.perform_action(
        ActionInput(id=GameAction.from_id(action_id), data=dict(data or {})), raw=True
    )


def close_domain(env: str, max_edges: int = MAX_EDGES) -> dict[str, Any]:
    count_mode = ACTION_COUNT_KEY_MODE[env]
    declaration = ALPHABETS[env]
    alphabet = _alphabet_actions(env)
    pass_ids = declaration["pass_ids"]

    driver = ReplayDriver(env)
    game = driver.new_game()
    response = _perform(game, 0, None)
    root_frames = _plain_frames(response.frame or [])
    if not root_frames:
        raise ValueError(f"{env}: initial RESET returned no frames")
    grid_shape = [len(root_frames[-1]), len(root_frames[-1][0])]

    states: list[dict[str, Any]] = []
    key_to_id: dict[str, int] = {}
    edges: list[list[Any]] = []

    def _register(key: str, grid: list, levels: int, state_name: str) -> tuple[int, bool]:
        existing = key_to_id.get(key)
        if existing is not None:
            return existing, False
        state_id = len(states)
        key_to_id[key] = state_id
        states.append(
            {
                "key": key,
                "grid_rle": encode_grid(grid),
                "levels": levels,
                "state": state_name,
            }
        )
        return state_id, True

    def _state_name(raw_state: Any) -> str:
        return str(getattr(raw_state, "value", raw_state))

    root_key = canonical_state_key(game, count_mode)
    root_levels = int(response.levels_completed or 0)
    root_id, _ = _register(root_key, root_frames[-1], root_levels, _state_name(game._state))

    queue: deque[tuple[int, Any]] = deque([(root_id, game)])
    edge_count = 0
    pass_checks = pass_failures = 0
    expanded = 0
    start = time.perf_counter()
    budget_hit: str | None = None

    while queue:
        if edge_count >= max_edges:
            budget_hit = "max_edges"
            break
        if len(queue) > MAX_FRONTIER:
            budget_hit = "max_frontier"
            break
        state_id, live = queue.popleft()
        expanded += 1
        parent_levels = states[state_id]["levels"]
        terminal = states[state_id]["state"] in ("WIN", "GAME_OVER")
        actions = [(0, None)] if terminal else alphabet
        pass_reference_key: str | None = None
        for action_id, data in actions:
            branch = copy.deepcopy(live)
            branch_response = _perform(branch, action_id, data)
            edge_count += 1
            frames = _plain_frames(branch_response.frame or [])
            branch_levels = int(branch_response.levels_completed or 0)
            completed = branch_levels > parent_levels
            branch_state = _state_name(branch._state)
            settled = (
                frames[-1]
                if frames
                else decode_grid(
                    states[state_id]["grid_rle"],
                    width=grid_shape[1],
                    height=grid_shape[0],
                )
            )
            branch_key = canonical_state_key(branch, count_mode)
            branch_id, novel = _register(branch_key, settled, branch_levels, branch_state)
            eval_rle = None
            if completed and frames:
                eval_grid = (
                    frames[-1]
                    if branch_state == "WIN" or len(frames) < 2
                    else frames[-2]
                )
                eval_rle = encode_grid(eval_grid)
            edges.append(
                [
                    state_id,
                    action_id,
                    data,
                    branch_id,
                    "complete" if completed else "non_complete",
                    eval_rle,
                ]
            )
            if novel and branch_state not in ("WIN", "GAME_OVER"):
                queue.append((branch_id, branch))
            if not terminal and pass_ids and action_id == pass_ids[0]:
                pass_reference_key = branch_key
        if (
            pass_reference_key is not None
            and len(pass_ids) > 1
            and expanded % PASS_CHECK_STRIDE == 0
        ):
            checker = copy.deepcopy(live)
            check_id = pass_ids[1]
            check_data = {"x": 13, "y": 27} if check_id == 6 else None
            _perform(checker, check_id, check_data)
            pass_checks += 1
            if canonical_state_key(checker, count_mode) != pass_reference_key:
                pass_failures += 1

    closed = budget_hit is None and not queue
    if pass_failures:
        raise ValueError(
            f"{env}: declared pass-turn uniformity FAILED {pass_failures}/{pass_checks} "
            "spot checks — the alphabet declaration is wrong; closure aborted"
        )

    return {
        "format_version": FORMAT_VERSION,
        "env": env,
        "grid_shape": grid_shape,
        "alphabet": {
            **declaration,
            "actions_per_state": len(alphabet),
            "action_count_key_mode": count_mode,
        },
        "budgets": {"max_edges": max_edges, "max_frontier": MAX_FRONTIER},
        "closure": {
            "achieved": closed,
            "budget_hit": budget_hit,
            "states": len(states),
            "edges": len(edges),
            "expanded": expanded,
            "frontier_remaining": len(queue),
            "completion_edges": sum(1 for edge in edges if edge[4] == "complete"),
            "terminal_states": sum(
                1 for state in states if state["state"] in ("WIN", "GAME_OVER")
            ),
            "levels_reached": max(state["levels"] for state in states),
            "pass_uniformity_checks": pass_checks,
            "wall_seconds": round(time.perf_counter() - start, 1),
        },
        "states": states,
        "edges": edges,
    }


def domain_path(env: str) -> Path:
    return ROOT / f"logs/es_domain_{env}.json.gz"


def write_domain(document: dict[str, Any]) -> str:
    path = domain_path(document["env"])
    payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    with gzip.open(path, "wb", compresslevel=6) as handle:
        handle.write(payload)
    return _sha256(payload)


def read_domain(env: str) -> tuple[dict[str, Any], str]:
    with gzip.open(domain_path(env), "rb") as handle:
        payload = handle.read()
    return json.loads(payload), _sha256(payload)


# ====================================================================================
# Extensional equivalence over a closed domain
# ====================================================================================


class _ObjectsCache:
    def __init__(
        self,
        states: list[dict[str, Any]],
        grid_shape: tuple[int, int] = (GRID_SIZE, GRID_SIZE),
        cap: int = 60_000,
    ):
        self.states = states
        self.grid_shape = grid_shape
        self.cap = cap
        self.cache: OrderedDict[int, _Objects] = OrderedDict()

    def decode(self, payload: str) -> list:
        return decode_grid(payload, width=self.grid_shape[1], height=self.grid_shape[0])

    def get(self, state_id: int) -> _Objects:
        hit = self.cache.get(state_id)
        if hit is not None:
            self.cache.move_to_end(state_id)
            return hit
        objects = _Objects(self.decode(self.states[state_id]["grid_rle"]))
        self.cache[state_id] = objects
        if len(self.cache) > self.cap:
            self.cache.popitem(last=False)
        return objects


def candidate_verdict(
    candidate: dict[str, Any],
    domain: dict[str, Any],
    cache: _ObjectsCache,
    eval_objects: dict[int, _Objects],
) -> dict[str, Any]:
    """Two-valued agreement with the engine label on EVERY reachable transition."""
    for index, (pre_id, _aid, _data, post_id, label, eval_rle) in enumerate(
        domain["edges"]
    ):
        pre_objects = cache.get(pre_id)
        if eval_rle is not None:
            objects = eval_objects.get(index)
            if objects is None:
                objects = _Objects(cache.decode(eval_rle))
                eval_objects[index] = objects
        else:
            objects = cache.get(post_id)
        value = evaluate(candidate, {"objects": objects, "pre_objects": pre_objects})
        expected = TRUE if label == "complete" else FALSE
        if value != expected:
            return {
                "equivalent": False,
                "edges_checked": index + 1,
                "first_disagreement": {
                    "edge_index": index,
                    "label": label,
                    "value": value,
                },
            }
    return {"equivalent": True, "edges_checked": len(domain["edges"])}


def equivalence_pass(env: str) -> dict[str, Any]:
    domain, domain_digest = read_domain(env)
    if domain["env"] != env:
        raise ValueError(f"domain artifact env {domain['env']} != {env}")
    if not domain["closure"]["achieved"]:
        return {
            "env": env,
            "domain_digest": domain_digest,
            "closure_achieved": False,
            "note": "no route-2 proof exists without closure; equivalence not computed",
            "cases": _cases_without_proof(env),
        }

    inventory = json.loads(INVENTORY.read_text())
    cases = [case for case in inventory["cases"] if case["env"] == env]
    grids_by_session: dict[str, dict[int, list]] = {}
    for case in cases:
        guid = case["guid"]
        if guid not in grids_by_session:
            wanted = {
                c["query"]["pre_state_row"] for c in cases if c["guid"] == guid
            }
            found: dict[int, list] = {}
            for step in iter_trace(CORPUS / env / f"{guid}.recording.jsonl"):
                if step.index in wanted and step.frames:
                    found[step.index] = step.frames[-1].grid
            grids_by_session[guid] = found

    distinct: dict[str, dict[str, Any]] = {}
    per_case: list[dict[str, Any]] = []
    for case in cases:
        generated = enumerate_universe(
            grids_by_session[case["guid"]][case["query"]["pre_state_row"]]
        )
        serials = [serialize(candidate) for candidate in generated["universe"]]
        for serial, candidate in zip(serials, generated["universe"]):
            distinct.setdefault(serial, candidate)
        per_case.append(
            {
                "case_id": case["case_id"],
                "role": case["role"],
                "universe_hash": generated["universe_hash"],
                "tractable": generated["tractable"],
                "serials": serials,
            }
        )

    cache = _ObjectsCache(domain["states"], tuple(domain["grid_shape"]))
    eval_objects: dict[int, _Objects] = {}
    verdicts: dict[str, dict[str, Any]] = {}
    for serial in sorted(distinct):
        verdicts[serial] = candidate_verdict(
            distinct[serial], domain, cache, eval_objects
        )

    equivalent_serials = sorted(
        serial for serial, verdict in verdicts.items() if verdict["equivalent"]
    )
    case_rows = []
    for row in per_case:
        e_indices = [
            index
            for index, serial in enumerate(row["serials"])
            if serial in set(equivalent_serials)
        ]
        case_rows.append(
            {
                "case_id": row["case_id"],
                "role": row["role"],
                "universe_hash": row["universe_hash"],
                "tractable": row["tractable"],
                "E_size_route2": len(e_indices),
                "E_indices_route2": e_indices,
                "covered_route2": bool(e_indices),
            }
        )

    return {
        "env": env,
        "domain_digest": domain_digest,
        "closure_achieved": True,
        "closure": domain["closure"],
        "alphabet": domain["alphabet"],
        "distinct_candidates": len(distinct),
        "equivalent_candidates": [
            {"serial": serial, "edges_checked": verdicts[serial]["edges_checked"]}
            for serial in equivalent_serials
        ],
        "cases": case_rows,
    }


def _cases_without_proof(env: str) -> list[dict[str, Any]]:
    inventory = json.loads(INVENTORY.read_text())
    return [
        {
            "case_id": case["case_id"],
            "role": case["role"],
            "E_size_route2": 0,
            "E_indices_route2": [],
            "covered_route2": False,
        }
        for case in inventory["cases"]
        if case["env"] == env
    ]


# ====================================================================================
# Summary artifact
# ====================================================================================


def merge_summary(entry: dict[str, Any]) -> dict[str, Any]:
    if SUMMARY_OUTPUT.exists():
        summary = json.loads(SUMMARY_OUTPUT.read_text())
        summary = canonical_payload(summary)
    else:
        summary = {
            "format_version": FORMAT_VERSION,
            "generated_by": "agent/harness/es_sources/domain_closure.py",
            "inputs": {},
            "games": {},
        }
    summary["inputs"]["logs/es_inventory.json"] = json.loads(
        INVENTORY.read_text()
    )["fingerprint"]
    entry = dict(entry)
    entry.pop("states", None)
    entry.pop("edges", None)
    summary["games"][entry["env"]] = entry
    payload = json.dumps(canonical_payload(summary), sort_keys=True, separators=(",", ":"))
    summary["fingerprint"] = _sha256(payload.encode())
    SUMMARY_OUTPUT.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="close the domain, then equivalence")
    parser.add_argument("--close", action="store_true", help="closure BFS only")
    parser.add_argument("--equivalence", action="store_true", help="equivalence over an existing domain")
    parser.add_argument("--env", required=True, choices=sorted(ALPHABETS))
    parser.add_argument("--max-edges", type=int, default=MAX_EDGES)
    args = parser.parse_args()

    if args.run or args.close:
        document = close_domain(args.env, max_edges=args.max_edges)
        digest = write_domain(document)
        closure = document["closure"]
        print(
            f"{args.env}: closed={closure['achieved']} states={closure['states']} "
            f"edges={closure['edges']} completions={closure['completion_edges']} "
            f"levels={closure['levels_reached']} budget_hit={closure['budget_hit']} "
            f"({closure['wall_seconds']}s); domain digest {digest[:16]}..."
        )
    if args.run or args.equivalence:
        entry = equivalence_pass(args.env)
        merge_summary(entry)
        if entry["closure_achieved"]:
            covered = sum(1 for row in entry["cases"] if row["covered_route2"])
            print(
                f"{args.env}: distinct candidates {entry['distinct_candidates']}, "
                f"equivalent {len(entry['equivalent_candidates'])}, route-2 covered "
                f"cases {covered}/{len(entry['cases'])}"
            )
            for eq in entry["equivalent_candidates"]:
                print(f"  equivalent: {eq['serial']}")
        else:
            print(f"{args.env}: closure not achieved — no route-2 proof; recorded")
        print(f"updated {SUMMARY_OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
