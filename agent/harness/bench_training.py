"""Measure local training throughput for a Track-A-sized world model.

WHY
---
`notes/local-compute-options.md` asserts that S2/S3 are "comfortable" locally because Track A targets
~20M parameters against the reference agent's 27B. That assertion was reasoned, not measured, and the
open question is whether the machine actually delivers the throughput S3 needs.

THE 20M FIGURE IS A GUESS, AND IT IS NOT PRE-REGISTERED
--------------------------------------------------------
Checked 2026-07-27: "20M trainable parameters" appears NOWHERE in `gate_manifest.yaml`. Its sources are
`docs/arc-agi-3-ship-jepa-x-architecture.md` §20 — "a compact implementation **can target
approximately** 20 million", in a document CLAUDE.md marks *candidate design, not committed* — and the
frozen, partly-superseded executive summary, which calls it a "fixed budget".

So this benchmark does NOT ask "can the machine train 20M parameters". That question inherits the guess.
It SWEEPS parameter counts and reports the feasible frontier, so the size can be chosen against measured
throughput instead of the reverse.

WHAT S3 NEEDS, AND WHAT IS MISSING
----------------------------------
S3 screens 3 objectives (A latent / B reconstructive / C exact-delta) crossed with rollout on/off — six
configurations — across 2 paired seeds, in 5 days. So ~12 training runs plus cheap controls.

**No training budget is pre-registered anywhere.** The parameter budget is fixed (20M ±5%, matched
within ±5%) and "matched optimization budget" is required, but no step count, epoch count, or dataset
size is given. The only compute figure in the documents is the FROZEN 48-model matrix's "roughly 290
GPU-hours" for 72 models — about 4 GPU-hours per model, on an unspecified GPU. That matrix is
superseded, so the figure is a loose anchor at best.

This benchmark therefore reports **steps per second at a stated shape**, and leaves the conversion to
wall-clock explicit rather than assuming a step count nobody has registered.

WHAT IS MEASURED
----------------
A model of roughly the documented shape and parameter budget: a spatial grid encoder over 64x64 cells
with 16 values, a sequential context transformer over a K-transition window, and prediction heads.
Exact module boundaries differ from the architecture doc — this measures the COMPUTE PROFILE
(parameter count, sequence length, grid size, batch size), not the design.

Forward + backward + optimizer step, steady state after warm-up, with peak memory.

HONEST LIMITS
-------------
* Not the real model. A different attention pattern or a heavier decoder in arm B moves this.
* MLX only; no torch/MPS comparison is available in this environment.
* Single process. Running it while the MLX LLM server holds the GPU produces meaningless numbers —
  the script refuses to run in that case rather than reporting contaminated figures.

Run:  .venv/bin/python agent/harness/bench_training.py [--params 20 --k 16 --grid 64 --batch 32]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import mlx.core as mx
import mlx.nn as nn
import mlx.optimizers as optim


class GridEncoder(nn.Module):
    """Embeds 64x64 cells (16 values) and pools to a per-frame vector."""

    def __init__(self, d: int, n_values: int = 16):
        super().__init__()
        self.emb = nn.Embedding(n_values, d // 4)
        self.proj1 = nn.Linear(d // 4, d // 2)
        self.proj2 = nn.Linear(d // 2, d)
        self.norm = nn.LayerNorm(d)

    def __call__(self, grids):                     # (B, K, H, W) int32
        B, K, H, W = grids.shape
        x = self.emb(grids.reshape(B * K, H * W))  # (B*K, HW, d/4)
        x = nn.relu(self.proj1(x))
        x = x.mean(axis=1)                         # pool over cells
        x = self.norm(self.proj2(x))
        return x.reshape(B, K, -1)


class ContextTransformer(nn.Module):
    def __init__(self, d: int, layers: int, heads: int):
        super().__init__()
        self.blocks = [nn.TransformerEncoderLayer(d, heads, d * 4) for _ in range(layers)]

    def __call__(self, x):
        for b in self.blocks:
            x = b(x)
        return x


class WorldModel(nn.Module):
    def __init__(self, d: int, layers: int, heads: int, n_values: int = 16):
        super().__init__()
        self.enc = GridEncoder(d, n_values)
        self.ctx = ContextTransformer(d, layers, heads)
        self.act_emb = nn.Embedding(8, d)
        self.pred = nn.Sequential(nn.Linear(d * 2, d * 2), nn.ReLU(), nn.Linear(d * 2, d))
        self.heads = nn.Sequential(nn.Linear(d, d), nn.ReLU(), nn.Linear(d, d))

    def __call__(self, grids, actions):
        h = self.ctx(self.enc(grids))              # (B, K, d)
        a = self.act_emb(actions)                  # (B, K, d)
        z = self.pred(mx.concatenate([h, a], axis=-1))
        return self.heads(z)


def count_params(m) -> int:
    def walk(t):
        if isinstance(t, dict):
            return sum(walk(v) for v in t.values())
        if isinstance(t, list):
            return sum(walk(v) for v in t)
        return t.size if hasattr(t, "size") else 0
    return walk(m.parameters())


def pick_width(target_m: float, layers: int, heads: int, grid: int, k: int) -> tuple:
    """Search d so the parameter count lands near the target."""
    best = None
    for d in range(64, 1025, 32):
        if d % heads:
            continue
        m = WorldModel(d, layers, heads)
        mx.eval(m.parameters())
        n = count_params(m)
        err = abs(n - target_m * 1e6)
        if best is None or err < best[0]:
            best = (err, d, n, m)
    return best[1], best[2], best[3]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="5,10,20,50,100",
                    help="comma-separated parameter counts in millions to sweep")
    ap.add_argument("--k", type=int, default=16, help="transitions in the context window")
    ap.add_argument("--grid", type=int, default=64)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--layers", type=int, default=6)
    ap.add_argument("--heads", type=int, default=8)
    ap.add_argument("--steps", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=10)
    args = ap.parse_args()

    # Contended measurements are worthless; refuse rather than mislead.
    try:
        busy = subprocess.run(["pgrep", "-f", "mlx_vlm[.]server"],
                              capture_output=True, text=True).stdout.strip()
    except Exception:  # noqa: BLE001
        busy = ""
    if busy:
        print("REFUSING: an mlx_vlm server is running and holds the GPU.")
        print("A training benchmark taken under contention measures the contention, not the machine.")
        print(f"   pids: {busy.split()}")
        return 2

    print(f"K={args.k} · grid {args.grid}x{args.grid} · batch {args.batch} · "
          f"{args.layers}L/{args.heads}H · sweep {args.sweep}M params\n")

    results = []
    for target_m in [float(x) for x in args.sweep.split(",")]:
        d, n_params, model = pick_width(target_m, args.layers, args.heads, args.grid, args.k)
        opt = optim.AdamW(learning_rate=3e-4)
        grids = mx.random.randint(0, 16, (args.batch, args.k, args.grid, args.grid))
        actions = mx.random.randint(0, 8, (args.batch, args.k))
        tgt = mx.random.normal((args.batch, args.k, d))

        def loss_fn(m):
            return ((m(grids, actions) - tgt) ** 2).mean()

        grad_fn = nn.value_and_grad(model, loss_fn)
        mx.reset_peak_memory()
        for _ in range(args.warmup):
            _, g = grad_fn(model); opt.update(model, g); mx.eval(model.parameters(), opt.state)
        mx.eval(model.parameters())
        t0 = time.perf_counter()
        for _ in range(args.steps):
            _, g = grad_fn(model); opt.update(model, g); mx.eval(model.parameters(), opt.state)
        dt = time.perf_counter() - t0
        sps = args.steps / dt
        results.append((n_params, d, sps, mx.get_peak_memory() / 1e9))
        print(f"  {n_params/1e6:6.1f}M (d={d:4d})  {sps:7.2f} steps/s  "
              f"{dt/args.steps*1000:6.0f} ms/step  peak {mx.get_peak_memory()/1e9:5.2f} GB")

    print(f"\n  Wall-clock for ~12 S3 runs, by parameter count x step budget.")
    print(f"  NO step budget is pre-registered — that is the missing number, not this table.\n")
    print(f"  {'params':>8s} " + " ".join(f"{s//1000:>6d}k" for s in (10_000, 50_000, 100_000, 500_000)))
    for n_params, d, sps, _ in results:
        row = " ".join(f"{steps/sps/3600*12:6.1f}h" for steps in (10_000, 50_000, 100_000, 500_000))
        print(f"  {n_params/1e6:7.1f}M {row}")
    print(f"\n  S3 allows 5 days (120 h) for ~12 runs plus controls. Cells under ~100 h are")
    print(f"  reachable locally; the largest such row is the size the machine supports, which is")
    print(f"  the number to choose a parameter budget AGAINST rather than to check 20M against.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
