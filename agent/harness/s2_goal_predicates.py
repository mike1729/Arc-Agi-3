"""Extract each public game's level-advance predicate from its source, as evidence for a rater.

Every one of the 25 public games ships its Python source in the competition bundle
(`data/environment_files/<env>/<hash>/<env>.py`, 119k lines total), and every one calls
`self.next_level()` at **exactly one** site. That call is the goal: whatever guards it is the
condition a player must satisfy to advance. So the goal predicate of each game is recoverable as
ground truth rather than inferred from play, which is what makes a measured predicate distribution
possible at all.

THIS SCRIPT DOES NOT CLASSIFY. IT ASSEMBLES EVIDENCE.
-----------------------------------------------------
The S1 labelling method applies here unchanged and for the same reason: the frequencies these labels
produce are meant to decide which goal-induction machinery gets built first, and a heuristic that maps
AST shapes onto the predicate taxonomy would manufacture exactly the distribution it was supposed to
measure. `np.array_equal` is not "template match" — it is a function call that a rater may decide
implements one, after reading what is being compared against what.

So each record carries an empty `label`, the guard expression, and enough resolved source for the
label to be assigned by reading. The `features` block holds structural facts (does the guard call
`all()`, does it compare a length, does it iterate a collection) and exists to make the rater faster
and the eventual disagreement analysable. Features are diagnostics. They are never the label, and
nothing downstream should derive one from them.

WHY A CLOSURE AND NOT A LINE
----------------------------
The guard is only sometimes readable where it sits. Across the 25 games it takes four forms, and the
naive extraction — print the enclosing `if` test — is uninformative or actively wrong for three:

    cd82   inline         `if np.array_equal(a[mask], b[mask]): self.next_level()`
    vc33   delegated      `if self.ielczunthe(): self.next_level()` — the predicate is a method
    tn36   instance flag  `if self.nyhaiggftp: self.next_level()` — the predicate is wherever that
                          flag is SET, which for tn36 is a different method entirely
    sc25   guard clause   no enclosing `if` at all; the call sits at function top level behind two
                          early returns, and the condition is their negative space

The flag form is the dangerous one. Reported literally it reads as a trivially-guarded game, when in
fact its condition is the one computed furthest from the call site. The guard-clause form is worse
still: it reports as *unconditional*. So this script resolves, transitively, the `self.<method>()`
calls in the guard; the assignment sites of any `self.<attr>` the guard reads, together with the
conditions under which they are assigned; and the negated tests of every preceding guard clause. The
enclosing function is always included, because the local-flag variant computes its condition there.

Identifiers are name-mangled, and the mangling scheme is not even consistent between games — cd82 uses
ten-character lowercase names, ft09 uses three-character mixed-case ones. Nothing here relies on
identifier meaning; resolution is structural, by AST.

FIVE WAYS THIS USED TO STOP SHORT, ALL FOUND BY RATERS CONFINED TO THE PACKET
-----------------------------------------------------------------------------
Every one was silent: the packet looked complete and simply lacked the condition. Raters allowed to
consult the source patched them invisibly, which is how two labelling passes once came to rate
different material. Confining raters to the packet turned each into a report.

  over-budget attributes   a bound meant for heavily-mutated bookkeeping fields also dropped
                           attributes the guard reads DIRECTLY. Guard attributes are now exempt.
  container mutation       a write counted only as `self.x = ...`, so `self.d[k] = v`, `del`, and
                           `.add()`/`.append()` were invisible. wa30's exclusion set had no writes.
  module-level functions   the index walked ClassDefs only, so ka59's `jxudaewdwt` at line 41075 was
                           unindexed. Closing it ALSO required collecting bare-name calls, since the
                           reference walk gathered attributes only — indexed but never asked for.
  local bindings           sk48 arms its flag under `nuikqmprbq`, bound one line earlier by
                           `nuikqmprbq = self.gvtmoopqgy()`. A local name reached nothing.
  arming call sites        the function that WRITES a guard flag often says nothing about the goal —
                           sc25's arming method sets its flag unconditionally, and the sub-engine
                           `win()` in bp35 and lf52 is a bare assignment. The condition a player
                           establishes guards the CALL, in another function entirely.

Call sites are followed only for a write that is itself near-unconditional (at most one guard of its
own) and never for `__init__`, which has a call site per instantiation and explains nothing. A writer
carrying its own guards already states the condition; following its callers would add the caller's
unrelated context to every such packet.

BOUNDED, AND LOUDLY SO
----------------------
Resolution stops at `--depth` (default 10) and packets are capped at `--max-lines` (default 12000).
Both are set where the whole corpus resolves untruncated — 45.8k evidence lines over 25 games, median
1088, the largest 8607. That is 2.5x the corpus before these five fixes, which is the price of the
packets actually containing their conditions. A third bound, `--max-sites`, still drops attributes
written in more than six places; it fires on four games, is recorded per record, and is intended —
those are bookkeeping fields, not guard state. All three truncations appear in the record and in the
summary, because a packet that silently dropped the branch carrying the real condition would read
exactly like a simple predicate.

Resolution follows the CONDITION, not the enclosing function. The enclosing function is included in
the packet for context but is not searched: seeding the name walk from it drags in every attribute
`step()` touches — movement, rendering, input handling — which under module-wide lookup hit the line
cap for 15 of 25 games and buried the condition in the material it needed to be distinguished from.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ENVS = REPO / "data/environment_files"

# Structural facts a rater might otherwise have to hunt for. Diagnostics, not labels.
FEATURE_CALLS = {
    "all": "universal_quantifier",
    "any": "existential_quantifier",
    "len": "cardinality",
    "sum": "accumulation",
    "array_equal": "array_equality",
    "get_sprites_by_tag": "tag_selection",
    "get_sprites_by_name": "name_selection",
    "get_sprite_at": "position_lookup",
    "get_sprites": "sprite_enumeration",
}


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    out = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            out[child] = node
    return out


def _game_class(tree: ast.AST) -> ast.ClassDef | None:
    """The ARCBaseGame subclass. Identified by base name, never by class name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if any(isinstance(b, ast.Name) and b.id == "ARCBaseGame" for b in node.bases):
                return node
    return None


