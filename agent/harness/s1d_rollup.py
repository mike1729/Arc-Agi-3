"""S1-d — generate `gate_manifest.yaml -> s1.results` roll-ups from the promoted gate result.

The four fields this emits (`total_failure_episodes`, `failure_frequency_ranking`, `build_order`,
`viability_verdict`) were null until the blind re-rate was scored, because the manifest fills them
ONLY from a promoted `gate_valid` result. That is a rule about provenance, and transcribing numbers
by eye from a terminal into a YAML file defeats it silently: nothing afterwards can tell a
mis-keyed share from a real one.

So the block is generated. `--verify` re-derives it and exits non-zero if the manifest has drifted
from the artifacts, which makes the fill checkable in CI or by hand at any later date.

TWO INPUTS, AND NEITHER IS OPTIONAL
-----------------------------------
* the pooled corpus supplies the FREQUENCIES — every count and share, over all 75 episodes;
* the promoted gate result supplies the EXCLUSIONS — which categories cleared the 0.40 agreement
  floor on both axes and may therefore drive the build order.

A frequency without its agreement verdict ranks categories whose labels are not reproducible; an
agreement verdict without frequencies ranks nothing. The script refuses a gate result that is not
`gate_valid`, for the same reason the manifest does.

RANKING BAND
------------
`frequencies.ranking_rule` in the corpus: rank on the **L2+ band**, report pooled beside it. Level 1
is soft (the reference cleared 15 of 25) and level 2 is the wall (3 of 25), so a pooled ranking is
dominated by the easy case and would order the build wrong.

  .venv/bin/python agent/harness/s1d_rollup.py                     # emit the YAML block
  .venv/bin/python agent/harness/s1d_rollup.py --verify             # check the manifest against it
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "logs" / "s1d_corpus_pooled.json"
GATE = REPO / "logs" / "s1d_rerate_result.json"
MANIFEST = REPO / "gate_manifest.yaml"

# Structurally unobservable on this reference (manifest `categories_unobservable`): no coordinate
# candidate set exists anywhere in the logs, and the solver does not search. They are EXCLUDED from
# the ranking, never recorded at zero frequency — a zero would read as "measured and absent".
UNOBSERVABLE = ("coordinate_unreachable", "planning_depth")

# Which specification component each surviving category is answered by. Editorial, and deliberately
# so: it is the one column that maps a measurement onto the build, and it is stated here rather than
# inferred so that a reader can disagree with it explicitly.
ADDRESSED_BY = {
    "goal_unknown":
        "spec §9 goal induction + gate G0 (G0-R recognition, G0-A pre-action utility); "
        "§4.6 hypothesis store goal-hypothesis pruning",
    "action_semantics_unknown":
        "spec §4.3 canonicalizer and delta compiler; §5 evaluator factual heads "
        "(no-op / visible / persistent change, changed-region); §11 belief model",
    "exploration_or_probe_selection":
        "spec §7 portfolio row 4 discriminating probe; §4.6 ledger cheapest-test field",
    "progress_signal_misinterpretation":
        "spec §5 P(progress event) head on a predeclared observable event class; "
        "§4.8 terminal-transition logging; §13.2 progress metric",
}


def load():
    corpus = json.loads(CORPUS.read_text())
    gate = json.loads(GATE.read_text())
    if not gate.get("gate_valid"):
        sys.exit(f"REFUSED — {GATE.name} is not a valid gate result "
                 f"(gate_valid={gate.get('gate_valid')!r}, result_kind={gate.get('result_kind')!r}). "
                 f"The roll-ups are filled only from a promoted, gate_valid result.")
    return corpus, gate


def rows(corpus: dict, gate: dict) -> list[dict]:
    freq = corpus["frequencies"]
    pooled, band = freq["pooled"], freq["by_level_band"]["L2+"]
    n_pooled, n_band = pooled["total_failure_episodes"], band["total_failure_episodes"]
    driving = set(gate["categories_driving_build_order"] or [])

    cats = set(pooled["primary_share"]) | set(pooled["episode_share"])
    cats -= set(UNOBSERVABLE)

    # THREE OUTCOMES, NOT TWO. A category absent from the drawn sample has no kappa, and recording it
    # alongside the ones that were measured and failed reads as "tested, unreproducible" when the truth
    # is "never tested". `reasoning_inconsistency` is the live case: 1 episode in 75, not drawn. Both
    # are excluded from the build order, but only one of them is evidence about label stability.
    tested = set(gate.get("per_category") or {})

    out = []
    for c in cats:
        if c in driving:
            status = "cleared"
        elif c in tested:
            status = "failed"
        else:
            status = "untested — absent from the drawn sample, so no kappa exists"
        out.append({
            "category": c,
            "agreement_status": status,
            "primary_count": round(pooled["primary_share"].get(c, 0.0) * n_pooled),
            "primary_share": pooled["primary_share"].get(c, 0.0),
            "episode_count": round(pooled["episode_share"].get(c, 0.0) * n_pooled),
            "episode_share": pooled["episode_share"].get(c, 0.0),
            "primary_share_L2plus": band["primary_share"].get(c, 0.0),
            "episode_share_L2plus": band["episode_share"].get(c, 0.0),
            "primary_count_L2plus": round(band["primary_share"].get(c, 0.0) * n_band),
            "survives_agreement_floor": c in driving,
            "kappa_primary": (gate["per_category"].get(c) or {}).get("kappa_primary"),
            "kappa_any_label": (gate["per_category"].get(c) or {}).get("kappa_any_label"),
            "addressed_by": ADDRESSED_BY.get(c),
        })
    # Rank on the L2+ band per `frequencies.ranking_rule`; survivors first, so the build order reads
    # off the top of the table without a reader having to filter it themselves.
    out.sort(key=lambda r: (not r["survives_agreement_floor"],
                            -r["primary_share_L2plus"], -r["primary_share"], r["category"]))
    return out


def build_order(ranked: list[dict]) -> list[str]:
    return [r["category"] for r in ranked if r["survives_agreement_floor"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="exit non-zero if the manifest's roll-ups have drifted from the artifacts")
    a = ap.parse_args()

    corpus, gate = load()
    ranked = rows(corpus, gate)
    order = build_order(ranked)
    n = corpus["frequencies"]["pooled"]["total_failure_episodes"]

    if a.verify:
        text = MANIFEST.read_text()
        problems = []
        if f"total_failure_episodes: {n}" not in text:
            problems.append(f"total_failure_episodes: expected {n}")
        for c in order:
            if f"category: {c}" not in text:
                problems.append(f"failure_frequency_ranking: {c} missing")
        for r in ranked:
            if not r["survives_agreement_floor"]:
                continue
            if f"primary_share: {r['primary_share']}" not in text:
                problems.append(f"{r['category']}: primary_share {r['primary_share']} not in manifest")
        if problems:
            print("MANIFEST HAS DRIFTED FROM THE ARTIFACTS:")
            for p in problems:
                print(f"    {p}")
            return 1
        print(f"manifest roll-ups agree with {CORPUS.name} + {GATE.name} "
              f"({n} episodes, build order {order})")
        return 0

    print(f"# generated by agent/harness/s1d_rollup.py from {CORPUS.name} + {GATE.name}")
    print(f"total_failure_episodes: {n}")
    print("failure_frequency_ranking:")
    for r in ranked:
        print(f"  - category: {r['category']}")
        for k in ("primary_count", "primary_share", "episode_count", "episode_share",
                  "primary_count_L2plus", "primary_share_L2plus", "episode_share_L2plus",
                  "survives_agreement_floor", "agreement_status",
                  "kappa_primary", "kappa_any_label"):
            print(f"    {k}: {json.dumps(r[k], ensure_ascii=False)}")
        print(f"    addressed_by: {json.dumps(r['addressed_by'], ensure_ascii=False)}")
    print(f"build_order: {json.dumps(order)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
