"""Direct tests for `gi1_retrieval` — GI-1 cross-game terminal retrieval (d/f) and the
programmatic floors (e/f).

WHY THIS FILE EXISTS. `gi1_retrieval.py --selftest` is real coverage but it checks the query
TYPE and never the query CONTENT. That gap matters more here than it would elsewhere: the
typed-query split exists because a review found one query shape mixing fields from different
levels, so the property that has to hold is the exact feature vector — a zero-completion
packet must not be ranked by a completing action, a level length, or a final-transition size
it never observed. A wrong vector still reports qtype "state", still returns k hits from k
distinct games, and still passes the selftest.

Three more behaviours have no assertions anywhere and each decides a reported number:

  - the ONE-NEIGHBOUR-PER-SOURCE-GAME cap, the fix for the measured collapse where 62 of 78
    queries returned all three neighbours from a single game. The selftest only checks that
    the returned envs are distinct — which is equally true when the cap is doing nothing
    because the pool happened to be diverse.
  - MIN-over-anchors aggregation. Mean, first-anchor and last-anchor aggregation all produce
    a well-formed "terminal" query over distinct games; only the ranking differs.
  - the vote ordering, prior backfill and leave-one-game-out arithmetic in (e)/(f), which
    produce the K2 attribution comparison with no model in the loop.

Two groups, split by what they need:

  - SYNTHETIC tests build index records as plain dicts and Packets directly, on 2x2 grids.
    They read no replay data, no `logs/` and no draw file — every module constant or helper
    that reaches the filesystem is monkeypatched — and they assert exact vectors and exact
    orderings rather than shapes.
  - CORPUS tests re-run the same invariants against the real mirror and skip when it is
    absent (mutation sandbox, or a checkout without the replay data).

Run:
  .venv/bin/python -m pytest tests/test_gi1_retrieval.py -q
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[1] / "agent" / "harness"
sys.path.insert(0, str(HARNESS))

import gi1_packets as P        # noqa: E402
import gi1_retrieval as R      # noqa: E402

# Resolved at import, before any fixture monkeypatches R.REPO. build_index and
# _primary_classes read these two logs at CALL time, so a test that reaches either without a
# monkeypatch must be gated here rather than skipped from inside.
DRAW = R.REPO / "logs/gi1_game_draw.json"
LABELS = R.REPO / "logs/s2_goal_predicates_labelled.json"
CORPUS_PRESENT = (P.CORPUS.exists() and P.SESSIONS_TABLE.exists()
                  and DRAW.exists() and LABELS.exists())
requires_corpus = pytest.mark.skipif(
    not CORPUS_PRESENT, reason="replay corpus / GI-1 logs not present (mutation sandbox)")
requires_labels = pytest.mark.skipif(
    not LABELS.exists(), reason="labelled predicate file not present (mutation sandbox)")

TERMINAL_DIMS = 42          # 32 state + 8 action one-hot + level length + transition size


# --------------------------------------------------------------------------- synthetic fixtures

def _grid(rows: str) -> list:
    """A settled grid from hex digits, '01/10' -> [[0, 1], [1, 0]]. Nothing in the retrieval
    layer inspects grid size, so these stay 2x2; the 64x64 / 0..15 invariants belong to
    gi1_packets' selftest, against real recordings."""
    return [[int(ch, 16) for ch in row] for row in rows.split("/")]


def _step(index: int, settled: list, action_id: int = 1) -> P.Step:
    return P.Step(index=index, action_id=action_id, action_data={}, n_frames=1,
                  settled=settled, levels_completed=0, available_actions=[1, 2, 3],
                  state="NOT_FINISHED", full_reset=False)


def _completion(step_index: int, level: int, action_id: int, pre_terminal: list | None,
                level_start_index: int) -> P.Completion:
    return P.Completion(step_index=step_index, level=level, increment=1, action_id=action_id,
                        action_data={}, level_start_index=level_start_index,
                        pre_terminal_settled=pre_terminal, degenerate=pre_terminal is None)


def _packet(env: str, grids: list, completions=(), guid: str = "s1") -> P.Packet:
    steps = [_step(i + 1, g) for i, g in enumerate(grids)]
    return P.Packet(env=env, guid=guid, checkpoint_kind="synthetic",
                    checkpoint_step=len(steps), initial_settled=steps[0].settled,
                    initial_is_post_action=False, steps=steps,
                    completions=list(completions), available_actions=[1, 2, 3])


def _timeline(env: str, guid: str, grids: list, completions=()) -> P.Timeline:
    return P.Timeline(env=env, guid=guid, win_levels=3, initial_is_post_action=False,
                      steps=[_step(i + 1, g) for i, g in enumerate(grids)],
                      completions=list(completions))


_STUB_ABSTRACT = {"level_completed": 1, "completing_action": "SPACE",
                  "level_length_actions": 3, "distinct_actions_in_level": ["UP"],
                  "degenerate": False}


def _record(env: str, vector: list, guid: str = "s1", step: int = 1, level: int = 1) -> dict:
    """An index record in exactly the shape build_index emits — the key set is pinned against
    the real producer by test_build_index_emits_one_record_per_non_degenerate_completion."""
    return {"env": env, "guid": guid, "step": step, "level": level,
            "vector": list(vector), "abstract": dict(_STUB_ABSTRACT)}


def _expected_state(grid: list, objects_per_value: dict) -> list:
    """The documented state vector, recomputed without the module: 16 colour-pixel FRACTIONS
    then 16 log1p object counts. `objects_per_value` is the 4-connected component count per
    colour, stated by hand — these grids are small enough to count by eye."""
    px = [0.0] * 16
    for row in grid:
        for v in row:
            px[v] += 1.0
    total = sum(px)
    counts = [0.0] * 16
    for value, n in objects_per_value.items():
        counts[value] = float(n)
    return [p / total for p in px] + [math.log1p(c) for c in counts]