def _advance_calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "next_level"]


def _guard_chain(node: ast.AST, parents: dict):
    """Walk up from the advance call, collecting the `if` tests that gate it.

    Returns (rendered_tests, test_nodes, enclosing_function). The nodes are returned alongside the
    text because the text is for a human and must not be parsed back: rendering negation as
    `not (expr)` and later stripping the wrapper truncates every predicate that legitimately ends in
    a parenthesis, which is most of them.

    A test reached through `orelse` is recorded negated — the branch that advances is the one that
    matters, and dropping the polarity would invert the meaning of every else-guarded predicate.
    """
    tests, nodes, fn, cur = [], [], None, node
    while cur in parents:
        parent = parents[cur]
        if isinstance(parent, ast.If):
            negated = any(cur is s or cur in set(ast.walk(s)) for s in parent.orelse)
            expr = ast.unparse(parent.test)
            tests.append(f"not ({expr})" if negated else expr)
            nodes.append(parent.test)
        elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn is None:
            fn = parent
        cur = parent
    return list(reversed(tests)), list(reversed(nodes)), fn


def _exits(body: list[ast.stmt]) -> bool:
    """Is this branch a guard clause — does control leave the block from its own top level?

    Both obvious spellings are wrong. Walking into the body counts a return nested inside a
    conditional, which does not exit unconditionally; requiring every statement to be a terminator
    rejects the ordinary guard clause that does some bookkeeping before returning. sc25's second
    clause is exactly that shape, and the strict reading dropped its precondition silently.
    """
    return any(isinstance(s, (ast.Return, ast.Raise, ast.Continue, ast.Break)) for s in body)


def _exit_guards(node: ast.AST, parents: dict) -> list[str]:
    """Preconditions imposed by early returns that precede the advance call.

    sc25 reaches `next_level()` with no enclosing `if` at all — the condition is the negative space
    left by two guard clauses that return first. Collecting only `If` ancestors reports that game as
    unconditional, which is the one reading guaranteed to be wrong.
    """
    out, cur = [], node
    while cur in parents:
        parent = parents[cur]
        for field, value in ast.iter_fields(parent):
            if not isinstance(value, list) or cur not in value:
                continue
            for sibling in value[:value.index(cur)]:
                if isinstance(sibling, ast.If) and _exits(sibling.body):
                    out.append(f"not ({ast.unparse(sibling.test)})")
        cur = parent
    return out


