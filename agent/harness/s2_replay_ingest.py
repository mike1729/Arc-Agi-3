"""Ingest the 340 ARC Prize human replay recordings into a per-session table and per-level costs.

Source: the ARC-AGI-3 Public Demo human testing release (ARC Prize, 2026-04-14), unpacked to
`data/human_replays/kaggle_mirror/public_games-dataset/<env>/<guid>.recording.jsonl`. The Kaggle
mirror `magicsword001/arc-agi-3-public-demo-human-testing` was verified md5-identical to the official
Google Drive zip, file for file, on 2026-07-28 — 340/340, no mismatches. Either copy works.

THE COUNT IS 340, NOT 342 — AND THE GAP IS FULLY ACCOUNTED FOR
--------------------------------------------------------------
The release blog's per-game table says 342 plays and 145 solves, and gives g50t 14 plays / 3 solves.
The archive ships 340 recordings and 144 wins, with g50t at 12 / 2. Every other game matches exactly.
Three independent counts agree that precisely two g50t sessions are absent, one of them a solve:

    plays    342 blog  =  340 recordings + 2 absent g50t
    solves   145 blog  =  144 archive wins + 1 absent g50t solve
    ratings  144 rows  =  143 that join a recording + 1 orphan — and that orphan is
                          d2aef7cd/g50t, fun 5 hard 5, a rated solve with no recording

So the gap is not mirror corruption, not a parsing artifact, and not spread thinly across games. It
is two missing g50t files, and `testing_feedback_ratings.csv` still carries the fingerprint of one.

That matters because 342 is not a number anything here can be divided by. Every denominator this
script emits is a count of recordings that exist. If a per-game normalizer ever reads 14 for g50t, it
came from the blog and not from data — and g50t's solve rate is understated by the loss.

TRAP 1 — `actions_by_level` IS CUMULATIVE
-----------------------------------------
The field looks like per-level action counts and is described that way in the third-party HuggingFace
card ("a nested list breaking down the action counts at each specific level"). It is not. Each entry
is `[level, total_actions_elapsed_when_that_level_was_completed]`, measured from the start of the
session:

    r11l  actions_by_level = [[1,13],[2,40],[3,70],[4,88],[5,126],[6,152]]   total_actions = 152
                              ^^^^ level 1 cost 13          ^^^^^ level 6 ENDS at 152, cost 26

Read literally, that session's level 6 costs 152 actions — an 6x overstatement, and the error grows
with level index, so it does not look like noise. It looks like "later levels are harder", which is
also true, which is what makes it dangerous. Per-level cost is the first difference; this module
computes it once, in `_per_level_costs`, and nothing downstream should touch the raw field.

The competition's own `environment_files/<env>/<hash>/metadata.json` uses the OTHER convention:
`baseline_actions` is per-level already (cd82 = [55, 8, 41, 21, 23, 23] — not monotonic, so it cannot
be cumulative). Two conventions, one word. `--check-baselines` compares the differenced medians
against it rather than assuming they agree.

TRAP 2 — THREE SPELLINGS OF "NO LEVELS COMPLETED"
------------------------------------------------
`actions_by_level` arrives as `None` (lp85, sc25), as `[[]]` (bp35, ka59), and as `[[...]]` when
populated — an outer list per play wrapping the real list. A `for level, cum in abl` written against
any one of those crashes or silently iterates the wrong depth on the others. `_per_level_costs`
normalizes all three.

TRAP 3 — A CARD CAN DESCRIBE MORE PLAYS THAN THE FILE RECORDS
-------------------------------------------------------------
The summary's `cards[game_id]` holds PARALLEL ARRAYS — `guids`, `states`, `actions`,
`levels_completed`, `resets`, `actions_by_level` — one slot per play. 337 of the 340 recordings have
one slot. Three have two:

    tn36/0268d6a8   guids = [59e160e8, 0268d6a8]   actions = [0, 498]   states = [NOT_FINISHED, GAME_OVER]
                            ^^^^^^^^ an abandoned stub with no recording file of its own

Taking slot 0 is wrong for exactly these three and silently right for the other 337 — the failure
mode is a handful of sessions reporting someone else's zero-action abandonment as their own result.
The slot is selected by matching the FILENAME guid against `guids`, never by position.

`guids` can also be empty outright (every sc25 session), so the filename remains the only reliable
identity. When `guids` is empty and the card holds one play, slot 0 is unambiguous and is used.

COUNT FILES, NOT PLAYS
----------------------
Those parallel arrays total 343 plays across 340 files, and the extra three are stubs. Per game,
against the blog table: g50t has 12 files / 12 plays where the blog says 14; lp85 has 54 files but 56
plays; tn36 has 14 files but 15. Every other game agrees exactly. So the blog's per-game numbers track
recording counts, not play slots — and g50t is the one game where two sessions are simply absent.

The unit of observation here is the recording. This script emits one row per file.

SHAPE OF A RECORDING
--------------------
JSONL. Every line but the last is one action:

    {timestamp, data:{game_id, frame, state, levels_completed, win_levels,
                      action_input:{id, data, reasoning}, guid, full_reset, available_actions}}

The LAST line is a different object — a session summary carrying `won`, `played`, `total_actions`,
and a `cards` dict with `actions_by_level`, `resets`, `states`. Uniform-schema iteration breaks on it.

This pass deliberately does not parse the action lines. It needs the first line, the last line, and a
newline count, so it seeks instead of streaming 6.4 GB — the whole corpus reads in seconds rather than
minutes. `frame` payloads are never materialized. The click-salience pass will need the action lines
and should stream them per file; it must not load a recording whole (bp35 sessions reach 100 MB).

DO NOT RECONSTRUCT `actions` FROM THE LINE COUNT
------------------------------------------------
The obvious integrity check — "one line per action, plus the summary" — is wrong, and wrong
inconsistently. Scanning all 340 recordings and every action id:

    295 sessions   actions == action_lines - 1 - undos     (leading RESET and ACTION7/Undo unscored)
     23 sessions   actions == action_lines                 (no leading RESET line at all — all 12 of
                                                             cn04, plus a few dc22/lf52/m0r0/tr87)
     22 sessions   actions == action_lines - 1             (bp35 and lf52, undos scored after all)

So whether Undo counts toward the action total varies by game, and whether a leading RESET frame is
even recorded varies by client. Mid-session RESETs are always scored — sessions with 39 resets show
the same offset as sessions with none.

`actions` and `actions_by_level` are internally consistent with each other, which is what the
per-level costs depend on, so the declared value is authoritative and the line count is recorded as
`line_delta` rather than asserted. `--check-baselines` is the real validation. Differenced UPPER medians tie
`baseline_actions` exactly on 167 of 183 game-levels, which identifies `baseline_actions` as the
upper median per-level cost over these sessions — the benchmark's own definition, "the upper median
human (by fewest actions) per level". Sixteen game-levels still differ, and the residual is not
scattered: it falls on lp85 (7), vc33 (6) and g50t (3) and nowhere else. Two of those three are the
games with already-known provenance defects — g50t is missing two sessions including a solve, so its
baseline was set over a cohort we do not hold, and lp85's recordings come from the July 2025 preview
build. vc33 is unexplained. So the identification holds everywhere the corpus is complete, and the
exceptions are where it is known not to be; state it with that qualification, never flatly.

Action ids are encoded as STRINGS ("ACTION5") rather than ints in five games — exclusively in cn04,
and mixed with int sessions in dc22, lf52, m0r0 and tr87 — which tracks the client version rather
than the game, since the string sessions are also the ones recording no leading RESET frame. Anything
bucketing by action id, click salience above all, has to handle both.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "data/human_replays/kaggle_mirror/public_games-dataset"
RATINGS = REPO / "data/human_replays/official/testing_feedback_ratings.csv"
ENVS = REPO / "data/environment_files"


def _last_line(path: Path) -> dict:
    """Read the final JSON line without reading the file.

    Recordings reach 100 MB. Walk backwards in blocks until a newline separates the tail from
    something earlier, which is the only way to know the last line is complete.
    """
    with path.open("rb") as f:
        f.seek(0, 2)
        end = f.tell()
        block = 65536
        span = 0
        while True:
            span = min(span + block, end)
            f.seek(end - span)
            buf = f.read(span)
            lines = buf.strip().split(b"\n")
            if len(lines) > 1 or span == end:
                return json.loads(lines[-1])


def _first_line(path: Path) -> dict:
    with path.open("rb") as f:
        return json.loads(f.readline())


def _count_lines(path: Path) -> int:
    """Newline count. Valid because JSONL forbids raw newlines inside a record."""
    n = 0
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            n += chunk.count(b"\n")
    return n


def _play_slot(card: dict, guid: str) -> tuple[int | None, int]:
    """Locate this recording's slot in the card's parallel arrays. Returns (slot, n_plays).

    `guids` is the reliable key but is sometimes empty and sometimes absent entirely. The fallback is
    not positional: a stub play has zero actions and therefore cannot have completed a level, so when
    exactly one play acted at all, that play is this recording. Anything else is unresolvable and is
    reported rather than guessed — picking wrong would attribute someone else's abandonment here.
    """
    guids = card.get("guids") or []
    acts = card.get("actions") or []
    n = max(len(guids), len(card.get("states") or []), len(acts), 1)
    if guid in guids:
        return guids.index(guid), n
    if n == 1:
        return 0, n
    acting = [i for i, a in enumerate(acts) if a]
    if len(acting) == 1:
        return acting[0], n
    return None, n


def _slot(card: dict, key: str, slot: int):
    """Read one play's value out of a parallel array.

    `actions_by_level` is not always as long as its siblings — a zero-action play is sometimes
    included as `[]` and sometimes omitted outright. When it is short but holds a single entry, that
    entry belongs to the only play that acted, which is the slot the caller already resolved.
    """
    seq = card.get(key)
    if not isinstance(seq, list):
        return None
    if slot < len(seq):
        return seq[slot]
    if len(seq) == 1 and sum(1 for a in (card.get("actions") or []) if a) == 1:
        return seq[0]
    return None


def _per_level_costs(actions_by_level) -> tuple[dict[int, int], list, str]:
    """Difference one play's cumulative pairs into per-level costs.

    Takes the already-slotted value, not the outer per-play list. Returns (costs_by_level,
    normalized_pairs, form) where form names which of the three spellings was seen, so the caller can
    report the distribution rather than assume it.
    """
    if actions_by_level is None:
        return {}, [], "none"
    if not actions_by_level:
        return {}, [], "empty_list"
    costs, prev = {}, 0
    for level, cumulative in actions_by_level:
        costs[int(level)] = int(cumulative) - prev
        prev = int(cumulative)
    return costs, [[int(a), int(b)] for a, b in actions_by_level], "populated"


def _ratings() -> dict[str, dict]:
    if not RATINGS.exists():
        return {}
    with RATINGS.open() as f:
        return {r["session_id"]: {"fun": int(r["fun"]), "hard": int(r["hard"])}
                for r in csv.DictReader(f)}


def _env_metadata() -> dict[str, dict]:
    """Per-game competition metadata, keyed by the four-character env id."""
    out = {}
    for meta in sorted(ENVS.glob("*/*/metadata.json")):
        d = json.loads(meta.read_text())
        out[meta.parent.parent.name] = d
    return out


def ingest(out: Path, check_baselines: bool) -> int:
    if not CORPUS.is_dir():
        print(f"corpus not found: {CORPUS}")
        return 1
    ratings = _ratings()
    meta = _env_metadata()

    sessions, problems, empty_forms = [], [], {"none": 0, "empty_list": 0, "populated": 0}
    for path in sorted(CORPUS.glob("*/*.recording.jsonl")):
        env = path.parent.name
        guid = path.name.split(".")[0]
        summary = _last_line(path)["data"]
        cards = summary.get("cards") or {}
        if len(cards) != 1:
            problems.append(f"{env}/{guid}: {len(cards)} cards, expected 1")
            continue
        game_id, card = next(iter(cards.items()))

        slot, n_plays = _play_slot(card, guid)
        if slot is None:
            problems.append(f"{env}/{guid}: {n_plays} plays in card, filename guid not in {card.get('guids')}")
            continue
        if n_plays > 1:
            others = [g[:8] for g in (card.get("guids") or []) if g != guid]
            problems.append(f"{env}/{guid}: card holds {n_plays} plays; slot {slot} taken, "
                            f"stub(s) {others} ignored (they have no recording of their own)")

        costs, cumulative, form = _per_level_costs(_slot(card, "actions_by_level", slot))
        empty_forms[form] += 1
        n_lines = _count_lines(path)
        # Per-play, not the card/summary aggregate: with two plays in a card the top-level
        # total_actions sums both, and attributing that sum to this recording inflates it.
        total_actions = _slot(card, "actions", slot)
        if total_actions is None:
            total_actions = int(summary.get("total_actions", 0))
        total_actions = int(total_actions)
        state = _slot(card, "states", slot)

        # line_delta is DATA, not an assertion — see the module docstring. Its per-game distribution
        # is reported so the RESET/Undo convention stays visible instead of being silently averaged.
        first = _first_line(path)["data"]
        id_type = type(((first.get("action_input") or {}).get("id"))).__name__

        if cumulative and cumulative[-1][1] > total_actions:
            problems.append(f"{env}/{guid}: last cumulative {cumulative[-1][1]} > total {total_actions}")
        if any(b <= a for (_, a), (_, b) in zip(cumulative, cumulative[1:])):
            problems.append(f"{env}/{guid}: non-monotonic cumulative actions")
        if n_plays == 1 and int(summary.get("played", 1)) != 1:
            problems.append(f"{env}/{guid}: summary played={summary.get('played')} but card holds 1 play")
        if env in meta and meta[env].get("game_id") != game_id:
            problems.append(f"{env}/{guid}: game_id {game_id} != competition {meta[env].get('game_id')}")

        levels = _slot(card, "levels_completed", slot)
        sessions.append({
            "env": env,
            "guid": guid,
            "game_id": game_id,
            "won": int(state == "WIN"),
            "state": state,
            "levels_completed": int(levels if levels is not None else summary.get("levels_completed", 0)),
            "total_actions": total_actions,
            "resets": _slot(card, "resets", slot),
            "action_lines": n_lines - 1,
            "line_delta": (n_lines - 1) - total_actions,
            "action_id_type": id_type,
            "plays_in_card": n_plays,
            "cumulative_by_level": cumulative,
            "per_level_actions": {str(k): v for k, v in sorted(costs.items())},
            "rating": ratings.get(guid),
        })

    # Per game x level. Only sessions that actually completed the level contribute a cost, so n
    # falls away with depth — that decay is the difficulty signal and is reported, not smoothed.
    per_level: dict[str, dict] = {}
    for s in sessions:
        for level, cost in s["per_level_actions"].items():
            per_level.setdefault(s["env"], {}).setdefault(level, []).append(cost)
    # UPPER median, not the ordinary one. The benchmark defines its baseline as "the upper median
    # human (by fewest actions) per level" — with an even sample the better of the two middle
    # performers, never their average. `statistics.median` averages them and so invents an action
    # count no human achieved, which for an even sample is usually not an integer at all. Measured
    # against the competition's own baselines the difference is not cosmetic: upper median ties
    # exactly on 167 of 183 game-levels, the ordinary median on 94, the lower median on 95. The
    # plain median is retained beside it as a descriptive statistic and is NOT the scoring baseline.
    per_level_stats = {
        env: {
            level: {
                "n": len(v),
                "upper_median": statistics.median_high(v),
                "median": statistics.median(v),
                "mean": round(statistics.fmean(v), 1),
                "min": min(v),
                "max": max(v),
            }
            for level, v in sorted(levels.items(), key=lambda kv: int(kv[0]))
        }
        for env, levels in sorted(per_level.items())
    }

    baseline_check = {}
    if check_baselines:
        for env, levels in per_level_stats.items():
            baseline = (meta.get(env) or {}).get("baseline_actions")
            if not baseline:
                continue
            rows = []
            for i, b in enumerate(baseline, start=1):
                st = levels.get(str(i))
                rows.append({
                    "level": i,
                    "baseline": b,
                    "upper_median": st["upper_median"] if st else None,
                    "median": st["median"] if st else None,
                    "n": st["n"] if st else 0,
                })
            baseline_check[env] = rows

    # Agreement between the differenced medians and the competition's own baseline_actions. This is
    # the validation that the cumulative->per-level differencing is right: reading the field
    # literally would put these ratios far from 1 and rising with level index.
    ratios = [r["upper_median"] / r["baseline"]
              for env in baseline_check for r in baseline_check[env]
              if r["upper_median"] and r["baseline"]]
    agreement = {}
    if ratios:
        exact = sum(1 for env in baseline_check for r in baseline_check[env]
                    if r["upper_median"] == r["baseline"])
        agreement = {
            "game_levels_compared": len(ratios),
            "exact_ties": exact,
            "median_ratio": round(statistics.median(ratios), 3),
            "mean_ratio": round(statistics.fmean(ratios), 3),
            "min_ratio": round(min(ratios), 3),
            "max_ratio": round(max(ratios), 3),
        }

    conventions = {}
    for s in sessions:
        c = conventions.setdefault(s["env"], {"line_delta": {}, "action_id_type": set()})
        c["line_delta"][str(s["line_delta"])] = c["line_delta"].get(str(s["line_delta"]), 0) + 1
        c["action_id_type"].add(s["action_id_type"])
    conventions = {k: {"line_delta": v["line_delta"], "action_id_type": sorted(v["action_id_type"])}
                   for k, v in sorted(conventions.items())}

    payload = {
        "source": str(CORPUS.relative_to(REPO)),
        "sessions_ingested": len(sessions),
        "games": len({s["env"] for s in sessions}),
        "wins": sum(s["won"] for s in sessions),
        "actions_by_level_forms": empty_forms,
        "per_game_conventions": conventions,
        "baseline_agreement": agreement,
        "integrity_problems": problems,
        "sessions": sessions,
        "per_level_actions": per_level_stats,
        "baseline_check": baseline_check,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")

    won = sum(s["won"] for s in sessions)
    print(f"ingested {len(sessions)} sessions across {payload['games']} games — {won} wins")
    print(f"actions_by_level spellings: {empty_forms}")
    per_env = {}
    for s in sessions:
        per_env.setdefault(s["env"], []).append(s)
    print(f"\n{'env':<6}{'n':>4}{'won':>5}{'levels':>8}{'med.actions':>13}{'hard':>6}")
    for env in sorted(per_env):
        v = per_env[env]
        rated = [s["rating"]["hard"] for s in v if s["rating"]]
        print(f"{env:<6}{len(v):>4}{sum(s['won'] for s in v):>5}"
              f"{max(s['levels_completed'] for s in v):>8}"
              f"{statistics.median([s['total_actions'] for s in v]):>13.0f}"
              f"{(statistics.fmean(rated) if rated else float('nan')):>6.1f}")
    odd = {k: v for k, v in conventions.items()
           if len(v["line_delta"]) > 1 or v["action_id_type"] != ["int"]}
    if odd:
        print("\ngames whose recording convention differs (see docstring — do not 'fix' these):")
        for env, v in odd.items():
            print(f"   {env}: line_delta={v['line_delta']} action_id_type={v['action_id_type']}")
    if agreement:
        print(f"\nbaseline_actions agreement: median ratio {agreement['median_ratio']} over "
              f"{agreement['game_levels_compared']} game-levels, {agreement['exact_ties']} exact ties "
              f"(range {agreement['min_ratio']}–{agreement['max_ratio']})")
        print("   -> differencing confirmed; baseline_actions is the UPPER median per-level human cost")
    if problems:
        print(f"\n{len(problems)} integrity problem(s):")
        for p in problems[:20]:
            print(f"   {p}")
        if len(problems) > 20:
            print(f"   ... and {len(problems) - 20} more (all in {out})")
    else:
        print("\nno integrity problems")
    print(f"\nwrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/s2_replay_sessions.json")
    ap.add_argument("--check-baselines", action="store_true",
                    help="compare differenced per-level medians against metadata.json baseline_actions")
    args = ap.parse_args()
    return ingest(Path(args.out), args.check_baselines)


if __name__ == "__main__":
    raise SystemExit(main())
