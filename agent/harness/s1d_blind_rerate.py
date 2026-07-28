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

Naming, as corrected by S1-E10: the first pass was rated by an LLM (claude-opus-5), not a human, so
this is an **independent re-rate, same model** — NOT `delayed test-retest`. A fresh context has no
memory to decay, which makes the second pass blinder than the pre-registered procedure but measures a
different quantity. `cooling_period_hours: 48` is INAPPLICABLE and must not be reported as satisfied.
Cohen's kappa is still the right statistic; the claim it supports is weaker. It bounds label
STABILITY, not correctness — a rater can reproduce a confound identically in both passes, and an LLM
rating another LLM's reasoning may share systematic blind spots (S1-E10 `shared_failure_modes`).
Do not compare this kappa against a literature expecting human test-retest.

Usage — the four steps, in order. Copy-pasteable; the `score` line previously omitted the mandatory
`--result-out` and produced an argparse error.

  1. draw the sample. Writes the blinded file AND a `.manifest.json` sidecar beside it; keep both.
       .venv/bin/python agent/harness/s1d_blind_rerate.py draw \
           logs/s1d_corpus_pooled.json --n 30 --out logs/s1d_rerate_draw.json

  2. re-rate `logs/s1d_rerate_draw.json` IN A FRESH CONTEXT that has not seen the first pass, filling
     `labels` / `primary_label` and adding:
       "rerate_provenance": {"rater": "<same model as the first pass>",
                             "context": "fresh session, no access to the first pass",
                             "date": "YYYY-MM-DD"}

  3. score it to a PER-RUN path. `--result-out` is mandatory and may not be the canonical file.
       .venv/bin/python agent/harness/s1d_blind_rerate.py score \
           logs/s1d_corpus_pooled.json logs/s1d_rerate_draw.json \
           --manifest logs/s1d_rerate_draw.manifest.json \
           --result-out logs/s1d_rerate_run1.json

  4. if that reports `gate_valid: true`, promote it. Promotion RE-SCORES the inputs it names and
     installs the recomputed artifact as the canonical result the manifest roll-ups are filled from.
       .venv/bin/python agent/harness/s1d_blind_rerate.py promote logs/s1d_rerate_run1.json

  To withdraw a promoted verdict (superseded corpus, retracted re-rate):
       .venv/bin/python agent/harness/s1d_blind_rerate.py invalidate "<reason>" --detail "<...>"
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import datetime
import fcntl
import hashlib
import io
import json
import os
import random
import re
import tempfile
from pathlib import Path


# The fields the rater is asked to FILL IN. Everything else in a blinded episode is material shown to
# them, so everything else is covered by the digest.
RATER_FILLED = ("labels", "primary_label", "rater_notes")


def episode_digest(ep: dict) -> str:
    """A stable fingerprint of EVERYTHING the rater is shown, not just `evidence`.

    Hashing `evidence` alone left the rest of the packet unprotected, and the rest of the packet is
    not decoration: `latency_or_budget` is decided on `censored_at_seconds` and `budget_terminated`,
    and the action-ratio categories are decided on `actions_taken` and `human_baseline`. An artifact
    could rewrite all of those, leave `evidence` untouched, and score — changing the basis of the
    rating without changing the one field that was checked.
    """
    payload = {k: v for k, v in ep.items() if k not in RATER_FILLED}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _rel(p: Path) -> str:
    """Path recorded in an artifact: repo-relative where possible, else absolute.

    Anchored to the repository so a result stays promotable from a clone or a relocated checkout,
    which an absolute path is not. Falls back to absolute for inputs genuinely outside the repo
    (a scratch directory during development) — those are machine-specific by nature, and saying so
    is better than recording a `../../..` chain that resolves somewhere unrelated elsewhere.
    """
    rp = p.resolve()
    try:
        return str(rp.relative_to(_REPO_ROOT))
    except ValueError:
        return str(rp)


def _resolve_recorded(path_str: str) -> Path:
    """Inverse of `_rel`: interpret a recorded path against the repository, never against CWD."""
    p = Path(path_str)
    return p if p.is_absolute() else (_REPO_ROOT / p)


def manifest_path_for(p: Path) -> Path:
    return p.with_name(p.stem + ".manifest.json")


class CanonicalWriteRefused(Exception):
    """Raised when anything but `promote` tries to write the canonical gate result."""


def _read_canonical_lineage() -> tuple[list, dict | None]:
    """(chain_before, summary_of_current) for whatever is on the canonical path right now.

    Call INSIDE `canonical_lock()`. Shared by `promote` and `invalidate` so the two cannot drift into
    recording lineage differently — they had duplicate copies of this, which is how one of them ended
    up carrying the chain forward and the other not.
    """
    if not CANONICAL_RESULT.exists():
        return [], None
    raw = CANONICAL_RESULT.read_bytes()
    try:
        prev = json.loads(raw)
    except ValueError:
        prev = {}
    summary = {
        "sha256": _sha256(raw),
        "result_kind": prev.get("result_kind"),
        "gate_valid": prev.get("gate_valid"),
        "promoted_from": prev.get("promoted_from"),
        "categories_driving_build_order": prev.get("categories_driving_build_order"),
        "n_episodes": prev.get("n_episodes"),
        "inputs": prev.get("inputs"),
        "invalidated_at": prev.get("invalidated_at"),
    }
    chain = prev.get("invalidation_chain")
    return (chain if isinstance(chain, list) else []), summary


@contextlib.contextmanager
def canonical_lock():
    """Hold an exclusive lock across a whole read-modify-replace of the canonical result.

    Unique temp files made each individual write atomic, which stops a torn file but not a LOST
    UPDATE: `promote` and `invalidate` both read the canonical file, build the new lineage from what
    they read, and only then replace it. Interleaved, an invalidation that had read score A would
    overwrite a promotion of B while recording A as its predecessor — B silently gone, and the
    history actively wrong rather than merely incomplete. The whole transaction has to be serialised,
    not just its final write.

    The lock file sits beside the canonical result and is never deleted; unlinking it would let two
    processes hold locks on different inodes and believe they were excluded.
    """
    CANONICAL_RESULT.parent.mkdir(parents=True, exist_ok=True)
    lock_path = CANONICAL_RESULT.with_name(CANONICAL_RESULT.name + ".lock")
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _write_result(path: Path, payload: dict, *, promoting: bool = False) -> None:
    """Atomically replace a result file. Never leave a half-written one behind.

    ENFORCED HERE, NOT IN `main()`. The canonical-path check lived in the CLI wrapper, so calling
    `score(..., result_out=CANONICAL_RESULT)` as a library — which the tests and the other harness
    modules do — walked straight past it. An invariant that only holds when you come in through
    argparse is not an invariant; this is the single choke point every write passes through.
    """
    if not promoting and path.resolve() == CANONICAL_RESULT.resolve():
        raise CanonicalWriteRefused(
            f"{path} is the canonical gate result. Score to a per-run path and use "
            f"`s1d_blind_rerate.py promote <that file>`, which re-scores and re-verifies inputs.")
    path.parent.mkdir(parents=True, exist_ok=True)
    # A UNIQUE temp in the destination directory, not a shared `<name>.tmp`. Two concurrent writers
    # to one result path took turns clobbering the same scratch file: the loser could install the
    # winner's payload and report success, or hit FileNotFoundError when its own tmp had already been
    # renamed away. Same-directory keeps `os.replace` atomic (one filesystem).
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_refusal(path: Path | None, reason: str, detail: list[str] | None = None) -> None:
    """Overwrite the result file with an explicit refusal.

    A refused run used to leave the PREVIOUS result untouched, so the default gate path kept a stale
    file that still read as a valid verdict — `logs/s1d_rerate_result.json` sat on disk containing a
    `NOT_A_CATEGORY` label and a full `categories_driving_build_order`, from inputs the current scorer
    rejects outright. Anything reading that path would have been reading a verdict no run produced.
    Failure must be recorded in the same place success is, or success is not falsifiable.
    """
    if path is None:
        return
    _write_result(path, {
        # Versioned like a successful result. Without this a consumer could not tell the current
        # refusal shape from a legacy or malformed artifact — and the canonical file spends most of
        # its life being a refusal, so it is the shape most often read.
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "result_kind": "refusal",
        "gate_valid": False,
        "refused": True,
        "reason": reason,
        "detail": detail or [],
        "categories_driving_build_order": None,
        "categories_excluded": None,
        # Always present in v3, even when empty: a refusal written to a per-run path has no lineage,
        # but a consumer reading `result_schema_version: 3` must not have to guess whether the field
        # exists. `invalidate` supplies the real chain on the canonical path.
        "superseded": None,
        "invalidation_chain": [],
        "note": ("Scoring REFUSED. This file replaces any earlier result at this path so a failed run "
                 "cannot leave a valid-looking one behind. Do not fill manifest roll-ups from it."),
    })


