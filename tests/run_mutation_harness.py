"""Mutation harness for the S1-d gates — turns "the tests pass" into evidence.

WHY THIS EXISTS
---------------
Across four review rounds the guards in `s1d_*` held up, and the TESTS were what kept failing: an
assertion that went vacuous when a new guard started rejecting earlier; a fixture that dropped model
AND sampling so it could not tell whether the other three fields were required; a test that passed
through a neighbouring check rather than the one it named. Every one of those was found by breaking
the code on purpose and noticing the suite stayed green — never by reading it.

A passing suite says "no test fails". A surviving mutant says "this line could be deleted and nothing
would notice", which is the question actually worth asking of a pre-registration gate.

WHAT IT DOES
------------
Parses each target module, enumerates mutation sites, and for each one writes a single-mutation copy
of the harness into a temp tree and runs the suite against it.

    killed     the suite failed  -> that line is pinned by a test
    SURVIVED   the suite passed  -> nothing tests it. Either write a test or record it as equivalent.

Operators, chosen to match the defects this project actually produced:

  guard-off   an `if` whose body exits early (return / continue / break / raise) has its condition
              replaced by `False`. This is precisely "delete the guard", and every real defect found
              in review was a guard that was missing, scoped wrongly, or checked the wrong object.
  compare     swap a comparison: `>=` <-> `>`, `<=` <-> `<`, `==` <-> `!=`, `is` <-> `is not`.
              Catches off-by-one and inverted-threshold errors — e.g. an agreement floor applied as
              `>` instead of `>=`.
  return-ok   `return 1` becomes `return 0`: the guard still detects the problem and then reports
              success anyway. Several defects here were exactly this shape — detected and not refused.

EQUIVALENT MUTANTS
------------------
Some survivors are not bugs. A guard can be genuinely redundant with another (the `corpus_digest`
check is subsumed by sample re-derivation), or a comparison can be unreachable in practice. Those go
in `tests/mutation_allowlist.txt` WITH A REASON, so the harness can exit non-zero on new survivors
only. An allowlist entry is a claim that the line is untestable, not that testing it is inconvenient —
it is keyed by function and source fragment rather than line number so it survives edits above it.

Run:
  .venv/bin/python tests/run_mutation_harness.py                 # all s1d_* modules
  .venv/bin/python tests/run_mutation_harness.py --list          # enumerate sites, run nothing
  .venv/bin/python tests/run_mutation_harness.py --target s1d_blind_rerate.py
  .venv/bin/python tests/run_mutation_harness.py --operator guard-off --jobs 8

Exit status: 0 if every survivor is allowlisted, 1 otherwise. Suitable for a pre-commit gate.
"""

from __future__ import annotations

import argparse
import ast
import concurrent.futures
import copy
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS_DIR = REPO / "agent" / "harness"
TESTS_DIR = REPO / "tests"
ALLOWLIST = TESTS_DIR / "mutation_allowlist.txt"

# The modules `test_s1d_gates.py` actually imports. Mutating a module with NO tests produces a wall of
# survivors that says one thing — "this module is untested" — a hundred times over, which buries the
# survivors that mean "this guard is untested". The uncovered modules are reported as a single honest
# line instead, and `--target` runs them when someone is ready to write those tests.
DEFAULT_TARGETS = ["s1d_blind_rerate.py", "s1d_build_corpus.py",
                   "s2_blind_rerate.py", "s2_apply_labels.py"]

# `ast.walk` is deterministic, so a node's index in it is a stable handle into a fresh parse of the
# same source. That is how a site found during collection is re-located when the mutant is built.
EARLY_EXIT = (ast.Return, ast.Continue, ast.Break, ast.Raise)

COMPARE_SWAP = {
    ast.GtE: ast.Gt, ast.Gt: ast.GtE,
    ast.LtE: ast.Lt, ast.Lt: ast.LtE,
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
}


@dataclass
class Site:
    path: Path            # module the mutation lives in
    nid: int              # index into list(ast.walk(tree))
    lineno: int
    func: str
    operator: str
    detail: str           # human-readable description of the change
    fragment: str         # unparsed original, used as the stable allowlist key

    @property
    def key(self) -> str:
        return f"{self.path.name}::{self.func}::{self.operator}::{self.fragment}"

    def __str__(self) -> str:
        return f"{self.path.name}:{self.lineno} [{self.operator}] {self.func}(): {self.detail}"


def _function_names(tree: ast.AST) -> dict[int, str]:
    """Map every node to its innermost enclosing function.

    `ast.walk` is breadth-first, so an outer function is visited before an inner one and the inner
    assignment overwrites it — which is the name we want for a nested definition.
    """
    names: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                names[id(child)] = node.name
    return names


