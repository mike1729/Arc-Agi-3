import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from es_questions import (  # noqa: E402
    PERMUTATIONS,
    assign_roles,
    build_cases,
    modal_color,
    partition_index,
    pre_state_complexity,
)


def test_permutation_table_matches_frozen_manifest_enumeration():
    assert PERMUTATIONS == (
        ("S", "C", "R"),
        ("S", "R", "C"),
        ("C", "S", "R"),
        ("C", "R", "S"),
        ("R", "S", "C"),
        ("R", "C", "S"),
    )
    for permutation in PERMUTATIONS:
        assert sorted(permutation) == ["C", "R", "S"]


def test_partition_indices_pinned_for_the_six_iteration_games():
    # These literals pin the frozen hash rule (gate_manifest.yaml -> es ->
    # corpus.partition_rule). A change here is a contract change, not a refactor.
    assert partition_index("dc22") == 4
    assert partition_index("ft09") == 2
    assert partition_index("ls20") == 3
    assert partition_index("m0r0") == 0
    assert partition_index("tu93") == 2
    assert partition_index("vc33") == 0


def test_assign_roles_uses_session_order_and_covers_all_roles():
    roles = assign_roles("m0r0", ["g1", "g2", "g3"])  # p=0 -> (S, C, R)
    assert roles == {"g1": "S", "g2": "C", "g3": "R"}
    roles = assign_roles("dc22", ["g1", "g2", "g3"])  # p=4 -> (R, S, C)
    assert roles == {"g1": "R", "g2": "S", "g3": "C"}


def test_modal_color_tie_resolves_to_smaller_value():
    assert modal_color([[1, 1], [2, 2]]) == 1
    assert modal_color([[5, 5, 0], [0, 5, 0]]) == 0


def test_pre_state_complexity_counts_non_background_components():
    # Background = modal colour 0; two separate 1-components (diagonal is not adjacent),
    # one 2-component.
    grid = [
        [0, 0, 0, 0],
        [0, 1, 0, 1],
        [0, 0, 0, 0],
        [2, 2, 0, 0],
    ]
    assert pre_state_complexity(grid) == 3


def _row(
    step,
    action_class=1,
    is_completion=False,
    completed_level=None,
    has_frames=True,
    has_pre=True,
    pre_state_row=None,
    pre_complexity=5,
    solved=False,
):
    return {
        "step": step,
        "action_class": action_class,
        "is_completion": is_completion,
        "completed_level": completed_level,
        "has_frames": has_frames,
        "has_pre": has_pre,
        "pre_state_row": pre_state_row if pre_state_row is not None else step - 1,
        "pre_complexity": pre_complexity,
        "solved": solved,
    }


def _synthetic_session():
    # step 1: initial RESET (no pre-state), steps 2..: actions. Completions at 5, 9, 14
    # completing levels 1, 2, 2 respectively (level repeat exercises DOSE-2 skipping).
    return [
        _row(1, action_class=0, has_pre=False, pre_state_row=None),
        _row(2, pre_complexity=5),
        _row(3, pre_complexity=9),
        _row(4, action_class=2, pre_complexity=5),
        _row(5, is_completion=True, completed_level=1, solved=True, pre_complexity=6),
        _row(6, pre_complexity=4),
        _row(7, pre_complexity=7),
        _row(8, action_class=2, pre_complexity=6),
        _row(9, is_completion=True, completed_level=2, solved=True, pre_complexity=8),
        _row(10, pre_complexity=6),
        _row(11, pre_complexity=8),
        _row(12, pre_complexity=3),
        _row(13, pre_complexity=7),
        _row(
            14,
            is_completion=True,
            completed_level=2,
            solved=True,
            pre_complexity=7,
        ),
    ]


def test_first_completion_anchors_no_transfer_case():
    cases = build_cases("dc22", "guid", "S", _synthetic_session())
    assert [case["query"]["step"] for case in cases] == [9, 14]