def blind_episode(e: dict) -> dict:
    """The blinding transform, in one place so `score` can RECONSTRUCT it from the corpus.

    Used by `draw` to produce the artifact and by `score` to derive what that artifact must have
    contained. Without a reconstruction, packet integrity could only be checked against the manifest's
    recorded digests — and those are written by whoever writes the manifest, so correct episode IDs
    plus re-forged digests passed every check while the packet contents had been rewritten.
    """
    b = {k: v for k, v in e.items() if k not in STRIP}
    b["labels"] = []
    b["primary_label"] = None
    b["rater_notes"] = ""
    return b


# --------------------------------------------------------------------- re-rate label schema
# The first pass is validated by `s1d_apply_labels.py`; the SECOND pass was not validated at all, so a
# re-rate could name a category outside the taxonomy, repeat one, use an invented confidence, or
# designate a primary absent from its own label list — all of which corrupt the agreement statistic
# rather than being caught by it.
LABELABLE = {
    "goal_unknown", "action_semantics_unknown", "perception_parsing",
    "hidden_state_aliasing_or_memory", "exploration_or_probe_selection",
    "progress_signal_misinterpretation", "irreversible_mistake",
    "invalid_output_interface", "retrieval_or_context", "reasoning_inconsistency",
    "latency_or_budget",
}
CONFIDENCES = {"low", "med", "high"}

# `context` must assert the one condition the procedure rests on. A controlled vocabulary is checkable;
# free text is not, and "x" satisfied the previous non-empty test.
VALID_CONTEXTS = {
    "fresh session, no access to the first pass",
    "fresh session, no access to the first pass (independent re-rate, S1-E10)",
}


def validate_labels(episodes: dict) -> list[str]:
    errs = []
    for eid, ep in episodes.items():
        labels = ep.get("labels")
        if not isinstance(labels, list) or not labels:
            errs.append(f"{eid}: `labels` missing or empty")
            continue
        cats = []
        for x in labels:
            if not isinstance(x, dict) or "category" not in x:
                errs.append(f"{eid}: malformed label entry {x!r}")
                continue
            cats.append(x["category"])
            if x["category"] not in LABELABLE:
                errs.append(f"{eid}: category {x['category']!r} is outside the taxonomy")
            if x.get("confidence") not in CONFIDENCES:
                errs.append(f"{eid}: confidence {x.get('confidence')!r} not in {sorted(CONFIDENCES)}")
        if len(set(cats)) != len(cats):
            errs.append(f"{eid}: repeats a category")
        if ep.get("primary_label") not in cats:
            errs.append(f"{eid}: primary_label {ep.get('primary_label')!r} is not among its own "
                        f"labels {cats}")
    return errs

# The six games whose level 1 opens with simple actions only (measured, logs/s2_arc_conventions.json).
SIMPLE_ACTION_GAMES = {
    "g50t-5849a774", "ls20-9607627b", "re86-8af5384d",
    "tr87-cd924810", "tu93-0768757b", "wa30-ee6fef47",
}
OVERSAMPLE = ["goal_unknown", "exploration_or_probe_selection"]
# `labelling` carries the FIRST pass's rater, worksheet and source file. Leaving it on a blinded
# episode both rides first-pass provenance into the second pass and, once re-rated, makes the artifact
# claim `pass: "first"` about labels that are the re-rate's. Stripped with the labels themselves.
STRIP = ("labels", "primary_label", "rater_notes", "labelling")
# S1-E10: no cooling period. The rater is an LLM with no cross-session memory, so there is nothing to
# decay and `cooling_period_hours: 48` cannot be satisfied or reported. The requirement it stood in for
# — that the second pass not see the first — is met structurally by a fresh context plus STRIP.
AGREEMENT_TYPE = "independent re-rate, same model (S1-E10) — NOT delayed test-retest"

# THE PRE-REGISTERED FLOOR. `gate_manifest.yaml -> s1.blind_rerate.agreement_floor` fixes this at 0.40
# and it is frozen, so a run at any other value is not the gate. `--floor` was accepted verbatim: at
# 0.0 the scorer exited 0 and wrote a file titled "the gate result" in which nothing could ever be
# excluded. A pre-registered threshold the caller can choose is not a threshold.
GATE_FLOOR = 0.40

# `gate_manifest.yaml -> s1.blind_rerate.sample_size`, also frozen. The short-draw test compared the
# scored count against the MANIFEST'S OWN `requested`, which the draw chooses — so drawing 20 and
# scoring all 20 was "complete" and produced a valid gate with a full build-order verdict. A sample
# size the run picks for itself is not a pre-registered sample size.
PREREGISTERED_SAMPLE_SIZE = 30

# Bumped whenever the meaning of a field changes, so a consumer can refuse a shape it does not know.
#
#   v2  `inputs` with sha256 per input; verdict withheld on invalid runs
#   v3  `result_kind` discriminator on EVERY artifact; refusals and invalidations versioned;
#       `superseded` and `invalidation_chain` present on EVERY v3 artifact (null / [] when there is
#       no predecessor) — they were added during v3 and were briefly optional, which left a canonical
#       file that was v3 without them. A consumer must be able to read a field it is told exists, so
#       they are written unconditionally rather than documented as "sometimes";
#       input paths recorded repo-relative against `path_anchor`; invalidation records what it
#       withdrew. `result_kind` was added DURING v2, so a v2 artifact may or may not carry it — which
#       is exactly why a consumer cannot branch on it at v2 and why this is a new version rather than
#       an in-place addition. v3 artifacts always have it.
RESULT_SCHEMA_VERSION = 3

