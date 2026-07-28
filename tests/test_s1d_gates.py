"""Regression tests for the S1-d corpus and blind-re-rate gates.

WHY THIS FILE EXISTS
--------------------
Every guard here was added in response to a defect found by review, and several of them were introduced
BY an earlier fix to a neighbouring defect. That is the specific failure mode this file exists to stop:
the guards were verified once, by hand, in scratch scripts that no longer exist, so each new fix was
free to silently undo the last one.

Each test names the defect it pins. Read the docstring before changing the assertion — an assertion that
looks arbitrary is usually the shape of a real bug.

Run:
  .venv/bin/python -m pytest tests/test_s1d_gates.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import s1d_blind_rerate as RR      # noqa: E402
import s1d_build_corpus as B       # noqa: E402


# --------------------------------------------------------------------------- fixtures

def _ep(run: str, game: str, level: int, *, evidence: str = "t") -> dict:
    return {
        "episode_id": f"{run}::{game}_p0::L{level}",
        "game": game, "level": level, "pass_key": f"{game}_p0",
        "actions_taken": 10, "terminal_state": "gave_up",
        "evidence": {"reasoning_by_step": {"1": [evidence]}},
    }


@pytest.fixture
def build_corpus(tmp_path, monkeypatch):
    """Drive `build()` over synthetic runs with stubbed signatures.

    Stubbing `_config_signature` is deliberate: these tests pin the POOLING RULE, not the signature's
    own construction, which `test_signature_*` covers separately against real run directories.
    """
    def run(fixtures: dict[str, list], signatures: dict[str, str], **kw):
        monkeypatch.setattr(B, "extract_episodes",
                            lambda rd: {"episodes": [copy.deepcopy(e) for e in fixtures[rd.name]]})
        monkeypatch.setattr(B, "_config_signature", lambda rd: signatures[rd.name])
        monkeypatch.setattr(B, "_budget_seconds", lambda rd: None)
        monkeypatch.setattr(B, "_wallclock", lambda rd, g, p=0: None)
        monkeypatch.setattr(B, "frequencies", lambda eps: {})
        dirs = []
        for name in fixtures:
            (tmp_path / name).mkdir(exist_ok=True)
            dirs.append(tmp_path / name)
        out = tmp_path / "corpus.json"
        B.build(dirs, kw.get("require_evidence", False), kw.get("allow_censored", True),
                out, kw.get("replicates", True))
        return json.loads(out.read_text())
    return run


# --------------------------------------------------------------------------- corpus pooling

def test_mixed_configuration_unique_levels_are_refused(build_corpus):
    """A foreign-configuration run must contribute NOTHING — not even games no other run covered.

    The guard was once scoped per (game, level), so a different-model run was refused only where it
    collided with a game-level someone already owned; its five unique games walked in and the corpus
    silently held two configurations. Configuration identity is a property of the RUN.
    """
    d = build_corpus(
        {"v2": [_ep("v2", g, 1) for g in "abc"],
         "v3": [_ep("v3", g, 1) for g in "abcdefgh"]},
        {"v2": "CONFIG-A", "v3": "CONFIG-B"},
    )
    assert {e["source_run"] for e in d["episodes"]} == {"v2"}
    assert d["n_episodes"] == 3
    assert [r["run"] for r in d["refused_runs_different_configuration"]] == ["v3"]


def test_same_configuration_replicates_pool_across_runs(build_corpus):
    """The converse: identical configurations across separate runs ARE replicates (S1-E14).

    Keying ownership on the run directory refused exactly these, collapsing v2+v3 from 50 to 30.
    """
    d = build_corpus(
        {"v2": [_ep("v2", g, 1) for g in "abc"],
         "v3": [_ep("v3", g, 1) for g in "abc"]},
        {"v2": "CONFIG-A", "v3": "CONFIG-A"},
    )
    assert d["n_episodes"] == 6
    assert d["n_distinct_game_levels"] == 3


def test_unknown_signature_run_is_admitted_alone_but_never_pooled(build_corpus):
    """One unidentifiable run is one configuration by construction, so it may build a corpus alone.

    It must not crash: an earlier version refused its own first episode and then looked up an owner
    that did not exist yet, raising StopIteration out of build().
    """
    d = build_corpus({"vU": [_ep("vU", "a", 1)]}, {"vU": B.UNKNOWN_SIGNATURE})
    assert d["n_episodes"] == 1

    d2 = build_corpus(
        {"vU": [_ep("vU", "a", 1)], "vV": [_ep("vV", "b", 1)]},
        {"vU": B.UNKNOWN_SIGNATURE, "vV": B.UNKNOWN_SIGNATURE},
    )
    assert {e["source_run"] for e in d2["episodes"]} == {"vU"}


def test_replicates_off_collapses_to_one_per_game_level(build_corpus):
    """Default mode is unchanged: one episode per (game, level)."""
    d = build_corpus(
        {"v2": [_ep("v2", "a", 1)], "v3": [_ep("v3", "a", 1)]},
        {"v2": "CONFIG-A", "v3": "CONFIG-A"},
        replicates=False,
    )
    assert d["n_episodes"] == 1


# --------------------------------------------------------------------------- signature

def _run_dir(tmp_path, name, cfg: dict | None, *, label="L") -> Path:
    p = tmp_path / name
    p.mkdir(exist_ok=True)
    (p / "benchmark.json").write_text(json.dumps({"label": label, "n_passes": 1, "game_runs": []}))
    if cfg is not None:
        (p / "run_config.json").write_text(json.dumps(cfg))
    return p


FULL_SAMPLING = {"LOCAL_ANALYZER_TEMPERATURE": "0.6", "LOCAL_ANALYZER_TOP_P": "0.95",
                 "LOCAL_ANALYZER_TOP_K": "20", "LOCAL_ANALYZER_SEED": None,
                 "LOCAL_ANALYZER_ENABLE_THINKING": "true"}
FULL_CFG = {"model": "m-1", "provider": "vllm", "context_window": "32768",
            "sampling": dict(FULL_SAMPLING), "max_runtime_minutes_per_game": 132.0}


def test_signature_splits_on_model_and_on_sampling(tmp_path):
    """Model and sampling live only in run_config.json; the solver repr says `model='local'`."""
    a = B._config_signature(_run_dir(tmp_path, "a", FULL_CFG))
    other_model = dict(FULL_CFG, model="m-2")
    b = B._config_signature(_run_dir(tmp_path, "b", other_model))
    hot = dict(FULL_CFG, sampling=dict(FULL_SAMPLING, LOCAL_ANALYZER_TEMPERATURE="1.0"))
    c = B._config_signature(_run_dir(tmp_path, "c", hot))
    assert not B._same_config(a, b)
    assert not B._same_config(a, c)
    assert B._same_config(a, B._config_signature(_run_dir(tmp_path, "d", FULL_CFG)))


def test_missing_run_config_is_incomplete_not_silently_equal(tmp_path):
    """Absence must not read as agreement.

    Kaggle does not emit run_config.json. When the file was missing the signature simply omitted model
    and sampling, so two runs on DIFFERENT WEIGHTS compared equal — and did not look UNKNOWN.
    """
    a = B._config_signature(_run_dir(tmp_path, "a", None))
    b = B._config_signature(_run_dir(tmp_path, "b", None))
    assert a.startswith(B.INCOMPLETE_PREFIX)
    assert not B._same_config(a, b)
    assert not B._same_config(a, a)


def test_partial_run_config_is_incomplete(tmp_path):
    """A config recording the budget but not the model is not a weaker identity — it is none."""
    sig = B._config_signature(_run_dir(tmp_path, "a", {"max_runtime_minutes_per_game": 132.0}))
    assert sig.startswith(B.INCOMPLETE_PREFIX)
    assert not B._same_config(sig, sig)


@pytest.mark.parametrize("dropped", ["provider", "context_window", "max_runtime_minutes_per_game"])
def test_each_outcome_relevant_field_is_required(tmp_path, dropped):
    """Model and sampling are not the whole identity, and this test must DISCRIMINATE.

    Every field here changes what the episodes mean, so a run missing one cannot be shown to share a
    configuration with another: `provider` fixes the inference stack, `context_window` fixes when
    history is truncated — which is what `retrieval_or_context` is defined on — and
    `max_runtime_minutes_per_game` is the censoring bound `latency_or_budget` is defined on.

    Written after mutation testing: an earlier version dropped model AND sampling too, so it passed
    whether or not these three were required, and reverting the requirement broke nothing.
    """
    cfg = {k: v for k, v in FULL_CFG.items() if k != dropped}
    assert cfg.get("model") and cfg.get("sampling"), "must isolate the field under test"
    sig = B._config_signature(_run_dir(tmp_path, f"drop_{dropped}", cfg))
    assert sig.startswith(B.INCOMPLETE_PREFIX), f"dropping {dropped} left a complete identity"
    assert not B._same_config(sig, sig)


@pytest.mark.parametrize("dropped", sorted(FULL_SAMPLING))
def test_each_sampling_parameter_is_required(tmp_path, dropped):
    """`sampling` is NESTED, and requiring the key only checked the dict was non-empty.

    A run recording temperature alone therefore passed as a complete identity while top_p, top_k, the
    seed and the thinking flag were unknown — each of which changes the distribution the episodes were
    drawn from. Note `LOCAL_ANALYZER_SEED` is legitimately `null` in the reference config, so presence
    is tested rather than truthiness: the field that says "this run is unseeded" is a recorded value,
    not a missing one.
    """
    cfg = dict(FULL_CFG, sampling={k: v for k, v in FULL_SAMPLING.items() if k != dropped})
    sig = B._config_signature(_run_dir(tmp_path, f"s_{dropped}", cfg))
    assert sig.startswith(B.INCOMPLETE_PREFIX), f"dropping sampling.{dropped} left a complete identity"
    assert not B._same_config(sig, sig)


def test_null_seed_counts_as_recorded(tmp_path):
    """The reference samples unseeded. `SEED: null` must NOT read as an incomplete identity."""
    sig = B._config_signature(_run_dir(tmp_path, "seeded_null", FULL_CFG))
    assert not sig.startswith(B.INCOMPLETE_PREFIX)
    assert B._same_config(sig, B._config_signature(_run_dir(tmp_path, "seeded_null2", FULL_CFG)))


def test_concurrency_difference_splits_the_signature(tmp_path):
    """Not required — a run may omit it — but where recorded it must not be ignored.

    Contention changes how much wall clock each game gets against a fixed budget.
    """
    a = dict(FULL_CFG, effective_concurrent_jobs=28)
    b = dict(FULL_CFG, effective_concurrent_jobs=1)
    assert not B._same_config(B._config_signature(_run_dir(tmp_path, "ca", a)),
                              B._config_signature(_run_dir(tmp_path, "cb", b)))


# --------------------------------------------------------------------------- draw

def _corpus(n: int, cats: list[str]) -> dict:
    eps = []
    for i in range(n):
        c = cats[i % len(cats)]
        e = _ep("v2", f"g{i}", 1, evidence=f"reasoning-{i}")
        e["primary_label"] = c
        e["labels"] = [{"category": c, "confidence": "high"},
                       {"category": "retrieval_or_context", "confidence": "med"}]
        # The first pass records WHO rated it. `score` compares the re-rate's rater against this to
        # enforce the "same model" the artifact claims, so the fixture has to carry it.
        e["labelling"] = {"pass": "first", "rater": "claude-opus-5",
                          "worksheet": "synthetic", "source": "fixture"}
        eps.append(e)
    return {"episodes": eps}


CATS = ["goal_unknown", "latency_or_budget", "perception_parsing"]
PROVENANCE = {"rater": "claude-opus-5", "context": "fresh session, no access to the first pass",
              "date": "2026-07-28"}


def test_short_draw_is_refused_and_allow_short_records_it(tmp_path):
    """`sample_size` is pre-registered; returning 25 of 30 with exit 0 weakens the gate silently."""
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(25, CATS)))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 1

    assert RR.draw(src, 30, 1, out, True) == 0
    d = json.loads(out.read_text())
    assert d["short_draw"] is True and d["drawn"] == 25 and d["requested"] == 30


def test_blinding_strips_labels_and_first_pass_provenance_but_keeps_evidence(tmp_path):
    """`labelling` carries the first pass's rater and worksheet; it must not ride into the second.

    Left in place, a re-rated artifact also claims `pass: "first"` about the re-rate's own labels.
    """
    src = tmp_path / "c.json"
    c = _corpus(30, CATS)
    for e in c["episodes"]:
        e["labelling"] = {"pass": "first", "rater": "r", "worksheet": "w", "source": "batch1.json"}
    src.write_text(json.dumps(c))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    ep = json.loads(out.read_text())["episodes"][0]
    assert ep["primary_label"] is None and ep["labels"] == []
    assert "labelling" not in ep
    assert ep["evidence"]["reasoning_by_step"]          # evidence survives, by design


# --------------------------------------------------------------------------- score

@pytest.fixture
def drawn(tmp_path):
    """A real 30-draw plus a helper that answers it from the first pass.

    Returns the sidecar manifest path too: `score` reads its commitment from there, never from the
    re-rate file, so every test must pass it explicitly.
    """
    src = tmp_path / "c.json"
    corpus = _corpus(30, CATS)
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    manifest = RR.manifest_path_for(out)
    assert manifest.exists()
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}

    def answer(mutate=None):
        d = json.loads(out.read_text())
        for e in d["episodes"]:
            s = by_id[e["episode_id"]]
            e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
        d["rerate_provenance"] = dict(PROVENANCE)
        if mutate:
            mutate(d, by_id)
        p = tmp_path / "rr.json"
        p.write_text(json.dumps(d))
        return p
    return src, answer, by_id, corpus, manifest


def test_faithful_rerate_scores(drawn):
    src, answer, _, _, man = drawn
    assert RR.score(src, answer(), 0.40, man) == 0


def test_truncated_rerate_is_refused(drawn):
    """Completeness was checked against the re-rate file's own length, which truncation satisfies."""
    src, answer, _, _, man = drawn
    def cut(d, _by_id):
        d["episodes"] = d["episodes"][:5]
    assert RR.score(src, answer(cut), 0.40, man) == 1


