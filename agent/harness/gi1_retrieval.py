#!/usr/bin/env python3
"""GI-1 terminal-packet retrieval (conditions d/f) and the programmatic floors (e/f).

Pool semantics frozen in notes/design-pivot.md §2.4, implemented as:

  - CROSS-GAME POOL: terminal-packet records from other games' sessions, leave-one-game-out
    over the non-reserved set — the retrievable/displayable/votable library. A hidden target
    game is never in a shipped library; LOGO reproduces that. Reserved games are refused at
    index build.
  - SAME-SESSION completions participate as QUERY ANCHORS, not as retrievable records: each
    observed completion's true terminal features (pre-terminal grid, completing action, level
    length, final transition) become a query, and a record's distance is its minimum over
    those queries. This is the deployment posterior — observed completions specialize what
    "similar" means — and it is what E3's ablation switches off. They are never *displayed*
    by (d) (the digest already shows them) and never *voted* by (f) (their class label is the
    evaluated game's own, which is scoring-only).
  - NEVER another human session of the current game, in any role.

QUERY TYPES (review issue: a single query shape mixed fields from different levels):
  - zero completions, or E3 ablation — a STATE query: color-pixel fractions + object counts
    of the current board, compared on the state subvector only. No completing action, no
    level length, no fabricated transition size.
  - one or more completions — TERMINAL queries as above, compared on the full vector.

FROZEN FOR GI-1 ITERATION (SPEC below): features, distance, k, tie-breaking and query
aggregation froze after MoE-only development and before the measured 27B-8bit pass.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
INDEX_CACHE = REPO / "logs/gi1_retrieval_index.json"
INDEX_FORMAT_VERSION = 1

from gi1_digest import ARC_COLOR_CHARS, segment_layer, terminal_abstract  # noqa: E402
from gi1_packets import (Packet, checkpoints, extract, load_timeline,  # noqa: E402
                         select_sessions, settled_delta)

STATE_DIMS = 32   # 16 color-pixel fractions + 16 log1p object counts

SPEC = {  # GI-1 iteration freeze
    "state_features": "16 color-pixel fractions + 16 color-object counts (log1p)",
    "terminal_features": "state features of the pre-terminal grid + 8 action one-hot"
                         " + log1p(level length) + log1p(final-transition changed cells)",
    "distance": "cosine; state queries on the state subvector, terminal queries full-vector",
    "aggregation": "record distance = min over the packet's terminal queries",
    "k": 3,
    "per_source_game": 1,   # see query(): at most one neighbour per source game
    "tie_break": "(distance, env, guid, step) ascending",
    "version": "gi1-iteration-frozen-2026-07-29",
}


def _state_features(grid: list) -> list[float]:
    px = [0.0] * 16
    for row in grid:
        for v in row:
            px[v] += 1.0
    total = sum(px) or 1.0
    px = [p / total for p in px]
    objs = [0.0] * 16
    for n in segment_layer(grid, ARC_COLOR_CHARS)["nodes"]:
        objs[ARC_COLOR_CHARS.index(n["color"])] += 1.0
    return px + [math.log1p(o) for o in objs]


def _terminal_features(pre_terminal: list, action_id: int, level_length: int,
                       final_changed_cells: int) -> list[float]:
    act = [0.0] * 8
    # Folding an out-of-range id onto slot 0 would make it indistinguishable from RESET in the
    # feature vector — a silent corruption of the distance that a future ingest bug could hide
    # behind. gi1_packets raises on a boolean action id for the same reason; the platform
    # advertises only RESET and ACTION1-7, so anything else is a parse failure, not a value.
    if isinstance(action_id, bool) or not isinstance(action_id, int):
        raise ValueError(f"action id {action_id!r} is not an integer in the 0..7 one-hot")
    if not 0 <= action_id <= 7:
        raise ValueError(f"action id {action_id} outside the 0..7 one-hot")
    act[action_id] = 1.0
    return (_state_features(pre_terminal) + act
            + [math.log1p(level_length), math.log1p(final_changed_cells)])


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return 1.0 - dot / (na * nb)


def _completion_terminal_features(tl_or_packet, completion) -> list[float] | None:
    """Terminal features of one observed completion, from packet/timeline steps only."""
    if completion.degenerate or completion.pre_terminal_settled is None:
        return None
    steps = [s for s in tl_or_packet.steps
             if completion.level_start_index <= s.index < completion.step_index]
    # Seeded with the board before the level's first action, exactly as gi1_digest's
    # terminal_abstract is: the two must agree or a record's vector and its rendered abstract
    # would describe different final transitions. Level 1 has no predecessor and keeps the short
    # chain. Measured 2026-07-29: no completion in the selected sessions is affected.
    seed = next((s for s in tl_or_packet.steps
                 if s.index == completion.level_start_index - 1), None)
    chain = ([seed] + steps) if seed is not None else steps
    changed = 0
    if len(chain) >= 2:
        changed = len(settled_delta(chain[-2].settled, chain[-1].settled))
    return _terminal_features(completion.pre_terminal_settled, completion.action_id,
                              completion.step_index - completion.level_start_index + 1,
                              changed)


def _reserved_games() -> set:
    """The draw's reserved list, or empty when no draw is on disk.

    Empty is the honest answer rather than a lax one: the reserved set is *declared* by the
    draw, so with no draw there is no declaration to enforce, and every environment that runs a
    real GI-1 pass has one. It also keeps the guard from turning a missing artifact into a hard
    failure in environments that deliberately carry no logs/ (the mutation sandbox)."""
    path = REPO / "logs/gi1_game_draw.json"
    return set(json.loads(path.read_text())["reserved"]) if path.exists() else set()


def _refuse_reserved(games, context: str) -> None:
    """Reserved games stay out of EVERY GI-1 artifact, not only the index.

    The programmatic floors take their library as a parameter, so guarding the index alone left
    the same leak open through another door: `condition_e_prior(env, [..., 'su15'])` counted a
    reserved game's label into an (e)/(f) output. su15 is the only game in the set carrying
    `counts`, so that class appearing in a floor output was a positive signature of the leak."""
    bad = _reserved_games() & set(games)
    if bad:
        raise SystemExit(f"reserved games in {context}: {sorted(bad)}")


def build_index(games: list[str]) -> list[dict]:
    """One record per non-degenerate completion in the selected sessions of `games`."""
    _refuse_reserved(games, "index request")
    records = []
    for env in sorted(games):
        for sel in select_sessions(env):
            tl = load_timeline(env, sel["guid"])
            # `completion:k` means the k-th completion everywhere else (gi1_packets.checkpoints
            # indexes tl.completions[k-1]), so the ordinal is the label — not c.level, which
            # differs the moment an increment exceeds 1.
            for ordinal, c in enumerate(tl.completions, start=1):
                vec = _completion_terminal_features(tl, c)
                if vec is None:
                    continue
                p = extract(tl, f"completion:{ordinal}", c.step_index)
                records.append({"env": env, "guid": sel["guid"], "step": c.step_index,
                                "level": c.level, "vector": vec,
                                "abstract": terminal_abstract(p, c)})
    return records


def _index_contract(games: list[str]) -> dict:
    """Cheap identity for the expensive replay-derived index build."""
    ordered = sorted(games)
    _refuse_reserved(ordered, "index cache contract")
    return {
        "format_version": INDEX_FORMAT_VERSION,
        "library_games": ordered,
        "retrieval_spec": SPEC,
        "session_selection": {
            env: [
                {
                    "guid": row["guid"],
                    "levels_completed": row["levels_completed"],
                    "total_actions": row["total_actions"],
                    "tier": row["tier"],
                    "rank": row["rank"],
                }
                for row in select_sessions(env)
            ]
            for env in ordered
        },
    }


def validate_index_artifact(value, games: list[str]) -> list[str]:
    """Validate a cached index without rescanning the multi-gigabyte replay files."""
    expected = _index_contract(games)
    if not isinstance(value, dict):
        return ["retrieval index artifact must be an object"]
    problems = []
    if set(value) != set(expected) | {"records"}:
        problems.append("retrieval index artifact keys do not match the contract")
    for name, wanted in expected.items():
        if value.get(name) != wanted:
            problems.append(f"retrieval index contract drift: {name}")
    records = value.get("records")
    if not isinstance(records, list):
        return problems + ["retrieval index records must be a list"]
    allowed = set(expected["library_games"])
    selected = {
        env: {row["guid"] for row in rows}
        for env, rows in expected["session_selection"].items()
    }
    seen = set()
    expected_record_keys = {"env", "guid", "step", "level", "vector", "abstract"}
    for offset, record in enumerate(records):
        where = f"retrieval index record {offset}"
        if not isinstance(record, dict) or set(record) != expected_record_keys:
            problems.append(f"{where}: malformed record")
            continue
        env, guid = record.get("env"), record.get("guid")
        if env not in allowed:
            problems.append(f"{where}: game {env!r} outside library")
        elif guid not in selected.get(env, set()):
            problems.append(f"{where}: session {guid!r} outside frozen selection")
        identity = (env, guid, record.get("step"))
        if identity in seen:
            problems.append(f"{where}: duplicate completion identity {identity!r}")
        seen.add(identity)
        for name in ("step", "level"):
            number = record.get(name)
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                problems.append(f"{where}: {name} must be a positive integer")
        vector = record.get("vector")
        if (
            not isinstance(vector, list)
            or len(vector) != STATE_DIMS + 10
            or any(
                isinstance(number, bool)
                or not isinstance(number, (int, float))
                or not math.isfinite(number)
                for number in vector
            )
        ):
            problems.append(f"{where}: malformed {STATE_DIMS + 10}-dimensional vector")
        if not isinstance(record.get("abstract"), dict):
            problems.append(f"{where}: abstract must be an object")
    if not records:
        problems.append("retrieval index has no records")
    return problems


def load_or_build_index(
    games: list[str],
    path: Path = INDEX_CACHE,
    *,
    rebuild: bool = False,
) -> list[dict]:
    """Load the replay-derived index, building it once when absent.

    A present but drifting cache is refused, never silently rebuilt.  Before measurement the
    operator may pass ``rebuild=True`` explicitly; after freeze its SHA-256 is part of the
    implementation manifest.
    """
    if path.exists() and not rebuild:
        try:
            artifact = json.loads(path.read_text())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read retrieval index cache {path}: {exc}") from exc
        problems = validate_index_artifact(artifact, games)
        if problems:
            raise ValueError("retrieval index cache is invalid: " + "; ".join(problems))
        return artifact["records"]
    contract = _index_contract(games)
    artifact = {**contract, "records": build_index(contract["library_games"])}
    problems = validate_index_artifact(artifact, games)
    if problems:
        raise ValueError("fresh retrieval index is invalid: " + "; ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(artifact, separators=(",", ":")) + "\n")
    temporary.replace(path)
    return artifact["records"]


def query(index: list[dict], packet: Packet, k: int | None = None,
          ablate_completions: bool = False) -> tuple[list[dict], str]:
    """Nearest cross-game terminal packets, at most one per source game. Returns (hits, type).

    THE PER-GAME CAP IS LOAD-BEARING, not tidying. A game contributes one record per
    completion in each of its three selected sessions, so its records are many and mutually
    similar; without a cap the k nearest are usually the same game's near-duplicates.
    Measured on the iteration slice before this cap: 62 of 78 queries returned all three
    neighbours from ONE source game, and no query ever reached three distinct games. That
    made (f)'s "3 votes" one game's class counted three times — the appearance of consensus
    from a single source — and handed (d) three near-identical exemplars instead of three
    analogies. Capping at one per game is the cheaper of the two fixes the review proposed
    (the other being per-game distance aggregation) and keeps the existing tie-break order
    intact: records stay sorted, the cap only skips a game already represented."""
    k = SPEC["k"] if k is None else k
    pool = [r for r in index if r["env"] != packet.env]     # LOGO: whole game excluded
    anchors = []
    if not ablate_completions:
        anchors = [v for v in (_completion_terminal_features(packet, c)
                               for c in packet.completions) if v is not None]
    if anchors:
        qtype = "terminal"
        def dist(r):
            return min(_cosine(a, r["vector"]) for a in anchors)
    else:
        qtype = "state"
        state = _state_features(packet.steps[-1].settled)
        def dist(r):
            return _cosine(state, r["vector"][:STATE_DIMS])
    per_game = SPEC["per_source_game"]
    scored = sorted(pool, key=lambda r: (dist(r), r["env"], r["guid"], r["step"]))
    hits: list[dict] = []
    taken: dict[str, int] = {}
    for r in scored:
        if len(hits) >= k:
            break
        if taken.get(r["env"], 0) >= per_game:
            continue
        taken[r["env"]] = taken.get(r["env"], 0) + 1
        hits.append(r)
    return hits, qtype


def render_exemplars(hits: list[dict]) -> str:
    lines = ["Analogous completions retrieved from OTHER public games "
             "(never this game; treat as analogy, not ground truth):"]
    for h in hits:
        t = h["abstract"]
        lines.append(f"- {h['env']} level {t['level_completed']}: completed with "
                     f"{t['completing_action']} after {t['level_length_actions']} action(s)")
        pre = t.get("pre_terminal_inventory")
        if pre:
            lines.append("    board immediately before the completing action: " + "; ".join(
                f"{c}:{v['objects']}x{v['pixels']}px" for c, v in pre["by_color"].items()))
        ft = t.get("final_transition")
        if ft and ft.get("changed_cells"):
            lines.append(f"    last change before that action: {ft['changed_cells']} cells, "
                         f"transitions {ft['color_transitions']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- programmatic floors (e/f)

def _primary_classes() -> dict[str, str]:
    data = json.loads((REPO / "logs/s2_goal_predicates_labelled.json").read_text())
    return {r["env"]: r["label"]["primary"] for r in data["records"]}


def condition_e_prior(env: str, library_games: list[str], top: int = 3) -> list[str]:
    """(e): leave-one-game-out class prior — the evaluated game's label never contributes."""
    _refuse_reserved(library_games, "(e) prior library")
    classes = _primary_classes()
    counts: dict[str, int] = {}
    for g in library_games:
        if g == env:
            continue
        counts[classes[g]] = counts.get(classes[g], 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [c for c, _ in ranked[:top]]


def condition_f_vote(index: list[dict], packet: Packet, library_games: list[str],
                     top: int = 3, ablate_completions: bool = False) -> list[str]:
    """(f): retrieved games' primary classes vote; LOGO prior tie-breaks and back-fills.
    With completions observed, retrieval re-anchors on them (the programmatic posterior);
    under E3 ablation it falls back to the state query — that difference IS the E3 read."""
    _refuse_reserved(library_games, "(f) vote library")
    classes = _primary_classes()
    prior = condition_e_prior(packet.env, library_games, top=len(set(classes.values())))
    prior_rank = {c: i for i, c in enumerate(prior)}
    hits, _ = query(index, packet, ablate_completions=ablate_completions)
    votes: dict[str, int] = {}
    for h in hits:
        votes[classes[h["env"]]] = votes.get(classes[h["env"]], 0) + 1
    ranked = sorted(votes.items(),
                    key=lambda kv: (-kv[1], prior_rank.get(kv[0], len(prior)), kv[0]))
    out = [c for c, _ in ranked]
    out += [c for c in prior if c not in out]
    return out[:top]


def selftest() -> int:
    draw = json.loads((REPO / "logs/gi1_game_draw.json").read_text())
    iteration = draw["iteration"]
    index = build_index(iteration)          # development stays on the slice
    failures = []
    if not index:
        failures.append("empty index over iteration slice")
    classes = _primary_classes()
    for env in ("ls20", "m0r0"):
        sel = select_sessions(env)[0]
        tl = load_timeline(env, sel["guid"])
        cps = checkpoints(tl)
        zero = next((s for k, s in cps.items() if s and k.startswith("offset:")), None)
        comp = cps.get("completion:1")
        if zero:
            p = extract(tl, "offset", zero)
            hits, qtype = query(index, p)
            if qtype != "state":
                failures.append(f"{env}: zero-completion query type {qtype}")
            if any(h["env"] == env for h in hits):
                failures.append(f"{env}: same-game record retrieved (leak)")
            if len({h["env"] for h in hits}) != len(hits):
                failures.append(f"{env}: source game repeated in hits (cap not applied)")
            if (hits, qtype) != query(index, p):
                failures.append(f"{env}: nondeterministic")
        if comp:
            p = extract(tl, "completion:1", comp)
            hits, qtype = query(index, p)
            if qtype != "terminal":
                failures.append(f"{env}: completion checkpoint query type {qtype}")
            if len({h["env"] for h in hits}) != len(hits):
                failures.append(f"{env}: source game repeated in hits (cap not applied)")
            _, qtype_ab = query(index, p, ablate_completions=True)
            if qtype_ab != "state":
                failures.append(f"{env}: ablated query did not fall back to state")
            f_on = condition_f_vote(index, p, iteration)
            f_off = condition_f_vote(index, p, iteration, ablate_completions=True)
            if len(f_on) != 3 or any(c not in set(classes.values()) for c in f_on):
                failures.append(f"{env}: (f) vote malformed: {f_on}")
            if len(f_off) != 3:
                failures.append(f"{env}: ablated (f) vote malformed")
        prior = condition_e_prior(env, iteration)
        manual: dict[str, int] = {}
        for g in iteration:
            if g != env:
                manual[classes[g]] = manual.get(classes[g], 0) + 1
        expected = [c for c, _ in sorted(manual.items(), key=lambda kv: (-kv[1], kv[0]))][:3]
        if prior != expected:
            failures.append(f"{env}: (e) prior wrong or not leave-one-game-out")
    try:
        build_index(iteration + [draw["reserved"][0]])
        failures.append("reserved game accepted into index")
    except SystemExit:
        pass
    if failures:
        print(f"SELFTEST FAILED — {len(failures)}:")
        for f in failures:
            print("  " + f)
        return 1
    print(f"retrieval selftest OK — {len(index)} records over the iteration slice; typed "
          f"queries (state/terminal), ablation fallback, LOGO + reserved guards, floors")
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
