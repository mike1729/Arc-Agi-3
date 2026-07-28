"""Apply rater label files to a corpus, in place, with the checks that make it auditable.

Labelling happens in batches over a worksheet (`s1d_worksheet.py`), so the labels arrive as separate
JSON files rather than as one edit to the corpus. This merges them and refuses the three ways that can
go wrong silently:

  * an episode_id in a label file that is not in the corpus — a typo or a stale corpus, and if it were
    ignored the label would simply vanish;
  * a primary_label not present in that episode's own `labels` list, which would make `primary_share`
    and `episode_share` disagree about what was observed;
  * a category outside the manifest's labelable set, including the two structurally unobservable ones
    (`coordinate_unreachable`, `planning_depth`), which are never recorded even as zeros.

Each episode records WHICH label file and worksheet produced it, because a frequency table whose
provenance is not per-episode cannot be re-rated selectively later.

Run:
  .venv/bin/python agent/harness/s1d_apply_labels.py logs/s1d_corpus_pooled.json \
      logs/s1d_labels_v3v4_pass1/*.json --worksheet-slice "first1+last2, r1000/c700/t350"
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

LABELABLE = {
    "goal_unknown", "action_semantics_unknown", "perception_parsing",
    "hidden_state_aliasing_or_memory", "exploration_or_probe_selection",
    "progress_signal_misinterpretation", "irreversible_mistake",
    "invalid_output_interface", "retrieval_or_context", "reasoning_inconsistency",
    "latency_or_budget",
}
CONFIDENCES = {"low", "med", "high"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("label_files", nargs="+")
    ap.add_argument("--rater", default="claude-opus-5")
    ap.add_argument("--pass-name", default="first")
    ap.add_argument("--worksheet-slice", default="")
    ap.add_argument("--allow-relabel", action="store_true",
                    help="overwrite an episode that already carries labels (default: refuse)")
    ap.add_argument("--allow-foreign-episodes", action="store_true",
                    help="skip label entries whose episode_id is absent from this corpus, e.g. applying "
                         "a multi-run label file to a single-run corpus. Every skip is printed.")
    a = ap.parse_args()

    corpus_path = Path(a.corpus)
    d = json.loads(corpus_path.read_text())
    by_id = {e["episode_id"]: e for e in d["episodes"]}

    errors, applied = [], 0
    conflicts: set[tuple[str, str, str]] = set()
    skipped: list[str] = []
    for lf in a.label_files:
        labels = json.loads(Path(lf).read_text())
        for eid, rec in labels.items():
            ep = by_id.get(eid)
            if ep is None:
                # Default: an unknown episode_id is a typo or a stale corpus, and ignoring it would
                # make the label vanish silently. But a label file that spans several runs is
                # legitimately a superset of a single-run corpus, so that case is allowed explicitly
                # and every skipped id is printed — permitted, never silent.
                if a.allow_foreign_episodes:
                    skipped.append(f"{Path(lf).name}: {eid}")
                else:
                    errors.append(f"{lf}: episode_id not in corpus — {eid}")
                continue
            if ep.get("labels") and not a.allow_relabel:
                errors.append(f"{lf}: {eid} already labelled; use --allow-relabel to overwrite")
                continue
            cats = [x["category"] for x in rec["labels"]]
            bad = [c for c in cats if c not in LABELABLE]
            if bad:
                errors.append(f"{lf}: {eid} has non-labelable categories {bad}")
            badconf = [x for x in rec["labels"] if x.get("confidence") not in CONFIDENCES]
            if badconf:
                errors.append(f"{lf}: {eid} has confidences outside {sorted(CONFIDENCES)}")
            if len(set(cats)) != len(cats):
                errors.append(f"{lf}: {eid} repeats a category")
            if rec["primary_label"] not in cats:
                errors.append(f"{lf}: {eid} primary_label {rec['primary_label']!r} "
                              f"is not among its own labels {cats}")
            if errors and errors[-1].startswith(f"{lf}: {eid}"):
                continue
            ep["labels"] = rec["labels"]
            ep["primary_label"] = rec["primary_label"]
            ep["rater_notes"] = rec.get("rater_notes")
            # PROVENANCE RECORDED IN THE LABEL FILE WINS OVER THE COMMAND LINE. A label file may carry
            # its own `labelling` block — v2's records `worksheet: "AD HOC (pre-dates
            # s1d_worksheet.py)"`, which is true and cannot be re-derived. Overwriting it with a single
            # CLI `--worksheet-slice` stamped every pooled episode with the scripted slice, including
            # 25 that were never rated under it, so the corpus asserted a uniform method it did not
            # have. The CLI now supplies DEFAULTS for files that record nothing, never overrides.
            rec_prov = rec.get("labelling") or {}
            cli_ws = a.worksheet_slice or "unspecified"
            ep["labelling"] = {
                "pass": rec_prov.get("pass", a.pass_name),
                "rater": rec_prov.get("rater", a.rater),
                "worksheet": rec_prov.get("worksheet", cli_ws),
                "source": Path(lf).name,
                "provenance": "from label file" if rec_prov else "from command line",
            }
            if rec_prov.get("worksheet") and a.worksheet_slice \
                    and rec_prov["worksheet"] != a.worksheet_slice:
                conflicts.add((Path(lf).name, rec_prov["worksheet"], a.worksheet_slice))
            applied += 1

    if errors:
        print("REFUSED — nothing written:")
        for e in errors:
            print(f"  {e}")
        return 1

    if skipped:
        print(f"skipped {len(skipped)} label entr{'y' if len(skipped)==1 else 'ies'} not in this corpus:")
        for sk in skipped:
            print(f"  {sk}")

    for fname, in_file, on_cli in sorted(conflicts):
        print(f"NOTE {fname}: kept the file's worksheet {in_file!r}, ignored --worksheet-slice "
              f"{on_cli!r}. The file's record is the one that was actually used.")

    from s1d_label import frequencies
    labelled = [e for e in d["episodes"] if e.get("labels")]
    d["frequencies"] = frequencies(labelled)
    d["labelled_count"] = len(labelled)
    corpus_path.write_text(json.dumps(d, indent=2) + "\n")
    print(f"applied {applied} label sets · corpus now {len(labelled)}/{len(d['episodes'])} labelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
