"""Frozen goal-inference sentinels (slice-4 protocol revision 4).

Readability microtasks alone do not establish construct validity: before any
real-game cell, synthetic mini-games — using the actual carrier primitives and
the pilot's exact answer schema — must show that the instrument CAN carry a
causal, history-sensitive goal to a capable reader.  The sentinels contain no
public game assets, names, source, or human histories.

The generated family ("charge-order") has a conjunctive causal objective with a
history-sensitive condition:

    the mover must arrive at zone B while CHARGED; entering zone A charges it,
    entering zone D discharges it, and charge is invisible on the board — so
    two episodes can end with the SAME final board, different ordered
    histories, and different outcomes.

Passive controls: three counterbalanced variants (palette, action labels,
locations, page order, chronology position, and nonces permuted; latent logic
preserved), each containing multiple genuine successes, one near-miss per
required constraint, at least one same-final-board/different-history pair,
unused actions, and salient causally-inert distractors.  Run through T, V and O
under the production sampler, one answer call per variant: each arm must infer
the complete objective in at least 2/3 variants, with no constraint credited
from a partial or merely correlated description (adjudicated worksheets; the
aggregation is mechanical).

Active controls: three counterbalanced P variants whose initial evidence is
deliberately consistent with two plausible goals; exactly one legal probe
discriminates.  The pre-probe answer must preserve the ambiguity and request a
discriminating observation (mechanically checkable), and the post-probe answer
must revise to the correct complete goal.  P passes with 2/3 final goals AND
2/3 valid discriminating interactions; a lucky pre-probe guess does not pass
the interaction criterion.

Leakage controls: a committed generator seed and generator hash define every
fixture before model use; model-visible IDs are nonces; fixture/gold maps are
sealed separately; sentinel outputs never enter a real-game prompt; a
source-blind independent reviewer must attest evidence adequacy (the pinned
same-model comparator is NOT an acceptable reviewer).  Any sentinel failure
ends the frozen protocol version — a redesign is a new version, never a rerun.

This module performs no model generation unless invoked with --run.
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

import s4_delta as sd  # noqa: E402
import s4_ledgers as sl  # noqa: E402
import s4_render as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_VERSION = "r4"
FORMAT_VERSION = 1
SEALED_R4 = ROOT / "logs/s4_sealed" / PROTOCOL_VERSION
SENTINEL_ASSETS = SEALED_R4 / "fixtures/sentinels/assets"     # model-visible
SENTINEL_GOLD = SEALED_R4 / "fixtures/sentinels/gold"         # sealed separately
DEV_ROOT = ROOT / "logs/s4_sentinel_dev"

PASSIVE_VARIANTS = 3
ACTIVE_VARIANTS = 3
PASSIVE_ARMS = ("T", "V", "O")
PASS_THRESHOLD = 2          # of 3 variants, per arm / per criterion
TOTAL_GENERATIONS = PASSIVE_VARIANTS * len(PASSIVE_ARMS) + ACTIVE_VARIANTS * 2  # 15

RESULT_FORMAT_VERSION = 3
ACTIVE_ARM = "P"
ACTIVE_STAGES = ("pre", "post")
CONFIRM_RAW_RESULTS = SEALED_R4 / "sentinel_raw_results.json"
CONFIRM_RESULTS = SEALED_R4 / "sentinel_results.json"
CONFIRM_RUN_DIR = SEALED_R4 / "sentinel_run"

GRID = 24                   # sentinel boards are 24x24: small, fully legible
MOVE = 3                    # mover step (its own size), like the pilot games


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_sha256(value: Any) -> str:
    return sd.canonical_sha256(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _parse_utc(value: Any, label: str) -> _dt.datetime:
    require(isinstance(value, str) and value.strip(), f"{label} must be a UTC timestamp")
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{label} is not ISO-8601: {value!r}") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == _dt.timedelta(0),
            f"{label} must include an explicit UTC offset")
    return parsed


def _atomic_create_json(path: Path, value: Any, *, read_only: bool = False) -> None:
    """Create a JSON artifact exactly once; never replace an existing record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=1, sort_keys=True, default=str) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(f"append-only artifact already exists: {path}") from exc
    if read_only:
        path.chmod(0o444)


def _action_schema(action_label: str) -> dict[str, Any]:
    """Map the synthetic A1..A5 labels into the pilot's exact action schema."""
    match = re.fullmatch(r"A([1-5])", action_label)
    require(match is not None, f"invalid synthetic action label {action_label!r}")
    return {"id": int(match.group(1)) - 1, "click": None}