def test_dose1_is_earliest_and_dose2_skips_same_level():
    cases = build_cases("dc22", "guid", "S", _synthetic_session())
    case_9, case_14 = cases

    # case at step 9: only one earlier completion -> DOSE-2 unavailable.
    assert case_9["doses"]["DOSE-1"]["step"] == 5
    assert case_9["doses"]["DOSE-2"] is None
    assert case_9["availability"]["dose2"] is False
    assert case_9["availability"]["passive_complete"] is False

    # case at step 14: DOSE-1 = step 5 (earliest); DOSE-2 = step 9 (level 2 != 1).
    assert case_14["doses"]["DOSE-1"]["step"] == 5
    assert case_14["doses"]["DOSE-2"]["step"] == 9
    assert case_14["availability"]["dose2"] is True


def test_dose2_requires_distinct_level():
    rows = _synthetic_session()
    # Make the second completion also level 1: case at 14 then has no distinct level.
    rows[8] = _row(9, is_completion=True, completed_level=1, solved=True, pre_complexity=8)
    cases = build_cases("dc22", "guid", "S", rows)
    case_14 = cases[1]
    assert case_14["doses"]["DOSE-2"] is None
    assert case_14["availability"]["dose2"] is False


def test_dose3_matches_class_then_nearest_complexity_then_chronology():
    cases = build_cases("dc22", "guid", "S", _synthetic_session())
    case_14 = cases[1]
    # Query at 14: action class 1, query pre-complexity 7. Class-1 pool before step 14:
    # steps 2(5), 3(9), 6(4), 7(7), 10(6), 11(8), 12(3), 13(7). Nearest |delta|=0: steps
    # 7 and 13 -> chronological order picks both, 7 first.
    picks = case_14["doses"]["DOSE-3"]
    assert [row["step"] for row in picks] == [7, 13]
    assert [row["delta_complexity"] for row in picks] == [0, 0]
    assert case_14["availability"]["dose3"] is True

    # Query at 9: completing action class 1, query pre-complexity 8. Pool before 9 with
    # class 1: steps 2(5), 3(9), 6(4), 7(7) -> deltas 3,1,4,1 -> picks 3 then 7.
    case_9 = cases[0]
    assert [row["step"] for row in case_9["doses"]["DOSE-3"]] == [3, 7]


def test_dose3_excludes_completions_other_classes_and_future_steps():
    cases = build_cases("dc22", "guid", "S", _synthetic_session())
    for case in cases:
        query_step = case["query"]["step"]
        for pick in case["doses"]["DOSE-3"]:
            assert pick["step"] < query_step
            assert pick["action_class"] == case["query"]["action_class"]
            # completions (5, 9, 14) and the initial RESET (1) never enter DOSE-3.
            assert pick["step"] not in {1, 5, 9, 14}


def test_all_evidence_is_strictly_before_the_query():
    cases = build_cases("dc22", "guid", "S", _synthetic_session())
    for case in cases:
        query_step = case["query"]["step"]
        doses = case["doses"]
        steps = [doses[k]["step"] for k in ("DOSE-1", "DOSE-2") if doses[k] is not None]
        steps += [row["step"] for row in doses["DOSE-3"]]
        assert all(step < query_step for step in steps)


def test_insufficient_dose3_pool_reports_unavailable():
    rows = [
        _row(1, action_class=0, has_pre=False, pre_state_row=None),
        _row(2, action_class=6, pre_complexity=5),
        _row(
            3,
            action_class=6,
            is_completion=True,
            completed_level=1,
            solved=True,
            pre_complexity=6,
        ),
        _row(4, action_class=6, pre_complexity=5),
        _row(
            5,
            action_class=6,
            is_completion=True,
            completed_level=2,
            solved=True,
            pre_complexity=6,
        ),
    ]
    cases = build_cases("dc22", "guid", "S", rows)
    # Query at 5 has class 6; pool holds only steps 2 and 4 -> exactly two -> available.
    assert cases[0]["availability"]["dose3"] is True
    # Remove one pool row -> only one candidate -> unavailable.
    cases = build_cases("dc22", "guid", "S", rows[:3] + rows[4:])
    assert cases[0]["availability"]["dose3"] is False
    assert cases[0]["availability"]["passive_complete"] is False
