"""One loader for a run directory's artifacts, keyed by pass.

WHY THIS EXISTS
---------------
Four modules independently parsed `benchmark.json`, `artifacts/*_events.jsonl` and
`*_requests.jsonl`: `s1c_measure.py`, `s1d_label.py`, `make_run_tables.py`,
`analyse_reference_run.py`. On 2026-07-26 the same defect had to be fixed in two of them
separately — both read `game_runs[0]` and applied one game's identity, human baseline and terminal
state to every game in a chunk directory. It corrupted the Kaggle reference episode file: 25 episodes
from 25 games all scored against `sk48`'s baselines, median action ratio 0.90x where the truth was
2.03x.

This module makes that defect unrepresentable rather than merely fixed. There is no way to ask it for
"the run's game" — every accessor is per PASS key (`<game>_p<N>`), matching the artifact stems.

WHAT IT ENCODES, EACH FROM A MEASURED FAILURE
---------------------------------------------
* **game_runs is a mapping, never a list index.** `game_runs` is not ordered like the event files, so
  `[0]` was not even reliably "the first game".
* **The mapping key is the PASS, not the game (S1-E11).** Under `n_passes > 1` the vendor appends one
  `game_run` per (pass, game) and every pass repeats the same `game_id` — `taaf/benchmark.py` checks id
  uniqueness only on `pass_idx == 0`, commenting that "later passes legitimately repeat the same ids".
  Keying by `game_id` therefore kept only the LAST pass and silently served its action counts, terminal
  state and wall clock as p0's, p1's and p2's alike. That is the same one-identity-for-many-runs defect
  described above, re-entering through the pass axis, and it would have corrupted all three passes of
  the S1-E11 corpus. `game_runs` is passes-major, so the k-th occurrence of a game id IS its pass k.
* **A `game_run` entry means SCHEDULED, not ran.** The killed 25-game directory lists 25 entries
  against 4 event files. Games with no event file are reported, not silently absorbed.
* **Request logs are per pass, with a single-game fallback.** The harness writes
  `<game>_p<N>_requests.jsonl` only when a directory holds more than one game; with exactly one it
  writes a run-level `requests.jsonl` and no per-pass file. Globbing `*requests.jsonl` pools every
  game's reasoning into shared `analysis_step` buckets — which would hand a rater three other games'
  reasoning as evidence. Scoping strictly to the per-pass file instead produced *evidence-less*
  episodes for every concurrency-1 run. So: prefer the per-pass file; fall back to the run-level file
  ONLY when the directory holds exactly one pass, where attribution is unambiguous; otherwise refuse
  and say so.
* **Per-level action counts come from `benchmark.json`, not from the event `level` field.** The action
  that CLEARS a level is stamped with the NEW level in the event stream while `benchmark.json` counts
  it toward the level it completed. Measured on `ar25-0c556536`: benchmark `[30, 80]` against event
  stream `L1: 29, L2: 81`. Deriving counts from the event field alone makes a cleared level's total
  one low and the next level's one high — and it biases exactly the L2+ episodes S1-E2 says to rank
  the build order on.
* **Conclusion is decided by wall-clock, not by the recorded state (S1-E9).** `gave_up` versus
  `cancelled` reflects whether a request happened to be in flight at the deadline, which is a function
  of generation length. 0 of 25 reference games finished early yet all recorded `gave_up`; our
  identically budget-terminated games recorded `cancelled`.
"""

from __future__ import annotations

import glob
import json
import re
from pathlib import Path

AGENT_FINISHED = {"gave_up", "won"}
BUDGET_TOLERANCE = 0.98


def game_of(pass_key: str) -> str:
    """`bp35-0a0ad940_p0` -> `bp35-0a0ad940`."""
    return re.sub(r"_p\d+$", "", pass_key)


def _load_json(p: Path):
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


