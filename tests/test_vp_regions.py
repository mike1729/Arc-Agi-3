import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "harness"))
import vp_inventory as I  # noqa: E402
import vp_regions as R  # noqa: E402


def test_inventory_bands_separate_eligible_nine_to_twelve_from_excluded_tail():
    assert [I._region_band(n) for n in (1, 2, 3, 4, 8, 9, 12, 13)] == [
        "1", "2", "3", "4-8", "4-8", "9-12", "9-12", ">12"
    ]


def test_delta_regions_are_four_connected_not_diagonal():
    assert sorted(I._delta_regions({(0, 0), (0, 1), (1, 2)})) == [1, 2]


def test_recorded_mouse_coordinates_are_canonicalized_to_row_col():
    assert I._mouse_cell({"x": 7, "y": 11}) == (11, 7)
    assert I._mouse_cell({}) == (-1, -1)


def test_boxes_are_inclusive_zero_based_canonical_and_strict():
    assert R.canonicalize_boxes([[2, 3, 2, 3], [0, 0, 1, 1]]) == (
        (0, 0, 1, 1), (2, 3, 2, 3)
    )
    assert R.box_iou((0, 0, 0, 0), (0, 0, 0, 0)) == 1.0
    for bad in ([0, 0, 64, 64], [1, 1, 0, 0], [True, 0, 1, 1], [0, 0, 1]):
        with pytest.raises(ValueError):
            R.validate_box(bad)
    with pytest.raises(ValueError):
        R.validate_box(1)
    with pytest.raises(ValueError, match="duplicate"):
        R.canonicalize_boxes([[0, 0, 0, 0], [0, 0, 0, 0]])
    assert len(R.canonicalize_boxes([[0, col, 0, col] for col in range(12)])) == 12
    with pytest.raises(ValueError, match="at most 12"):
        R.canonicalize_boxes([[0, col, 0, col] for col in range(13)], grid_size=16)


def test_matching_maximizes_cardinality_instead_of_taking_the_best_first_iou():
    # P0 matches both golds and has the best IoU for G0. P1 matches only G0. A greedy
    # best-IoU choice for G0 gets one match; the frozen bipartite rule gets two.
    predicted = [[0, 0, 0, 2], [0, 2, 0, 3]]
    gold = [
        R.GoldRegion((0, 0, 0, 3), 4),
        R.GoldRegion((0, 0, 0, 1), 2),
    ]
    score = R.score_region_boxes(predicted, gold)
    assert score.matched == 2
    assert score.f1 == 1.0


def test_tiny_region_edge_tolerance_is_gold_conditioned():
    shifted = [[2, 2, 2, 2]]
    assert R.score_region_boxes(shifted, [R.GoldRegion((1, 1, 1, 1), 4)]).f1 == 1.0
    assert R.score_region_boxes(shifted, [R.GoldRegion((1, 1, 1, 1), 5)]).f1 == 0.0


def test_matching_uses_summed_iou_then_lexicographic_pairs_as_tiebreaks():
    high_iou = R.score_region_boxes(
        [[0, 0, 0, 3], [0, 1, 0, 4]],
        [R.GoldRegion((0, 0, 0, 3), 8), R.GoldRegion((0, 1, 0, 4), 8)],
    )
    assert high_iou.pairs == ((0, 0), (1, 1))

    lex_tie = R.score_region_boxes(
        [[0, 0, 0, 2], [0, 1, 0, 3]],
        [R.GoldRegion((0, 0, 0, 3), 8), R.GoldRegion((0, 0, 0, 3), 8)],
    )
    assert lex_tie.pairs == ((0, 0), (1, 1))

    # With one prediction equally matching two gold regions, the canonical earlier gold
    # index wins over the equally scoring match found by the skip branch.
    one_prediction = R.score_region_boxes(
        [[0, 0, 0, 3]],
        [R.GoldRegion((0, 0, 0, 3), 8), R.GoldRegion((0, 0, 0, 3), 8)],
    )
    assert one_prediction.pairs == ((0, 0),)


@pytest.mark.parametrize("cell_count", [0, -1, True, "1"])
def test_gold_region_cell_count_is_a_positive_non_boolean_integer(cell_count):
    with pytest.raises(ValueError, match="positive integer"):
        R.score_region_boxes([], [R.GoldRegion((0, 0, 0, 0), cell_count)])


def test_gold_region_cap_allows_twelve_and_rejects_thirteen():
    twelve = [R.GoldRegion((0, col, 0, col), 1) for col in range(12)]
    assert R.score_region_boxes([], twelve).gold == 12
    with pytest.raises(ValueError, match="at most 12"):
        R.score_region_boxes([], twelve + [R.GoldRegion((1, 0, 1, 0), 1)])


def test_empty_lists_and_false_positives_have_defined_scores():
    assert R.score_region_boxes([], []).f1 == 1.0
    assert R.score_region_boxes([[0, 0, 0, 0]], []).f1 == 0.0
    assert R.score_region_boxes([], [R.GoldRegion((0, 0, 0, 0), 1)]).f1 == 0.0


def _step(grid, *, action=1, reset=False):
    frame = SimpleNamespace(role=I.ROLE_SETTLED, grid=grid)
    return SimpleNamespace(
        action_id=I.RESET_ACTION_ID if reset else action,
        action_data={"x": 2, "y": 3},
        available_actions=[1, 6],
        completion_increment=0,
        frames=[frame],
        full_reset=False,
        is_completion=False,
        levels_completed=0,
    )


def _isolated_change_grid(count):
    grid = [[0] * 8 for _ in range(8)]
    for row, col in [(row, col) for row in range(0, 8, 2) for col in range(0, 8, 2)][:count]:
        grid[row][col] = 1
    return grid


@pytest.mark.parametrize("count, eligible, excluded", [(12, 1, 0), (13, 0, 1)])
def test_session_inventory_records_the_region_question_boundary(
    monkeypatch, count, eligible, excluded
):
    baseline = [[0] * 8 for _ in range(8)]
    steps = [_step(baseline, reset=True), _step(_isolated_change_grid(count), action=6)]
    monkeypatch.setattr(I, "iter_trace", lambda _path: iter(steps))
    result = I._session_inventory(Path("unused"))
    assert result["pairs_changed"] == 1
    assert result["pairs_region_eligible"] == eligible
    assert result["pairs_region_excluded"] == excluded
    assert result["delta_regions_hist"]["9-12" if eligible else ">12"] == 1
    assert result["clicks_effective"] == 1