def _expected_terminal(grid: list, objects_per_value: dict, action_id: int,
                       level_length: int, changed_cells: int) -> list:
    act = [0.0] * 8
    act[action_id] = 1.0
    return (_expected_state(grid, objects_per_value) + act
            + [math.log1p(level_length), math.log1p(changed_cells)])


@pytest.fixture
def cosine_spy(monkeypatch):
    """Capture what `query` actually compares: (query vector, record side) per call. The
    record side is the slice the distance saw, so the pair pins both the query construction
    and which part of the record it was allowed to reach."""
    seen = []
    real = R._cosine

    def spy(a, b):
        seen.append((list(a), list(b)))
        return real(a, b)

    monkeypatch.setattr(R, "_cosine", spy)
    return seen


# --------------------------------------------------------------------------- feature vectors

def test_state_features_are_sixteen_pixel_fractions_then_sixteen_log1p_object_counts():
    """A 2x2 checkerboard: two W pixels and two w pixels, each pixel its own 4-connected
    component, so four objects split two-and-two."""
    vec = R._state_features(_grid("01/10"))
    assert len(vec) == R.STATE_DIMS == 32
    assert vec[:2] == pytest.approx([0.5, 0.5])          # fractions, not counts
    assert vec[2:16] == [0.0] * 14
    assert vec[16:18] == pytest.approx([math.log1p(2)] * 2)
    assert vec[18:] == [0.0] * 14
    assert vec == pytest.approx(_expected_state(_grid("01/10"), {0: 2, 1: 2}))


