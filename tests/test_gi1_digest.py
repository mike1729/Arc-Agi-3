"""Direct tests for `gi1_digest` — the GI-1 layer-3 evidence compiler (conditions c/d).

WHY THIS FILE EXISTS. `gi1_digest.py --selftest` is real coverage but it is a spot-check on
two iteration games (ls20, m0r0), it is not collected by pytest, and it can only assert what
those two recordings happen to contain. The cases that decide whether GI-1 measures anything
are exactly the ones a pair of well-behaved sessions does not exercise: a completion on the
first recorded line, a level completed in a single action, an action that changes nothing, an
ACTION6 click, and the E3 ablation's containment.

The load-bearing one is post-terminal exclusion. A completion's own settled grid is the NEXT
level's board — a level reset, not a solved-state image (notes/design-pivot.md §2.3). If the
compiler ever showed it as evidence for the *completed* level it would be handing the model a
fresh board and calling it goal evidence, and every (c)/(d) number would be invalid while
still looking healthy. Nothing downstream would catch it, so it is asserted here in both
directions: the abstract must carry the pre-terminal board, and must not carry the other one.

The second reason is the derivability rule — layer 3 may add NO information beyond the
canonical packet, only representation and computation. That is a property of the compiler
rather than of any one digest, so it is tested as recomputation (counts re-derived from the
grids without the segmenter) and as containment (nothing named that the packet does not hold).

Two groups, split by what they need:

  - SYNTHETIC tests build Packet/Step/Completion objects directly on tiny grids. They need no
    replay data, cover every branch of the compiler, and are the whole suite in the mutation
    sandbox.
  - CORPUS tests compile a real ls20 packet and skip when the replay mirror is absent.

Run:
  .venv/bin/python -m pytest tests/test_gi1_digest.py -q
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_packets as P     # noqa: E402
import gi1_digest as D      # noqa: E402

# Resolved at import: the mutation sandbox copies only agent/harness and tests, so neither the
# replay mirror nor logs/ exists there and every corpus test must skip rather than error.
CORPUS_PRESENT = P.CORPUS.exists() and P.SESSIONS_TABLE.exists() and P.DRAW.exists()
requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT, reason="replay corpus not present (mutation sandbox / no mirror)")

# The compiler's own colour table, taken from its namespace so the tests cannot drift from the
# vendored mapping they are checking against.
_CH = D.ARC_COLOR_CHARS


# --------------------------------------------------------------------------- synthetic packets

def _grid(v: int = 0, n: int = 3) -> list:
    """A settled grid of one uniform colour. The segmentation the compiler calls is
    size-agnostic and nothing here needs 64x64, so grids stay at 3x3 and the suite stays fast;
    the real-board invariants are the corpus group's job."""
    return [[v] * n for _ in range(n)]


def _steps_and_completions(rows: list) -> tuple[list, list]:
    """Build Step/Completion objects from (action_id, action_data, settled, levels) rows by the
    rule load_timeline applies: a completion is `levels_completed` rising, its pre-terminal grid
    is the PREVIOUS step's board (absent on line 1), and the level window restarts on the step
    after it."""
    steps: list = []
    completions: list = []
    prev_levels, level_start = 0, 1
    for index, (action_id, action_data, settled, levels) in enumerate(rows, start=1):
        steps.append(P.Step(
            index=index, action_id=action_id, action_data=dict(action_data), n_frames=1,
            settled=settled, levels_completed=levels, available_actions=[1, 2, 3],
            state="NOT_FINISHED", full_reset=False))
        if levels > prev_levels:
            completions.append(P.Completion(
                step_index=index, level=levels, increment=levels - prev_levels,
                action_id=action_id, action_data=dict(action_data),
                level_start_index=level_start,
                pre_terminal_settled=steps[index - 2].settled if index >= 2 else None,
                degenerate=index < 2))
            level_start, prev_levels = index + 1, levels
    return steps, completions


def _packet(rows: list, checkpoint: int | None = None) -> P.Packet:
    """A canonical packet over `rows`, truncated at `checkpoint` exactly as extract() does."""
    steps, completions = _steps_and_completions(rows)
    checkpoint = checkpoint or len(steps)
    return P.Packet(
        env="zz01", guid="g1", checkpoint_kind=f"offset:{checkpoint}",
        checkpoint_step=checkpoint, initial_settled=steps[0].settled,
        initial_is_post_action=steps[0].action_id != 0, steps=steps[:checkpoint],
        completions=[c for c in completions if c.step_index <= checkpoint],
        available_actions=steps[checkpoint - 1].available_actions)


