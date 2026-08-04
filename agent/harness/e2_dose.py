#!/usr/bin/env python3
"""E2 (zero-model half) — the evidence-dose curve over the E1 v2 store.

`notes/l1-evidence-first.md` defines E2 as goal-candidate quality and synthesis quality as
a function of exploration dose. This file is the model-free substrate of that measurement:
the E0 miner and the row-C goal grammar run over increasing prefixes of the explorer's own
evidence (`logs/e1_store_v2/`), validated against HUMAN replay transitions — an external
test set the explorer never saw. The Qwen half (thinking on, two-phase decode) reads the
same store; its numbers mean nothing unless these floors and curves exist first.

MECHANICS CURVE (per game, per dose, modes full + moveset)
----------------------------------------------------------
    mine(explorer prefix) -> score on human L1  (does explorer evidence recover the rules
                                                 governing competent play?)
                          -> score on human L2  (the transfer question, E0's l1_to_l2)
    memorizer floor on both targets; ceiling = mine(human L1) scored on human L2 — which
    is E0's own row, recomputed here as a cross-check against logs/e0_row_m_all.json.

GOAL CURVE (per game, per dose; row-C grammar, zero model calls)
----------------------------------------------------------------
    Stream the explorer transitions through the row-C universe (kill on definite
    contradiction — identical semantics to rs_completion.survivors, computed
    incrementally). Record the survivor count at each dose boundary; score the FULL-dose
    survivors against human L1 (whose ~10 completions per game are the positive examples
    the store mostly lacks). A true goal the explorer evidence has falsified shows up here
    as human-L1 falsification of every survivor.

Transitions are reconstructed from the store with effect and guards RECOMPUTED through the
canonical rs_transitions pipeline (never parsed from the store) wherever both grids exist;
only completion rows — whose post frame the explorer does not retain as a state — fall back
to the stored effect signature.

Run:
  .venv/bin/python agent/harness/e2_dose.py --jobs 8 --out logs/e2_dose.json
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

import es_candidates as ec  # noqa: E402
from es_candidates import _Objects  # noqa: E402
from rs_completion import (  # noqa: E402
    FALSE,
    TRUE,
    ObjectCache,
    score as goal_score,
)
from rs_e0 import EFFECT_MODES, memorizer, mine, score  # noqa: E402
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ROOT,
    Transition,
    effect_signature,
    guard_features,
    load_game,
)

STORE = ROOT / "logs/e1_store_v2"
OUTPUT = ROOT / "logs/e2_dose.json"
FORMAT_VERSION = 1

DOSES = (125, 250, 500, 1000, 2000, None)  # (w) None = the full store
MODES = tuple(mode for mode in EFFECT_MODES if mode != "changed")  # changed is degenerate


def _tupleize(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tupleize(item) for item in value)
    return value


def load_store(game: str) -> tuple[list[Transition], set[int]]:
    """Explorer store rows -> canonical Transitions in step order, plus the steps whose
    POST frame the store does not retain (completion rows — the explorer hashes the
    level-advance frame but never adds it to states). Their effect comes from the store
    and their guards from the pre frame, so MINING is sound; but any consumer that reads
    `.post` directly (the goal grammar) must skip them — `post` is a placeholder there."""
    states = json.loads((STORE / f"{game}.states.json").read_text())
    grids = {digest: grid for digest, grid in states.items()}
    transitions: list[Transition] = []
    post_missing: set[int] = set()
    with (STORE / f"{game}.transitions.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            pre = grids.get(row["pre"])
            if pre is None:  # cannot score or guard without the pre frame
                continue
            post = grids.get(row["post"])
            if post is None:
                post_missing.add(row["step"])
            action_id, click_row, click_col = row["action"]
            data = (
                {"y": click_row, "x": click_col} if action_id == 6 else {}
            )
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
    transitions.sort(key=lambda transition: transition.step)
    return transitions, post_missing


def mechanics_curve(
    explorer: list[Transition], human_l1: list[Transition], human_l2: list[Transition]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in MODES:
        doses: list[dict[str, Any]] = []
        for dose in DOSES:
            prefix = explorer if dose is None else explorer[:dose]
            if dose is not None and len(explorer) < dose:
                doses.append({"dose": dose, "skipped": "store smaller than dose"})
                continue
            rules, _ = mine(prefix, mode)
            doses.append(
                {
                    "dose": dose if dose is not None else len(explorer),
                    "full_store": dose is None,
                    "rules": len(rules),
                    "on_human_l1": score(rules, prefix, human_l1, mode),
                    "on_human_l2": score(rules, prefix, human_l2, mode),
                    "memorizer_on_human_l1": memorizer(prefix, human_l1, mode),
                }
            )
        ceiling_rules, _ = mine(human_l1, mode)
        out[mode] = {
            "doses": doses,
            "human_ceiling_on_l2": score(ceiling_rules, human_l1, human_l2, mode),
        }
    return out


def goal_curve(
    explorer: list[Transition], human_l1: list[Transition], post_missing: set[int]
) -> dict[str, Any]:
    if not explorer:
        return {"skipped": "empty store"}
    universe_doc = ec.enumerate_universe(explorer[0].pre)
    row: dict[str, Any] = {
        "universe_size": universe_doc["universe_size"],
        "universe_tractable": universe_doc["tractable"],
        "universe_hash": universe_doc["universe_hash"],
    }
    if not universe_doc["tractable"]:
        return row

    cache = ObjectCache()
    alive = list(universe_doc["universe"])
    boundaries = sorted({dose for dose in DOSES if dose} | {len(explorer)})
    counts: list[dict[str, int]] = []
    consumed = 0
    for boundary in boundaries:
        if boundary > len(explorer):
            break
        for transition in explorer[consumed:boundary]:
            if not alive:
                break
            if transition.step in post_missing:
                continue  # no real post frame — a fabricated one would corrupt the
                # store's only positive example (this run: exactly the completion rows)
            truth = TRUE if transition.completed else FALSE
            context = cache.context(transition.pre, transition.post)
            alive = [
                candidate
                for candidate in alive
                if (value := ec.evaluate(candidate, context)) not in (TRUE, FALSE)
                or value == truth
            ]
        consumed = boundary
        counts.append({"dose": boundary, "survivors": len(alive)})
    row["survivors_by_dose"] = counts
    row["final_survivors"] = len(alive)
    row["positives_skipped_no_post_frame"] = sum(
        1 for t in explorer if t.completed and t.step in post_missing
    )
    row["final_vs_human_l1"] = goal_score(alive, human_l1, cache) if alive else None
    return row


def run_game(game: str) -> dict[str, Any]:
    explorer, post_missing = load_store(game)
    human = load_game(game, max_level=2)
    human_l1 = [t for t in human if t.level == 1]
    human_l2 = [t for t in human if t.level == 2]
    row = {
        "game": game,
        "store_transitions": len(explorer),
        "store_completions": sum(t.completed for t in explorer),
        "human_l1": len(human_l1),
        "human_l2": len(human_l2),
        "mechanics": mechanics_curve(explorer, human_l1, human_l2),
        "goal": goal_curve(explorer, human_l1, post_missing),
    }
    return row


def _job(game: str) -> dict[str, Any]:
    try:
        return run_game(game)
    except Exception as error:
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--games",
        nargs="*",
        default=[game for game in ALL_GAMES if game not in EXCLUDED_GAMES],
    )
    parser.add_argument("--jobs", type=int, default=6)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()

    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(_job, game): game for game in args.games}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results.append(row)
            if "error" in row:
                print(f"{row['game']:5s} ERROR {row['error']}", flush=True)
                continue
            full = row["mechanics"]["full"]["doses"][-1]
            ceiling = row["mechanics"]["full"]["human_ceiling_on_l2"]
            goal = row["goal"]
            print(
                f"{row['game']:5s} store={row['store_transitions']:5d} "
                f"full@max L1acc={full['on_human_l1']['accuracy_over_all']:.3f} "
                f"cov={full['on_human_l1']['coverage']:.3f} "
                f"L2acc={full['on_human_l2']['accuracy_over_all']:.3f} "
                f"ceilL2={ceiling['accuracy_over_all']:.3f} "
                f"goalsurv={goal.get('final_survivors', 'n/a')}",
                flush=True,
            )
    results.sort(key=lambda row: args.games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "store": str(STORE.relative_to(ROOT)),
        "doses": list(DOSES),
        "modes": list(MODES),
        "games": {row["game"]: row for row in results},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
