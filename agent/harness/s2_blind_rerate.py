"""S2 goal-predicate blind re-rate — blind the corpus, then score agreement against pass 1.

Follows the S1-d procedure (`s1d_blind_rerate.py`) and inherits its correction S1-E10 verbatim: the
first pass was rated by an LLM, not a human, so this is an **independent re-rate, same model** — not a
delayed test-retest. A fresh context has no memory to decay, which makes the second pass blinder than
a human retest while measuring a different quantity. Cohen's kappa is still the right statistic and
still bounds label STABILITY, never correctness: a rater can reproduce a confound identically twice,
and one LLM rating another's reading of obfuscated source may share systematic blind spots. Do not
compare this kappa against a literature expecting human test-retest, and do not report a cooling
period — there is none and the concept does not apply.

NO SAMPLING. S1-d drew a stratified sample because its corpus was larger than the re-rate budget.
This corpus is 25 games. The whole of it is re-rated, so there is no stratum to declare, no
eligibility fraction to qualify the statistic with, and no sampling variance on top of rater variance.

BLIND TO THE LABELS, NOT TO THE EVIDENCE
----------------------------------------
    strip      predicate_classes, primary, guard_form, notes, rater  (everything pass 1 produced)
    preserve   guard_tests, preconditions, flag_sites, resolved_methods, features, evidence

Stripping the evidence would leave the two passes rating different material, which is not an
agreement measurement. Stripping less than the whole label leaks the answer: `notes` in particular
states the predicate in English, so a re-rate that saw it would measure reading comprehension.

Items are also given opaque ids and shuffled under a fixed seed. The environment name carries no
information to a rater who has not seen this corpus, but ordering does — pass 1 was rated in
alphabetical order, and an item's neighbours are a weak cue to its own class.

DIGEST PROTECTION
-----------------
Every blinded item carries a digest over EVERYTHING shown to the rater, not just `evidence`. The
classes here turn on `guard_tests` and `flag_sites` as much as on the source text, so a rewritten
packet with untouched evidence would change the basis of the rating without changing what was
checked. Scoring recomputes the digest and refuses on any mismatch rather than reporting agreement
between passes that read different things.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
from pathlib import Path

from s2_apply_labels import ESCAPE, GUARD_FORMS, TAXONOMY

SHOWN = ("guard_tests", "preconditions_from_early_returns", "flag_sites",
         "resolved_methods", "features", "evidence", "enclosing_function", "advance_line")
SEED = 20260728


def item_digest(item: dict) -> str:
    payload = {k: item[k] for k in SHOWN if k in item}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def worksheet_id(items: list) -> str:
    """Identity of one drawn worksheet: its item ids paired with the packets they showed.

    Item ids are positional (`g00`..`g24`) and therefore identical across every draw, so a ratings
    file keyed by them fits ANY worksheet of the same size. Nothing tied a submitted second pass to
    the worksheet it was actually produced from: ratings made against the superseded extraction
    scored cleanly against the corrected one and reported kappa 0.659, while 17 of the 25 evidence
    packets had changed underneath. The two passes were rating different material and the statistic
    could not tell.
    """
    payload = [[i["item_id"], i["digest"]] for i in items]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def draw(corpus_path: Path, out: Path) -> int:
    corpus = json.loads(corpus_path.read_text())
    records = [r for r in corpus["records"] if "error" not in r]
    items = []
    for r in records:
        item = {k: r[k] for k in SHOWN if k in r}
        item["digest"] = item_digest(item)
        item["_env"] = r["env"]          # stripped from the rater's copy below
        items.append(item)
    rng = random.Random(SEED)
    rng.shuffle(items)
    for i, item in enumerate(items):
        item["item_id"] = f"g{i:02d}"

    key = {item["item_id"]: item.pop("_env") for item in items}
    wid = worksheet_id(items)
    worksheet = {
        "worksheet_id": wid,
        "instructions": (
            "Assign predicate classes to each item from the closed taxonomy below, primary first. "
            "Each item is the level-advance condition of one interactive environment, extracted from "
            "its source. Use `outside_taxonomy` if and only if no class fits. Also record guard_form: "
            "how the condition is reached from the advance site. "
            "SUBMIT YOUR RATINGS IN THE TEMPLATE WRITTEN BESIDE THIS FILE — it carries the "
            "worksheet_id and per-item digests that bind your pass to this exact worksheet."),
        "taxonomy": sorted(TAXONOMY) + [ESCAPE],
        "guard_forms": sorted(GUARD_FORMS),
        "n_items": len(items),
        "items": items,
    }
    out.write_text(json.dumps(worksheet, indent=1) + "\n")
    (out.with_name(out.stem + ".key.json")).write_text(
        json.dumps({"worksheet_id": wid, "key": key}, indent=1) + "\n")

    # A PRE-FILLED TEMPLATE, so the binding costs the rater nothing. Asking a rater to copy 25
    # digests by hand would be its own failure mode; emitting them here means a submitted pass
    # carries its provenance by construction rather than by discipline.
    template = {
        "worksheet_id": wid,
        "drawn_from": str(corpus_path),
        "pass": "second",
        "raters": "<model id — must match the first pass>",
        "dated": "<YYYY-MM-DD>",
        "note": ("Fill `predicate_classes` (primary first), `guard_form` and `notes` for each item. "
                 "Leave `worksheet_id` and each `item_digest` untouched: `score` refuses a pass whose "
                 "binding does not match the worksheet it is scored against."),
        "ratings": {i["item_id"]: {"item_digest": i["digest"], "predicate_classes": [],
                                   "guard_form": None, "notes": ""} for i in items},
    }
    tpath = out.with_name(out.stem + ".ratings-template.json")
    tpath.write_text(json.dumps(template, indent=1) + "\n")

    print(f"blinded {len(items)} items -> {out}")
    print(f"worksheet_id {wid} — a ratings file must carry it to be scorable against this worksheet")
    print(f"ratings template (give THIS to the rater to fill) -> {tpath}")
    print(f"id->env key (DO NOT give this to the rater) -> {out.with_name(out.stem + '.key.json')}")
    return 0


def _kappa(a: list[str], b: list[str]) -> tuple[float, float, float]:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = collections.Counter(a), collections.Counter(b)
    pe = sum(ca[c] / n * cb[c] / n for c in set(a) | set(b))
    return (po - pe) / (1 - pe) if pe != 1 else float("nan"), po, pe


def score(first_path: Path, worksheet_path: Path, rerate_path: Path, out: Path) -> int:
    first = {r["env"]: r for r in json.loads(first_path.read_text())["records"] if "error" not in r}
    worksheet = json.loads(worksheet_path.read_text())
    key = json.loads(worksheet_path.with_name(worksheet_path.stem + ".key.json").read_text())
    rerate = json.loads(rerate_path.read_text())
    shown = {i["item_id"]: i for i in worksheet["items"]}
    # The key file gained a wrapper when worksheet_id was added; accept either shape.
    if isinstance(key, dict) and "key" in key and "worksheet_id" in key:
        key_wid, key = key["worksheet_id"], key["key"]
    else:
        key_wid = None

    problems = []

    # BIND THE SUBMITTED PASS TO THIS WORKSHEET. Everything below verifies the worksheet against the
    # corpus; none of it says the RATINGS came from this worksheet. Item ids are positional and
    # identical across draws, so a ratings file fits any worksheet of the same size — ratings made
    # against the superseded extraction scored against the corrected one at kappa 0.659 while 17 of
    # 25 packets had changed. Two passes rating different material is not an agreement measurement.
    expected_wid = worksheet.get("worksheet_id") or worksheet_id(worksheet["items"])
    declared = rerate.get("worksheet_id")
    if declared is None:
        problems.append(
            "the ratings file records no `worksheet_id`, so it cannot be shown to have been produced "
            "from this worksheet. Re-rate using the `.ratings-template.json` emitted by `draw`.")
    elif declared != expected_wid:
        problems.append(
            f"ratings were produced against worksheet {declared}, but this is worksheet "
            f"{expected_wid}. They rate different material; kappa between them measures nothing.")
    if key_wid is not None and key_wid != expected_wid:
        problems.append(f"the id->env key belongs to worksheet {key_wid}, not {expected_wid}")
    for item_id, item in shown.items():
        # Two DIFFERENT checks, and the first alone is worthless. Recomputing an item's digest from
        # the item proves only that the worksheet is internally consistent — it is trivially true of
        # any self-consistent file, including one drawn from a corpus that has since been re-extracted
        # and one whose id->env key has been permuted. Kappa would still compute, and would still look
        # plausible, while comparing each second-pass rating against a first-pass label for a
        # different environment. The binding check is the one that matters.
        if item_digest(item) != item["digest"]:
            problems.append(f"{item_id}: digest mismatch — worksheet altered after drawing")
            continue
        env = key.get(item_id)
        if env is None:
            problems.append(f"{item_id}: absent from the id->env key")
        elif env not in first:
            problems.append(f"{item_id}: key maps to {env}, which is not in the first-pass corpus")
        elif item_digest(first[env]) != item["digest"]:
            problems.append(
                f"{item_id}: worksheet does not match first-pass record for {env} — the corpus was "
                f"re-extracted or the key was permuted after drawing. Re-draw and re-rate.")
    missing = sorted(set(shown) - set(rerate["ratings"]))
    if missing:
        problems.append(f"{len(missing)} item(s) unrated: {missing[:8]}")
    for item_id, rating in rerate["ratings"].items():
        if item_id not in shown:
            problems.append(f"{item_id}: not in the worksheet")
            continue
        cls = rating.get("predicate_classes") or []
        bad = [c for c in cls if c not in TAXONOMY and c != ESCAPE]
        if bad:
            problems.append(f"{item_id}: classes outside the taxonomy: {bad}")
        if not cls:
            problems.append(f"{item_id}: no predicate_classes")
        # Per item as well as per worksheet, so a pass spliced together from two worksheets is
        # caught even when the worksheet_id it declares happens to be right.
        rd = rating.get("item_digest")
        if rd is not None and rd != shown[item_id]["digest"]:
            problems.append(
                f"{item_id}: rated against packet {rd}, this worksheet shows {shown[item_id]['digest']}")
    if problems:
        print(f"REFUSED — {len(problems)} problem(s), nothing scored:")
        for p in problems[:12]:
            print(f"   {p}")
        return 1

    rows = []
    for item_id, rating in sorted(rerate["ratings"].items()):
        env = key[item_id]
        f = first[env]["label"]
        r_cls = rating["predicate_classes"]
        rows.append({
            "env": env,
            "item_id": item_id,
            "first_primary": f["primary"],
            "rerate_primary": r_cls[0],
            "first_classes": sorted(f["predicate_classes"]),
            "rerate_classes": sorted(r_cls),
            "first_guard_form": f.get("guard_form"),
            "rerate_guard_form": rating.get("guard_form"),
        })

    k, po, pe = _kappa([r["first_primary"] for r in rows], [r["rerate_primary"] for r in rows])
    exact_set = sum(r["first_classes"] == r["rerate_classes"] for r in rows) / len(rows)
    jac = sum(len(set(r["first_classes"]) & set(r["rerate_classes"])) /
              len(set(r["first_classes"]) | set(r["rerate_classes"])) for r in rows) / len(rows)
    gf = [r for r in rows if r["rerate_guard_form"]]
    gf_agree = (sum(r["first_guard_form"] == r["rerate_guard_form"] for r in gf) / len(gf)) if gf else None
    # A class the second pass never uses is not disagreement spread thin — it is one rater's category
    # going unused, which moves kappa without any item being read differently.
    first_only = sorted({r["first_primary"] for r in rows} - {r["rerate_primary"] for r in rows})
    rerate_only = sorted({r["rerate_primary"] for r in rows} - {r["first_primary"] for r in rows})

    disagreements = [r for r in rows if r["first_primary"] != r["rerate_primary"]]
    result = {
        "n": len(rows),
        "sampling": "none — the whole 25-game corpus was re-rated",
        "procedure": "independent re-rate, same model, fresh context (S1-E10). Bounds label "
                     "stability, not correctness. No cooling period applies.",
        "raters_second_pass": rerate.get("raters"),
        "primary_kappa": round(k, 3),
        "primary_observed_agreement": round(po, 3),
        "primary_expected_agreement": round(pe, 3),
        "full_set_exact_agreement": round(exact_set, 3),
        "mean_jaccard_over_class_sets": round(jac, 3),
        "guard_form_agreement": None if gf_agree is None else round(gf_agree, 3),
        "primary_classes_used_by_first_pass_only": first_only,
        "primary_classes_used_by_rerate_only": rerate_only,
        "disagreements": disagreements,
        "rows": rows,
    }
    out.write_text(json.dumps(result, indent=1) + "\n")

    print(f"n = {len(rows)} (whole corpus, no sampling)\n")
    print(f"primary-class Cohen's kappa      {k:.3f}   (observed {po:.3f}, expected {pe:.3f})")
    print(f"full class-set exact agreement   {exact_set:.3f}")
    print(f"mean Jaccard over class sets     {jac:.3f}")
    if gf_agree is not None:
        print(f"guard_form agreement             {gf_agree:.3f}")
    if first_only or rerate_only:
        print(f"\nprimary classes used by only one pass: first={first_only} rerate={rerate_only}")
    print(f"\n{len(disagreements)} primary disagreement(s):")
    for d in disagreements:
        print(f"   {d['env']}: pass1={d['first_primary']}  rerate={d['rerate_primary']}")
        print(f"        sets  pass1={d['first_classes']}\n              rerate={d['rerate_classes']}")
    print(f"\nwrote {out}")
    print("\nkappa here bounds STABILITY of the labelling, not its correctness — same model family, "
          "shared blind spots\npossible (S1-E10). A human re-rate remains outstanding.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw")
    d.add_argument("corpus")
    d.add_argument("--out", default="logs/s2_rerate_worksheet.json")
    s = sub.add_parser("score")
    s.add_argument("first")
    s.add_argument("worksheet")
    s.add_argument("rerate")
    s.add_argument("--out", default="logs/s2_rerate_result.json")
    a = ap.parse_args()
    if a.cmd == "draw":
        return draw(Path(a.corpus), Path(a.out))
    return score(Path(a.first), Path(a.worksheet), Path(a.rerate), Path(a.out))


if __name__ == "__main__":
    raise SystemExit(main())