def test_substituted_sample_members_are_refused(drawn):
    """Swapping members re-selects the sample after seeing it, at a preserved count of 30."""
    src, answer, _, _, man = drawn
    def swap(d, _by_id):
        d["episodes"][0] = dict(d["episodes"][0], episode_id="v2::NOT-IN-SAMPLE_p0::L1")
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.score(src, answer(swap), 0.40, man)
    assert rc == 1
    # The manifest here is HONEST, so re-derivation passes and the membership check is what fires.
    assert "is not the sample that was drawn" in buf.getvalue(), buf.getvalue()


def test_mutated_evidence_is_refused(drawn):
    """The packet is the one thing both passes must share, and the one thing nothing checked."""
    src, answer, _, _, man = drawn
    def mutate(d, _by_id):
        d["episodes"][0]["evidence"] = {"reasoning_by_step": {"1": ["REWRITTEN"]}}
    assert RR.score(src, answer(mutate), 0.40, man) == 1


def test_self_authored_manifest_does_not_authorise_substitution(tmp_path):
    """The commitment must not come from the file being checked.

    An in-file manifest is authored by whoever edited the re-rate: substitute the episodes, recompute
    the field, and every membership and digest check passes. `score` therefore reads the sidecar
    `draw` wrote, and the in-file copy is advisory only.
    """
    # A 40-episode corpus so a 30-draw genuinely leaves candidates outside the sample to swap in.
    src = tmp_path / "c40.json"
    corpus = _corpus(40, CATS)
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d40.json"
    assert RR.draw(src, 30, 1, out) == 0
    man = RR.manifest_path_for(out)
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}

    d = json.loads(out.read_text())
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])

    drawn_ids = set(json.loads(man.read_text())["episodes"])
    outside = [e for e in corpus["episodes"] if e["episode_id"] not in drawn_ids]
    assert outside, "fixture must leave episodes outside the sample"

    swapped = copy.deepcopy(outside[0])
    d["episodes"][0] = swapped
    # forge a perfectly self-consistent in-file manifest over the tampered sample
    d["sample_manifest_advisory"] = {e["episode_id"]: RR.episode_digest(e) for e in d["episodes"]}
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr40.json"
    rr.write_text(json.dumps(d))

    assert RR.score(src, rr, 0.40, man) == 1


def test_worksheet_field_mutation_outside_evidence_is_refused(drawn):
    """`evidence` is not the only material the rater sees.

    `latency_or_budget` is decided on `censored_at_seconds` / `budget_terminated`, and the ratio
    categories on `actions_taken` / `human_baseline`. Hashing `evidence` alone left all of them free
    to change between passes.
    """
    src, answer, _, _, man = drawn
    def mutate_fields(d, _by_id):
        for e in d["episodes"][:5]:
            e["actions_taken"] = 1
            e["human_baseline"] = 999
            e["censored_at_seconds"] = None
            e["budget_terminated"] = False
    assert RR.score(src, answer(mutate_fields), 0.40, man) == 1


def test_missing_manifest_is_refused(drawn, tmp_path, capsys):
    """No commitment, no score — including when the sidecar was simply not kept.

    Message-asserted: without these guards the code reaches `manifest_path.exists()` on None, or
    `read_text()` on a missing file, and the exception handler turns both into refusals. The exit
    code would look right while the guard that names the problem was gone.
    """
    src, answer, _, _, _man = drawn
    capsys.readouterr()
    assert RR.score(src, answer(), 0.40, None) == 1
    assert "no sample manifest supplied" in capsys.readouterr().out

    assert RR.score(src, answer(), 0.40, tmp_path / "absent.manifest.json") == 1
    assert "sample manifest not found" in capsys.readouterr().out


def test_undefined_kappa_is_refused(tmp_path, capsys):
    """With every episode sharing one label, chance agreement is 1.0 and kappa does not exist.

    Printing `None` beside a 0.40 floor invites reading it as a pass.

    Rewritten after this test went VACUOUS: once `score` required a manifest, the old version — which
    passed none — returned 1 for the missing manifest and never reached the kappa check. It would have
    passed with the kappa guard deleted. It now supplies a real manifest and provenance, and asserts on
    the refusal MESSAGE so it cannot silently start testing a different rejection again.
    """
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(6, ["goal_unknown"])))
    out = tmp_path / "d.json"
    assert RR.draw(src, 6, 1, out) == 0
    d = json.loads(out.read_text())
    for e in d["episodes"]:
        e["primary_label"] = "goal_unknown"
        e["labels"] = [{"category": "goal_unknown", "confidence": "high"}]
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))
    capsys.readouterr()
    assert RR.score(src, rr, 0.40, RR.manifest_path_for(out)) == 1
    assert "overall kappa is undefined" in capsys.readouterr().out


def test_forged_sidecar_over_real_episodes_is_refused(tmp_path):
    """A sidecar is still only a claim; the draw is deterministic, so the sample is RE-DERIVED.

    Substituting genuine corpus episodes and regenerating the sidecar to match defeats every check
    that reads the sidecar — membership agrees, digests agree, and the evidence is real so the
    corpus cross-check agrees too. Only recomputing the selection from (corpus, n, seed) catches it.
    """
    src = tmp_path / "c40.json"
    corpus = _corpus(40, CATS)
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    man = RR.manifest_path_for(out)
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}

    d = json.loads(out.read_text())
    drawn_ids = set(json.loads(man.read_text())["episodes"])
    outside = [e for e in corpus["episodes"] if e["episode_id"] not in drawn_ids]
    assert outside
    d["episodes"][0] = copy.deepcopy(outside[0])
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    forged = json.loads(man.read_text())
    forged["episodes"] = {e["episode_id"]: RR.episode_digest(e) for e in d["episodes"]}
    fman = tmp_path / "forged.manifest.json"
    fman.write_text(json.dumps(forged))

    # Message-asserted so this pins RE-DERIVATION specifically. Several downstream checks also refuse
    # a substituted sample, and an exit-code assertion cannot say which one fired.
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.score(src, rr, 0.40, fman)
    assert rc == 1
    assert "does not match the sample that seed" in buf.getvalue(), buf.getvalue()


def test_swapped_corpus_under_a_valid_manifest_is_refused(tmp_path):
    """The manifest binds to the population it was drawn from, not just to the sample.

    HONEST LIMIT: this asserts the behaviour, not the specific guard. Deleting the `corpus_digest`
    comparison leaves all 26 tests green, because a changed population also changes what the
    re-derivation produces, so the re-derivation catches it first. The digest check is
    defence-in-depth with a clearer error message, and it is NOT independently pinned — found by
    mutation testing, recorded here rather than papered over with a contrived case.
    """
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(30, CATS)))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    other = tmp_path / "other.json"
    other.write_text(json.dumps(_corpus(31, CATS)))       # a different population
    d = json.loads(out.read_text())
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))
    assert RR.score(other, rr, 0.40, RR.manifest_path_for(out)) == 1


