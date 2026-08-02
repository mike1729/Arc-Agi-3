import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_replay import RecordedAction, compare_response  # noqa: E402


def _recorded(frames):
    return RecordedAction(
        step=1,
        action_id=1,
        action_data={},
        frames=frames,
        state="NOT_FINISHED",
        levels_completed=0,
        win_levels=0,
        available_actions=(1, 2),
        full_reset=False,
    )


def _response(frames):
    return SimpleNamespace(
        frame=frames,
        state=SimpleNamespace(value="NOT_FINISHED"),
        levels_completed=0,
        win_levels=0,
        available_actions=[1, 2],
        full_reset=False,
    )


def test_compare_response_accepts_exact_frames_and_metadata():
    result = compare_response(_recorded([[[1, 2]]]), _response([[[1, 2]]]))
    assert result["frames"]
    assert all(result["metadata"].values())
    assert result["first_frame_difference"] is None


def test_compare_response_reports_cell_difference():
    result = compare_response(_recorded([[[1, 2]]]), _response([[[1, 3]]]))
    assert not result["frames"]
    assert result["first_frame_difference"]["frame_index"] == 0
    assert result["first_frame_difference"]["changed_cells"] == 1


def test_compare_response_reports_frame_count_difference():
    result = compare_response(_recorded([[[1]], [[2]]]), _response([[[1]]]))
    assert result["first_frame_difference"]["frame_count"] == {
        "replayed": 1,
        "recorded": 2,
    }
