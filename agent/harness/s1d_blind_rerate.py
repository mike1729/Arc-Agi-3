"""S1-d blind re-rate — draw the stratified sample, blind it, then score agreement.

Implements `gate_manifest.yaml → s1.blind_rerate`, as amended by errata S1-E2/E3/E4.

ORDER MATTERS, and the manifest is explicit about it: **label first, then sample, then blind.**
Stratification is on the first-pass `primary_label`, so a sample set aside *unlabelled* cannot be
stratified and there is nothing to re-rate against.

BLIND TO THE LABELS, NOT TO THE EVIDENCE. Stripping the agent's rationale would delete the sole basis
for `reasoning_inconsistency` and the recorded-goal evidence for `goal_unknown` — the procedure would
remove what its own categories are defined on, and the two passes would rate different material, which
is not an agreement measurement at all.

  strip    first-pass labels, confidences, rater notes
  preserve the complete evidence packet, unchanged, including reasoning text

Oversampling, per S1-E2 as tightened by S1-E4:
  * `goal_unknown`
  * `exploration_or_probe_selection`, but ONLY on episodes whose game exposes no ACTION6 at the rated
    steps — i.e. the six simple-action games. `planning_depth` was the original second stratum and is
    structurally unobservable here, so it was replaced.

The eligible fraction is reported beside the agreement statistic: an agreement number computed on a
subset must say which subset.

Naming: with one rater this is **delayed test-retest** (intra-rater) agreement, not inter-rater
reliability. Cohen's kappa is still the right statistic; the claim it supports is weaker. It bounds
label STABILITY, not correctness — a rater can reproduce a confound identically in both passes.

Usage:
  draw   .venv/bin/python agent/harness/s1d_blind_rerate.py draw  <episodes.json> [--n 30]
  score  .venv/bin/python agent/harness/s1d_blind_rerate.py score <first_pass.json> <rerate.json>
"""

from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

# The six games whose level 1 opens with simple actions only (measured, logs/s2_arc_conventions.json).
SIMPLE_ACTION_GAMES = {
    "g50t-5849a774", "ls20-9607627b", "re86-8af5384d",
    "tr87-cd924810", "tu93-0768757b", "wa30-ee6fef47",
}
OVERSAMPLE = ["goal_unknown", "exploration_or_probe_selection"]
STRIP = ("labels", "primary_label", "rater_notes")
COOLING_PERIOD_HOURS = 48


def eligible_for(cat: str, ep: dict) -> bool:
    """S1-E4: exploration_or_probe_selection needs alternative-action evidence, which does not exist
    when ACTION6 is in the candidate set — the alternative there is a coordinate, not a named action."""
    if cat != "exploration_or_probe_selection":
        return True
    return str(ep.get("game", "")) in SIMPLE_ACTION_GAMES


