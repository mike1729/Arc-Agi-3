# Methods — goal predicates recovered from environment source

*Written 2026-07-28, the day the extraction was built (§5 standing obligation). Implementation:
`agent/harness/{s2_goal_predicates,s2_apply_labels}.py`; outputs `logs/s2_goal_predicates.json`,
`logs/s2_labels_round2.json`, `logs/s2_goal_predicates_labelled.json`. Round 1's inputs and results
are quarantined under `logs/quarantine/s2-superseded-worksheet-2026-07-28/`; the worksheet they used
differs from the corrected extraction on seventeen of twenty-five packets.*

## Why the predicates are measured rather than inferred

The competition distributes the Python source of all twenty-five public environments. Each defines
exactly one site at which the level advances. The condition guarding that site is the goal: the
property a player must establish to progress. This makes the goal predicate of each environment
recoverable as ground truth, where the alternative — inferring it from watching agents or humans play
— recovers only what the observer believed the goal to be. We use the source for the predicate and
reserve the play data for behaviour.

The recovery is not a matter of printing a line. Identifiers are systematically obfuscated, and the
scheme differs between environments, so nothing can depend on names. Resolution is structural,
performed over the syntax tree.

## What has to be resolved, and why the obvious extraction misreads the corpus

The guarding condition is stated at the advance site in only three of twenty-five environments. The
remaining twenty-two take one of three other forms, each of which the naive extraction reports
incorrectly rather than incompletely:

In ten environments the condition is *delegated* to a method, so the advance site names a function and
nothing else. In six it is an *instance flag*: the site tests a boolean, and the condition is wherever
that boolean is assigned — which is not merely elsewhere, but characteristically the furthest-away
computation in the file. Reported literally these read as the simplest environments in the set, when
they are the ones whose goal is least locally visible. In six more the advance is *deferred behind an
animation*: the real condition arms a countdown, and the site tests only that the countdown expired.
Labelling those from the site alone would record a timer as the goal. One environment has no guarding
conditional at all — the call sits at function top level behind two early returns, and its condition
is their negative space, so a scan for enclosing conditionals reports it as unconditional.

The extraction therefore resolves, transitively and by name across every class in the module: methods
called from the condition; the assignment sites of any attribute the condition reads, together with
the conditions under which those assignments occur; and the negated tests of preceding guard clauses.
Module-wide resolution is necessary because thirteen environments route the condition through a helper
class, and inferring which class an obfuscated attribute belongs to would require type inference the
obfuscation defeats. Where a name is defined in more than one class every definition is reported, since
choosing one would silently substitute a stranger's definition.

Resolution follows the condition and not the enclosing function. Seeding it from the function pulls in
every attribute the step handler touches — movement, rendering, input — which in our first attempt
reached the size cap for fifteen of twenty-five environments and buried the condition in exactly the
material it needed to be distinguished from. Both remaining bounds are recorded per record and
reported, because a packet that had silently dropped the branch carrying the real condition would read
as a simple predicate.

## Labelling

The extraction assigns no classes. It emits an evidence packet per environment with an empty label,
and a rater assigns classes by reading. This follows the labelling method used for our failure corpus
and for the same reason: these frequencies are intended to order construction of goal-induction
machinery, and a rule mapping syntax onto the class library would manufacture the distribution it was
meant to measure. An array-equality call is not a template match; it is a call that a rater may judge
implements one, after reading what is compared against what. Structural facts — whether the condition
quantifies, compares a cardinality, iterates a collection — are recorded alongside as diagnostics, and
are never permitted to determine a label.

The class library is the ten predicate classes fixed in advance in our architecture analysis. It is
closed at merge time, and a predicate that does not fit is recorded under an explicit escape category,
counted and reported separately. A library that quietly absorbs whatever arrives cannot be found
wrong, and discovering that it is incomplete is worth more before the induction machinery is built
than after.

It is a pre-*specified* codebook and not a pre-*registered* instrument, and the distinction is not
pedantic in a project that treats pre-registration as a formal act. The list was fixed before any
environment was read and has not changed since, but it was never entered in the gate manifest, where
this sprint is still recorded as not started. Every frequency below therefore rests on an
investigator-fixed codebook applied to a corpus the same investigator assembled, with no external
record of the list predating the analysis. That is a weaker guarantee than pre-registration and is
carried as a limitation rather than described as one.

Two frequencies are reported. The primary share ranks what each predicate mainly is; the any-class
share counts every class judged present, so that a class which is pervasive as a component but never
dominant does not read as absent.

## Agreement, round 2

The section this replaces reported round 1, in which the first pass was the same agent that built the
extraction and the second was fresh contexts. Two defects were then found by review: the extraction
silently discarded the assignment sites of any attribute written in more than six places, including
attributes the advance guard reads directly, and name resolution iterated a set, so the identical
corpus hashed differently on every run. Correcting both changed seventeen of twenty-five packets, and
round 1's figures — a primary-class kappa of 0.537 — describe a corpus that no longer exists. They are
not reported here as a comparison, because round 2 does not measure the same thing.

Round 2 changed the design in three ways. Both passes are fresh contexts, so the statistic is
reader-against-reader rather than author-against-reader. Batches are balanced by evidence volume
rather than by item count, because the corrected packets range from fourteen lines to over two
thousand and an unbalanced split would enter reader fatigue as if it were item difficulty. And raters
are confined to the packet: where the evidence does not contain the deciding condition they are
required to say so rather than consult the environment source. In round 1 raters on both passes
silently filled such gaps from the source, which is how the two passes came to rate different
material.