def collect_sites(path: Path, skip_functions: set[str]) -> list[Site]:
    tree = ast.parse(path.read_text())
    fnames = _function_names(tree)
    sites: list[Site] = []

    for nid, node in enumerate(ast.walk(tree)):
        func = fnames.get(id(node), "<module>")
        if func in skip_functions:
            continue

        # `if __name__ == "__main__":` is not gate logic and can never be killed by an import-based
        # suite. Excluded rather than allowlisted 147 times.
        if isinstance(node, ast.Compare) and ast.unparse(node) == "__name__ == '__main__'":
            continue
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and ast.unparse(node.test) == "__name__ == '__main__'"):
            continue

        if isinstance(node, ast.If) and any(isinstance(s, EARLY_EXIT) for s in node.body):
            frag = ast.unparse(node.test)
            sites.append(Site(path, nid, node.lineno, func, "guard-off",
                              f"if {_ellipsis(frag)}: -> if False:", frag))

        elif isinstance(node, ast.Compare) and len(node.ops) == 1:
            op = type(node.ops[0])
            if op in COMPARE_SWAP:
                frag = ast.unparse(node)
                sites.append(Site(path, nid, node.lineno, func, "compare",
                                  f"{_ellipsis(frag)}  [{op.__name__} -> "
                                  f"{COMPARE_SWAP[op].__name__}]", frag))

        # `not isinstance(..., bool)` because `True == 1` in Python, so `return True` was matching and
        # being reported as "return 1 -> return 0" — a real mutation described by a false label.
        elif (isinstance(node, ast.Return) and isinstance(node.value, ast.Constant)
                and not isinstance(node.value.value, bool) and node.value.value == 1):
            sites.append(Site(path, nid, node.lineno, func, "return-ok",
                              "return 1 -> return 0", "return 1"))

    return sites


def _ellipsis(s: str, n: int = 58) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def apply_mutation(path: Path, site: Site) -> str:
    """Re-parse and mutate exactly one node, returning the mutated source."""
    tree = ast.parse(path.read_text())
    node = list(ast.walk(tree))[site.nid]

    if site.operator == "guard-off":
        assert isinstance(node, ast.If)
        node.test = ast.Constant(value=False)
    elif site.operator == "compare":
        assert isinstance(node, ast.Compare)
        node.ops = [COMPARE_SWAP[type(node.ops[0])]()]
    elif site.operator == "return-ok":
        assert isinstance(node, ast.Return)
        node.value = ast.Constant(value=0)
    else:                                                   # pragma: no cover - guarded by argparse
        raise ValueError(site.operator)

    return ast.unparse(ast.fix_missing_locations(tree))


def run_mutant(site: Site, pytest_args: list[str]) -> tuple[Site, bool, str]:
    """Build a one-mutation copy of the tree and run the suite. Returns (site, killed, detail).

    The whole harness and tests are copied rather than patched in place: a mutation must never be
    able to escape into the working tree, and the modules import each other, so the mutated one has
    to sit beside unmutated siblings.
    """
    with tempfile.TemporaryDirectory(prefix="mut-") as tmp:
        root = Path(tmp)
        dst_harness = root / "agent" / "harness"
        dst_harness.parent.mkdir(parents=True)
        shutil.copytree(HARNESS_DIR, dst_harness,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(TESTS_DIR, root / "tests",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        try:
            (dst_harness / site.path.name).write_text(apply_mutation(site.path, site))
        except Exception as exc:                            # pragma: no cover - unparse failure
            return site, True, f"could not build mutant ({exc}) — treated as killed"

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-x", "-q", "--no-header",
             "-p", "no:cacheprovider", *pytest_args],
            cwd=root, capture_output=True, text=True,
        )
        killed = proc.returncode != 0
        detail = ""
        if killed:
            for line in proc.stdout.splitlines():
                if line.startswith("FAILED") or line.startswith("ERROR"):
                    detail = line.split(" - ")[0].replace("FAILED ", "").replace("tests/", "")
                    break
        return site, killed, detail