def _flag_sites(cls: ast.ClassDef, attrs: set[str], lines: list[str], parents: dict) -> dict:
    """Where each guard attribute is assigned, and under what condition.

    Several games gate advancement on a boolean flag — `if self.nyhaiggftp: self.next_level()` — so
    the guard expression names the flag and says nothing about the goal. The predicate is at the
    assignment. Reporting the flag check alone would render those games as trivially-guarded, which
    is precisely backwards: they are the ones whose condition is computed furthest away.
    """
    sites: dict[str, list] = {}
    for node in ast.walk(cls):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for t in targets:
            if not (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name)
                    and t.value.id == "self" and t.attr in attrs):
                continue
            fn, cur = None, node
            while cur in parents:
                cur = parents[cur]
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fn = cur
                    break
            guards, _, _ = _guard_chain(node, parents)
            sites.setdefault(t.attr, []).append({
                "function": fn.name if fn is not None else None,
                "line": node.lineno,
                "value": ast.unparse(node.value) if getattr(node, "value", None) is not None else None,
                "guards": guards + _exit_guards(node, parents),
                "source": "\n".join(lines[fn.lineno - 1:fn.end_lineno]) if fn is not None else "",
            })
    return sites


def _guard_attrs(nodes: list[ast.AST]) -> set[str]:
    """`self.x` read in a guard, excluding `self.x()` — a call is resolved as a method instead."""
    out, called = set(), set()
    for root in nodes:
        for n in ast.walk(root):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                called.add(n.func.attr)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
                out.add(n.attr)
    return out - called


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _self_calls(node: ast.AST) -> list[str]:
    return [n.func.attr for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Name) and n.func.value.id == "self"]


