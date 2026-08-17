#!/usr/bin/env python3
"""Slice-4 sealed grader — five axes, worksheets for judgment, mechanics for the rest.

`notes/qwen-3.8-slice4-design.md` → pilot grading + PROPOSED pre-registration. The
grader is the ONLY code allowed to read `logs/s4_sealed/`, and it refuses to run
until two markers exist:

  logs/s4_sealed/FROZEN.json    — written by `--freeze` BEFORE any pilot generation:
                                  hashes every sealed gold file + records git state.
  <answers file>                — the runner's cells.json; answers are frozen by
                                  existing.

Axes:
  1 observation consistency  MECHANICAL  every cited evidence id resolves (existence,
                                         stated as existence — support is axis 2's
                                         judgment)
  2 source-correct goal      WORKSHEET   model claims beside sealed gold paraphrase +
                                         constraint checklist; operator fills verdicts
  3 counterfactual validity  WORKSHEET   sealed counterfactual boards beside the
                                         model's conditions and predicted
                                         counterexample
  4 confidence calibration   MECHANICAL  Brier + top-rank accuracy, once axis-2
                                         per-hypothesis verdicts are filled
  5 plan success             MECHANICAL  execute goal_directed_plan from a fresh
                                         engine start under the preregistered action
                                         budget; success = level advance

Terminal-evidence classification {initially-present, probe-acquired, never-present}
is computed once axis-2 verdicts exist, from pre-probe vs final answers + probe log.

Gold file schema (content written at freeze time, per game):
  logs/s4_sealed/gold/<game>.json = {
    "paraphrase": "...", "constraints": ["shape", "colour", ...],
    "counterfactuals": [{"board": [[...]], "objective_holds": true/false,
                          "note": "..."}],
    "familiarity": "operator statement for the exposure control"
  }

Run:
  .venv/bin/python agent/harness/s4_grade.py --freeze          # before the pilot
  .venv/bin/python agent/harness/s4_grade.py --answers <cells.json>
  .venv/bin/python agent/harness/s4_grade.py --answers <cells.json> --tally
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HARNESS = Path(__file__).resolve().parent
if str(HARNESS) not in sys.path:
    sys.path.insert(0, str(HARNESS))

ROOT = Path(__file__).resolve().parents[2]
SEALED = ROOT / "logs/s4_sealed"
GOLD = SEALED / "gold"
FROZEN = SEALED / "FROZEN.json"
PLAN_BUDGET_DEFAULT = 150  # (w) preregistration: 2x autonomous completion length where known


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def freeze() -> int:
    """Hash every sealed gold file; after this, edits to gold are drift, not truth."""
    require(GOLD.is_dir() and any(GOLD.glob("*.json")),
            f"no gold files in {GOLD} — write them first (schema in the docstring)")
    import subprocess

    files = {p.name: sha256_file(p) for p in sorted(GOLD.glob("*.json"))}
    blind = SEALED / "blind_map.json"
    payload = {
        "frozen_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "gold_files": files,
        "blind_map_sha256": sha256_file(blind) if blind.exists() else None,
        "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     capture_output=True, text=True).stdout.strip(),
    }
    require(not FROZEN.exists(), f"{FROZEN} already exists — the freeze is append-only")
    FROZEN.write_text(json.dumps(payload, indent=1))
    print(f"FROZEN {len(files)} gold files at {payload['git_commit'][:9]}")
    return 0


def verify_freeze() -> dict[str, Any]:
    require(FROZEN.exists(), "sealed gold is not frozen — run --freeze BEFORE the pilot")
    frozen = json.loads(FROZEN.read_text())
    for name, digest in frozen["gold_files"].items():
        require(sha256_file(GOLD / name) == digest,
                f"SEALED DRIFT: {name} changed after the freeze")
    return frozen


def blind_to_game() -> dict[str, str]:
    mapping = json.loads((SEALED / "blind_map.json").read_text())
    return {v: k for k, v in mapping.items()}


def axis1_consistency(cell: dict[str, Any]) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    cited: list[str] = []
    for h in answer.get("hypotheses") or []:
        cited += [str(x) for x in (h.get("evidence_for") or [])]
        cited += [str(x) for x in (h.get("evidence_against") or [])]
    pages = {f"page {p}" for p in range(1, (cell.get("packet_pages") or 0) + 1)}
    def resolves(ref: str) -> bool:
        r = ref.strip().lower()
        return (
            r in pages
            or r.startswith("page")
            or (len(r) >= 6 and r[0] in "sk" and r[1:6].isdigit())
        )
    resolved = [c for c in cited if resolves(c)]
    return {"cited": len(cited), "resolved": len(resolved),
            "unresolved": [c for c in cited if not resolves(c)][:10],
            "note": "existence check only; support is axis 2"}


def axis2_worksheet(cell: dict[str, Any], gold: dict[str, Any] | None) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    hypotheses = answer.get("hypotheses") or []
    return {
        "model_best_goal": (answer.get("best_goal") or {}).get("plain_causal_condition"),
        "model_structured_factors": (answer.get("best_goal") or {}).get("structured_factors"),
        "model_hypotheses": [
            {"index": i, "probability": h.get("probability"),
             "sufficient_condition": h.get("sufficient_condition")}
            for i, h in enumerate(hypotheses)
        ],
        "sealed_paraphrase": (gold or {}).get("paraphrase"),
        "sealed_constraints": (gold or {}).get("constraints"),
        "VERDICT_correct_in_kind": None,
        "VERDICT_constraints_present": None,
        "VERDICT_per_hypothesis_true": [None] * len(hypotheses),
    }


def axis3_worksheet(cell: dict[str, Any], gold: dict[str, Any] | None) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    return {
        "model_conditions": [(h.get("sufficient_condition"), h.get("predicted_counterexample"))
                             for h in answer.get("hypotheses") or []],
        "sealed_counterfactuals": [
            {"index": i, "objective_holds": c.get("objective_holds"), "note": c.get("note")}
            for i, c in enumerate((gold or {}).get("counterfactuals") or [])
        ],
        "VERDICT_survives_counterfactuals": None,
    }


def axis4_calibration(worksheet2: dict[str, Any]) -> dict[str, Any]:
    verdicts = worksheet2.get("VERDICT_per_hypothesis_true")
    hyps = worksheet2.get("model_hypotheses") or []
    if not verdicts or any(v is None for v in verdicts):
        return {"status": "pending axis-2 per-hypothesis verdicts"}
    brier = sum(
        (float(h.get("probability") or 0.0) - (1.0 if v else 0.0)) ** 2
        for h, v in zip(hyps, verdicts)
    ) / max(1, len(hyps))
    top = max(range(len(hyps)), key=lambda i: float(hyps[i].get("probability") or 0.0))
    return {"brier": round(brier, 4), "top_rank_correct": bool(verdicts[top])}


def axis5_plan(cell: dict[str, Any], game: str, budget: int, execute: bool) -> dict[str, Any]:
    answer = cell.get("final_answer") or {}
    plan = answer.get("goal_directed_plan") or []
    record: dict[str, Any] = {"plan_length": len(plan), "action_budget": budget}
    if not plan:
        record["status"] = "no plan given"
        return record
    if not execute:
        record["status"] = "not executed (pass --execute-plans)"
        return record
    from s4_recapture import Engine  # engine allowed on the sealed/grading side

    engine = Engine(game)
    handle = engine.new()
    completed = False
    steps = 0
    start_level = None
    for step in plan[:budget]:
        action = (step or {}).get("action") or {}
        aid = action.get("id")
        if not (isinstance(aid, int) and 0 <= aid <= 7):
            record["invalid_at"] = steps
            break
        click = action.get("click")
        y, x = (click if click else (None, None))
        response = engine.perform(handle, (aid, y, x))
        steps += 1
        frames = engine.frames(response)
        state = getattr(response, "state", None)
        level = getattr(response, "level", None)
        if start_level is None:
            start_level = level
        if (level is not None and start_level is not None and level > start_level) or (
            str(state) in ("WIN", "GameState.WIN")
        ):
            completed = True
            break
    record.update(status="executed", steps_executed=steps, level_advanced=completed)
    return record


def grade(answers_path: Path, execute_plans: bool, tally: bool) -> int:
    frozen = verify_freeze()
    doc = json.loads(answers_path.read_text())
    games = blind_to_game()
    out = {
        "note": "slice-4 sealed grading",
        "answers": str(answers_path),
        "answers_sha256": sha256_file(answers_path),
        "frozen_utc": frozen["frozen_utc"],
        "cells": [],
    }
    for cell in doc.get("cells", []):
        bid = cell.get("game_blind")
        game = games.get(bid, bid)
        gold_path = GOLD / f"{game}.json"
        gold = json.loads(gold_path.read_text()) if gold_path.exists() else None
        w2 = axis2_worksheet(cell, gold)
        graded = {
            "game_blind": bid,
            "arm": cell.get("arm"),
            "outcome": cell.get("outcome"),
            "missing_observation": cell.get("outcome") != "answered",
            "axis1_consistency": axis1_consistency(cell),
            "axis2_worksheet": w2,
            "axis3_worksheet": axis3_worksheet(cell, gold),
            "axis4_calibration": axis4_calibration(w2),
            "axis5_plan": axis5_plan(cell, game, PLAN_BUDGET_DEFAULT, execute_plans),
            "answer_changed_after_probes": (
                None if cell.get("arm") != "P" or cell.get("outcome") != "answered"
                else json.dumps(cell.get("pre_probe_answer", {}).get("best_goal"))
                != json.dumps((cell.get("final_answer") or {}).get("best_goal"))
            ),
        }
        out["cells"].append(graded)
    graded_path = answers_path.with_name(answers_path.stem + "_graded.json")
    graded_path.write_text(json.dumps(out, indent=1))
    print(f"wrote {graded_path} ({len(out['cells'])} cells)")
    if tally:
        answered = [c for c in out["cells"] if not c["missing_observation"]]
        print(f"answered {len(answered)}/{len(out['cells'])}; "
              f"axis-2 verdicts pending: "
              f"{sum(1 for c in answered if c['axis2_worksheet']['VERDICT_correct_in_kind'] is None)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--execute-plans", action="store_true")
    parser.add_argument("--tally", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        return freeze()
    if args.answers:
        return grade(args.answers, args.execute_plans, args.tally)
    parser.error("pass --freeze (before the pilot) or --answers <cells.json>")
    return 2


if __name__ == "__main__":
    sys.exit(main())