# Six steps over two levels, each board a distinct uniform colour, so "which board did the
# digest report" is answerable from the digest alone.
C_OPEN, C_MID, C_PRE, C_POST, C_NEXT_A, C_NEXT_B = (_CH[v] for v in (0, 5, 8, 15, 4, 6))

_ONE_COMPLETION = [
    (0, {}, _grid(0), 0),       # 1  RESET  -> C_OPEN
    (1, {}, _grid(5), 0),       # 2  UP     -> C_MID
    (2, {}, _grid(8), 0),       # 3  DOWN   -> C_PRE     the pre-terminal board
    (7, {}, _grid(15), 1),      # 4  UNDO   -> C_POST    completes level 1; level 2's board
    (3, {}, _grid(4), 1),       # 5  LEFT   -> C_NEXT_A
    (3, {}, _grid(6), 1),       # 6  LEFT   -> C_NEXT_B
]


def _colours_named(blob) -> set:
    """Every colour character the digest mentions anywhere: `by_color` keys, `a->b` transition
    keys, and the `color` field of a largest-object entry. Used to assert containment — what
    the digest talks about must be what the packet holds."""
    found: set = set()
    for node in _walk(blob):
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("color"), str):
            found.add(node["color"])
        for key in node:
            if "->" in key:
                found.update(key.split("->"))
            elif len(key) == 1 and key in _CH:
                found.add(key)
    return found


def _walk(blob):
    yield blob
    if isinstance(blob, dict):
        for value in blob.values():
            yield from _walk(value)
    elif isinstance(blob, list):
        for value in blob:
            yield from _walk(value)


# --------------------------------------------------------------------------- fixture fidelity

def test_the_synthetic_builder_agrees_with_the_real_packet_loader(tmp_path, monkeypatch):
    """Every other test here trusts `_packet` to wire completions the way layer 1 does. Pin
    that against load_timeline/extract on a written recording, so a change to the pre-terminal
    or level-window rule cannot leave this suite quietly testing fiction."""
    root = tmp_path / "corpus"
    (root / "zz01").mkdir(parents=True)
    lines = [json.dumps({"data": {
        "frame": [settled], "action_input": {"id": action_id, "data": dict(action_data)},
        "levels_completed": levels, "win_levels": 3, "available_actions": [1, 2, 3],
        "state": "NOT_FINISHED", "full_reset": False}})
        for action_id, action_data, settled, levels in _ONE_COMPLETION]
    (root / "zz01" / "g1.recording.jsonl").write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(P, "CORPUS", root)

    loaded = P.extract(P.load_timeline("zz01", "g1"), "offset:6", 6)
    built = _packet(_ONE_COMPLETION)
    assert built.steps == loaded.steps
    assert built.completions == loaded.completions
    assert D.compile_digest(built) == D.compile_digest(loaded)


# --------------------------------------------------------------------------- action rendering

@pytest.mark.parametrize("action_id,expected", [
    (0, "RESET"), (1, "UP"), (2, "DOWN"), (3, "LEFT"),
    (4, "RIGHT"), (5, "SPACE"), (7, "UNDO"),
])
def test_action_display_renders_the_model_facing_name(action_id, expected):
    """The literal table the vendored solver shows the model. Spelled out rather than read
    back from the maps, so a corrupted map fails here instead of agreeing with itself."""
    assert D.action_display(action_id, {}) == expected


@pytest.mark.parametrize("action_id", sorted(D._ID_TO_ENGINE))
def test_every_engine_name_in_the_id_map_has_a_model_facing_name(action_id):
    """The two maps are replicated from the solver and have to stay aligned: an id whose engine
    name is missing from _ENGINE_TO_MODEL falls through to the raw ACTION<n> spelling, which is
    a different token to the model and would split one action into two in the trail."""
    engine = D._ID_TO_ENGINE[action_id]
    assert engine in D._ENGINE_TO_MODEL
    expected = "MOUSE(row=0, col=0)" if engine == "ACTION6" else D._ENGINE_TO_MODEL[engine]
    assert D.action_display(action_id, {}) == expected