def test_rerate_without_rater_provenance_is_refused(drawn):
    """S1-E10 reports this as an INDEPENDENT re-rate — a claim about the rater and the context.

    An artifact recording neither cannot support it, and the freshness of the context is the single
    condition the whole procedure rests on.
    """
    src, answer, _, _, man = drawn
    def drop(d, _by_id):
        d.pop("rerate_provenance", None)
    assert RR.score(src, answer(drop), 0.40, man) == 1

    def partial(d, _by_id):
        d["rerate_provenance"] = {"rater": "claude-opus-5"}      # no context recorded
    assert RR.score(src, answer(partial), 0.40, man) == 1


def test_gate_result_is_written_as_an_artifact(drawn, tmp_path):
    """The verdict must not exist only as terminal text.

    The manifest roll-ups are filled from it, and the project rule is that tables are generated from
    logs rather than transcribed — a verdict in a scrollback cannot be regenerated, diffed or cited.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "result.json"
    assert RR.score(src, answer(), 0.40, man, res) == 0
    d = json.loads(res.read_text())
    assert d["agreement_floor"] == 0.40
    assert d["rerate_provenance"]["context"]
    assert set(d) >= {"per_category", "categories_driving_build_order", "categories_excluded",
                      "overall_kappa_primary", "verdict_rule", "interpretation_limit"}
    for cat, row in d["per_category"].items():
        assert row["drives_build_order"] == (cat not in d["categories_excluded"])


def test_verdict_requires_both_axes(tmp_path, capsys):
    """A category with PERFECT primary agreement must still be excluded if its any-label kappa fails.

    This is the exact shape the reference corpus presents: `latency_or_budget` is a SECONDARY label on
    nearly every episode, so a category can be designated primary completely reproducibly while the two
    passes disagree about whether it applies at all. The verdict column once read the primary axis
    alone and printed "yes" at kappa 1.0 beside a full-label kappa of 0.0.

    Construction: `goal_unknown` is the primary on a third of the episodes — reproduced exactly — and
    ALSO a secondary on the rest, which the re-rate drops. Primary kappa 1.0, any-label kappa below
    floor, so the verdict must be NO on the any-label axis specifically.
    """
    eps = []
    for i in range(30):
        prim = CATS[i % 3]
        e = _ep("v2", f"g{i}", 1, evidence=f"r-{i}")
        e["primary_label"] = prim
        labels = [{"category": prim, "confidence": "high"}]
        if prim != "goal_unknown":                     # goal_unknown also rides as a secondary here
            labels.append({"category": "goal_unknown", "confidence": "med"})
        e["labels"] = labels
        e["labelling"] = {"pass": "first", "rater": "claude-opus-5"}
        eps.append(e)
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"episodes": eps}))
    out_p = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out_p) == 0

    by_id = {e["episode_id"]: e for e in eps}
    d = json.loads(out_p.read_text())
    for e in d["episodes"]:
        prim = by_id[e["episode_id"]]["primary_label"]
        e["primary_label"] = prim
        e["labels"] = [{"category": prim, "confidence": "high"}]     # secondaries dropped
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    assert RR.score(src, rr, 0.40, RR.manifest_path_for(out_p)) == 0
    out = capsys.readouterr().out
    verdict = out.split("VERDICT")[1]
    row = next(l for l in verdict.splitlines() if l.startswith("goal_unknown"))
    assert "1.0" in row, row                                   # primary axis is perfect
    assert "NO — fails any-label" in row, row                  # and it is still excluded
    assert "goal_unknown" in out.split("EXCLUDED")[1]


def test_forged_packet_digests_over_correct_ids_are_refused(drawn, capsys):
    """Correct episode IDs plus re-forged digests must not authorise a rewritten packet.

    Re-deriving MEMBERSHIP proved which episodes were drawn but said nothing about their contents,
    and the contents were checked against the manifest — which the same hand writes. With the IDs
    left intact, mutating the packet and recomputing the manifest's digests passed every check.
    Integrity is now reconstructed from the corpus via `blind_episode`, so the manifest cannot
    vouch for material the corpus contradicts.

    Asserts on the MESSAGE, not just the exit code. Mutation testing showed that reverting the digest
    source to the manifest still refused — via the separate manifest-vs-corpus consistency check — so
    an exit-code assertion passed while the guard it names was disabled.
    """
    src, answer, _, _, man = drawn

    def mutate_packet(d, _by_id):
        for e in d["episodes"][:6]:
            e["actions_taken"] = 1
            e["human_baseline"] = 9999
            e["censored_at_seconds"] = None
            e["budget_terminated"] = False
    rr = answer(mutate_packet)

    forged = json.loads(man.read_text())
    forged["episodes"] = {e["episode_id"]: RR.episode_digest(e)
                          for e in json.loads(rr.read_text())["episodes"]}
    fman = rr.with_name("forged.manifest.json")
    fman.write_text(json.dumps(forged))

    capsys.readouterr()
    assert RR.score(src, rr, 0.40, fman) == 1
    out = capsys.readouterr().out
    assert "does not match the corpus" in out, out
    assert "Reconstructed from the first-pass corpus" in out, out


@pytest.mark.parametrize("prov,why", [
    ({"rater": ".", "context": "x", "date": "nope"}, "all three fields junk"),
    ({"rater": "claude-opus-5", "context": "x", "date": "2026-07-28"}, "context not controlled"),
    ({"rater": "ab", "context": "fresh session, no access to the first pass",
      "date": "2026-07-28"}, "rater too short to identify anyone"),
    ({"rater": "claude-opus-5", "context": "fresh session, no access to the first pass",
      "date": "28/07/2026"}, "date not ISO"),
])
def test_semantically_invalid_provenance_is_refused(drawn, prov, why):
    """Non-empty is not the same as meaningful.

    A truthiness test accepted rater "." and context "x": the appearance of provenance rather than
    provenance, which is worse than an absent field because it reads as compliant. `context` asserts
    the one condition the procedure rests on, so it is a controlled value, not free text.
    """
    src, answer, _, _, man = drawn

    def set_prov(d, _by_id):
        d["rerate_provenance"] = dict(prov)
    assert RR.score(src, answer(set_prov), 0.40, man) == 1, why


@pytest.mark.parametrize("break_it,why", [
    (lambda e: e.update(primary_label="NOT_A_CATEGORY"), "primary outside the taxonomy"),
    (lambda e: e.update(labels=[{"category": "goal_unknown", "confidence": "ultra"}],
                        primary_label="goal_unknown"), "invented confidence"),
    (lambda e: e.update(labels=[{"category": "goal_unknown", "confidence": "high"},
                                {"category": "goal_unknown", "confidence": "low"}],
                        primary_label="goal_unknown"), "repeated category"),
    (lambda e: e.update(labels=[{"category": "goal_unknown", "confidence": "high"}],
                        primary_label="latency_or_budget"), "primary absent from its own labels"),
    (lambda e: e.update(labels=[], primary_label="goal_unknown"), "empty label list"),
])
def test_malformed_rerate_labels_are_refused(drawn, break_it, why):
    """The FIRST pass is validated by `s1d_apply_labels.py`; the second was validated nowhere.

    An invented category or a primary absent from its own list corrupts the agreement statistic
    rather than being caught by it — `primary_share` and `episode_share` would disagree about what
    was observed.
    """
    src, answer, _, _, man = drawn

    def mutate(d, _by_id):
        break_it(d["episodes"][0])
    assert RR.score(src, answer(mutate), 0.40, man) == 1, why


def test_short_draw_is_marked_in_the_gate_result(tmp_path, capsys):
    """A gate scored below the pre-registered size must not write a normal-looking result.

    `--allow-short` was recorded at draw time and went no further, so a verdict reached on 20 of 30
    produced a result JSON indistinguishable from a complete one — and that file is what the manifest
    roll-ups are filled from.
    """
    src = tmp_path / "c20.json"
    corpus = _corpus(20, CATS)
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out, True) == 0          # deliberately short, explicitly accepted
    man = RR.manifest_path_for(out)

    by_id = {e["episode_id"]: e for e in corpus["episodes"]}
    d = json.loads(out.read_text())
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    res = tmp_path / "res.json"
    capsys.readouterr()
    assert RR.score(src, rr, 0.40, man, res) == 0
    assert "SHORT DRAW" in capsys.readouterr().out

    got = json.loads(res.read_text())
    assert got["short_draw"] is True
    assert got["sample_size_requested"] == 30
    assert got["sample_size_scored"] == 20
    assert "BELOW THE PRE-REGISTERED SAMPLE SIZE" in got["short_draw_warning"]


# ------------------------------------------------------- boundaries (found by mutation testing)
# Every test below exists because a mutation survived: the line it pins could be deleted or its
# comparison loosened and the suite stayed green. Boundary conditions are the recurring blind spot —
# `>=` reads correct and tests written with clearly-passing values never exercise the edge.

def _rerate_from(corpus_path: Path, out: Path, tmp_path: Path, assign, n=30, seed=1):
    """Draw, then answer each episode with `assign(index, corpus_episode) -> (primary, labels)`."""
    corpus = json.loads(corpus_path.read_text())
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}
    assert RR.draw(corpus_path, n, seed, out) == 0
    d = json.loads(out.read_text())
    for i, e in enumerate(d["episodes"]):
        prim, labels = assign(i, by_id[e["episode_id"]])
        e["primary_label"], e["labels"] = prim, labels
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr_b.json"
    rr.write_text(json.dumps(d))
    return rr, RR.manifest_path_for(out)


def test_a_category_exactly_at_the_agreement_floor_passes(tmp_path, capsys):
    """`agreement_floor: 0.40` is pre-registered as a floor, so kappa == floor must PASS.

    Mutating `kp >= floor` to `kp > floor` survived the whole suite: every existing test used
    clearly-passing or clearly-failing agreement, so nothing exercised the boundary the gate is
    literally defined by. An off-by-one here silently excludes a category that met the criterion.
    """
    # Construct disagreement tuned so one category lands exactly on 0.40 by both measures.
    # 10 episodes: 8 agree on `goal_unknown`/`latency_or_budget`, 2 disagree — kappa 0.4 for a
    # balanced 2-category split with 2 swaps out of 10.
    cats = ["goal_unknown", "latency_or_budget"]
    eps = []
    for i in range(10):
        c = cats[i % 2]
        e = _ep("v2", f"g{i}", 1, evidence=f"r-{i}")
        e["primary_label"] = c
        e["labels"] = [{"category": c, "confidence": "high"}]
        e["labelling"] = {"pass": "first", "rater": "claude-opus-5"}
        eps.append(e)
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"episodes": eps}))

    def assign(i, orig):
        # swap 3 of 10 -> po = 0.7, pe = 0.5, kappa = 0.4 exactly
        c = orig["primary_label"]
        if i < 3:
            c = cats[1] if c == cats[0] else cats[0]
        return c, [{"category": c, "confidence": "high"}]

    rr, man = _rerate_from(src, tmp_path / "d.json", tmp_path, assign, n=10)
    res = tmp_path / "res.json"
    capsys.readouterr()
    assert RR.score(src, rr, 0.40, man, res) == 0
    out = capsys.readouterr().out
    assert "overall kappa: 0.4" in out, out
    verdict = out.split("VERDICT")[1]
    for cat in cats:
        row = next(l for l in verdict.splitlines() if l.startswith(cat))
        assert "0.4" in row and "yes" in row, f"kappa exactly at the floor must pass: {row}"
    # 10 episodes is not the pre-registered 30, so this run is diagnostic; the FLOOR COMPARISON is
    # still what is under test, and it is reported per category regardless.
    got = json.loads(res.read_text())
    for cat in cats:
        assert got["per_category"][cat]["clears_requested_floor"] is True


def test_a_complete_draw_is_not_marked_short(tmp_path):
    """`len(...) < n` must not become `<=`, or a complete draw reports itself as short.

    Three separate `len(common) < (m_n or 0)` comparisons and two in `draw` all survived, because
    every short-draw test used 20-of-30 and every complete test never asserted the flag was False.
    """
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(30, CATS)))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    assert json.loads(out.read_text())["short_draw"] is False

    def assign(_i, orig):
        return orig["primary_label"], copy.deepcopy(orig["labels"])
    rr, man = _rerate_from(src, tmp_path / "d2.json", tmp_path, assign, n=30)
    res = tmp_path / "res.json"
    assert RR.score(src, rr, 0.40, man, res) == 0
    got = json.loads(res.read_text())
    assert got["short_draw"] is False
    assert got["sample_size_scored"] == got["sample_size_requested"] == 30
    assert got["short_draw_warning"] is None


def test_rater_name_length_boundary(tmp_path):
    """`len(rater) < 3` must not loosen to `<=`: a 3-character rater is acceptable, 2 is not.

    The identity rule would otherwise mask this, so the corpus records `abc` as its first-pass rater:
    a matching 3-character name is then accepted on identity and must also clear the length rule,
    while `ab` fails the length rule even though it is not the recorded identity either.
    """
    corpus = _corpus(10, CATS)
    for e in corpus["episodes"]:
        e["labelling"] = {"pass": "first", "rater": "abc"}   # identity check must not mask the length
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}

    def rr_with(rater):
        out = tmp_path / f"d_{rater}.json"
        assert RR.draw(src, 10, 1, out) == 0
        d = json.loads(out.read_text())
        for e in d["episodes"]:
            s = by_id[e["episode_id"]]
            e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
        d["rerate_provenance"] = dict(PROVENANCE, rater=rater)
        p = tmp_path / f"rr_{rater}.json"
        p.write_text(json.dumps(d))
        return p, RR.manifest_path_for(out)

    rr, man = rr_with("abc")
    assert RR.score(src, rr, 0.40, man) == 0
    rr, man = rr_with("ab")
    assert RR.score(src, rr, 0.40, man) == 1


# ------------------------------------------------------- corpus admissibility rules

def test_censored_episodes_are_excluded_unless_allowed(build_corpus):
    """S1-E9 admissibility: a run that stopped early is an operator kill, not a failure episode."""
    ep = _ep("v2", "a", 1)
    ep["terminal_state"] = "cancelled"                     # not in AGENT_FINISHED, no budget info
    d_excl = build_corpus({"v2": [ep]}, {"v2": "CONFIG-A"}, allow_censored=False)
    assert d_excl["n_episodes"] == 0
    assert d_excl["excluded_censored_run_never_completed"]
    d_incl = build_corpus({"v2": [copy.deepcopy(ep)]}, {"v2": "CONFIG-A"}, allow_censored=True)
    assert d_incl["n_episodes"] == 1


def test_require_evidence_drops_episodes_with_no_reasoning(build_corpus):
    """Three categories are defined on reasoning text; keeping an evidence-less episode makes them
    look rarer than they are."""
    bare = _ep("v2", "a", 1)
    bare["evidence"] = {"reasoning_by_step": {}}
    d = build_corpus({"v2": [bare, _ep("v2", "b", 1)]}, {"v2": "CONFIG-A"}, require_evidence=True)
    assert {e["game"] for e in d["episodes"]} == {"b"}
    assert d["excluded_no_reasoning_evidence"]


def test_duplicate_run_pass_gamelevel_enters_once(build_corpus):
    """The `key in chosen` guard: identical (game, level, run, pass) is one episode, not two."""
    e1, e2 = _ep("v2", "a", 1), _ep("v2", "a", 1)
    e2["actions_taken"] = 999
    d = build_corpus({"v2": [e1, e2]}, {"v2": "CONFIG-A"})
    assert d["n_episodes"] == 1
    assert d["excluded_duplicate_game_level"]


def test_wallclock_is_read_per_pass_not_per_game(tmp_path):
    """`game_runs` is passes-major and repeats the game id, so the k-th match is pass k.

    Returning the first match served p0's wall clock for every pass — the same one-identity-for-many
    -runs defect that corrupted the reference episode file, reached through the pass axis.
    """
    p = tmp_path / "r"
    p.mkdir()
    (p / "benchmark.json").write_text(json.dumps({"label": "L", "n_passes": 3, "game_runs": [
        {"game_id": "a", "final_wallclock_seconds": 100.0},
        {"game_id": "b", "final_wallclock_seconds": 111.0},
        {"game_id": "a", "final_wallclock_seconds": 200.0},
        {"game_id": "b", "final_wallclock_seconds": 222.0},
        {"game_id": "a", "final_wallclock_seconds": 300.0},
    ]}))
    assert B._wallclock(p, "a", 0) == 100.0
    assert B._wallclock(p, "a", 1) == 200.0
    assert B._wallclock(p, "a", 2) == 300.0
    assert B._wallclock(p, "a", 3) is None
    assert B._wallclock(p, "b", 1) == 222.0


# ------------------------------------------------------- re-rate input validation

@pytest.mark.parametrize("labels", [
    "not-a-list",
    [["category", "goal_unknown"]],
    [{"confidence": "high"}],
])
def test_structurally_malformed_label_containers_are_refused(drawn, labels):
    """`validate_labels` must reject shapes, not only bad values: a non-list `labels`, or an entry
    that is not a dict with a `category`, would otherwise reach the kappa computation."""
    src, answer, _, _, man = drawn

    def mutate(d, _b):
        d["episodes"][0]["labels"] = copy.deepcopy(labels)
        d["episodes"][0]["primary_label"] = "goal_unknown"
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.score(src, answer(mutate), 0.40, man)
    assert rc == 1
    # Message-asserted: without the shape guard these raise TypeError/KeyError inside
    # validate_labels, which the exception handler would convert into a refusal anyway.
    assert "schema error" in buf.getvalue(), buf.getvalue()


def test_draw_refuses_an_unlabelled_corpus(tmp_path):
    """label -> sample -> blind. A corpus with no primary labels cannot be stratified."""
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"episodes": [_ep("v2", "a", 1)]}))
    assert RR.draw(src, 5, 1, tmp_path / "d.json") == 2


@pytest.mark.parametrize("drop", ["seed", "requested"])
def test_manifest_missing_its_own_parameters_is_refused(drawn, drop):
    """Without `seed` and `requested` the sample cannot be re-derived, only trusted.

    NOTE the split, which this test got wrong first time round: `seed` and `requested` are read from
    the MANIFEST (they drive re-derivation), while `drawn` is read from the RE-RATE file (it drives
    the completeness check). Removing `drawn` from the manifest changes nothing — covered separately
    by `test_rerate_missing_its_drawn_count_is_refused`.
    """
    src, answer, _, _, man = drawn
    broken = json.loads(man.read_text())
    broken.pop(drop)
    bad = man.with_name("broken.manifest.json")
    bad.write_text(json.dumps(broken))
    assert RR.score(src, answer(), 0.40, bad) == 1


def test_rerate_missing_its_drawn_count_is_refused(drawn):
    """`drawn` lives on the re-rate artifact and is what completeness is measured against."""
    src, answer, _, _, man = drawn

    def drop_drawn(d, _b):
        d.pop("drawn", None)
    assert RR.score(src, answer(drop_drawn), 0.40, man) == 1


def test_a_complete_draw_prints_no_short_draw_banner(tmp_path, capsys):
    """The banner condition is a separate `<` from the recorded flag, and needs its own boundary.

    Asserting only that the flag is False left the printed warning free to fire on a complete draw,
    which is the version an operator actually reads.
    """
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(30, CATS)))

    def assign(_i, orig):
        return orig["primary_label"], copy.deepcopy(orig["labels"])
    rr, man = _rerate_from(src, tmp_path / "d.json", tmp_path, assign, n=30)
    assert json.loads((tmp_path / "d.json").read_text())["short_draw_note"] is None
    capsys.readouterr()
    assert RR.score(src, rr, 0.40, man) == 0
    assert "SHORT DRAW" not in capsys.readouterr().out


def test_partially_labelled_rerate_is_refused_as_incomplete(drawn, capsys):
    """Membership and count can both be intact while the PASS is unfinished.

    Truncation deletes episodes; abandonment leaves them in place unlabelled. Only the second reaches
    the `len(common) < expected` guard, and no test produced it.
    """
    src, answer, _, _, man = drawn

    def unlabel_some(d, _b):
        for e in d["episodes"][:7]:
            e["primary_label"] = None
            e["labels"] = []
    capsys.readouterr()
    assert RR.score(src, answer(unlabel_some), 0.40, man) == 1
    assert "carry a re-rate label" in capsys.readouterr().out


def test_truncation_is_caught_by_the_count_check_specifically(drawn, capsys):
    """Isolates the count guard from the re-derivation that also catches truncation.

    Both refuse, so an exit-code assertion cannot tell which fired — the same trap that let the
    forged-digest test pass with its guard disabled.
    """
    src, answer, _, _, man = drawn

    def cut(d, _b):
        d["episodes"] = d["episodes"][:5]
    capsys.readouterr()
    assert RR.score(src, answer(cut), 0.40, man) == 1
    assert "Episodes were removed from the sample after it was drawn" in capsys.readouterr().out


def test_rerate_without_drawn_is_caught_by_its_own_guard(drawn, capsys):
    """Isolates the `declared is None` branch from the count comparison downstream."""
    src, answer, _, _, man = drawn

    def drop_drawn(d, _b):
        d.pop("drawn", None)
    capsys.readouterr()
    assert RR.score(src, answer(drop_drawn), 0.40, man) == 1
    assert "does not record `drawn`" in capsys.readouterr().out


# ---------------------------------------- de-allowlisted: these change gate behaviour, not messages

def test_s1e4_eligibility_restricts_the_oversampled_stratum(tmp_path):
    """S1-E4 changes WHICH EPISODES ARE DRAWN, so it is sample composition, not a message.

    `exploration_or_probe_selection` is oversampled only on games exposing no ACTION6 at the rated
    steps, because elsewhere the alternative action is a coordinate and the evidence the category is
    defined against does not exist. Disabling the restriction pulls ineligible episodes into the
    stratum and changes the deterministic sample — which was allowlisted as "defensive" and is not.
    """
    simple = sorted(RR.SIMPLE_ACTION_GAMES)[0]
    assert RR.eligible_for("exploration_or_probe_selection", {"game": simple}) is True
    assert RR.eligible_for("exploration_or_probe_selection", {"game": "zzzz-nocoords"}) is False
    # Every other category is unrestricted, whatever the game.
    assert RR.eligible_for("goal_unknown", {"game": "zzzz-nocoords"}) is True

    # And it moves the drawn sample, not just a printed count.
    eps = []
    for i in range(12):
        game = simple if i % 2 == 0 else f"other-{i}"
        e = _ep("v2", game, 1, evidence=f"r-{i}")
        e["game"] = game
        e["primary_label"] = "exploration_or_probe_selection"
        e["labels"] = [{"category": "exploration_or_probe_selection", "confidence": "high"}]
        e["labelling"] = {"pass": "first", "rater": "claude-opus-5"}
        eps.append(e)
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"episodes": eps}))
    out = tmp_path / "d.json"
    assert RR.draw(src, 4, 1, out) == 0
    payload = json.loads(out.read_text())
    elig = payload["eligibility"]["eligible_of_total"]["exploration_or_probe_selection"]
    assert elig == "6/12", elig          # only the simple-action half is eligible


def test_eligible_of_total_is_reported_accurately(tmp_path):
    """The eligible fraction is a recorded artifact field, not decoration.

    "An agreement number computed on a subset must say which subset" — so a mutation that changes
    only this field still changes what the artifact claims about its own sample.
    """
    eps = []
    for i in range(9):
        c = "goal_unknown" if i < 5 else "perception_parsing"
        e = _ep("v2", f"g{i}", 1, evidence=f"r-{i}")
        e["primary_label"] = c
        e["labels"] = [{"category": c, "confidence": "high"}]
        e["labelling"] = {"pass": "first", "rater": "claude-opus-5"}
        eps.append(e)
    src = tmp_path / "c.json"
    src.write_text(json.dumps({"episodes": eps}))
    out = tmp_path / "d.json"
    assert RR.draw(src, 9, 1, out) == 0
    got = json.loads(out.read_text())["eligibility"]["eligible_of_total"]
    assert got["goal_unknown"] == "5/5"
    assert got["exploration_or_probe_selection"] == "0/0"


@pytest.mark.parametrize("wall,admitted", [
    (7920.0, True),                          # exactly the budget
    (0.98 * 7920.0, True),                   # EXACTLY the tolerance: inclusive, so `>=` not `>`
    (0.98 * 7920.0 - 1e-6, False),           # a hair under: an early stop, not a budget expiry
    (100.0, False),                          # plainly killed early
])
def test_censoring_tolerance_boundary_decides_admission(tmp_path, monkeypatch, wall, admitted):
    """S1-E9 admissibility turns on `wall >= 0.98 * budget`, which ADMITS OR DROPS an episode.

    Allowlisted as defensive; it is not. `cancelled` is recorded both by a budget expiry and by an
    operator kill, and only this comparison separates them — so the tolerance decides which episodes
    enter the corpus the build order is ranked on.
    """
    ep = _ep("v2", "a", 1)
    ep["terminal_state"] = "cancelled"          # not agent-finished: only the wall clock can admit it
    monkeypatch.setattr(B, "extract_episodes", lambda rd: {"episodes": [copy.deepcopy(ep)]})
    monkeypatch.setattr(B, "_config_signature", lambda rd: "CONFIG-A")
    monkeypatch.setattr(B, "_budget_seconds", lambda rd: 7920.0)
    monkeypatch.setattr(B, "_wallclock", lambda rd, g, p=0: wall)
    monkeypatch.setattr(B, "frequencies", lambda eps: {})
    rd = tmp_path / "v2"
    rd.mkdir()
    out = tmp_path / "corpus.json"
    B.build([rd], False, False, out, True)      # allow_censored=False: admission is the question
    d = json.loads(out.read_text())
    assert (d["n_episodes"] == 1) is admitted, d["excluded_censored_run_never_completed"]


# ---------------------------------------------------------------- gate validity and result integrity

def test_first_pass_labels_cannot_be_edited_after_the_draw(drawn):
    """The first pass is one side of the comparison and nothing else protects it.

    `blind_episode` strips labels by design, so packet reconstruction cannot see them, and
    `corpus_digest` hashed only episode ids. Adding a secondary label to every sampled episode after
    drawing changed the outcome — a new category appeared at kappa 0.0 and was excluded from the
    build order — while membership, digests and evidence all still verified.
    """
    src, answer, _, corpus, man = drawn
    rr = answer()
    tampered = copy.deepcopy(corpus)
    for e in tampered["episodes"]:
        e["labels"] = e["labels"] + [{"category": "invalid_output_interface", "confidence": "med"}]
    bad = src.with_name("tampered_corpus.json")
    bad.write_text(json.dumps(tampered))
    assert RR.score(bad, rr, 0.40, man) == 1


def test_corpus_digest_covers_order_as_well_as_content(drawn):
    """`select()` consumes the corpus positionally, so a reordered corpus is a different sample."""
    src, answer, _, corpus, man = drawn
    rr = answer()
    reordered = copy.deepcopy(corpus)
    reordered["episodes"] = list(reversed(reordered["episodes"]))
    other = src.with_name("reordered.json")
    other.write_text(json.dumps(reordered))
    assert RR.score(other, rr, 0.40, man) == 1


@pytest.mark.parametrize("floor", [0.0, 0.3, 0.5, 1.0])
def test_a_non_preregistered_floor_is_diagnostic_only(drawn, tmp_path, floor):
    """`agreement_floor: 0.40` is frozen, so a run at any other floor is not the gate.

    At 0.0 the scorer exited 0 and wrote a file titled "the gate result" in which nothing could ever
    be excluded. It still runs — an alternate floor is a legitimate sensitivity check — but it must
    not present itself as the gate, and it must withhold the verdict rather than emit an empty one.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / f"res_{floor}.json"
    assert RR.score(src, answer(), floor, man, res) == 0
    got = json.loads(res.read_text())
    assert got["gate_valid"] is False
    assert got["categories_driving_build_order"] is None
    assert got["categories_excluded"] is None
    assert any("not the pre-registered" in r for r in got["gate_invalid_reasons"])
    assert got["per_category"], "the kappas are still real measurements and are kept"


