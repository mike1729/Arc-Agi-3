"""MU driver regressions: acceptance gating, planning, scoring. Each names its defect."""

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent" / "harness"))
import mu_probes as M  # noqa: E402
import mu_render as R  # noqa: E402
import mu_screen as S  # noqa: E402

INVENTORY = ROOT / "logs/mu_inventory.json"


@pytest.fixture(scope="module")
def inventory() -> dict:
    if not INVENTORY.exists():
        pytest.skip("logs/mu_inventory.json has not been built")
    return json.loads(INVENTORY.read_text())


# ------------------------------------------------------------------ acceptance gating


def test_freeze_refuses_while_the_manifest_block_is_still_draft():
    # The whole point of the DRAFT/PROPOSED vocabulary: no measured call may precede the
    # operator's acceptance, and the run path requires the freeze.
    block = S.manifest_block()
    if block.get("status") == "frozen":
        pytest.skip("the mu block has been accepted; this gate no longer applies")
    with pytest.raises(ValueError, match="not frozen"):
        S.build_freeze()


def test_every_applied_number_is_mirrored_from_the_manifest():
    assert S.check_mirrors(S.manifest_block()) == []


def test_a_manifest_drift_fails_closed_rather_than_being_ignored():
    block = copy.deepcopy(S.manifest_block())
    block["cases"]["t2_rows_max"] = 99
    problems = S.check_mirrors(block)
    assert any("t2_rows_max" in problem for problem in problems)


def test_the_measurement_model_is_the_only_one_a_run_accepts(inventory):
    with pytest.raises(ValueError, match="measurement model"):
        S.run_rows(
            [], document=inventory, model="/models/" + S.DEV_MODEL_BASENAME,
            base_url="http://127.0.0.1:1", timeout=1, concurrency=1,
        )


# ------------------------------------------------------------------ planning


def test_s_pass_is_the_full_factorial_and_c_runs_t1_for_every_unique_selected_arm(inventory):
    s_rows = S.plan_rows(inventory, role="S", arms=None)
    s_cases = {case["case_id"] for case in inventory["cases"] if case["role"] == "S"}
    assert len(s_rows) == len(s_cases) * len(R.ARMS)
    assert {row["arm"] for row in s_rows} == set(R.ARMS)

    # Selection covers T2-T5 only; T1 on C must run for EVERY unique selected arm, so a
    # T2-T5 winner cannot escape a C legibility measurement (review finding 3).
    selected = {"T2": "map", "T3": "events", "T4": "events", "T5": "grid"}
    c_rows = S.plan_rows(inventory, role="C", arms=selected)
    c_cases = [case for case in inventory["cases"] if case["role"] == "C"]
    t1_cases = [case for case in c_cases if case["probe"] == "T1"]
    assert len(c_rows) == (len(c_cases) - len(t1_cases)) + len(t1_cases) * 3
    assert {row["arm"] for row in c_rows if row["probe"] == "T1"} == {"map", "events", "grid"}
    for probe, arm in selected.items():
        assert {row["arm"] for row in c_rows if row["probe"] == probe} == {arm}
    assert len({row["row_id"] for row in c_rows}) == len(c_rows)


def test_a_no_legible_arm_probe_contributes_no_c_rows(inventory):
    selected = {"T3": "events"}          # T2/T4/T5 read no_legible_arm -> absent
    c_rows = S.plan_rows(inventory, role="C", arms=selected)
    assert {row["probe"] for row in c_rows} == {"T1", "T3"}
    assert {row["arm"] for row in c_rows} == {"events"}


def test_planned_call_budget_prices_the_worst_case_c_pass(inventory):
    budget = inventory["call_budget"]
    assert budget["s_pass_calls"] == len(S.plan_rows(inventory, role="S", arms=None))
    assert budget["c_pass_calls_worst"] == (
        budget["c_pass_calls_selected_arms"] + budget["c_t1_confirm_calls_worst"]
    )
    assert budget["planned_calls_worst"] == (
        budget["s_pass_calls"] + budget["c_pass_calls_worst"]
    )
    assert budget["call_ceiling"] > budget["planned_calls_worst"]


# ------------------------------------------------------------------ the run path, model-free