def test_terminal_features_append_the_action_one_hot_level_length_and_transition_size():
    vec = R._terminal_features(_grid("01/10"), 5, 3, 2)
    assert len(vec) == TERMINAL_DIMS
    assert vec[:32] == pytest.approx(R._state_features(_grid("01/10")))
    assert vec[32:40] == [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    assert vec[40:] == pytest.approx([math.log1p(3), math.log1p(2)])


@pytest.mark.parametrize("action_id", [8, 9, -1, 99])
def test_an_action_id_outside_the_one_hot_is_refused_not_folded(action_id):
    """Folding onto slot 0 made an out-of-range id indistinguishable from RESET in the vector —
    a corrupted distance with no symptom, which is precisely what would hide an ingest bug.
    ARC-AGI-3 advertises only 0..7, so anything else is a parse failure, not a value."""
    with pytest.raises(ValueError, match=r"outside the 0\.\.7 one-hot"):
        R._terminal_features(_grid("00/00"), action_id, 1, 0)


@pytest.mark.parametrize("action_id", [True, False, 1.0, 1.5, "1", None])
def test_a_non_integer_action_id_is_refused_not_coerced(action_id):
    """bool aliases integer slots in Python and integral floats can look harmless, but neither
    is a normalized packet action id. Reject every non-int before indexing the one-hot."""
    with pytest.raises(ValueError, match=r"not an integer in the 0\.\.7 one-hot"):
        R._terminal_features(_grid("00/00"), action_id, 1, 0)


@pytest.mark.parametrize("action_id", range(8))
def test_every_advertised_action_id_gets_its_own_one_hot_slot(action_id):
    vec = R._terminal_features(_grid("00/00"), action_id, 1, 0)
    assert vec[R.STATE_DIMS:R.STATE_DIMS + 8].index(1.0) == action_id


def test_a_degenerate_completion_yields_no_anchor_rather_than_a_backfilled_one():
    pkt = _packet("aa11", [_grid("00/00"), _grid("01/10")],
                  [_completion(1, 1, 1, None, 1)])
    assert R._completion_terminal_features(pkt, pkt.completions[0]) is None


def test_the_degenerate_flag_alone_refuses_an_anchor():
    """The flag is the declared signal, not a shorthand for "pre-terminal grid missing". A
    completion flagged degenerate must contribute no anchor even if something upstream put a
    grid on it — otherwise a backfilled board would silently become a retrieval query."""
    backfilled = P.Completion(step_index=1, level=1, increment=1, action_id=1, action_data={},
                              level_start_index=1, pre_terminal_settled=_grid("01/10"),
                              degenerate=True)
    pkt = _packet("aa11", [_grid("00/00"), _grid("01/10")], [backfilled])
    assert R._completion_terminal_features(pkt, backfilled) is None
    assert R.query([_record("bb22", [0.1] * TERMINAL_DIMS)], pkt)[1] == "state"


def test_the_anchor_of_a_completion_is_its_measured_terminal_features():
    """Level window is [level_start, completing step): its last two settled grids give the
    transition size, and the completing step's own board — the next level's board — is not
    in it at all."""
    grids = [_grid("00/00"), _grid("01/10"), _grid("ff/ff")]
    pkt = _packet("aa11", grids, [_completion(3, 1, 5, grids[1], 1)])
    vec = R._completion_terminal_features(pkt, pkt.completions[0])
    # level length 3-1+1 = 3; the delta into the pre-terminal board changed 2 cells
    assert vec == pytest.approx(_expected_terminal(_grid("01/10"), {0: 2, 1: 2}, 5, 3, 2))


# --------------------------------------------------------------------------- query construction

def test_a_zero_completion_packet_queries_the_state_subvector_and_nothing_else(cosine_spy):
    """The whole point of the typed split: with no completion observed there is no completing
    action, no level length and no transition size to query with, so the query is 32-wide and
    it reaches only the first 32 dims of a record."""
    pkt = _packet("aa11", [_grid("00/00"), _grid("01/10")])
    index = [_record("bb22", R._terminal_features(_grid("22/22"), 3, 7, 4))]

    hits, qtype = R.query(index, pkt)

    assert qtype == "state"
    assert len(cosine_spy) == 1
    asked, against = cosine_spy[0]
    assert asked == pytest.approx(_expected_state(_grid("01/10"), {0: 2, 1: 2}))
    assert against == pytest.approx(index[0]["vector"][:32])
    assert len(against) == R.STATE_DIMS
    assert [h["env"] for h in hits] == ["bb22"]


def test_a_state_query_cannot_reach_a_records_action_level_length_or_transition_size(
        cosine_spy):
    """Two records with the same pre-terminal board but different completing action, level
    length and transition size must be indistinguishable to a state query. If the tail ever
    leaked in, a zero-completion packet would be ranked by evidence it never saw."""
    pkt = _packet("aa11", [_grid("01/10")])
    board = _grid("22/22")
    index = [_record("bb22", R._terminal_features(board, 1, 2, 1)),
             _record("cc33", R._terminal_features(board, 6, 99, 500))]

    hits, qtype = R.query(index, pkt, k=2)

    assert qtype == "state"
    compared = [against for _, against in cosine_spy]
    assert [len(c) for c in compared] == [R.STATE_DIMS, R.STATE_DIMS]
    assert compared[0] == pytest.approx(compared[1])        # the tails never arrived
    assert [h["env"] for h in hits] == ["bb22", "cc33"]     # so only the tie-break ordered them


def test_a_completion_bearing_packet_queries_on_the_full_vector(cosine_spy):
    grids = [_grid("00/00"), _grid("01/10"), _grid("ff/ff")]
    pkt = _packet("aa11", grids, [_completion(3, 1, 5, grids[1], 1)])
    index = [_record("bb22", R._terminal_features(_grid("22/22"), 3, 7, 4))]

    hits, qtype = R.query(index, pkt)

    assert qtype == "terminal"
    assert len(cosine_spy) == 1
    asked, against = cosine_spy[0]
    assert asked == pytest.approx(_expected_terminal(_grid("01/10"), {0: 2, 1: 2}, 5, 3, 2))
    assert against == pytest.approx(index[0]["vector"])
    assert len(against) == TERMINAL_DIMS
    assert [h["env"] for h in hits] == ["bb22"]


def test_a_terminal_query_does_reach_the_tail_a_state_query_cannot(cosine_spy):
    """Control for the state-query test above: on the same pair of records, the terminal
    query compares 42 dims and the two records are no longer identical to it."""
    grids = [_grid("00/00"), _grid("01/10"), _grid("ff/ff")]
    pkt = _packet("aa11", grids, [_completion(3, 1, 5, grids[1], 1)])
    board = _grid("22/22")
    index = [_record("bb22", R._terminal_features(board, 1, 2, 1)),
             _record("cc33", R._terminal_features(board, 6, 99, 500))]

    _, qtype = R.query(index, pkt, k=2)

    assert qtype == "terminal"
    compared = [against for _, against in cosine_spy]
    assert [len(c) for c in compared] == [TERMINAL_DIMS, TERMINAL_DIMS]
    assert compared[0] != pytest.approx(compared[1])


def _three_completion_packet(env: str = "aa11") -> P.Packet:
    """Three levels of three steps each, with distinct pre-terminal boards, distinct
    completing actions and distinct transition sizes — three genuinely different anchors."""
    grids = [_grid("00/00"), _grid("01/10"), _grid("22/22"),
             _grid("33/33"), _grid("04/40"), _grid("55/55"),
             _grid("66/06"), _grid("77/70"), _grid("88/88")]
    completions = [_completion(3, 1, 1, grids[1], 1),
                   _completion(6, 2, 5, grids[4], 4),
                   _completion(9, 3, 6, grids[7], 7)]
    return _packet(env, grids, completions)


def test_every_observed_completion_contributes_one_anchor(cosine_spy):
    """"TERMINAL queries" is plural: three completions mean three query vectors compared
    against each record, not one summary query."""
    pkt = _three_completion_packet()
    index = [_record("bb22", [0.1] * TERMINAL_DIMS)]

    _, qtype = R.query(index, pkt)

    assert qtype == "terminal"
    assert len(cosine_spy) == 3
    expected = [R._completion_terminal_features(pkt, c) for c in pkt.completions]
    for asked, want in zip([a for a, _ in cosine_spy], expected):
        assert asked == pytest.approx(want)


# --------------------------------------------------------------------------- anchor aggregation

def test_a_records_distance_is_the_minimum_over_the_packets_terminal_queries():
    """Min, not mean, not first, not last. A record that matches ONE observed completion
    exactly must beat a record that is moderately similar to all three — that is what
    "observed completions specialize what similar means" buys, and every other aggregation
    reverses this pair."""
    pkt = _three_completion_packet()
    anchors = [R._completion_terminal_features(pkt, c) for c in pkt.completions]
    exact_middle = _record("bb22", anchors[1])
    blend = _record("cc33", [sum(dim) / 3.0 for dim in zip(*anchors)])

    d_exact = [R._cosine(a, exact_middle["vector"]) for a in anchors]
    d_blend = [R._cosine(a, blend["vector"]) for a in anchors]
    # the construction has to separate the aggregations, or this test asserts nothing
    assert min(d_exact) < min(d_blend)          # min picks the exact match
    assert sum(d_exact) > sum(d_blend)          # mean would pick the blend
    assert d_exact[0] > d_blend[0]              # first-anchor-only would pick the blend
    assert d_exact[-1] > d_blend[-1]            # last-anchor-only would pick the blend

    hits, qtype = R.query([exact_middle, blend], pkt, k=2)

    assert qtype == "terminal"
    assert [h["env"] for h in hits] == ["bb22", "cc33"]


# --------------------------------------------------------------------------- ablation fallback

@pytest.fixture
def e3_pool():
    """A packet whose current board and whose observed completion point at DIFFERENT records.

    The completion's pre-terminal board and the packet's current board have disjoint colour
    support, so the two query types are orthogonal: the terminal group is at distance 0 under
    the terminal query and 1.0 under the state query, and the state group is the reverse.
    Returns (packet, index, terminal_envs, state_envs)."""
    pre, now = _grid("01/10"), _grid("23/32")
    grids = [_grid("00/00"), pre, _grid("44/44"), _grid("23/23"), now]
    pkt = _packet("aa11", grids, [_completion(3, 1, 5, pre, 1)])
    anchor = R._completion_terminal_features(pkt, pkt.completions[0])
    state_vec = R._state_features(now) + [0.0] * 10
    terminal_envs = ["bb22", "cc33", "dd44"]
    state_envs = ["ee55", "ff66", "gg77"]
    index = ([_record(e, anchor) for e in terminal_envs]
             + [_record(e, state_vec) for e in state_envs])
    return pkt, index, terminal_envs, state_envs


def test_ablating_completions_turns_a_terminal_query_back_into_a_state_query(e3_pool):
    pkt, index, _, _ = e3_pool
    assert R.query(index, pkt)[1] == "terminal"
    assert R.query(index, pkt, ablate_completions=True)[1] == "state"


def test_the_ablation_changes_which_records_come_back(e3_pool):
    """The E3 read is this difference. If ablation only relabelled the query type while
    returning the same neighbours, (d)/(f) would measure nothing at all."""
    pkt, index, terminal_envs, state_envs = e3_pool
    on, _ = R.query(index, pkt)
    off, _ = R.query(index, pkt, ablate_completions=True)
    assert [h["env"] for h in on] == terminal_envs
    assert [h["env"] for h in off] == state_envs


def test_the_ablated_query_matches_a_packet_that_never_had_the_completion(e3_pool):
    """Ablation must fall back to the SAME state query a zero-completion packet builds, not
    to some third thing that keeps a residue of the completion."""
    pkt, index, _, _ = e3_pool
    stripped = _packet(pkt.env, [s.settled for s in pkt.steps])
    assert R.query(index, pkt, ablate_completions=True) == R.query(index, stripped)


def test_a_packet_whose_only_completion_is_degenerate_already_queries_as_state():
    """A degenerate completion yields no anchor, so ablated and non-ablated collapse onto the
    same state query: for such a checkpoint the E3 contrast is structurally zero, not small."""
    pkt = _packet("aa11", [_grid("00/00"), _grid("01/10")],
                  [_completion(1, 1, 1, None, 1)])
    index = [_record("bb22", R._terminal_features(_grid("22/22"), 3, 7, 4))]
    assert R.query(index, pkt)[1] == "state"
    assert R.query(index, pkt) == R.query(index, pkt, ablate_completions=True)


# --------------------------------------------------------------------------- LOGO guard

def test_the_packets_own_game_is_excluded_from_a_state_query_even_at_distance_zero():
    """LOGO is whole-game, not whole-session: an exact match from another session of the same
    game is the leak the guard exists for, and it is the record the ranking most wants."""
    pkt = _packet("aa11", [_grid("01/10")], guid="s1")
    perfect = R._state_features(_grid("01/10")) + [0.0] * 10
    index = [_record("aa11", perfect, guid="other-session"),
             _record("bb22", R._terminal_features(_grid("22/22"), 3, 7, 4))]

    hits, qtype = R.query(index, pkt)

    assert qtype == "state"
    assert [h["env"] for h in hits] == ["bb22"]


def test_the_packets_own_game_is_excluded_from_a_terminal_query_even_at_distance_zero():
    grids = [_grid("00/00"), _grid("01/10"), _grid("ff/ff")]
    pkt = _packet("aa11", grids, [_completion(3, 1, 5, grids[1], 1)], guid="s1")
    anchor = R._completion_terminal_features(pkt, pkt.completions[0])
    index = [_record("aa11", anchor, guid="other-session"),
             _record("bb22", R._terminal_features(_grid("22/22"), 3, 7, 4))]

    hits, qtype = R.query(index, pkt)

    assert qtype == "terminal"
    assert [h["env"] for h in hits] == ["bb22"]


def test_a_pool_that_is_entirely_the_packets_own_game_returns_nothing():
    pkt = _packet("aa11", [_grid("01/10")])
    index = [_record("aa11", [0.5] * TERMINAL_DIMS, guid=g) for g in ("s1", "s2", "s3")]
    assert R.query(index, pkt) == ([], "state")


# --------------------------------------------------------------------------- reserved guard

@pytest.fixture
def synthetic_repo(tmp_path, monkeypatch):
    """A temporary REPO holding only the draw build_index reads, so no test in this group
    depends on the real draw or reaches logs/."""
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "gi1_game_draw.json").write_text(json.dumps(
        {"iteration": ["aa11"], "reserved": ["zz99", "zz98"], "one_shot": []}))
    monkeypatch.setattr(R, "REPO", tmp_path)
    return tmp_path