def test_the_preregistered_floor_is_the_gate(drawn, tmp_path):
    """The converse: at exactly 0.40 the run IS the gate and does emit a verdict."""
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    assert RR.score(src, answer(), RR.GATE_FLOOR, man, res) == 0
    got = json.loads(res.read_text())
    assert got["gate_valid"] is True
    assert got["gate_invalid_reasons"] is None
    assert isinstance(got["categories_driving_build_order"], list)


def test_a_short_draw_is_not_a_gate_result(tmp_path):
    """A warning does not stop a roll-up reading `categories_driving_build_order`.

    The 20-of-30 case previously exited 0 with a populated verdict and a file describing itself as
    the gate result. The floor was applied to fewer episodes than `sample_size` specifies, so the
    verdict is withheld outright rather than annotated.
    """
    src = tmp_path / "c20.json"
    corpus = _corpus(20, CATS)
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out, True) == 0
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}
    d = json.loads(out.read_text())
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    res = tmp_path / "res.json"
    assert RR.score(src, rr, 0.40, man := RR.manifest_path_for(out), res) == 0
    got = json.loads(res.read_text())
    assert got["gate_valid"] is False
    assert got["categories_driving_build_order"] is None
    assert any("sample size" in r for r in got["gate_invalid_reasons"])
    assert man.exists()


