"""Tests for the source-grounded GI-1 iteration predicate gold.

Most tests use a one-game temporary draw, label packet, and source file.  That keeps the
validator executable in the mutation sandbox, which intentionally has no ``logs/`` or
``data/environment_files/`` tree.  The checked-in artifact test is the only corpus test and
skips when those files are not staged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_predicate_gold as G  # noqa: E402


EXPECTED_HYPOTHESES = {
    "dc22": {
        "class": "state_relations",
        "predicate": {
            "subject": "player",
            "relation": "overlapping",
            "object": "goal tile",
        },
    },
    "ft09": {
        "class": "symmetry_and_template_match",
        "predicate": {
            "scope": "eight neighboring cells around every clue",
            "pattern": "clue 3x3 same-color and different-color template",
        },
    },
    "ls20": {
        "class": "state_relations",
        "predicate": {
            "subject": "avatar with each goal's required shape color and rotation",
            "relation": "overlapping",
            "object": "every goal tile",
        },
    },
    "m0r0": {
        "class": "all_instances_transformed",
        "predicate": {
            "subject": "all mirror-linked mover sprites",
            "transformation": "paired with another mover and merged at a shared cell",
        },
    },
    "tu93": {
        "class": "quantified_object_conditions",
        "predicate": {
            "subject": "nonempty set of surviving mover sprites",
            "quantifier": "all",
            "n": None,
            "condition": "overlapping an exit sprite",
        },
    },
    "vc33": {
        "class": "quantified_object_conditions",
        "predicate": {
            "subject": "falling item sprites",
            "quantifier": "all",
            "n": None,
            "condition": (
                "matched to a same-color receptacle at the item's lateral coordinate "
                "beside its supporting platform"
            ),
        },
    },
}

requires_corpus = pytest.mark.skipif(
    not (G.GOLD.exists() and G.DRAW.exists() and G.LABELS.exists()),
    reason="checked-in GI-1 gold inputs not staged (mutation sandbox / partial checkout)",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[dict, dict, dict]:
    source_rel = "data/environment_files/aa11/hash/aa11.py"
    source = tmp_path / source_rel
    source.parent.mkdir(parents=True)
    source.write_text("def step(self):\n    self.next_level()\n")

    draw = {
        "iteration": ["aa11"],
        "reserved": ["zz99"],
        "one_shot": ["yy88"],
        "primary_class": {
            "aa11": "counts",
            "zz99": "state_relations",
            "yy88": "event_occurrence",
        },
    }
    labels = {
        "records": [
            {
                "env": "aa11",
                "source": source_rel,
                "advance_line": 2,
                "enclosing_function": "step",
                "label": {
                    "primary": "counts",
                    "packet_digest": "0123456789abcdef",
                    "packet_verified": True,
                },
            }
        ]
    }
    gold = {
        "format_version": G.FORMAT_VERSION,
        "status": "frozen",
        "scope": "iteration",
        "draw_file": "logs/gi1_game_draw.json",
        "labels_file": "logs/s2_goal_predicates_labelled.json",
        "schema": {
            "module": "agent/harness/gi1_predicate_schema.py",
            "fingerprint": G.schema_fingerprint(),
        },
        "equivalence_cases": [],
        "records": [
            {
                "env": "aa11",
                "hypothesis": {
                    "class": "counts",
                    "predicate": {
                        "counted": "active blocks",
                        "comparator": "exactly",
                        "target_count": 2,
                    },
                },
                "summary": "Advance when exactly two active blocks remain.",
                "provenance": {
                    "source": source_rel,
                    "source_sha256": _sha(source),
                    "advance_line": 2,
                    "enclosing_function": "step",
                    "primary_label": "counts",
                    "packet_digest": "0123456789abcdef",
                    "packet_verified": True,
                },
            }
        ],
    }
    return gold, draw, labels


def _problems(tmp_path: Path, gold: dict, draw: dict, labels: dict) -> list[str]:
    return G.validate_gold(gold, draw, labels, root=tmp_path, verify_sources=True)


@requires_corpus
def test_checked_in_gold_reproduces_draw_labels_schema_and_sources():
    assert G.verify() == []


@requires_corpus
def test_checked_in_hypotheses_are_the_six_reviewable_normal_forms():
    artifact = json.loads(G.GOLD.read_text())
    actual = {record["env"]: record["hypothesis"] for record in artifact["records"]}
    assert actual == EXPECTED_HYPOTHESES


@requires_corpus
def test_checked_in_artifact_contains_iteration_games_only():
    artifact = json.loads(G.GOLD.read_text())
    draw = json.loads(G.DRAW.read_text())
    envs = [record["env"] for record in artifact["records"]]
    assert sorted(envs) == sorted(draw["iteration"])
    assert not (set(envs) & (set(draw["reserved"]) | set(draw["one_shot"])))


@requires_corpus
def test_publishable_gold_contains_no_verbatim_guard_expressions():
    artifact_text = G.GOLD.read_text()
    assert '"guard_tests"' not in artifact_text
    assert "self." not in artifact_text


def test_minimal_source_grounded_artifact_is_valid(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    assert _problems(tmp_path, gold, draw, labels) == []


@pytest.mark.parametrize("junk", [None, 7, "gold", []])
def test_non_object_gold_returns_problems_instead_of_raising(tmp_path, junk):
    _, draw, labels = _fixture(tmp_path)
    problems = G.validate_gold(junk, draw, labels, root=tmp_path)
    assert any("gold: expected an object" in p for p in problems)


@pytest.mark.parametrize("junk", [None, 7, "draw", []])
def test_non_object_draw_returns_problems_instead_of_raising(tmp_path, junk):
    gold, _, labels = _fixture(tmp_path)
    problems = G.validate_gold(gold, junk, labels, root=tmp_path)
    assert any("draw: expected an object" in p for p in problems)


@pytest.mark.parametrize(
    ("field", "junk", "fragment"),
    [
        ("iteration", "aa11", "iteration, reserved, and one_shot must be lists"),
        ("reserved", None, "iteration, reserved, and one_shot must be lists"),
        ("one_shot", {}, "iteration, reserved, and one_shot must be lists"),
        ("primary_class", [], "draw.primary_class"),
    ],
)
def test_malformed_draw_membership_returns_problems(tmp_path, field, junk, fragment):
    gold, draw, labels = _fixture(tmp_path)
    draw[field] = junk
    assert any(fragment in p for p in _problems(tmp_path, gold, draw, labels))


@pytest.mark.parametrize("junk", [None, 7, "labels", []])
def test_non_object_labels_returns_problems_instead_of_raising(tmp_path, junk):
    gold, draw, _ = _fixture(tmp_path)
    problems = G.validate_gold(gold, draw, junk, root=tmp_path)
    assert any("labels.records" in p for p in problems)


def test_non_list_label_records_are_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    labels["records"] = {}
    assert any("labels.records" in p for p in _problems(tmp_path, gold, draw, labels))


def test_malformed_label_record_is_ignored_without_raising(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    labels["records"].insert(0, None)
    assert _problems(tmp_path, gold, draw, labels) == []


@pytest.mark.parametrize("junk", [None, 7, [], {}])
def test_non_text_label_game_id_is_ignored_without_raising(tmp_path, junk):
    gold, draw, labels = _fixture(tmp_path)
    labels["records"].insert(0, {"env": junk})
    assert _problems(tmp_path, gold, draw, labels) == []


def test_non_list_gold_records_are_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"] = {}
    assert any("gold.records: expected a list" in p
               for p in _problems(tmp_path, gold, draw, labels))


def test_non_object_gold_record_is_rejected_without_raising(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"] = [None]
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("gold.records[0]: expected an object" in p for p in problems)


@pytest.mark.parametrize("junk", [None, 7, [], {}])
def test_non_text_game_id_is_rejected_without_raising(tmp_path, junk):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["env"] = junk
    assert any(".env: expected text" in p for p in _problems(tmp_path, gold, draw, labels))


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("format_version", 2, "format_version"),
        ("status", "draft-ish", "gold.status"),
        ("status", "dev_unfrozen", "expected frozen measurement status"),
        ("scope", "all_games", "gold.scope"),
        ("draw_file", "other.json", "gold.draw_file"),
        ("labels_file", "other.json", "gold.labels_file"),
    ],
)
def test_top_level_contract_drift_is_rejected(tmp_path, field, value, fragment):
    gold, draw, labels = _fixture(tmp_path)
    gold[field] = value
    assert any(fragment in problem for problem in _problems(tmp_path, gold, draw, labels))


def test_schema_fingerprint_drift_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["schema"]["fingerprint"] = "0" * 64
    assert any("schema drift" in problem for problem in _problems(tmp_path, gold, draw, labels))


def test_nonempty_equivalence_list_cannot_sneak_in_before_its_contract(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["equivalence_cases"] = [{"left": "player", "right": "avatar"}]
    assert any("must remain empty" in problem for problem in _problems(tmp_path, gold, draw, labels))


def test_missing_iteration_game_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"] = []
    assert any("missing iteration games ['aa11']" in p
               for p in _problems(tmp_path, gold, draw, labels))


def test_duplicate_iteration_game_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"].append(copy.deepcopy(gold["records"][0]))
    assert any("duplicate game aa11" in p for p in _problems(tmp_path, gold, draw, labels))


@pytest.mark.parametrize(("env", "bucket"), [("zz99", "reserved"), ("yy88", "one-shot")])
def test_reserved_and_one_shot_rows_are_rejected(tmp_path, env, bucket):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["env"] = env
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("forbidden reserved/one-shot" in p for p in problems), (bucket, problems)


def test_game_outside_the_frozen_draw_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["env"] = "xx77"
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("outside draw" in p for p in problems)
    assert any("no unique S2 source annotation for xx77" in p for p in problems)


def test_malformed_predicate_is_rejected_by_shared_schema(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["hypothesis"]["predicate"]["target_count"] = "two"
    assert any("not an integer" in p for p in _problems(tmp_path, gold, draw, labels))


def test_predicate_class_must_match_both_draw_and_source_label(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["hypothesis"] = {
        "class": "event_occurrence",
        "predicate": {"event": "two blocks remain"},
    }
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("!= draw primary" in p for p in problems)
    assert any("!= S2 primary" in p for p in problems)


def test_draw_must_supply_a_primary_class_for_every_gold_game(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    del draw["primary_class"]["aa11"]
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("draw.primary_class has no class for aa11" in p for p in problems)


def test_hypothesis_class_is_compared_directly_to_s2_primary(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    labels["records"][0]["label"]["primary"] = "event_occurrence"
    gold["records"][0]["provenance"]["primary_label"] = "event_occurrence"
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("hypothesis.class: 'counts' != S2 primary 'event_occurrence'" in p
               for p in problems)
    assert any("draw primary 'counts' != S2 primary 'event_occurrence'" in p
               for p in problems)


def test_duplicate_iteration_rows_in_s2_labels_are_rejected_not_last_wins(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    duplicate = copy.deepcopy(labels["records"][0])
    duplicate["label"]["primary"] = "event_occurrence"
    labels["records"].append(duplicate)
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("duplicate iteration game aa11" in p for p in problems)
    # The first row remains authoritative; a later duplicate cannot overwrite it.
    assert not any("!= S2 primary" in p for p in problems)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("advance_line", 1),
        ("enclosing_function", "other"),
        ("primary_label", "state_relations"),
        ("packet_digest", "ffffffffffffffff"),
        ("packet_verified", False),
    ],
)
def test_provenance_must_reproduce_s2_annotation(tmp_path, field, value):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["provenance"][field] = value
    assert any(f"provenance.{field}" in p for p in _problems(tmp_path, gold, draw, labels))


def test_source_digest_drift_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["provenance"]["source_sha256"] = "0" * 64
    assert any("source drift" in p for p in _problems(tmp_path, gold, draw, labels))


def test_non_utf8_source_returns_a_problem_instead_of_raising(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    source = tmp_path / gold["records"][0]["provenance"]["source"]
    source.write_bytes(b"\xff\xfe\x00")
    gold["records"][0]["provenance"]["source_sha256"] = _sha(source)
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("cannot read as UTF-8 Python" in p for p in problems)


def test_missing_source_file_is_rejected_before_hashing(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    missing = "data/environment_files/aa11/hash/missing.py"
    gold["records"][0]["provenance"]["source"] = missing
    labels["records"][0]["source"] = missing
    assert any("file not found" in p for p in _problems(tmp_path, gold, draw, labels))


@pytest.mark.parametrize("junk", [None, 7, [], {}])
def test_non_text_source_path_is_rejected_without_raising(tmp_path, junk):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["provenance"]["source"] = junk
    labels["records"][0]["source"] = junk
    assert any("expected a relative path" in p for p in _problems(tmp_path, gold, draw, labels))


def test_malformed_s2_label_is_rejected_without_reading_its_fields(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    labels["records"][0]["label"] = []
    assert any("malformed S2 label" in p for p in _problems(tmp_path, gold, draw, labels))


def test_advance_line_must_point_at_the_sole_level_transition(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["provenance"]["advance_line"] = 1
    labels["records"][0]["advance_line"] = 1
    assert any("expected the sole self.next_level()" in p
               for p in _problems(tmp_path, gold, draw, labels))


def test_source_with_two_level_transition_sites_is_rejected(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    source = tmp_path / gold["records"][0]["provenance"]["source"]
    source.write_text(
        "def step(self):\n"
        "    self.next_level()\n"
        "    self.next_level()\n"
    )
    gold["records"][0]["provenance"]["source_sha256"] = _sha(source)
    problems = _problems(tmp_path, gold, draw, labels)
    assert any("expected the sole self.next_level() site, found lines [2, 3]" in p
               for p in problems)


def test_textual_next_level_in_comment_does_not_count_as_a_transition(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    source = tmp_path / gold["records"][0]["provenance"]["source"]
    source.write_text(
        "def step(self):\n"
        "    self.next_level()\n"
        "    # self.next_level()\n"
    )
    gold["records"][0]["provenance"]["source_sha256"] = _sha(source)
    assert _problems(tmp_path, gold, draw, labels) == []


def test_first_source_line_can_be_the_valid_transition(tmp_path):
    gold, draw, labels = _fixture(tmp_path)
    source = tmp_path / gold["records"][0]["provenance"]["source"]
    source.write_text("self.next_level()\n")
    gold["records"][0]["provenance"]["source_sha256"] = _sha(source)
    gold["records"][0]["provenance"]["advance_line"] = 1
    labels["records"][0]["advance_line"] = 1
    assert _problems(tmp_path, gold, draw, labels) == []


def test_verify_reports_missing_inputs_instead_of_raising(tmp_path):
    problems = G.verify(
        tmp_path / "missing-gold.json",
        tmp_path / "missing-draw.json",
        tmp_path / "missing-labels.json",
        root=tmp_path,
    )
    assert len(problems) == 3
    assert all("required input not found" in p for p in problems)


def test_verify_reports_invalid_json_instead_of_raising(tmp_path):
    gold_path = tmp_path / "gold.json"
    draw_path = tmp_path / "draw.json"
    labels_path = tmp_path / "labels.json"
    gold_path.write_text("{")
    draw_path.write_text("{}")
    labels_path.write_text('{"records": []}')
    problems = G.verify(gold_path, draw_path, labels_path, root=tmp_path)
    assert len(problems) == 1
    assert problems[0].startswith("gold: cannot read")


@pytest.mark.parametrize(
    "unsafe",
    [
        "/tmp/aa11.py",
        "../../data/environment_files/aa11/hash/aa11.py",
        "data/environment_files/zz99/hash/zz99.py",
    ],
)
def test_source_path_cannot_escape_its_iteration_game(tmp_path, unsafe):
    gold, draw, labels = _fixture(tmp_path)
    gold["records"][0]["provenance"]["source"] = unsafe
    labels["records"][0]["source"] = unsafe
    assert any("is outside data/environment_files/aa11/" in p
               for p in _problems(tmp_path, gold, draw, labels))


@pytest.mark.parametrize(("container", "extra"), [("gold", "mystery"), ("record", "guess")])
def test_unknown_artifact_fields_are_rejected(tmp_path, container, extra):
    gold, draw, labels = _fixture(tmp_path)
    target = gold if container == "gold" else gold["records"][0]
    target[extra] = True
    assert any("unknown keys" in p for p in _problems(tmp_path, gold, draw, labels))