def _referenced(node: ast.AST) -> list[str]:
    """Every attribute and method name mentioned, at any depth of an attribute chain, SORTED.

    `self.player.solved` yields both `player` and `solved`. Chains are how the games delegate: the
    game object holds a helper instance and the real condition is a field on that helper.

    Bare function calls count too. `ka59` reaches its relation through `jxudaewdwt(a, b)` — an
    `ast.Name` call to a module-level `def`, not an attribute — so collecting only attribute names
    left it unreferenced and therefore unresolved, even once module-level functions were indexed.
    Indexing the definition and seeing the call site are two separate requirements and the gap needed
    both. Only names in FUNC position are taken; every `ast.Name` would drag in locals and builtins.

    Sorted, and returned as a list rather than a set, because this drives the resolution order and
    therefore the order blocks appear in the packet. Iterating a set of strings is ordered by hash,
    which Python randomises per process — so the identical corpus hashed differently on every run,
    which would have made the packet digests, and every integrity check built on them, meaningless.
    """
    names = {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
    names |= {n.func.id for n in ast.walk(node)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return sorted(names)


# Methods that WRITE to the container they are called on. A dict or set the guard reads is state,
# and `self.seen.add(x)` writes it every bit as much as `self.seen = {x}` does.
CONTAINER_MUTATORS = {"add", "append", "extend", "update", "insert", "discard", "remove", "pop",
                      "clear", "setdefault", "popitem", "sort", "reverse", "difference_update",
                      "intersection_update", "symmetric_difference_update"}


def _module_index(tree: ast.AST, parents: dict, lines: list[str]) -> tuple[dict, dict, dict]:
    """Index the whole module by function name, written-attribute name, and call site.

    Resolution is by NAME across the whole module, not by owning class, because inferring which
    class `self.vgwycxsxjz` is an instance of would need type inference the mangling defeats. Names
    are effectively unique under the obfuscation — where one is not, every defining site is reported
    rather than one being chosen, since choosing would silently pick a stranger's definition.

    TWO KINDS OF SITE THIS USED TO MISS, both found by raters confined to the packet:

    MODULE-LEVEL FUNCTIONS. The walk started from each `ClassDef`, so a bare `def` at module level was
    never indexed. ka59's advance predicate calls `jxudaewdwt(...)`, defined at line 41075 outside any
    class, and the packet therefore explained the universal quantifier while omitting the relation
    being quantified. This has been wrong since the first extraction; no earlier run surfaced it
    because raters filled the hole from the source instead of reporting it.

    CONTAINER MUTATION. A write was recognised only when the assignment target was `self.<attr>`.
    wa30's exclusion set is written as `self.zmqreragji[sprite] = ...` and `del self.zmqreragji[...]`
    — the target is a `Subscript` wrapping the attribute, matching nothing — so the guard's
    `sprite not in self.zmqreragji` conjunct had no population sites at all. Subscript assignment,
    `del`, and mutating method calls now all count as writes.
    """
    methods: dict[str, list] = {}
    attr_sites: dict[str, list] = {}

    def _owner(node: ast.AST) -> str:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, ast.ClassDef):
                return cur.name
        return "<module>"

    def _enclosing_fn(node: ast.AST):
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
        return None

    def _record(attr: str, node: ast.AST, rendered: str | None) -> None:
        fn = _enclosing_fn(node)
        guards, _, _ = _guard_chain(node, parents)
        attr_sites.setdefault(attr, []).append({
            "cls": _owner(node),
            "function": fn.name if fn is not None else None,
            "line": node.lineno,
            "value": rendered,
            "guards": guards + _exit_guards(node, parents),
            "node": node,
            "fn_node": fn,
        })

    def _self_attr(node: ast.AST) -> str | None:
        """`self.x` -> 'x'; `self.x[...]` -> 'x'; anything else -> None."""
        if isinstance(node, ast.Subscript):
            node = node.value
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id == "self"):
            return node.attr
        return None

    call_sites: dict[str, list] = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.setdefault(n.name, []).append((_owner(n), n))
        # Where each function is CALLED, with the condition guarding the call. A method that writes
        # a guard flag usually says nothing about the goal itself — sc25's arming method sets its
        # flag unconditionally, and bp35's sub-engine `win()` is a bare assignment. The condition a
        # player establishes is at the CALL, and without this it is nowhere in the packet.
        if isinstance(n, ast.Call):
            called = (n.func.attr if isinstance(n.func, ast.Attribute)
                      else n.func.id if isinstance(n.func, ast.Name) else None)
            if called is not None:
                fn = _enclosing_fn(n)
                guards, _, _ = _guard_chain(n, parents)
                call_sites.setdefault(called, []).append({
                    "cls": _owner(n),
                    "function": fn.name if fn is not None else None,
                    "line": n.lineno,
                    "call": ast.unparse(n)[:120],
                    "guards": guards + _exit_guards(n, parents),
                    "node": n,
                    "fn_node": fn,
                })
        targets = (n.targets if isinstance(n, ast.Assign)
                   else [n.target] if isinstance(n, (ast.AnnAssign, ast.AugAssign))
                   else n.targets if isinstance(n, ast.Delete) else [])
        for t in targets:
            attr = _self_attr(t)
            if attr is None:
                continue
            value = getattr(n, "value", None)
            _record(attr, n, ast.unparse(value) if value is not None else f"del {ast.unparse(t)}")
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr in CONTAINER_MUTATORS):
            attr = _self_attr(n.func.value)
            if attr is not None:
                _record(attr, n, ast.unparse(n))
    return methods, attr_sites, call_sites


def _local_names(node: ast.AST) -> set[str]:
    """Bare local names READ by an expression — not attributes, not call targets."""
    return {n.id for n in ast.walk(node)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)} - {"self", "True", "False",
                                                                           "None"}


def _local_bindings(fn: ast.FunctionDef | None, names: set[str]) -> dict[str, list]:
    """Assignments to those locals inside the function that guards the write.

    Scoped to the one function on purpose. A local name is meaningful only inside its frame, and
    matching it module-wide would attach a stranger's variable of the same short mangled name.
    """
    out: dict[str, list] = {}
    if fn is None or not names:
        return out
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out.setdefault(t.id, []).append(n)
    return {k: out[k] for k in sorted(out)}