def test_the_id_map_covers_reset_through_action7():
    assert set(D._ID_TO_ENGINE) == set(range(8))


def test_mouse_puts_the_y_coordinate_in_the_row_and_x_in_the_column():
    """ACTION6 is the only action carrying coordinates, and the axis swap is the easy thing to
    get backwards: the engine records x/y, the model reads row/col."""
    assert D.action_display(6, {"x": 3, "y": 7}) == "MOUSE(row=7, col=3)"


def test_mouse_without_coordinates_falls_back_to_the_origin_rather_than_raising():
    assert D.action_display(6, {}) == "MOUSE(row=0, col=0)"


def test_mouse_coordinates_render_as_integers():
    """A float out of JSON would print as `row=7.0`, which no longer string-matches any other
    rendering of the same click — and clicks are compared as strings in the level trail."""
    assert D.action_display(6, {"x": 3.0, "y": 7.9}) == "MOUSE(row=7, col=3)"


def test_an_action_id_outside_the_map_renders_as_itself_rather_than_guessing():
    assert D.action_display(9, {}) == "ACTION9"


def test_a_mouse_click_survives_into_the_compiled_trail():
    """End to end for the click path: ACTION6 reaches the digest through two separate call
    sites — `after_action` on a delta, and `completing_action` on a terminal abstract."""
    rows = [(0, {}, _grid(0), 0), (6, {"x": 2, "y": 1}, _grid(5), 0),
            (6, {"x": 4, "y": 6}, _grid(8), 1)]
    abstract = D.compile_digest(_packet(rows))["observed_completions"][0]
    assert abstract["completing_action"] == "MOUSE(row=6, col=4)"
    assert abstract["distinct_actions_in_level"] == ["MOUSE(row=1, col=2)", "RESET"]


# --------------------------------------------------------------------------- object inventory

def test_inventory_pixel_totals_equal_a_direct_recount_of_the_grid():
    """Derivability at its most literal: the inventory is a regrouping of the grid's own cells,
    so per-colour pixel counts must survive a recount that never touches the segmenter."""
    grid = [[0, 1, 1], [0, 0, 1], [2, 2, 0]]
    counted: dict = {}
    for row in grid:
        for v in row:
            counted[_CH[v]] = counted.get(_CH[v], 0) + 1
    by_color = D.inventory(grid)["by_color"]
    assert {c: v["pixels"] for c, v in by_color.items()} == counted


def test_inventory_counts_four_connected_components_not_colours():
    """Two same-coloured cells that do not touch are two objects; their shape hash is
    position-independent, so they are still only one distinct shape."""
    grid = [[1, 0, 0], [0, 0, 0], [0, 0, 1]]
    inv = D.inventory(grid)
    assert inv["n_objects"] == 3                    # two 1-cells plus the 0 background
    assert inv["by_color"][_CH[0]] == {"objects": 1, "pixels": 7, "distinct_shapes": 1}
    assert inv["by_color"][_CH[1]] == {"objects": 2, "pixels": 2, "distinct_shapes": 1}


def test_inventory_reports_at_most_five_largest_objects():
    """The abstract is a decision summary; the cap is what keeps a busy board from turning the
    digest back into an object dump."""
    grid = [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15]]
    inv = D.inventory(grid)
    assert inv["n_objects"] == 16
    assert len(inv["largest"]) == 5


def test_inventory_bboxes_bound_their_own_object():
    grid = [[0, 0, 0], [0, 1, 1], [0, 0, 0]]
    boxes = {o["color"]: o["bbox"] for o in D.inventory(grid)["largest"]}
    assert boxes[_CH[1]] == [1, 1, 1, 2]


def test_object_totals_are_consistent_within_one_inventory():
    grid = [[0, 1, 2], [1, 1, 0], [2, 0, 0]]
    inv = D.inventory(grid)
    assert inv["n_objects"] == sum(v["objects"] for v in inv["by_color"].values())
    assert sum(v["pixels"] for v in inv["by_color"].values()) == 9


# ---------------------------------------------------------------------------- delta summaries

def test_an_action_that_changes_nothing_yields_a_bare_zero_not_a_summary():
    """The whole point: a no-op action must report a no-op. Emitting a bbox, a transition table
    and an object count over an empty change set would be an invented observation, and §2.3
    forbids the digest from adding anything the packet does not contain."""
    assert D.delta_summary(_grid(5), _grid(5)) == {"changed_cells": 0}