def test_a_refused_run_overwrites_any_earlier_result(drawn, tmp_path):
    """Failure must be recorded where success would have been, or success is not falsifiable.

    A refused run used to leave the previous result untouched: `logs/s1d_rerate_result.json` sat on
    disk holding a `NOT_A_CATEGORY` label and a full build-order verdict, produced from inputs the
    current scorer rejects outright. Anything reading that path read a verdict no run produced.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    assert RR.score(src, answer(), 0.40, man, res) == 0
    assert json.loads(res.read_text())["gate_valid"] is True

    def break_it(d, _b):
        d["episodes"][0]["primary_label"] = "NOT_A_CATEGORY"
    assert RR.score(src, answer(break_it), 0.40, man, res) == 1
    got = json.loads(res.read_text())
    assert got["refused"] is True
    assert got["gate_valid"] is False
    assert got["categories_driving_build_order"] is None
    assert "REFUSED" in got["reason"]


def test_rerate_by_a_different_model_is_refused(drawn):
    """The artifact asserts "same model" unconditionally, so it has to be true.

    A different rater measures inter-rater agreement between two models — not the intra-model
    stability S1-E10 describes, and not what the agreement floor was chosen for.
    """
    src, answer, _, _, man = drawn

    def other_model(d, _b):
        d["rerate_provenance"] = dict(PROVENANCE, rater="different-model")
    assert RR.score(src, answer(other_model), 0.40, man) == 1


@pytest.mark.parametrize("date", ["2026-99-99", "2026-02-30", "2026-13-01", "20260728"])
def test_impossible_dates_are_refused(drawn, date):
    """ISO-SHAPED is not the same as a real calendar date; `2026-99-99` matched the old regex."""
    src, answer, _, _, man = drawn

    def bad_date(d, _b):
        d["rerate_provenance"] = dict(PROVENANCE, date=date)
    assert RR.score(src, answer(bad_date), 0.40, man) == 1


def test_manifest_without_a_corpus_digest_is_refused(drawn):
    """No corpus digest means the first pass could have been edited after the draw, unobserved.

    `seed` and `requested` let the SAMPLE be re-derived; only `corpus_digest` binds the ANNOTATIONS
    the agreement is computed against, which blinding deliberately removes from the packet.
    """
    src, answer, _, _, man = drawn
    broken = json.loads(man.read_text())
    broken.pop("corpus_digest")
    bad = man.with_name("nodigest.manifest.json")
    bad.write_text(json.dumps(broken))
    # Message-asserted: an absent digest also fails the != comparison below it, so an exit-code
    # assertion would pass with this guard removed.
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.score(src, answer(), 0.40, bad)
    assert rc == 1
    assert "records no `corpus_digest`" in buf.getvalue(), buf.getvalue()


# ---------------------------------------------------------- pre-registered size, and failing closed

def test_a_self_consistent_20_of_20_draw_is_not_the_gate(tmp_path):
    """`sample_size: 30` is pre-registered, so a run that requests 20 and scores 20 is not it.

    The size check compared the scored count against the manifest's OWN `requested`, which the draw
    chooses — so any self-consistent draw was "complete" and produced a full build-order verdict.
    Both numbers must equal the pre-registered size.
    """
    corpus = _corpus(20, CATS)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}
    out = tmp_path / "d.json"
    assert RR.draw(src, 20, 1, out) == 0                 # a complete 20-of-20 draw, no --allow-short
    d = json.loads(out.read_text())
    assert d["short_draw"] is False                      # ... and it does not consider itself short
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    res = tmp_path / "res.json"
    assert RR.score(src, rr, 0.40, RR.manifest_path_for(out), res) == 0
    got = json.loads(res.read_text())
    assert got["gate_valid"] is False
    assert got["categories_driving_build_order"] is None
    assert any(str(RR.PREREGISTERED_SAMPLE_SIZE) in r for r in got["gate_invalid_reasons"])


def test_invalid_first_pass_labels_are_refused_by_draw_and_score(tmp_path):
    """The digest COMMITS the annotations; it does not make them legal.

    Validation covers the whole first pass rather than the sampled slice, because `select()`
    stratifies on every label — a malformed one shifts WHICH episodes are drawn even when it is not
    itself drawn, so a scoped check would validate a sample the bad label had already moved.
    """
    corpus = _corpus(30, CATS)
    corpus["episodes"][0]["primary_label"] = "NOT_A_CATEGORY"
    corpus["episodes"][0]["labels"] = [{"category": "NOT_A_CATEGORY", "confidence": "high"}]
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    assert RR.draw(src, 30, 1, tmp_path / "d.json") == 1

    # And at score time, for a manifest drawn before the check existed.
    clean = _corpus(30, CATS)
    csrc = tmp_path / "clean.json"
    csrc.write_text(json.dumps(clean))
    out = tmp_path / "dc.json"
    assert RR.draw(csrc, 30, 1, out) == 0
    by_id = {e["episode_id"]: e for e in clean["episodes"]}
    d = json.loads(out.read_text())
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))

    labelled = [e for e in corpus["episodes"] if e.get("primary_label")]
    man = json.loads(RR.manifest_path_for(out).read_text())
    man["corpus_digest"] = RR.corpus_digest(labelled)
    picked = RR.select(labelled, man["requested"], man["seed"])
    man["episodes"] = {e["episode_id"]: RR.episode_digest(RR.blind_episode(e)) for e in picked}
    bad_man = tmp_path / "bad.manifest.json"
    bad_man.write_text(json.dumps(man))
    d["episodes"] = [RR.blind_episode(e) for e in picked]
    d["drawn"] = len(d["episodes"])
    for e in d["episodes"]:
        e["primary_label"] = "goal_unknown"
        e["labels"] = [{"category": "goal_unknown", "confidence": "high"}]
    rr2 = tmp_path / "rr2.json"
    rr2.write_text(json.dumps(d))
    assert RR.score(src, rr2, 0.40, bad_man) == 1


@pytest.mark.parametrize("broken", ['{"episodes": [', "not json at all", ""])
def test_malformed_input_writes_a_refusal_instead_of_crashing(drawn, tmp_path, broken):
    """A crash is a failed run and must leave the trace a refusal leaves.

    Only non-zero RETURNS were handled, so truncated JSON raised out of `score()` and the previous,
    valid-looking verdict stayed on disk — the stale-artifact failure reached by a different route.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    assert RR.score(src, answer(), 0.40, man, res) == 0
    assert json.loads(res.read_text())["gate_valid"] is True

    bad = tmp_path / "broken.json"
    bad.write_text(broken)
    assert RR.score(src, bad, 0.40, man, res) == 1       # returns, does not raise
    got = json.loads(res.read_text())
    assert got["refused"] is True and got["gate_valid"] is False
    assert got["categories_driving_build_order"] is None


