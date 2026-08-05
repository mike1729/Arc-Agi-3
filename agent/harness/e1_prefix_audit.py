#!/usr/bin/env python3
"""Audit the E1 v2 store's prefix maps by verified replay. Read-only, zero model calls.

`notes/e1-prefix-audit.md`. The E2 probe channel's determinism gate
(`notes/e2-probe-channel.md` §2) found that dc22 and m0r0 do not reproduce their stored
states when their recorded prefixes are replayed. This sweeps the same test over all 24
games so the scope of the defect is a measured number rather than an inference from two
samples.

WHAT A PREFIX IS, AND WHY IT CAN BE WRONG
-----------------------------------------
`e1_explorer.Explorer.observe` records `prefix[new] = prefix[source] + [action]` — a path
COMPOSED from edges observed at different moments in the run, not a path anyone walked end
to end. Composition is sound only if the settled frame identifies the state. Where it does
not, the composed path is a claim the store never tested, and routing by RESET + prefix
lands somewhere else.

THE THREE NUMBERS
-----------------
    verified    the state's own recorded prefix lands on the grid it claims. These states
                survive any verified re-derivation, so this is a LOWER bound on the keep
                rate.
    reached     the state is the endpoint of SOME walked prefix in this sweep, whether or
                not it was its own. Also a sound lower bound, and a strictly tighter one:
                a state whose own prefix is wrong may still sit on another state's path.
    unreached   neither. An UPPER bound on the drop rate — a re-derivation that searches
                harder (BFS over verified edges, alternative routes) may recover some.

The audit never re-derives anything and never writes into `logs/e1_store_v2/`.

CONTROLS (`--stage controls`) — the three ways this measurement could be an artifact
-------------------------------------------------------------------------------------
1. ENGINE REUSE. This sweep replays many prefixes on one engine, as E1 itself did. If a
   game accumulated state across RESET over a long run, late replays would sit in a
   different latent context than E1's. Measured against a FRESH `new_game()` per replay on
   a 60-state sample: identical counts, so reuse is not the cause.
2. RESET NOT RESTORING THE ORIGIN. If RESET did not return to the stored origin, every
   composed prefix would fail from step zero for an uninteresting reason. Checked per
   game; it restores the origin in all 24.
3. HASHING. `e1_explorer._hash` keys on `(level, grid)`, and `self.level` is set to 1 and
   never mutated, so every stored digest is a level-1 digest and the audit's own level-1
   hashing is comparable. Grid equality — not hash equality — decides `verified` anyway.

`--stage origin-edges` replays every single-action edge out of the origin. It separates
"the recorded EDGES are wrong" from "the recorded edges are fine and COMPOSING them is
wrong", which are very different defects with very different repairs.

Run:
  .venv/bin/python agent/harness/e1_prefix_audit.py --jobs 8
  .venv/bin/python agent/harness/e1_prefix_audit.py --stage controls
  .venv/bin/python agent/harness/e1_prefix_audit.py --stage origin-edges
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from arcengine import ActionInput, GameAction  # noqa: E402

from gi2_replay import ReplayDriver, _plain_frames  # noqa: E402
from rs_transitions import ROOT  # noqa: E402

STORE = ROOT / "logs/e1_store_v2"
OUTPUT = ROOT / "logs/e1_prefix_audit.json"
FORMAT_VERSION = 1

CONTROL_SAMPLE = 60      # (w) states per game in the engine-reuse control
CONTROL_SEED = 7         # (w)
CONTROL_GAMES = ("cd82", "ka59", "dc22", "m0r0", "bp35")   # 4 defective + 1 partial


def _hash(grid: list) -> str:
    """`e1_explorer._hash` at level 1 — the level is never mutated in E1."""
    return hashlib.sha256(
        json.dumps([1, grid], separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _load(game: str) -> tuple[dict, dict]:
    return (
        json.loads((STORE / f"{game}.graph.json").read_text()),
        json.loads((STORE / f"{game}.states.json").read_text()),
    )


class Replayer:
    def __init__(self, game: str, *, fresh_each: bool = False):
        self.driver = ReplayDriver(game)
        self.fresh_each = fresh_each
        self.engine = self.driver.new_game()

    def run(self, prefix: list) -> list | None:
        if self.fresh_each:
            self.engine = self.driver.new_game()
        grid = self._step(0, None, None)
        for action_id, row, col in prefix:
            grid = self._step(action_id, row, col)
            if grid is None:
                return None
        return grid

    def run_recording(self, prefix: list) -> tuple[list | None, list[str]]:
        """As `run`, but returns every state hash passed through."""
        if self.fresh_each:
            self.engine = self.driver.new_game()
        grid = self._step(0, None, None)
        seen = [] if grid is None else [_hash(grid)]
        for action_id, row, col in prefix:
            grid = self._step(action_id, row, col)
            if grid is None:
                return None, seen
            seen.append(_hash(grid))
        return grid, seen

    def _step(self, action_id: int, row: int | None, col: int | None) -> list | None:
        response = self.driver.perform(
            self.engine,
            ActionInput(
                id=GameAction.from_id(action_id),
                data={} if row is None else {"y": row, "x": col},
            ),
        )
        frames = _plain_frames(response.frame or [])
        return frames[-1] if frames else None


def audit(game: str) -> dict[str, Any]:
    graph, states = _load(game)
    prefix = graph["prefix"]
    replayer = Replayer(game)

    verified: set[str] = set()
    reached: set[str] = set()
    origin_ok: bool | None = None
    failures: list[dict[str, Any]] = []

    # shortest first: a failure at small depth is a different animal from one at depth 80
    for digest in sorted(prefix, key=lambda d: (len(prefix[d]), d)):
        grid, seen = replayer.run_recording(prefix[digest])
        if origin_ok is None and seen:
            origin_ok = seen[0] == graph["origin"]
        reached.update(seen)
        if grid is not None and grid == states.get(digest):
            verified.add(digest)
        elif len(failures) < 5:
            failures.append({
                "state": digest,
                "prefix_actions": len(prefix[digest]),
                "landed_on": seen[-1] if seen else None,
            })

    known = set(states)
    depths = [len(prefix[d]) for d in known if d in prefix]
    return {
        "game": game,
        "states": len(known),
        "reset_restores_origin": origin_ok,
        "verified": len(verified),
        "reached": len(known & reached),
        "unreached": len(known - reached),
        "verified_rate": round(len(verified) / len(known), 4),
        "reached_rate": round(len(known & reached) / len(known), 4),
        "drop_upper_bound": round(len(known - reached) / len(known), 4),
        "max_prefix_depth": max(depths) if depths else 0,
        "shallowest_failures": failures,
        "conflicted_edges": len(graph["conflicted"]),
        "suspect_states": len(graph["suspect"]),
    }


def origin_edges(game: str) -> dict[str, Any]:
    """Every single-action edge out of the origin, replayed. Are the EDGES wrong, or only
    their compositions?"""
    graph, _ = _load(game)
    origin = graph["origin"]
    replayer = Replayer(game)
    counts: Counter = Counter()
    for source, action, target in graph["edges"]:
        if source != origin:
            continue
        grid = replayer.run([action])
        got = _hash(grid) if grid is not None else None
        if got == target:
            counts["match"] += 1
        elif got == origin:
            counts[f"replay_no_change_A{action[0]}"] += 1
        else:
            counts[f"other_A{action[0]}"] += 1
    total = sum(counts.values())
    return {
        "game": game,
        "origin_edges": total,
        "match": counts["match"],
        "match_rate": round(counts["match"] / total, 4) if total else None,
        "breakdown": dict(counts),
    }


def reuse_control(game: str) -> dict[str, Any]:
    """Is the failure rate an artifact of replaying many prefixes on ONE engine?"""
    graph, states = _load(game)
    prefix = graph["prefix"]
    ordered = sorted(prefix, key=lambda d: (len(prefix[d]), d))
    sample = random.Random(CONTROL_SEED).sample(
        ordered, min(CONTROL_SAMPLE, len(ordered))
    )
    sample = [d for d in sample if prefix[d]]
    shared = Replayer(game)
    fresh = Replayer(game, fresh_each=True)
    return {
        "game": game,
        "sampled": len(sample),
        "verified_shared_engine": sum(
            shared.run(prefix[d]) == states[d] for d in sample
        ),
        "verified_fresh_game": sum(
            fresh.run(prefix[d]) == states[d] for d in sample
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage", choices=("audit", "controls", "origin-edges"), default="audit"
    )
    parser.add_argument("--games", nargs="*")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    games = args.games or sorted(
        path.name.split(".")[0] for path in STORE.glob("*.graph.json")
    )

    if args.stage == "controls":
        rows = [reuse_control(game) for game in (args.games or CONTROL_GAMES)]
        for row in rows:
            print(
                f"{row['game']:5s} sampled={row['sampled']:3d} "
                f"shared-engine={row['verified_shared_engine']:3d} "
                f"fresh-game={row['verified_fresh_game']:3d}",
                flush=True,
            )
        print(json.dumps(rows, indent=2))
        return 0

    if args.stage == "origin-edges":
        rows = [origin_edges(game) for game in games]
        for row in rows:
            print(
                f"{row['game']:5s} origin_edges={row['origin_edges']:3d} "
                f"match={row['match']:3d} {row['breakdown']}", flush=True
            )
        print(json.dumps(rows, indent=2))
        return 0

    rows: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        for row in pool.map(audit, games):
            rows.append(row)
            print(
                f"{row['game']:5s} states={row['states']:5d} "
                f"verified={row['verified_rate']:.4f} "
                f"reached={row['reached_rate']:.4f} "
                f"drop<={row['drop_upper_bound']:.4f} "
                f"conflicted={row['conflicted_edges']}",
                flush=True,
            )

    total = sum(row["states"] for row in rows)
    document = {
        "format_version": FORMAT_VERSION,
        "store": str(STORE.relative_to(ROOT)),
        "note": "notes/e1-prefix-audit.md — read-only. Nothing here re-derives a prefix.",
        "totals": {
            "games": len(rows),
            "fully_verified_games": sum(1 for r in rows if r["verified_rate"] == 1.0),
            "states": total,
            "verified": sum(r["verified"] for r in rows),
            "reached": sum(r["reached"] for r in rows),
            "verified_rate": round(sum(r["verified"] for r in rows) / total, 4),
            "reached_rate": round(sum(r["reached"] for r in rows) / total, 4),
            "drop_upper_bound": round(
                1 - sum(r["reached"] for r in rows) / total, 4
            ),
        },
        "games": {row["game"]: row for row in rows},
    }
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\n{document['totals']}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
