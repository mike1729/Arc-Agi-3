"""Apply rater labels to the goal-predicate corpus, with the checks that make it auditable.

Mirrors `s1d_apply_labels.py`: labels arrive as a separate file rather than as an edit to the corpus,
each record records which label file produced it, and the merge refuses the ways it can go wrong
quietly:

  * an env in the label file that is not in the corpus — a typo or a stale corpus, and ignoring it
    would make the label vanish rather than fail;
  * a predicate class outside the pre-specified codebook, which would let a frequency table grow a
    category nobody registered;
  * an empty class list, which is not a label but an omission, and would otherwise be counted as a
    labelled record with no classes and silently deflate every share.

The taxonomy is the ten classes defined in `docs/arc-agi-3-screening-experiments-and-results.md`,
appendix "evaluation apparatus" — the definition site, and EVIDENTIARY rather than normative: the
implementation spec neither defines nor references it, so it binds this labelling and nothing else.
It is a PRE-SPECIFIED CLOSED CODEBOOK, not a pre-registered instrument: fixed in advance and unchanged
since, but never entered in `gate_manifest.yaml`, where `s2` is still `NOT_STARTED`. Frequencies
computed here must carry that open pre-registration as a stated limitation.
It previously cited `arc-agi-3-agent-architecture.md` §5.2; that document was archived on 2026-07-28
and `docs/archive/README.md` says archived documents must not be cited, which left a closed,
pre-specified class list with no citable definition. The list is unchanged by the relocation, which
is registered as `DOCS-TAXONOMY-2026-07-28` in `docs/README.md`. Closed on
purpose. A predicate that does not fit is labelled `outside_taxonomy` — recorded, counted, and
reported separately — because a taxonomy that quietly absorbs everything cannot be found wrong, and
"the class library is incomplete" is a result worth having before the induction machinery is built.

The corpus emitted by `s2_goal_predicates.py` is per GAME, not per level. Cross-level transfer is
parameterized (the same family with different targets, regions and orderings), so a class frequency
here is a frequency over games, and must not be reported as a frequency over levels.

Run:
  python3 agent/harness/s2_apply_labels.py logs/s2_goal_predicates.json logs/s2_labels_pass1.json
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

TAXONOMY = {
    "state_relations",
    "quantified_object_conditions",
    "counts",
    "region_membership",
    "symmetry_and_template_match",
    "all_instances_transformed",
    "event_occurrence",
    "ordered_event_programs",
    "action_conditioned_terminal_triggers",
    "cumulative_counters",
}
ESCAPE = "outside_taxonomy"

# The structural shape of the advance guard, recorded alongside the class because it is a separate
# fact about how hard the predicate is to OBSERVE, as opposed to how hard it is to represent.
GUARD_FORMS = {"inline", "delegated", "instance_flag", "guard_clause", "deferred_animation"}


def apply(corpus_path: Path, label_paths: list[Path], out: Path) -> int:
    corpus = json.loads(corpus_path.read_text())
    records = {r["env"]: r for r in corpus["records"] if "error" not in r}

    # A label is a judgment about a specific packet, so it is only valid against the packet it was
    # read from. Re-extracting the corpus and re-applying old labels produces an artifact that looks
    # labelled and is not: the rater never saw this evidence. The re-rate scorer has the same
    # exposure and closes it by binding worksheet digests to the corpus; this is the label-path twin.
    # A label file with no recorded digest is not rejected — it predates the check — but it cannot
    # be called verified either, and says so.
    from s2_blind_rerate import item_digest
    digests = {env: item_digest(r) for env, r in records.items()}

    problems, applied, unverified = [], 0, []
    for lp in label_paths:
        labels = json.loads(lp.read_text())
        rater = labels.get("rater")
        for env, lab in labels["labels"].items():
            if env not in records:
                problems.append(f"{lp.name}: env {env} not in corpus")
                continue
            classes = lab.get("predicate_classes") or []
            if not classes:
                problems.append(f"{lp.name}: {env} has no predicate_classes")
                continue
            bad = [c for c in classes if c not in TAXONOMY and c != ESCAPE]
            if bad:
                problems.append(f"{lp.name}: {env} has classes outside the taxonomy: {bad}")
                continue
            form = lab.get("guard_form")
            if form is not None and form not in GUARD_FORMS:
                problems.append(f"{lp.name}: {env} has unknown guard_form {form!r}")
                continue
            declared = lab.get("packet_digest")
            if declared is None:
                unverified.append(env)
            elif declared != digests[env]:
                problems.append(f"{lp.name}: {env} was labelled against packet {declared}, corpus "
                                f"now has {digests[env]} — re-extracted since. Re-label {env}.")
                continue
            records[env]["label"] = {
                "predicate_classes": classes,
                "primary": classes[0],
                "guard_form": form,
                "notes": lab.get("notes", ""),
                "rater": rater,
                "label_file": lp.name,
                "packet_digest": digests[env],
                "packet_verified": lab.get("packet_digest") is not None,
            }
            applied += 1

    if problems:
        print(f"REFUSED — {len(problems)} problem(s), nothing written:")
        for p in problems:
            print(f"   {p}")
        return 1

    labelled = [r for r in records.values() if r["label"]["predicate_classes"]]
    corpus["unlabelled"] = len(records) - len(labelled)

    # Two frequencies, because they answer different questions. `primary_share` ranks what the
    # predicate mainly IS; `any_share` counts every class a rater judged present, so a class that is
    # never primary but pervasive as a component does not read as absent.
    primary = collections.Counter(r["label"]["primary"] for r in labelled)
    any_cls = collections.Counter(c for r in labelled for c in r["label"]["predicate_classes"])
    forms = collections.Counter(r["label"].get("guard_form") for r in labelled)
    corpus["frequencies"] = {
        "n_games": len(labelled),
        "primary": dict(primary.most_common()),
        "any": dict(any_cls.most_common()),
        "guard_forms": dict(forms.most_common()),
        "unused_classes": sorted(TAXONOMY - set(any_cls)),
    }
    corpus["labels_packet_verified"] = not unverified
    corpus["labels_unverified_envs"] = sorted(unverified)
    out.write_text(json.dumps(corpus, indent=1) + "\n")

    print(f"applied {applied} label(s); {corpus['unlabelled']} still unlabelled")
    if unverified:
        print(f"\nWARNING — {len(unverified)} label(s) carry no packet_digest, so it CANNOT be "
              f"verified that\nthe rater saw the evidence now in the corpus. Treat as provisional "
              f"and re-label if the\nextraction has changed since. Affected: "
              f"{', '.join(unverified[:8])}{' ...' if len(unverified) > 8 else ''}")
    print()
    print(f"{'predicate class':<38}{'primary':>9}{'any':>6}")
    for c in sorted(TAXONOMY | {ESCAPE}, key=lambda c: (-any_cls[c], c)):
        if any_cls[c] or primary[c]:
            print(f"{c:<38}{primary[c]:>9}{any_cls[c]:>6}")
    unused = corpus["frequencies"]["unused_classes"]
    if unused:
        print(f"\nclasses with ZERO occurrences across all {len(labelled)} games:")
        for c in unused:
            print(f"   {c}")
        print("   -> a pre-specified class the public set never exercises. Not evidence it is rare "
              "in the hidden set;\n      it is evidence this corpus cannot rank it.")
    print(f"\nguard forms: {dict(forms.most_common())}")
    print(f"wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--out", default="logs/s2_goal_predicates_labelled.json")
    args = ap.parse_args()
    return apply(Path(args.corpus), [Path(p) for p in args.labels], Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
