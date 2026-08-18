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
import datetime as _dt
import hashlib
import json
import sys
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

GRID = 24                   # sentinel boards are 24x24: small, fully legible
MOVE = 3                    # mover step (its own size), like the pilot games


def require(condition: Any, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical_sha256(value: Any) -> str:
    return sd.canonical_sha256(value)


def _nonce(seed_text: str, prefix: str, length: int = 6) -> str:
    return prefix + hashlib.sha256(seed_text.encode()).hexdigest()[:length]


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
            "constraint_0": near_miss_uncharged["name"],
            "constraint_1": near_miss_drained["name"],
        },
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
        "uncharged_near_b": _nonce(nonce_root + ":p1", "PR"),
        "charged_near_a": _nonce(nonce_root + ":p2", "PR"),
        "start": _nonce(nonce_root + ":p3", "PR"),
    }
    # Probe pool: replayable prefixes + one action each.  Exactly one probe
    # reaches B uncharged (discriminating G1 vs G2); the others are redundant.
    inverse = {tuple(v): k for k, v in layout["action_directions"].items()}
    prefix_to_b = _route(layout, ["zone_b"])           # from start, never touches A
    probes = {
        prefix_ids["uncharged_near_b"]: {
            "prefix_actions": prefix_to_b[:-1],
            "action": prefix_to_b[-1],
            "discriminating": True,
            "described": "replay a prefix that has visited no coloured zone and "
                         "ends adjacent to the target zone; perform the final "
                         "approach action",
        },
        prefix_ids["charged_near_a"]: {
            "prefix_actions": _route(layout, ["zone_a"]),
            "action": inverse[(0, 1)],
            "discriminating": False,
            "described": "replay a prefix that just entered the charging zone; "
                         "perform one further action",
        },
        prefix_ids["start"]: {
            "prefix_actions": [],
            "action": layout["unused_action"],
            "discriminating": False,
            "described": "replay the empty prefix; perform the never-used action",
        },
    }
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


def render_text_carrier(fixture: dict[str, Any]) -> str:
    """T carrier: exact boards + semantics-free delta records + action rows,
    in the packet's exact-text conventions."""
    import s4_packet as spk

    nonce_root = f"{fixture['namespace']}:{fixture['index']}:{fixture['variant_id']}"
    lines: list[str] = [
        "AUTONOMOUS OBSERVATION LEDGER [OBSERVED/DERIVED-EXACT only]",
    ]
    ordered = fixture["episodes"][fixture.get("chronology_offset", 0):] + \
        fixture["episodes"][: fixture.get("chronology_offset", 0)]
    for episode in ordered:
        eid = _nonce(nonce_root + episode["name"], "E")
        lines.append(f"episode {eid}: {len(episode['rows'])} transitions")
        boards = [episode["rows"][0]["pre"]] + [row["post"] for row in episode["rows"]]
        frame_ids = [_nonce(nonce_root + episode["name"] + str(i), "F")
                     for i in range(len(boards))]
        for row_index, row in enumerate(episode["rows"]):
            lines.append(
                f"  {frame_ids[row_index]} -{row['action']}-> "
                f"{frame_ids[row_index + 1]} completed={row['completed']} [OBSERVED]"
            )
        lines.append(f"  first board {frame_ids[0]}: {spk._grid_rle(boards[0])}")
        lines.append(f"  final board {frame_ids[-1]}: {spk._grid_rle(boards[-1])}")
        record = sd.sequence_record(
            frame_ids, boards, binding={"eid": eid, "kind": "episode"},
        )
        lines.append(sd.render_text_block(record))
    return "\n".join(lines)


