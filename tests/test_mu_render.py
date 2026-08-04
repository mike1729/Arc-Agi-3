"""MU rendering regressions. Every test names the defect it pins."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "harness"))
import mu_probes as M  # noqa: E402
import mu_render as R  # noqa: E402

INVENTORY = ROOT / "logs/mu_inventory.json"


@pytest.fixture(scope="module")
def inventory() -> dict:
    if not INVENTORY.exists():
        pytest.skip("logs/mu_inventory.json has not been built")
    return json.loads(INVENTORY.read_text())


@pytest.fixture(scope="module")
def index(inventory):
    import mu_screen

    return mu_screen.CaseIndex(inventory)


def one_case(inventory: dict, probe: str) -> dict:
    return next(case for case in inventory["cases"] if case["probe"] == probe)


def rendered(index, case: dict) -> dict[str, str]:
    window = index.window(case)
    return {
        arm: R.render_case(arm, case, window)[0][0]["content"] for arm in R.ARMS
    }


# ------------------------------------------------------------------ frozen mirrors


def test_cell_characters_mirror_the_vendored_reference_renderer():
    # MU must print exactly the characters GI-1 and the live harness printed; a private
    # table would make every MU grid a different stimulus from the measured ones.
    from gi1_render import format_grid_ascii

    assert format_grid_ascii([list(range(16))]) == R.ARC_COLOR_CHARS


# ------------------------------------------------------------------ matched information


def test_question_and_schema_are_byte_identical_across_all_seven_arms(inventory, index):
    for probe in M.PROBES:
        case = one_case(inventory, probe)
        window = index.window(case)
        question = {R.question_block(case)}
        schema = {R.schema_block(case)}
        fingerprints = {
            R.render_case(arm, case, window)[1]["question_sha256"] for arm in R.ARMS
        }
        assert len(question) == len(schema) == len(fingerprints) == 1, probe


def test_arms_are_payload_inclusive_so_their_cost_order_is_entailed(inventory, index):
    # grid < objects < events < card by strict inclusion (the ES arm_cost_order argument):
    # each adds tables to the identical base, so a cost tie is impossible.
    case = one_case(inventory, "T1")
    window = index.window(case)
    base = R.cell_evidence(window, canvas=False)
    text = {arm: R.representation(arm, case, window) for arm in ("grid", "objects", "events", "card")}
    for block in base:
        for arm in text:
            assert block in text[arm], arm
    for smaller, larger in (("grid", "objects"), ("objects", "events"), ("events", "card")):
        assert len(text[smaller]) < len(text[larger])


# ------------------------------------------------------------------ withholding


def test_identity_probe_withholds_the_lineage_table_that_would_be_its_answer(inventory, index):
    case = one_case(inventory, "T2")
    window = index.window(case)
    last = len(window.states) - 1
    for arm, text in rendered(index, case).items():
        assert f"identity (S{last - 1} -> S{last})" not in text, arm


def test_identity_probe_relabels_the_query_state_and_hides_its_aliases(inventory, index):
    case = one_case(inventory, "T2")
    window = index.window(case)
    aliases = {item.alias for item in window.query.objects}
    last = len(window.states) - 1
    markers = {
        "objects": f"S{last} objects",
        "events": f"S{last} objects",
        "card": f"S{last} objects",
        "verbal": f"S{last} (the current state) contains",
    }
    for arm, marker in markers.items():
        text = R.representation(arm, case, window)
        table = text.split(marker)[-1].split("\n\n")[0]
        assert "B1 " in table or "B1 is" in table, arm
        assert not any(f"\n{alias} " in table for alias in aliases), arm
        assert not any(f"\n{alias} is" in table for alias in aliases), arm


def test_identity_probe_still_shows_the_cell_evidence_of_the_queried_transition(inventory, index):
    case = one_case(inventory, "T2")
    window = index.window(case)
    last = len(window.states) - 1
    for arm in ("grid", "film", "objects"):
        assert f"S{last - 1} -> S{last}" in R.representation(arm, case, window), arm


# ------------------------------------------------------------------ exactness


def test_delta_encoding_is_exact_and_takes_whichever_form_is_shorter():
    before = [[0] * 64 for _ in range(64)]
    after = [row[:] for row in before]
    after[3][4] = 9
    small = R.format_delta(before, after)
    assert small.startswith("changed cells: 1") and "(3,4) W->b" in small
    assert "\n  0 " not in small                    # no full board for a one-cell delta
    everything = [[9] * 64 for _ in range(64)]
    large = R.format_delta(before, everything)
    assert "the full board after the action is" in large
    assert len(large) < len("  ".join(["(00,00) W->b"] * 4096))


def test_delta_reports_a_no_op_instead_of_an_empty_list():
    grid = [[0] * 64 for _ in range(64)]
    assert R.format_delta(grid, grid) == "changed cells: 0 (the board is identical)"


def test_film_canvas_marks_unchanged_cells_and_keeps_the_changed_value():
    before = [[0] * 64 for _ in range(64)]
    after = [row[:] for row in before]
    after[1][2] = 8
    canvas = R.format_delta_canvas(before, after).splitlines()
    assert canvas[1 + 2][4 + 2] == "R"              # two ruler lines, four index columns
    assert canvas[1 + 2].count(R.UNCHANGED_CHAR) == 63


# ------------------------------------------------------------------ the map arm


def test_map_lattice_downsamples_by_the_frozen_factor_and_breaks_ties_by_size():
    from gi2_observation import Tracker

    grid = [[0] * 64 for _ in range(64)]
    for row in range(4):
        for col in range(4):
            grid[row][col] = 9                      # a 16-cell blue block in lattice (0,0)
    grid[8][8] = 8                                  # a single red cell in lattice (2,2)
    observation = Tracker().update(grid, previous_grid=None, action_id=1, action_data={})
    rows = R.lattice(M.build_registry(observation)).splitlines()[2:]
    assert len(rows) == M.MAP_LATTICE
    assert rows[0][4] == "b"
    assert rows[2][4 + 2] == "R"


# ------------------------------------------------------------------ no gold in the prompt


def test_choice_probes_do_not_reveal_which_option_is_accepted(inventory, index):
    for probe in ("T4", "T5"):
        case = one_case(inventory, probe)
        for arm, text in rendered(index, case).items():
            for label in case["gold"]["accepting"]:
                assert f"{label} =" in text          # offered like every other option
            assert "accepting" not in text, arm
            assert json.dumps(case["gold"]) not in text, arm


def test_no_arm_renders_a_state_beyond_the_shown_prefix(inventory, index):
    # The leak invariant in rendering terms: the representation may only name states inside
    # the window, so the queried outcome (T3's next state, T4/T5's fork results) cannot be
    # narrated. Counting occurrences of the queried ACTION cannot express this — an arm may
    # legitimately name one shown action several times, once per evidence table.
    for probe in ("T3", "T4", "T5"):
        case = one_case(inventory, probe)
        window = index.window(case)
        last = len(window.states) - 1
        for arm, text in rendered(index, case).items():
            representation_text = text.split("QUESTION")[0]
            for left, right in re.findall(r"S(\d+) -> S(\d+)", representation_text):
                assert int(right) <= last, (arm, probe, left, right)
            assert f"S{last + 1}" not in representation_text, (arm, probe)


def test_the_two_t3_forms_both_survive_the_frozen_cohort_split(inventory):
    # t3_executed_share is bound to the T3 case count: a share equal to the count would
    # leave zero fork-form cases and silently drop half of T3's design.
    forms = {case.get("form") for case in inventory["cases"] if case["probe"] == "T3"}
    assert forms == {"executed", "fork"}


def test_prompt_layout_is_preamble_representation_question_schema(inventory, index):
    case = one_case(inventory, "T1")
    window = index.window(case)
    for arm in R.ARMS:
        text = R.render_case(arm, case, window)[0][0]["content"]
        assert text.index("REPRESENTATION") < text.index("QUESTION") < text.index("ANSWER")
        assert text.startswith("You are given consecutive states")