def test_the_run_path_renders_parses_and_scores_without_a_model(inventory):
    # Drives _execute with a stubbed transport that answers with the case's own floor, so
    # rendering, guided-schema construction, parsing, and scoring are exercised offline.
    index = S.CaseIndex(inventory)
    case = next(case for case in inventory["cases"] if case["probe"] == "T3")

    def stub(base_url, payload, timeout):
        assert payload["response_format"]["json_schema"]["schema"] == M.output_schema(case)
        assert payload["temperature"] == 0
        answer = json.dumps(case["floor_answer"])
        return {"choices": [{"message": {"content": answer}}], "usage": {}}, 0.0

    record = S._execute(
        {"row_id": "r", "case_id": case["case_id"], "probe": "T3", "env": case["env"],
         "role": case["role"], "arm": "events"},
        case=case, index=index, model="x", base_url="", timeout=1,
        freeze_fingerprint="f", chat=stub,
    )
    assert record["parse_valid"] is True
    assert record["score"]["rate"] == case["floor"]["rate"]
    assert record["packet_meta"]["arm"] == "events"


def test_a_refused_response_is_scored_zero_and_kept(inventory):
    index = S.CaseIndex(inventory)
    case = next(case for case in inventory["cases"] if case["probe"] == "T1")

    def stub(base_url, payload, timeout):
        return {"choices": [{"message": {"content": "I cannot tell."}}], "usage": {}}, 0.0

    record = S._execute(
        {"row_id": "r", "case_id": case["case_id"], "probe": "T1", "env": case["env"],
         "role": case["role"], "arm": "map"},
        case=case, index=index, model="x", base_url="", timeout=1,
        freeze_fingerprint="f", chat=stub,
    )
    assert record["parse_valid"] is False and record["score"]["rate"] == 0.0
    assert record["status"] == "complete"          # it stays in the denominator


# ------------------------------------------------------------------ aggregation


def test_game_macro_weights_games_equally_not_cases():
    rows = [{"env": "a", "v": 1.0}] + [{"env": "b", "v": 0.0} for _ in range(9)]
    assert S.game_macro(rows, lambda row: row["v"]) == 0.5


def _t1(**macros):
    return {
        arm: {"game_macro": macro, "median_prompt_tokens": 1000}
        for arm, macro in macros.items()
    }


def test_selection_prefers_the_cheaper_arm_inside_the_margin():
    profile = {
        "T1": _t1(events=0.95, grid=0.92, map=0.90),
        "T3": {
            "events": {"game_macro": 0.80, "median_prompt_tokens": 12000},
            "grid": {"game_macro": 0.78, "median_prompt_tokens": 6000},
            "map": {"game_macro": 0.40, "median_prompt_tokens": 1400},
        },
    }
    selection = S.select_profile(profile)
    assert selection["T3"]["status"] == "selected"
    assert selection["T3"]["arm"] == "grid"
    assert selection["T3"]["best_game_macro"] == 0.80
    assert set(selection["T3"]["within_margin"]) == {"events", "grid"}
    assert "T1" not in selection          # T1 is a gate, never a selected cell


def test_an_arm_below_the_t1_gate_is_reported_but_flagged_uninterpretable():
    # §2: a low T2-T5 rate under a failed T1 is an illegibility result, not a reasoning one.
    profile = {"T1": _t1(grid=0.91, map=0.20)}
    flags = S.legibility(profile)
    assert flags["grid"]["legible"] is True
    assert flags["map"]["legible"] is False
    # Three-state (review finding 3): no T1 rows means UNMEASURED, never illegible.
    assert flags["film"]["t1_game_macro"] is None and flags["film"]["legible"] is None


def test_selection_keeps_the_leader_when_the_gap_exceeds_the_margin():
    profile = {
        "T1": _t1(events=0.95, grid=0.92),
        "T3": {
            "events": {"game_macro": 0.80, "median_prompt_tokens": 12000},
            "grid": {"game_macro": 0.60, "median_prompt_tokens": 6000},
        },
    }
    assert S.select_profile(profile)["T3"]["arm"] == "events"


def test_selection_excludes_arms_that_fail_the_t1_gate_on_s():
    # Review finding 3: the best T4 rate sits on an S-illegible arm; it must not win, and
    # it must not even count as a contender.
    profile = {
        "T1": _t1(map=0.20, grid=0.91),
        "T4": {
            "map": {"game_macro": 0.95, "median_prompt_tokens": 1400},
            "grid": {"game_macro": 0.60, "median_prompt_tokens": 6000},
        },
    }
    selection = S.select_profile(profile)
    assert selection["T4"]["arm"] == "grid"
    assert "map" not in selection["T4"]["within_margin"]


