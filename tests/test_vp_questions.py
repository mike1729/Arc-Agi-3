import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "harness"))

from vp_screen import (  # noqa: E402
    _selector_rows,
    _semantic_rows,
    _palette_rows,
    _vp1_rows,
    _vp2_main_rows,
    parse_semantic,
    parse_vp1,
    parse_vp2,
    score_vp1,
    score_vp2,
)


def _vp1_answer():
    return {
        "marked_cells": {key: "red" for key in "ABCDE"},
        "patch_P": [["blue"] * 3 for _ in range(3)],
        "pixel_count_band": "17-64",
        "component_count_band": "3-4",
        "lookups": {"U1": "green", "U2": "black"},
    }


def test_vp1_parser_is_strict_and_closed():
    answer = _vp1_answer()
    assert parse_vp1(json.dumps(answer, separators=(",", ":"))) == answer
    invalid = copy.deepcopy(answer)
    invalid["marked_cells"]["A"] = "scarlet"
    with pytest.raises(ValueError, match="unknown color"):
        parse_vp1(json.dumps(invalid))
    with pytest.raises(ValueError, match="bare JSON"):
        parse_vp1("```json\n" + json.dumps(answer) + "\n```")


def test_vp2_parser_enforces_boxes_and_cross_fields():
    answer = {"changed_count_band": "5-16", "regions": [[1, 2, 3, 4], [8, 0, 8, 0]],
              "no_op": False, "change_kind": "move"}
    assert parse_vp2(json.dumps(answer)) == answer
    for regions in ([[[8, 0, 8, 0], [1, 2, 3, 4]]], [[[0, 0, 0, 0]] * 2], [[[2, 2, 1, 3]]]):
        invalid = {**answer, "regions": regions}
        with pytest.raises(ValueError):
            parse_vp2(json.dumps(invalid))
    with pytest.raises(ValueError, match="inconsistent no-op"):
        parse_vp2(json.dumps({"changed_count_band": "1-4", "regions": [],
                              "no_op": True, "change_kind": "none"}))


def test_semantic_parser_rejects_non_schema_values():
    assert parse_semantic('{"identity":"C"}', "identity") == {"identity": "C"}
    assert parse_semantic('{"transition":"became_false"}', "relation") == {"transition": "became_false"}
    with pytest.raises(ValueError):
        parse_semantic('{"identity":"target C"}', "identity")


def test_scorers_keep_format_failure_on_primary_track():
    answer = _vp1_answer()
    question = {
        "markers": [{"label": key, "gold": "red"} for key in "ABCDE"],
        "patch": {"gold": [["blue"] * 3 for _ in range(3)]},
        "pixel_target": {"gold": "17-64"}, "component_target": {"gold": "3-4"},
        "lookups": [{"label": "U1", "gold": "green"}, {"label": "U2", "gold": "black"}],
    }
    assert score_vp1(question, answer)["patch_exact"]
    assert score_vp1(question, None)["marked_correct"] == 0

    changed = {"changed": True, "gold": {"changed_count_band": "1-4", "no_op": False,
               "change_kind": "appear", "regions": [{"box": [1, 1, 1, 1], "cell_count": 1}]}}
    parsed = {"changed_count_band": "1-4", "regions": [[1, 1, 1, 1]],
              "no_op": False, "change_kind": "appear"}
    score = score_vp2(changed, parsed)
    assert score["count_band"] and score["change_kind"] and score["region_f1"] == 1


def test_frozen_row_plan_counts_when_artifact_exists():
    artifact = ROOT / "logs" / "vp_questions.json"
    if not artifact.exists():
        pytest.skip("question artifact not emitted yet")
    document = json.loads(artifact.read_text())
    assert len(_vp1_rows(document)) == 288
    selector = _selector_rows(document, "I-8")
    assert len(selector) == 96
    assert len(_vp2_main_rows(document, "I-8", "contact")) == 384
    assert len(_vp2_main_rows(document, "I-4", "contact")) == 240
    assert len(_semantic_rows(document, "I-8", "contact")) == 72
    assert len(_palette_rows(document, "I-8", "contact")) == 48
    assert all("session_index" in row for row in _vp1_rows(document) + selector)