def test_build_index_refuses_a_reserved_game_and_names_it(synthetic_repo, monkeypatch):
    """Guard logic, independent of which games the real draw reserved. A reserved game must
    appear in no GI-1 artifact, and an index is the artifact it would leak through."""
    opened = []
    monkeypatch.setattr(R, "select_sessions", lambda env: opened.append(env) or [])
    with pytest.raises(SystemExit, match=r"reserved games in index request: \['zz99'\]"):
        R.build_index(["aa11", "zz99"])
    assert opened == []          # refused before a single recording is opened


def test_build_index_names_every_reserved_game_in_the_request(synthetic_repo, monkeypatch):
    monkeypatch.setattr(R, "select_sessions", lambda env: [])
    with pytest.raises(SystemExit, match=r"\['zz98', 'zz99'\]"):
        R.build_index(["zz99", "aa11", "zz98"])


def test_build_index_admits_a_request_with_no_reserved_game(synthetic_repo, monkeypatch):
    """Control: the guard is a filter on the draw, not a refusal of everything."""
    monkeypatch.setattr(R, "select_sessions", lambda env: [])
    assert R.build_index(["aa11"]) == []


def test_build_index_emits_one_record_per_non_degenerate_completion(synthetic_repo,
                                                                   monkeypatch):
    """Also pins the record shape the synthetic tests above assume: if build_index ever adds
    or renames a field, `_record` stops matching the producer and this fails."""
    grids = [_grid("00/00"), _grid("01/10"), _grid("22/22"), _grid("03/30"), _grid("44/44")]
    completions = [_completion(1, 1, 1, None, 1),            # degenerate — no pre-terminal
                   _completion(3, 2, 5, grids[1], 2),
                   _completion(5, 3, 6, grids[3], 4)]
    tl = _timeline("aa11", "g1", grids, completions)
    monkeypatch.setattr(R, "select_sessions", lambda env: [{"guid": "g1"}])
    monkeypatch.setattr(R, "load_timeline", lambda env, guid: tl)

    records = R.build_index(["aa11"])

    assert [r["step"] for r in records] == [3, 5]            # the degenerate one is skipped
    assert [r["level"] for r in records] == [2, 3]
    assert all(set(r) == set(_record("x", [0.0] * TERMINAL_DIMS)) for r in records)
    assert all(len(r["vector"]) == TERMINAL_DIMS for r in records)
    assert records[0]["vector"] == pytest.approx(
        R._completion_terminal_features(tl, completions[1]))
    assert records[0]["abstract"]["completing_action"] == "SPACE"


