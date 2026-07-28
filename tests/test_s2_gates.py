"""Regression tests for the S2 goal-predicate re-rate and label application.

The S1 suite's two taxonomy tests cover document/code governance only — nothing exercised the S2
modules themselves, so the mutation harness had no target there either. These are the direct tests.

The defect that motivated the file: `score` verified the WORKSHEET against the corpus and never
verified that the submitted RATINGS came from that worksheet. Item ids are positional (`g00`..`g24`)
and therefore identical across every draw, so a ratings file fits any worksheet of the same size.
Ratings produced against the superseded extraction scored cleanly against the corrected one and
reported kappa 0.659 while 17 of the 25 evidence packets had changed underneath.

Run:
  .venv/bin/python -m pytest tests/test_s2_gates.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import s2_apply_labels as AL     # noqa: E402
import s2_blind_rerate as RR     # noqa: E402


# --------------------------------------------------------------------------- fixtures

CLASSES = ["state_relations", "counts", "region_membership", "event_occurrence"]


def _record(env: str, *, advance: str = "advance()", cls: str | None = None) -> dict:
    """One corpus record, carrying every field the worksheet shows."""
    r = {
        "env": env,
        "advance_line": advance,
        "enclosing_function": f"def step_{env}():",
        "evidence": [f"line about {env}"],
        "features": {"has_counter": False},
        "flag_sites": [],
        "guard_tests": [f"if {env}_done:"],
        "preconditions_from_early_returns": [],
        "resolved_methods": {},
    }
    if cls:
        r["label"] = {"predicate_classes": [cls], "primary": cls, "guard_form": "inline",
                      "notes": "", "rater": "claude-opus-5", "label_file": "fixture.json"}
    return r


def _corpus(n: int = 6, labelled: bool = True) -> dict:
    return {"records": [_record(f"env{i:02d}", cls=CLASSES[i % len(CLASSES)] if labelled else None)
                        for i in range(n)]}


@pytest.fixture
def drawn(tmp_path):
    """A drawn worksheet plus a helper that fills its template faithfully from the first pass."""
    corpus = _corpus()
    src = tmp_path / "corpus.json"
    src.write_text(json.dumps(corpus))
    ws = tmp_path / "ws.json"
    assert RR.draw(src, ws) == 0
    template = json.loads((tmp_path / "ws.ratings-template.json").read_text())
    key = json.loads((tmp_path / "ws.key.json").read_text())["key"]
    first = {r["env"]: r for r in corpus["records"]}

    def answer(mutate=None):
        t = copy.deepcopy(template)
        for iid, slot in t["ratings"].items():
            lab = first[key[iid]]["label"]
            slot["predicate_classes"] = list(lab["predicate_classes"])
            slot["guard_form"] = lab["guard_form"]
        t["raters"], t["dated"] = "claude-opus-5", "2026-07-28"
        if mutate:
            mutate(t)
        p = tmp_path / "pass2.json"
        p.write_text(json.dumps(t))
        return p

    return src, ws, answer, tmp_path


# --------------------------------------------------------------------------- worksheet binding

def test_a_faithful_second_pass_scores(drawn):
    src, ws, answer, tmp_path = drawn
    assert RR.score(src, ws, answer(), tmp_path / "out.json") == 0
    got = json.loads((tmp_path / "out.json").read_text())
    assert got["primary_kappa"] == 1.0
    assert got["primary_observed_agreement"] == 1.0


def test_ratings_without_a_worksheet_id_are_refused(drawn, capsys):
    """A pass that cannot say which worksheet produced it cannot be scored against one."""
    src, ws, answer, tmp_path = drawn

    def strip(t):
        t.pop("worksheet_id")
    capsys.readouterr()
    assert RR.score(src, ws, answer(strip), tmp_path / "out.json") == 1
    assert "records no `worksheet_id`" in capsys.readouterr().out


def test_ratings_from_a_different_worksheet_are_refused(drawn, capsys):
    """THE defect. Item ids are positional, so the ids line up and kappa computes regardless.

    Reproduced against the real artifacts before the fix: the superseded round's ratings scored
    against the corrected worksheet at kappa 0.659 with 17 of 25 packets changed.
    """
    src, ws, answer, tmp_path = drawn

    # A genuinely different worksheet: same size, same ids, different packets.
    other_corpus = _corpus()
    for r in other_corpus["records"]:
        r["advance_line"] = "advance()  # re-extracted"
    other_src = tmp_path / "other.json"
    other_src.write_text(json.dumps(other_corpus))
    other_ws = tmp_path / "other_ws.json"
    assert RR.draw(other_src, other_ws) == 0
    other_id = json.loads(other_ws.read_text())["worksheet_id"]
    assert other_id != json.loads(ws.read_text())["worksheet_id"]

    def retag(t):
        t["worksheet_id"] = other_id
    capsys.readouterr()
    assert RR.score(src, ws, answer(retag), tmp_path / "out.json") == 1
    out = capsys.readouterr().out
    assert "They rate different material" in out, out


def test_a_spliced_pass_is_refused_per_item(drawn, capsys):
    """Right worksheet_id, one item rated against some other packet.

    The per-item digest catches a pass assembled from two worksheets, which the whole-worksheet id
    alone would wave through.
    """
    src, ws, answer, tmp_path = drawn

    def splice(t):
        first_id = sorted(t["ratings"])[0]
        t["ratings"][first_id]["item_digest"] = "deadbeefdeadbeef"
    capsys.readouterr()
    assert RR.score(src, ws, answer(splice), tmp_path / "out.json") == 1
    assert "rated against packet deadbeefdeadbeef" in capsys.readouterr().out


def test_the_key_must_belong_to_the_worksheet(drawn, capsys):
    """A key from another draw silently re-pairs every rating with a different first-pass label."""
    src, ws, answer, tmp_path = drawn
    key_path = tmp_path / "ws.key.json"
    k = json.loads(key_path.read_text())
    k["worksheet_id"] = "0000000000000000"
    key_path.write_text(json.dumps(k))
    capsys.readouterr()
    assert RR.score(src, ws, answer(), tmp_path / "out.json") == 1
    assert "id->env key belongs to worksheet" in capsys.readouterr().out


def test_draw_emits_the_template_and_the_key_separately(tmp_path):
    """The template is what the rater fills; the key must never reach them.

    Binding costs the rater nothing precisely because the digests are pre-filled — asking anyone to
    copy 25 of them by hand would be its own failure mode.
    """
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus()))
    ws = tmp_path / "ws.json"
    assert RR.draw(src, ws) == 0
    template = json.loads((tmp_path / "ws.ratings-template.json").read_text())
    sheet = json.loads(ws.read_text())

    assert template["worksheet_id"] == sheet["worksheet_id"]
    assert set(template["ratings"]) == {i["item_id"] for i in sheet["items"]}
    for iid, slot in template["ratings"].items():
        assert slot["predicate_classes"] == [] and slot["guard_form"] is None
        assert slot["item_digest"] == next(i["digest"] for i in sheet["items"] if i["item_id"] == iid)
    # The worksheet the rater sees carries no environment identity. Checked STRUCTURALLY: a
    # substring scan gives false positives the moment a fixture names anything `step_env00`.
    assert all("_env" not in i and "env" not in i for i in sheet["items"])
    envs = {r["env"] for r in json.loads(src.read_text())["records"]}
    key = json.loads((tmp_path / "ws.key.json").read_text())["key"]
    assert set(key.values()) == envs, "the key must map every item to its environment"
    assert not (envs & set(json.dumps(sheet).split('"'))), "no env id appears as a value in the sheet"


def test_worksheet_id_changes_with_the_packets_not_the_order(tmp_path):
    """It must be an identity of the MATERIAL shown, or it cannot detect a re-extraction."""
    a = _corpus()
    b = copy.deepcopy(a)
    b["records"][0]["advance_line"] = "advance()  # changed"
    ids = []
    for i, c in enumerate((a, b, copy.deepcopy(a))):
        src = tmp_path / f"c{i}.json"
        src.write_text(json.dumps(c))
        ws = tmp_path / f"ws{i}.json"
        assert RR.draw(src, ws) == 0
        ids.append(json.loads(ws.read_text())["worksheet_id"])
    assert ids[0] != ids[1], "a changed packet must change the worksheet identity"
    assert ids[0] == ids[2], "the same corpus must reproduce the same identity"


# --------------------------------------------------------------------------- label application

def test_labels_outside_the_codebook_are_refused(tmp_path):
    """The codebook is closed; `outside_taxonomy` is the only escape and is counted separately."""
    corpus = _corpus(labelled=False)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    labels = {"rater": "claude-opus-5",
              "labels": {"env00": {"predicate_classes": ["NOT_A_CLASS"]}}}
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps(labels))
    assert AL.apply(src, [lf], tmp_path / "out.json") == 1
    assert not (tmp_path / "out.json").exists(), "a refused apply must write nothing"


def test_an_empty_class_list_is_an_omission_not_a_label(tmp_path):
    """Counting it as labelled would silently deflate every share."""
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(labelled=False)))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {"env00": {"predicate_classes": []}}}))
    assert AL.apply(src, [lf], tmp_path / "out.json") == 1


def test_a_label_against_a_stale_packet_is_refused(tmp_path):
    """A label is a judgment about a specific packet, so it is only valid against that packet.

    Re-extracting the corpus and re-applying old labels produces an artifact that looks labelled and
    is not: the rater never saw this evidence.
    """
    corpus = _corpus(labelled=False)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {
        "env00": {"predicate_classes": ["counts"], "packet_digest": "deadbeefdeadbeef"}}}))
    assert AL.apply(src, [lf], tmp_path / "out.json") == 1


def test_an_unknown_env_is_refused_rather_than_dropped(tmp_path):
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(labelled=False)))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {
        "env_that_does_not_exist": {"predicate_classes": ["counts"]}}}))
    assert AL.apply(src, [lf], tmp_path / "out.json") == 1


def test_unused_classes_are_reported_not_hidden(tmp_path, capsys):
    """A pre-specified class the corpus never exercises is a result, not an absence to tidy away."""
    corpus = _corpus(labelled=False)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {
        r["env"]: {"predicate_classes": ["counts"], "guard_form": "inline"}
        for r in corpus["records"]}}))
    capsys.readouterr()
    assert AL.apply(src, [lf], tmp_path / "out.json") == 0
    out = capsys.readouterr().out
    got = json.loads((tmp_path / "out.json").read_text())
    assert "counts" not in got["frequencies"]["unused_classes"]
    assert len(got["frequencies"]["unused_classes"]) == len(AL.TAXONOMY) - 1
    assert "ZERO occurrences" in out


# --------------------------------------------------- statistics, and the checks around them

def test_a_disagreeing_pass_reports_each_statistic_separately(drawn, tmp_path):
    """The four agreement numbers answer different questions and must not collapse into one.

    Constructed so they cannot coincide: one item's primary is changed (moving kappa and exact-set
    agreement), another keeps its primary but gains a class (moving exact-set and Jaccard only), and
    a third changes only its guard_form (moving guard-form agreement alone).
    """
    src, ws, answer, tmp_path = drawn

    def disagree(t):
        ids = sorted(t["ratings"])
        t["ratings"][ids[0]]["predicate_classes"] = ["cumulative_counters"]      # primary flips
        t["ratings"][ids[1]]["predicate_classes"] += ["counts"]                  # set grows only
        t["ratings"][ids[2]]["guard_form"] = "delegated"                         # guard form only
    assert RR.score(src, ws, answer(disagree), tmp_path / "out.json") == 0
    got = json.loads((tmp_path / "out.json").read_text())

    assert got["n"] == 6
    assert got["primary_observed_agreement"] == round(5 / 6, 3)     # one primary changed
    assert got["full_set_exact_agreement"] == round(4 / 6, 3)       # that one plus the grown set
    assert got["mean_jaccard_over_class_sets"] < 1.0
    assert got["guard_form_agreement"] == round(5 / 6, 3)           # one guard form changed
    assert len(got["disagreements"]) == 1
    assert got["primary_kappa"] < 1.0


def test_guard_form_agreement_is_none_when_none_were_recorded(drawn, tmp_path):
    """`None` and `0.0` mean different things: nothing to compare vs compared and disagreed."""
    src, ws, answer, tmp_path = drawn

    def drop_forms(t):
        for slot in t["ratings"].values():
            slot["guard_form"] = None
    assert RR.score(src, ws, answer(drop_forms), tmp_path / "out.json") == 0
    assert json.loads((tmp_path / "out.json").read_text())["guard_form_agreement"] is None


def test_a_class_used_by_only_one_pass_is_reported(drawn, tmp_path):
    """A category one rater never uses moves kappa without any item being read differently."""
    src, ws, answer, tmp_path = drawn

    def swap_all(t):
        for slot in t["ratings"].values():
            slot["predicate_classes"] = ["cumulative_counters"]
    assert RR.score(src, ws, answer(swap_all), tmp_path / "out.json") == 0
    got = json.loads((tmp_path / "out.json").read_text())
    assert got["primary_classes_used_by_rerate_only"] == ["cumulative_counters"]
    assert set(got["primary_classes_used_by_first_pass_only"]) == set(CLASSES[:4]) - {"cumulative_counters"}


def test_a_tampered_worksheet_is_refused(drawn, capsys):
    """The per-item digest catches a worksheet edited after it was drawn."""
    src, ws, answer, tmp_path = drawn
    sheet = json.loads(ws.read_text())
    sheet["items"][0]["advance_line"] = "advance()  # edited after drawing"
    ws.write_text(json.dumps(sheet))
    capsys.readouterr()
    assert RR.score(src, ws, answer(), tmp_path / "out.json") == 1
    assert "digest mismatch" in capsys.readouterr().out


def test_a_rating_for_an_unknown_item_is_refused(drawn, capsys):
    """An id the worksheet never issued cannot be scored against anything."""
    src, ws, answer, tmp_path = drawn

    def add_ghost(t):
        t["ratings"]["g99"] = {"predicate_classes": ["counts"], "guard_form": "inline"}
    capsys.readouterr()
    assert RR.score(src, ws, answer(add_ghost), tmp_path / "out.json") == 1
    assert "not in the worksheet" in capsys.readouterr().out


def test_outside_taxonomy_is_accepted_as_the_escape(drawn, tmp_path):
    """The escape hatch must work, or raters are pushed into forcing a bad fit."""
    src, ws, answer, tmp_path = drawn

    def escape(t):
        t["ratings"][sorted(t["ratings"])[0]]["predicate_classes"] = [RR.ESCAPE]
    assert RR.score(src, ws, answer(escape), tmp_path / "out.json") == 0
    got = json.loads((tmp_path / "out.json").read_text())
    assert RR.ESCAPE in got["primary_classes_used_by_rerate_only"]


# --------------------------------------------------------------------------- label application

def test_an_unknown_guard_form_is_refused(tmp_path):
    """`guard_form` is a closed set too — it records how hard the condition is to OBSERVE."""
    src = tmp_path / "c.json"
    src.write_text(json.dumps(_corpus(labelled=False)))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {
        "env00": {"predicate_classes": ["counts"], "guard_form": "not_a_guard_form"}}}))
    assert AL.apply(src, [lf], tmp_path / "out.json") == 1


def test_labels_without_a_packet_digest_are_applied_but_flagged(tmp_path, capsys):
    """They predate the check, so they are not rejected — but they cannot be called verified."""
    corpus = _corpus(labelled=False)
    src = tmp_path / "c.json"
    src.write_text(json.dumps(corpus))
    lf = tmp_path / "labels.json"
    lf.write_text(json.dumps({"rater": "r", "labels": {
        r["env"]: {"predicate_classes": ["counts"], "guard_form": "inline"}
        for r in corpus["records"]}}))
    capsys.readouterr()
    assert AL.apply(src, [lf], tmp_path / "out.json") == 0
    out = capsys.readouterr().out
    got = json.loads((tmp_path / "out.json").read_text())
    assert got["labels_packet_verified"] is False
    assert len(got["labels_unverified_envs"]) == len(corpus["records"])
    assert all(not r["label"]["packet_verified"] for r in got["records"])
    assert "CANNOT be verified" in out