def test_changed_cells_agrees_with_the_layer_one_delta_primitive():
    """The compiler is built on settled_delta and must not recount the grid independently."""
    before, after = [[0, 1], [2, 3]], [[0, 9], [2, 8]]
    assert D.delta_summary(before, after)["changed_cells"] == len(
        P.settled_delta(before, after))


def test_the_delta_bbox_bounds_exactly_the_changed_cells():
    before = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    after = [[0, 0, 0], [0, 1, 0], [0, 0, 1]]
    assert D.delta_summary(before, after)["bbox"] == [1, 1, 2, 2]


def test_colour_transitions_are_counted_per_ordered_pair():
    before, after = [[0, 0], [0, 1]], [[1, 1], [0, 0]]
    assert D.delta_summary(before, after)["color_transitions"] == {
        f"{_CH[0]}->{_CH[1]}": 2, f"{_CH[1]}->{_CH[0]}": 1}


def test_colour_transitions_keep_at_most_the_eight_most_frequent():
    """A lossy top-8 view, which is why `changed_cells` is reported separately: the counts in
    the table need not sum to it and nothing downstream may assume they do."""
    before = [[v for v in range(9)]]
    after = [[(v + 1) % 16 for v in range(9)]]
    summary = D.delta_summary(before, after)
    assert summary["changed_cells"] == 9
    assert len(summary["color_transitions"]) == 8


def test_object_count_delta_tracks_the_segmentation_of_both_boards():
    before = _grid(0)
    after = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    assert D.delta_summary(before, after)["object_count_delta"] == 1
    assert D.delta_summary(before, after)["objects_appeared"] >= 1
    assert D.delta_summary(after, before)["object_count_delta"] == -1


# ------------------------------------------------------ pre-terminal vs post-terminal evidence

def test_the_terminal_abstract_reports_the_board_before_the_completing_action():
    """The pre-terminal board is the completed level's goal evidence: the arrangement the
    completing action was taken against."""
    abstract = D.compile_digest(_packet(_ONE_COMPLETION))["observed_completions"][0]
    assert abstract["degenerate"] is False
    assert abstract["completing_action"] == "UNDO"
    assert set(abstract["pre_terminal_inventory"]["by_color"]) == {C_PRE}


def test_the_post_terminal_board_never_appears_as_evidence_for_the_completed_level():
    """The other direction, and the one that would invalidate GI-1 silently. The completing
    step's own settled grid is level 2's fresh board; if any part of it reached the completed
    level's abstract, conditions (c)/(d) would be scored on a board they had been shown."""
    abstract = D.compile_digest(_packet(_ONE_COMPLETION))["observed_completions"][0]
    assert C_POST not in _colours_named(abstract)
    post_terminal = D.inventory(_grid(15))
    post_terminal.pop("_hashes")
    assert abstract["pre_terminal_inventory"] != post_terminal


def test_the_final_transition_is_the_delta_into_the_pre_terminal_board():
    """The last observable within-level change, C_MID -> C_PRE. Reading one step later would
    give C_PRE -> C_POST, which is the level reset rather than an in-level effect."""
    abstract = D.compile_digest(_packet(_ONE_COMPLETION))["observed_completions"][0]
    assert abstract["final_transition"]["color_transitions"] == {f"{C_MID}->{C_PRE}": 9}
    assert abstract["final_transition"]["changed_cells"] == 9


def test_the_completed_levels_trail_stops_before_the_completing_action():
    abstract = D.compile_digest(_packet(_ONE_COMPLETION))["observed_completions"][0]
    assert abstract["distinct_actions_in_level"] == ["DOWN", "RESET", "UP"]
    assert "UNDO" not in abstract["distinct_actions_in_level"]
    assert abstract["level_length_actions"] == 4


def test_the_post_terminal_board_is_still_the_current_board_at_a_completion_checkpoint():
    """Excluded as goal evidence, present as the situation. At the completion step it is what
    the agent is looking at, and the level's action counter is back to zero."""
    digest = D.compile_digest(_packet(_ONE_COMPLETION, checkpoint=4))
    assert set(digest["current_inventory"]["by_color"]) == {C_POST}
    assert digest["actions_this_level"] == 0
    assert digest["current_level_recent_deltas"] == []