def test_selection_records_no_legible_arm_rather_than_selecting_an_illegible_one():
    profile = {
        "T1": _t1(map=0.10),
        "T5": {"map": {"game_macro": 0.99, "median_prompt_tokens": 1400}},
    }
    selection = S.select_profile(profile)
    assert selection["T5"] == {"status": "no_legible_arm", "s_legible_arms": []}


# ------------------------------------------------------------------ screen-positive


def _c_records(probe, arm, rate_by_game):
    return [
        {"probe": probe, "arm": arm, "role": "C", "env": env, "score": {"rate": rate}}
        for env, rate in rate_by_game.items()
    ]


def _floor_cases(rate_by_game):
    return [{"env": env, "floor": {"rate": rate}} for env, rate in rate_by_game.items()]


GAMES = ("dc22", "ft09", "ls20", "m0r0", "tu93", "vc33")


def test_screen_positive_requires_the_arms_own_measured_t1_on_c():
    # Review finding 3: capability must never be labelled while C legibility is unmeasured.
    verdict = S.screen_positive_verdict(
        probe="T3", arm="events",
        c_records=_c_records("T3", "events", {env: 1.0 for env in GAMES}),
        floor_cases=_floor_cases({env: 0.0 for env in GAMES}),
        c_legibility={"events": {"legible": None, "t1_game_macro": None}},
    )
    assert verdict["status"] == "t1_unmeasured_on_C"
    assert "screen_positive" not in verdict


def test_an_arm_illegible_on_c_can_never_be_screen_positive():
    verdict = S.screen_positive_verdict(
        probe="T3", arm="events",
        c_records=_c_records("T3", "events", {env: 1.0 for env in GAMES}),
        floor_cases=_floor_cases({env: 0.0 for env in GAMES}),
        c_legibility={"events": {"legible": False, "t1_game_macro": 0.3}},
    )
    assert verdict["status"] == "arm_illegible_on_C"


def test_a_one_game_spike_cannot_carry_the_screen_positive_verdict():
    # Review finding 4: with ~18 C cases a single game can clear the macro margin alone;
    # the per-game consistency requirement kills exactly that.
    rates = {env: 0.0 for env in GAMES} | {"dc22": 1.0}
    verdict = S.screen_positive_verdict(
        probe="T4", arm="grid",
        c_records=_c_records("T4", "grid", rates),
        floor_cases=_floor_cases({env: 0.0 for env in GAMES}),
        c_legibility={"grid": {"legible": True, "t1_game_macro": 1.0}},
    )
    assert verdict["status"] == "confirmed"
    assert verdict["margin"] >= S.SCREEN_POSITIVE_MARGIN
    assert verdict["games_beating_floor"] == 1
    assert verdict["screen_positive"] is False


def test_screen_positive_passes_with_margin_and_per_game_consistency():
    verdict = S.screen_positive_verdict(
        probe="T4", arm="grid",
        c_records=_c_records("T4", "grid", {env: 0.8 for env in GAMES}),
        floor_cases=_floor_cases({env: 0.5 for env in GAMES}),
        c_legibility={"grid": {"legible": True, "t1_game_macro": 1.0}},
    )
    assert verdict["screen_positive"] is True
    assert verdict["games_beating_floor"] == len(GAMES)


# ------------------------------------------------------------------ freeze gating


def test_the_freeze_refuses_without_the_bringup_artifact(monkeypatch, tmp_path):
    # Review finding 5: bring-up (latency + guided JSON) must GATE the freeze, not advise it.
    frozen = copy.deepcopy(S.manifest_block())
    frozen["status"] = "frozen"
    monkeypatch.setattr(S, "manifest_block", lambda: frozen)
    monkeypatch.setattr(S, "BRINGUP", tmp_path / "absent.json")
    with pytest.raises(ValueError, match="bring-up"):
        S.build_freeze()


def test_the_freeze_refuses_until_the_manifest_accepts_the_measured_bringup(monkeypatch, tmp_path):
    frozen = copy.deepcopy(S.manifest_block())
    frozen["status"] = "frozen"
    bringup = tmp_path / "mu_bringup.json"
    bringup.write_text(json.dumps({
        "guided_json_validated": True, "p50_s": 200.0, "p95_s": 260.0,
        "max_prompt_tokens": 24700,
    }))
    monkeypatch.setattr(S, "manifest_block", lambda: frozen)
    monkeypatch.setattr(S, "BRINGUP", bringup)
    with pytest.raises(ValueError, match="bringup.measured"):
        S.build_freeze()                  # measured numbers not accepted into the block


