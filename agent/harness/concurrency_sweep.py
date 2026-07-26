"""Concurrency sweep against the local MLX server — S1-c latency work, pulled forward.

The freeze (§5) requires per-action latency to be measured "under the *actual* batching pattern", and
warns that a single-threaded number misleads by the batching factor. This measures that factor directly.

The question it answers: does raising concurrency buy aggregate throughput on one Apple GPU, and how far
before memory or compute binds? It deliberately does NOT claim anything about single-request latency
improving — decode of one stream cannot go faster by adding neighbours.

Run:  .venv/bin/python agent/harness/concurrency_sweep.py --levels 1,2,4,8
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE_URL = "http://127.0.0.1:1234/v1"
MODEL = os.path.expanduser("~/models/mlx/Qwen3.6-27B-4bit")

# A prompt that reliably generates to the token cap rather than stopping early, so completion_tokens is
# a controlled variable across concurrency levels rather than a property of the answer's length.
PROMPT = (
    "Describe, step by step and in detail, how you would systematically explore an unfamiliar "
    "grid-based puzzle game to infer its rules. Cover at least eight distinct strategies and explain "
    "the trade-offs of each. Be thorough and verbose."
)


def server_rss_gib() -> float:
    try:
        pid = subprocess.run(["pgrep", "-f", "mlx_vlm.server"], capture_output=True, text=True).stdout.split()
        if not pid:
            return float("nan")
        rss = subprocess.run(["ps", "-o", "rss=", "-p", pid[0]], capture_output=True, text=True).stdout.strip()
        return int(rss) / 1048576
    except Exception:  # noqa: BLE001
        return float("nan")


def one_request(max_tokens: int, timeout: float) -> tuple[float, int]:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0.6,
        "top_p": 0.95,
    }
    t0 = time.monotonic()
    r = requests.post(f"{BASE_URL}/chat/completions", json=payload, timeout=timeout)
    dt = time.monotonic() - t0
    r.raise_for_status()
    return dt, int((r.json().get("usage") or {}).get("completion_tokens", 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="1,2,4,8")
    ap.add_argument("--max-tokens", type=int, default=256)
    ap.add_argument("--timeout", type=float, default=1800.0)
    args = ap.parse_args()

    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    rows = []
    print(f"model={MODEL}")
    print(f"max_tokens={args.max_tokens}  (thinking left at server default)")
    print(f"baseline server RSS: {server_rss_gib():.1f} GiB\n")
    print(f"{'N':>3} {'wall_s':>8} {'tok':>7} {'agg tok/s':>10} {'per-req tok/s':>14} "
          f"{'p50 lat s':>10} {'p95 lat s':>10} {'RSS GiB':>8}")
    print("-" * 78)

    for n in levels:
        with ThreadPoolExecutor(max_workers=n) as ex:
            t0 = time.monotonic()
            results = list(ex.map(lambda _: one_request(args.max_tokens, args.timeout), range(n)))
            wall = time.monotonic() - t0
        lats = sorted(dt for dt, _ in results)
        toks = sum(t for _, t in results)
        agg = toks / wall if wall else 0.0
        per_req = statistics.median(t / dt for dt, t in results if dt)
        p50 = statistics.median(lats)
        p95 = lats[max(0, int(round(0.95 * (len(lats) - 1))))]
        rss = server_rss_gib()
        rows.append({
            "concurrency": n, "wall_s": round(wall, 2), "completion_tokens": toks,
            "aggregate_tok_s": round(agg, 2), "per_request_tok_s": round(per_req, 2),
            "p50_latency_s": round(p50, 2), "p95_latency_s": round(p95, 2),
            "server_rss_gib": round(rss, 2),
        })
        print(f"{n:>3} {wall:>8.1f} {toks:>7} {agg:>10.1f} {per_req:>14.1f} "
              f"{p50:>10.1f} {p95:>10.1f} {rss:>8.1f}")

    if len(rows) > 1:
        base = rows[0]["aggregate_tok_s"]
        print(f"\nscaling vs concurrency {rows[0]['concurrency']} (this sweep's lowest level):")
        for r in rows:
            print(f"  N={r['concurrency']:>2}  {r['aggregate_tok_s'] / base:>5.2f}x aggregate   "
                  f"per-request {r['per_request_tok_s']:>5.1f} tok/s")

    out = "logs/concurrency_sweep.json"
    with open(out, "w") as fh:
        json.dump(rows, fh, indent=2)
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