def test_the_current_level_deltas_never_reach_back_into_the_completed_level():
    """The window opens on the completing step's OWN board — which is this level's initial
    board, not a solved-state image — and never earlier, so no board belonging to the completed
    level can reappear in the current level's change record."""
    recent = D.compile_digest(_packet(_ONE_COMPLETION))["current_level_recent_deltas"]
    assert [d["after_action"] for d in recent] == ["LEFT", "LEFT"]
    assert recent[0]["color_transitions"] == {f"{C_POST}->{C_NEXT_A}": 9}
    assert recent[1]["color_transitions"] == {f"{C_NEXT_A}->{C_NEXT_B}": 9}
    assert {C_OPEN, C_MID, C_PRE} & _colours_named(recent) == set()


# --------------------------------------------------------------------- degenerate completions

def test_a_completion_on_the_first_line_compiles_without_inventing_a_board():
    """No board exists before line 1. The compiler must leave the field out rather than reach
    for the completing step's own grid — the one board it is specifically forbidden."""
    abstract = D.compile_digest(
        _packet([(0, {}, _grid(15), 1), (1, {}, _grid(5), 1)]))["observed_completions"][0]
    assert abstract["degenerate"] is True
    assert "pre_terminal_inventory" not in abstract
    assert "final_transition" not in abstract
    assert _colours_named(abstract) == set()


def test_a_degenerate_completion_renders_without_crashing():
    """Rendering reaches for the optional keys, and the degenerate abstract has none of them."""
    text = D.render_digest(D.compile_digest(
        _packet([(0, {}, _grid(15), 1), (1, {}, _grid(5), 1)])))
    assert "COMPLETED level 1 with RESET" in text
    assert "board immediately before the completing action" not in text


def test_a_level_completed_in_one_action_carries_no_final_transition():
    """Back-to-back completions: level 2's window is a single step, so there is no pair of
    within-level boards to difference. The pre-terminal board still exists — it is level 2's
    initial board — and is reported; the transition is absent rather than faked."""
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 1), (2, {}, _grid(8), 2)]
    abstracts = D.compile_digest(_packet(rows))["observed_completions"]
    assert [a["level_completed"] for a in abstracts] == [1, 2]
    assert abstracts[1]["degenerate"] is False
    assert abstracts[1]["level_length_actions"] == 1
    assert abstracts[1]["distinct_actions_in_level"] == []
    assert set(abstracts[1]["pre_terminal_inventory"]["by_color"]) == {C_MID}
    assert "final_transition" not in abstracts[1]


def test_a_level_after_a_completion_differences_against_its_own_initial_board():
    """Level 2's window here is the single step 3, but the board before that step exists — it is
    step 2's own grid, which IS level 2's initial board. Chaining from it is what lets a short
    level report the change that actually preceded its completing action instead of a
    final-transition size of zero, which would be a claim about the game rather than a gap in
    the window."""
    rows = [(0, {}, _grid(0), 0),      # 1  RESET -> C_OPEN
            (1, {}, _grid(5), 1),      # 2  UP    -> C_MID   completes level 1; level 2's board
            (2, {}, _grid(8), 1),      # 3  DOWN  -> C_PRE
            (3, {}, _grid(15), 2)]     # 4  LEFT  -> C_POST  completes level 2
    second = D.compile_digest(_packet(rows))["observed_completions"][1]
    assert second["level_completed"] == 2
    assert set(second["pre_terminal_inventory"]["by_color"]) == {C_PRE}
    assert second["final_transition"]["color_transitions"] == {f"{C_MID}->{C_PRE}": 9}


def test_a_level_of_exactly_two_actions_is_where_the_final_transition_appears():
    """The boundary the test above sits one short of. Two within-level steps are the fewest
    that can be differenced, so this is the first level length that carries the transition —
    and requiring three would silently drop it from every short level."""
    rows = [(0, {}, _grid(0), 0),     # 1  RESET -> C_OPEN
            (1, {}, _grid(5), 0),     # 2  UP    -> C_MID, the pre-terminal board
            (2, {}, _grid(15), 1)]    # 3  DOWN  completes level 1
    abstract = D.compile_digest(_packet(rows))["observed_completions"][0]
    assert set(abstract["pre_terminal_inventory"]["by_color"]) == {C_MID}
    assert abstract["final_transition"]["color_transitions"] == {f"{C_OPEN}->{C_MID}": 9}