# ------------------------------------------------------------- one neighbour per source game

def _graded_index(query_vec: list, spec: list) -> list:
    """Records at controlled distance from `query_vec`: each is tilted `t` of the way toward
    a fixed orthogonal reference, so distance grows with t. `spec` is (env, guid, t)."""
    away = R._state_features(_grid("cd/dc"))
    return [_record(env, [(1 - t) * a + t * b for a, b in zip(query_vec, away)] + [0.0] * 10,
                    guid=guid)
            for env, guid, t in spec]


def test_one_source_game_cannot_occupy_more_than_one_slot():
    """The cap is the fix for the measured collapse: a game contributes one record per
    completion per selected session, so its records are many and mutually similar. Here bb22
    owns the five nearest records outright and must still get exactly one slot."""
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [("bb22", f"b{i}", 0.02 * (i + 1)) for i in range(5)]
                          + [("cc33", "c1", 0.30), ("dd44", "d1", 0.40),
                             ("ee55", "e1", 0.50)])
    uncapped = sorted(index, key=lambda r: R._cosine(q, r["vector"][:R.STATE_DIMS]))
    assert [r["env"] for r in uncapped[:3]] == ["bb22"] * 3   # one game would sweep all of k

    hits, _ = R.query(index, pkt, k=3)

    assert [h["env"] for h in hits] == ["bb22", "cc33", "dd44"]
    assert len({h["env"] for h in hits}) == len(hits)


def test_the_record_kept_from_a_capped_game_is_that_games_nearest_one():
    """Capping must not degrade into "first one seen": the survivor is the game's best
    record, so (d) still shows its closest analogy and (f) still votes on it."""
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [("bb22", "far", 0.40), ("bb22", "near", 0.05),
                              ("bb22", "middling", 0.20), ("cc33", "c1", 0.60)])

    hits, _ = R.query(index, pkt, k=2)

    assert [(h["env"], h["guid"]) for h in hits] == [("bb22", "near"), ("cc33", "c1")]


def test_a_tie_inside_a_capped_game_is_broken_by_guid_then_step():
    """Ordering must not depend on index order — the pre-registered tie-break is
    (distance, env, guid, step) ascending, and build_index emits records in session order."""
    pkt = _packet("aa11", [_grid("01/10")])
    vec = R._state_features(_grid("01/10")) + [0.0] * 10
    index = [_record("bb22", vec, guid="z", step=1),
             _record("bb22", vec, guid="a", step=9),
             _record("bb22", vec, guid="a", step=2)]

    hits, _ = R.query(index, pkt, k=3)

    assert [(h["guid"], h["step"]) for h in hits] == [("a", 2)]
    assert R.query(index, pkt, k=3) == R.query(list(reversed(index)), pkt, k=3)


def test_the_per_source_game_cap_is_the_one_SPEC_declares():
    """SPEC records the pre-registered value; query() implements it as a hardcoded "skip a
    game already represented". This asserts the two still agree."""
    assert R.SPEC["per_source_game"] == 1
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [("bb22", "b1", 0.05), ("bb22", "b2", 0.06),
                              ("cc33", "c1", 0.30)])
    hits, _ = R.query(index, pkt, k=3)
    assert sum(1 for h in hits if h["env"] == "bb22") == R.SPEC["per_source_game"]


def test_the_cap_is_read_from_SPEC_not_hardcoded_beside_it(monkeypatch):
    """SPEC is the pre-registration record. A value declared there that query() ignores is
    worse than no value at all: editing it to widen the cap would change the registered
    document and nothing else, and the run would silently keep the old behaviour."""
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [("bb22", "b1", 0.05), ("bb22", "b2", 0.06),
                              ("cc33", "c1", 0.30)])
    monkeypatch.setitem(R.SPEC, "per_source_game", 2)
    hits, _ = R.query(index, pkt, k=3)
    assert [h["guid"] for h in hits] == ["b1", "b2", "c1"]


def test_k_defaults_to_the_value_SPEC_declares():
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [(f"g{i}", "s1", 0.05 * (i + 1)) for i in range(6)])
    assert len(R.query(index, pkt)[0]) == R.SPEC["k"] == 3


# --------------------------------------------------------------------------- fewer than k games