def test_the_freeze_refuses_an_unvalidated_guided_json_stack(monkeypatch, tmp_path):
    frozen = copy.deepcopy(S.manifest_block())
    frozen["status"] = "frozen"
    bringup = tmp_path / "mu_bringup.json"
    bringup.write_text(json.dumps({"guided_json_validated": False}))
    monkeypatch.setattr(S, "manifest_block", lambda: frozen)
    monkeypatch.setattr(S, "BRINGUP", bringup)
    with pytest.raises(ValueError, match="guided-JSON"):
        S.build_freeze()


# ------------------------------------------------------------------ the decision contract


def _selected(*probes):
    return {probe: {"status": "selected", "arm": "events"} for probe in probes}


def test_no_legible_arm_anywhere_on_s_routes_straight_to_stop():
    # §5.1 first stop condition: the menu is exhausted before any C call is worth making.
    selection = {probe: {"status": "no_legible_arm"} for probe in S.SELECTABLE_PROBES}
    decision = S.decision_verdict(selection, {}, s_complete=True, c_complete=False)
    assert decision["verdict"] == "stop"
    assert "T1 legibility gate on S" in decision["reason"]


def test_a_funding_cell_that_is_screen_positive_on_c_routes_to_continue():
    decision = S.decision_verdict(
        _selected("T3", "T4", "T5"),
        {"T3": {"screen_positive": True}, "T4": {"screen_positive": False},
         "T5": {"screen_positive": True}},
        s_complete=True, c_complete=True,
    )
    assert decision["verdict"] == "continue"
    assert decision["screen_positive_funding_cells"] == ["T3"]


def test_t5_alone_cannot_fund_the_continuation():
    # §5.1: T5 is terminal-action discrimination at a REVEALED pre-terminal state, so it
    # informs the continuation design but is not a funding probe.
    decision = S.decision_verdict(
        _selected("T3", "T4", "T5"),
        {"T3": {"screen_positive": False}, "T4": {"screen_positive": False},
         "T5": {"screen_positive": True}},
        s_complete=True, c_complete=True,
    )
    assert decision["verdict"] == "stop"
    assert decision["screen_positive_funding_cells"] == []


def test_an_unfinished_pass_is_pending_not_a_stop():
    # An incomplete pass is not evidence of absence; routing a stop off one would repeat
    # the error the complete-S-pass rule already forbids for selection.
    for s_done, c_done in ((True, False), (False, False)):
        decision = S.decision_verdict(
            _selected("T3"), {"T3": {"screen_positive": True}},
            s_complete=s_done, c_complete=c_done,
        )
        assert decision["verdict"] == "pending", (s_done, c_done)


def test_an_illegible_or_unmeasured_c_arm_can_never_be_screen_positive():
    for status in ("arm_illegible_on_C", "t1_unmeasured_on_C", "not_confirmed"):
        decision = S.decision_verdict(
            _selected("T3", "T4"), {"T3": {"status": status}, "T4": {"status": status}},
            s_complete=True, c_complete=True,
        )
        assert decision["verdict"] == "stop"


def test_adopt_is_never_a_reachable_verdict():
    # §5.1: adoption needs a separate exact-stack protocol plus the register + SPEC route.
    verdicts = set()
    for positive in (True, False):
        for s_done in (True, False):
            for c_done in (True, False):
                verdicts.add(
                    S.decision_verdict(
                        _selected("T3"), {"T3": {"screen_positive": positive}},
                        s_complete=s_done, c_complete=c_done,
                    )["verdict"]
                )
    assert verdicts <= {"stop", "continue", "pending"}


def test_the_results_document_ties_its_verdict_to_the_completeness_flags():
    # This test once asserted `s_pass_complete is False`, which pinned the moment before any
    # measured call rather than a rule, and broke the day the pass finished. What must hold
    # at every point in the measurement is the RELATIONSHIP: `pending` exactly while a pass
    # is unfinished, unless the S-side no-legible-arm short-circuit fires.
    document = S.build_results()
    verdict = document["decision"]["verdict"]
    assert verdict in {"stop", "continue", "pending"}
    assert isinstance(document["s_pass_complete"], bool)
    assert isinstance(document["c_pass_complete"], bool)
    both_done = document["s_pass_complete"] and document["c_pass_complete"]
    short_circuit = "T1 legibility gate on S" in document["decision"]["reason"]
    assert (verdict == "pending") == (not both_done and not short_circuit)
    if verdict == "continue":
        assert document["decision"]["screen_positive_funding_cells"]
    assert "adopt" not in {verdict}
