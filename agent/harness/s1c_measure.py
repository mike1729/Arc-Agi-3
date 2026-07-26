"""S1-c measurement harness — everything S1 promises to measure, read from a closed run.

Reads a run directory and emits every S1-c threshold input. Script-generated only (§9); no number here
is typed by hand.

  per-action latency        p50/p95 from GameRun.history wallclock_seconds deltas
  legal-action reliability  attempted actions (parsed from tool code) vs executed action events
  throughput degradation    first-10-min action rate vs whole-run rate
  token accounting          generated / uncached-input per action

CONCURRENCY MUST BE RECORDED WITH EVERY LATENCY FIGURE (freeze §5). A p50 at concurrency 1 is not
comparable to one at concurrency 4, and the reference runs 32. It is read from run_config.json and
stamped into the output.

Run:  .venv/bin/python agent/harness/s1c_measure.py <run_dir> [--out logs/s1c_<name>.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import statistics
from pathlib import Path

# The duck emits game actions by calling action([...]) inside its Python tool.
# The duck calls action(actions=[...]) with a KEYWORD argument, not positionally.
_ACTION_CALL = re.compile(r"action\s*\(\s*(?:actions\s*=\s*)?\[", re.S)
_ACTION_DICT = re.compile(r"\{\s*['\"]action['\"]\s*:", re.S)


def load_history(run_dir: Path):
    bj = run_dir / "benchmark.json"
    if not bj.exists():
        return [], {}
    b = json.loads(bj.read_text())
    gr = (b.get("game_runs") or [{}])[0]
    return gr.get("history") or [], gr


def latency_stats(history, batch_gap_s=0.25):
    """Latency, reported at TWO units — because the pre-registered `per_action_latency` threshold
    assumes one model call per action, and this agent BATCHES.

    The duck calls action(actions=[a, b, c, ...]), so several ActionRecords can be committed from a
    single model decision. Consecutive deltas within such a batch are ~0 and are NOT model latency;
    reporting their p50 as "per-action latency" would understate the real cost by an order of magnitude.

      per_action  — every delta. What the frozen threshold literally names. Dominated by intra-batch
                    zeros whenever the agent batches, so it flatters the agent.
      per_decision— deltas above `batch_gap_s`, i.e. gaps that actually contain a model round-trip.
                    This is the quantity the latency budget should be read against.
    """
    ts = [h.get("wallclock_seconds") for h in history if h.get("wallclock_seconds") is not None]
    if len(ts) < 2:
        return {}
    deltas = [b - a for a, b in zip(ts, ts[1:]) if b >= a]
    if not deltas:
        return {}
    def stats(xs):
        if not xs:
            return None
        xs_s = sorted(xs)
        def pct(p):
            return xs_s[min(len(xs_s) - 1, int(round(p * (len(xs_s) - 1))))]
        return {"n": len(xs), "p50_s": round(statistics.median(xs), 2),
                "p95_s": round(pct(0.95), 2), "mean_s": round(statistics.fmean(xs), 2),
                "max_s": round(max(xs), 2)}

    decisions = [d for d in deltas if d > batch_gap_s]
    batched = len(deltas) - len(decisions)
    return {
        "n_actions": len(ts),
        "total_wallclock_s": round(ts[-1], 1),
        "batch_gap_s": batch_gap_s,
        "actions_committed_in_batches": batched,
        "batched_fraction": round(batched / len(deltas), 3) if deltas else None,
        "per_action": stats(deltas),
        "per_decision": stats(decisions),
        "which_to_use": ("per_decision. The frozen threshold names per-action latency, but with "
                         "batching that statistic is dominated by intra-batch zeros and understates "
                         "the model cost. Record both; gate on per_decision."),
    }


def legal_action_reliability(run_dir: Path, executed_events: int):
    """Requested vs executed, read from the harness's OWN action results.

    CORRECTED: an earlier version parsed action() calls out of the tool source and concluded the
    threshold was unmeasurable, because the agent builds action lists programmatically. That was
    looking in the wrong place. `_compact_action_result` emits `requested_count`, `executed_count`,
    `stopped_early` and `stop_reason` directly, and those payloads are fed back to the model as tool
    output — so they are captured verbatim in the D6 request logs.

    One subtlety: the fields are only emitted when `batch_size > 1 or stopped_early` (tool_agent.py
    ~1437). A single action that executed normally carries neither, and counts 1/1 implicitly.
    """
    requested = executed = 0
    explicit_batches = implicit_singles = 0
    stops: dict[str, int] = {}

    # The action result is delivered to the model as a TOOL message whose content is pretty-printed
    # JSON. Parse the request row, walk its messages, and read the tool payloads — a regex over the
    # raw line fails because the payload is escaped JSON inside a JSON string.
    seen = set()
    for f in glob.glob(str(run_dir / "*requests.jsonl")):
        for line in open(f):
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            for msg in (row.get("messages") or []):
                if msg.get("role") != "tool":
                    continue
                content = msg.get("content")
                if not isinstance(content, str) or '"executed"' not in content:
                    continue
                if content in seen:      # history repeats every tool result in each later prompt
                    continue
                seen.add(content)
                try:
                    payload = json.loads(content)
                except Exception:  # noqa: BLE001
                    continue
                # Shape is {"tool": ..., "returncode": ..., "result": {<action result>}}.
                res = None
                if isinstance(payload, dict):
                    for key in ("result", "action_result"):
                        cand = payload.get(key)
                        if isinstance(cand, dict) and "executed" in cand:
                            res = cand
                            break
                    if res is None and "executed" in payload:
                        res = payload
                if not isinstance(res, dict):
                    continue
                if "requested_count" in res or "executed_count" in res:
                    requested += int(res.get("requested_count") or 0)
                    executed += int(res.get("executed_count") or 0)
                    explicit_batches += 1
                    if res.get("stopped_early"):
                        k = str(res.get("stop_reason") or "unknown")
                        stops[k] = stops.get(k, 0) + 1
                else:
                    requested += 1
                    executed += 1 if res.get("executed") else 0
                    implicit_singles += 1

    validity = (executed / requested) if requested else None
    return {
        "requested_actions": requested,
        "executed_actions": executed,
        "validity": round(validity, 4) if validity is not None else None,
        "explicit_batch_results": explicit_batches,
        "implicit_single_results": implicit_singles,
        "rejection_taxonomy": stops or {},
        "executed_action_events": executed_events,
        "method": ("read from the harness's own requested_count/executed_count in action results, "
                   "captured verbatim in the D6 request logs. Single non-early-stopped actions omit "
                   "the fields and count 1/1."),
    }


def throughput_degradation(history, window_s=600.0):
    """Actions/min in the first window vs across the whole run. Thermal/throttling proxy."""
    ts = [h.get("wallclock_seconds") for h in history if h.get("wallclock_seconds") is not None]
    if len(ts) < 4 or ts[-1] <= window_s:
        return {"note": f"run shorter than the {window_s:.0f}s window; not computable"}
    early = sum(1 for t in ts if t <= window_s)
    early_rate = early / (window_s / 60.0)
    full_rate = len(ts) / (ts[-1] / 60.0)
    deg = 1.0 - (full_rate / early_rate) if early_rate else None
    return {
        "first_window_s": window_s,
        "actions_per_min_first_window": round(early_rate, 2),
        "actions_per_min_whole_run": round(full_rate, 2),
        "degradation": round(deg, 4) if deg is not None else None,
        "note": "positive degradation = slower later. Confounded by task phase, not only thermals.",
    }


def token_accounting(history):
    gen = [h.get("generated_tokens", 0) or 0 for h in history]
    unc = [h.get("uncached_input_tokens", 0) or 0 for h in history]
    if not gen:
        return {}
    return {
        "generated_total": sum(gen),
        "generated_per_action_p50": statistics.median(gen),
        "uncached_input_total": sum(unc),
        "uncached_input_per_action_p50": statistics.median(unc),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)

    history, gr = load_history(run_dir)
    events = glob.glob(str(run_dir / "artifacts" / "*_events.jsonl"))
    executed = 0
    for f in events:
        executed += sum(1 for l in open(f) if json.loads(l).get("type") == "action")

    cfg = {}
    rc = run_dir / "run_config.json"
    if rc.exists():
        try:
            cfg = json.loads(rc.read_text())
        except Exception:  # noqa: BLE001
            cfg = {}

    out = {
        "run": run_dir.name,
        # Freeze §5: every latency figure carries the concurrency it was measured at.
        "concurrency": cfg.get("concurrent_jobs") or cfg.get("concurrency"),
        "model": cfg.get("model"),
        "state": gr.get("state"),
        "levels_completed": gr.get("levels_completed"),
        "actions_per_level": gr.get("actions_per_level"),
        "base_actions_per_level": gr.get("base_actions_per_level"),
        "per_action_latency": latency_stats(history),
        "legal_action_reliability": legal_action_reliability(run_dir, executed),
        "throughput_degradation": throughput_degradation(history),
        "token_accounting": token_accounting(history),
    }
    out_path = args.out or f"logs/s1c_{run_dir.name}.json"
    Path(out_path).write_text(json.dumps(out, indent=2) + "\n")

    print(f"run        : {out['run']}")
    print(f"concurrency: {out['concurrency']}   model: {str(out['model']).split('/')[-1]}")
    print(f"state      : {out['state']}  levels={out['levels_completed']}")
    for k in ("per_action_latency", "legal_action_reliability", "throughput_degradation", "token_accounting"):
        print(f"\n{k}:")
        for kk, vv in (out[k] or {}).items():
            print(f"   {kk:34s} {vv}")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