def test_diagnostic_runs_carry_no_per_category_verdict(drawn, tmp_path):
    """Nulling the top-level lists is not enough — a roll-up reads the rows.

    `drives_build_order` is a VERDICT and exists only for a gate run. `clears_requested_floor` is the
    STATISTIC and is always present, so a diagnostic run still reports what it measured.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    assert RR.score(src, answer(), 0.0, man, res) == 0
    got = json.loads(res.read_text())
    assert got["gate_valid"] is False
    assert got["per_category"], "the measurements are kept"
    assert all(r["drives_build_order"] is None for r in got["per_category"].values())
    assert all(isinstance(r["clears_requested_floor"], bool) for r in got["per_category"].values())


def test_same_model_check_fails_closed(drawn, tmp_path):
    """Absent or ambiguous first-pass identity must refuse, not wave through.

    With no recorded rater the check was skipped entirely; with several recorded, matching any one
    sufficed. Both leave "same model" asserted on evidence that does not establish it.
    """
    src, answer, _, corpus, man = drawn
    rr = answer()

    none_recorded = copy.deepcopy(corpus)
    for e in none_recorded["episodes"]:
        e.pop("labelling", None)
    p1 = src.with_name("norater.json")
    p1.write_text(json.dumps(none_recorded))
    assert RR.score(p1, rr, 0.40, man) == 1

    two_recorded = copy.deepcopy(corpus)
    for i, e in enumerate(two_recorded["episodes"]):
        e["labelling"] = dict(e.get("labelling") or {},
                              rater="claude-opus-5" if i % 2 else "some-other-model")
    p2 = src.with_name("multirater.json")
    p2.write_text(json.dumps(two_recorded))
    assert RR.score(p2, rr, 0.40, man) == 1


# ------------------------------------------------- input binding, single reads, canonical promotion

def test_a_partially_labelled_corpus_is_refused(tmp_path, drawn):
    """`draw` filtered unlabelled episodes out silently, redefining the population.

    A 40-episode corpus with 30 labelled drew and scored as though the corpus were 30, so the
    frequency ranking would rest on whichever episodes happened to have been rated.
    """
    corpus = _corpus(40, CATS)
    for e in corpus["episodes"][30:]:
        e["primary_label"] = None
        e["labels"] = []
    src = tmp_path / "partial.json"
    src.write_text(json.dumps(corpus))
    assert RR.draw(src, 30, 1, tmp_path / "d.json") == 1

    # ... and the same backstop at score time, for a manifest drawn before the check existed.
    _src, answer, _, full, man = drawn
    partial = copy.deepcopy(full)
    for e in partial["episodes"][-3:]:
        e["primary_label"] = None
        e["labels"] = []
    p = tmp_path / "partial2.json"
    p.write_text(json.dumps(partial))
    # Message-asserted: an edited corpus also fails the digest check, so an exit-code assertion would
    # pass with the unlabelled-episode guard removed.
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.score(p, answer(), 0.40, man)
    assert rc == 1
    assert "carry no `primary_label`" in buf.getvalue(), buf.getvalue()


def test_each_input_is_read_exactly_once(tmp_path):
    """A commitment that verifies a different read from the one used for kappa verifies nothing.

    The corpus was parsed twice — once for `first`, which kappa is computed from, and again for
    validation and the digest. A path returning two individually-legal versions passed validation and
    matched the manifest while kappa ran over the uncommitted one, scoring `gate_valid: true` at
    kappa -1.0. Asserted structurally: one read per input, so the object checked IS the object used.
    """
    import inspect
    src = inspect.getsource(RR._score)
    for name in ("first_path", "rerate_path", "manifest_path"):
        assert src.count(f"{name}.read") == 1, f"{name} is read more than once in _score"


def test_results_bind_their_inputs_by_hash(drawn, tmp_path):
    """Paths are mutable; digests are not.

    Recording only paths left a valid-looking result silently detached from what was scored.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    assert RR.score(src, answer(), 0.40, man, res) == 0
    got = json.loads(res.read_text())
    assert got["result_schema_version"] == RR.RESULT_SCHEMA_VERSION
    for name, path in (("first_pass", src), ("manifest", man)):
        assert got["inputs"][name]["sha256"] == RR._sha256(path.read_bytes())
    assert got["manifest_commitment"]["corpus_digest"]
    assert got["manifest_commitment"]["seed"] is not None


def test_score_refuses_to_write_the_canonical_result(drawn, monkeypatch, tmp_path):
    """`score` must never write the file the roll-ups are filled from.

    Under a fixed default output path every invocation wrote there — during this harness's own
    development a fabricated verification run left `gate_valid: true` in it, and an accidental
    failure would equally have destroyed a real verdict.
    """
    from argparse import Namespace
    src, answer, _, _, man = drawn
    rr = answer()
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    monkeypatch.setattr(sys, "argv", ["s1d_blind_rerate.py", "score", str(src), str(rr),
                                      "--manifest", str(man), "--result-out", str(canonical)])
    assert RR.main() == 1
    assert not canonical.exists()


