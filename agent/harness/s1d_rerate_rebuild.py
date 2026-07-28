"""S1-d — rebuild the two large re-rate artifacts from tracked inputs, and verify them.

WHY THESE TWO FILES ARE NOT IN GIT
----------------------------------
`logs/s1d_rerate_draw.json` and `logs/s1d_rerate_pass2.json` are ~5 MB each because each carries the
complete evidence packet for 30 episodes — the reference model's reasoning text, verbatim. The corpus
they come from is already tracked and is the same material; adding two more copies of it buys nothing
and doubles the reference-derived content in the history, which `PUBLISHING.md` treats as
redistribution that deleting later does not undo.

Neither file contains anything that cannot be recomputed:

  draw   = select(pooled corpus, n, seed) then blind      — deterministic in (corpus, n, seed)
  pass2  = draw + the second pass's labels                — the labels are the only new information

So the LABELS are tracked (`logs/s1d_labels_rerate_pass2.json`, ~30 KB, the same bucket as
`s1d_labels_v3v4_pass1/`) and the packets are rebuilt from the corpus on demand.

WHY THIS IS A SCRIPT AND NOT A README PARAGRAPH
-----------------------------------------------
`logs/s1d_rerate_result.json` records a SHA-256 for each of its three inputs. A rebuild that produced
subtly different bytes — a different `json.dumps` separator, a re-ordered key — would leave the
promoted gate result pointing at hashes nothing on disk matches, and the failure would surface as an
unverifiable gate months later rather than here. `--verify` compares the rebuilt bytes against the
hashes the promoted result committed to, so the rebuild is checked rather than assumed.

  .venv/bin/python agent/harness/s1d_rerate_rebuild.py            # rebuild both files
  .venv/bin/python agent/harness/s1d_rerate_rebuild.py --verify   # rebuild and check against the gate

`--verify` exits non-zero on any mismatch. It is the check to run in a fresh clone before trusting
`logs/s1d_rerate_result.json`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s1d_blind_rerate import (  # noqa: E402
    AGREEMENT_TYPE, OVERSAMPLE, STRIP, blind_episode, corpus_digest, eligible_for,
    episode_digest, manifest_path_for, select,
)

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "logs" / "s1d_corpus_pooled.json"
LABELS = REPO / "logs" / "s1d_labels_rerate_pass2.json"
DRAW = REPO / "logs" / "s1d_rerate_draw.json"
SIDECAR = REPO / "logs" / "s1d_rerate_draw.manifest.json"
PASS2 = REPO / "logs" / "s1d_rerate_pass2.json"
GATE = REPO / "logs" / "s1d_rerate_result.json"


def rebuild() -> tuple[bytes, bytes]:
    """Reproduce the draw and the re-rated pass, byte-for-byte, from tracked inputs."""
    labels_doc = json.loads(LABELS.read_text())
    params = labels_doc["draw_parameters"]
    n, seed = params["requested"], params["seed"]
    # `draw` recorded `source` as the string it was INVOKED with, so an absolute path here produces
    # different bytes from a run launched with a relative one — a one-field difference that changes
    # the whole file's hash. The sidecar is the committed record of what that string was; take it
    # from there rather than reconstructing it and hoping the working directory matches.
    source = json.loads(SIDECAR.read_text())["drawn_from"]

    data = json.loads(CORPUS.read_bytes())
    labelled = [e for e in (data.get("episodes") or []) if e.get("primary_label")]
    picked = select(labelled, n, seed)
    blinded = [blind_episode(e) for e in picked]

    elig = {c: sum(1 for e in labelled if e.get("primary_label") == c and eligible_for(c, e))
            for c in OVERSAMPLE}
    total = {c: sum(1 for e in labelled if e.get("primary_label") == c) for c in OVERSAMPLE}

    # Field-for-field as `draw` wrote it. Any divergence here shows up as a hash mismatch under
    # --verify rather than as a file that merely looks right.
    payload = {
        "source": source,
        "drawn": len(blinded),
        "requested": n,
        "sample_manifest_advisory": {e["episode_id"]: episode_digest(e) for e in blinded},
        "sample_manifest_note": (f"ADVISORY ONLY. The authoritative manifest is "
                                 f"{manifest_path_for(DRAW).name}, which `score` reads instead."),
        "short_draw": len(blinded) < n,
        "short_draw_note": None,
        "seed": seed,
        "cooling_period_hours": None,
        "cooling_period_status": ("INAPPLICABLE per S1-E10 — the rater is an LLM with no cross-session "
                                  "memory; there is nothing to decay. Not reported as satisfied."),
        "stratified_on": "first-pass primary_label",
        "oversampled": OVERSAMPLE,
        "eligibility": {
            "rule": ("exploration_or_probe_selection is restricted to games with no ACTION6 in the "
                     "candidate set (S1-E4); the six simple-action games"),
            "eligible_of_total": {c: f"{elig[c]}/{total[c]}" for c in OVERSAMPLE},
        },
        "stripped": list(STRIP),
        "preserved": "the complete evidence packet, unchanged, including reasoning text",
        "agreement_type": AGREEMENT_TYPE,
        "episodes": blinded,
    }
    draw_bytes = (json.dumps(payload, indent=2) + "\n").encode()

    ratings = labels_doc["ratings"]
    for e in payload["episodes"]:
        r = ratings[e["episode_id"]]
        e["labels"] = r["labels"]
        e["primary_label"] = r["primary_label"]
        e["rater_notes"] = r.get("rater_notes", "")
    payload["rerate_provenance"] = labels_doc["rerate_provenance"]
    pass2_bytes = (json.dumps(payload, indent=2) + "\n").encode()
    return draw_bytes, pass2_bytes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="check the rebuild against the hashes the promoted gate result recorded")
    a = ap.parse_args()

    draw_bytes, pass2_bytes = rebuild()

    if a.verify:
        gate = json.loads(GATE.read_text())
        want = gate.get("inputs") or {}
        got = {"rerate": hashlib.sha256(pass2_bytes).hexdigest(),
               "first_pass": hashlib.sha256(CORPUS.read_bytes()).hexdigest()}
        problems = [f"{k}: gate records {want[k]['sha256']}, rebuild produces {v}"
                    for k, v in got.items()
                    if k in want and want[k]["sha256"] != v]
        if problems:
            print("REBUILD DOES NOT MATCH THE PROMOTED GATE RESULT:")
            for p in problems:
                print(f"    {p}")
            return 1
        print(f"rebuild matches {GATE.name} on {', '.join(sorted(got))} — "
              f"the promoted gate result is verifiable from tracked inputs alone")
        return 0

    DRAW.write_bytes(draw_bytes)
    PASS2.write_bytes(pass2_bytes)
    print(f"wrote {DRAW.relative_to(REPO)} and {PASS2.relative_to(REPO)} "
          f"({len(json.loads(pass2_bytes)['episodes'])} episodes). "
          f"Run with --verify to check them against the promoted gate result.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
