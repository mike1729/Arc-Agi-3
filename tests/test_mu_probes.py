"""MU probe regressions. Every test names the defect it pins."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "harness"))
import mu_probes as M  # noqa: E402

INVENTORY = ROOT / "logs/mu_inventory.json"


# ------------------------------------------------------------------ synthetic fixtures


def grid_from(rows: list[str]) -> list[list[int]]:
    """'..9..' style rows over hex digits; '.' is 0."""
    return [[0 if char == "." else int(char, 16) for char in row] for row in rows]


def registry(rows: list[str]) -> tuple[M.MuObject, ...]:
    from gi2_observation import Tracker

    tracker = Tracker()
    observation = tracker.update(
        grid_from(rows), previous_grid=None, action_id=1, action_data={}
    )
    return M.build_registry(observation)


def two_state_window(before: list[str], after: list[str]) -> M.EvidenceWindow:
    stubs = [
        {"step": 1, "frame_index": 0, "role": "settled", "level": 0,
         "action": {"id": 0, "data": {}}, "available_actions": [1, 2, 3],
         "starts_window": True, "level_increment": 0},
        {"step": 2, "frame_index": 0, "role": "settled", "level": 0,
         "action": {"id": 2, "data": {}}, "available_actions": [1, 2, 3],
         "starts_window": False, "level_increment": 0},
    ]
    grids = {"1.0": grid_from(before), "2.0": grid_from(after)}
    return M.build_window("test", "guid", "S", "T3", stubs, grids, [0, 1])


# ------------------------------------------------------------------ frozen mirrors


def test_colour_names_mirror_vp_freeze_one_rather_than_drifting():
    # A private palette would silently rename gold that VP already measured against.
    import vp_questions

    assert M.COLOR_NAMES == vp_questions.COLOR_NAMES


def test_visual_relations_agree_with_the_frozen_es_grammar_implementation():
    # mu_probes.relation_holds is a duplicate of es_candidates._relation_holds kept for
    # freeze independence; a silent divergence would make MU-T1 gold disagree with ES.
    import es_candidates

    objects = registry([
        "99..8",
        "9...8",
        ".....",
        "..77.",
    ])
    as_es = [
        {"colour": item.colour, "cells": item.cells, "bbox": item.bbox} for item in objects
    ]
    for name in M.VISUAL_RELATIONS:
        for left_index, left in enumerate(objects):
            for right_index, right in enumerate(objects):
                assert M.relation_holds(name, left, right) == es_candidates._relation_holds(
                    name, as_es[left_index], as_es[right_index]
                ), (name, left.alias, right.alias)


# ------------------------------------------------------------------ referent aliases


def test_alias_rank_is_reading_order_of_the_bbox_corner_within_one_colour():
    objects = {item.alias: item for item in registry([
        ".9...",
        ".....",
        "9..9.",
    ])}
    assert objects["blue#1"].bbox[:2] == (0, 1)
    assert objects["blue#2"].bbox[:2] == (2, 0)
    assert objects["blue#3"].bbox[:2] == (2, 3)


def test_alias_numbering_restarts_per_colour_so_names_are_not_global_ranks():
    aliases = {item.alias for item in registry([
        "9.8",
        "...",
    ])}
    assert {"blue#1", "red#1"} <= aliases


def test_adjacency_lists_only_report_four_connected_contact_not_diagonal():
    # The background is an object like any other here, so the assertion is about the
    # diagonal pair: red touches blue orthogonally, pink only diagonally.
    objects = registry([
        "98.",
        "..7",
    ])
    lists = M.adjacency_lists(objects)
    assert "red#1" in lists["blue#1"]
    assert "pink#1" not in lists["red#1"]
    assert "blue#1" not in lists["pink#1"]


# ------------------------------------------------------------------ transition outcomes


def test_moved_requires_an_exact_translation_not_a_centroid_shift():
    # A component that grows keeps a moving centroid; labelling that "moved" would put a
    # wrong delta into MU-T3 gold, so the vocabulary refuses it.
    window = two_state_window(["99..", "...."], ["999.", "...."])
    outcomes = window.transitions[0].outcomes
    assert outcomes["blue#1"]["kind"] == M.INELIGIBLE_OUTCOME


def test_translated_object_is_moved_with_the_exact_delta():
    window = two_state_window([".99.", "...."], ["....", ".99."])
    assert window.transitions[0].outcomes["blue#1"] == {"kind": "moved", "delta": [1, 0]}


def test_recolour_needs_the_same_cells_and_reports_the_new_colour():
    window = two_state_window([".99.", "...."], [".88.", "...."])
    outcome = window.transitions[0].outcomes["blue#1"]
    assert outcome["kind"] == "recoloured" and outcome["to"] == "red"


def test_split_parents_are_deformed_rather_than_labelled_moved_or_unchanged():
    window = two_state_window(["999.", "...."], ["9.9.", "...."])
    outcome = window.transitions[0].outcomes["blue#1"]
    assert outcome["kind"] == M.INELIGIBLE_OUTCOME
    assert outcome["reason"] in {"split", "reshaped"}


def test_disappearance_and_appearance_are_counted_separately():
    window = two_state_window(["9...", "...."], ["....", "..8."])
    transition = window.transitions[0]
    assert transition.outcomes["blue#1"]["kind"] == "disappeared"
    assert transition.appeared == 1


def test_no_op_is_a_cell_level_fact_not_an_object_level_one():
    window = two_state_window([".9..", "...."], [".9..", "...."])
    assert window.transitions[0].no_op is True
    assert window.transitions[0].changed_cells == 0


# ------------------------------------------------------------------ windows


def test_window_never_crosses_a_level_boundary_or_a_reset():
    stubs = [
        {"starts_window": True}, {"starts_window": False}, {"starts_window": True},
        {"starts_window": False}, {"starts_window": False},
    ]
    assert M.window_members(stubs, 4, 4) == [2, 3, 4]
    assert M.window_members(stubs, 2, 4) is None       # a boundary state opens no window
    assert M.window_members(stubs, 1, 4) == [0, 1]


def test_window_span_is_capped_by_the_requested_prefix_not_by_the_level_length():
    stubs = [{"starts_window": index == 0} for index in range(10)]
    assert M.window_members(stubs, 9, 2) == [7, 8, 9]


# ------------------------------------------------------------------ selection determinism


def test_hash_order_is_stable_and_independent_of_the_input_order():
    items = [{"a": index} for index in range(20)]
    forward = M.hash_order(items, "seed")
    backward = M.hash_order(list(reversed(items)), "seed")
    assert forward == backward
    assert M.hash_order(items, "other") != forward


def test_bounded_fork_representative_policy_caps_mouse_rows_and_keeps_simple_actions():
    forks = [{"action_id": 1, "action_data": {}}] + [
        {"action_id": 6, "action_data": {"x": index, "y": 2 * index}} for index in range(40)
    ]
    kept = M.bounded_fork_candidates(forks, "case")
    mouse = [row for row in kept if row["action_id"] == 6]
    assert len(mouse) == M.MOUSE_REPRESENTATIVE_CAP
    assert [row for row in kept if row["action_id"] == 1]
    assert mouse == sorted(mouse, key=lambda row: (row["action_data"]["y"], row["action_data"]["x"]))
    assert M.bounded_fork_candidates(list(reversed(forks)), "case") == kept


def test_fork_rows_are_authenticated_against_the_query_state_byte_for_byte():
    from gi2_forks import encode_grid

    grid = [[0] * 64 for _ in range(64)]
    grid[3][4] = 9
    row = {"pre_grid_rle": encode_grid([[0] * 64 for _ in range(64)]), "forks": []}
    with pytest.raises(ValueError, match="pre-state"):
        M.authenticate_forks(row, grid)
    assert M.authenticate_forks({"pre_grid_rle": encode_grid(grid), "forks": [1]}, grid) == [1]


# ------------------------------------------------------------------ schemas and scoring


def t1_case() -> dict:
    return {
        "probe": "T1", "window": ["1.0", "2.0"],
        "question": {"count_colour": "blue", "bbox_alias": "blue#1", "size_alias": "red#1",
                     "relation": {"name": "adjacent", "left": "blue#1", "right": "red#1"}},
        "gold": {"count": 2, "bbox": [0, 1, 2, 3], "size": 4, "relation": True},
    }


def test_parse_refuses_prose_wrapped_json_and_unknown_keys():
    case = t1_case()
    with pytest.raises(ValueError, match="bare JSON"):
        M.parse_answer(case, 'Here you go: {"count": 2}')
    with pytest.raises(ValueError, match="keys differ"):
        M.parse_answer(case, '{"count": 2}')
    with pytest.raises(ValueError):
        M.parse_answer(case, '{"count": true, "bbox": [0,1,2,3], "size": 4, "relation": true}')


def test_unparsed_answers_score_zero_and_stay_in_the_denominator():
    case = t1_case()
    score = M.score_case(case, None)
    assert score["rate"] == 0.0 and score["exact"] is False
    assert len(score["items"]) == len(M.T1_ITEMS)


def test_t3_moved_is_only_correct_when_the_delta_matches():
    case = {
        "probe": "T3", "question": {"objects": ["blue#1"]},
        "gold": {"no_op": False, "level_increment": 0,
                 "objects": {"blue#1": {"kind": "moved", "delta": [1, 0]}}},
    }
    right = {"no_op": False, "level_increment": 0,
             "objects": {"blue#1": {"kind": "moved", "delta": [1, 0]}}}
    wrong = {"no_op": False, "level_increment": 0,
             "objects": {"blue#1": {"kind": "moved", "delta": [0, 1]}}}
    assert M.score_case(case, right)["exact"] is True
    assert M.score_case(case, wrong)["items"]["blue#1"] is False


def test_t3_ignores_a_redundant_delta_instead_of_refusing_it():
    # MU-E1: `delta` is REQUIRED in the guided schema and typed ["array","null"] with no
    # conditional, so a non-null delta on a non-moved outcome is what the model was asked
    # for. Refusing it scored compliant answers 0 on 41% of T3 rows, unequally by arm.
    case = {
        "probe": "T3", "question": {"objects": ["blue#1"]},
        "gold": {"no_op": False, "level_increment": 0,
                 "objects": {"blue#1": {"kind": "unchanged", "delta": None}}},
    }
    body = ('{"no_op": false, "level_increment": 0, '
            '"objects": {"blue#1": {"kind": "unchanged", "delta": %s}}}')
    for supplied in ("[0, 0]", "null", "[3, -1]"):
        answer = M.parse_answer(case, body % supplied)
        assert M.score_case(case, answer)["exact"] is True, supplied
    # A `moved` outcome still needs a real pair, and the pair is still compared.
    moved = {"probe": "T3", "question": {"objects": ["blue#1"]},
             "gold": {"no_op": False, "level_increment": 0,
                      "objects": {"blue#1": {"kind": "moved", "delta": [1, 0]}}}}
    with pytest.raises(ValueError, match="moved needs an integer delta pair"):
        M.parse_answer(moved, body.replace("unchanged", "moved") % "null")
    wrong = M.parse_answer(moved, body.replace("unchanged", "moved") % "[0, 1]")
    assert M.score_case(moved, wrong)["exact"] is False


def test_choice_probes_accept_any_completing_option_and_refuse_unoffered_ones():
    case = {
        "probe": "T5",
        "question": {"options": [{"label": "A1", "id": 1, "data": {}},
                                 {"label": "A2", "id": 2, "data": {}}]},
        "gold": {"accepting": ["A1", "A2"]},
    }
    assert M.score_case(case, {"choice": "A2"})["rate"] == 1.0
    with pytest.raises(ValueError, match="not an offered option"):
        M.parse_answer(case, '{"choice": "A9"}')


def test_output_schema_pins_the_answer_space_to_this_case():
    case = {
        "probe": "T4",
        "question": {"options": [{"label": "A1", "id": 1, "data": {}}]},
        "gold": {"accepting": ["A1"]},
    }
    assert M.output_schema(case)["properties"]["choice"]["enum"] == ["A1"]


# ------------------------------------------------------------------ the built inventory


@pytest.fixture(scope="module")
def inventory() -> dict:
    if not INVENTORY.exists():
        pytest.skip("logs/mu_inventory.json has not been built")
    return json.loads(INVENTORY.read_text())


def test_inventory_never_contains_a_sealed_r_role_session(inventory):
    sealed = {row["guid"] for row in inventory["sealed_sessions"]}
    assert sealed
    assert not sealed & {case["guid"] for case in inventory["cases"]}
    assert {case["role"] for case in inventory["cases"]} == {"S", "C"}


def test_t1_floor_is_exact_by_construction_so_t1_is_a_gate_not_a_screen_positive_cell(inventory):
    rates = [
        case["floor"]["rate"] for case in inventory["cases"] if case["probe"] == "T1"
    ]
    assert rates and set(rates) == {1.0}


def test_every_case_fits_the_context_ceiling_in_every_arm(inventory):
    ceiling = inventory["context_audit"]["prompt_tokens_max"]
    for row in inventory["context_audit"]["rows"]:
        assert max(row["tokens"].values()) <= ceiling, row["case_id"]


def test_t3_cases_never_show_the_state_they_ask_about(inventory):
    seen = {"executed": 0, "fork": 0}
    for case in inventory["cases"]:
        if case["probe"] != "T3":
            continue
        seen[case["form"]] += 1
        assert case["query_state"] == case["window"][-1]
        assert case["audit"]["queried_post_state"] not in case["window"], case["case_id"]
    assert seen["executed"] and seen["fork"]


def test_choice_cases_are_never_unanimous_so_guessing_cannot_be_right(inventory):
    for case in inventory["cases"]:
        if case["probe"] not in {"T4", "T5"}:
            continue
        options = {option["label"] for option in case["question"]["options"]}
        accepting = set(case["gold"]["accepting"])
        assert accepting and accepting < options, case["case_id"]
        assert len(options) >= M.CLOSED_ACTION_OPTIONS_MIN


def test_t2_gold_maps_every_offered_row_to_a_previous_alias_or_new(inventory):
    for case in inventory["cases"]:
        if case["probe"] != "T2":
            continue
        assert set(case["gold"]) == set(case["question"]["rows"])
        assert all(row.startswith("B") for row in case["gold"])
        assert case["reveal"]["relabel_query_state"] is True
        assert case["reveal"]["derived_through"] == len(case["window"]) - 3


def test_case_counts_match_the_frozen_plan_or_are_recorded_as_shortfalls(inventory):
    shortfalls = {
        (row["env"], row["role"], row["probe"]) for row in inventory["shortfalls"]
    }
    for key, cell in inventory["cells"].items():
        env, role, probe = key.split("|")
        wanted = M.CASES_PER_PROBE_PER_GAME_PER_ROLE[probe]
        assert cell["n"] == wanted or (env, role, probe) in shortfalls, key


def test_the_stated_alias_tie_break_is_the_one_the_registry_applies():
    # Review finding (a): two same-colour components CAN share a bounding-box top-left
    # corner, so the prompt's naming rule has to state the deeper key or the arms without
    # an object table cannot resolve the referent in principle.
    import mu_render
    from types import SimpleNamespace

    objects = [item for item in registry(["9.9", ".99", "99."]) if item.colour == 9]
    assert len(objects) == 2
    assert objects[0].bbox[:2] == objects[1].bbox[:2] == (0, 0)   # the corner really ties
    ranked = sorted(objects, key=lambda item: int(item.alias.split("#")[1]))
    assert ranked[0].bbox[2] <= ranked[1].bbox[2]                 # broken on bottom row
    text = mu_render.preamble(SimpleNamespace(states=[None, None]))
    assert "smaller bounding-box bottom row" in text
    assert "MORE cells" in text


def test_manifest_dates_are_fingerprintable_but_junk_still_raises():
    # The freeze fingerprints the whole manifest block, and PyYAML returns `frozen_on` as a
    # datetime.date — the freeze crashed on it. Coercion is ISO-8601 and date-only: anything
    # else must still raise rather than be fingerprinted as its repr.
    import datetime

    stamped = M.fingerprint({"frozen_on": datetime.date(2026, 8, 3)})
    assert stamped == M.fingerprint({"frozen_on": "2026-08-03"})
    with pytest.raises(TypeError):
        M.fingerprint({"bad": object()})