def test_promote_requires_a_valid_gate_and_unchanged_inputs(drawn, tmp_path, monkeypatch):
    """Promotion is the only way onto the canonical path, and it re-checks the inputs.

    Otherwise promotion could launder a result whose corpus or re-rate changed after scoring.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)

    diag = tmp_path / "diag.json"
    assert RR.score(src, answer(), 0.0, man, diag) == 0        # diagnostic floor
    assert RR.promote(diag) == 1                                # not a gate result
    assert not canonical.exists()

    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    assert RR.promote(good) == 0
    assert json.loads(canonical.read_text())["gate_valid"] is True

    # Mutate an input after scoring: promotion must refuse.
    corpus = json.loads(src.read_text())
    corpus["_touched"] = True
    src.write_text(json.dumps(corpus))
    assert RR.promote(good) == 1


def test_promote_refuses_a_missing_input(drawn, tmp_path, monkeypatch):
    """An input that no longer exists cannot be re-verified, so the result cannot be trusted."""
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    src.unlink()
    assert RR.promote(good) == 1
    assert not canonical.exists()


def test_promote_refuses_an_older_result_schema(drawn, tmp_path, monkeypatch):
    """A result written under a different schema may not mean what this build assumes it means."""
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    payload = json.loads(good.read_text())
    payload["result_schema_version"] = RR.RESULT_SCHEMA_VERSION - 1
    good.write_text(json.dumps(payload))
    assert RR.promote(good) == 1
    assert not canonical.exists()


# --------------------------------------------- promotion recomputes; canonical is protected below main

def test_promote_refuses_a_result_that_names_no_inputs(tmp_path, monkeypatch):
    """A self-authored result is only a claim, and a loop over zero inputs verifies zero inputs.

    A hand-written file carrying `gate_valid: true`, an empty `inputs` map and a fabricated
    `categories_driving_build_order` was promoted successfully: every recorded input was checked, and
    there were none.
    """
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps({
        "result_schema_version": RR.RESULT_SCHEMA_VERSION,
        "result_kind": "score",          # otherwise the kind check refuses it before this guard
        "gate_valid": True,
        "inputs": {},
        "categories_driving_build_order": ["FORGED_CATEGORY"],
    }))
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.promote(forged)
    assert rc == 1
    assert "nothing to re-score from" in buf.getvalue(), buf.getvalue()
    assert not canonical.exists()


def test_promote_recomputes_and_ignores_the_submitted_verdict(drawn, tmp_path, monkeypatch, capsys):
    """Correct hashes beside an altered verdict must not survive promotion.

    The payload is a POINTER TO INPUTS. What gets written is the artifact produced by re-scoring
    those inputs at the pre-registered floor, so a forged verdict is simply overwritten by the truth.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    real = tmp_path / "real.json"
    assert RR.score(src, answer(), 0.40, man, real) == 0
    honest = json.loads(real.read_text())["categories_driving_build_order"]

    tampered = json.loads(real.read_text())
    tampered["categories_driving_build_order"] = ["FORGED_CATEGORY"]
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(tampered))       # hashes still correct; only the verdict is a lie

    capsys.readouterr()
    assert RR.promote(forged) == 0
    out = capsys.readouterr().out
    assert "disagreed with a fresh scoring" in out, out
    promoted = json.loads(canonical.read_text())
    assert promoted["categories_driving_build_order"] == honest
    assert "FORGED_CATEGORY" not in json.dumps(promoted)
    assert promoted["promotion_note"]


def test_score_cannot_write_the_canonical_result_as_a_library_call(drawn, tmp_path, monkeypatch):
    """The invariant must hold below `main()`.

    The canonical-path check lived in the CLI wrapper, so `score(..., result_out=CANONICAL_RESULT)`
    walked past it — and the tests and other harness modules call `score` directly.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    with pytest.raises(RR.CanonicalWriteRefused):
        RR.score(src, answer(), 0.40, man, canonical)
    assert not canonical.exists()

    # `write_refusal` goes through the same choke point.
    with pytest.raises(RR.CanonicalWriteRefused):
        RR.write_refusal(canonical, "should not be possible")
    assert not canonical.exists()


def test_invalidate_is_the_deliberate_way_to_withdraw_a_verdict(tmp_path, monkeypatch):
    """`score` cannot reach the canonical file, so withdrawing a promoted verdict needs its own verb."""
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    assert RR.invalidate("superseded corpus", ["v5 lands tomorrow"]) == 0
    got = json.loads(canonical.read_text())
    assert got["gate_valid"] is False and got["refused"] is True
    assert got["categories_driving_build_order"] is None
    assert got["reason"] == "superseded corpus"


def test_draw_reads_the_corpus_exactly_once(tmp_path):
    """The manifest must commit to the snapshot the sample was actually taken from.

    `draw` selected and blinded from one parse and computed `corpus_digest` from a second, so a path
    returning two individually-legal versions committed to a corpus it had not sampled — and scoring
    then accepted the pair at kappa -1.0.
    """
    import inspect
    assert inspect.getsource(RR.draw).count("episodes_path.read") == 1

    # Behavioural check: the digest in the manifest matches the corpus as read at draw time.
    corpus = _corpus(30, CATS)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    out = tmp_path / "d.json"
    assert RR.draw(src, 30, 1, out) == 0
    man = json.loads(RR.manifest_path_for(out).read_text())
    labelled = [e for e in corpus["episodes"] if e.get("primary_label")]
    assert man["corpus_digest"] == RR.corpus_digest(labelled)


def test_promote_refuses_when_rescoring_yields_an_invalid_gate(tmp_path, monkeypatch):
    """Re-scoring can SUCCEED and still not be a gate — e.g. the sample was never size 30.

    A payload can claim `gate_valid: true` over a 20-of-20 run; the recomputation exits 0 but reports
    `gate_valid: false`, and that is what must decide.
    """
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    corpus = _corpus(20, CATS)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    by_id = {e["episode_id"]: e for e in corpus["episodes"]}
    out = tmp_path / "d.json"
    assert RR.draw(src, 20, 1, out) == 0
    d = json.loads(out.read_text())
    for e in d["episodes"]:
        s = by_id[e["episode_id"]]
        e["primary_label"], e["labels"] = s["primary_label"], copy.deepcopy(s["labels"])
    d["rerate_provenance"] = dict(PROVENANCE)
    rr = tmp_path / "rr.json"
    rr.write_text(json.dumps(d))
    res = tmp_path / "res.json"
    man = RR.manifest_path_for(out)
    assert RR.score(src, rr, 0.40, man, res) == 0
    payload = json.loads(res.read_text())
    assert payload["gate_valid"] is False
    payload["gate_valid"] = True                      # forge the claim; inputs are genuine
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(payload))
    assert RR.promote(forged) == 1
    assert not canonical.exists()


def test_promote_refuses_when_rescoring_fails_outright(drawn, tmp_path, monkeypatch):
    """If the named inputs no longer score at all, there is nothing to promote.

    Reached when the payload records no hashes to check first — the early hash comparison is a fast
    signal, not the guarantee; re-scoring is.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    rr = answer()
    res = tmp_path / "res.json"
    assert RR.score(src, rr, 0.40, man, res) == 0

    payload = json.loads(res.read_text())
    for rec in payload["inputs"].values():
        rec.pop("sha256")                             # no hash to short-circuit on
    stripped = tmp_path / "stripped.json"
    stripped.write_text(json.dumps(payload))

    broken = json.loads(rr.read_text())               # make the re-rate unscoreable
    broken["episodes"] = broken["episodes"][:5]
    rr.write_text(json.dumps(broken))

    # Message-asserted: a failed re-score also writes a refusal into the temp result, whose
    # `gate_valid: false` the NEXT guard would catch — so an exit-code assertion cannot tell which
    # of the two fired.
    import contextlib, io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = RR.promote(stripped)
    assert rc == 1
    assert "does not succeed" in buf.getvalue(), buf.getvalue()
    assert not canonical.exists()


# ------------------------------------------------------- path anchoring, concurrency, artifact shape

def test_canonical_path_is_anchored_to_the_module_not_the_cwd(tmp_path, monkeypatch):
    """A protection that depends on where you are standing protects nothing.

    As a bare relative path `CANONICAL_RESULT` resolved against CWD: run from anywhere but the
    repository root it named a different file, so `score --result-out <absolute canonical>` slipped
    past the guard while `promote` installed its verdict somewhere that was not the canonical file.
    """
    expected = Path(RR.__file__).resolve().parents[2] / "logs" / "s1d_rerate_result.json"
    assert RR.CANONICAL_RESULT == expected
    assert RR.CANONICAL_RESULT.is_absolute()

    monkeypatch.chdir(tmp_path)                       # a foreign working directory
    assert RR.CANONICAL_RESULT.resolve() == expected.resolve()
    with pytest.raises(RR.CanonicalWriteRefused):
        RR.write_refusal(expected, "absolute-path bypass from a foreign cwd")


def test_concurrent_writers_do_not_corrupt_a_result(tmp_path):
    """A shared `<name>.tmp` let two writers clobber each other's scratch file.

    One caller could install the other's payload and report success; the other could raise
    FileNotFoundError when its own temp had already been renamed away.
    """
    import threading
    target = tmp_path / "result.json"
    errors: list[str] = []

    def writer(i: int):
        for _ in range(40):
            try:
                RR._write_result(target, {"writer": i, "filler": "x" * 2000})
            except Exception as exc:                  # noqa: BLE001 - the failure under test
                errors.append(repr(exc))

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors[:3]
    assert isinstance(json.loads(target.read_text())["writer"], int)   # never a torn write
    assert not list(tmp_path.glob("result.json.*tmp")), "temp files left behind"


@pytest.mark.parametrize("kind,make", [
    ("refusal", lambda p: RR.write_refusal(p, "because")),
    ("invalidation", None),                            # exercised against CANONICAL_RESULT below
])
def test_every_artifact_carries_a_schema_version(tmp_path, monkeypatch, kind, make):
    """Refusals were unversioned, and the canonical file spends most of its life being one.

    A consumer could not tell the current refusal shape from a legacy or malformed artifact.
    """
    if make is None:
        canonical = tmp_path / "canonical.json"
        monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
        assert RR.invalidate("withdrawn") == 0
        got = json.loads(canonical.read_text())
    else:
        p = tmp_path / "r.json"
        make(p)
        got = json.loads(p.read_text())
    assert got["result_schema_version"] == RR.RESULT_SCHEMA_VERSION
    assert got["result_kind"] == kind
    assert got["gate_valid"] is False


def test_scored_results_record_repo_relative_input_paths(drawn, tmp_path, monkeypatch):
    """Recorded paths must survive both a foreign CWD and a relocated checkout.

    CWD-relative names whatever happens to sit there; absolute makes a byte-identical result
    unpromotable from a clone. Anchored-relative survives both, and inputs genuinely outside the
    repository stay absolute because they are machine-specific by nature.
    """
    src, answer, _, _, man = drawn
    res = tmp_path / "res.json"
    monkeypatch.chdir(tmp_path)
    assert RR.score(src, answer(), 0.40, man, res) == 0
    got = json.loads(res.read_text())
    assert got["result_kind"] == "score"
    assert got["path_anchor"]
    for rec in got["inputs"].values():
        # tmp_path is outside the repo, so these fall back to absolute — and must round-trip.
        assert RR._resolve_recorded(rec["path"]).exists(), rec
    # No duplicate top-level path fields to drift out of step with `inputs`.
    assert not any(k in got for k in ("first_pass", "rerate", "manifest"))