class RunArtifacts:
    """Everything a run directory holds, addressable only per pass (`<game>_p<N>`)."""

    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.name = self.run_dir.name
        bench = _load_json(self.run_dir / "benchmark.json") or {}
        # Passes-major: `game_runs[pass_idx * n_games + g]`. Counting occurrences recovers the pass
        # index without trusting `n_passes` to agree with the list length on a truncated run.
        self._runs: dict[str, dict] = {}
        seen: dict[str, int] = {}
        for gr in (bench.get("game_runs") or []):
            gid = gr.get("game_id")
            if not gid:
                continue
            idx = seen.get(gid, 0)
            seen[gid] = idx + 1
            self._runs[f"{gid}_p{idx}"] = gr
        self.n_passes_declared = bench.get("n_passes")
        self._config = _load_json(self.run_dir / "run_config.json") or {}
        self._events: dict[str, list] = {}
        for f in sorted(glob.glob(str(self.run_dir / "artifacts" / "*_events.jsonl"))):
            key = Path(f).name.split("_events")[0]
            self._events[key] = [json.loads(l) for l in open(f)]
        self.warnings: list[str] = []
        for pk in self._events:
            if pk not in self._runs:
                self.warnings.append(
                    f"{pk}: no game_run in benchmark.json — no baseline or terminal state")

    # ---------------------------------------------------------------- structure

    @property
    def passes(self) -> list[str]:
        return sorted(self._events)

    @property
    def scheduled_not_run(self) -> list[str]:
        """Pass keys with a `game_run` but no event file. Per pass: under `n_passes > 1` a game can
        complete p0 and never reach p2, and collapsing to the game id would hide that."""
        return sorted(pk for pk in self._runs if pk not in self._events)

    @property
    def concurrency(self):
        c = self._config
        return c.get("effective_concurrent_jobs") or c.get("concurrent_jobs") or c.get("concurrency")

    @property
    def model(self):
        return self._config.get("model") or (self._config.get("deployment") or {}).get("model")

    @property
    def budget_seconds(self):
        m = self._config.get("max_runtime_minutes_per_game")
        return float(m) * 60.0 if m else None

    # ---------------------------------------------------------------- per pass

    def game_run(self, pass_key: str) -> dict:
        """The `game_run` for ONE pass. `pass_key` is `<game>_p<N>`, never a bare game id — a bare id
        would silently miss and return {}, which reads as "no data" rather than "wrong key"."""
        return self._runs.get(pass_key, {})

    def events(self, pass_key: str) -> list:
        return self._events.get(pass_key, [])

    def actions_per_level(self, pass_key: str) -> list:
        """From benchmark.json — authoritative. See the class docstring on the clearing action."""
        return self.game_run(pass_key).get("actions_per_level") or []

    def baselines(self, pass_key: str) -> list:
        """Human baselines. Identical across passes of one game, but read per pass so a missing pass
        yields [] rather than another pass's numbers."""
        return self.game_run(pass_key).get("base_actions_per_level") or []

    def actions_on_level(self, pass_key: str, level) -> int | None:
        """Actions spent on a 1-indexed level, reconciled against benchmark.json."""
        apl = self.actions_per_level(pass_key)
        try:
            i = int(level) - 1
        except (TypeError, ValueError):
            return None
        return apl[i] if 0 <= i < len(apl) else None

    def baseline_for(self, pass_key: str, level):
        bal = self.baselines(pass_key)
        try:
            i = int(level) - 1
        except (TypeError, ValueError):
            return None
        return bal[i] if 0 <= i < len(bal) else None

    def wallclock(self, pass_key: str):
        return self.game_run(pass_key).get("final_wallclock_seconds")

    def budget_terminated(self, pass_key: str):
        """True / False / None. None means UNKNOWN, not "no".

        `run_config.json` is absent from Kaggle kernel output, so `budget_seconds` is None there and
        an earlier version returned False — asserting "not censored" for 25 episodes that each ran the
        full 132-minute budget. `latency_or_budget` is defined on exactly that fact, so a False here
        misleads the rater about the one category it decides.
        """
        b, w = self.budget_seconds, self.wallclock(pass_key)
        if b is None or w is None:
            return None
        return w >= BUDGET_TOLERANCE * b

    def concluded(self, pass_key: str) -> bool:
        """S1-E9: the agent finished, OR the uniform pre-registered budget expired."""
        return bool(self.game_run(pass_key).get("state") in AGENT_FINISHED
                    or self.budget_terminated(pass_key))

    @staticmethod
    def _tool_code(msg: dict) -> list:
        codes = []
        for tc in (msg.get("tool_calls") or []):
            try:
                codes.append(json.loads(
                    tc.get("function", {}).get("arguments", "")).get("code", ""))
            except Exception:  # noqa: BLE001
                pass
        return codes

    def requests(self, pass_key: str) -> dict:
        """analysis_step -> reasoning and tool calls, for ONE pass. See the class docstring.

        TWO LOG SHAPES, because the serving stacks differ. Measured 2026-07-27:

          mlx_vlm (local)  response rows carry `response_message` with reasoning/content/tool_calls.
          vLLM (Kaggle)    response rows carry NO `response_message` — only `finish_reason`. The
                           model's output appears as `assistant` messages inside the REPLAYED
                           CONVERSATION of subsequent rows, because every request resends the whole
                           history.

        Reading only `response_message` therefore returned EMPTY evidence for all 25 Kaggle episodes
        while `evidence_steps_with_reasoning` still counted 22 — it was counting response rows, not
        reasoning. Silent, and it would have been labelled on.

        Replay attribution: an assistant message that appears for the FIRST time in row R was produced
        by the request immediately preceding R, so it is attributed to the PREVIOUS row's
        analysis_step. That is exact across turn boundaries too — the last turn of step N first
        appears in the replay of step N+1's first request, and the row before it is still step N.
        """
        per_pass = self.run_dir / f"{pass_key}_requests.jsonl"
        run_level = self.run_dir / "requests.jsonl"
        if per_pass.exists():
            files = [per_pass]
        elif len(self._events) == 1 and run_level.exists():
            files = [run_level]
        else:
            if run_level.exists():
                self.warnings.append(
                    f"{pass_key}: no per-pass request log and {len(self._events)} passes present — "
                    f"the run-level log cannot be attributed; evidence will be EMPTY")
            return {}

        by_step: dict = {}
        direct = 0
        seen: set = set()
        prev_step = None
        for f in files:
            for line in open(f):
                try:
                    r = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue

                msg = r.get("response_message")
                if r.get("event") == "response" and msg:
                    direct += 1
                    by_step.setdefault(r.get("analysis_step"), []).append({
                        "finish_reason": r.get("finish_reason"),
                        "reasoning": (msg.get("reasoning") or "")[:4000],
                        "content": (msg.get("content") or "")[:4000],
                        "tool_code": self._tool_code(msg),
                        "usage": r.get("usage"),
                    })
                else:
                    # Replay path. Walk the conversation for assistant turns not yet emitted.
                    for m in (r.get("messages") or []):
                        if m.get("role") != "assistant":
                            continue
                        key = json.dumps([m.get("reasoning"), m.get("content"),
                                          m.get("tool_calls")], sort_keys=True)
                        if key in seen:
                            continue
                        seen.add(key)
                        by_step.setdefault(prev_step if prev_step is not None
                                           else r.get("analysis_step"), []).append({
                            "finish_reason": r.get("finish_reason"),
                            "reasoning": (m.get("reasoning")
                                          or m.get("reasoning_content") or "")[:4000],
                            "content": (m.get("content") or "")[:4000],
                            "tool_code": self._tool_code(m),
                            "usage": r.get("usage"),
                        })
                prev_step = r.get("analysis_step")

        if not direct and seen:
            self.warnings.append(
                f"{pass_key}: no `response_message` in the log (vLLM-side shape) — "
                f"reasoning recovered from {len(seen)} replayed assistant turns")
        return by_step


def load_run(run_dir) -> RunArtifacts:
    return RunArtifacts(Path(run_dir))