def test_fewer_distinct_games_than_k_returns_what_exists():
    """No padding, no looping, no second helping from a game already represented — a thin
    pool must produce a short hit list rather than a fabricated full one."""
    pkt = _packet("aa11", [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    index = _graded_index(q, [("bb22", "b1", 0.05), ("bb22", "b2", 0.10),
                              ("bb22", "b3", 0.15), ("cc33", "c1", 0.30)])

    hits, _ = R.query(index, pkt, k=3)

    assert [h["env"] for h in hits] == ["bb22", "cc33"]
    assert len(hits) == 2


def test_an_empty_index_returns_no_hits_and_still_reports_a_query_type():
    pkt = _packet("aa11", [_grid("01/10")])
    assert R.query([], pkt) == ([], "state")


# ------------------------------------------------------------------ programmatic floor (e)

@pytest.fixture
def class_table(monkeypatch):
    """Stand in for logs/s2_goal_predicates_labelled.json, which build/query never read but
    both floors do — at call time, so it has to be patched rather than skipped around."""
    table = {"aa11": "alpha", "bb22": "beta", "cc33": "beta", "dd44": "gamma",
             "ee55": "delta", "ff66": "gamma", "gg77": "delta"}
    monkeypatch.setattr(R, "_primary_classes", lambda: dict(table))
    return table


def test_condition_e_prior_never_counts_the_evaluated_games_own_label(class_table):
    """Leave-one-game-out has to change the ANSWER, not just the membership: with bb22
    counting itself, beta ties gamma and wins on name; without it, gamma wins outright."""
    library = ["bb22", "cc33", "dd44", "ff66"]
    assert R.condition_e_prior("bb22", library) == ["gamma", "beta"]
    assert R.condition_e_prior("zz00", library) == ["beta", "gamma"]   # the same library, kept whole


def test_condition_e_prior_drops_a_class_only_the_evaluated_game_carries(class_table):
    assert "alpha" not in R.condition_e_prior("aa11", ["aa11", "bb22", "cc33", "dd44"])


def test_the_floors_refuse_a_library_holding_a_reserved_game(synthetic_repo, class_table):
    """The index guard alone left this door open: the floors take their library as an argument,
    so a reserved game's label reached an (e)/(f) output without any index being built. Both
    entry points are guarded because both are entry points."""
    with pytest.raises(SystemExit, match=r"\(e\) prior library: \['zz99'\]"):
        R.condition_e_prior("aa11", ["bb22", "zz99"])
    with pytest.raises(SystemExit, match=r"\(f\) vote library: \['zz99'\]"):
        R.condition_f_vote([], _packet("aa11", [_grid("01/10")]), ["bb22", "zz99"])


def test_the_floors_admit_a_library_with_no_reserved_game(synthetic_repo, class_table):
    assert R.condition_e_prior("aa11", ["bb22", "cc33", "dd44"])


def test_a_missing_draw_leaves_the_reserved_set_empty_rather_than_failing(tmp_path,
                                                                         monkeypatch):
    """The reserved set is DECLARED by the draw. With no draw there is no declaration to
    enforce, and every environment running a real pass has one — so this keeps the guard from
    turning a deliberately absent logs/ into an error, without ever waving a declared game
    through."""
    monkeypatch.setattr(R, "REPO", tmp_path)
    assert R._reserved_games() == set()
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "gi1_game_draw.json").write_text(
        json.dumps({"iteration": [], "reserved": ["zz99"], "one_shot": []}))
    assert R._reserved_games() == {"zz99"}


def test_condition_e_prior_ranks_by_count_then_class_name(class_table):
    library = ["bb22", "cc33", "dd44", "ff66", "ee55"]
    assert R.condition_e_prior("aa11", library, top=3) == ["beta", "gamma", "delta"]
    assert R.condition_e_prior("aa11", library, top=2) == ["beta", "gamma"]


def test_condition_e_prior_is_deterministic(class_table):
    library = ["ff66", "bb22", "ee55", "dd44", "cc33"]
    first = R.condition_e_prior("aa11", library)
    assert first == R.condition_e_prior("aa11", library)
    assert first == R.condition_e_prior("aa11", list(reversed(library)))


def test_primary_classes_reads_the_labelled_predicate_file(tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "s2_goal_predicates_labelled.json").write_text(json.dumps(
        {"records": [{"env": "aa11", "label": {"primary": "alpha", "secondary": "x"}},
                     {"env": "bb22", "label": {"primary": "beta"}}]}))
    monkeypatch.setattr(R, "REPO", tmp_path)
    assert R._primary_classes() == {"aa11": "alpha", "bb22": "beta"}


# ------------------------------------------------------------------ programmatic floor (f)

def _vote_pool(env: str = "aa11"):
    """A packet plus an index whose records sit at graded distance from its state query, so
    the vote is decided by which games retrieval reaches."""
    pkt = _packet(env, [_grid("01/10")])
    q = R._state_features(_grid("01/10"))
    return pkt, q


def test_condition_f_vote_is_deterministic_and_independent_of_index_order(class_table):
    pkt, q = _vote_pool()
    index = _graded_index(q, [("bb22", "b1", 0.05), ("dd44", "d1", 0.10),
                              ("ee55", "e1", 0.15), ("ff66", "f1", 0.40)])
    library = ["aa11", "cc33", "dd44", "ee55", "ff66"]
    first = R.condition_f_vote(index, pkt, library)
    assert first == R.condition_f_vote(index, pkt, library)
    assert first == R.condition_f_vote(list(reversed(index)), pkt, library)


def test_condition_f_vote_breaks_a_vote_tie_by_prior_rank_not_class_name(class_table):
    """Three neighbours from three games give one vote each. The prior — not alphabetical
    order — has to decide, otherwise (f) is a name sort wearing a retrieval costume."""
    pkt, q = _vote_pool()
    index = _graded_index(q, [("bb22", "b1", 0.05),    # beta
                              ("dd44", "d1", 0.10),    # gamma
                              ("ee55", "e1", 0.15)])   # delta
    library = ["aa11", "cc33", "dd44", "ee55", "ff66"]  # gamma 2, beta 1, delta 1
    assert R.condition_e_prior("aa11", library) == ["gamma", "beta", "delta"]

    out = R.condition_f_vote(index, pkt, library)

    assert out == ["gamma", "beta", "delta"]
    assert out != sorted(out)          # alphabetical order would have been beta, delta, gamma


def test_condition_f_vote_backfills_from_the_prior_when_retrieval_is_thin(class_table):
    """Retrieval reaches two games that share a class, so the vote supplies one class and the
    remaining two slots come from the prior, in prior order and without repeating it."""
    pkt, q = _vote_pool()
    index = _graded_index(q, [("bb22", "b1", 0.05), ("cc33", "c1", 0.10)])   # both beta
    library = ["aa11", "cc33", "dd44", "ee55", "ff66"]

    out = R.condition_f_vote(index, pkt, library)

    assert out == ["beta", "gamma", "delta"]
    assert len(out) == len(set(out)) == 3


def test_condition_f_vote_respects_top(class_table):
    pkt, q = _vote_pool()
    index = _graded_index(q, [("bb22", "b1", 0.05), ("cc33", "c1", 0.10)])
    library = ["aa11", "cc33", "dd44", "ee55", "ff66"]
    assert R.condition_f_vote(index, pkt, library, top=2) == ["beta", "gamma"]
    assert R.condition_f_vote(index, pkt, library, top=1) == ["beta"]


def test_condition_f_vote_never_counts_the_evaluated_games_own_class(class_table):
    """The votes come through query(), so LOGO applies to them too: aa11's own alpha label is
    scoring-only and must not reach its own vote, however near its records sit."""
    pkt, q = _vote_pool()
    index = _graded_index(q, [("aa11", "own", 0.0), ("dd44", "d1", 0.30)])
    out = R.condition_f_vote(index, pkt, ["aa11", "cc33", "dd44", "ee55", "ff66"])
    assert "alpha" not in out
    assert out[0] == "gamma"


def test_condition_f_vote_reads_the_ablation_through_to_retrieval(class_table, e3_pool):
    """(f)'s E3 read: with completions observed the vote re-anchors on them, and under
    ablation it falls back to the state query. The two must disagree, or K2 has nothing to
    compare."""
    pkt, index, _, _ = e3_pool
    library = ["aa11", "bb22", "cc33", "dd44", "ee55", "ff66", "gg77"]

    posterior = R.condition_f_vote(index, pkt, library)
    ablated = R.condition_f_vote(index, pkt, library, ablate_completions=True)

    assert posterior[0] == "beta"       # bb22/cc33 beta + dd44 gamma, from the terminal query
    assert ablated[0] == "delta"        # ee55/gg77 delta + ff66 gamma, from the state query
    assert posterior != ablated


# --------------------------------------------------------------------------- exemplar rendering

def test_render_exemplars_says_the_analogies_are_from_other_games():
    hits = [_record("bb22", [0.0] * TERMINAL_DIMS)]
    text = R.render_exemplars(hits)
    assert "never this game" in text
    assert "bb22 level 1" in text and "SPACE" in text


def test_render_exemplars_survives_an_abstract_without_the_optional_blocks():
    """`pre_terminal_inventory` is absent for a degenerate completion and `final_transition`
    for a one-step level; neither may take the renderer down mid-prompt."""
    hits = [_record("bb22", [0.0] * TERMINAL_DIMS)]
    hits[0]["abstract"] = dict(_STUB_ABSTRACT, final_transition={"changed_cells": 0})
    assert R.render_exemplars(hits).count("\n") == 1     # header plus the one exemplar line


# --------------------------------------------------------------------------- corpus integration

@pytest.fixture(scope="module")
def real_index():
    """ft09 and ls20 only — two source games is enough for the per-game cap to bind, and the
    full iteration slice costs several times as long in segmentation."""
    return R.build_index(["ft09", "ls20"])


def _real_packet(env: str, checkpoint: str):
    tl = P.load_timeline(env, P.select_sessions(env)[0]["guid"])
    step = P.checkpoints(tl)[checkpoint]
    assert step is not None, f"{env} no longer has a valid {checkpoint} — re-measure"
    return P.extract(tl, checkpoint, step)


@requires_corpus
def test_a_real_index_record_matches_the_shape_the_synthetic_records_assume(real_index):
    """The keystone for everything above: if the real producer's records drift, the synthetic
    fixtures stop testing the deployed thing."""
    assert real_index, "empty index over ft09 + ls20"
    for r in real_index:
        assert set(r) == set(_record("x", [0.0] * TERMINAL_DIMS))
        assert len(r["vector"]) == TERMINAL_DIMS
        assert r["env"] in ("ft09", "ls20")
    assert set(_STUB_ABSTRACT) <= set(real_index[0]["abstract"])


@requires_corpus
def test_a_real_terminal_query_obeys_logo_and_the_per_source_game_cap(real_index):
    pkt = _real_packet("vc33", "completion:1")
    hits, qtype = R.query(real_index, pkt)
    assert qtype == "terminal"
    assert all(h["env"] != "vc33" for h in hits)
    assert len({h["env"] for h in hits}) == len(hits)
    assert (hits, qtype) == R.query(real_index, pkt)


@requires_corpus
def test_a_real_zero_completion_checkpoint_queries_as_state(real_index):
    """m0r0's offset:10 is valid — its first completion is at step 24 — so this is a genuine
    zero-completion packet rather than one with the completions filtered out."""
    pkt = _real_packet("m0r0", "offset:10")
    assert pkt.completions == []
    hits, qtype = R.query(real_index, pkt)
    assert qtype == "state"
    assert all(h["env"] != "m0r0" for h in hits)


@requires_corpus
def test_a_real_completion_packet_falls_back_to_state_under_ablation(real_index):
    pkt = _real_packet("vc33", "completion:1")
    assert pkt.completions, "vc33 completion:1 packet carries no completion"
    assert R.query(real_index, pkt, ablate_completions=True)[1] == "state"


@requires_labels
def test_the_real_prior_never_counts_the_evaluated_games_own_label():
    draw = json.loads(DRAW.read_text())
    classes = R._primary_classes()
    for env in draw["iteration"]:
        prior = R.condition_e_prior(env, draw["iteration"])
        manual = {}
        for g in draw["iteration"]:
            if g != env:
                manual[classes[g]] = manual.get(classes[g], 0) + 1
        assert prior == [c for c, _ in sorted(manual.items(), key=lambda kv: (-kv[1], kv[0]))][:3]


def test_the_level_window_is_seeded_with_the_board_before_its_first_action():
    """A level that starts after a completion has a predecessor board — the previous completing
    step's own grid, which IS this level's initial board — one index before level_start. Without
    it a two-action level reports a final-transition size of 0 and its vector says "nothing
    changed before the completing action", which is a claim about the game, not a gap in the
    window. gi1_digest.terminal_abstract seeds identically; the two must agree or a record's
    vector and its rendered abstract describe different transitions."""
    # Step 2 differs from step 3 in THREE cells, step 1 in four, so the assertion distinguishes
    # seeding from the right board rather than merely from some earlier one.
    grids = [_grid("00/00"), _grid("01/00"), _grid("11/11"), _grid("22/22")]
    pkt = _packet("aa11", grids)
    # level 2 spans steps 3..4 and completes at 4, so its window is the single step 3 and its
    # initial board — the seed — is step 2's grid.
    completion = _completion(4, 2, 1, grids[2], 3)
    vec = R._completion_terminal_features(pkt, completion)
    assert vec[-1] == math.log1p(3)


def test_level_one_keeps_the_short_chain_because_it_has_no_predecessor():
    """Control: before the first completion there genuinely is no earlier board, so a one-step
    window yields no transition rather than a fabricated one."""
    grids = [_grid("00/00"), _grid("11/11")]
    pkt = _packet("aa11", grids)
    vec = R._completion_terminal_features(pkt, _completion(2, 1, 1, grids[0], 1))
    assert vec[-1] == math.log1p(0)


# ---------------------------------------------------------------------- index cache contract

def _cache_selection(env):
    return [{"guid": f"{env}-s", "levels_completed": 3, "total_actions": 10,
             "tier": 3, "rank": 0}]


def _cache_artifact(monkeypatch, games=("aa11",)):
    monkeypatch.setattr(R, "select_sessions", _cache_selection)
    contract = R._index_contract(list(games))
    return {
        **contract,
        "records": [_record(
            games[0], [0.0] * TERMINAL_DIMS, guid=f"{games[0]}-s"
        )],
    }


def test_index_cache_contract_pins_library_spec_and_session_selection(monkeypatch):
    artifact = _cache_artifact(monkeypatch)
    assert artifact["format_version"] == R.INDEX_FORMAT_VERSION
    assert artifact["library_games"] == ["aa11"]
    assert artifact["retrieval_spec"] == R.SPEC
    assert artifact["session_selection"]["aa11"][0]["guid"] == "aa11-s"
    assert R.validate_index_artifact(artifact, ["aa11"]) == []


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda a: a.update(library_games=["bb22"]), "library_games"),
        (lambda a: a.update(retrieval_spec={"k": 99}), "retrieval_spec"),
        (
            lambda a: a["session_selection"]["aa11"][0].update(guid="wrong"),
            "session_selection",
        ),
        (lambda a: a["records"][0].update(env="bb22"), "outside library"),
        (lambda a: a["records"][0].update(vector=[0.0]), "42-dimensional"),
        (lambda a: a["records"][0].update(step=0), "positive integer"),
    ],
)
def test_index_cache_validator_refuses_contract_or_record_drift(
    monkeypatch, mutate, needle
):
    artifact = _cache_artifact(monkeypatch)
    mutate(artifact)
    assert any(
        needle in problem
        for problem in R.validate_index_artifact(artifact, ["aa11"])
    )