def test_repo_relative_paths_round_trip_through_the_anchor(tmp_path):
    """A path inside the repository is recorded relative and resolved against the repo, not CWD."""
    inside = Path(RR.__file__).resolve()
    rel = RR._rel(inside)
    assert not Path(rel).is_absolute(), rel
    assert RR._resolve_recorded(rel) == inside

    outside = tmp_path / "elsewhere.json"
    outside.write_text("{}")
    assert Path(RR._rel(outside)).is_absolute()
    assert RR._resolve_recorded(RR._rel(outside)) == outside.resolve()


def test_documented_score_invocation_requires_result_out():
    """The docstring's `score` example omitted the mandatory flag and produced an argparse error."""
    doc = RR.__doc__
    assert "--result-out" in doc
    assert "promote" in doc and "invalidate" in doc
    # the four numbered steps are all present
    for step in ("1. draw", "2. re-rate", "3. score", "4. if that reports"):
        assert step in doc, step


def test_promote_requires_a_score_kind_artifact(drawn, tmp_path, monkeypatch):
    """`result_kind` is a required discriminator from v3 on, and promote must act on it.

    A refusal or an invalidation is not a candidate verdict; only a `score` artifact is. The
    discriminator was introduced mid-v2, so a v2 file may or may not carry it — which is why v3
    exists and why branching on it is only safe once v3 is required.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)

    refusal = tmp_path / "refusal.json"
    RR.write_refusal(refusal, "nope")
    assert RR.promote(refusal) == 1

    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    payload = json.loads(good.read_text())
    payload["result_kind"] = "invalidation"          # right version, wrong kind
    wrong_kind = tmp_path / "wrong.json"
    wrong_kind.write_text(json.dumps(payload))
    assert RR.promote(wrong_kind) == 1
    assert not canonical.exists()


def test_invalidation_records_what_it_withdrew(drawn, tmp_path, monkeypatch):
    """Invalidation destroyed the only copy of the verdict it retracted.

    Unless a commit happened between promotion and invalidation — which nothing enforces — there was
    afterwards no durable trace of what had been withdrawn, or that anything had.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    assert RR.promote(good) == 0
    promoted = json.loads(canonical.read_text())
    promoted_sha = RR._sha256(canonical.read_bytes())

    assert RR.invalidate("superseded corpus", ["v5 lands tomorrow"], now="2026-07-28T12:00:00+02:00") == 0
    inv = json.loads(canonical.read_text())
    assert inv["result_kind"] == "invalidation"
    assert inv["invalidated_at"] == "2026-07-28T12:00:00+02:00"
    w = inv["invalidated"]
    assert w["sha256"] == promoted_sha
    assert w["result_kind"] == "score" and w["gate_valid"] is True
    assert w["categories_driving_build_order"] == promoted["categories_driving_build_order"]
    assert w["inputs"] == promoted["inputs"]


def test_manifest_rollups_are_null_while_the_gate_is_unapplied():
    """`[]` encodes "nothing qualified"; null encodes "the gate has not been applied".

    The scorer already makes this distinction by withholding its verdict on an invalid run; the
    manifest recorded `[]` and so asserted a result no run produced.
    """
    import yaml
    repo = Path(RR.__file__).resolve().parents[2]
    manifest, result = repo / "gate_manifest.yaml", repo / "logs" / "s1d_rerate_result.json"
    if not (manifest.exists() and result.exists()):
        # This is an integration check on REPOSITORY state, not on module logic, so it is meaningless
        # in the mutation harness's sandbox (which copies only agent/harness and tests). Skipping
        # keeps the sandbox suite runnable — a test that ERRORS there fails every mutant for an
        # unrelated reason and reports a perfect score.
        pytest.skip("repository files not present (mutation sandbox)")
    results = yaml.safe_load(manifest.read_text())["s1"]["results"]
    canonical = json.loads(result.read_text())
    if not canonical.get("gate_valid"):
        for field in ("failure_frequency_ranking", "build_order", "viability_verdict",
                      "total_failure_episodes"):
            assert results[field] is None, (
                f"{field} is {results[field]!r} while no valid gate result exists")


def test_repeated_invalidation_preserves_the_original_verdict(drawn, tmp_path, monkeypatch):
    """Summarising only the immediate predecessor loses the thing the record exists for.

    A second invalidation recorded the FIRST INVALIDATION and dropped the score it had withdrawn, so
    after two rounds the promoted verdict's SHA-256 was gone. Each invalidation now carries its
    predecessor's chain forward, oldest last.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    assert RR.promote(good) == 0
    score_sha = RR._sha256(canonical.read_bytes())
    verdict = json.loads(canonical.read_text())["categories_driving_build_order"]

    for i in (1, 2, 3):
        assert RR.invalidate(f"round {i}", now=f"2026-07-2{i}T00:00:00+02:00") == 0

    final = json.loads(canonical.read_text())
    chain = final["invalidation_chain"]
    assert len(chain) == 3
    original = [link for link in chain if link["sha256"] == score_sha]
    assert original, "the promoted score is no longer reachable after repeated invalidation"
    assert original[0]["result_kind"] == "score"
    assert original[0]["gate_valid"] is True
    assert original[0]["categories_driving_build_order"] == verdict
    assert chain[-1]["sha256"] == score_sha, "chain must be oldest-last"
def test_s1_status_is_stated_consistently():
    """S1 was simultaneously "complete, DEGRADED" and "reopened, gate not applied".

    One state everywhere: measurement complete, gate open pending the blind re-rate.
    """
    repo = Path(RR.__file__).resolve().parents[2]
    manifest = repo / "gate_manifest.yaml"
    archive_readme = repo / "docs" / "archive" / "README.md"
    if not (manifest.exists() and archive_readme.exists()):
        pytest.skip("repository docs not present (mutation sandbox)")
    header = "\n".join(manifest.read_text().splitlines()[:12])
    assert "S0 and S1 both complete" not in header
    assert "GATE OPEN" in header
    assert "**Both complete**" not in archive_readme.read_text()


def test_promotion_preserves_the_prior_canonical_lineage(drawn, tmp_path, monkeypatch):
    """The documented recovery path must not lose history.

    Consecutive invalidations chained correctly, but `promote` overwrote the canonical file without
    reading it — so score A → invalidate → promote B → invalidate ended with a chain containing only
    B, and A's SHA-256 was gone. Promotion now carries the existing lineage forward too.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)

    a = tmp_path / "a.json"
    assert RR.score(src, answer(), 0.40, man, a) == 0
    assert RR.promote(a) == 0
    sha_a = RR._sha256(canonical.read_bytes())
    assert RR.invalidate("withdraw A", now="2026-07-21T00:00:00+02:00") == 0

    b = tmp_path / "b.json"
    assert RR.score(src, answer(), 0.40, man, b) == 0
    assert RR.promote(b) == 0
    promoted_b = json.loads(canonical.read_text())
    assert promoted_b["superseded"]["result_kind"] == "invalidation"
    sha_b = RR._sha256(canonical.read_bytes())
    assert RR.invalidate("withdraw B", now="2026-07-22T00:00:00+02:00") == 0

    chain = json.loads(canonical.read_text())["invalidation_chain"]
    shas = [link["sha256"] for link in chain]
    assert sha_a in shas, "score A is unreachable after a later promotion"
    assert sha_b in shas
    assert shas[-1] == sha_a, "chain must be oldest-last"
    assert [l["result_kind"] for l in chain] == ["score", "invalidation", "score"]


def test_canonical_updates_are_transactional(drawn, tmp_path, monkeypatch):
    """The whole read-modify-replace must be serialised, not just the final write.

    Unique temp files made each write atomic, which prevents a torn file but not a LOST UPDATE:
    `promote` and `invalidate` both read the canonical result, build lineage from what they read, and
    only then replace it. Interleaved, an invalidation holding score A would overwrite a promotion of
    B while recording A as its predecessor — B gone, and the history actively wrong.

    Run in-process with real threads; `canonical_lock` uses flock, which excludes across file
    descriptors and so serialises threads and processes alike.
    """
    import threading
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)
    good = tmp_path / "good.json"
    assert RR.score(src, answer(), 0.40, man, good) == 0
    assert RR.promote(good) == 0

    errors: list[str] = []

    def invalidator(tag: str):
        for i in range(10):
            try:
                RR.invalidate(f"{tag}-{i}", now="2026-07-21T00:00:00+02:00")
            except Exception as exc:                       # noqa: BLE001 - the failure under test
                errors.append(repr(exc))

    threads = [threading.Thread(target=invalidator, args=(t,)) for t in ("a", "b", "c", "d")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors[:3]
    final = json.loads(canonical.read_text())              # never torn
    chain = final["invalidation_chain"]
    shas = [link["sha256"] for link in chain]
    assert len(chain) == 40, len(chain)                    # every update appended exactly one link
    assert all(shas[i] != shas[i + 1] for i in range(len(shas) - 1)), "a lost update duplicated a link"
    assert all(link.get("sha256") and link.get("result_kind") for link in chain)


def test_every_v3_artifact_carries_the_lineage_fields(drawn, tmp_path, monkeypatch):
    """One shape per schema version, or a consumer cannot read a field it is told exists.

    `superseded` and `invalidation_chain` were added during v3 and were briefly optional, which left
    a canonical file that was v3 without them — newly written artifacts had them, the one on disk did
    not, and tests that only checked fresh output passed.
    """
    src, answer, _, _, man = drawn
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(RR, "CANONICAL_RESULT", canonical)

    scored = tmp_path / "scored.json"
    assert RR.score(src, answer(), 0.40, man, scored) == 0
    refusal = tmp_path / "refusal.json"
    RR.write_refusal(refusal, "because")
    assert RR.promote(scored) == 0
    assert RR.invalidate("withdrawn", now="2026-07-21T00:00:00+02:00") == 0

    for path in (scored, refusal, canonical):
        got = json.loads(path.read_text())
        assert got["result_schema_version"] == RR.RESULT_SCHEMA_VERSION, path
        assert "superseded" in got or "invalidated" in got, f"{path} has no predecessor field"
        assert "invalidation_chain" in got, f"{path} has no invalidation_chain"
        assert isinstance(got["invalidation_chain"], list), path


def test_the_on_disk_canonical_conforms_to_the_v3_contract():
    """The repository's own canonical artifact must satisfy the contract, not just fresh output."""
    repo = Path(RR.__file__).resolve().parents[2]
    canonical = repo / "logs" / "s1d_rerate_result.json"
    if not canonical.exists():
        pytest.skip("repository files not present (mutation sandbox)")
    got = json.loads(canonical.read_text())
    assert got["result_schema_version"] == RR.RESULT_SCHEMA_VERSION
    assert "invalidation_chain" in got and isinstance(got["invalidation_chain"], list)
    assert "superseded" in got or "invalidated" in got
