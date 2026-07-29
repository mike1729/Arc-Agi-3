"""Tests for the mechanical GI-1 K4 predicate scorer."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_k4_scorer as K  # noqa: E402
import gi1_output_parser as P  # noqa: E402
from gi1_predicate_gold import schema_fingerprint  # noqa: E402


def _hypothesis(rank: int, cls: str, predicate: dict) -> dict:
    return {
        "rank": rank,
        "class": cls,
        "predicate": copy.deepcopy(predicate),
        "evidence_for": "observed support",
        "evidence_against": "remaining uncertainty",
    }


def _raw(candidates: list[tuple[str, dict]]) -> str:
    hypotheses = [
        _hypothesis(rank, cls, predicate)
        for rank, (cls, predicate) in enumerate(candidates, 1)
    ]
    return json.dumps(
        {
            "hypotheses": hypotheses,
            "discriminating_probe": "take one cheap action and inspect the delta",
        }
    )


COUNTS = {
    "class": "counts",
    "predicate": {
        "counted": "blue blocks",
        "comparator": "exactly",
        "target_count": 2,
    },
}
EVENT = {"class": "event_occurrence", "predicate": {"event": "door opens"}}


def _three(first: tuple[str, dict], second=None, third=None):
    second = second or ("event_occurrence", {"event": "door opens"})
    third = third or (
        "region_membership",
        {"subject": "player", "region": "goal", "membership": "inside"},
    )
    return _raw([first, second, third])


def test_exact_top_one_predicate_scores_correct():
    score = K.score_raw_output(_three(("counts", COUNTS["predicate"])), COUNTS)
    assert score.parse_valid
    assert score.top1_class_correct
    assert score.top3_class_correct
    assert score.top1_predicate_correct
    assert score.top3_predicate_correct
    assert score.top1_fields_correct == 3
    assert score.top1_fields_total == 3
    assert score.top1_field_accuracy == 1.0
    assert score.best_top3_fields_correct == 3
    assert score.best_top3_field_accuracy == 1.0
    assert score.hypotheses[0].fields_correct == 3
    assert score.hypotheses[0].fields_total == 3


def test_correct_predicate_at_rank_two_is_top3_not_top1():
    raw = _raw(
        [
            ("event_occurrence", {"event": "door opens"}),
            ("counts", COUNTS["predicate"]),
            (
                "region_membership",
                {"subject": "player", "region": "goal", "membership": "inside"},
            ),
        ]
    )
    score = K.score_raw_output(raw, COUNTS)
    assert not score.top1_class_correct
    assert score.top3_class_correct
    assert not score.top1_predicate_correct
    assert score.top3_predicate_correct
    assert score.top1_field_accuracy == 0.0
    assert score.best_top3_field_accuracy == 1.0


def test_invalid_json_is_an_all_false_observed_outcome_not_an_excluded_row():
    score = K.score_raw_output("```json\n{}\n```", COUNTS)
    assert not score.parse_valid
    assert score.parse_problems
    assert not score.top1_class_correct
    assert not score.top3_class_correct
    assert not score.top1_predicate_correct
    assert not score.top3_predicate_correct
    assert score.top1_fields_correct == 0
    assert score.top1_fields_total == 3
    assert score.top1_field_accuracy == 0.0
    assert score.best_top3_fields_total == 3
    assert score.best_top3_field_accuracy == 0.0
    assert score.hypotheses == ()


def test_wrong_class_scores_every_gold_field_false():
    scored = K.score_hypothesis(EVENT, COUNTS, rank=1)
    assert not scored.class_correct
    assert not scored.predicate_correct
    assert scored.fields_total == 3
    assert scored.fields_correct == 0
    assert [field.name for field in scored.fields] == [
        "counted",
        "comparator",
        "target_count",
    ]
    assert all(field.candidate is None and not field.correct for field in scored.fields)


def test_realistic_paraphrase_has_a_first_class_top_level_graded_signal():
    gold = {
        "class": "state_relations",
        "predicate": {
            "subject": "player",
            "relation": "overlapping",
            "object": "goal tile",
        },
    }
    paraphrase = {
        "subject": "the player",
        "relation": "overlapping",
        "object": "the target",
    }
    score = K.score_raw_output(
        _three(("state_relations", paraphrase)),
        gold,
    )
    assert score.top1_class_correct
    assert not score.top1_predicate_correct
    assert score.top1_fields_correct == 1
    assert score.top1_fields_total == 3
    assert score.top1_field_accuracy == pytest.approx(1 / 3)


def test_enum_comparison_is_case_and_outer_whitespace_insensitive():
    candidate = copy.deepcopy(COUNTS)
    candidate["predicate"]["comparator"] = " EXACTLY "
    scored = K.score_hypothesis(candidate, COUNTS, rank=1)
    assert scored.predicate_correct


def test_entity_comparison_uses_shared_punctuation_and_case_normalization():
    candidate = copy.deepcopy(COUNTS)
    candidate["predicate"]["counted"] = "Blue, BLOCKS!"
    assert K.score_hypothesis(candidate, COUNTS, rank=1).predicate_correct


def test_arc_symbol_and_its_colour_name_compare_equal():
    gold = copy.deepcopy(COUNTS)
    gold["predicate"]["counted"] = "B blocks"
    candidate = copy.deepcopy(COUNTS)
    candidate["predicate"]["counted"] = "black blocks"
    assert K.score_hypothesis(candidate, gold, rank=1).predicate_correct


def test_entity_token_order_is_not_erased():
    gold = {"class": "event_occurrence", "predicate": {"event": "player reaches target"}}
    candidate = {
        "class": "event_occurrence",
        "predicate": {"event": "target reaches player"},
    }
    scored = K.score_hypothesis(candidate, gold, rank=1)
    assert not scored.predicate_correct
    assert not scored.fields[0].correct


def test_integer_comparison_is_exact():
    candidate = copy.deepcopy(COUNTS)
    candidate["predicate"]["target_count"] = 3
    scored = K.score_hypothesis(candidate, COUNTS, rank=1)
    assert not scored.predicate_correct
    assert scored.fields_correct == 2
    assert not next(field for field in scored.fields if field.name == "target_count").correct


def test_entity_list_comparison_preserves_order():
    gold = {
        "class": "ordered_event_programs",
        "predicate": {"events_in_order": ["red switch", "blue switch"]},
    }
    candidate = {
        "class": "ordered_event_programs",
        "predicate": {"events_in_order": ["blue switch", "red switch"]},
    }
    assert not K.score_hypothesis(candidate, gold, rank=1).predicate_correct


def test_entity_list_comparison_requires_equal_length():
    gold = {
        "class": "ordered_event_programs",
        "predicate": {"events_in_order": ["red switch", "blue switch"]},
    }
    candidate = {
        "class": "ordered_event_programs",
        "predicate": {"events_in_order": ["red switch"]},
    }
    assert not K.score_hypothesis(candidate, gold, rank=1).predicate_correct


def test_inactive_conditional_n_is_not_scored():
    gold = {
        "class": "quantified_object_conditions",
        "predicate": {
            "subject": "movers",
            "quantifier": "all",
            "n": None,
            "condition": "on exits",
        },
    }
    candidate = {
        "class": "quantified_object_conditions",
        "predicate": {
            "subject": "movers",
            "quantifier": "all",
            "condition": "on exits",
        },
    }
    scored = K.score_hypothesis(candidate, gold, rank=1)
    assert scored.predicate_correct
    assert [field.name for field in scored.fields] == [
        "subject",
        "quantifier",
        "condition",
    ]


def test_active_conditional_n_is_scored():
    gold = {
        "class": "quantified_object_conditions",
        "predicate": {
            "subject": "movers",
            "quantifier": "exactly_n",
            "n": 2,
            "condition": "on exits",
        },
    }
    candidate = copy.deepcopy(gold)
    candidate["predicate"]["n"] = 3
    scored = K.score_hypothesis(candidate, gold, rank=1)
    assert not scored.predicate_correct
    assert scored.fields_total == 4
    assert next(field for field in scored.fields if field.name == "n").correct is False


@pytest.mark.parametrize("which", ["candidate", "gold"])
def test_direct_hypothesis_scoring_refuses_schema_invalid_inputs(which):
    candidate, gold = copy.deepcopy(COUNTS), copy.deepcopy(COUNTS)
    target = candidate if which == "candidate" else gold
    target["predicate"]["target_count"] = True
    with pytest.raises(ValueError, match=f"{which} is not schema-valid"):
        K.score_hypothesis(candidate, gold, rank=1)


def test_invalid_parse_does_not_mask_schema_invalid_gold_configuration():
    parsed = P.parse_model_output("not JSON")
    invalid_gold = copy.deepcopy(COUNTS)
    invalid_gold["predicate"]["target_count"] = True
    with pytest.raises(ValueError, match="gold is not schema-valid"):
        K.score_parsed_output(parsed, invalid_gold)


def test_hand_built_ok_parse_result_is_revalidated_before_indexing():
    fabricated = P.ParseResult(
        value={"hypotheses": [], "discriminating_probe": "probe"},
        problems=(),
    )
    with pytest.raises(ValueError, match="inconsistent ParseResult"):
        K.score_parsed_output(fabricated, COUNTS)


def test_scorer_covers_every_field_kind_in_the_shared_schema():
    assert K.SCHEMA_FIELD_KINDS == K.SUPPORTED_FIELD_KINDS


def test_score_serializes_to_plain_measurement_data():
    score = K.score_raw_output(_three(("counts", COUNTS["predicate"])), COUNTS)
    encoded = json.dumps(score.as_dict(), sort_keys=True)
    assert '"top1_predicate_correct": true' in encoded
    assert '"fields_total": 3' in encoded


def _gold_artifact(records=None) -> dict:
    return {
        "format_version": 1,
        "status": "dev_unfrozen",
        "scope": "iteration",
        "draw_file": "logs/gi1_game_draw.json",
        "labels_file": "logs/s2_goal_predicates_labelled.json",
        "schema": {
            "module": "agent/harness/gi1_predicate_schema.py",
            "fingerprint": schema_fingerprint(),
        },
        "equivalence_cases": [],
        "records": records
        if records is not None
        else [
            {
                "env": "aa11",
                "hypothesis": copy.deepcopy(COUNTS),
                "summary": "synthetic test gold",
                "provenance": {},
            }
        ],
    }


def _write_gold(tmp_path: Path, artifact: dict) -> Path:
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(artifact))
    return path


def _write_draw(tmp_path: Path, iteration=None) -> Path:
    path = tmp_path / "draw.json"
    path.write_text(json.dumps({"iteration": ["aa11"] if iteration is None else iteration}))
    return path


def _load_synthetic(tmp_path: Path, artifact: dict, iteration=None):
    return K.load_gold_index(
        _write_gold(tmp_path, artifact),
        draw_path=_write_draw(tmp_path, iteration),
    )


def test_gold_index_loads_publishable_hypotheses_without_source_bundle(tmp_path):
    assert _load_synthetic(tmp_path, _gold_artifact()) == {"aa11": COUNTS}


def test_gold_index_rejects_non_object_artifact(tmp_path):
    with pytest.raises(ValueError, match="predicate gold must be an object"):
        _load_synthetic(tmp_path, [])


def test_checked_in_iteration_gold_loads_when_staged():
    if not K.GOLD.exists():
        pytest.skip("publishable gold not staged in mutation sandbox")
    index = K.load_gold_index()
    assert set(index) == {"dc22", "ft09", "ls20", "m0r0", "tu93", "vc33"}


def test_every_staged_iteration_gold_predicate_can_score_exactly():
    if not K.GOLD.exists():
        pytest.skip("publishable gold not staged in mutation sandbox")
    for env, gold in K.load_gold_index().items():
        raw = _raw(
            [
                (gold["class"], gold["predicate"]),
                (gold["class"], gold["predicate"]),
                (gold["class"], gold["predicate"]),
            ]
        )
        score = K.score_raw_output(raw, gold)
        assert score.parse_valid, (env, score.parse_problems)
        assert score.top1_predicate_correct, env
        assert score.hypotheses[0].fields_correct == score.hypotheses[0].fields_total


def test_gold_index_rejects_schema_drift(tmp_path):
    artifact = _gold_artifact()
    artifact["schema"]["fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        _load_synthetic(tmp_path, artifact)


@pytest.mark.parametrize(
    ("field", "value", "fragment"),
    [
        ("format_version", 2, "format version"),
        ("status", "frozen", "status"),
        ("scope", "one_shot", "scope"),
    ],
)
def test_gold_index_rejects_artifact_contract_drift(tmp_path, field, value, fragment):
    artifact = _gold_artifact()
    artifact[field] = value
    with pytest.raises(ValueError, match=fragment):
        _load_synthetic(tmp_path, artifact)


def test_scorer_and_validator_share_the_current_status_and_scope_contract(tmp_path):
    artifact = _gold_artifact()
    artifact["scope"] = "one_shot"
    artifact["status"] = "frozen"
    with pytest.raises(ValueError, match="status"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_unknown_top_level_fields(tmp_path):
    artifact = _gold_artifact()
    artifact["new_contract"] = True
    with pytest.raises(ValueError, match="top-level keys"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_refuses_unimplemented_equivalences(tmp_path):
    artifact = _gold_artifact()
    artifact["equivalence_cases"] = [{"left": "player", "right": "avatar"}]
    with pytest.raises(ValueError, match="equivalence_cases"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_duplicate_games(tmp_path):
    record = {
        "env": "aa11",
        "hypothesis": copy.deepcopy(COUNTS),
        "summary": "synthetic test gold",
        "provenance": {},
    }
    artifact = _gold_artifact([record, copy.deepcopy(record)])
    with pytest.raises(ValueError, match="duplicate predicate gold game"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_invalid_hypothesis(tmp_path):
    invalid = copy.deepcopy(COUNTS)
    invalid["predicate"]["target_count"] = "two"
    artifact = _gold_artifact(
        [
            {
                "env": "aa11",
                "hypothesis": invalid,
                "summary": "synthetic test gold",
                "provenance": {},
            }
        ]
    )
    with pytest.raises(ValueError, match="predicate gold aa11 is invalid"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_record_shape_drift(tmp_path):
    artifact = _gold_artifact()
    artifact["records"][0]["new_field"] = True
    with pytest.raises(ValueError, match="record 0"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_non_list_records(tmp_path):
    artifact = _gold_artifact()
    artifact["records"] = {}
    with pytest.raises(ValueError, match="records must be a list"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_rejects_empty_records(tmp_path):
    with pytest.raises(ValueError, match="contains no records"):
        _load_synthetic(tmp_path, _gold_artifact([]), iteration=[])


def test_gold_index_rejects_reserved_or_other_non_iteration_game(tmp_path):
    artifact = _gold_artifact()
    artifact["records"][0]["env"] = "g50t"
    with pytest.raises(ValueError, match="do not equal draw iteration membership"):
        _load_synthetic(tmp_path, artifact)


def test_gold_index_requires_every_iteration_game(tmp_path):
    with pytest.raises(ValueError, match="missing=\\['bb22'\\]"):
        _load_synthetic(tmp_path, _gold_artifact(), iteration=["aa11", "bb22"])


@pytest.mark.parametrize("iteration", [None, "aa11", ["aa11", "aa11"], ["aa11", 7]])
def test_gold_index_rejects_malformed_draw_membership(tmp_path, iteration):
    draw = tmp_path / "draw.json"
    draw.write_text(json.dumps({"iteration": iteration}))
    with pytest.raises(ValueError, match="game draw"):
        K.load_gold_index(_write_gold(tmp_path, _gold_artifact()), draw_path=draw)