def test_load_or_build_index_reuses_a_valid_cache_without_rescanning(
    tmp_path, monkeypatch
):
    artifact = _cache_artifact(monkeypatch)
    path = tmp_path / "index.json"
    path.write_text(json.dumps(artifact))
    monkeypatch.setattr(
        R,
        "build_index",
        lambda games: (_ for _ in ()).throw(AssertionError("replay rescan")),
    )
    assert R.load_or_build_index(["aa11"], path) == artifact["records"]


def test_load_or_build_index_builds_validates_and_atomically_publishes(
    tmp_path, monkeypatch
):
    artifact = _cache_artifact(monkeypatch)
    path = tmp_path / "index.json"
    monkeypatch.setattr(R, "build_index", lambda games: artifact["records"])
    assert R.load_or_build_index(["aa11"], path) == artifact["records"]
    assert json.loads(path.read_text()) == artifact
    assert not path.with_suffix(".json.tmp").exists()


def test_present_invalid_cache_is_refused_not_silently_rebuilt(tmp_path, monkeypatch):
    _cache_artifact(monkeypatch)
    path = tmp_path / "index.json"
    path.write_text('{"records":[]}')
    monkeypatch.setattr(
        R,
        "build_index",
        lambda games: (_ for _ in ()).throw(AssertionError("silent rebuild")),
    )
    with pytest.raises(ValueError, match="cache is invalid"):
        R.load_or_build_index(["aa11"], path)