# ---------------------------------------------------------------------- no-change bookkeeping

def test_a_no_change_action_is_counted_and_rendered_as_no_visible_change():
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 0), (2, {}, _grid(5), 0)]
    digest = D.compile_digest(_packet(rows))
    assert digest["current_level_recent_deltas"][-1] == {
        "changed_cells": 0, "after_action": "DOWN"}
    assert digest["no_change_actions_this_level"] == 1
    assert "after DOWN: no visible change" in D.render_digest(digest)


def test_no_change_actions_are_counted_over_the_whole_level_not_the_shown_window():
    """Only the last six deltas are shown, but the count is the level's. Taking it from the
    truncated list would understate exactly the symptom S1 was stuck on — an agent repeating
    an action that does nothing."""
    rows = [(0, {}, _grid(5), 0)] + [(1, {}, _grid(5), 0) for _ in range(9)]
    digest = D.compile_digest(_packet(rows))
    assert digest["actions_this_level"] == 10
    assert len(digest["current_level_recent_deltas"]) == 6
    assert digest["no_change_actions_this_level"] == 9


def test_the_first_action_of_a_level_after_a_completion_gets_its_own_delta():
    """The two counters on the rendered line have to share a denominator. The delta chain is
    seeded with the completing step's own grid — the new level's initial board — so a level of
    N actions yields N deltas. Step 3 below changes nothing, and must be counted: without the
    seed it went unobserved and the line read "2 action(s), 0 changed nothing"."""
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 1),
            (2, {}, _grid(5), 1), (3, {}, _grid(8), 1)]
    digest = D.compile_digest(_packet(rows))
    assert digest["actions_this_level"] == 2
    assert len(digest["current_level_recent_deltas"]) == 2
    assert digest["no_change_actions_this_level"] == 1


def test_the_opening_action_of_the_session_legitimately_has_no_predecessor_board():
    """Control for the test above: before the first completion there genuinely is no earlier
    board, so N actions yielding N-1 deltas is correct there."""
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 0), (2, {}, _grid(8), 0)]
    digest = D.compile_digest(_packet(rows))
    assert digest["actions_this_level"] == 3
    assert len(digest["current_level_recent_deltas"]) == 2


# ------------------------------------------------------------- E3 completion-content ablation

def test_the_ablation_removes_the_terminal_abstracts_and_changes_nothing_else():
    """E3's contrast is interpretable only if the two arms differ in one thing. Anything else
    that moved would be an undeclared second treatment."""
    packet = _packet(_ONE_COMPLETION)
    full = D.compile_digest(packet)
    ablated = D.compile_digest(packet, ablate_completions=True)
    assert "observed_completions" in full
    assert "observed_completions" not in ablated
    assert ablated == {k: v for k, v in full.items() if k != "observed_completions"}


def test_the_ablation_removes_the_pre_terminal_board_the_completing_action_and_the_trail():
    """The three pieces of terminal-packet CONTENT named in E3, checked in the rendered text
    the model actually receives and not only in the dict."""
    packet = _packet(_ONE_COMPLETION)
    ablated = D.compile_digest(packet, ablate_completions=True)
    text = D.render_digest(ablated)
    assert "COMPLETED" not in text
    assert "UNDO" not in text                      # the completing action
    assert "board immediately before" not in text  # the pre-terminal board
    assert "last change before" not in text        # the deltas leading into it
    assert {C_OPEN, C_MID, C_PRE} & _colours_named(ablated) == set()


def test_the_ablation_leaves_the_levels_completed_increment_intact_on_the_packet():
    """The increment is free platform metadata in every deployment regime, so E3 hides terminal
    CONTENT and not the fact of the completion. The ablation is a digest-level choice: layer 2
    still renders the counter off this same packet."""
    packet = _packet(_ONE_COMPLETION)
    D.compile_digest(packet, ablate_completions=True)
    assert [c.increment for c in packet.completions] == [1]
    assert [c.level for c in packet.completions] == [1]
    assert packet.steps[-1].levels_completed == 1


