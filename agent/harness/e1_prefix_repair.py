#!/usr/bin/env python3
"""E1 prefix repair — replace the store's COMPOSED prefixes with WALKED paths.

`notes/e1-prefix-repair.md`. Zero model calls. Read-only with respect to
`logs/e1_store_v2/`, which is frozen and never opened for writing here.

THE DEFECT AND WHY THIS FIXES IT
--------------------------------
`e1_explorer.Explorer.observe` records `prefix[new] = prefix[source] + [action]` — a route
COMPOSED out of edges that were observed at different moments. On a game with latent state
that is a claim nobody tested, and the audit (`logs/e1_prefix_audit.json`) measured the
damage: 14 of 24 stores do not fully replay their own prefixes, 9 of them catastrophically
(sub-6% verified).

The explorer is deterministic, and the instrumented rerun in `e2_hidden_state.py` reproduces
every store's transition log byte-for-byte in all 24 games while additionally logging every
`perform()` — routing actions and RESETs included — to
`logs/e2_hidden_state_rerun/{game}.performs.jsonl`. That log is a record of what was actually
EXECUTED, so the true route to any state is recoverable from it: for the state's first
observation, the actions since the last RESET. No composition anywhere.

THE ANCHOR, AND WHY IT IS A RESET THAT LANDED ON THE ORIGIN
-----------------------------------------------------------
A walked path is only a usable ROUTE if its starting point can be re-created from a fresh
game. `RESET` is the only such point, and the audit checked per game that RESET restores the
stored origin in all 24 (`reset_restores_origin`). But RESET in ARC-AGI-3 restores the
LEVEL, not the game: once a level is cleared, RESET lands on the next level's start and not
on the origin. So the anchor here is specifically *a RESET whose observed post digest is the
origin*, taken from the rerun log rather than assumed. Actions executed while no such anchor
is in force are not routable from a fresh game and the states they discovered are reported as
uncovered with that reason — never given a route that would silently be wrong.

Deliberately NOT used as an anchor: a non-RESET action that happens to land back on the
origin DIGEST. Treating a board as a state is the exact fallacy that produced the composed
prefixes; it is not reintroduced here to shave a few actions.

TWO VALIDATIONS, BOTH REPORTED
------------------------------
  trajectory  per episode, one fresh `new_game()`, RESET, then the episode's actions replayed
              in order with the digest checked at EVERY position. This covers 100% of the
              walked paths rather than a sample, because a walked path is by construction a
              prefix of its episode. It is the cheaper test and the complete one.
  sample      the note's acceptance test, and the stricter one: a fresh `new_game()` PER
              STATE, so it also rules out any cross-replay contamination the trajectory pass
              would share. >= 12 states per game stratified by walked depth, plus every state
              in the audit's `shallowest_failures`.

A walked-path replay failure is not a skip and not a caveat: it would mean the engine is not
deterministic under the one operation this whole line assumes, so it is reported per state
and surfaced in the summary.

SHORT ROUTES (`--stage all` covers this; clean games only)
----------------------------------------------------------
On the 13 games the audit verified at >= 95%, a BFS over the store's own non-conflicted edges
proposes a shorter route per state. Every proposal is EXECUTED and checked before it is
recorded, so a `short` route is never a composed claim — it is a composed *guess* that then
had to walk. On the nine rotten games no edge is chained at all: the audit measured 0 of 70
such routes landing there.

Run:
  .venv/bin/python agent/harness/e1_prefix_repair.py --jobs 8
  .venv/bin/python agent/harness/e1_prefix_repair.py --games m0r0 --stage extract
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v2"                    # frozen; opened read-only
RERUN = ROOT / "logs/e2_hidden_state_rerun"
MAPS = ROOT / "logs/e1_prefix_v2"                    # gitignored per-state sidecars
AUDIT = ROOT / "logs/e1_prefix_audit.json"
OUTPUT = ROOT / "logs/e1_prefix_repair.json"
FORMAT_VERSION = 1

SAMPLE_STATES = 12          # (w) the note's floor; strata are drawn over walked depth
SAMPLE_SEED = 11            # (w) never 20260804 (the reserved draw seed)
CLEAN_THRESHOLD = 0.95      # (w) audit verified_rate at or above which edges may be chained
RESET_ACTION = [0, None, None]


def _hash(grid: list) -> str:
    """`e1_explorer._hash` at level 1 — the level is never mutated in E1."""
    return hashlib.sha256(
        json.dumps([1, grid], separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _games() -> list[str]:
    return sorted(path.name.split(".")[0] for path in STORE.glob("*.graph.json"))


def _load(game: str) -> tuple[dict, dict]:
    return (
        json.loads((STORE / f"{game}.graph.json").read_text()),
        json.loads((STORE / f"{game}.states.json").read_text()),
    )


def _performs(game: str) -> list[dict]:
    path = RERUN / f"{game}.performs.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# ======================================================================================
# Gate — the rerun must be the store, byte for byte
# ======================================================================================


def gate(game: str) -> dict[str, Any]:
    """The same gate `e2_hidden_state.rerun` applies, re-checked here on the artifacts.

    Nothing downstream may run on a game whose sidecar is not the store's own trajectory. A
    mismatch is a stop-and-report: the sidecar would be describing a different run than the
    store the prefixes belong to, and every route derived from it would be fiction.
    """
    stored = (STORE / f"{game}.transitions.jsonl").read_bytes()
    sidecar = RERUN / f"{game}.transitions.jsonl"
    performs = RERUN / f"{game}.performs.jsonl"
    if not sidecar.exists() or not performs.exists():
        return {"passed": False, "reason": "sidecar missing", "sidecar": str(sidecar)}
    fresh = sidecar.read_bytes()
    rows = _performs(game)
    indices = [row["index"] for row in rows]
    return {
        "passed": bool(fresh == stored and indices == list(range(1, len(rows) + 1))),
        "transitions_bytes_identical": fresh == stored,
        "stored_bytes": len(stored),
        "rerun_bytes": len(fresh),
        "performs_rows": len(rows),
        "performs_indices_contiguous": indices == list(range(1, len(rows) + 1)),
    }


# ======================================================================================
# Step 2 — extract the walked prefixes
# ======================================================================================


def extract(game: str) -> dict[str, Any]:
    """Per state, the actions since the last origin-restoring RESET at its FIRST observation.

    One pass over the rerun's `performs` log. `anchor` is the index of the RESET currently in
    force; `path` is what has been executed since. A state is covered the first time it
    appears as a `post` while an anchor is in force — first, not shortest, because the first
    observation is the one whose route is a plain suffix of a single uninterrupted episode.
    """
    graph, states = _load(game)
    origin = graph["origin"]
    composed = graph["prefix"]
    rows = _performs(game)

    walked: dict[str, list] = {}
    first_index: dict[str, int] = {}
    anchor_of: dict[str, int] = {}
    episodes: dict[int, list] = {}          # anchor index -> executed actions after it
    unanchored_states: set[str] = set()

    anchor: int | None = None
    path: list = []
    reset_rows = 0
    reset_to_origin = 0
    for row in rows:
        action = row["action"]
        post = row["post"]
        if action[0] == 0:
            reset_rows += 1
            if post == origin:
                reset_to_origin += 1
                anchor = row["index"]
                path = []
                episodes[anchor] = []
            else:
                # RESET landed somewhere else (a cleared level): nothing after this point is
                # routable from a fresh game until another RESET restores the origin.
                anchor = None
                path = []
            if post is not None and anchor is not None and post not in walked:
                walked[post] = []
                first_index[post] = row["index"]
                anchor_of[post] = anchor
            continue
        if anchor is None:
            if post is not None and post not in walked:
                unanchored_states.add(post)
            continue
        path.append(action)
        episodes[anchor].append(action)
        if post is not None and post not in walked:
            walked[post] = list(path)
            first_index[post] = row["index"]
            anchor_of[post] = anchor

    known = set(states)
    covered = sorted(known & set(walked))
    uncovered = sorted(known - set(walked))

    lengths = [len(walked[d]) for d in covered]
    old_lengths = [len(composed[d]) for d in covered if d in composed]
    paired = [
        (len(walked[d]), len(composed[d])) for d in covered if d in composed
    ]
    return {
        "game": game,
        "origin": origin,
        "store_states": len(known),
        "covered": len(covered),
        "uncovered": len(uncovered),
        "uncovered_states": uncovered[:20],
        "uncovered_seen_only_while_unanchored": len(
            known & unanchored_states - set(walked)
        ),
        "resets": reset_rows,
        "resets_restoring_origin": reset_to_origin,
        "episodes": len(episodes),
        "length_stats": _length_stats(lengths, old_lengths, paired),
        # not serialised into the summary; consumed by the sidecar writer and the validators
        "_walked": {d: walked[d] for d in covered},
        "_first_index": {d: first_index[d] for d in covered},
        "_anchor": {d: anchor_of[d] for d in covered},
        "_episodes": episodes,
        "_composed": {d: composed[d] for d in covered if d in composed},
    }


def _length_stats(walked: list[int], old: list[int], paired: list[tuple]) -> dict[str, Any]:
    """Walked routes are longer than composed ones — that is the price of correctness, so it
    is quantified rather than mentioned. `ratio_mean` is over states with a composed prefix of
    non-zero length; the origin (length 0 on both sides) would otherwise divide by zero."""
    def block(values: list[int]) -> dict[str, Any]:
        if not values:
            return {"n": 0}
        return {
            "n": len(values),
            "mean": round(statistics.mean(values), 2),
            "median": statistics.median(values),
            "p90": sorted(values)[int(0.9 * (len(values) - 1))],
            "max": max(values),
        }

    ratios = [w / o for w, o in paired if o]
    return {
        "walked": block(walked),
        "composed": block(old),
        "walked_longer": sum(1 for w, o in paired if w > o),
        "walked_equal": sum(1 for w, o in paired if w == o),
        "walked_shorter": sum(1 for w, o in paired if w < o),
        "ratio_mean": round(statistics.mean(ratios), 3) if ratios else None,
        "ratio_median": round(statistics.median(ratios), 3) if ratios else None,
        "ratio_max": round(max(ratios), 2) if ratios else None,
    }


# ======================================================================================
# Step 3 — validation by fresh replay
# ======================================================================================


class Engine:
    """A fresh-game driver. `new()` per episode or per state; never shared across a claim."""

    def __init__(self, game: str):
        from arcengine import ActionInput, GameAction  # noqa: PLC0415
        from gi2_replay import ReplayDriver, _plain_frames  # noqa: PLC0415

        self._input = ActionInput
        self._action = GameAction
        self._frames = _plain_frames
        self.driver = ReplayDriver(game)
        self.steps = 0

    def new(self):
        return self.driver.new_game()

    def step(self, handle, action) -> list | None:
        action_id, row, col = action
        response = self.driver.perform(
            handle,
            self._input(
                id=self._action.from_id(action_id),
                data={} if row is None else {"y": row, "x": col},
            ),
        )
        self.steps += 1
        frames = self._frames(response.frame or [])
        return frames[-1] if frames else None

    def route(self, path: list) -> list | None:
        """`new_game(); RESET; path` — the route as a consumer would execute it."""
        handle = self.new()
        grid = self.step(handle, RESET_ACTION)
        for action in path:
            grid = self.step(handle, action)
            if grid is None:
                return None
        return grid


def validate_trajectory(game: str, data: dict, engine: Engine) -> dict[str, Any]:
    """Replay every episode from a fresh game and check the digest at every position.

    A walked path is a prefix of exactly one episode, so replaying the episode validates every
    route derived from it at once. The check is per position, not only at the states that
    happen to be stored, which makes the first divergence — if there is one — locatable.
    """
    _, states = _load(game)
    rows = {row["index"]: row for row in _performs(game)}
    by_anchor: dict[int, list[str]] = defaultdict(list)
    for digest, anchor in data["_anchor"].items():
        by_anchor[anchor].append(digest)

    checked = matched = 0
    states_ok = 0
    failures: list[dict[str, Any]] = []
    for anchor, actions in sorted(data["_episodes"].items()):
        if not by_anchor.get(anchor):
            continue
        expected_at = {len(data["_walked"][d]): d for d in by_anchor[anchor]}
        handle = engine.new()
        grid = engine.step(handle, RESET_ACTION)
        position = 0
        diverged = False
        # the anchor state itself: walked path of length 0, checked on the RESET's own frame
        anchor_digest = expected_at.get(0)
        if anchor_digest is not None:
            checked += 1
            if grid is not None and _hash(grid) == rows[anchor]["post"]:
                matched += 1
            if grid is not None and grid == states[anchor_digest]:
                states_ok += 1
        for action in actions:
            grid = engine.step(handle, action)
            position += 1
            index = anchor + position
            row = rows.get(index)
            if row is None:
                break
            checked += 1
            got = _hash(grid) if grid is not None else None
            if got == row["post"]:
                matched += 1
            elif not diverged:
                diverged = True
                failures.append(
                    {
                        "episode_anchor": anchor,
                        "position": position,
                        "expected_post": row["post"],
                        "landed_on": got,
                    }
                )
            digest = expected_at.get(position)
            if digest is not None and grid is not None and grid == states[digest]:
                states_ok += 1
    total = len(data["_walked"])
    return {
        "positions_checked": checked,
        "positions_matched": matched,
        "position_match_rate": round(matched / checked, 6) if checked else None,
        "states_covered": total,
        "states_grid_verified": states_ok,
        "states_verified_rate": round(states_ok / total, 6) if total else None,
        "episodes_replayed": sum(1 for a in data["_episodes"] if by_anchor.get(a)),
        "first_divergences": failures[:10],
        "episodes_with_divergence": len(failures),
    }


def validate_sample(game: str, data: dict, engine: Engine, audit: dict) -> dict[str, Any]:
    """The note's acceptance test: a fresh engine PER STATE, one route each.

    Stratified by walked depth so a pass is not a pass on the shallow states only, and forced
    to include every state the audit named in `shallowest_failures` — the composed prefixes
    that broke earliest are the ones a repair has to be shown to fix.
    """
    _, states = _load(game)
    walked = data["_walked"]
    ordered = sorted(walked, key=lambda d: (len(walked[d]), d))
    strata = SAMPLE_STATES
    picked: list[str] = []
    if ordered:
        rng = random.Random(SAMPLE_SEED)
        size = max(1, len(ordered) // strata)
        for start in range(0, len(ordered), size):
            block = ordered[start:start + size]
            picked.append(rng.choice(block))
    forced = [
        row["state"]
        for row in audit.get("games", {}).get(game, {}).get("shallowest_failures", [])
    ]
    forced_covered = [d for d in forced if d in walked]
    sample = sorted(set(picked) | set(forced_covered))

    passed: list[str] = []
    failures: list[dict[str, Any]] = []
    for digest in sample:
        grid = engine.route(walked[digest])
        if grid is not None and grid == states[digest]:
            passed.append(digest)
        else:
            failures.append(
                {
                    "state": digest,
                    "walked_actions": len(walked[digest]),
                    "landed_on": _hash(grid) if grid is not None else None,
                }
            )
    return {
        "sampled": len(sample),
        "stratified_draws": len(set(picked)),
        "audit_shallowest_failures": len(forced),
        "audit_shallowest_failures_covered": len(forced_covered),
        "audit_shallowest_failures_passed": sum(
            1 for d in forced_covered if d in passed
        ),
        "passed": len(passed),
        "rate": round(len(passed) / len(sample), 4) if sample else None,
        "failures": failures[:10],
        "depths_sampled": sorted({len(walked[d]) for d in sample}),
    }


# ======================================================================================
# Step 4 — BFS-shortened routes, clean games only, verified before recorded
# ======================================================================================


def shorten(game: str, data: dict, engine: Engine) -> dict[str, Any]:
    """Shortest route over the store's non-conflicted edges, then EXECUTED to be believed.

    Composition is what broke the prefixes, so a composed route is treated here as nothing
    more than a proposal: it is recorded only if a fresh `RESET + route` lands on the stored
    grid. Attempted only where the audit already measured the store's edges to be reliable —
    on the nine rotten games this search produces garbage (the audit walked 110 such routes:
    0 of 70 landed in the sub-6% games) and it is not run at all.
    """
    graph, states = _load(game)
    origin = graph["origin"]
    walked = data["_walked"]
    conflicted = {(source, tuple(action)) for source, action in graph["conflicted"]}
    suspect = set(graph["suspect"])

    adjacency: dict[str, list[tuple]] = defaultdict(list)
    for source, action, target in graph["edges"]:
        if (source, tuple(action)) in conflicted or target in suspect:
            continue
        adjacency[source].append((tuple(action), target))

    routes: dict[str, list] = {origin: []}
    queue: deque[str] = deque([origin])
    while queue:
        node = queue.popleft()
        for action, target in adjacency.get(node, ()):
            if target in routes:
                continue
            routes[target] = routes[node] + [list(action)]
            queue.append(target)

    proposed = [
        d for d in sorted(routes)
        if d in walked and len(routes[d]) < len(walked[d]) and d in states
    ]
    verified: dict[str, list] = {}
    rejected = 0
    for digest in proposed:
        grid = engine.route(routes[digest])
        if grid is not None and grid == states[digest]:
            verified[digest] = routes[digest]
        else:
            rejected += 1

    saved = [len(walked[d]) - len(verified[d]) for d in verified]
    return {
        "attempted": len(proposed),
        "verified": len(verified),
        "rejected": rejected,
        "verified_rate": round(len(verified) / len(proposed), 4) if proposed else None,
        "actions_saved_mean": round(statistics.mean(saved), 2) if saved else None,
        "actions_saved_total": sum(saved),
        "short_length_mean": (
            round(statistics.mean([len(v) for v in verified.values()]), 2)
            if verified else None
        ),
        "_short": verified,
    }


# ======================================================================================
# Per-game driver
# ======================================================================================


def repair(args: tuple[str, dict, bool, bool]) -> dict[str, Any]:
    game, audit, do_short, write_maps = args
    row: dict[str, Any] = {"game": game}
    row["gate"] = gate(game)
    if not row["gate"]["passed"]:
        row["stopped"] = "gate failed — sidecar is not this store's trajectory"
        return row

    data = extract(game)
    row.update({k: v for k, v in data.items() if not k.startswith("_")})

    engine = Engine(game)
    row["validation_trajectory"] = validate_trajectory(game, data, engine)
    row["validation_sample"] = validate_sample(game, data, engine, audit)

    verified_rate = audit.get("games", {}).get(game, {}).get("verified_rate", 0.0)
    row["audit_verified_rate"] = verified_rate
    row["clean_game"] = verified_rate >= CLEAN_THRESHOLD
    short: dict[str, list] = {}
    if do_short and row["clean_game"]:
        result = shorten(game, data, engine)
        short = result.pop("_short")
        row["short_routes"] = result
    else:
        row["short_routes"] = {
            "attempted": 0,
            "skipped": "not a clean game — store edges are not chained here"
            if do_short else "stage did not run",
        }

    row["replay_actions_executed"] = engine.steps
    row["fully_routable"] = bool(
        row["covered"] == row["store_states"]
        and row["validation_trajectory"]["states_verified_rate"] == 1.0
        and row["validation_sample"]["rate"] == 1.0
    )

    if write_maps:
        MAPS.mkdir(parents=True, exist_ok=True)
        document = {
            "format_version": FORMAT_VERSION,
            "game": game,
            "note": "notes/e1-prefix-repair.md — walked paths; logs/e1_store_v2 is untouched",
            "source": f"logs/e2_hidden_state_rerun/{game}.performs.jsonl",
            "gate": row["gate"],
            "origin": data["origin"],
            "route_form": "new_game(); RESET; <actions>",
            "routes": {
                digest: {
                    "walked": data["_walked"][digest],
                    "walked_len": len(data["_walked"][digest]),
                    "composed_len": len(data["_composed"].get(digest, [])),
                    "first_perform_index": data["_first_index"][digest],
                    "episode_anchor": data["_anchor"][digest],
                    **(
                        {"short": short[digest], "short_len": len(short[digest])}
                        if digest in short else {}
                    ),
                }
                for digest in sorted(data["_walked"])
            },
            "uncovered_states": data["uncovered_states"],
        }
        (MAPS / f"{game}.json").write_text(json.dumps(document, sort_keys=True))
        row["map"] = f"logs/e1_prefix_v2/{game}.json"
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("all", "extract"), default="all")
    parser.add_argument("--games", nargs="*")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    audit = json.loads(AUDIT.read_text())
    games = args.games or _games()
    jobs = [(game, audit, args.stage == "all", True) for game in games]

    rows: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(repair, jobs):
            rows.append(row)
            if "stopped" in row:
                print(f"{row['game']:5s} STOPPED {row['stopped']}", flush=True)
                continue
            traj = row["validation_trajectory"]
            sample = row["validation_sample"]
            stats = row["length_stats"]
            print(
                f"{row['game']:5s} covered={row['covered']:5d}/{row['store_states']:<5d} "
                f"walked_med={stats['walked'].get('median', '-'):<5} "
                f"(was {stats['composed'].get('median', '-'):<5}) "
                f"traj={traj['states_verified_rate'] or 0:.4f} "
                f"sample={sample['passed']}/{sample['sampled']} "
                f"short={row['short_routes'].get('verified', 0)} "
                f"{'ROUTABLE' if row['fully_routable'] else ''}",
                flush=True,
            )

    live = [r for r in rows if "stopped" not in r]
    covered = sum(r["covered"] for r in live)
    total = sum(r["store_states"] for r in live)
    sampled = sum(r["validation_sample"]["sampled"] for r in live)
    sample_passed = sum(r["validation_sample"]["passed"] for r in live)
    positions = sum(r["validation_trajectory"]["positions_checked"] for r in live)
    positions_ok = sum(r["validation_trajectory"]["positions_matched"] for r in live)
    document = {
        "format_version": FORMAT_VERSION,
        "note": "notes/e1-prefix-repair.md",
        "store": "logs/e1_store_v2 (frozen, read-only here)",
        "maps": "logs/e1_prefix_v2 (gitignored; per-state routes)",
        "sample_seed": SAMPLE_SEED,
        "sample_states_per_game": SAMPLE_STATES,
        "clean_threshold": CLEAN_THRESHOLD,
        "totals": {
            "games": len(rows),
            "gate_passed": sum(1 for r in rows if r["gate"]["passed"]),
            "store_states": total,
            "covered": covered,
            "coverage_rate": round(covered / total, 4) if total else None,
            "trajectory_positions_checked": positions,
            "trajectory_positions_matched": positions_ok,
            "trajectory_position_match_rate": (
                round(positions_ok / positions, 6) if positions else None
            ),
            "states_grid_verified": sum(
                r["validation_trajectory"]["states_grid_verified"] for r in live
            ),
            "sampled": sampled,
            "sample_passed": sample_passed,
            "sample_rate": round(sample_passed / sampled, 4) if sampled else None,
            "fully_routable_games": sum(1 for r in live if r["fully_routable"]),
            "short_routes_verified": sum(
                r["short_routes"].get("verified", 0) for r in live
            ),
            "audit_verified_rate_before": audit["totals"]["verified_rate"],
        },
        "fully_routable": sorted(r["game"] for r in live if r["fully_routable"]),
        "not_fully_routable": sorted(r["game"] for r in live if not r["fully_routable"]),
        "games": {r["game"]: r for r in rows},
    }
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\n{json.dumps(document['totals'], indent=2)}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