def draw(episodes_path: Path, n: int, seed: int, out: Path):
    data = json.loads(episodes_path.read_text())
    eps = data.get("episodes") or []
    labelled = [e for e in eps if e.get("primary_label")]
    if not labelled:
        print("NOTHING TO SAMPLE: no episode carries a primary_label.")
        print("The manifest order is label -> sample -> blind. Complete the first pass first.")
        return 2

    rng = random.Random(seed)
    by_label = collections.defaultdict(list)
    for e in labelled:
        by_label[e["primary_label"]].append(e)

    # Oversample the two designated strata, then fill proportionally from the rest.
    picked, picked_ids = [], set()
    for cat in OVERSAMPLE:
        pool = [e for e in by_label.get(cat, []) if eligible_for(cat, e)]
        take = min(len(pool), max(1, n // 3))
        for e in rng.sample(pool, take) if pool else []:
            picked.append(e)
            picked_ids.add(e["episode_id"])
    rest = [e for e in labelled if e["episode_id"] not in picked_ids]
    rng.shuffle(rest)
    picked.extend(rest[: max(0, n - len(picked))])

    blinded = []
    for e in picked:
        b = {k: v for k, v in e.items() if k not in STRIP}
        b["labels"] = []                 # to be filled at re-rate
        b["primary_label"] = None
        b["rater_notes"] = ""
        blinded.append(b)                # `evidence` is carried through UNCHANGED, by construction

    elig = {c: sum(1 for e in labelled if e.get("primary_label") == c and eligible_for(c, e))
            for c in OVERSAMPLE}
    total = {c: sum(1 for e in labelled if e.get("primary_label") == c) for c in OVERSAMPLE}

    payload = {
        "source": str(episodes_path),
        "drawn": len(blinded),
        "seed": seed,
        "cooling_period_hours": COOLING_PERIOD_HOURS,
        "stratified_on": "first-pass primary_label",
        "oversampled": OVERSAMPLE,
        "eligibility": {
            "rule": ("exploration_or_probe_selection is restricted to games with no ACTION6 in the "
                     "candidate set (S1-E4); the six simple-action games"),
            "eligible_of_total": {c: f"{elig[c]}/{total[c]}" for c in OVERSAMPLE},
        },
        "stripped": list(STRIP),
        "preserved": "the complete evidence packet, unchanged, including reasoning text",
        "agreement_type": "delayed test-retest (same rater) — NOT inter-rater reliability",
        "episodes": blinded,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"drew {len(blinded)} of {len(labelled)} labelled episodes")
    for c in OVERSAMPLE:
        print(f"   oversampled {c}: eligible {elig[c]} of {total[c]} first-pass episodes")
    print(f"cooling period: {COOLING_PERIOD_HOURS} h before re-rating")
    print(f"wrote {out}")
    return 0


def kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for two label sequences over the same items."""
    if not a or len(a) != len(b):
        return None
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum((ca[k] / n) * (cb.get(k, 0) / n) for k in ca)
    if pe == 1.0:
        return None
    return round((po - pe) / (1 - pe), 4)


def score(first_path: Path, rerate_path: Path, floor: float):
    first = {e["episode_id"]: e for e in json.loads(first_path.read_text()).get("episodes", [])}
    second = {e["episode_id"]: e for e in json.loads(rerate_path.read_text()).get("episodes", [])}
    common = [i for i in second if i in first and second[i].get("primary_label")]
    if not common:
        print("no re-rated episodes carry a primary_label yet.")
        return 2
    a = [first[i]["primary_label"] for i in common]
    b = [second[i]["primary_label"] for i in common]
    overall = kappa(a, b)
    print(f"re-rated episodes: {len(common)}   overall kappa: {overall}")
    print(f"\n{'category':34s} {'n':>4} {'kappa':>7}  drives build order?")
    per = {}
    for cat in sorted(set(a) | set(b)):
        ai = [("Y" if x == cat else "N") for x in a]
        bi = [("Y" if x == cat else "N") for x in b]
        k = kappa(ai, bi)
        per[cat] = k
        drives = "yes" if (k is not None and k >= floor) else "NO — below the agreement floor"
        print(f"{cat:34s} {sum(1 for x in a if x == cat):>4} {str(k):>7}  {drives}")
    print(f"\nagreement floor: {floor}. Categories below it are reported as unreliable and DO NOT "
          f"drive build order.")
    print("Interpretation limit: this is test-retest agreement, so it bounds label STABILITY, not "
          "correctness.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw"); d.add_argument("episodes"); d.add_argument("--n", type=int, default=30)
    d.add_argument("--seed", type=int, default=20260726); d.add_argument("--out", default="")
    sc = sub.add_parser("score"); sc.add_argument("first"); sc.add_argument("rerate")
    sc.add_argument("--floor", type=float, default=0.40)
    args = ap.parse_args()

    if args.cmd == "draw":
        src = Path(args.episodes)
        out = Path(args.out) if args.out else src.with_name(src.stem + "_blinded.json")
        return draw(src, args.n, args.seed, out)
    return score(Path(args.first), Path(args.rerate), args.floor)


if __name__ == "__main__":
    raise SystemExit(main())