def render_page_carrier(fixture: dict[str, Any], carrier: str,
                        work: Path) -> tuple[list[Path], list[str]]:
    """V/O carriers: page images through the real renderer at carrier floors."""
    require(carrier in {"raw", "overlay"}, f"unknown carrier {carrier!r}")
    nonce_root = f"{fixture['namespace']}:{fixture['index']}:{fixture['variant_id']}"
    pages: list[tuple[str, Any]] = []
    first_board = np.asarray(fixture["episodes"][0]["rows"][0]["pre"], dtype=np.uint8)
    pages.append(("opening_8px", sr.render_board(first_board, cell_px=8)))
    ordered = fixture["episodes"][fixture.get("chronology_offset", 0):] + \
        fixture["episodes"][: fixture.get("chronology_offset", 0)]
    for episode in ordered[:5]:
        frames = [np.asarray(episode["rows"][0]["pre"], dtype=np.uint8)] + [
            np.asarray(row["post"], dtype=np.uint8) for row in episode["rows"]
        ]
        label = _nonce(nonce_root + episode["name"], "E")
        pages.append((f"{label}_storyboard",
                      sr.storyboard(frames, cols=min(6, len(frames)), cell_px=8)))
        if carrier == "overlay":
            pre = frames[-2]
            post = frames[-1]
            pages.append((f"{label}_diff", sr.render_diff_mask(pre, post, cell_px=8)))
    labels = []
    paths = []
    for page_no, (name, plate) in enumerate(pages, start=1):
        path = plate.save(work / f"{fixture['variant_id']}_{carrier}_p{page_no:02d}.png")
        paths.append(path)
        labels.append(f"Page {page_no} of {len(pages)}: {name}")
    return paths, labels


def sentinel_request(fixture: dict[str, Any], *, outcome_note: str) -> str:
    """The pilot's exact answer contract, with completed flags as the outcomes."""
    import s4_run as srun

    return (
        f"{outcome_note}\n\n" + srun.REQUEST
    )


# ----------------------------------------------------------------- scoring


def score_active_interaction(fixture: dict[str, Any],
                             pre_payload: dict[str, Any] | None) -> dict[str, Any]:
    """Mechanical: did the pre-probe answer request the discriminating probe
    while keeping more than one live hypothesis?"""
    if pre_payload is None:
        return {"valid_discriminating_interaction": False,
                "reason": "no schema-valid pre-probe answer"}
    request = pre_payload.get("probe_request") or {}
    requested = request.get("prefix")
    discriminating = fixture["gold"]["discriminating_probe"]
    hypotheses = pre_payload.get("hypotheses") or []
    live = [h for h in hypotheses
            if isinstance(h, dict) and (h.get("probability") or 0) >= 0.1]
    return {
        "requested_prefix": requested,
        "discriminating_prefix": discriminating,
        "kept_ambiguity": len(live) >= 2,
        "valid_discriminating_interaction": (
            requested == discriminating and len(live) >= 2
        ),
    }