def test_the_ablated_digest_still_starts_the_level_window_at_the_completion():
    """The increment staying visible, expressed inside the digest itself: the ablated arm still
    knows a level ended at step 4, so its current-level bookkeeping restarts there. An ablation
    that also hid the boundary would be hiding the completion count."""
    ablated = D.compile_digest(_packet(_ONE_COMPLETION), ablate_completions=True)
    assert ablated["actions_this_level"] == 2       # steps 5 and 6, not all six steps
    assert [d["after_action"] for d in ablated["current_level_recent_deltas"]] == ["LEFT", "LEFT"]


def test_the_ablation_does_not_mutate_the_packet_it_was_given():
    """Both arms are compiled from the same packet in E3; a mutating ablation would make the
    result depend on the order the arms were run in."""
    packet = _packet(_ONE_COMPLETION)
    before = copy.deepcopy((packet.steps, packet.completions))
    D.compile_digest(packet, ablate_completions=True)
    D.compile_digest(packet)
    assert (packet.steps, packet.completions) == before


def test_a_zero_completion_packet_has_an_empty_abstract_list_and_nothing_to_ablate():
    """The key is present-but-empty before the first completion rather than absent, so the two
    E3 arms carry identical evidence at the zero-completion rows of the ladder."""
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 0), (2, {}, _grid(8), 0)]
    packet = _packet(rows)
    full = D.compile_digest(packet)
    ablated = D.compile_digest(packet, ablate_completions=True)
    assert full["observed_completions"] == []
    assert ablated == {k: v for k, v in full.items() if k != "observed_completions"}


def test_every_observed_completion_is_compiled_not_only_the_latest():
    """The ladder reads 1 -> 2 -> 3 completions, so a packet at completion:2 has to carry both
    abstracts; keeping only the most recent would flatten the slope E3 measures."""
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 1),
            (2, {}, _grid(8), 1), (3, {}, _grid(4), 2)]
    digest = D.compile_digest(_packet(rows))
    assert [a["level_completed"] for a in digest["observed_completions"]] == [1, 2]
    assert "observed_completions" not in D.compile_digest(
        _packet(rows), ablate_completions=True)


# ---------------------------------------------------------------------- the derivability rule

def test_the_digest_names_no_colour_that_is_absent_from_the_packet_grids():
    """Containment, the direct reading of "no information beyond the canonical packet": every
    colour the digest talks about must be one that occurs on a board it was handed."""
    packet = _packet(_ONE_COMPLETION)
    in_packet = {_CH[v] for s in packet.steps for row in s.settled for v in row}
    assert _colours_named(D.compile_digest(packet)) <= in_packet


def test_the_digest_depends_on_the_prefix_and_on_nothing_after_the_checkpoint():
    """The property the packet layer guarantees, restated one layer up: the compiler must read
    `packet.steps`/`packet.completions` and never the session they were cut from."""
    truncated = _packet(_ONE_COMPLETION[:3])
    with_a_future = _packet(_ONE_COMPLETION, checkpoint=3)
    assert D.compile_digest(truncated) == D.compile_digest(with_a_future)


def test_compiling_the_same_packet_twice_gives_the_same_digest():
    """Set iteration inside `inventory` is the obvious place for ordering to leak in, and a
    digest that differed run to run would surface as condition variance in E1."""
    packet = _packet(_ONE_COMPLETION)
    assert D.compile_digest(packet) == D.compile_digest(packet)
    assert D.render_digest(D.compile_digest(packet)) == D.render_digest(
        D.compile_digest(packet))


def test_the_digest_is_json_serialisable_with_no_internal_hash_set_leaking():
    """`inventory` carries a `_hashes` set for cross-frame object tracking. It is an
    implementation detail, it is not JSON-serialisable, and every place it surfaces has to strip
    it or the logged record of the condition cannot be written at all."""
    digest = D.compile_digest(_packet(_ONE_COMPLETION))
    assert json.loads(json.dumps(digest)) == digest
    assert "_hashes" not in digest["current_inventory"]
    assert "_hashes" not in digest["observed_completions"][0]["pre_terminal_inventory"]


def test_current_inventory_pixel_totals_equal_a_direct_recount_of_the_checkpoint_board():
    packet = _packet(_ONE_COMPLETION)
    counted: dict = {}
    for row in packet.steps[-1].settled:
        for v in row:
            counted[_CH[v]] = counted.get(_CH[v], 0) + 1
    by_color = D.compile_digest(packet)["current_inventory"]["by_color"]
    assert {c: v["pixels"] for c, v in by_color.items()} == counted


