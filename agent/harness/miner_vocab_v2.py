#!/usr/bin/env python3
"""Miner vocabulary v2 — the two mechanisms of notes/miner-vocab-v2.md, measured.

Zero model calls. Runs the E0 measurement over the full 24-game human-replay corpus under a
2 x 3 arm matrix and reports the deltas that decide adoption:

    vocabulary   v1 (committed)  vs  v2 (+ `clicked_adjacent_to:C`)
    census scope none (=v1)  vs  effect_local  vs  present_only  vs  full

The two mechanisms are INDEPENDENT and are reported independently. Mechanism 1 is a feature
gap — the E2 slice's one keepable output was Qwen naming a word the vocabulary lacks.
Mechanism 2 is a rule-SCOPING gap — E0's largest transfer-failure bucket is
`separable_by_census`, where the separator is already in the vocabulary and nothing selected
it because tier 1 only looks for features that partition the training evidence. Running them
together as well as apart is what distinguishes "two fixes" from "one fix counted twice".

WHAT DECIDES ADOPTION
---------------------
No invented thresholds. Per mechanism, per mode, the reported quantities are:

    accuracy_over_all      the headline; scoping trades wrong predictions for abstentions,
                           so this can only fall for mechanism 2 and that is not a verdict
    accuracy_over_covered  what the rules that DO fire are worth
    coverage / abstained   the price paid for that
    failure_split          census bucket should SHRINK, uncovered should GROW
    tier1_guard_families   how often `clicked_adjacent_to:*` is the SELECTED partition
                           feature — a feature that never partitions is dead weight and is
                           reported as such, not silently kept

The `full` scope arm exists to show the collapse, not to win: inside one level's evidence
nearly every census feature is constant, so a fully-scoped L1 rule should abstain on almost
every L2 state. If it does not, effect-locality is not doing what it claims. (It did: 0.000
coverage in all 24 games, both modes.)

`present_only` is POST HOC — it was added after the first run, on the strength of the
abstention causes that run reported, and is labelled as such everywhere it appears. It is a
diagnosis of why the three pre-specified arms collapsed, not a fourth hypothesis, and it is
NOT adopted here: adopting a variant on the strength of the same pass that suggested it is
how a measurement becomes a story. It is recorded as the candidate to pre-register next.

Run:
  .venv/bin/python agent/harness/miner_vocab_v2.py --jobs 8
  .venv/bin/python agent/harness/miner_vocab_v2.py --regress   # v1 still reproduces E0
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/ship-jepa-mpl")

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

from rs_e0 import (  # noqa: E402
    SCOPES,
    guard_families,
    key_purity,
    memorizer,
    mine,
    score,
)
from rs_transitions import (  # noqa: E402
    ALL_GAMES,
    EXCLUDED_GAMES,
    ROOT,
    load_game,
    set_vocab,
    split_half,
)

OUTPUT = ROOT / "logs/miner_vocab_v2.json"
FORMAT_VERSION = 1

VOCABS = ("v1", "v2")
MODES = ("full", "moveset")  # `changed` is degenerate here, as in e2_dose

# E0's three largest `separable_by_census` games — mechanism 2's focus rows — and the game
# whose missing word motivated mechanism 1.
CENSUS_FOCUS = ("lp85", "g50t", "sk48")
FEATURE_FOCUS = "ft09"


def arm(l1, l2, a, b, mode: str, scope: str) -> dict[str, Any]:
    rules_a, _ = mine(a, mode, scope)
    rules_l1, report = mine(l1, mode, scope)
    return {
        "rules": len(rules_l1),
        "tier1_guard_families": guard_families(rules_l1),
        "unresolved_keys": report["unresolved_keys"],
        # Only for the unscoped arm: scope does not touch mining, so the purity table is
        # identical across scopes and computing it three times would only bloat the file.
        "key_purity": key_purity(l1, mode) if scope == "none" else None,
        "within_l1": score(rules_a, a, b, mode),
        "l1_to_l2": score(rules_l1, l1, l2, mode),
    }


def run_game(game: str) -> dict[str, Any]:
    row: dict[str, Any] = {"game": game, "arms": {}}
    for vocabulary in VOCABS:
        # Read at call time by `guard_features`, so this must precede `load_game`: the guards
        # are computed during extraction and are never recomputed afterwards.
        set_vocab(vocabulary)
        transitions = load_game(game, max_level=2)
        l1 = [t for t in transitions if t.level == 1]
        l2 = [t for t in transitions if t.level == 2]
        a, b = split_half(l1)
        if vocabulary == VOCABS[0]:
            row["l1_transitions"] = len(l1)
            row["l2_transitions"] = len(l2)
            row["memorizer_l1_to_l2"] = {
                mode: memorizer(l1, l2, mode)["accuracy_over_all"] for mode in MODES
            }
        for mode in MODES:
            for scope in SCOPES:
                row["arms"][f"{vocabulary}/{mode}/{scope}"] = arm(l1, l2, a, b, mode, scope)
    return row


def _job(game: str) -> dict[str, Any]:
    try:
        return run_game(game)
    except Exception as error:  # a game that cannot load is reported, never skipped silently
        return {"game": game, "error": f"{type(error).__name__}: {error}"}


# ======================================================================================
# Reporting
# ======================================================================================


def _delta(rows: list[dict], left: str, right: str, mode: str, field: str) -> dict[str, Any]:
    """Paired per-game delta right - left on `l1_to_l2[field]`, plus the win/tie/loss count.

    Paired and per-game because the games differ by two orders of magnitude in accuracy; a
    pooled mean would be a report about tu93 and vc33 with the other 22 as rounding error.
    """
    pairs = []
    for row in rows:
        if "error" in row:
            continue
        lhs = row["arms"][left.replace("MODE", mode)]["l1_to_l2"][field]
        rhs = row["arms"][right.replace("MODE", mode)]["l1_to_l2"][field]
        if lhs is None or rhs is None:
            continue
        pairs.append((row["game"], lhs, rhs))
    deltas = [rhs - lhs for _, lhs, rhs in pairs]
    return {
        "n": len(pairs),
        "median_left": round(statistics.median([p[1] for p in pairs]), 4) if pairs else None,
        "median_right": round(statistics.median([p[2] for p in pairs]), 4) if pairs else None,
        "median_delta": round(statistics.median(deltas), 4) if deltas else None,
        "wins": sum(1 for d in deltas if d > 1e-9),
        "ties": sum(1 for d in deltas if abs(d) <= 1e-9),
        "losses": sum(1 for d in deltas if d < -1e-9),
        "largest_gain": max(
            (p for p in pairs), key=lambda p: p[2] - p[1], default=None
        ),
        "largest_loss": min(
            (p for p in pairs), key=lambda p: p[2] - p[1], default=None
        ),
    }


def summarize(rows: list[dict]) -> dict[str, Any]:
    ok = [row for row in rows if "error" not in row]
    out: dict[str, Any] = {"games_measured": len(ok), "errors": len(rows) - len(ok)}

    for mode in MODES:
        out[f"mechanism1_{mode}"] = {
            "accuracy_over_all": _delta(ok, "v1/MODE/none", "v2/MODE/none", mode, "accuracy_over_all"),
            "coverage": _delta(ok, "v1/MODE/none", "v2/MODE/none", mode, "coverage"),
        }
        out[f"mechanism2_{mode}"] = {
            "accuracy_over_all": _delta(
                ok, "v1/MODE/none", "v1/MODE/effect_local", mode, "accuracy_over_all"
            ),
            "accuracy_over_covered": _delta(
                ok, "v1/MODE/none", "v1/MODE/effect_local", mode, "accuracy_over_covered"
            ),
            "coverage": _delta(ok, "v1/MODE/none", "v1/MODE/effect_local", mode, "coverage"),
        }
        out[f"mechanism2_full_scope_{mode}"] = {
            "coverage": _delta(ok, "v1/MODE/none", "v1/MODE/full", mode, "coverage"),
        }
        # POST HOC arm — see the module docstring. Reported, not adopted.
        out[f"mechanism2_present_only_{mode}"] = {
            "accuracy_over_all": _delta(
                ok, "v1/MODE/none", "v1/MODE/present_only", mode, "accuracy_over_all"
            ),
            "accuracy_over_covered": _delta(
                ok, "v1/MODE/none", "v1/MODE/present_only", mode, "accuracy_over_covered"
            ),
            "coverage": _delta(ok, "v1/MODE/none", "v1/MODE/present_only", mode, "coverage"),
        }
        out[f"both_{mode}"] = {
            "accuracy_over_all": _delta(
                ok, "v1/MODE/none", "v2/MODE/effect_local", mode, "accuracy_over_all"
            ),
            "accuracy_over_covered": _delta(
                ok, "v1/MODE/none", "v2/MODE/effect_local", mode, "accuracy_over_covered"
            ),
        }

    # Mechanism 1 guard-quality check: is the new feature ever the SELECTED tier-1 partition?
    selected = {}
    for mode in MODES:
        total = live = 0
        for row in ok:
            families = row["arms"][f"v2/{mode}/none"]["tier1_guard_families"]
            total += sum(families.values())
            live += families.get("clicked_adjacent_to", 0)
        selected[mode] = {
            "tier1_rules_total": total,
            "selected_clicked_adjacent_to": live,
            "share": round(live / total, 4) if total else None,
            "games_where_selected": sorted(
                row["game"]
                for row in ok
                if row["arms"][f"v2/{mode}/none"]["tier1_guard_families"].get(
                    "clicked_adjacent_to"
                )
            ),
        }
    out["mechanism1_guard_quality"] = selected

    # Census bucket movement — the bucket mechanism 2 exists to drain.
    for mode in MODES:
        bucket = []
        for row in ok:
            base = row["arms"][f"v1/{mode}/none"]["l1_to_l2"]["failure_split"]
            scoped = row["arms"][f"v1/{mode}/effect_local"]["l1_to_l2"]["failure_split"]
            bucket.append(
                {
                    "game": row["game"],
                    "census_before": base["separable_by_census"],
                    "census_after": scoped["separable_by_census"],
                    "abstained": row["arms"][f"v1/{mode}/effect_local"]["l1_to_l2"]["abstained"],
                }
            )
        out[f"census_bucket_{mode}"] = {
            "before": sum(b["census_before"] for b in bucket),
            "after": sum(b["census_after"] for b in bucket),
            "focus": [b for b in bucket if b["game"] in CENSUS_FOCUS],
        }

    # Mechanism 1, below the tier-1 bar: tier 1 selects a feature only if it resolves a key
    # COMPLETELY, so `rules mined` cannot distinguish "the new feature carries no signal"
    # from "it carries more signal than anything else and still falls short". Purity can.
    for mode in MODES:
        rows_p = []
        for row in ok:
            for item in row["arms"][f"v2/{mode}/none"]["key_purity"] or []:
                rows_p.append({"game": row["game"], **item})
        new_best = [r for r in rows_p if r["best_family"] == "clicked_adjacent_to"]
        gains = [
            r for r in rows_p if r["best_new_purity"] is not None and r["best_new_purity"] > 0
        ]
        out[f"unresolved_key_purity_{mode}"] = {
            "unresolved_keys": len(rows_p),
            "keys_where_new_feature_is_best": len(new_best),
            "keys_where_new_feature_has_any_purity": len(gains),
            "median_best_purity": round(
                statistics.median([r["best_purity"] for r in rows_p]), 4
            )
            if rows_p
            else None,
            "top_new_feature_keys": sorted(
                (
                    {
                        "game": r["game"],
                        "key": r["key"],
                        "n": r["transitions"],
                        "feature": r["best_new_feature"],
                        "purity": r["best_new_purity"],
                        "best_overall": r["best_purity"],
                    }
                    for r in gains
                ),
                key=lambda item: -item["purity"],
            )[:15],
        }

    # Focus row for mechanism 1: did ft09's A6 keys resolve?
    focus = next((row for row in ok if row["game"] == FEATURE_FOCUS), None)
    if focus:
        detail: dict[str, Any] = {"game": FEATURE_FOCUS}
        for mode in MODES:
            detail[mode] = {
                vocabulary: {
                    "rules": focus["arms"][f"{vocabulary}/{mode}/none"]["rules"],
                    "unresolved_keys": [
                        item["key"]
                        for item in focus["arms"][f"{vocabulary}/{mode}/none"][
                            "unresolved_keys"
                        ]
                    ],
                    "l1_to_l2_accuracy": focus["arms"][f"{vocabulary}/{mode}/none"][
                        "l1_to_l2"
                    ]["accuracy_over_all"],
                }
                for vocabulary in VOCABS
            }
            detail[f"{mode}_purity"] = focus["arms"][f"v2/{mode}/none"]["key_purity"]
        out["feature_focus"] = detail
    return out


def regress() -> int:
    """Assert that `--vocab v1` still reproduces logs/e0_row_m_all.json exactly.

    The v2 adoption is only defensible if the v1 numbers it is compared against are still
    the v1 numbers. Adding a guard feature touches tier-1 selection, failure classification
    and the `_classify_failure` ordering, and any of those could have moved v1 silently.
    """
    reference = ROOT / "logs/e0_row_m_all.json"
    ref = {row["game"]: row for row in json.loads(reference.read_text())["games"]}
    set_vocab("v1")
    checked = 0
    for game, want in sorted(ref.items()):
        transitions = load_game(game, max_level=2)
        l1 = [t for t in transitions if t.level == 1]
        l2 = [t for t in transitions if t.level == 2]
        a, b = split_half(l1)
        for mode, cell in want["by_effect_mode"].items():
            rules_a, _ = mine(a, mode)
            rules_l1, _ = mine(l1, mode)
            for got, expected in (
                (score(rules_a, a, b, mode), cell["within_l1"]),
                (score(rules_l1, l1, l2, mode), cell["l1_to_l2"]),
            ):
                for field in (
                    "covered",
                    "correct",
                    "accuracy_over_all",
                    "accuracy_over_covered",
                    "coverage",
                    "failure_split",
                    "rules_survived",
                    "separating_guard_family",
                ):
                    if got[field] != expected[field]:
                        print(f"REGRESSION {game}/{mode}/{field}: {got[field]} != {expected[field]}")
                        return 1
                checked += 1
        print(f"  {game} ok", flush=True)
    print(f"\nv1 reproduces logs/e0_row_m_all.json exactly ({checked} scored splits)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regress",
        action="store_true",
        help="check that --vocab v1 still reproduces logs/e0_row_m_all.json, then exit",
    )
    parser.add_argument(
        "--games",
        nargs="*",
        default=[game for game in ALL_GAMES if game not in EXCLUDED_GAMES],
    )
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.regress:
        return regress()

    results: list[dict[str, Any]] = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(_job, game): game for game in args.games}
        for future in concurrent.futures.as_completed(futures):
            row = future.result()
            results.append(row)
            if "error" in row:
                print(f"{row['game']:5s} ERROR {row['error']}", flush=True)
                continue
            base = row["arms"]["v1/full/none"]["l1_to_l2"]
            feat = row["arms"]["v2/full/none"]["l1_to_l2"]
            scoped = row["arms"]["v1/full/effect_local"]["l1_to_l2"]
            print(
                f"{row['game']:5s} L1={row['l1_transitions']:5d} L2={row['l2_transitions']:5d} | "
                f"v1 acc={base['accuracy_over_all']:.3f} cov={base['coverage']:.3f} "
                f"census={base['failure_split']['separable_by_census']:5d} | "
                f"+feat acc={feat['accuracy_over_all']:.3f} | "
                f"+scope acc={scoped['accuracy_over_all']:.3f} "
                f"cov={scoped['coverage']:.3f} "
                f"census={scoped['failure_split']['separable_by_census']:5d} "
                f"abst={scoped['abstained']:5d}",
                flush=True,
            )
    results.sort(key=lambda row: args.games.index(row["game"]))

    document = {
        "format_version": FORMAT_VERSION,
        "note": "notes/miner-vocab-v2.md",
        "vocabs": list(VOCABS),
        "scopes": list(SCOPES),
        "modes": list(MODES),
        "summary": summarize(results),
        "games": {row["game"]: row for row in results},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(document, indent=2, sort_keys=True, default=str))
    print(f"\nwrote {args.out}")
    print(json.dumps(document["summary"], indent=2, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