def sentinel_call_seed(namespace: str, variant_id: str, carrier: str,
                       stage: str, base_seed: int) -> int:
    require(carrier in set(PASSIVE_ARMS) | {ACTIVE_ARM},
            f"invalid sentinel carrier {carrier!r}")
    require(stage in {"single", *ACTIVE_STAGES}, f"invalid sentinel stage {stage!r}")
    digest = hashlib.sha256(
        f"{PROTOCOL_VERSION}:sentinel-call:{namespace}:{variant_id}:"
        f"{carrier}:{stage}:{base_seed}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _nonce(seed_text: str, prefix: str, length: int = 6) -> str:
    return prefix + hashlib.sha256(seed_text.encode()).hexdigest()[:length]


def _state_nonce(seed_text: str) -> str:
    """Opaque Sxxxxx identifier compatible with the pilot next_probe contract."""
    value = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    return f"S{value % 100_000:05d}"


def variant_seed(namespace: str, kind: str, index: int, base_seed: int) -> int:
    require(namespace in {"dev", "confirm"}, f"unknown namespace {namespace!r}")
    digest = hashlib.sha256(
        f"{PROTOCOL_VERSION}:sentinel:{namespace}:{kind}:{index}:{base_seed}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big")


# ------------------------------------------------------------- the state machine


class ChargeOrderGame:
    """Deterministic synthetic mini-game; gold derives from THIS machine and is
    then independently checked against final arrays and rendered pages."""

    def __init__(self, layout: dict[str, Any]):
        self.layout = layout
        self.mover = tuple(layout["mover_start"])
        self.charged = False
        self.done = False

    def _zone(self, name: str) -> tuple[int, int, int, int]:
        return tuple(self.layout[name])  # (r0, c0, r1, c1) inclusive

    def _overlaps(self, position: tuple[int, int], zone: tuple[int, int, int, int]) -> bool:
        r, c = position
        r0, c0, r1, c1 = zone
        return not (r + MOVE - 1 < r0 or r > r1 or c + MOVE - 1 < c0 or c > c1)

    def board(self) -> list[list[int]]:
        grid = np.zeros((GRID, GRID), dtype=np.uint8)
        palette = self.layout["palette"]
        for zone_name, colour_key in (
            ("zone_a", "a"), ("zone_d", "d"), ("zone_b", "b"),
            ("decor_1", "s1"), ("decor_2", "s2"), ("inert_zone", "inert"),
        ):
            r0, c0, r1, c1 = self._zone(zone_name)
            grid[r0 : r1 + 1, c0 : c1 + 1] = palette[colour_key]
        r, c = self.mover
        grid[r : r + MOVE, c : c + MOVE] = palette["mover"]
        return grid.tolist()

    def step(self, action: str) -> dict[str, Any]:
        """Apply one action label from the variant's mapping; returns the
        transition row in the observation-log shape (pre/post/completed)."""
        require(not self.done, "episode already completed")
        pre = self.board()
        directions = self.layout["action_directions"]
        delta = directions.get(action)
        moved = False
        if delta is not None:
            dr, dc = delta
            r = min(max(self.mover[0] + dr * MOVE, 0), GRID - MOVE)
            c = min(max(self.mover[1] + dc * MOVE, 0), GRID - MOVE)
            moved = (r, c) != self.mover
            self.mover = (r, c)
            if self._overlaps(self.mover, self._zone("zone_a")):
                self.charged = True
            elif self._overlaps(self.mover, self._zone("zone_d")):
                self.charged = False
        completed = False
        if moved and self._overlaps(self.mover, self._zone("zone_b")) and self.charged:
            completed = True
            self.done = True
        return {
            "action": action, "pre": pre, "post": self.board(),
            "completed": completed, "moved": moved,
        }


def objective_holds(game_layout: dict[str, Any], history: list[str]) -> bool:
    """Ground truth from the machine itself: replay and read the outcome."""
    game = ChargeOrderGame(game_layout)
    for action in history:
        row = game.step(action)
        if row["completed"]:
            return True
    return False


# ------------------------------------------------------------------- layouts


def _base_layout(rng: np.random.Generator) -> dict[str, Any]:
    colours = list(rng.permutation(np.arange(1, 16)))
    palette = {
        "mover": int(colours[0]), "a": int(colours[1]), "d": int(colours[2]),
        "b": int(colours[3]), "s1": int(colours[4]), "s2": int(colours[5]),
        "inert": int(colours[6]),
    }
    slots = [(2, 2), (2, 17), (17, 2), (17, 17)]
    order = list(rng.permutation(len(slots)))
    zones = {}
    for name, slot_index in zip(("zone_a", "zone_d", "zone_b", "inert_zone"), order):
        r0, c0 = slots[slot_index]
        zones[name] = [r0, c0, r0 + 3, c0 + 3]
    action_ids = [f"A{i}" for i in range(1, 5)]
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    mapping = {
        action: directions[j]
        for action, j in zip(action_ids, rng.permutation(4))
    }
    return {
        "palette": palette,
        **zones,
        "decor_1": [10, 4, 12, 9],
        "decor_2": [11, 14, 13, 19],
        "mover_start": [10, 10],
        "action_directions": mapping,
        "unused_action": "A5",
    }


def _lattice_goal(start: int, r0: int, r1: int) -> int:
    """The mover moves in MOVE-steps from its start, so a reachable overlap
    coordinate must sit on start's lattice inside [r0-MOVE+1, r1]."""
    candidates = [
        value for value in range(start % MOVE, GRID - MOVE + 1, MOVE)
        if r0 - MOVE + 1 <= value <= r1
    ]
    require(candidates, f"zone rows {r0}-{r1} unreachable from lattice of {start}")
    centre = (r0 + r1) / 2 - (MOVE - 1) / 2
    return min(candidates, key=lambda value: abs(value - centre))


def _route(layout: dict[str, Any], targets: list[str]) -> list[str]:
    """Deterministic action route overlapping each named zone in order.

    Every leg detours through the centre corridor (the mover's start), so a
    corner-to-corner walk can never clip an unintended zone; the caller then
    verifies actual zone entries against intent with `_zone_entries`.
    """
    inverse = {tuple(v): k for k, v in layout["action_directions"].items()}
    start = tuple(layout["mover_start"])
    position = start
    actions: list[str] = []

    def walk_to(goal: tuple[int, int]) -> None:
        nonlocal position
        guard = 0
        while position != goal:
            guard += 1
            require(guard < 64, f"walk to {goal} did not converge")
            dr = (goal[0] > position[0]) - (goal[0] < position[0])
            dc = (goal[1] > position[1]) - (goal[1] < position[1])
            step = (dr, 0) if dr else (0, dc)
            actions.append(inverse[step])
            position = (min(max(position[0] + step[0] * MOVE, 0), GRID - MOVE),
                        min(max(position[1] + step[1] * MOVE, 0), GRID - MOVE))

    for name in targets:
        r0, c0, r1, c1 = layout[name]
        goal = (_lattice_goal(start[0], r0, r1), _lattice_goal(start[1], c0, c1))
        if position != start:
            walk_to(start)
        walk_to(goal)
    return actions


def _zone_entries(layout: dict[str, Any], actions: list[str]) -> list[str]:
    """The ordered sequence of zone ENTRIES an action list actually produces."""
    game = ChargeOrderGame(layout)
    entries: list[str] = []
    inside: set[str] = set()
    zones = ("zone_a", "zone_d", "zone_b", "inert_zone")
    for action in actions:
        game.step(action)
        now = {name for name in zones if game._overlaps(game.mover, game._zone(name))}
        for name in now - inside:
            entries.append(name)
        inside = now
        if game.done:
            break
    return entries


def build_passive_variant(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """One counterbalanced passive fixture with its episodes and sealed gold."""
    rng = np.random.default_rng(variant_seed(namespace, "passive", index, base_seed))
    layout = _base_layout(rng)
    episodes: list[dict[str, Any]] = []

    def run_episode(name: str, targets: list[str], *,
                    stop_at_first: str | None = None) -> dict[str, Any]:
        actions = _route(layout, targets)
        require(_zone_entries(layout, actions) == list(targets),
                f"{name}: route entered zones beyond its intent")
        game = ChargeOrderGame(layout)
        rows = []
        for action in actions:
            rows.append(game.step(action))
            if rows[-1]["completed"]:
                break
            if stop_at_first is not None and game._overlaps(
                game.mover, game._zone(stop_at_first)
            ):
                # end the episode at FIRST overlap so a failure and a success can
                # share their exact final board (charge is invisible)
                break
        episode = {
            "name": name, "actions": [row["action"] for row in rows],
            "rows": rows, "completed": rows[-1]["completed"],
            "final_board": rows[-1]["post"],
        }
        episodes.append(episode)
        return episode

    success_1 = run_episode("success_direct", ["zone_a", "zone_b"])
    success_2 = run_episode("success_scenic", ["zone_d", "zone_a", "zone_b"])
    near_miss_uncharged = run_episode("near_miss_uncharged", ["zone_b"],
                                      stop_at_first="zone_b")
    near_miss_not_at_b = run_episode("near_miss_not_at_b",
                                     ["zone_a", "inert_zone"],
                                     stop_at_first="inert_zone")
    near_miss_drained = run_episode("near_miss_drained",
                                    ["zone_a", "zone_d", "zone_b"],
                                    stop_at_first="zone_b")
    # same-final-board pair: identical boards, different history, different outcome
    pair_success = success_1
    pair_failure = near_miss_drained
    require(pair_success["final_board"] == pair_failure["final_board"],
            "history pair does not share its final board")
    require(pair_success["completed"] and not pair_failure["completed"],
            "history pair does not differ in outcome")
    # unused action: observed no-effect row appended to a failure episode
    game = ChargeOrderGame(layout)
    for action in near_miss_uncharged["actions"]:
        game.step(action)
    no_effect = game.step(layout["unused_action"])
    require(no_effect["pre"] == no_effect["post"], "unused action must be a no-op")
    episodes.append({
        "name": "unused_action_probe", "actions": [layout["unused_action"]],
        "rows": [no_effect], "completed": False,
        "final_board": no_effect["post"],
    })

    # verify gold against the machine, both directions
    require(objective_holds(layout, success_1["actions"]), "gold: success_1 must hold")
    require(objective_holds(layout, success_2["actions"]), "gold: success_2 must hold")
    require(not objective_holds(layout, near_miss_uncharged["actions"]),
            "gold: uncharged near-miss must fail")
    require(not objective_holds(layout, near_miss_not_at_b["actions"]),
            "gold: not-at-target near-miss must fail")
    audit_not_at_b = ChargeOrderGame(layout)
    for action in near_miss_not_at_b["actions"]:
        audit_not_at_b.step(action)
    require(audit_not_at_b.charged
            and not audit_not_at_b._overlaps(
                audit_not_at_b.mover, audit_not_at_b._zone("zone_b")
            ), "gold: constraint-0 near-miss must preserve charge away from B")
    require(not objective_holds(layout, near_miss_drained["actions"]),
            "gold: drained near-miss must fail")

    nonce_root = f"{namespace}:{index}:{base_seed}"
    variant_id = _nonce(nonce_root, "SV")
    palette = layout["palette"]
    gold = {
        "variant_id": variant_id,
        "paraphrase": (
            f"The mover (colour {palette['mover']}) must arrive at the colour-"
            f"{palette['b']} zone while charged. Entering the colour-{palette['a']} "
            f"zone charges it; entering the colour-{palette['d']} zone discharges "
            "it; charge is not visible on the board, so outcome depends on the "
            "ORDER of zone visits, not on the final picture."
        ),
        "constraints": [
            f"The mover overlaps the colour-{palette['b']} zone at the completing step.",
            f"The mover entered the colour-{palette['a']} zone at some earlier step "
            f"and has not entered the colour-{palette['d']} zone since.",
        ],
        "history_pair": {
            "success": pair_success["name"], "failure": pair_failure["name"],
            "note": "identical final boards; only the ordered history differs",
        },
        "near_misses": {
            "constraint_0": near_miss_not_at_b["name"],
            "constraint_1": near_miss_uncharged["name"],
        },
        "history_sensitive_near_miss": near_miss_drained["name"],
        "distractors": [f"colour-{palette['s1']} shape", f"colour-{palette['s2']} shape",
                        f"colour-{palette['inert']} zone (causally inert)"],
        "unused_action": layout["unused_action"],
        "layout": layout,
    }
    return {
        "kind": "passive", "namespace": namespace, "index": index,
        "variant_id": variant_id, "layout": layout, "episodes": episodes,
        "gold": gold, "chronology_offset": index,  # pair position permutes by index
    }


def build_active_variant(namespace: str, index: int, base_seed: int) -> dict[str, Any]:
    """Ambiguous-evidence P fixture: exactly one listed probe discriminates.

    Shown evidence is consistent with G1 ("arriving at B completes") and G2
    ("arriving at B while charged completes", the truth): every shown success
    visited A before B, and every shown failure never reached B at all.
    """
    rng = np.random.default_rng(variant_seed(namespace, "active", index, base_seed))
    layout = _base_layout(rng)
    episodes = []

    def scripted(name: str, targets: list[str]) -> dict[str, Any]:
        actions = _route(layout, targets)
        require(_zone_entries(layout, actions) == list(targets),
                f"{name}: route entered zones beyond its intent")
        game = ChargeOrderGame(layout)
        rows = []
        for action in actions:
            rows.append(game.step(action))
            if rows[-1]["completed"]:
                break
        episode = {"name": name, "actions": actions, "rows": rows,
                   "completed": rows[-1]["completed"], "final_board": rows[-1]["post"]}
        episodes.append(episode)
        return episode

    success = scripted("shown_success", ["zone_a", "zone_b"])
    require(success["completed"], "active fixture: shown success must complete")
    wander = scripted("shown_wander", ["zone_d", "inert_zone"])
    require(not wander["completed"], "active fixture: wander must not complete")

    nonce_root = f"{namespace}:active:{index}:{base_seed}"
    variant_id = _nonce(nonce_root, "SA")
    prefix_ids = {
        "uncharged_near_b": _state_nonce(nonce_root + ":p1"),
        "charged_near_a": _state_nonce(nonce_root + ":p2"),
        "start": _state_nonce(nonce_root + ":p3"),
    }
    require(len(set(prefix_ids.values())) == len(prefix_ids),
            "active replay-state nonce collision")
    # Probe pool: replayable prefixes + one action each.  Exactly one probe
    # reaches B uncharged (discriminating G1 vs G2); the others are redundant.
    inverse = {tuple(v): k for k, v in layout["action_directions"].items()}
    prefix_to_b = _route(layout, ["zone_b"])           # from start, never touches A
    probes = {
        prefix_ids["uncharged_near_b"]: {
            "prefix_actions": prefix_to_b[:-1],
            "action": prefix_to_b[-1],
            "discriminating": True,
        },
        prefix_ids["charged_near_a"]: {
            "prefix_actions": _route(layout, ["zone_a"]),
            "action": inverse[(0, 1)],
            "discriminating": False,
        },
        prefix_ids["start"]: {
            "prefix_actions": [],
            "action": layout["unused_action"],
            "discriminating": False,
        },
    }
    for start_state_id, candidate in probes.items():
        game = ChargeOrderGame(layout)
        for action in candidate["prefix_actions"]:
            game.step(action)
        candidate["start_state_id"] = start_state_id
        candidate["action_schema"] = _action_schema(candidate["action"])
        candidate["prefix_board"] = game.board()
    # verify the discrimination claim against the machine
    disc = probes[prefix_ids["uncharged_near_b"]]
    outcome_true_goal = objective_holds(layout, disc["prefix_actions"] + [disc["action"]])
    require(outcome_true_goal is False,
            "discriminating probe must FAIL under the true conjunctive goal")
    game = ChargeOrderGame(layout)
    for action in disc["prefix_actions"]:
        game.step(action)
    final = game.step(disc["action"])
    reached_b = ChargeOrderGame(layout)._overlaps(  # geometry check on the final position
        tuple(np.argwhere(np.asarray(final["post"]) == layout["palette"]["mover"]).min(axis=0)),
        tuple(layout["zone_b"]),
    )
    require(reached_b, "discriminating probe must actually reach zone B uncharged")
    discriminating_ids: list[str] = []
    for start_state_id, candidate in probes.items():
        replay = ChargeOrderGame(layout)
        for action in candidate["prefix_actions"]:
            replay.step(action)
        candidate_row = replay.step(candidate["action"])
        decoy_completion = (
            candidate_row["moved"]
            and replay._overlaps(replay.mover, replay._zone("zone_b"))
        )
        true_completion = candidate_row["completed"]
        if decoy_completion != true_completion:
            discriminating_ids.append(start_state_id)
        require(candidate["discriminating"] == (decoy_completion != true_completion),
                "active probe discrimination annotation differs from replay")
    require(discriminating_ids == [prefix_ids["uncharged_near_b"]],
            "active fixture must have exactly one discriminating legal probe")

    gold = {
        "variant_id": variant_id,
        "true_goal": (
            f"arriving at the colour-{layout['palette']['b']} zone completes ONLY "
            f"when charged (colour-{layout['palette']['a']} zone entered, no "
            f"colour-{layout['palette']['d']} zone since)"
        ),
        "decoy_goal": f"arriving at the colour-{layout['palette']['b']} zone completes",
        "discriminating_probe": prefix_ids["uncharged_near_b"],
        "constraints": [
            f"The mover overlaps the colour-{layout['palette']['b']} zone at the "
            "completing step.",
            f"The mover entered the colour-{layout['palette']['a']} zone earlier "
            f"and has not entered the colour-{layout['palette']['d']} zone since.",
        ],
        "layout": layout,
    }
    return {
        "kind": "active", "namespace": namespace, "index": index,
        "variant_id": variant_id, "layout": layout, "episodes": episodes,
        "probes": probes, "gold": gold,
    }


# ---------------------------------------------------------------- carriers


def _grid_rle_exact(grid: Any) -> str:
    """Packet RLE syntax with an honest sentinel dimension prefix."""
    import s4_packet as spk

    rows = np.asarray(grid, dtype=np.uint8)
    require(rows.shape == (GRID, GRID), "sentinel text grid has unexpected shape")
    payload = spk._grid_rle(rows).removeprefix("rle64:")
    return f"rle{GRID}:" + payload


def _decode_grid_rle_exact(encoded: str) -> list[list[int]]:
    prefix = f"rle{GRID}:"
    require(encoded.startswith(prefix), "unknown sentinel text-grid encoding")
    result: list[list[int]] = []
    for grouped in encoded.removeprefix(prefix).split("/"):
        row_text, repeat_text = (grouped.rsplit("^", 1)
                                 if "^" in grouped else (grouped, "1"))
        row: list[int] = []
        for run in row_text.split(","):
            colour, count = run.split("*", 1) if "*" in run else (run, "1")
            row.extend([int(colour, 16)] * int(count))
        require(len(row) == GRID, "decoded sentinel RLE row has wrong width")
        result.extend([list(row) for _ in range(int(repeat_text))])
    require(len(result) == GRID, "decoded sentinel RLE has wrong height")
    return result


def render_text_carrier(fixture: dict[str, Any]) -> str:
    """T carrier: exact boards + semantics-free delta records + action rows,
    in the packet's exact-text conventions."""
    nonce_root = f"{fixture['namespace']}:{fixture['index']}:{fixture['variant_id']}"
    lines: list[str] = [
        "AUTONOMOUS OBSERVATION LEDGER [OBSERVED/DERIVED-EXACT only]",
        f"Boards are {GRID}x{GRID}. rle{GRID} uses hex_colour*run_length, "
        "slash-separated rows, and ^N for N identical complete rows.",
    ]
    ordered = fixture["episodes"][fixture.get("chronology_offset", 0):] + \
        fixture["episodes"][: fixture.get("chronology_offset", 0)]
    mover_colour = int(fixture["layout"]["palette"]["mover"])

    def mover_bbox(board: list[list[int]]) -> list[int]:
        hits = np.argwhere(np.asarray(board, dtype=np.uint8) == mover_colour)
        require(hits.shape[0] == MOVE * MOVE,
                "sentinel mover component is not uniquely recoverable")
        return [int(hits[:, 0].min()), int(hits[:, 1].min()),
                int(hits[:, 0].max()), int(hits[:, 1].max())]

    for episode in ordered:
        eid = _nonce(nonce_root + episode["name"], "E")
        lines.append(f"episode {eid}: {len(episode['rows'])} transitions")
        boards = [episode["rows"][0]["pre"]] + [row["post"] for row in episode["rows"]]
        frame_ids = [_nonce(nonce_root + episode["name"] + str(i), "F")
                     for i in range(len(boards))]
        for row_index, row in enumerate(episode["rows"]):
            lines.append(
                f"  {frame_ids[row_index]} -{row['action']}-> "
                f"{frame_ids[row_index + 1]} moved={row['moved']} "
                f"completed={row['completed']} "
                f"acted_colour={mover_colour} "
                f"bbox={mover_bbox(row['pre'])}>{mover_bbox(row['post'])} [OBSERVED]"
            )
        first_rle = _grid_rle_exact(boards[0])
        final_rle = _grid_rle_exact(boards[-1])
        require(_decode_grid_rle_exact(first_rle) == boards[0]
                and _decode_grid_rle_exact(final_rle) == boards[-1],
                "sentinel text-grid decode differs from the state machine")
        lines.append(f"  first board {frame_ids[0]}: {first_rle}")
        lines.append(f"  final board {frame_ids[-1]}: {final_rle}")
        # The complete action/bbox chronology above is exact and compact.  One
        # cell-exact temporal record per episode exercises the same delta
        # primitive without repeating 80 mostly translational sparse cell lists.
        record = sd.sequence_record(
            frame_ids[-2:], boards[-2:],
            binding={"eid": eid, "kind": "episode_final_transition"},
        )
        sd.verify_sequence_record(record, boards[-2:])
        lines.append(sd.render_text_block(record))
    return "\n".join(lines)


def _decode_storyboard(plate: sr.Plate, shape: tuple[int, int]) -> list[np.ndarray]:
    """Independently recover every board from final storyboard pixels."""
    rgb = np.asarray(plate.image)
    frames = int(plate.meta["frames"])
    cols = int(plate.meta["cols"])
    gap, label_h = 8, 16
    height, width = shape
    panel_h, panel_w = height * plate.cell_px, width * plate.cell_px
    lookup = {colour: value for value, colour in sr.ARC_COLOR_MAP.items()}
    decoded: list[np.ndarray] = []
    for frame_index in range(frames):
        panel_r, panel_c = divmod(frame_index, cols)
        y0 = gap + panel_r * (panel_h + label_h + gap)
        x0 = gap + panel_c * (panel_w + gap)
        cells = rgb[y0:y0 + panel_h:plate.cell_px,
                    x0:x0 + panel_w:plate.cell_px]
        require(cells.shape[:2] == shape,
                "sentinel storyboard has invalid final-pixel geometry")
        board = np.zeros(shape, dtype=np.uint8)
        for r in range(height):
            for c in range(width):
                colour = tuple(int(value) for value in cells[r, c])
                require(colour in lookup,
                        "sentinel storyboard contains a non-palette board pixel")
                board[r, c] = lookup[colour]
        decoded.append(board)
    return decoded


def _decode_diff(plate: sr.Plate, shape: tuple[int, int]) -> np.ndarray:
    rgb = np.asarray(plate.image)
    cells = rgb[:shape[0] * plate.cell_px:plate.cell_px,
                :shape[1] * plate.cell_px:plate.cell_px, 0]
    require(cells.shape == shape and set(int(value) for value in np.unique(cells)) <= {0, 255},
            "sentinel diff page has invalid final pixels")
    return cells == 255


def render_page_carrier(fixture: dict[str, Any], carrier: str,
                        work: Path) -> tuple[list[Path], list[str]]:
    """V/O carriers: page images through the real renderer at carrier floors."""
    require(carrier in {"raw", "overlay"}, f"unknown carrier {carrier!r}")
    nonce_root = f"{fixture['namespace']}:{fixture['index']}:{fixture['variant_id']}"
    pages: list[tuple[str, Any]] = []
    first_board = np.asarray(fixture["episodes"][0]["rows"][0]["pre"], dtype=np.uint8)
    opening = sr.render_board(first_board, cell_px=8)
    require(np.array_equal(sr.decode_board(opening), first_board),
            "sentinel opening PNG decode differs from the state machine")
    pages.append(("opening_8px", opening))
    ordered = fixture["episodes"][fixture.get("chronology_offset", 0):] + \
        fixture["episodes"][: fixture.get("chronology_offset", 0)]
    for episode in ordered:
        frames = [np.asarray(episode["rows"][0]["pre"], dtype=np.uint8)] + [
            np.asarray(row["post"], dtype=np.uint8) for row in episode["rows"]
        ]
        label = _nonce(nonce_root + episode["name"], "E")
        story = sr.storyboard(frames, cols=min(6, len(frames)), cell_px=8)
        decoded_story = _decode_storyboard(story, first_board.shape)
        require(len(decoded_story) == len(frames)
                and all(np.array_equal(actual, expected)
                        for actual, expected in zip(decoded_story, frames)),
                "sentinel storyboard PNG decode differs from the state machine")
        pages.append((f"{label}_storyboard", story))
        if carrier == "overlay":
            pre = frames[-2]
            post = frames[-1]
            diff = sr.render_diff_mask(pre, post, cell_px=8)
            require(np.array_equal(_decode_diff(diff, first_board.shape), pre != post),
                    "sentinel diff PNG decode differs from the state machine")
            pages.append((f"{label}_diff", diff))
    labels = []
    paths = []
    for page_no, (name, plate) in enumerate(pages, start=1):
        path = plate.save(work / f"{fixture['variant_id']}_{carrier}_p{page_no:02d}.png")
        paths.append(path)
        labels.append(f"Page {page_no} of {len(pages)}: {name}")
    return paths, labels


def execute_active_probe(fixture: dict[str, Any], start_state_id: str,
                         action: dict[str, Any]) -> dict[str, Any] | None:
    """Execute an exact listed candidate; invalid requests are never repaired."""
    candidate = fixture["probes"].get(start_state_id)
    if candidate is None or action != candidate["action_schema"]:
        return None
    game = ChargeOrderGame(fixture["layout"])
    for prefix_action in candidate["prefix_actions"]:
        game.step(prefix_action)
    pre = game.board()
    row = game.step(candidate["action"])
    pre_id = _nonce(f"{fixture['variant_id']}:{start_state_id}:pre", "Q")
    post_id = _nonce(f"{fixture['variant_id']}:{start_state_id}:post", "Q")
    delta = sd.sequence_record(
        [pre_id, post_id], [pre, row["post"]],
        binding={"start_state_id": start_state_id,
                 "action": candidate["action_schema"], "kind": "live_probe"},
    )
    sd.verify_sequence_record(delta, [pre, row["post"]])
    return {
        "start_state_id": start_state_id,
        "action": candidate["action_schema"],
        "pre_id": pre_id,
        "post_id": post_id,
        "pre": pre,
        "post": row["post"],
        "completed": row["completed"],
        "moved": row["moved"],
        "delta": delta,
        # This field is sealed/audit-only and never rendered into a prompt.
        "discriminating": candidate["discriminating"],
    }


def render_active_assets(fixture: dict[str, Any], assets_root: Path) -> dict[str, Any]:
    """Render the P carrier and every possible probe result before freezing.

    The model-visible pool is deliberately semantics-free: it exposes only an
    opaque replay-state nonce, exact pilot action object, and rendered prefix.
    Internal mnemonic keys and the discriminating bit never enter an asset.
    """
    variant_root = assets_root / fixture["variant_id"]
    variant_root.mkdir(parents=True, exist_ok=True)
    text_path = assets_root / f"{fixture['variant_id']}_text.txt"
    text_path.write_text(render_text_carrier(fixture), encoding="utf-8")
    initial_paths, initial_labels = render_page_carrier(
        fixture, "overlay", variant_root,
    )
    pool: list[dict[str, Any]] = []
    observations: dict[str, Any] = {}
    for candidate_index, start_state_id in enumerate(sorted(fixture["probes"]), start=1):
        candidate = fixture["probes"][start_state_id]
        prefix_name = f"candidate_{candidate_index:02d}_prefix.png"
        prefix_board = np.asarray(candidate["prefix_board"], dtype=np.uint8)
        prefix_plate = sr.render_board(prefix_board, cell_px=8)
        require(np.array_equal(sr.decode_board(prefix_plate), prefix_board),
                "active prefix PNG decode differs from replay")
        prefix_path = prefix_plate.save(variant_root / prefix_name)
        observation = execute_active_probe(
            fixture, start_state_id, candidate["action_schema"],
        )
        require(observation is not None, "generated active probe failed exact replay")
        storyboard_name = f"candidate_{candidate_index:02d}_result.png"
        diff_name = f"candidate_{candidate_index:02d}_result_diff.png"
        observation_frames = [
            np.asarray(observation["pre"], dtype=np.uint8),
            np.asarray(observation["post"], dtype=np.uint8),
        ]
        storyboard_plate = sr.storyboard(observation_frames, cols=2, cell_px=8)
        require(all(np.array_equal(actual, expected) for actual, expected in zip(
            _decode_storyboard(storyboard_plate, prefix_board.shape), observation_frames,
        )), "active result PNG decode differs from replay")
        storyboard_path = storyboard_plate.save(variant_root / storyboard_name)
        diff_plate = sr.render_diff_mask(
            observation_frames[0], observation_frames[1], cell_px=8,
        )
        require(np.array_equal(_decode_diff(diff_plate, prefix_board.shape),
                               observation_frames[0] != observation_frames[1]),
                "active result diff PNG decode differs from replay")
        diff_path = diff_plate.save(variant_root / diff_name)
        pool.append({
            "candidate": candidate_index,
            "start_state_id": start_state_id,
            "action": candidate["action_schema"],
            "prefix_page": prefix_path.name,
        })
        observations[start_state_id] = {
            "action": candidate["action_schema"],
            "completed": observation["completed"],
            "moved": observation["moved"],
            "delta_text": sd.render_text_block(observation["delta"]),
            "result_pages": [storyboard_path.name, diff_path.name],
        }
    visible = {
        "variant_id": fixture["variant_id"],
        "initial_text_file": text_path.name,
        "initial_pages": [path.name for path in initial_paths],
        "initial_page_labels": initial_labels,
        "probe_pool": pool,
        "probe_observations": observations,
    }
    visible_path = variant_root / "active_carrier.json"
    visible_path.write_text(json.dumps(visible, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
    return visible


def sentinel_request(fixture: dict[str, Any], *, outcome_note: str) -> str:
    """The pilot's exact answer contract, with completed flags as the outcomes."""
    import s4_run as srun

    return srun.REQUEST + "\n\n" + outcome_note


# ----------------------------------------------------------------- scoring


def score_active_interaction(fixture: dict[str, Any],
                             pre_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Mechanical: did the pre-probe answer request the discriminating probe
    while keeping more than one live hypothesis?"""
    if pre_payload is None:
        return {"valid_discriminating_interaction": False,
                "reason": "no schema-valid pre-probe answer"}
    request = pre_payload.get("next_probe") or {}
    requested = request.get("start_state_id")
    requested_action = request.get("action")
    discriminating = fixture["gold"]["discriminating_probe"]
    expected_action = fixture["probes"][discriminating]["action_schema"]
    hypotheses = pre_payload.get("hypotheses") or []
    live = [h for h in hypotheses
            if isinstance(h, dict)
            and isinstance(h.get("probability"), (int, float))
            and not isinstance(h.get("probability"), bool)
            and h["probability"] >= 0.1]
    predictions = request.get("predictions_by_hypothesis") or {}
    prediction_values = ([
        predictions.get("0", "").strip().casefold(),
        predictions.get("1", "").strip().casefold(),
    ] if isinstance(predictions, dict)
        and isinstance(predictions.get("0"), str)
        and isinstance(predictions.get("1"), str) else [])
    predictions_disagree = (
        len(prediction_values) == 2
        and all(prediction_values)
        and prediction_values[0] != prediction_values[1]
    )
    return {
        "requested_start_state_id": requested,
        "requested_action": requested_action,
        "discriminating_start_state_id": discriminating,
        "discriminating_action": expected_action,
        "kept_ambiguity": len(live) >= 2,
        "predictions_disagree": predictions_disagree,
        "valid_discriminating_interaction": (
            requested == discriminating
            and requested_action == expected_action
            and len(live) >= 2
            and predictions_disagree
        ),
    }


def build_worksheet(fixture: dict[str, Any], payload: dict[str, Any] | None,
                    *, stage: str, carrier: str) -> dict[str, Any]:
    """Adjudication worksheet in the grader's style: sealed gold constraints
    against the model's stated goal; VERDICT slots empty; aggregation mechanical.
    No constraint may be credited from a partial or correlated description."""
    gold = fixture["gold"]
    answer = payload or {}
    return {
        "variant_id": fixture["variant_id"], "kind": fixture["kind"],
        "carrier": carrier, "stage": stage,
        "model_best_goal": (answer.get("best_goal") or {}).get("plain_causal_condition"),
        "model_hypotheses": answer.get("hypotheses"),
        "sealed_paraphrase": gold.get("paraphrase") or gold.get("true_goal"),
        "sealed_constraints": gold["constraints"],
        "VERDICT_goal_correct_in_kind": None,
        "VERDICT_constraints_by_item": [None] * len(gold["constraints"]),
        "adjudication_rule": (
            "a constraint is credited only when the answer states it as a "
            "necessary condition; partial or merely correlated descriptions "
            "receive no credit"
        ),
    }


def _worksheet_complete(sheet: dict[str, Any], *, label: str) -> bool | None:
    require(isinstance(sheet, dict), f"{label} must be an object")
    goal = sheet.get("VERDICT_goal_correct_in_kind")
    constraints = sheet.get("VERDICT_constraints_by_item")
    require(goal is None or type(goal) is bool,
            f"{label}.VERDICT_goal_correct_in_kind must be bool|null")
    require(isinstance(constraints, list) and len(constraints) == 2,
            f"{label} must contain exactly two constraint verdicts")
    require(all(value is None or type(value) is bool for value in constraints),
            f"{label} constraint verdicts must be bool|null")
    verdicts = [goal, *constraints]
    if any(value is None for value in verdicts):
        return None
    return all(value is True for value in verdicts)


def aggregate_passive(
    worksheets: dict[str, list[dict[str, Any]]],
    *, expected_variant_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Mechanical aggregation once verdicts are filled: >=2/3 complete variants
    per arm.  A worksheet with any unfilled verdict keeps its arm undecided."""
    require(isinstance(worksheets, dict), "passive_worksheets must be an object")
    require(set(worksheets) == set(PASSIVE_ARMS),
            f"passive inventory must contain exactly {list(PASSIVE_ARMS)}")
    expected = set(expected_variant_ids) if expected_variant_ids is not None else None
    if expected is not None:
        require(len(expected) == PASSIVE_VARIANTS,
                f"expected exactly {PASSIVE_VARIANTS} passive variant IDs")
    summary: dict[str, Any] = {}
    reference_ids: set[str] | None = None
    for arm in PASSIVE_ARMS:
        sheets = worksheets[arm]
        require(isinstance(sheets, list) and len(sheets) == PASSIVE_VARIANTS,
                f"{arm} must contain exactly {PASSIVE_VARIANTS} worksheets")
        variant_ids = [sheet.get("variant_id") if isinstance(sheet, dict) else None
                       for sheet in sheets]
        require(all(isinstance(value, str) and value for value in variant_ids),
                f"{arm} worksheets need non-empty variant_id values")
        require(len(set(variant_ids)) == PASSIVE_VARIANTS,
                f"{arm} passive variant IDs must be unique")
        require(all(sheet.get("carrier") == arm and sheet.get("kind") == "passive"
                    and sheet.get("stage") == "single" for sheet in sheets),
                f"{arm} passive worksheet carrier/kind/stage binding is invalid")
        arm_ids = set(variant_ids)
        if expected is not None:
            require(arm_ids == expected,
                    f"{arm} passive variants differ from the frozen manifest")
        if reference_ids is None:
            reference_ids = arm_ids
        else:
            require(arm_ids == reference_ids,
                    "T/V/O must contain the same passive variant inventory")
        complete = 0
        undecided = 0
        for index, sheet in enumerate(sheets):
            verdict = _worksheet_complete(sheet, label=f"{arm}[{index}]")
            if verdict is None:
                undecided += 1
            elif verdict:
                complete += 1
        summary[arm] = {
            "variants": PASSIVE_VARIANTS, "complete_objective": complete,
            "undecided": undecided,
            "pass": complete >= PASS_THRESHOLD and undecided == 0,
        }
    return summary


def aggregate_active(
    records: list[dict[str, Any]],
    *, expected_variant_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    require(isinstance(records, list) and len(records) == ACTIVE_VARIANTS,
            f"active_records must contain exactly {ACTIVE_VARIANTS} variants")
    ids = [record.get("variant_id") if isinstance(record, dict) else None
           for record in records]
    require(all(isinstance(value, str) and value for value in ids),
            "active records need non-empty variant_id values")
    require(len(set(ids)) == ACTIVE_VARIANTS, "active variant IDs must be unique")
    if expected_variant_ids is not None:
        expected = set(expected_variant_ids)
        require(len(expected) == ACTIVE_VARIANTS,
                f"expected exactly {ACTIVE_VARIANTS} active variant IDs")
        require(set(ids) == expected,
                "active variants differ from the frozen sentinel manifest")
    final_values: list[bool | None] = []
    for index, record in enumerate(records):
        require(record.get("kind") == "active" and record.get("carrier") == ACTIVE_ARM,
                f"active[{index}] carrier/kind binding is invalid")
        require(set(record.get("stages") or []) == set(ACTIVE_STAGES),
                f"active[{index}] must bind exactly pre and post calls")
        worksheet = record.get("final_worksheet")
        require(isinstance(worksheet, dict)
                and worksheet.get("variant_id") == record["variant_id"]
                and worksheet.get("carrier") == ACTIVE_ARM
                and worksheet.get("kind") == "active"
                and worksheet.get("stage") == "post",
                f"active[{index}] final worksheet binding is invalid")
        final_values.append(_worksheet_complete(
            worksheet, label=f"active[{index}].final_worksheet",
        ))
    finals = sum(value is True for value in final_values)
    undecided = sum(value is None for value in final_values)
    interactions = sum(
        1 for record in records
        if record.get("interaction", {}).get("valid_discriminating_interaction")
    )
    return {
        "variants": ACTIVE_VARIANTS,
        "final_goal_passes": finals,
        "valid_discriminating_interactions": interactions,
        "undecided": undecided,
        "pass": (finals >= PASS_THRESHOLD and interactions >= PASS_THRESHOLD
                 and undecided == 0),
    }


def _manifest_variant_carriers(manifest: dict[str, Any]) -> dict[str, set[str]]:
    require(isinstance(manifest, dict), "sentinel manifest must be an object")
    passive = manifest.get("passive")
    active = manifest.get("active")
    require(isinstance(passive, list) and len(passive) == PASSIVE_VARIANTS,
            "sentinel manifest passive inventory is invalid")
    require(isinstance(active, list) and len(active) == ACTIVE_VARIANTS,
            "sentinel manifest active inventory is invalid")
    expected: dict[str, set[str]] = {}
    for record in passive:
        variant_id = record.get("variant_id") if isinstance(record, dict) else None
        require(isinstance(variant_id, str) and variant_id not in expected,
                "sentinel manifest passive IDs must be unique strings")
        expected[variant_id] = set(PASSIVE_ARMS)
    for record in active:
        variant_id = record.get("variant_id") if isinstance(record, dict) else None
        require(isinstance(variant_id, str) and variant_id not in expected,
                "sentinel manifest active IDs must be unique and disjoint")
        expected[variant_id] = {ACTIVE_ARM}
    return expected


def validate_adequacy_attestation(
    value: Any, *, manifest: dict[str, Any] | None = None,
    manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """The independent, source-blind reviewer's record.  The pinned same-model
    descriptive comparator is not an independent adequacy ceiling."""
    require(isinstance(value, dict), "adequacy attestation must be an object")
    required = {
        "reviewer", "reviewer_kind", "method", "per_variant", "verdict",
        "attested_utc", "source_blind", "pinned_same_model_used",
        "sentinel_outputs_seen",
    }
    missing = required - set(value)
    require(not missing, f"adequacy attestation missing {sorted(missing)}")
    require(isinstance(value["reviewer"], str) and value["reviewer"].strip(),
            "adequacy reviewer must be identified")
    require(isinstance(value["method"], str) and value["method"].strip(),
            "adequacy review method must be described")
    require(value["source_blind"] is True,
            "adequacy reviewer must attest source blindness")
    require(value["pinned_same_model_used"] is False,
            "the pinned same-model comparator cannot review adequacy")
    require(value["sentinel_outputs_seen"] is False,
            "adequacy must be judged from carriers, not sentinel model outputs")
    require(value["reviewer_kind"] in {"human", "independent_model"},
            "adequacy reviewer must be a human or an INDEPENDENT model")
    require(value["reviewer_kind"] != "independent_model"
            or value.get("model_identity_differs_from_pinned") is True,
            "an independent-model reviewer must attest a different model identity")
    if value["reviewer_kind"] == "independent_model":
        require(isinstance(value.get("reviewer_model_identity"), dict)
                and value["reviewer_model_identity"],
                "independent-model adequacy needs an exact reviewer identity")
    per_variant = value["per_variant"]
    require(isinstance(per_variant, dict) and per_variant,
            "adequacy attestation needs per-variant records")
    expected = _manifest_variant_carriers(manifest) if manifest is not None else None
    if expected is None:
        # Even a standalone/dev attestation must cover a complete six-variant
        # inventory; only a manifest-bound review can establish exact IDs.
        require(len(per_variant) == PASSIVE_VARIANTS + ACTIVE_VARIANTS,
                "adequacy attestation must contain all six sentinel variants")
    else:
        require(set(per_variant) == set(expected),
                "adequacy variant inventory differs from the frozen manifest")
        require(isinstance(manifest_sha256, str) and len(manifest_sha256) == 64,
                "manifest-bound adequacy validation requires its byte SHA-256")
        require(value.get("sentinel_manifest_sha256") == manifest_sha256,
                "adequacy attestation is not bound to the sealed sentinel manifest")
    all_sufficient = True
    for variant_id, record in per_variant.items():
        require(isinstance(record, dict), f"adequacy record for {variant_id} is incomplete")
        carriers = record.get("carriers")
        require(isinstance(carriers, dict),
                f"adequacy record for {variant_id} needs a carriers object")
        wanted = expected[variant_id] if expected is not None else set(carriers)
        require(wanted and set(carriers) == wanted,
                f"adequacy carrier inventory for {variant_id} is incomplete")
        for carrier, carrier_record in carriers.items():
            require(carrier in set(PASSIVE_ARMS) | {ACTIVE_ARM},
                    f"unknown adequacy carrier {carrier!r}")
            require(isinstance(carrier_record, dict)
                    and isinstance(carrier_record.get("recovered_goal"), str)
                    and carrier_record["recovered_goal"].strip()
                    and type(carrier_record.get("evidence_sufficient")) is bool,
                    f"adequacy record for {variant_id}/{carrier} is incomplete")
            all_sufficient = all_sufficient and carrier_record["evidence_sufficient"]
    require(value["verdict"] in {"adequate", "inadequate"},
            "adequacy verdict must be adequate|inadequate")
    require((value["verdict"] == "adequate") == all_sufficient,
            "adequacy verdict must equal the conjunction of every carrier record")
    _parse_utc(value["attested_utc"], "adequacy attested_utc")
    return value


def _populate_all(namespace: str, base_seed: int, out_root: Path) -> dict[str, Any]:
    """Populate a new staging directory; the caller publishes it atomically."""
    assets_root = out_root / "assets"
    gold_root = out_root / "gold"
    assets_root.mkdir(parents=True, exist_ok=True)
    gold_root.mkdir(parents=True, exist_ok=True)
    generator_hash = sha256_file(Path(__file__))
    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION, "protocol_version": PROTOCOL_VERSION,
        "namespace": namespace, "base_seed": base_seed,
        "generator_sha256": generator_hash,
        "total_generations_budget": TOTAL_GENERATIONS,
        "thresholds": {
            "passive_arms": list(PASSIVE_ARMS),
            "passive_variants_per_arm": PASSIVE_VARIANTS,
            "active_variants": ACTIVE_VARIANTS,
            "pass_threshold": PASS_THRESHOLD,
            "exact_generation_count": TOTAL_GENERATIONS,
        },
        "passive": [], "active": [],
    }
    for index in range(PASSIVE_VARIANTS):
        fixture = build_passive_variant(namespace, index, base_seed)
        text = render_text_carrier(fixture)
        text_path = assets_root / f"{fixture['variant_id']}_text.txt"
        text_path.write_text(text, encoding="utf-8")
        work = assets_root / fixture["variant_id"]
        work.mkdir(exist_ok=True)
        carriers: dict[str, Any] = {
            "T": {"text_file": str(text_path.relative_to(out_root)), "pages": []},
        }
        for carrier in ("raw", "overlay"):
            paths, labels = render_page_carrier(fixture, carrier, work)
            arm = "V" if carrier == "raw" else "O"
            carriers[arm] = {
                "text_file": str(text_path.relative_to(out_root)),
                "pages": [str(path.relative_to(out_root)) for path in paths],
                "labels": labels,
            }
        gold_path = gold_root / f"{fixture['variant_id']}.json"
        gold_path.write_text(json.dumps(fixture["gold"], indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
        manifest["passive"].append({
            "variant_id": fixture["variant_id"],
            "gold_sha256": sd.canonical_sha256(fixture["gold"]),
            "gold_file": str(gold_path.relative_to(out_root)),
            "carriers": carriers,
        })
    for index in range(ACTIVE_VARIANTS):
        fixture = build_active_variant(namespace, index, base_seed)
        visible = render_active_assets(fixture, assets_root)
        gold_path = gold_root / f"{fixture['variant_id']}.json"
        gold_path.write_text(json.dumps(fixture["gold"], indent=1, sort_keys=True) + "\n",
                             encoding="utf-8")
        manifest["active"].append({
            "variant_id": fixture["variant_id"],
            "gold_sha256": sd.canonical_sha256(fixture["gold"]),
            "gold_file": str(gold_path.relative_to(out_root)),
            "carrier_file": str(
                (assets_root / fixture["variant_id"] / "active_carrier.json")
                .relative_to(out_root)
            ),
            "probe_pool": [record["start_state_id"] for record in visible["probe_pool"]],
        })
    manifest["asset_files"] = {
        str(path.relative_to(out_root)): sha256_file(path)
        for path in sorted(assets_root.rglob("*")) if path.is_file()
    }
    manifest["gold_files"] = {
        str(path.relative_to(out_root)): sha256_file(path)
        for path in sorted(gold_root.rglob("*")) if path.is_file()
    }
    path = out_root / "sentinel_manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def generate_all(namespace: str, base_seed: int, out_root: Path) -> dict[str, Any]:
    """Build and atomically publish a complete append-only fixture family.

    Confirmation material is never regenerated or overwritten.  The same rule
    applies to an explicit development target so stale pages cannot survive a
    partial rebuild and masquerade as members of the new manifest.
    """
    require(namespace in {"dev", "confirm"}, f"unknown namespace {namespace!r}")
    require(type(base_seed) is int and 0 <= base_seed < 2 ** 63,
            "base_seed must be a non-negative JSON integer")
    require(not out_root.exists(), f"sentinel fixture root already exists: {out_root}")
    out_root.parent.mkdir(parents=True, exist_ok=True)
    staging: Path | None = Path(tempfile.mkdtemp(
        prefix=f".{out_root.name}.staging.", dir=out_root.parent,
    ))
    try:
        manifest = _populate_all(namespace, base_seed, staging)
        verify_manifest(staging / "sentinel_manifest.json", expected_namespace=namespace,
                        expected_base_seed=base_seed, require_live_generator=True)
        staging.rename(out_root)
        staging = None  # suppress cleanup after the atomic publish
        if namespace == "confirm":
            for path in sorted(out_root.rglob("*"), reverse=True):
                path.chmod(0o444 if path.is_file() else 0o555)
            out_root.chmod(0o555)
        return manifest
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)


def load_manifest(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing sentinel manifest: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read sentinel manifest {path}: {exc}") from exc
    require(isinstance(value, dict), "sentinel manifest must be a JSON object")
    return value


def verify_manifest(
    manifest_path: Path, *, expected_namespace: str | None = None,
    expected_base_seed: int | None = None, require_live_generator: bool = False,
) -> dict[str, Any]:
    """Verify exact file inventories and every model-visible/gold byte hash."""
    manifest = load_manifest(manifest_path)
    root = manifest_path.parent
    require(manifest.get("format_version") == FORMAT_VERSION
            and manifest.get("protocol_version") == PROTOCOL_VERSION,
            "sentinel manifest version mismatch")
    if expected_namespace is not None:
        require(manifest.get("namespace") == expected_namespace,
                "sentinel manifest namespace mismatch")
    if expected_base_seed is not None:
        require(manifest.get("base_seed") == expected_base_seed,
                "sentinel manifest base seed mismatch")
    require(manifest.get("total_generations_budget") == TOTAL_GENERATIONS,
            "sentinel manifest generation budget mismatch")
    expected_carriers = _manifest_variant_carriers(manifest)
    require(len(expected_carriers) == PASSIVE_VARIANTS + ACTIVE_VARIANTS,
            "sentinel manifest variant inventory is incomplete")
    thresholds = manifest.get("thresholds") or {}
    require(thresholds == {
        "passive_arms": list(PASSIVE_ARMS),
        "passive_variants_per_arm": PASSIVE_VARIANTS,
        "active_variants": ACTIVE_VARIANTS,
        "pass_threshold": PASS_THRESHOLD,
        "exact_generation_count": TOTAL_GENERATIONS,
    }, "sentinel manifest thresholds differ from the executable protocol")
    if require_live_generator:
        require(manifest.get("generator_sha256") == sha256_file(Path(__file__)),
                "sentinel generator differs from the committed fixture generator")
    for key, directory in (("asset_files", root / "assets"),
                           ("gold_files", root / "gold")):
        expected_files = manifest.get(key)
        require(isinstance(expected_files, dict) and expected_files,
                f"sentinel manifest lacks {key}")
        actual_paths = sorted(path for path in directory.rglob("*") if path.is_file())
        actual_names = {str(path.relative_to(root)) for path in actual_paths}
        require(actual_names == set(expected_files),
                f"sentinel {key} exact inventory drift")
        for relative, digest in expected_files.items():
            require(isinstance(digest, str) and len(digest) == 64,
                    f"invalid SHA-256 for {relative}")
            require(sha256_file(root / relative) == digest,
                    f"sentinel asset/gold byte drift: {relative}")
    asset_names = set(manifest["asset_files"])
    gold_names = set(manifest["gold_files"])
    for record in [*manifest["passive"], *manifest["active"]]:
        gold_file = record.get("gold_file")
        require(gold_file in gold_names, f"{record.get('variant_id')} gold is unbound")
        gold = _load_json(root / gold_file, "sentinel gold")
        require(gold.get("variant_id") == record.get("variant_id")
                and canonical_sha256(gold) == record.get("gold_sha256"),
                f"{record.get('variant_id')} gold content binding is invalid")
    for record in manifest["passive"]:
        carriers = record.get("carriers") or {}
        require(set(carriers) == set(PASSIVE_ARMS),
                f"{record.get('variant_id')} passive carrier inventory is invalid")
        for arm, carrier in carriers.items():
            require(carrier.get("text_file") in asset_names,
                    f"{record.get('variant_id')}/{arm} text carrier is unbound")
            pages = carrier.get("pages")
            require(isinstance(pages, list) and all(path in asset_names for path in pages),
                    f"{record.get('variant_id')}/{arm} page carrier is unbound")
    for record in manifest["active"]:
        require(record.get("carrier_file") in asset_names,
                f"{record.get('variant_id')} active carrier index is unbound")
        visible = _load_json(root / record["carrier_file"], "active sentinel carrier")
        require(visible.get("variant_id") == record.get("variant_id"),
                f"{record.get('variant_id')} active carrier ID drift")
        require([row.get("start_state_id") for row in visible.get("probe_pool") or []]
                == record.get("probe_pool"),
                f"{record.get('variant_id')} active probe-pool binding drift")
        probe_pool = visible.get("probe_pool") or []
        observations = visible.get("probe_observations") or {}
        require(len(probe_pool) == 3
                and len(set(record["probe_pool"])) == 3
                and set(observations) == set(record["probe_pool"]),
                f"{record.get('variant_id')} must expose exactly three unique probes")
        carrier_parent = Path(record["carrier_file"]).parent
        require(str(Path("assets") / visible["initial_text_file"]) in asset_names,
                f"{record.get('variant_id')} active ledger is unbound")
        for name in visible.get("initial_pages") or []:
            require(str(carrier_parent / name) in asset_names,
                    f"{record.get('variant_id')} active initial page is unbound")
        for candidate in probe_pool:
            state_id = candidate["start_state_id"]
            observation = observations[state_id]
            require(candidate.get("action") == observation.get("action"),
                    f"{record.get('variant_id')}/{state_id} action binding drift")
            require(str(carrier_parent / candidate["prefix_page"]) in asset_names,
                    f"{record.get('variant_id')}/{state_id} prefix page is unbound")
            for name in observation.get("result_pages") or []:
                require(str(carrier_parent / name) in asset_names,
                        f"{record.get('variant_id')}/{state_id} result page is unbound")
    return manifest


def _load_json(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"missing {label}: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read {label} {path}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _validate_served_inputs(
    trace_doc: dict[str, Any], expected_messages: list[dict[str, Any]],
    expected_images: list[Path], label: str,
) -> None:
    """Re-derive a sentinel call's visible prompt and image inventory."""
    from PIL import Image

    require(trace_doc.get("messages") == expected_messages,
            f"{label} messages differ from the generated source-blind carrier")
    message_sha = hashlib.sha256(json.dumps(
        expected_messages, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    require(trace_doc.get("messages_sha256") == message_sha,
            f"{label} message digest differs from the visible carrier")
    images = trace_doc.get("images")
    require(isinstance(images, list) and len(images) == len(expected_images),
            f"{label} image inventory differs from the visible carrier")
    for index, (actual, expected) in enumerate(zip(images, expected_images)):
        expected = expected.resolve()
        require(expected.is_file(), f"{label} expected image[{index}] is absent")
        with Image.open(expected) as opened:
            expected_size = [opened.width, opened.height]
        require(isinstance(actual, dict)
                and Path(str(actual.get("path", ""))).resolve() == expected
                and actual.get("sha256") == sha256_file(expected)
                and actual.get("source_size") == expected_size
                and actual.get("processed_size") == expected_size,
                f"{label} image[{index}] differs from its frozen carrier asset")


def _call_binding(run_dir: Path, tag: str, record: dict[str, Any],
                  payload: dict[str, Any] | None) -> dict[str, Any]:
    trace = Path(str(record.get("trace_path", "")))
    require(trace.is_file() and trace.parent.resolve() == run_dir.resolve(),
            f"serving trace was not written inside the run for {tag}")
    require(trace.name == f"{tag}.trace.json"
            and record.get("trace_sha256") == sha256_file(trace),
            f"serving trace receipt is stale for {tag}")
    return {
        "tag": tag,
        "trace_tag": record["trace_tag"],
        "round_index": record["round_index"],
        "round_kind": record["round_kind"],
        "seed": record["seed"],
        "sampler": record["sampler"],
        "reasoning_effort": record["reasoning_effort"],
        "preserve_thinking": record["preserve_thinking"],
        "serving_identity": record["serving_identity"],
        "max_tokens": record["max_tokens"],
        "native_context_tokens": record["native_context_tokens"],
        "completeness": record["completeness"],
        "completion_contains_close": record["completion_contains_close"],
        "payload_present": record["payload_present"],
        "schema_errors": record["schema_errors"],
        "messages_sha256": record["messages_sha256"],
        "prompt_sha256": record["prompt_sha256"],
        "visual_tokens": record["visual_tokens"],
        "images": record["images"],
        "image_grid_thw": record["image_grid_thw"],
        "expanded_prompt_tokens": record["expanded_prompt_tokens"],
        "derived_text_tokens": record["derived_text_tokens"],
        "input_text_token_cap": record["input_text_token_cap"],
        "prompt_tokens_match": record["prompt_tokens_match"],
        "token_accounting_match": record["token_accounting_match"],
        "stats": record["stats"],
        "wall_seconds": record["wall_seconds"],
        "finish_reason": record["finish_reason"],
        "trace": {"path": str(trace), "sha256": record["trace_sha256"]},
        "payload": payload,
    }


def _passive_turn(
    manifest_root: Path, manifest_record: dict[str, Any], fixture: dict[str, Any],
    arm: str,
) -> tuple[list[dict[str, Any]], list[Path]]:
    carrier = (manifest_record.get("carriers") or {}).get(arm)
    require(isinstance(carrier, dict),
            f"{fixture['variant_id']} lacks frozen {arm} carrier")
    text_path = manifest_root / carrier["text_file"]
    ledger = text_path.read_text(encoding="utf-8")
    items: list[dict[str, str]] = [{
        "type": "text",
        "text": sentinel_request(
            fixture,
            outcome_note=(
                "Sentinel outcome convention: completed=true is success and "
                "completed=false is failure. Infer the latent causal objective "
                "from this autonomous evidence."
            ),
        ),
    }, {"type": "text", "text": "== EXACT LEDGER ==\n" + ledger}]
    images: list[Path] = []
    pages = carrier.get("pages") or []
    labels = carrier.get("labels") or []
    require(len(pages) == len(labels), f"{arm} page/label inventory mismatch")
    for label, relative in zip(labels, pages):
        items.append({"type": "text", "text": label})
        items.append({"type": "image"})
        images.append(manifest_root / relative)
    return [{"role": "user", "content": items}], images


def _active_initial_turn(
    manifest_root: Path, manifest_record: dict[str, Any], fixture: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[Path], dict[str, Any]]:
    carrier_path = manifest_root / manifest_record["carrier_file"]
    carrier = _load_json(carrier_path, "active sentinel carrier")
    require(carrier.get("variant_id") == fixture["variant_id"],
            "active carrier variant binding mismatch")
    ledger = (manifest_root / "assets" / carrier["initial_text_file"]).read_text(
        encoding="utf-8"
    )
    items: list[dict[str, str]] = [{
        "type": "text",
        "text": sentinel_request(
            fixture,
            outcome_note=(
                "Sentinel outcome convention: completed=true is success and "
                "completed=false is failure. The initial evidence deliberately "
                "may underdetermine the objective. Preserve multiple live "
                "hypotheses and select exactly one listed legal probe using the "
                "next_probe object when discrimination is needed."
            ),
        ),
    }, {"type": "text", "text": "== EXACT LEDGER ==\n" + ledger}]
    images: list[Path] = []
    variant_root = carrier_path.parent
    for label, name in zip(carrier["initial_page_labels"], carrier["initial_pages"]):
        items.append({"type": "text", "text": label})
        items.append({"type": "image"})
        images.append(variant_root / name)
    items.append({
        "type": "text",
        "text": (
            "== LEGAL PROBE POOL ==\nOnly the exact start_state_id/action pairs "
            "listed below are legal. Requests are literal and are never repaired."
        ),
    })
    for candidate in carrier["probe_pool"]:
        items.append({
            "type": "text",
            "text": (
                f"Candidate {candidate['candidate']}: "
                f"start_state_id={candidate['start_state_id']} "
                f"action={json.dumps(candidate['action'], sort_keys=True)}"
            ),
        })
        items.append({"type": "image"})
        images.append(variant_root / candidate["prefix_page"])
    return [{"role": "user", "content": items}], images, carrier


def _active_probe_feedback(
    fixture: dict[str, Any], carrier: dict[str, Any],
    pre_payload: dict[str, Any] | None, carrier_path: Path,
) -> tuple[list[dict[str, str]], list[Path], dict[str, Any]]:
    request = (pre_payload or {}).get("next_probe") or {}
    start_state_id = request.get("start_state_id")
    action = request.get("action")
    candidate = next((row for row in carrier["probe_pool"]
                      if row["start_state_id"] == start_state_id), None)
    exact = candidate is not None and action == candidate["action"]
    if not exact:
        audit = {
            "accepted": False, "start_state_id": start_state_id,
            "action": action, "reason": "not an exact listed legal probe",
        }
        return ([{"type": "text", "text": (
            "PROBE REJECTED: the requested start_state_id/action pair was not an "
            "exact member of the legal pool. No observation was generated and "
            "the request was not repaired. Update from the evidence already shown."
        )}], [], audit)
    observation = carrier["probe_observations"][start_state_id]
    require(observation["action"] == action, "sealed active observation action drift")
    live = execute_active_probe(fixture, start_state_id, action)
    require(live is not None
            and live["completed"] == observation["completed"]
            and live["moved"] == observation["moved"]
            and sd.render_text_block(live["delta"]) == observation["delta_text"],
            "sealed active probe observation differs from state-machine replay")
    items: list[dict[str, str]] = [{
        "type": "text",
        "text": (
            "== EXACT LIVE PROBE RESULT ==\n"
            f"start_state_id={start_state_id} "
            f"action={json.dumps(action, sort_keys=True)} "
            f"moved={str(observation['moved']).lower()} "
            f"completed={str(observation['completed']).lower()}\n"
            f"{observation['delta_text']}\n\n"
            "Update your analysis. Answer with the same exact JSON schema on "
            "the last line."
        ),
    }]
    images: list[Path] = []
    for page_no, name in enumerate(observation["result_pages"], start=1):
        items.append({"type": "text", "text": f"Probe result page {page_no}:"})
        items.append({"type": "image"})
        images.append(carrier_path.parent / name)
    return items, images, {
        "accepted": True, "start_state_id": start_state_id, "action": action,
        "completed": observation["completed"], "moved": observation["moved"],
    }


def _expected_call_inventory(manifest: dict[str, Any]) -> set[tuple[str, str, str]]:
    expected = {
        (record["variant_id"], arm, "single")
        for record in manifest["passive"] for arm in PASSIVE_ARMS
    }
    expected.update({
        (record["variant_id"], ACTIVE_ARM, stage)
        for record in manifest["active"] for stage in ACTIVE_STAGES
    })
    require(len(expected) == TOTAL_GENERATIONS,
            "internal sentinel expected-call inventory is not exactly 15")
    return expected


def validate_sentinel_results_document(
    document: Any, *, manifest: dict[str, Any], manifest_sha256: str,
    frozen_manifest_sha256: str | None = None, require_decided: bool = False,
) -> dict[str, Any]:
    """Validate all 15 unique calls and derive threshold summaries from records."""
    import e2_probe_vlm as probe
    import s4_run as srun

    require(isinstance(document, dict), "sentinel results must be an object")
    require(document.get("format_version") == RESULT_FORMAT_VERSION
            and document.get("protocol_version") == PROTOCOL_VERSION,
            "sentinel results version mismatch")
    require(document.get("namespace") == manifest.get("namespace")
            and document.get("base_seed") == manifest.get("base_seed"),
            "sentinel results namespace/seed differs from manifest")
    require(type(document.get("answer_tokens")) is int
            and document["answer_tokens"] > 0,
            "sentinel results lack the exact answer-token budget")
    require(document.get("sentinel_manifest_sha256") == manifest_sha256,
            "sentinel results are not bound to the sentinel manifest bytes")
    run_dir = Path(str(document.get("run_dir", "")))
    require(run_dir.is_dir(), "sentinel results lack their serving run directory")
    if document.get("namespace") == "confirm":
        require(run_dir.resolve() == CONFIRM_RUN_DIR.resolve(),
                "confirm sentinel traces are outside the fixed append-only run")
        frozen_path = SEALED_R4 / "FROZEN.json"
        require(frozen_path.is_file(), "confirm sentinel results require FROZEN.json")
        frozen = _load_json(frozen_path, "r4 freeze")
        snapshot = frozen.get("serving_snapshot") or {}
        frozen_answer_tokens = (snapshot.get("budgets") or {}).get("answer_tokens")
        require(document["answer_tokens"] == srun.MAX_ANSWER_TOKENS
                and frozen_answer_tokens == srun.MAX_ANSWER_TOKENS,
                "confirm sentinel answer-token budget differs from frozen production "
                f"budget {srun.MAX_ANSWER_TOKENS}")
        expected_identity = {
            "checkpoint_sha256": (snapshot.get("checkpoint_fingerprint") or {}).get(
                "checkpoint_sha256"
            ),
            "verified_shards": True,
            "snapshot_sha256": snapshot.get("snapshot_sha256"),
        }
        require(document.get("serving_identity") == expected_identity,
                "confirm sentinel serving identity differs from FROZEN")
        require(document.get("frozen_manifest_sha256") == sha256_file(frozen_path),
                "confirm sentinel results bind a different FROZEN.json")
    if frozen_manifest_sha256 is not None:
        require(document.get("frozen_manifest_sha256") == frozen_manifest_sha256,
                "sentinel results are not bound to the exact freeze")
    calls = document.get("calls")
    require(isinstance(calls, list) and len(calls) == TOTAL_GENERATIONS,
            f"sentinel call inventory must contain exactly {TOTAL_GENERATIONS} calls")
    actual: set[tuple[str, str, str]] = set()
    tags: set[str] = set()
    calls_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    traces_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, call in enumerate(calls):
        require(isinstance(call, dict), f"sentinel call[{index}] must be an object")
        key = (call.get("variant_id"), call.get("carrier"), call.get("stage"))
        require(all(isinstance(item, str) for item in key),
                f"sentinel call[{index}] lacks a string inventory binding")
        require(key not in actual, f"duplicate sentinel call inventory member {key}")
        actual.add(key)
        calls_by_key[key] = call
        tag = call.get("tag")
        require(isinstance(tag, str) and tag not in tags,
                f"duplicate or invalid sentinel call tag {tag!r}")
        tags.add(tag)
        expected_seed = sentinel_call_seed(
            document["namespace"], key[0], key[1], key[2], document["base_seed"],
        )
        require(call.get("seed") == expected_seed,
                f"sentinel call {tag} seed differs from deterministic assignment")
        expected_round = 1 if key[2] == "post" else 0
        expected_round_kind = {
            "single": "sentinel_single",
            "pre": "sentinel_pre_probe",
            "post": "sentinel_post_probe",
        }[key[2]]
        require(call.get("sampler") == probe.PRODUCTION_SAMPLER
                and call.get("reasoning_effort") == probe.REASONING_EFFORT
                and call.get("preserve_thinking") is probe.PRESERVE_THINKING
                and call.get("native_context_tokens") == srun.NATIVE_CONTEXT_TOKENS
                and call.get("serving_identity") == document.get("serving_identity")
                and call.get("trace_tag") == tag
                and call.get("round_index") == expected_round
                and call.get("round_kind") == expected_round_kind,
                f"sentinel call {tag} differs from production sampler/effort")
        require(call.get("max_tokens") == document["answer_tokens"],
                f"sentinel call {tag} answer-token budget drift")
        text_cap = (srun.MAX_INITIAL_PROMPT_TEXT_TOKENS
                    if key[2] in {"single", "pre"}
                    else srun.MAX_CONTEXT_TEXT_TOKENS)
        require(call.get("input_text_token_cap") == text_cap
                and type(call.get("derived_text_tokens")) is int
                and call["derived_text_tokens"] <= text_cap,
                f"sentinel call {tag} text-token envelope drift")
        require(call.get("prompt_tokens_match") is True
                and call.get("token_accounting_match") is True,
                f"sentinel call {tag} token accounting did not pass")
        trace = call.get("trace") or {}
        trace_path = Path(str(trace.get("path", "")))
        require(trace_path.is_file() and trace_path.parent.resolve() == run_dir.resolve()
                and sha256_file(trace_path) == trace.get("sha256"),
                f"sentinel call {tag} trace binding is stale")
        trace_doc = _load_json(trace_path, f"sentinel serving trace {tag}")
        traces_by_key[key] = trace_doc
        exact_trace_fields = (
            "tag", "trace_tag", "round_index", "round_kind", "seed", "sampler",
            "reasoning_effort", "preserve_thinking", "serving_identity",
            "max_tokens", "native_context_tokens", "messages_sha256",
            "prompt_sha256", "visual_tokens", "images", "image_grid_thw",
            "expanded_prompt_tokens", "derived_text_tokens",
            "input_text_token_cap", "finish_reason", "prompt_tokens_match",
            "token_accounting_match", "completion_contains_close",
            "payload_present", "schema_errors", "completeness", "stats",
        )
        require(all(trace_doc.get(field) == call.get(field)
                    for field in exact_trace_fields),
                f"sentinel call {tag} metadata differs from its serving trace")
        messages = trace_doc.get("messages")
        require(isinstance(messages, list)
                and hashlib.sha256(json.dumps(
                    messages, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")).hexdigest() == call.get("messages_sha256"),
                f"sentinel call {tag} message receipt is inconsistent")
        raw = trace_doc.get("raw_response")
        require(isinstance(raw, str) and raw == trace_doc.get("raw"),
                f"sentinel call {tag} lacks an exact raw response")
        full = "<think>" + raw
        closed = "</think>" in full
        think = full.split("<think>", 1)[-1].split("</think>", 1)[0]
        answer = full.split("</think>", 1)[-1].strip() if closed else ""
        parsed = srun.extract_final_json(answer) if closed else None
        schema_errors = srun.validate_answer(parsed) if parsed is not None else []
        trace_payload = parsed if parsed is not None and not schema_errors else None
        stats = trace_doc.get("stats") or {}
        expected_completeness = probe.classify_completion(
            stats.get("finish_reason"), stats.get("generation_tokens"),
            trace_doc.get("max_tokens"), closed, parsed,
        )
        if expected_completeness == "complete" and schema_errors:
            expected_completeness = "malformed_schema"
        expanded = trace_doc.get("expanded_prompt_tokens")
        grids = trace_doc.get("image_grid_thw")
        require(type(expanded) is int
                and type(trace_doc.get("visual_tokens")) is int
                and type(trace_doc.get("derived_text_tokens")) is int
                and trace_doc["derived_text_tokens"]
                == expanded - trace_doc["visual_tokens"]
                and expanded + trace_doc["max_tokens"]
                <= srun.NATIVE_CONTEXT_TOKENS,
                f"sentinel call {tag} context/token derivation is inconsistent")
        require(isinstance(grids, list)
                and sum(int(t) * int(h) * int(w) // 4 for t, h, w in grids)
                == trace_doc.get("visual_tokens"),
                f"sentinel call {tag} visual-token derivation is inconsistent")
        require(trace_doc.get("completion_contains_close") is closed
                and trace_doc.get("think") == think
                and trace_doc.get("answer") == answer
                and trace_doc.get("parsed_payload") == parsed
                and trace_doc.get("schema_errors") == schema_errors
                and trace_doc.get("payload_present") is (trace_payload is not None)
                and trace_doc.get("completeness") == expected_completeness
                and trace_doc.get("assistant_history") == {
                    "role": "assistant", "content": answer,
                    "reasoning_content": think,
                }, f"sentinel call {tag} is not an exact projection of raw output")
        require(call.get("payload") == trace_payload,
                f"sentinel call {tag} payload differs from its serving trace")
    require(actual == _expected_call_inventory(manifest),
            "sentinel call inventory differs from the frozen 9-passive/6-active design")
    manifest_root = (SEALED_R4 / "fixtures/sentinels"
                     if document["namespace"] == "confirm" else DEV_ROOT)
    for index, manifest_record in enumerate(manifest["passive"]):
        fixture = build_passive_variant(
            document["namespace"], index, document["base_seed"],
        )
        for arm in PASSIVE_ARMS:
            expected_messages, expected_images = _passive_turn(
                manifest_root, manifest_record, fixture, arm,
            )
            key = (fixture["variant_id"], arm, "single")
            _validate_served_inputs(
                traces_by_key[key], expected_messages, expected_images,
                f"sentinel {key}",
            )
    active_input_audits: dict[str, dict[str, Any]] = {}
    for index, manifest_record in enumerate(manifest["active"]):
        fixture = build_active_variant(
            document["namespace"], index, document["base_seed"],
        )
        variant_id = fixture["variant_id"]
        messages, images, carrier = _active_initial_turn(
            manifest_root, manifest_record, fixture,
        )
        pre_key = (variant_id, ACTIVE_ARM, "pre")
        post_key = (variant_id, ACTIVE_ARM, "post")
        pre_trace = traces_by_key[pre_key]
        _validate_served_inputs(
            pre_trace, messages, images, f"sentinel {pre_key}",
        )
        feedback_items, feedback_images, probe_audit = _active_probe_feedback(
            fixture, carrier, calls_by_key[pre_key].get("payload"),
            manifest_root / manifest_record["carrier_file"],
        )
        post_messages = copy.deepcopy(messages)
        post_messages.append(copy.deepcopy(pre_trace["assistant_history"]))
        post_messages.append({"role": "user", "content": feedback_items})
        post_images = list(images) + list(feedback_images)
        _validate_served_inputs(
            traces_by_key[post_key], post_messages, post_images,
            f"sentinel {post_key}",
        )
        active_input_audits[variant_id] = probe_audit
    passive_ids = [record["variant_id"] for record in manifest["passive"]]
    active_ids = [record["variant_id"] for record in manifest["active"]]
    passive = aggregate_passive(
        document.get("passive_worksheets"), expected_variant_ids=passive_ids,
    )
    passive_index = {record["variant_id"]: index
                     for index, record in enumerate(manifest["passive"])}
    for arm in PASSIVE_ARMS:
        for sheet in document["passive_worksheets"][arm]:
            call = calls_by_key[(sheet["variant_id"], arm, "single")]
            require(sheet.get("call_tag") == call["tag"]
                    and sheet.get("payload") == call.get("payload"),
                    f"passive worksheet {arm}/{sheet['variant_id']} is not bound "
                    "to its serving call")
            fixture = build_passive_variant(
                document["namespace"], passive_index[sheet["variant_id"]],
                document["base_seed"],
            )
            expected_sheet = build_worksheet(
                fixture, call.get("payload"), stage="single", carrier=arm,
            )
            for key, expected_value in expected_sheet.items():
                if key.startswith("VERDICT_"):
                    continue
                require(sheet.get(key) == expected_value,
                        f"passive worksheet {arm}/{sheet['variant_id']} changed "
                        f"immutable field {key}")
    active = aggregate_active(
        document.get("active_records"), expected_variant_ids=active_ids,
    )
    active_index = {record["variant_id"]: index
                    for index, record in enumerate(manifest["active"])}
    for record in document["active_records"]:
        variant_id = record["variant_id"]
        pre_call = calls_by_key[(variant_id, ACTIVE_ARM, "pre")]
        post_call = calls_by_key[(variant_id, ACTIVE_ARM, "post")]
        require(record.get("pre_call_tag") == pre_call["tag"]
                and record.get("post_call_tag") == post_call["tag"]
                and record.get("pre_payload") == pre_call.get("payload")
                and record.get("post_payload") == post_call.get("payload"),
                f"active record {variant_id} is not bound to its two serving calls")
        fixture = build_active_variant(
            document["namespace"], active_index[variant_id], document["base_seed"],
        )
        require(record.get("interaction") == score_active_interaction(
            fixture, record.get("pre_payload"),
        ), f"active interaction score for {variant_id} was not mechanically derived")
        require(record.get("probe_audit") == active_input_audits[variant_id],
                f"active probe audit for {variant_id} differs from visible feedback")
        require(record["pre_worksheet"].get("model_best_goal") ==
                ((record.get("pre_payload") or {}).get("best_goal") or {}).get(
                    "plain_causal_condition"
                ), f"active pre worksheet {variant_id} differs from the model payload")
        require(record["final_worksheet"].get("model_best_goal") ==
                ((record.get("post_payload") or {}).get("best_goal") or {}).get(
                    "plain_causal_condition"
                ), f"active final worksheet {variant_id} differs from the model payload")
        expected_pre = build_worksheet(
            fixture, record.get("pre_payload"), stage="pre", carrier=ACTIVE_ARM,
        )
        expected_post = build_worksheet(
            fixture, record.get("post_payload"), stage="post", carrier=ACTIVE_ARM,
        )
        for actual, expected_sheet, label in (
            (record["pre_worksheet"], expected_pre, "pre"),
            (record["final_worksheet"], expected_post, "post"),
        ):
            for key, expected_value in expected_sheet.items():
                if key.startswith("VERDICT_"):
                    continue
                require(actual.get(key) == expected_value,
                        f"active {label} worksheet {variant_id} changed immutable "
                        f"field {key}")
    if require_decided:
        require(all(summary["undecided"] == 0 for summary in passive.values())
                and active["undecided"] == 0,
                "final sentinel results contain undecided semantic verdicts")
    return {"document": document, "passive": passive, "active": active}


def run_sentinels(*, namespace: str, base_seed: int, model: Path,
                  answer_tokens: int) -> tuple[dict[str, Any], Path]:
    """Execute the frozen 9 passive + 6 active production-serving calls once."""
    import e2_probe_vlm as probe
    import s4_run as srun

    sl.enforce_offline_scientific_run("s4_sentinels --run", [])
    manifest_root = (SEALED_R4 / "fixtures/sentinels" if namespace == "confirm"
                     else DEV_ROOT)
    manifest_path = manifest_root / "sentinel_manifest.json"
    manifest = verify_manifest(
        manifest_path, expected_namespace=namespace, expected_base_seed=base_seed,
        require_live_generator=True,
    )
    manifest_sha = sha256_file(manifest_path)
    frozen_sha: str | None = None
    if namespace == "confirm":
        frozen_path = SEALED_R4 / "FROZEN.json"
        frozen = _load_json(frozen_path, "r4 freeze")
        frozen_sha = sha256_file(frozen_path)
        confirm_assets = frozen.get("confirm_assets") or {}
        require(confirm_assets.get("sentinel_manifest_sha256") == manifest_sha,
                "frozen sentinel-manifest binding differs from sealed bytes")
        require(confirm_assets.get("sentinel_thresholds") == {
            "passive_variants": PASSIVE_VARIANTS,
            "active_variants": ACTIVE_VARIANTS,
            "pass_threshold": PASS_THRESHOLD,
            "total_generations": TOTAL_GENERATIONS,
        }, "frozen sentinel thresholds differ from executable thresholds")
        require(answer_tokens == srun.MAX_ANSWER_TOKENS
                and (frozen.get("serving_snapshot") or {}).get("budgets", {}).get(
                    "answer_tokens"
                ) == answer_tokens,
                "confirm sentinel answer-token budget differs from the freeze")
        require((frozen.get("serving_snapshot") or {}).get("request_prompt_sha256")
                == hashlib.sha256(srun.REQUEST.encode()).hexdigest(),
                "confirm sentinel request schema differs from the freeze")
        serving_identity = srun.verify_serving_snapshot(model, frozen["serving_snapshot"])
        run_dir = CONFIRM_RUN_DIR
        require(not run_dir.exists() and not CONFIRM_RAW_RESULTS.exists()
                and not CONFIRM_RESULTS.exists(),
                "confirm sentinels are append-only and have already started or finished")
    else:
        live = probe.fingerprint(model)
        serving_identity = {
            "checkpoint_sha256": live["checkpoint_sha256"],
            "verified_shards": True,
        }
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        run_dir = ROOT / f"logs/s4_sentinel_runs/{stamp}_{namespace}"
    vlm = probe.Vlm(model)
    run_dir.mkdir(parents=True, exist_ok=False)
    _atomic_create_json(run_dir / "STARTED.json", {
        "created_utc": _utc_now(), "namespace": namespace,
        "base_seed": base_seed, "sentinel_manifest_sha256": manifest_sha,
        "frozen_manifest_sha256": frozen_sha,
        "rule": "a confirm run is one-shot; interruption ends this frozen version",
    }, read_only=(namespace == "confirm"))
    passive_worksheets: dict[str, list[dict[str, Any]]] = {
        arm: [] for arm in PASSIVE_ARMS
    }
    active_records: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []

    for index, manifest_record in enumerate(manifest["passive"]):
        fixture = build_passive_variant(namespace, index, base_seed)
        require(fixture["variant_id"] == manifest_record["variant_id"],
                "passive generator/manifest variant drift")
        require(canonical_sha256(fixture["gold"]) == manifest_record["gold_sha256"],
                "passive generated gold differs from the sealed manifest")
        for arm in PASSIVE_ARMS:
            messages, images = _passive_turn(
                manifest_root, manifest_record, fixture, arm,
            )
            stage = "single"
            seed = sentinel_call_seed(namespace, fixture["variant_id"], arm,
                                      stage, base_seed)
            tag = f"sentinel_{fixture['variant_id']}_{arm.lower()}"
            record, payload, _answer = srun.ask_chat(
                vlm, messages, images, seed=seed, max_tokens=answer_tokens,
                max_input_text_tokens=srun.MAX_INITIAL_PROMPT_TEXT_TOKENS,
                run_dir=run_dir, tag=tag,
                ledger_module="s4_sentinels",
                ledger_purpose=f"goal sentinel passive {arm}",
                serving_identity=serving_identity,
                round_index=0, round_kind="sentinel_single",
            )
            binding = _call_binding(run_dir, tag, record, payload)
            binding.update({"variant_id": fixture["variant_id"],
                            "carrier": arm, "stage": stage})
            calls.append(binding)
            worksheet = build_worksheet(
                fixture, payload, stage=stage, carrier=arm,
            )
            worksheet["call_tag"] = tag
            worksheet["payload"] = payload
            passive_worksheets[arm].append(worksheet)

    for index, manifest_record in enumerate(manifest["active"]):
        fixture = build_active_variant(namespace, index, base_seed)
        variant_id = fixture["variant_id"]
        require(variant_id == manifest_record["variant_id"],
                "active generator/manifest variant drift")
        require(canonical_sha256(fixture["gold"]) == manifest_record["gold_sha256"],
                "active generated gold differs from the sealed manifest")
        messages, images, carrier = _active_initial_turn(
            manifest_root, manifest_record, fixture,
        )
        pre_seed = sentinel_call_seed(namespace, variant_id, ACTIVE_ARM, "pre", base_seed)
        pre_tag = f"sentinel_{variant_id}_p_pre"
        pre_record, pre_payload, pre_answer = srun.ask_chat(
            vlm, messages, images, seed=pre_seed, max_tokens=answer_tokens,
            max_input_text_tokens=srun.MAX_INITIAL_PROMPT_TEXT_TOKENS,
            run_dir=run_dir, tag=pre_tag,
            ledger_module="s4_sentinels",
            ledger_purpose="goal sentinel active pre-probe",
            serving_identity=serving_identity,
            round_index=0, round_kind="sentinel_pre_probe",
        )
        pre_binding = _call_binding(run_dir, pre_tag, pre_record, pre_payload)
        pre_binding.update({"variant_id": variant_id, "carrier": ACTIVE_ARM,
                            "stage": "pre"})
        calls.append(pre_binding)
        interaction = score_active_interaction(fixture, pre_payload)
        feedback_items, feedback_images, probe_audit = _active_probe_feedback(
            fixture, carrier, pre_payload,
            manifest_root / manifest_record["carrier_file"],
        )
        require(pre_record.get("assistant_history") == {
            "role": "assistant", "content": pre_answer,
            "reasoning_content": pre_record.get("think"),
        }, "active sentinel pre-probe assistant-history receipt is inconsistent")
        messages.append(copy.deepcopy(pre_record["assistant_history"]))
        messages.append({"role": "user", "content": feedback_items})
        images.extend(feedback_images)
        post_seed = sentinel_call_seed(namespace, variant_id, ACTIVE_ARM, "post", base_seed)
        post_tag = f"sentinel_{variant_id}_p_post"
        post_record, post_payload, _post_answer = srun.ask_chat(
            vlm, messages, images, seed=post_seed, max_tokens=answer_tokens,
            max_input_text_tokens=srun.MAX_CONTEXT_TEXT_TOKENS,
            run_dir=run_dir, tag=post_tag,
            ledger_module="s4_sentinels",
            ledger_purpose="goal sentinel active post-probe",
            serving_identity=serving_identity,
            round_index=1, round_kind="sentinel_post_probe",
        )
        post_binding = _call_binding(run_dir, post_tag, post_record, post_payload)
        post_binding.update({"variant_id": variant_id, "carrier": ACTIVE_ARM,
                             "stage": "post"})
        calls.append(post_binding)
        active_records.append({
            "variant_id": variant_id, "kind": "active", "carrier": ACTIVE_ARM,
            "stages": list(ACTIVE_STAGES),
            "pre_call_tag": pre_tag, "post_call_tag": post_tag,
            "pre_payload": pre_payload, "post_payload": post_payload,
            "interaction": interaction, "probe_audit": probe_audit,
            "pre_worksheet": build_worksheet(
                fixture, pre_payload, stage="pre", carrier=ACTIVE_ARM,
            ),
            "final_worksheet": build_worksheet(
                fixture, post_payload, stage="post", carrier=ACTIVE_ARM,
            ),
        })

    require(len(calls) == TOTAL_GENERATIONS,
            f"internal error: executed {len(calls)} sentinel calls, expected 15")
    result = {
        "format_version": RESULT_FORMAT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "created_utc": _utc_now(),
        "namespace": namespace,
        "base_seed": base_seed,
        "answer_tokens": answer_tokens,
        "frozen_manifest_sha256": frozen_sha,
        "sentinel_manifest_sha256": manifest_sha,
        "serving_identity": serving_identity,
        "run_dir": str(run_dir),
        "thresholds": manifest["thresholds"],
        "calls": calls,
        "passive_worksheets": passive_worksheets,
        "active_records": active_records,
        "adjudication_status": "PENDING",
        "rule": (
            "exactly 15 generations; no retry/repair. Semantic verdicts are "
            "merged once from a separately bound adjudication artifact."
        ),
    }
    if namespace == "confirm":
        for path in run_dir.iterdir():
            if path.is_file():
                path.chmod(0o444)
        run_dir.chmod(0o555)
    validate_sentinel_results_document(
        result, manifest=manifest, manifest_sha256=manifest_sha,
        frozen_manifest_sha256=frozen_sha,
    )
    out = CONFIRM_RAW_RESULTS if namespace == "confirm" else run_dir / "sentinel_raw_results.json"
    _atomic_create_json(out, result, read_only=(namespace == "confirm"))
    return result, out


def finalize_results(raw_path: Path, judgments_path: Path, out_path: Path) -> dict[str, Any]:
    """Merge semantic judgments without changing the append-only raw 15-call record."""
    raw = _load_json(raw_path, "raw sentinel results")
    manifest_path = ((SEALED_R4 / "fixtures/sentinels/sentinel_manifest.json")
                     if raw.get("namespace") == "confirm"
                     else DEV_ROOT / "sentinel_manifest.json")
    manifest = verify_manifest(
        manifest_path, expected_namespace=raw.get("namespace"),
        expected_base_seed=raw.get("base_seed"), require_live_generator=True,
    )
    manifest_sha = sha256_file(manifest_path)
    validate_sentinel_results_document(
        raw, manifest=manifest, manifest_sha256=manifest_sha,
        frozen_manifest_sha256=raw.get("frozen_manifest_sha256"),
    )
    judgments = _load_json(judgments_path, "sentinel judgments")
    required = {"adjudicator", "adjudicated_utc", "raw_results_sha256",
                "passive", "active"}
    require(required <= set(judgments),
            f"sentinel judgments missing {sorted(required - set(judgments))}")
    require(isinstance(judgments["adjudicator"], str)
            and judgments["adjudicator"].strip(), "judgments need an adjudicator")
    _parse_utc(judgments["adjudicated_utc"], "judgments adjudicated_utc")
    require(judgments["raw_results_sha256"] == sha256_file(raw_path),
            "judgments are not bound to the exact raw sentinel results")
    passive_ids = {record["variant_id"] for record in manifest["passive"]}
    active_ids = {record["variant_id"] for record in manifest["active"]}
    require(isinstance(judgments["passive"], dict)
            and set(judgments["passive"]) == set(PASSIVE_ARMS),
            "judgments passive arm inventory is incomplete")
    for arm in PASSIVE_ARMS:
        require(isinstance(judgments["passive"][arm], dict)
                and set(judgments["passive"][arm]) == passive_ids,
                f"judgments for {arm} differ from the passive manifest")
    require(isinstance(judgments["active"], dict)
            and set(judgments["active"]) == active_ids,
            "active judgment inventory differs from the manifest")

    finalized = json.loads(json.dumps(raw))
    for arm in PASSIVE_ARMS:
        by_id = {sheet["variant_id"]: sheet
                 for sheet in finalized["passive_worksheets"][arm]}
        for variant_id, verdict in judgments["passive"][arm].items():
            require(isinstance(verdict, dict)
                    and set(verdict) == {"goal_correct_in_kind", "constraints_by_item"},
                    f"invalid judgment schema for {arm}/{variant_id}")
            by_id[variant_id]["VERDICT_goal_correct_in_kind"] = \
                verdict["goal_correct_in_kind"]
            by_id[variant_id]["VERDICT_constraints_by_item"] = \
                verdict["constraints_by_item"]
    by_active = {record["variant_id"]: record for record in finalized["active_records"]}
    for variant_id, verdict in judgments["active"].items():
        require(isinstance(verdict, dict)
                and set(verdict) == {"goal_correct_in_kind", "constraints_by_item"},
                f"invalid active judgment schema for {variant_id}")
        worksheet = by_active[variant_id]["final_worksheet"]
        worksheet["VERDICT_goal_correct_in_kind"] = verdict["goal_correct_in_kind"]
        worksheet["VERDICT_constraints_by_item"] = verdict["constraints_by_item"]
    finalized["adjudication_status"] = "FINAL"
    finalized["adjudication"] = {
        "adjudicator": judgments["adjudicator"],
        "adjudicated_utc": judgments["adjudicated_utc"],
        "raw_results": {"path": str(raw_path), "sha256": sha256_file(raw_path)},
        "judgments": {"path": str(judgments_path), "sha256": sha256_file(judgments_path)},
    }
    finalized["created_utc"] = _utc_now()
    validated = validate_sentinel_results_document(
        finalized, manifest=manifest, manifest_sha256=manifest_sha,
        frozen_manifest_sha256=raw.get("frozen_manifest_sha256"),
        require_decided=True,
    )
    finalized["mechanical_summary"] = {
        "passive": validated["passive"], "active": validated["active"],
    }
    _atomic_create_json(out_path, finalized, read_only=(raw.get("namespace") == "confirm"))
    return finalized


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", choices=["dev", "confirm"], default="dev")
    parser.add_argument("--base-seed", type=int, default=4)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--generate", action="store_true")
    actions.add_argument("--run", action="store_true",
                         help="execute exactly 15 production-serving generations "
                              "(confirm requires FROZEN.json)")
    actions.add_argument("--finalize", action="store_true",
                         help="merge a separately hash-bound semantic judgment "
                              "artifact into the append-only raw results")
    parser.add_argument("--model", type=Path,
                        default=Path.home() / "models/mlx/Qwen3.8-27B-8bit")
    parser.add_argument("--answer-tokens", type=int, default=32_768)
    parser.add_argument("--raw-results", type=Path)
    parser.add_argument("--judgments", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sl.enforce_offline_scientific_run("s4_sentinels", sys.argv[1:])
    if args.generate:
        out_root = (DEV_ROOT if args.namespace == "dev"
                    else SEALED_R4 / "fixtures/sentinels")
        if args.namespace == "confirm":
            require(not (SEALED_R4 / "FROZEN.json").exists(),
                    "confirm sentinel assets must be generated before FROZEN.json")
            require(not CONFIRM_RUN_DIR.exists() and not CONFIRM_RAW_RESULTS.exists()
                    and not CONFIRM_RESULTS.exists(),
                    "confirm sentinel output already exists; assets are append-only")
        manifest = generate_all(args.namespace, args.base_seed, out_root)
        print(f"generated {len(manifest['passive'])} passive + "
              f"{len(manifest['active'])} active sentinel variants -> {out_root}")
        return 0
    if args.run:
        _result, out = run_sentinels(
            namespace=args.namespace, base_seed=args.base_seed, model=args.model,
            answer_tokens=args.answer_tokens,
        )
        print(f"executed exactly {TOTAL_GENERATIONS} sentinel generations -> {out}")
        print("semantic worksheets are pending; use --finalize with a bound judgment file")
        return 0
    require(args.raw_results is not None and args.judgments is not None,
            "--finalize requires --raw-results and --judgments")
    raw = _load_json(args.raw_results, "raw sentinel results")
    if raw.get("namespace") == "confirm":
        require(args.output is None or args.output.resolve() == CONFIRM_RESULTS.resolve(),
                f"confirm final results path is fixed at {CONFIRM_RESULTS}")
        out = CONFIRM_RESULTS
    else:
        out = args.output or args.raw_results.with_name("sentinel_results.json")
    finalize_results(args.raw_results, args.judgments, out)
    print(f"finalized sentinel results -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