# ------------------------------------------------------------------------------ rendered text

def test_the_rendered_digest_is_a_decision_summary_not_a_board_dump():
    """Layer 3 changes representation; smuggling the grid back in as text would make (c)/(d) a
    different evidence set to (a)/(b) rather than a different view of the same one."""
    rows = [(0, {}, _grid(6, n=8), 0), (1, {}, _grid(4, n=8), 0)]
    text = D.render_digest(D.compile_digest(_packet(rows)))
    assert _CH[6] * 8 not in text
    assert _CH[4] * 8 not in text


def test_rendering_tolerates_a_digest_with_no_completions_at_all():
    rows = [(0, {}, _grid(0), 0), (1, {}, _grid(5), 0)]
    text = D.render_digest(D.compile_digest(_packet(rows)))
    assert text.startswith("Compiled evidence digest")
    assert "COMPLETED" not in text


def test_the_rendered_completion_line_names_the_level_and_the_completing_action():
    text = D.render_digest(D.compile_digest(_packet(_ONE_COMPLETION)))
    assert "COMPLETED level 1 with UNDO after 4 action(s)" in text
    assert "board immediately before the completing action" in text
    assert "last change before the completing action" in text


# --------------------------------------------------------------------------- corpus integration

@pytest.fixture(scope="module")
def ls20_timeline():
    """One real iteration-game session. ls20 is in the iteration slice so reading it taints
    nothing, and select_sessions refuses reserved games on its own."""
    if not CORPUS_PRESENT:
        pytest.skip("replay corpus not present (mutation sandbox / no mirror)")
    return P.load_timeline("ls20", P.select_sessions("ls20")[0]["guid"])


@requires_corpus
def test_a_real_completion_packet_compiles_to_a_serialisable_digest(ls20_timeline):
    step = P.checkpoints(ls20_timeline)["completion:1"]
    digest = D.compile_digest(P.extract(ls20_timeline, "completion:1", step))
    assert json.loads(json.dumps(digest)) == digest
    assert digest["observed_completions"], "a completion:1 packet must carry its completion"


@requires_corpus
def test_a_real_terminal_abstract_uses_the_step_before_the_completing_action(ls20_timeline):
    """The same invariant on real 64x64 boards: the reported pre-terminal inventory is the
    inventory of step t-1's board, and not of the completing step's own board."""
    step = P.checkpoints(ls20_timeline)["completion:1"]
    packet = P.extract(ls20_timeline, "completion:1", step)
    abstract = D.compile_digest(packet)["observed_completions"][0]
    expected = D.inventory(packet.steps[step - 2].settled)
    expected.pop("_hashes")
    post_terminal = D.inventory(packet.steps[step - 1].settled)
    post_terminal.pop("_hashes")
    assert abstract["pre_terminal_inventory"] == expected
    assert abstract["pre_terminal_inventory"] != post_terminal


@requires_corpus
def test_real_pixel_totals_equal_a_direct_recount(ls20_timeline):
    packet = P.extract(ls20_timeline, "offset:10", 10)
    counted: dict = {}
    for row in packet.steps[-1].settled:
        for v in row:
            counted[_CH[v]] = counted.get(_CH[v], 0) + 1
    by_color = D.compile_digest(packet)["current_inventory"]["by_color"]
    assert {c: v["pixels"] for c, v in by_color.items()} == counted


@requires_corpus
def test_the_ablation_is_contained_on_a_real_completion_packet(ls20_timeline):
    step = P.checkpoints(ls20_timeline)["completion:1"]
    packet = P.extract(ls20_timeline, "completion:1", step)
    full = D.compile_digest(packet)
    ablated = D.compile_digest(packet, ablate_completions=True)
    assert ablated == {k: v for k, v in full.items() if k != "observed_completions"}
    assert "COMPLETED" not in D.render_digest(ablated)
    assert [c.increment for c in packet.completions] == [1]


@requires_corpus
def test_a_real_rendered_digest_stays_inside_the_prompt_budget(ls20_timeline):
    """8000 characters is the bound the module's own selftest asserts; a real 64x64 board with
    a full object inventory is the case that could breach it."""
    step = P.checkpoints(ls20_timeline)["completion:1"]
    text = D.render_digest(D.compile_digest(P.extract(ls20_timeline, "completion:1", step)))
    assert 0 < len(text) < 8000
