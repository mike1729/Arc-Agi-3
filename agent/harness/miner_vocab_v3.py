#!/usr/bin/env python3
"""Miner vocabulary v3 — the channel-C implementation queue, measured against the v2 floors.

`notes/e2-slice3.md` → RUN RESULTS. Zero model calls.

WHERE THESE FEATURES CAME FROM
------------------------------
Channel C was the one channel of the slice-3 night that measurably improved: proposals
naming a genuinely unresolved forward-model key went from 6/31 in slice 2 to 16/31 in slice
3, on the same games and the same key lists. Unlike channels A and B it does not need a goal
predicate at all, which is why it is the one worth building on. The distinct proposals were:

    min_row / min_col of the moving object   m0r0, ls20, tu93 — four independent proposals
    size(clicked)                            lf52
    enclosed_by                              ft09
    col_aligned                              sp80

v3 is exactly that list and nothing else, implemented in `rs_transitions.guard_features`.
This module measures whether it is worth having, under the protocol v2 was adopted by.

THE ADOPTION RULE, PRE-COMMITTED HERE
-------------------------------------
v2 was adopted on a rule stated before its numbers existed: zero losses on every metric of
every game, and non-zero gains somewhere. The same rule governs v3, and v2 remains the FLOOR
OF RECORD and the default vocabulary until v3 clears it. Nothing downstream switches on a
promising delta.

THE RISK THIS MEASUREMENT IS LOOKING FOR, NAMED IN ADVANCE
----------------------------------------------------------
`min_row`/`min_col` are high-cardinality integers. Tier-1 selection looks for a feature that
partitions the training evidence, and a feature with 64 possible values partitions ANY
training evidence — so it will be selected often and transfer badly. The signature is a v3
arm whose held-out-L1 accuracy holds or rises while L2 accuracy falls, together with
`min_row`/`min_col` dominating the selected-guard families. If that is what appears, the
positional features are the finding and the other four should be measured without them
(`--without-position`), which is why that arm exists rather than being a follow-up.

Run:
  .venv/bin/python agent/harness/miner_vocab_v3.py --jobs 8
  .venv/bin/python agent/harness/miner_vocab_v3.py --games m0r0 lf52 --jobs 2
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_e0 import guard_families, mine, score  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ROOT,
    load_game,
    set_vocab,
    split_half,
)

OUTPUT = ROOT / "logs/miner_vocab_v3.json"
# The same two effect modes v2 was measured under (`changed` is degenerate here, as in
# e2_dose), so the deltas are against the arm that actually set the floor.
MODES = ("full", "moveset")
FORMAT_VERSION = 1

# The positional pair, isolated so the `--without-position` arm can drop exactly it.
POSITIONAL = ("min_row", "min_col")


def _strip_positional(transitions: list) -> None:
    for transition in transitions:
        for name in [k for k in transition.guards if k.split(":")[0] in POSITIONAL]:
            del transition.guards[name]


def run_game(game: str, vocabulary: str, *, drop_position: bool = False) -> dict[str, Any]:
    set_vocab(vocabulary)
    try:
        transitions = load_game(game, max_level=2)
    except ValueError as error:
        return {"game": game, "skipped": str(error)}
    if drop_position:
        _strip_positional(transitions)

    l1 = [t for t in transitions if t.level == 1]
    l2 = [t for t in transitions if t.level == 2]
    train, held_out = split_half(l1)
    if not train or not held_out:
        return {"game": game, "skipped": "half split is empty at L1"}

    out: dict[str, Any] = {
        "game": game,
        "vocab": vocabulary,
        "drop_position": drop_position,
        "l1": len(l1),
        "l2": len(l2),
        "modes": {},
    }
    for mode in MODES:
        rules, _ = mine(train, mode)
        out["modes"][mode] = {
            "held_out_l1": score(rules, train, held_out, mode),
            "l2": score(rules, train, l2, mode) if l2 else None,
            "guard_families": guard_families(rules),
            "rules": len(rules),
        }
    return out


def _accuracy(row: dict[str, Any], mode: str, split: str) -> float | None:
    block = ((row.get("modes") or {}).get(mode) or {}).get(split)
    return None if not block else block.get("accuracy_over_all")


def compare(base: dict[str, Any], arm: dict[str, Any]) -> dict[str, Any]:
    """Per-game deltas on the adoption metrics. A loss anywhere is a loss."""
    deltas: dict[str, Any] = {}
    losses: list[str] = []
    for mode in MODES:
        for split in ("held_out_l1", "l2"):
            left, right = _accuracy(base, mode, split), _accuracy(arm, mode, split)
            if left is None or right is None:
                continue
            delta = round(right - left, 6)
            deltas[f"{mode}/{split}"] = delta
            if delta < 0:
                losses.append(f"{mode}/{split} {delta:+.4f}")
    return {
        "deltas": deltas,
        "losses": losses,
        "clean": not losses,
        "gains": [k for k, v in deltas.items() if v > 0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", nargs="*", default=[g for g in ALL_GAMES if g not in EXCLUDED_GAMES])
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--without-position",
        action="store_true",
        help="also run a v3 arm with min_row/min_col removed",
    )
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    arms = [("v2", False), ("v3", False)]
    if args.without_position:
        arms.append(("v3", True))

    jobs = [(game, vocabulary, drop) for game in args.games for vocabulary, drop in arms]
    results: dict[tuple[str, str, bool], dict[str, Any]] = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_game, game, vocabulary, drop_position=drop): (game, vocabulary, drop)
            for game, vocabulary, drop in jobs
        }
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()

    rows = []
    clean = 0
    for game in args.games:
        base = results.get((game, "v2", False), {})
        if "skipped" in base:
            print(f"{game:5s} skipped: {base['skipped']}", flush=True)
            continue
        for vocabulary, drop in arms[1:]:
            arm = results.get((game, vocabulary, drop), {})
            if "skipped" in arm:
                continue
            verdict = compare(base, arm)
            label = f"{vocabulary}{'-nopos' if drop else ''}"
            rows.append({"game": game, "arm": label, "base": base, "v3": arm, **verdict})
            clean += bool(verdict["clean"])
            families = arm["modes"][MODES[0]]["guard_families"]
            positional = sum(v for k, v in families.items() if k.split(":")[0] in POSITIONAL)
            print(
                f"{game:5s} {label:9s} "
                + " ".join(f"{k}={v:+.4f}" for k, v in verdict["deltas"].items())
                + f" | selected-positional={positional}"
                + ("" if verdict["clean"] else f"  LOSS: {', '.join(verdict['losses'])}"),
                flush=True,
            )

    args.out.write_text(
        json.dumps(
            {
                "format_version": FORMAT_VERSION,
                "generated_by": "agent/harness/miner_vocab_v3.py",
                "note": "notes/e2-slice3.md RUN RESULTS — the channel-C implementation queue",
                "floor_of_record": "v2 (logs/e2_dose_vocab_v2.json) — unchanged unless v3 clears it",
                "adoption_rule": "zero losses on every metric of every game, and gains somewhere",
                "arms": [f"{v}{'-nopos' if d else ''}" for v, d in arms],
                "games": rows,
            },
            indent=1,
        )
        + "\n"
    )
    print(f"\n{clean}/{len(rows)} arms clean — wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