def _window(lines: list[str], fn: ast.FunctionDef | None, node: ast.AST, span: int) -> str:
    """Source for an assignment site: the whole function when short, else a window around the line.

    Whole functions are preferable — the condition is often computed a few lines above the
    assignment — but `step()` in these games runs to hundreds of lines and would crowd out every
    other site in the packet.
    """
    if fn is not None and (fn.end_lineno - fn.lineno) <= span:
        return "\n".join(lines[fn.lineno - 1:fn.end_lineno])
    lo = max(0, node.lineno - 1 - span // 2)
    hi = min(len(lines), node.lineno + span // 2)
    return "\n".join(lines[lo:hi])


def _features(nodes: list[ast.AST]) -> dict:
    """Structural facts about the guard closure. Diagnostics only — see module docstring."""
    found, cmp_ops, iterates, attrs = set(), set(), 0, set()
    for root in nodes:
        for n in ast.walk(root):
            if isinstance(n, ast.Call):
                name = n.func.attr if isinstance(n.func, ast.Attribute) else (
                    n.func.id if isinstance(n.func, ast.Name) else None)
                if name in FEATURE_CALLS:
                    found.add(FEATURE_CALLS[name])
            elif isinstance(n, ast.Compare):
                cmp_ops.update(type(o).__name__ for o in n.ops)
            elif isinstance(n, (ast.For, ast.comprehension)):
                iterates += 1
            elif isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
                attrs.add(n.attr)
    return {
        "calls": sorted(found),
        "comparisons": sorted(cmp_ops),
        "iterations": iterates,
        "self_attributes_read": len(attrs),
    }


def extract(env: str, path: Path, depth: int, max_lines: int,
            max_sites: int = 6, window: int = 60) -> dict:
    src = path.read_text()
    lines = src.splitlines()
    tree = ast.parse(src)
    cls = _game_class(tree)
    if cls is None:
        return {"env": env, "error": "no ARCBaseGame subclass found"}
    calls = _advance_calls(cls)
    if len(calls) != 1:
        # Not fatal, but the one-site assumption is what makes "the guard" singular. Say so.
        return {"env": env, "error": f"{len(calls)} next_level() call sites, expected 1"}

    parents = _parents(tree)
    tests, test_nodes, fn = _guard_chain(calls[0], parents)
    preconditions = _exit_guards(calls[0], parents)
    methods, attr_sites, call_sites = _module_index(tree, parents, lines)

    # Seed from BOTH the enclosing `if` tests and the early-return preconditions. sc25 has no `if`
    # at all, so seeding from tests alone leaves its guard flag unresolved and the game unlabelable.
    pre_nodes = []
    for p in preconditions:
        try:
            pre_nodes.append(ast.parse(p, mode="eval").body)
        except SyntaxError:
            pass
    # The enclosing function goes into the packet for context but NOT into the name search. Seeding
    # resolution from it pulls every attribute `step()` touches — movement, rendering, input — and
    # under module-wide lookup that reached the line cap for 15 of 25 games, burying the condition
    # in the material it was supposed to be distinguished from. Resolution follows the CONDITION.
    condition_nodes = list(test_nodes) + pre_nodes
    seed = condition_nodes + ([fn] if fn is not None else [])

    # Breadth-first over NAMES. A name resolves to method definitions, to attribute assignment
    # sites, or to both, anywhere in the module — 13 of the 25 games route their condition through a
    # helper class, so game-class-only resolution bottoms out on an opaque field for the majority.
    resolved, resolved_nodes, flag_sites = {}, [], {}
    direct_names = {n for r in condition_nodes for n in _referenced(r)}
    queue = [(n, 1) for n in sorted(direct_names)]
    seen, truncated_depth, truncated_sites = set(), False, []
    while queue:
        name, d = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        if d > depth:
            truncated_depth = True
            continue
        for cls_name, m in methods.get(name, [])[:max_sites]:
            key = f"{cls_name}.{name}"
            # Slice the ORIGINAL lines for readability, but keep the node for analysis — a method
            # body lifted out of a class is indented and will not re-parse on its own.
            resolved[key] = "\n".join(lines[m.lineno - 1:m.end_lineno])
            resolved_nodes.append(m)
            queue += [(c, d + 1) for c in _referenced(m)]
        sites = attr_sites.get(name, [])
        # An attribute the GUARD ITSELF reads is never skipped for being written in many places.
        # `max_sites` exists to stop a heavily-mutated bookkeeping field from flooding the packet,
        # but applied to a direct guard attribute it removes the very thing being explained: su15
        # tests `self.vsfwpngmx` and `self.qygchysnh` and both have nine assignment sites, so the
        # packet omitted the arming conditions of both its guard flags — while reporting no
        # truncation at all. Over-budget skips are now recorded rather than silent.
        if sites and len(sites) > max_sites and name not in direct_names:
            truncated_sites.append(f"{name} ({len(sites)} sites)")
        elif sites:
            flag_sites[name] = [{k: v for k, v in s.items() if k not in ("node", "fn_node")}
                                for s in sites]
            for s in sites:
                resolved[f"={name}@{s['line']}"] = (
                    f"# --- sets self.{name} in {s['cls']}.{s['function']}() line {s['line']} ---\n"
                    + _window(lines, s["fn_node"], s["node"], window))
                resolved_nodes.append(s["node"])
                for g in s["guards"]:
                    try:
                        g_node = ast.parse(g, mode="eval").body
                    except SyntaxError:
                        continue
                    queue += [(c, d + 1) for c in _referenced(g_node)]
                    # LOCAL BINDINGS. A guard can rest on a plain local: sk48 arms its flag under
                    # `nuikqmprbq`, bound one line earlier by `nuikqmprbq = self.gvtmoopqgy()`.
                    # `_referenced` collects attributes and bare calls, so a local name reaches
                    # nothing and the predicate behind it stayed invisible — the packet explained
                    # the countdown and never the condition that started it.
                    for local, binds in _local_bindings(s["fn_node"], _local_names(g_node)).items():
                        for b in binds[:max_sites]:
                            resolved[f"~{local}@{b.lineno}"] = (
                                f"# --- local {local} bound in {s['function']}() line {b.lineno} ---\n"
                                + _window(lines, s["fn_node"], b, window))
                            resolved_nodes.append(b)
                            queue += [(c, d + 1) for c in _referenced(b.value)]
                # ARMING CALL SITES. The function that writes the flag frequently says nothing
                # about the goal — sc25's arming method sets its flag unconditionally, and the
                # sub-engine `win()` in bp35 and lf52 is a bare assignment. What the player must
                # establish is the condition guarding the CALL, which lives in another function
                # entirely and was in no packet at all.
                # Only for a write that is itself near-unconditional. If the writer already carries
                # its own guards, those ARE the condition and the call site adds the caller's
                # unrelated context; sc25 and the sub-engine `win()` are the opposite case, writing
                # the flag with nothing to say about why. Constructors are never followed — `__init__`
                # has a call site for every instantiation in the file and explains nothing.
                callers = ([] if (s["function"] or "").startswith("__") or len(s["guards"]) > 1
                           else call_sites.get(s["function"]) or [])
                if len(callers) > max_sites:
                    truncated_sites.append(f"{s['function']}() call sites ({len(callers)})")
                    callers = callers[:max_sites]
                for c_site in callers:
                    if c_site["fn_node"] is s["fn_node"]:
                        continue          # self-recursion, or the writer calling itself
                    resolved[f"@{s['function']}@{c_site['line']}"] = (
                        f"# --- {s['cls']}.{s['function']}() is CALLED in "
                        f"{c_site['cls']}.{c_site['function']}() line {c_site['line']}, under "
                        f"{c_site['guards']} ---\n"
                        + _window(lines, c_site["fn_node"], c_site["node"], window))
                    resolved_nodes.append(c_site["node"])
                    for g in c_site["guards"]:
                        try:
                            queue += [(c, d + 1)
                                      for c in _referenced(ast.parse(g, mode="eval").body)]
                        except SyntaxError:
                            pass

    enclosing = "\n".join(lines[fn.lineno - 1:fn.end_lineno]) if fn is not None else ""
    parts = [enclosing] + [v for k, v in resolved.items() if v != enclosing]
    packet = "\n\n".join(p for p in parts if p)
    truncated_lines = len(packet.splitlines()) > max_lines
    if truncated_lines:
        packet = "\n".join(packet.splitlines()[:max_lines])

    return {
        "env": env,
        "source": str(path.relative_to(REPO)),
        "advance_line": calls[0].lineno,
        "enclosing_function": fn.name if fn is not None else None,
        "guard_tests": tests,
        "preconditions_from_early_returns": preconditions,
        "flag_sites": {k: sorted(v, key=lambda e: e["line"]) for k, v in sorted(flag_sites.items())},
        "resolved_methods": sorted(resolved),
        "features": _features(seed + resolved_nodes),
        "truncated_at_depth": truncated_depth,
        "truncated_at_max_lines": truncated_lines,
        "truncated_at_max_sites": sorted(set(truncated_sites)),
        "evidence": packet,
        # Deliberately empty. See module docstring — this script does not classify.
        "label": {"predicate_classes": [], "notes": "", "rater": None},
    }


def build(out: Path, depth: int, max_lines: int, max_sites: int, window: int) -> int:
    sources = sorted(ENVS.glob("*/*/*.py"))
    if not sources:
        print(f"no game sources under {ENVS}")
        return 1
    records = [extract(p.parent.parent.name, p, depth, max_lines, max_sites, window) for p in sources]

    errors = [r for r in records if "error" in r]
    ok = [r for r in records if "error" not in r]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "games": len(records),
        "extracted": len(ok),
        "depth": depth,
        "max_lines": max_lines,
        "unlabelled": len(ok),
        "records": records,
    }, indent=1) + "\n")

    print(f"extracted {len(ok)}/{len(records)} games")
    print(f"\n{'env':<6}{'guards':>7}{'helpers':>8}{'lines':>7}  features")
    for r in ok:
        f = r["features"]
        marks = "".join([
            "D" if r["truncated_at_depth"] else " ",
            "L" if r["truncated_at_max_lines"] else " ",
            "S" if r["truncated_at_max_sites"] else " ",
        ])
        print(f"{r['env']:<6}{len(r['guard_tests'])+len(r['preconditions_from_early_returns']):>7}"
              f"{len(r['resolved_methods']):>8}"
              f"{len(r['evidence'].splitlines()):>7} {marks} "
              f"{','.join(f['calls']) or '-'}  cmp={','.join(f['comparisons']) or '-'}  it={f['iterations']}")
    if errors:
        print(f"\n{len(errors)} game(s) not extracted:")
        for e in errors:
            print(f"   {e['env']}: {e['error']}")
    trunc = [r["env"] for r in ok if r["truncated_at_depth"] or r["truncated_at_max_lines"]
             or r["truncated_at_max_sites"]]
    if trunc:
        print(f"\ntruncated packets (D=depth, L=max-lines, S=max-sites): {', '.join(trunc)}")
        for r in ok:
            if r["truncated_at_max_sites"]:
                print(f"   {r['env']} skipped over-budget: {sorted(set(r['truncated_at_max_sites']))}")
        print("   raise --depth/--max-lines before labelling these — a dropped branch reads as a simple predicate")
    print(f"\n{len(ok)} records written unlabelled. Labels are assigned by a rater, not by this script.")
    print(f"wrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/s2_goal_predicates.json")
    ap.add_argument("--depth", type=int, default=10, help="transitive resolution depth for self.<method>()")
    ap.add_argument("--max-sites", type=int, default=6,
                    help="skip a name assigned in more sites than this — it is state, not a goal flag")
    ap.add_argument("--window", type=int, default=60,
                    help="source lines around an assignment when its function is too long to inline")
    ap.add_argument("--max-lines", type=int, default=12000, help="cap on evidence packet size")
    args = ap.parse_args()
    return build(Path(args.out), args.depth, args.max_lines, args.max_sites, args.window)


if __name__ == "__main__":
    raise SystemExit(main())