# The one file the manifest roll-ups are filled from. `score` refuses to write it; `promote` is the
# only way in, and only for a result that is already `gate_valid`. Under a fixed default output path
# every invocation wrote here — during this harness's own development a fabricated verification run
# (its "re-rate" copied from the first pass, measuring nothing) left `gate_valid: true` sitting in it,
# and a later accidental failure would equally have destroyed a real verdict. Promotion is a separate,
# deliberate act for exactly that reason.
#
# ANCHORED TO THE MODULE, NOT THE WORKING DIRECTORY. As a bare relative path this resolved against
# CWD: run from anywhere but the repository root it named a *different* file, so `score` happily wrote
# the real canonical result by absolute path while the guard compared against `<cwd>/logs/...`, and
# `promote` installed its verdict somewhere that was not the canonical file at all. A protection that
# depends on where you happened to be standing protects nothing.
_REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RESULT = _REPO_ROOT / "logs" / "s1d_rerate_result.json"


def eligible_for(cat: str, ep: dict) -> bool:
    """S1-E4: exploration_or_probe_selection needs alternative-action evidence, which does not exist
    when ACTION6 is in the candidate set — the alternative there is a coordinate, not a named action."""
    if cat != "exploration_or_probe_selection":
        return True
    return str(ep.get("game", "")) in SIMPLE_ACTION_GAMES


