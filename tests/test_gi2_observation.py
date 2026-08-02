import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent/harness"))

from gi2_observation import (  # noqa: E402
    Handle,
    Tracker,
    changed_regions,
    componentize,
    local_compact_groups,
)


def test_componentize_and_changed_regions_are_four_connected():
    grid = [[1, 1, 0], [1, 2, 0], [0, 0, 0]]
    components = componentize(grid)
    assert sorted(component.pixels for component in components) == [1, 3, 5]
    assert changed_regions(grid, [[1, 1, 0], [1, 3, 0], [0, 0, 4]]) == [
        frozenset({(1, 1)}),
        frozenset({(2, 2)}),
    ]


def test_local_compact_groups_recovers_dense_multicolour_object():
    components = componentize([[1, 2], [1, 2]])
    handles = [Handle(f"o{i}", component) for i, component in enumerate(components)]
    groups = local_compact_groups(handles)
    assert [group.members for group in groups] == [("o0", "o1")]


def test_tracker_records_move_and_control_role():
    tracker = Tracker()
    first = tracker.update([[1, 0], [0, 0]], previous_grid=None, action_id=0, action_data={})
    second = tracker.update(
        [[0, 1], [0, 0]],
        previous_grid=[[1, 0], [0, 0]],
        action_id=1,
        action_data={},
    )
    assert any(event["type"] == "move" for event in second.events)
    moved = next(handle for handle in second.handles if handle.component.color == 1)
    assert moved.role_counts["controlled"] == 1