Cohen's kappa on the primary class is 0.858 over all twenty-five environments (observed agreement
0.880, expected 0.155). Exact agreement on the full class set is 0.640 and the mean Jaccard 0.767;
sixteen of twenty-five environments received identical class sets. Agreement on `guard_form` — the
structural question of how the condition is reached from the advance site — is 0.920.

Only three primary assignments differ, and two are near-misses rather than genuine disagreements: one
pair chose the same two classes and ordered them differently, and in another the second pass returned
a strict superset of the first. The third is an environment whose deciding predicate is absent from
its packet, so the two passes were reasoning about different things by construction.

Restricted to the nineteen environments whose packets are complete, kappa is 0.871 and only those two
near-misses remain. That the figure barely moves is itself informative: the under-determined packets
are not where the readers disagree, because a packet that visibly lacks its condition produces a
cautious label from both readers rather than two confident and different ones.

## What the corrected corpus says

Both passes now agree on the shape of the distribution, and it is not the shape round 1 reported.

Quantified object conditions are the primary class in six of twenty-five environments in both passes —
not the ten that round 1 claimed. State relations are primary in four and five, and are the most
common component. Symmetry and template match, event occurrence and all-instances-transformed each
sit at three or four primary. Counts and ordered event programs are primary once each in both passes.

Two of the ten pre-specified classes are effectively unexercised by this corpus. Action-conditioned
terminal triggers were not assigned by either pass, in any position. Cumulative counters were not
assigned as a primary class by either pass and appear once as a component. A closed class library was
adopted precisely so that this could be observed rather than absorbed, and it is the more useful
finding: the library is not incomplete, it is oversized for the public set.

Neither pass reached for the escape category. Nothing in these twenty-five environments demanded a
class the library lacks.

## Limitations

Both passes are the same model family in fresh contexts, so kappa bounds the *stability* of the
labelling and never its correctness. A confound reproduced identically by two readers raises the
figure rather than exposing anything, and one model reading obfuscated source may share systematic
blind spots with another. A human re-rate remains outstanding, and no figure here should be compared
against a literature expecting human test-retest.

Each pass is five raters over disjoint batches rather than one rater over all twenty-five, so the
statistic compares two composite readers and mixes between-rater variance into what is reported as
item variance. Balancing batches by evidence volume removes the largest confound this introduces but
not the effect itself.

**Six environments were rated on packets that do not contain their deciding condition**, and both
passes flagged them rather than filling them from source. Three distinct extraction gaps remain
responsible: the arming call site of a trigger method is not followed; a scripted win event inside an
embedded sub-engine is not crossed into; and a predicate reached through a local binding — `x =
self.method()` in the enclosing function — never enters resolution. Every label on those six is a
judgment about a condition the rater could not see, and the class frequencies should be read as
resting on nineteen environments, not twenty-five.

**The packets these figures were computed over have themselves since been superseded.** Two further
gaps were found and closed while round 2's second pass was already running: container mutation
(`self.d[k] = v`, `del`, and mutating method calls) was not recognised as a write at all, and
module-level functions were never indexed, which additionally required collecting bare-name calls
since the reference walk only gathered attributes. Closing them changes sixteen of twenty-five
packets. The corpus was deliberately not regenerated mid-flight, so round 2 measures two readers on
identical material and its kappa stands; its class distribution is provisional until a round 3 over
the corrected packets.

**Round 2's kappa is not currently reproducible, and that is a defect in the instrument rather than
in the round.** The scorer bound the worksheet to the corpus but never bound the submitted second
pass to the worksheet. Item ids are positional (`g00`..`g24`), so a ratings file fits any worksheet of
the same size: the superseded round's ratings scored cleanly against the corrected worksheet and
reported a kappa of 0.659 with seventeen of twenty-five packets changed underneath. Two passes rating
different material is not an agreement measurement, and nothing in the artifact said so.

The binding now exists — `draw` emits a `worksheet_id` over the ordered (item, packet-digest) pairs
plus a pre-filled ratings template carrying it and the per-item digests, and `score` refuses a pass
whose binding does not match. Round 2's ratings predate it and therefore **refuse**, so **0.858 is
recorded here as the figure that round produced, not as a figure this repository can currently
re-derive.** It should be treated as provisional on exactly the same footing as the class
distribution, and superseded by round 3 rather than compared against it.

Frequencies are over environments, not over levels. Cross-level transfer in this benchmark is
parameterized rather than literal — the family persists while targets, regions and orderings change —
so a per-environment frequency is the correct unit for choosing which families to support, and would
be the wrong unit for estimating how often a hypothesis class is needed during play.

Twenty-five environments out of a hundred and thirty-five, and public ones, which are materially
easier than the held-out set. A class absent here is not shown to be rare; it is shown to be
unrankable from this corpus. That distinction matters most exactly where the counts are thinnest, and
the re-rate sharpened it: the thin classes are not merely thin, they are the ones the two passes
disagree about, including which single environment carries the only ordered-event-program instance.

Finally, three of the predicates mutate state while evaluating, and two environments delegate the
condition into a sub-engine whose win event is scripted rather than computed from the board. For those
the goal is not a property of the observable state at all, and any induction scheme that assumes goals
are state predicates will not represent them.