def corpus_digest(labelled: list) -> str:
    """Fingerprint of the population AND its order AND every first-pass annotation.

    Hashing episode IDs alone left the first pass editable after the draw, which is the side of the
    comparison nothing else protects: `blind_episode` deliberately strips labels, so packet
    reconstruction cannot see them, and the agreement statistic is computed against them. Adding a
    secondary label to all 30 sampled episodes after drawing changed the result — a new category
    appeared at kappa 0.0 and was excluded from the build order — and every check passed.

    Order is included because `select()` consumes `labelled` positionally: the same episodes in a
    different order are a different sample.
    """
    payload = [
        {"episode_id": e["episode_id"],
         "primary_label": e.get("primary_label"),
         "labels": e.get("labels"),
         "rater_notes": e.get("rater_notes"),
         "labelling": e.get("labelling")}
        for e in labelled                                   # file order, deliberately not sorted
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def select(labelled: list, n: int, seed: int) -> list:
    """THE selection rule, in one place, deterministic in (labelled, n, seed).

    Factored out so `score` can RE-DERIVE the sample instead of believing a file. Selection is the one
    part of this procedure that must not be taken on trust: a manifest — sidecar or not — is a claim
    about which episodes were drawn, and any claim can be rewritten. Recomputation is not a claim.

    Depends on the ORDER of `labelled` as well as its contents, which is why the corpus digest is over
    a sorted id list and the caller must pass the corpus episodes in file order.
    """
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
    return picked


def draw(episodes_path: Path, n: int, seed: int, out: Path, allow_short: bool = False):
    # ONE PARSE, one snapshot. `draw` selected and blinded from this read and then computed the
    # manifest's `corpus_digest` from a SECOND read further down, so a path returning two
    # individually-legal versions committed to a corpus it had not sampled — the manifest matched the
    # later version while the packets came from the earlier one, and scoring accepted it at kappa -1.0.
    data = json.loads(episodes_path.read_bytes())
    eps = data.get("episodes") or []
    labelled = [e for e in eps if e.get("primary_label")]
    if not labelled:
        print("NOTHING TO SAMPLE: no episode carries a primary_label.")
        print("The manifest order is label -> sample -> blind. Complete the first pass first.")
        return 2

    # EVERY episode, not merely some. Filtering the unlabelled ones out silently redefines the
    # population: a 40-episode corpus with 30 labelled drew and scored as though it were a
    # 30-episode corpus, and the frequency ranking would have been computed over whichever episodes
    # happened to have been rated.
    unlabelled = [e.get("episode_id") for e in eps if not e.get("primary_label")]
    if unlabelled:
        print(f"REFUSED — {len(unlabelled)} of {len(eps)} corpus episodes carry no `primary_label`:")
        for eid in unlabelled[:8]:
            print(f"    {eid}")
        if len(unlabelled) > 8:
            print(f"    ... and {len(unlabelled) - 8} more")
        print("  Complete the first pass before drawing. `s1d_apply_labels.py` reports the count.")
        return 1

    # Refuse to sample a corpus whose own labels are not legal. Catching it at score time works, but
    # only after a rater has spent a pass on a sample that was never scoreable.
    corpus_errs = validate_labels({e["episode_id"]: e for e in labelled})
    if corpus_errs:
        print(f"REFUSED — {len(corpus_errs)} schema error(s) in the first-pass corpus:")
        for e in corpus_errs[:8]:
            print(f"    {e}")
        if len(corpus_errs) > 8:
            print(f"    ... and {len(corpus_errs) - 8} more")
        print("  Fix the corpus with s1d_apply_labels.py before drawing.")
        return 1

    picked = select(labelled, n, seed)

    # A SHORT DRAW IS A FAILED DRAW. `sample_size: 30` is pre-registered, and silently returning 25 of
    # 30 with exit 0 hands back an artifact that looks like the sampled corpus and is not — the caller
    # then scores a 25-episode agreement and reports it against a gate written for 30. Refuse instead,
    # and make the operator pass --allow-short to record that they accepted a smaller sample.
    if len(picked) < n and not allow_short:
        print(f"REFUSED — asked for {n} episodes, only {len(picked)} are available "
              f"({len(labelled)} labelled in this corpus).")
        print("  `sample_size` is pre-registered; a short draw silently weakens the gate it feeds.")
        print("  Enlarge the corpus (see S1-E11/S1-E14), or pass --allow-short to accept "
              f"{len(picked)} deliberately — which must then be reported beside the agreement.")
        return 1

    # `evidence` is carried through UNCHANGED, by construction — see blind_episode().
    blinded = [blind_episode(e) for e in picked]

    elig = {c: sum(1 for e in labelled if e.get("primary_label") == c and eligible_for(c, e))
            for c in OVERSAMPLE}
    total = {c: sum(1 for e in labelled if e.get("primary_label") == c) for c in OVERSAMPLE}

    payload = {
        "source": str(episodes_path),
        "drawn": len(blinded),
        "requested": n,
        # Informational copy only. The AUTHORITATIVE commitment is the sidecar written beside this
        # file — see the note in `score`. A manifest carried inside the artifact the rater edits is
        # self-authored: rewriting the episodes and recomputing this field defeats it completely.
        "sample_manifest_advisory": {e["episode_id"]: episode_digest(e) for e in blinded},
        "sample_manifest_note": (f"ADVISORY ONLY. The authoritative manifest is "
                                 f"{manifest_path_for(out).name}, which `score` reads instead."),
        "short_draw": len(blinded) < n,
        "short_draw_note": (f"ACCEPTED A SHORT DRAW: {len(blinded)} of the requested {n}. This is below "
                            f"the pre-registered sample_size and must be reported beside the agreement "
                            f"statistic." if len(blinded) < n else None),
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
    out.write_text(json.dumps(payload, indent=2) + "\n")

    # THE COMMITMENT LIVES OUTSIDE THE ARTIFACT THE RATER EDITS. Keep this file; `score` requires it.
    mpath = manifest_path_for(out)
    mpath.write_text(json.dumps({
        "drawn_from": str(episodes_path),
        "blinded_file": out.name,
        "requested": n,
        "drawn": len(blinded),
        "seed": seed,
        # The parameters `score` needs to RE-DERIVE the selection. The manifest's episode list is then
        # a convenience, not an authority: if it disagrees with the recomputation, the recomputation
        # wins and scoring is refused. A forged sidecar has to reproduce a deterministic draw over the
        # real corpus, which is exactly what it cannot do while listing a sample of someone's choosing.
        # From the SAME snapshot the sample was selected and blinded from, never a fresh read.
        "corpus_digest": corpus_digest(labelled),
        "reproduce": ("s1d_blind_rerate.select(labelled_episodes_in_file_order, requested, seed); "
                      "`score` does this and compares the id sets"),
        "digest_covers": f"every field of the blinded episode except {list(RATER_FILLED)}",
        "episodes": {e["episode_id"]: episode_digest(e) for e in blinded},
    }, indent=2) + "\n")

    print(f"drew {len(blinded)} of {len(labelled)} labelled episodes")
    print(f"wrote {mpath} — the authoritative sample commitment. `score` requires it; do not edit it "
          f"and do not regenerate it from the re-rated file.")
    for c in OVERSAMPLE:
        print(f"   oversampled {c}: eligible {elig[c]} of {total[c]} first-pass episodes")
    print("cooling period: INAPPLICABLE (S1-E10, LLM rater) — re-rate in a fresh context")
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


def score(first_path: Path, rerate_path: Path, floor: float, manifest_path: Path | None = None,
          result_out: Path | None = None):
    """Score the re-rate, and make sure a refusal is recorded where a success would have been.

    `_score` has many refusal paths and each used to `return 1` without touching `result_out`, so a
    rejected run left whatever was there before — including a full, valid-looking verdict from an
    earlier run over inputs the current scorer rejects. Output is captured so the refusal reason can
    be written into the artifact, then replayed to the terminal unchanged.
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = _score(first_path, rerate_path, floor, manifest_path, result_out)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        # A CRASH IS A FAILED RUN, and must leave the same trace a refusal does. Only non-zero
        # RETURNS were handled, so truncated JSON raised JSONDecodeError (a ValueError) straight out
        # of score() and the previous, valid-looking verdict stayed on disk untouched — the exact
        # stale-artifact failure the refusal path exists to prevent, reached by a different route.
        print(buf.getvalue(), end="")
        reason = f"REFUSED — scoring raised {type(exc).__name__}: {exc}"
        print(reason)
        write_refusal(result_out, reason,
                      [f"first_pass: {first_path}", f"rerate: {rerate_path}",
                       f"manifest: {manifest_path}",
                       "Malformed or unreadable input. The previous result at this path has been "
                       "replaced so a crash cannot leave a valid-looking verdict behind."])
        return 1
    text = buf.getvalue()
    print(text, end="")
    if rc != 0:
        refusals = [ln for ln in text.splitlines() if ln.startswith("REFUSED")]
        detail = [ln.strip() for ln in text.splitlines()
                  if ln.startswith("    ") and ln.strip()][:10]
        write_refusal(result_out, refusals[0] if refusals else f"scoring failed (exit {rc})", detail)
    return rc


def _score(first_path: Path, rerate_path: Path, floor: float, manifest_path: Path | None = None,
           result_out: Path | None = None):
    # READ EACH INPUT EXACTLY ONCE. The corpus was parsed twice — once for `first`, which kappa is
    # computed from, and again later for validation and the digest comparison. Two reads of a mutable
    # path are two different objects: a file engineered to return different (individually legal)
    # content on the second read passed validation and matched the manifest, while kappa was computed
    # over the uncommitted first version. It scored 0 with `gate_valid: true` and kappa -1.0.
    first_raw = first_path.read_bytes()
    rr_raw = rerate_path.read_bytes()
    first_payload = json.loads(first_raw)
    rr = json.loads(rr_raw)
    first = {e["episode_id"]: e for e in first_payload.get("episodes", [])}
    second_eps = rr.get("episodes", [])
    second = {e["episode_id"]: e for e in second_eps}

    # THE DRAW IS THE DENOMINATOR, NOT THE FILE. Checking completeness against the re-rate file's own
    # length is vacuous: deleting the un-re-rated episodes satisfies it. The blinded draw records how
    # many episodes it contained, so compare against that — otherwise a truncated pass scores as a
    # complete one, at whatever agreement the finished part happens to show.
    declared = rr.get("drawn")
    if declared is None:
        print("REFUSED — the re-rate file does not record `drawn`, so the sample it came from is "
              "unknown and completeness cannot be checked.")
        print("  Re-rate the file produced by `draw`, which records it, rather than a hand-built one.")
        return 1
    if len(second_eps) != declared:
        print(f"REFUSED — the re-rate holds {len(second_eps)} episodes but its draw recorded "
              f"{declared}. Episodes were removed from the sample after it was drawn.")
        print("  A sample that loses its hard cases scores higher than the sample that was drawn.")
        return 1

    # THE COMMITMENT MUST NOT COME FROM THE FILE BEING CHECKED. A manifest carried inside the re-rate
    # is self-authored: substitute the episodes, recompute the field, and every check passes. The
    # authoritative manifest is the sidecar `draw` wrote next to the blinded file.
    if manifest_path is None:
        print("REFUSED — no sample manifest supplied.")
        print("  Pass --manifest <the .manifest.json written beside the blinded file>. The copy inside "
              "the re-rate is advisory: it is authored by whoever edited the re-rate.")
        return 1
    if not manifest_path.exists():
        print(f"REFUSED — sample manifest not found: {manifest_path}")
        print("  It is written by `draw` beside the blinded file and must be kept.")
        return 1
    manifest_raw = manifest_path.read_bytes()
    mdata = json.loads(manifest_raw) or {}
    manifest = mdata.get("episodes") or {}
    if not manifest:
        print(f"REFUSED — {manifest_path} records no episodes.")
        return 1

    # RE-DERIVE THE SAMPLE. The sidecar raised the bar but did not clear it: regenerate it over a
    # tampered set of real corpus episodes and every membership and digest check agrees with it,
    # because it was written to agree. The draw is deterministic in (corpus, n, seed), so the sample
    # can be recomputed from the corpus itself and compared. A manifest is a claim; this is not.
    # From the SINGLE read taken at the top of this function, not a fresh one.
    all_eps = first_payload.get("episodes") or []
    labelled = [e for e in all_eps if e.get("primary_label")]

    # A PARTIAL FIRST PASS IS NOT A FIRST PASS. `draw` filtered unlabelled episodes out silently, so a
    # 40-episode corpus with 30 labelled drew and scored as though the corpus were 30 — the frequency
    # ranking the build order rests on would then be computed over whichever episodes happened to get
    # rated, which is not a sample of anything.
    unlabelled = [e.get("episode_id") for e in all_eps if not e.get("primary_label")]
    if unlabelled:
        print(f"REFUSED — {len(unlabelled)} of {len(all_eps)} corpus episodes carry no "
              f"`primary_label`:")
        for eid in unlabelled[:8]:
            print(f"    {eid}")
        if len(unlabelled) > 8:
            print(f"    ... and {len(unlabelled) - 8} more")
        print("  Label the whole corpus before drawing; a partially-labelled one silently redefines "
              "the population the sample is drawn from.")
        return 1

    m_seed, m_n = mdata.get("seed"), mdata.get("requested")
    if m_seed is None or m_n is None:
        print("REFUSED — the manifest does not record `seed` and `requested`, so the sample cannot be "
              "re-derived and can only be taken on trust. Re-draw with the current `draw`.")
        return 1
    recorded_corpus = mdata.get("corpus_digest")
    actual_corpus = corpus_digest(labelled)
    if recorded_corpus is None:
        print("REFUSED — the manifest records no `corpus_digest`, so the first pass could have been "
              "edited after the draw and nothing would show it. Re-draw with the current `draw`.")
        return 1
    if recorded_corpus != actual_corpus:
        print(f"REFUSED — the first-pass corpus changed after the draw "
              f"({recorded_corpus} recorded, {actual_corpus} now).")
        print("  The digest covers every first-pass annotation and the corpus order, not just the "
              "episode ids: the labels being compared against are exactly what nothing else protects, "
              "because blinding strips them from the packet.")
        return 1
    expected_ids = {e["episode_id"] for e in select(labelled, m_n, m_seed)}
    if set(manifest) != expected_ids:
        print(f"REFUSED — the manifest does not match the sample that seed {m_seed} produces over this "
              f"corpus: {len(set(manifest) - expected_ids)} listed but not drawn, "
              f"{len(expected_ids - set(manifest))} drawn but not listed.")
        print("  The draw is deterministic, so a manifest that cannot be reproduced was not produced "
              "by it. Re-draw rather than re-authoring the manifest.")
        return 1

    substituted = sorted(set(second) - set(manifest))
    dropped_ids = sorted(set(manifest) - set(second))
    if substituted or dropped_ids:
        print(f"REFUSED — the re-rate is not the sample that was drawn: "
              f"{len(substituted)} substituted, {len(dropped_ids)} missing.")
        for i in substituted[:5]:
            print(f"    substituted in : {i}")
        for i in dropped_ids[:5]:
            print(f"    missing        : {i}")
        print("  Swapping members re-selects the sample after seeing it, which is the one thing "
              "stratified sampling exists to prevent.")
        return 1
    # PACKET INTEGRITY IS CHECKED AGAINST THE CORPUS, NOT THE MANIFEST. Comparing the re-rate's digests
    # to the manifest's recorded digests proves only that two files agree, and both are writable: with
    # the correct episode IDs in place, re-forging the digests let a rewritten packet through. The
    # corpus is the independent artifact, so the expected packet is RECONSTRUCTED from it by applying
    # the same blinding transform, and the digest compared to that.
    expected_digest = {e["episode_id"]: episode_digest(blind_episode(e))
                       for e in labelled if e["episode_id"] in second}
    tampered = [i for i in sorted(second)
                if i in expected_digest and episode_digest(second[i]) != expected_digest[i]]
    if tampered:
        print(f"REFUSED — the material shown to the rater does not match the corpus on "
              f"{len(tampered)} episode(s): {', '.join(tampered[:5])}"
              f"{' …' if len(tampered) > 5 else ''}")
        print("  Reconstructed from the first-pass corpus, so a re-forged manifest cannot conceal it. "
              "The digest covers the whole packet: action counts, baselines and the censoring bound "
              "are what several categories are decided on, not just `evidence`.")
        return 1

    # The manifest must ALSO agree. It cannot authorise anything on its own now, but a disagreement
    # here means the manifest was edited, which is worth refusing on rather than ignoring.
    inconsistent = [i for i in sorted(second)
                    if i in manifest and manifest[i] != expected_digest.get(i)]
    if inconsistent:
        print(f"REFUSED — the manifest's digests disagree with the corpus on {len(inconsistent)} "
              f"episode(s). The manifest was edited after the draw.")
        return 1

    # THE RE-RATE'S OWN LABELS MUST BE WELL FORMED. The first pass is validated on the way in by
    # `s1d_apply_labels.py`; the second pass was not validated anywhere, so an invented category or a
    # primary absent from its own list would silently enter the agreement statistic.
    # THE FIRST PASS IS VALIDATED TOO. `corpus_digest` commits the annotations; it does not make them
    # well formed, and a corpus carrying a category outside the taxonomy scored cleanly with that
    # category appearing in `per_category`. Both sides of an agreement statistic have to be legal
    # labels, or the statistic is computed over something the taxonomy does not define.
    # Scoped to the WHOLE first pass, not the sampled slice. `select()` stratifies on every label in
    # the corpus, so a malformed one changes WHICH episodes are drawn even when it is not itself
    # drawn — a scoped check would silently pass while the sample it validated had been shifted by
    # the label it never looked at.
    first_errs = validate_labels({e["episode_id"]: e for e in labelled})
    if first_errs:
        print(f"REFUSED — {len(first_errs)} schema error(s) in the FIRST-PASS corpus:")
        for e in first_errs[:8]:
            print(f"    {e}")
        if len(first_errs) > 8:
            print(f"    ... and {len(first_errs) - 8} more")
        print("  The corpus digest commits these annotations; it does not validate them. Fix the "
              "corpus with s1d_apply_labels.py, which enforces the same schema on the way in.")
        return 1

    label_errs = validate_labels({i: e for i, e in second.items() if e.get("primary_label")})
    if label_errs:
        print(f"REFUSED — {len(label_errs)} schema error(s) in the re-rate labels:")
        for e in label_errs[:8]:
            print(f"    {e}")
        if len(label_errs) > 8:
            print(f"    ... and {len(label_errs) - 8} more")
        return 1

    # WHO RATED THE SECOND PASS, AND IN WHAT CONTEXT. S1-E10 requires the result be reported as an
    # "independent re-rate, same model" — a claim about the rater and the context, not about the
    # numbers. Left optional, the artifact carried no record of either, so the one condition the whole
    # procedure rests on (a context that has not seen the first-pass labels) was asserted nowhere and
    # could not be audited afterwards.
    # Checked SEMANTICALLY, not for non-emptiness. A truthiness test accepted rater "." and
    # context "x", which record nothing while satisfying the guard — the appearance of provenance
    # rather than provenance, which is worse than an absent field because it reads as compliant.
    prov = rr.get("rerate_provenance") or {}
    prov_errs = []
    rater = str(prov.get("rater") or "").strip()
    if len(rater) < 3:
        prov_errs.append(f"`rater` must identify the rater; got {prov.get('rater')!r}")
    context = str(prov.get("context") or "").strip()
    if context not in VALID_CONTEXTS:
        prov_errs.append(
            f"`context` must be one of {sorted(VALID_CONTEXTS)}; got {prov.get('context')!r}. "
            f"It asserts the one condition the procedure rests on, so it is a controlled value "
            f"rather than free text.")
    # BOTH the shape and the calendar. A regex alone accepted `2026-99-99`; `fromisoformat` alone
    # accepts the basic form `20260728` on Python 3.11+, which is a real date in the wrong format.
    date = str(prov.get("date") or "").strip()
    ok_date = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", date))
    if ok_date:
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            ok_date = False
    if not ok_date:
        prov_errs.append(f"`date` must be a real calendar date as YYYY-MM-DD; got {prov.get('date')!r}")

    # "SAME MODEL" IS A CLAIM THE ARTIFACT MAKES UNCONDITIONALLY, so it has to be true. The first pass
    # records its rater per episode (`labelling.rater`), and a re-rate by a DIFFERENT model is a
    # different measurement — inter-rater agreement between two models, not the intra-model stability
    # S1-E10 describes. `rater: different-model` previously scored while the output went on asserting
    # "independent re-rate, same model".
    # FAILS CLOSED. Two ways the old form let a mismatch through: with no recorded first-pass rater
    # the check was skipped entirely, and with several recorded raters matching any ONE of them
    # sufficed. Both leave "same model" asserted on evidence that does not establish it, so the
    # requirement is exactly one recorded identity, equal to the re-rater.
    first_raters = {(e.get("labelling") or {}).get("rater") for e in labelled}
    first_raters.discard(None)
    if not first_raters:
        prov_errs.append(
            "the first pass records no rater (`labelling.rater`), so 'same model' cannot be "
            "established. Re-apply the labels with s1d_apply_labels.py, which records it.")
    elif first_raters != {rater}:
        prov_errs.append(
            f"`rater` is {rater!r} but the first pass records {sorted(first_raters)}. This script "
            f"reports 'independent re-rate, SAME model', so exactly one first-pass identity must be "
            f"recorded and the re-rater must equal it. A different rater measures inter-rater "
            f"agreement between two models, which the pre-registration does not describe and the "
            f"agreement floor was not chosen for. Score it deliberately under a separate name.")
    if prov_errs:
        print("REFUSED — the re-rate's provenance is not usable:")
        for e in prov_errs:
            print(f"    {e}")
        print('  Example: "rerate_provenance": {"rater": "claude-opus-5", "context": '
              '"fresh session, no access to the first pass", "date": "2026-07-28"}')
        print("  S1-E10 reports this as an INDEPENDENT re-rate; that claim is about the rater and the "
              "context, so an artifact that does not record them cannot support it.")
        return 1

    common = [i for i in second if i in first and second[i].get("primary_label")]
    if not common:
        print("no re-rated episodes carry a primary_label yet.")
        return 2
    # An incomplete re-rate is not a re-rate. Scoring the subset that happens to be filled in reports an
    # agreement over a sample the operator did not choose — and the missing episodes are not missing at
    # random, since a rater stops where the evidence is hardest.
    expected = declared
    if len(common) < expected:
        print(f"REFUSED — {len(common)} of {expected} drawn episodes carry a re-rate label.")
        print("  An agreement computed on the completed subset is biased: episodes are abandoned where")
        print("  they are hardest to rate, which is where disagreement lives. Finish the pass, or")
        print("  re-draw at the size you intend to complete.")
        return 1

    a = [first[i]["primary_label"] for i in common]
    b = [second[i]["primary_label"] for i in common]
    overall = kappa(a, b)
    if overall is None:
        print(f"REFUSED — overall kappa is undefined on {len(common)} episode(s).")
        print("  Kappa needs variation in both passes; with one episode, or with every episode sharing")
        print("  a single label, chance agreement is 1.0 and the statistic does not exist. Reporting")
        print("  'None' beside a 0.40 floor invites reading it as a pass.")
        return 1

    if len(common) < (m_n or 0):
        print(f"\n*** SHORT DRAW: scoring {len(common)} of a pre-registered {m_n}. Every verdict below "
              f"rests on a smaller sample than `blind_rerate.sample_size` specifies. ***")
    print(f"re-rated episodes: {len(common)}   overall kappa: {overall}")

    # PRIMARY-LABEL AGREEMENT — one-vs-rest on the designated primary. Reported first, but it does NOT
    # decide the verdict on its own; see the combined table at the end.
    print(f"\nprimary label{'':21s} {'n':>4} {'kappa':>7}")
    per = {}
    for cat in sorted(set(a) | set(b)):
        ai = [("Y" if x == cat else "N") for x in a]
        bi = [("Y" if x == cat else "N") for x in b]
        k = kappa(ai, bi)
        per[cat] = k
        print(f"{cat:34s} {sum(1 for x in a if x == cat):>4} {str(k):>7}")

    # FULL LABEL-SET AGREEMENT — presence anywhere in `labels`, not just as the primary.
    # Primary-only agreement is blind to the secondary labels: a pass that drops every secondary label
    # still scores kappa 1.0 while `episode_share` moves. Both statistics are reported because the
    # frequency table is built from both fields, so a gate defined on only one under-tests it.
    def cats_of(ep):
        return {x.get("category") for x in (ep.get("labels") or []) if x.get("category")}
    setsA = [cats_of(first[i]) for i in common]
    setsB = [cats_of(second[i]) for i in common]
    allcats = sorted(set().union(*setsA, *setsB)) if (setsA or setsB) else []
    print(f"\nany label (incl. secondary){'':7s} {'n':>4} {'kappa':>7}  agreement on presence")
    per_set = {}
    for cat in allcats:
        ai = [("Y" if cat in s else "N") for s in setsA]
        bi = [("Y" if cat in s else "N") for s in setsB]
        k = kappa(ai, bi)
        per_set[cat] = k
        flag = "" if (k is not None and k >= floor) else "  <- below floor"
        print(f"{cat:34s} {sum(1 for s in setsA if cat in s):>4} {str(k):>7}{flag}")
    na, nb = sum(len(s) for s in setsA), sum(len(s) for s in setsB)
    if na != nb:
        print(f"\n  NOTE: total labels differ between passes — {na} first vs {nb} re-rate. Primary-only "
              f"kappa cannot see this; the table above can.")

    # THE VERDICT TAKES BOTH AXES, AND THE WEAKER ONE DECIDES. A category can be assigned as the
    # primary perfectly reproducibly while the raters disagree about whether it applies at all — the
    # frequency table reads `primary_share` AND `episode_share`, so a gate satisfied on one axis
    # under-tests it. Reporting "drives build order: yes" off the primary column alone let a category
    # pass at kappa 1.0 while its full-label kappa was 0.0.
    print(f"\n{'VERDICT — both axes must clear the floor':40s} {'primary':>8} {'any':>8}  drives build order?")
    failed = []
    for cat in sorted(set(per) | set(per_set)):
        kp, ks = per.get(cat), per_set.get(cat)
        ok = (kp is not None and kp >= floor) and (ks is not None and ks >= floor)
        if not ok:
            failed.append(cat)
            which = []
            if not (kp is not None and kp >= floor):
                which.append("primary")
            if not (ks is not None and ks >= floor):
                which.append("any-label")
            verdict = f"NO — fails {'+'.join(which)}"
        else:
            verdict = "yes"
        print(f"{cat:40s} {str(kp):>8} {str(ks):>8}  {verdict}")

    print(f"\nagreement floor: {floor}. A category drives build order only if BOTH its primary kappa "
          f"and its any-label kappa clear the floor.")
    if failed:
        print(f"EXCLUDED from the frequency ranking and build order: {', '.join(failed)}")

    # WHETHER THIS RUN IS THE GATE AT ALL. Two things disqualify it, and both previously produced a
    # file that read exactly like a valid gate result:
    #   * a floor other than the pre-registered 0.40 — diagnostic, never gating;
    #   * a short draw — the floor was applied to fewer episodes than `sample_size` specifies.
    # `gate_valid: false` is recorded and the build-order verdict is withheld entirely, because a
    # warning does not stop a downstream roll-up from reading `categories_driving_build_order`.
    # Both the request AND the scored count must equal the pre-registered size. Comparing them only
    # against each other made any self-consistent draw a valid gate.
    right_size = (m_n == PREREGISTERED_SAMPLE_SIZE
                  and len(common) == PREREGISTERED_SAMPLE_SIZE)
    gate_valid = (floor == GATE_FLOOR) and right_size
    invalid_reasons = []
    if floor != GATE_FLOOR:
        invalid_reasons.append(
            f"floor {floor} is not the pre-registered {GATE_FLOOR} (gate_manifest.yaml -> "
            f"s1.blind_rerate.agreement_floor); this run is DIAGNOSTIC ONLY")
    if not right_size:
        invalid_reasons.append(
            f"sample size {len(common)} scored of {m_n} requested; the pre-registered "
            f"`blind_rerate.sample_size` is {PREREGISTERED_SAMPLE_SIZE} and BOTH must equal it")
    if not gate_valid:
        print(f"\n*** NOT A GATE RESULT — {'; '.join(invalid_reasons)}. ***")
        print("    `gate_valid: false` is recorded and no build-order verdict is written.")

    # THE GATE RESULT IS AN ARTIFACT, NOT TERMINAL OUTPUT. `failure_frequency_ranking`, `build_order`
    # and `viability_verdict` are filled FROM this, and the project rule is that figures and tables are
    # generated from logs rather than transcribed. A verdict that exists only in a scrollback cannot be
    # regenerated, diffed, or cited — and transcribing it by hand is how a gate quietly loosens.
    if result_out is not None:
        _write_result(result_out, {
            "gate_valid": gate_valid,
            "gate_invalid_reasons": invalid_reasons or None,
            "result_schema_version": RESULT_SCHEMA_VERSION,
            "result_kind": "score",
            # Present-but-empty on a per-run score; `promote` fills them when it installs the result
            # on the canonical path. One shape for every v3 artifact.
            "superseded": None,
            "invalidation_chain": [],
            "scored": "s1d_blind_rerate.py score",
            # PATHS ARE MUTABLE; DIGESTS ARE NOT. Recording only the paths left a valid-looking result
            # silently detached from what was actually scored — edit any input afterwards and nothing
            # in the artifact disagrees. These are over the exact bytes read, so a result can always be
            # re-checked against the files it names.
            "inputs": {
                # REPO-RELATIVE against `path_anchor`, not absolute and not CWD-relative. Absolute
                # paths fixed foreign-CWD promotion but made a byte-identical result unpromotable
                # from a clone or a moved checkout; CWD-relative names whatever happens to sit there.
                # Anchored-relative survives both.
                "first_pass": {"path": _rel(first_path), "sha256": _sha256(first_raw)},
                "rerate": {"path": _rel(rerate_path), "sha256": _sha256(rr_raw)},
                "manifest": {"path": _rel(manifest_path), "sha256": _sha256(manifest_raw)},
            },
            "path_anchor": "repository root (the parent of agent/ and logs/)",
            "manifest_commitment": {"seed": m_seed, "requested": m_n,
                                    "corpus_digest": recorded_corpus},
            "rerate_provenance": prov,
            "agreement_type": AGREEMENT_TYPE,
            "cooling_period_status": "INAPPLICABLE (S1-E10, LLM rater)",
            "n_episodes": len(common),
            # A SHORT DRAW MUST NOT PRODUCE A NORMAL-LOOKING RESULT. `--allow-short` is recorded at
            # draw time and was going no further, so a gate scored on 20 of a pre-registered 30 wrote
            # a result indistinguishable from a complete one. It is carried here and stated first.
            "sample_size_requested": m_n,
            "sample_size_scored": len(common),
            "short_draw": len(common) < (m_n or 0),
            "short_draw_warning": (
                f"BELOW THE PRE-REGISTERED SAMPLE SIZE: scored on {len(common)} of {m_n}. The "
                f"agreement floor was applied to a smaller sample than `blind_rerate.sample_size` "
                f"specifies, and this must be reported wherever these categories are cited."
                if len(common) < (m_n or 0) else None),
            "agreement_floor": floor,
            "overall_kappa_primary": overall,
            # `clears_requested_floor` is a STATISTIC — did this category meet whatever floor was
            # asked for — and is always meaningful. `drives_build_order` is a VERDICT and exists only
            # when the run is the gate. Nulling the top-level lists while every row still carried
            # `drives_build_order: true` left the verdict readable one level down, which is where a
            # roll-up script would find it anyway.
            "per_category": {
                cat: {"kappa_primary": per.get(cat), "kappa_any_label": per_set.get(cat),
                      "clears_requested_floor": cat not in failed,
                      "drives_build_order": (cat not in failed) if gate_valid else None}
                for cat in sorted(set(per) | set(per_set))},
            "verdict_rule": ("a category drives build order only if BOTH its primary kappa and its "
                             "any-label kappa are >= the floor"),
            # WITHHELD when the run is not the gate. An empty list would read as "nothing qualified";
            # null forces a consumer to notice the run cannot answer the question. `per_category` is
            # kept either way — the kappas are real measurements, it is the VERDICT that is not.
            "categories_driving_build_order": (
                [c for c in sorted(set(per) | set(per_set)) if c not in failed]
                if gate_valid else None),
            "categories_excluded": failed if gate_valid else None,
            "verdict_withheld_because": None if gate_valid else invalid_reasons,
            "total_labels_first_vs_rerate": [na, nb],
            "interpretation_limit": (
                "bounds label STABILITY, not correctness. An LLM re-rating an LLM may share systematic "
                "blind spots (S1-E10); no human-rated sample bounds that."),
        })
        print(f"\nwrote {result_out} — "
              + ("the gate result. Fill the manifest roll-ups from this file, not from this terminal "
                 "output." if gate_valid else
                 "NOT a gate result (`gate_valid: false`). Do not fill the manifest roll-ups from it."))
    print(f"Agreement type: {AGREEMENT_TYPE}.")
    print("Interpretation limit: it bounds label STABILITY, not correctness, and an LLM re-rating an "
          "LLM may share systematic blind spots (S1-E10). Do not compare against human test-retest.")
    return 0


def promote(result_path: Path) -> int:
    """Promote a run onto the canonical path by RE-SCORING it, never by trusting what it says.

    The submitted file is treated as nothing but a POINTER TO THREE INPUTS. Verifying the payload's
    own claims cannot work: a hand-written result carrying `gate_valid: true`, an empty `inputs` map
    and a fabricated `categories_driving_build_order` passed every check, because a loop over zero
    recorded inputs verifies zero inputs — and even requiring all three is not enough, since a forged
    file can quote correct hashes beside an altered verdict. So the verdict is recomputed here, at the
    pre-registered floor, and the RECOMPUTED artifact is what gets written.
    """
    try:
        payload = json.loads(result_path.read_bytes())
    except (OSError, ValueError) as exc:
        print(f"REFUSED — cannot read {result_path}: {exc}")
        return 1

    # Recomputation REPLACES trusting the payload's verdict; it does not replace these preconditions,
    # which are cheap and strictly narrow what can be submitted. Together: you may not promote a run
    # you already know failed, and a run you believe passed is still re-scored before it counts.
    if payload.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        print(f"REFUSED — result schema version {payload.get('result_schema_version')!r}; this build "
              f"writes {RESULT_SCHEMA_VERSION}. Re-score rather than promoting an unknown shape.")
        return 1
    # The discriminator is only dependable from v3 on, which is why v3 exists — a v2 artifact may or
    # may not carry it. Having required v3 above, requiring it here is safe.
    if payload.get("result_kind") != "score":
        print(f"REFUSED — result_kind is {payload.get('result_kind')!r}; only a `score` artifact can "
              f"be promoted. A refusal or an invalidation is not a candidate verdict.")
        return 1
    if not payload.get("gate_valid"):
        print(f"REFUSED — {result_path} does not claim to be a valid gate result "
              f"(gate_valid={payload.get('gate_valid')!r}).")
        for r in payload.get("gate_invalid_reasons") or [payload.get("reason")]:
            if r:
                print(f"    {r}")
        print("  Promotion re-scores what it is given, but it will not silently upgrade a run that "
              "recorded itself as diagnostic or refused. Score at the gate floor first.")
        return 1

    inputs = payload.get("inputs") or {}
    required = ("first_pass", "rerate", "manifest")
    missing = [k for k in required if not (inputs.get(k) or {}).get("path")]
    if missing:
        print(f"REFUSED — {result_path} does not record {', '.join(missing)}, so there is nothing to "
              f"re-score from. A result that names no inputs cannot be promoted, whatever it claims.")
        return 1
    paths = {k: _resolve_recorded(inputs[k]["path"]) for k in required}
    for name, path in paths.items():
        if not path.exists():
            print(f"REFUSED — the {name} it names no longer exists: {path}")
            return 1

    # Any hash the file DOES record must still match — a cheap, early signal that the inputs moved.
    for name, path in paths.items():
        recorded = (inputs[name] or {}).get("sha256")
        if recorded and _sha256(path.read_bytes()) != recorded:
            print(f"REFUSED — the {name} has changed since it was scored: {path}")
            return 1

    with tempfile.TemporaryDirectory(prefix="promote-") as tmp:
        recomputed_path = Path(tmp) / "recomputed.json"
        print(f"re-scoring from the inputs named by {result_path} ...")
        rc = score(paths["first_pass"], paths["rerate"], GATE_FLOOR, paths["manifest"],
                   recomputed_path)
        if rc != 0 or not recomputed_path.exists():
            print(f"REFUSED — re-scoring those inputs does not succeed (exit {rc}).")
            return 1
        fresh = json.loads(recomputed_path.read_bytes())

    if not fresh.get("gate_valid"):
        print("REFUSED — re-scoring those inputs does not produce a valid gate result:")
        for r in fresh.get("gate_invalid_reasons") or []:
            print(f"    {r}")
        return 1

    if payload.get("gate_valid") and payload.get("categories_driving_build_order") != \
            fresh.get("categories_driving_build_order"):
        print("NOTE — the submitted file's verdict disagreed with a fresh scoring of its own inputs.")
        print(f"    submitted:  {payload.get('categories_driving_build_order')}")
        print(f"    recomputed: {fresh.get('categories_driving_build_order')}")
        print("    The recomputed verdict is the one promoted.")

    # CARRY THE EXISTING LINEAGE FORWARD. Consecutive invalidations chained correctly, but promotion
    # overwrote the canonical file without reading it, so the documented recovery path — score A,
    # invalidate, promote B, invalidate — ended with a chain containing only B. Whatever the canonical
    # file was before this promotion becomes the next link, so the history is continuous across
    # promotions as well as invalidations.
    # Read and replace INSIDE one lock. Both halves matter: reading the predecessor and installing the
    # successor are a single transaction, or an interleaved invalidation overwrites this promotion
    # while recording the artifact this promotion replaced.
    with canonical_lock():
        prior_chain, superseded = _read_canonical_lineage()
        _write_result(CANONICAL_RESULT,
                      dict(fresh, promoted_from=str(result_path),
                           promotion_note=("recomputed from the inputs named by promoted_from; the "
                                           "submitted payload's own verdict was not trusted"),
                           superseded=superseded,
                           invalidation_chain=(([superseded] + prior_chain) if superseded
                                               else prior_chain)),
                      promoting=True)
    print(f"promoted -> {CANONICAL_RESULT}")
    print("  Verdict recomputed from the named inputs at the pre-registered floor. The manifest "
          "roll-ups may now be filled from this file.")
    return 0


def invalidate(reason: str, detail: list[str] | None = None, *, now: str | None = None) -> int:
    """Deliberately mark the canonical result as refused.

    The counterpart to `promote`. `score` cannot reach this file, which is the point, but a promoted
    verdict sometimes has to be withdrawn — a superseded corpus, a retracted re-rate — and that has to
    be a named action rather than a side effect of some other command.
    """
    # WHAT WAS WITHDRAWN, captured before it is overwritten. Invalidation destroyed the only copy of
    # the verdict it retracted: unless a commit happened between promotion and invalidation — which
    # nothing enforces — there was afterwards no durable trace of what had been withdrawn, or that
    # anything had. The digest identifies the superseded artifact; the summary makes the record
    # readable without needing to find it.
    with canonical_lock():
        return _invalidate_locked(reason, detail, now)


def _invalidate_locked(reason: str, detail: list[str] | None, now: str | None) -> int:
    prior_chain, previous = _read_canonical_lineage()

    _write_result(CANONICAL_RESULT, {
        "result_schema_version": RESULT_SCHEMA_VERSION,
        "result_kind": "invalidation",
        "gate_valid": False,
        "refused": True,
        "reason": reason,
        "detail": detail or [],
        "invalidated_at": now or datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "invalidated": previous,
        # Oldest last. `invalidated` is the immediate predecessor; this is everything before it, so a
        # promoted score remains identifiable no matter how many invalidations followed it.
        "invalidation_chain": ([previous] + prior_chain) if previous else prior_chain,
        "categories_driving_build_order": None,
        "categories_excluded": None,
        "note": ("Canonical gate result INVALIDATED deliberately. `invalidated` identifies what this "
                 "replaced, including its SHA-256. Do not fill manifest roll-ups from it. Re-score "
                 "and re-promote to replace it."),
    }, promoting=True)
    print(f"invalidated {CANONICAL_RESULT}: {reason}")
    if previous:
        print(f"  withdrew: {previous['result_kind']} sha256={previous['sha256'][:16]}… "
              f"gate_valid={previous['gate_valid']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draw"); d.add_argument("episodes"); d.add_argument("--n", type=int, default=30)
    d.add_argument("--seed", type=int, default=20260726); d.add_argument("--out", default="")
    d.add_argument("--allow-short", action="store_true",
                   help="accept fewer than --n episodes (default: refuse; a short draw weakens the gate)")
    pr = sub.add_parser("promote"); pr.add_argument("result")
    iv = sub.add_parser("invalidate"); iv.add_argument("reason")
    iv.add_argument("--detail", nargs="*", default=[])
    sc = sub.add_parser("score"); sc.add_argument("first"); sc.add_argument("rerate")
    sc.add_argument("--floor", type=float, default=0.40)
    sc.add_argument("--result-out", required=True,
                    help="REQUIRED. Where to write this run's result. There is deliberately no "
                         "default: a fixed one is written by every invocation, so a diagnostic or a "
                         "harness check overwrites the canonical file, and an accidental failed run "
                         "destroys a genuine verdict. Write per-run, then promote deliberately.")
    sc.add_argument("--manifest", default="",
                    help="the .manifest.json written by `draw` beside the blinded file. "
                         "Defaults to <rerate>.manifest.json. Required: the copy inside the "
                         "re-rate is self-authored and is not trusted.")
    args = ap.parse_args()

    if args.cmd == "promote":
        return promote(Path(args.result))
    if args.cmd == "invalidate":
        return invalidate(args.reason, args.detail)
    if args.cmd == "draw":
        src = Path(args.episodes)
        out = Path(args.out) if args.out else src.with_name(src.stem + "_blinded.json")
        return draw(src, args.n, args.seed, out, args.allow_short)
    rr_path = Path(args.rerate)
    mpath = Path(args.manifest) if args.manifest else manifest_path_for(rr_path)
    res = Path(args.result_out)
    try:
        return score(Path(args.first), rr_path, args.floor, mpath, res)
    except CanonicalWriteRefused as exc:
        print(f"REFUSED — {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