def load_allowlist() -> dict[str, str]:
    """`key  # reason` per line. The reason is mandatory — an unexplained entry is a silenced bug."""
    if not ALLOWLIST.exists():
        return {}
    out = {}
    for raw in ALLOWLIST.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, reason = line.partition("  #")
        out[key.strip()] = reason.strip() or "NO REASON GIVEN"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--target", nargs="*", default=None,
                    help="module filenames under agent/harness (default: s1d_*.py)")
    ap.add_argument("--operator", nargs="*", default=None,
                    choices=["guard-off", "compare", "return-ok"])
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--list", action="store_true", help="enumerate sites and exit")
    ap.add_argument("--skip-functions", nargs="*", default=["main"],
                    help="functions to leave alone (default: main — CLI plumbing, not gate logic)")
    ap.add_argument("--pytest-args", nargs="*", default=[])
    args = ap.parse_args()

    targets = ([HARNESS_DIR / t for t in args.target] if args.target
               else [HARNESS_DIR / t for t in DEFAULT_TARGETS])
    missing = [t for t in targets if not t.exists()]
    if missing:
        print(f"no such module(s): {', '.join(m.name for m in missing)}")
        return 2

    if not args.target:
        uncovered = sorted(p.name for p in HARNESS_DIR.glob("s[12]*.py")
                           if p.name not in DEFAULT_TARGETS)
        if uncovered:
            print(f"NOT under mutation — no direct tests import them: {', '.join(uncovered)}")
            print(f"  Mutating them would report every line as untested, which is true and not "
                  f"useful here. Run with --target <module> once they have tests.\n")

    skip = set(args.skip_functions)
    sites = [s for t in targets for s in collect_sites(t, skip)]
    if args.operator:
        sites = [s for s in sites if s.operator in args.operator]
    if not sites:
        print("no mutation sites matched.")
        return 2

    if args.list:
        for s in sites:
            print(s)
        print(f"\n{len(sites)} site(s).")
        return 0

    # A mutant that "fails" because the suite was already red proves nothing. Establish the baseline
    # first and refuse to interpret anything against a broken tree.
    #
    # THE BASELINE RUNS IN THE SANDBOX, not in the repository. Running it at REPO while every mutant
    # ran in a temp copy compared two different environments: a test that cannot run in the sandbox —
    # one reading `gate_manifest.yaml`, say, which is not copied — passed the baseline and then failed
    # for EVERY mutant, reporting a flawless 155/0 that meant only "one test errors out there". A
    # false green is worse than a red, so the baseline is measured where the verdicts are.
    print("baseline: running the suite unmutated, in the sandbox ...", flush=True)
    with tempfile.TemporaryDirectory(prefix="mut-base-") as tmp:
        root = Path(tmp)
        (root / "agent").mkdir(parents=True)
        shutil.copytree(HARNESS_DIR, root / "agent" / "harness",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copytree(TESTS_DIR, root / "tests",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        base = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header",
             "-p", "no:cacheprovider", *args.pytest_args],
            cwd=root, capture_output=True, text=True)
    if base.returncode != 0:
        print("REFUSED — the suite does not pass in the sandbox, so survivors would be meaningless.")
        print("  Every mutant would 'fail' for this reason and the run would report a perfect score.")
        print(base.stdout[-2000:])
        return 2
    # How many tests actually RAN there. A suite that mostly skips in the sandbox kills mutants it
    # never exercised, so the number is printed rather than left to be assumed.
    summary = [ln for ln in base.stdout.splitlines() if " passed" in ln or " skipped" in ln]
    if summary:
        print(f"  sandbox baseline: {summary[-1].strip()}")
    print(f"baseline green. {len(sites)} mutant(s) over "
          f"{len({s.path.name for s in sites})} module(s), {args.jobs} job(s).\n", flush=True)

    allow = load_allowlist()
    survivors: list[Site] = []
    killed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_mutant, s, args.pytest_args) for s in sites]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            site, was_killed, detail = fut.result()
            if was_killed:
                killed += 1
                mark, note = "killed  ", f"  <- {detail}" if detail else ""
            else:
                survivors.append(site)
                mark = "SURVIVED"
                note = f"  [allowlisted: {allow[site.key]}]" if site.key in allow else ""
            print(f"[{i:3d}/{len(sites)}] {mark} {site}{note}", flush=True)

    unexplained = [s for s in survivors if s.key not in allow]
    print(f"\n{'=' * 78}")
    print(f"{killed} killed · {len(survivors)} survived "
          f"({len(survivors) - len(unexplained)} allowlisted, {len(unexplained)} unexplained)")

    if unexplained:
        print(f"\n{len(unexplained)} UNTESTED line(s) — each could be deleted and the suite would "
              f"still pass:\n")
        for s in unexplained:
            print(f"  {s}")
            print(f"      allowlist key: {s.key}")
        print("\nWrite a test that fails when the line is removed, or add the key to "
              f"{ALLOWLIST.relative_to(REPO)} with a reason.")
        return 1

    print("\nEvery mutation is either killed by a test or recorded as equivalent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