def build_worksheet(fixture: dict[str, Any], payload: dict[str, Any] | None,
                    *, stage: str) -> dict[str, Any]:
    """Adjudication worksheet in the grader's style: sealed gold constraints
    against the model's stated goal; VERDICT slots empty; aggregation mechanical.
    No constraint may be credited from a partial or correlated description."""
    gold = fixture["gold"]
    answer = payload or {}
    return {
        "variant_id": fixture["variant_id"], "kind": fixture["kind"], "stage": stage,
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


def aggregate_passive(worksheets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Mechanical aggregation once verdicts are filled: >=2/3 complete variants
    per arm.  A worksheet with any unfilled verdict keeps its arm undecided."""
    summary: dict[str, Any] = {}
    for arm, sheets in worksheets.items():
        complete = 0
        undecided = 0
        for sheet in sheets:
            verdicts = [sheet.get("VERDICT_goal_correct_in_kind")] + list(
                sheet.get("VERDICT_constraints_by_item") or [])
            if any(v is None for v in verdicts):
                undecided += 1
            elif all(v is True for v in verdicts):
                complete += 1
        summary[arm] = {
            "variants": len(sheets), "complete_objective": complete,
            "undecided": undecided,
            "pass": complete >= PASS_THRESHOLD and undecided == 0,
        }
    return summary


def aggregate_active(records: list[dict[str, Any]]) -> dict[str, Any]:
    finals = sum(1 for record in records if record.get("final_goal_pass") is True)
    undecided = sum(1 for record in records if record.get("final_goal_pass") is None)
    interactions = sum(
        1 for record in records
        if record.get("interaction", {}).get("valid_discriminating_interaction")
    )
    return {
        "variants": len(records),
        "final_goal_passes": finals,
        "valid_discriminating_interactions": interactions,
        "undecided": undecided,
        "pass": (finals >= PASS_THRESHOLD and interactions >= PASS_THRESHOLD
                 and undecided == 0),
    }


def validate_adequacy_attestation(value: Any) -> dict[str, Any]:
    """The independent, source-blind reviewer's record.  The pinned same-model
    descriptive comparator is not an independent adequacy ceiling."""
    require(isinstance(value, dict), "adequacy attestation must be an object")
    required = {"reviewer", "reviewer_kind", "method", "per_variant", "verdict",
                "attested_utc"}
    missing = required - set(value)
    require(not missing, f"adequacy attestation missing {sorted(missing)}")
    require(value["reviewer_kind"] in {"human", "independent_model"},
            "adequacy reviewer must be a human or an INDEPENDENT model")
    require(value["reviewer_kind"] != "independent_model"
            or value.get("model_identity_differs_from_pinned") is True,
            "an independent-model reviewer must attest a different model identity")
    per_variant = value["per_variant"]
    require(isinstance(per_variant, dict) and per_variant,
            "adequacy attestation needs per-variant records")
    for variant_id, record in per_variant.items():
        require(isinstance(record, dict)
                and record.get("recovered_goal")
                and type(record.get("evidence_sufficient")) is bool,
                f"adequacy record for {variant_id} is incomplete")
    require(value["verdict"] in {"adequate", "inadequate"},
            "adequacy verdict must be adequate|inadequate")
    return value


def generate_all(namespace: str, base_seed: int, out_root: Path) -> dict[str, Any]:
    """Build every sentinel fixture, verify machine/gold agreement, seal assets
    and gold SEPARATELY, and return the manifest (hashes only)."""
    assets_root = out_root / "assets"
    gold_root = out_root / "gold"
    assets_root.mkdir(parents=True, exist_ok=True)
    gold_root.mkdir(parents=True, exist_ok=True)
    generator_hash = sd.canonical_sha256(Path(__file__).read_text())
    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION, "protocol_version": PROTOCOL_VERSION,
        "namespace": namespace, "base_seed": base_seed,
        "generator_sha256": generator_hash,
        "total_generations_budget": TOTAL_GENERATIONS,
        "passive": [], "active": [],
    }
    for index in range(PASSIVE_VARIANTS):
        fixture = build_passive_variant(namespace, index, base_seed)
        text = render_text_carrier(fixture)
        (assets_root / f"{fixture['variant_id']}_text.txt").write_text(text)
        work = assets_root / fixture["variant_id"]
        work.mkdir(exist_ok=True)
        for carrier in ("raw", "overlay"):
            render_page_carrier(fixture, carrier, work)
        gold_path = gold_root / f"{fixture['variant_id']}.json"
        gold_path.write_text(json.dumps(fixture["gold"], indent=1, sort_keys=True))
        manifest["passive"].append({
            "variant_id": fixture["variant_id"],
            "gold_sha256": sd.canonical_sha256(fixture["gold"]),
            "text_sha256": sd.canonical_sha256(text),
        })
    for index in range(ACTIVE_VARIANTS):
        fixture = build_active_variant(namespace, index, base_seed)
        gold_path = gold_root / f"{fixture['variant_id']}.json"
        gold_path.write_text(json.dumps(fixture["gold"], indent=1, sort_keys=True))
        manifest["active"].append({
            "variant_id": fixture["variant_id"],
            "gold_sha256": sd.canonical_sha256(fixture["gold"]),
            "probe_pool": sorted(fixture["probes"]),
        })
    path = out_root / "sentinel_manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", choices=["dev", "confirm"], default="dev")
    parser.add_argument("--base-seed", type=int, default=4)
    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--run", action="store_true",
                        help="execute the 15 sentinel generations (requires "
                             "FROZEN.json for the confirm namespace)")
    args = parser.parse_args()
    sl.enforce_offline_scientific_run("s4_sentinels", sys.argv[1:])
    if args.generate:
        out_root = (DEV_ROOT if args.namespace == "dev"
                    else SEALED_R4 / "fixtures/sentinels")
        manifest = generate_all(args.namespace, args.base_seed, out_root)
        print(f"generated {len(manifest['passive'])} passive + "
              f"{len(manifest['active'])} active sentinel variants -> {out_root}")
        return 0
    if args.run:
        require(args.namespace == "dev" or (SEALED_R4 / "FROZEN.json").is_file(),
                "confirm-namespace sentinel runs require the sealed FROZEN.json")
        raise RuntimeError(
            "sentinel model execution is implemented behind the freeze; it is "
            "not authorized in this build-only revision"
        )
    parser.error("pass --generate or --run")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
