# Methods — goal predicates recovered from environment source

*Written 2026-07-28, the day the extraction was built (§5 standing obligation). Implementation:
`agent/harness/{s2_goal_predicates,s2_apply_labels}.py`; outputs `logs/s2_goal_predicates.json`,
`logs/s2_labels_round3.json`, `logs/s2_rerate_r3_pass2.json`, `logs/s2_rerate_r3_result.json`.
Round 1's inputs and results are quarantined under
`logs/quarantine/s2-superseded-worksheet-2026-07-28/`; round 2's (`s2_labels_round2.json`,
`s2_rerate_r2_*.json`) are retained as the record of a measurement over packets that five extraction
repairs have since changed. Neither is current.*

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

## Agreement, round 3

Three rounds were run. Only the third is a measurement; the earlier two are the record of finding out
why they were not. Round 1 paired the extraction's own author against fresh readers over packets since
invalidated, and reported 0.537. Round 2 was the first with both passes in fresh contexts and reported
0.858, but six environments in it were rated blind to their own deciding condition. Round 3 follows
five extraction repairs, each found by a rater who was required to report a missing condition rather
than fetch it from the source.

Cohen's kappa on the primary class is **0.947** over all twenty-five environments (observed 0.960,
expected 0.243), and 0.940 over the twenty-two whose packets are complete. Seventeen of twenty-five
received identical class sets, and the mean Jaccard is 0.807. Agreement on `guard_form` is **1.000** —
the two passes agree without exception on how each condition is reached from the advance site, which
is the structural question every one of the repairs was about.

Exactly one primary assignment differs, and it is not a disagreement about content: both passes chose
the same two classes for that environment and ordered them differently. There is no environment where
the passes read different conditions.

The repairs are what moved the figure, not the raters. Five of round 2's six blind environments now
carry their condition in the packet and are read identically by both passes: one went from a blind
"an event fired" to a state relation in both passes; another from two passes disagreeing while blind
to an identical pair of classes; a third from reporting as *unconditional* to a call-site move
condition read the same way twice. Three environments remain flagged, and only one seriously — a
sub-engine whose win event is reached through two hops of delegation where the extraction follows one.
The other two are missing peripheral helpers that neither pass treated as load-bearing.

## What the corpus says

Quantified object conditions are the primary class in nine and ten of twenty-five across the two
passes, and present in thirteen and fourteen — universals of the form "every object of this kind
stands in this relation to one of those". State relations are primary in five and six and present in
twelve and fourteen. Symmetry and template match is primary in five in both.

Two results survived all three rounds and are firmer for it.

Region membership is the primary class in **zero** environments in both passes while present in five
and six. It is real and never dominant: a component of goals rather than a shape of them.

Action-conditioned terminal triggers and cumulative counters are at **zero in every position, in both
passes**. Two of the ten pre-specified classes are unexercised by this corpus. Round 1 concluded the
opposite — that every class occurred and the library was therefore adequate — and that conclusion was
an artifact of packets that did not contain their conditions. Neither pass in any round reached for
the escape category, so nothing in these environments demanded a class the codebook lacks. The
codebook is oversized for the public set, not incomplete.

## Limitations

Both passes are the same model family in fresh contexts, so kappa bounds the *stability* of the
labelling and never its correctness. A confound reproduced by two readers raises the figure rather
than exposing anything. A human re-rate remains outstanding, and no figure here should be compared
against a literature expecting human test-retest.

Each pass is eight raters over disjoint batches, so the statistic compares two composite readers.
Batches are balanced by evidence volume rather than item count, which removes the largest confound
that introduces — one environment's packet is larger than most whole batches and was rated alone,
so its label carries no cross-item calibration.

Three environments were still rated without their full deciding condition. One is materially
affected; for the other two both passes judged the missing helper peripheral and labelled from what
was present. Frequencies rest on twenty-two environments read completely and three read partially.

The packets are verbose in a way that should be fixed before anyone reads this corpus again: roughly
forty-four per cent of the largest ones is duplicated text, because several writes to the same guard
flag each emit their own overlapping window of the enclosing function. The corpus grew from 18.6k to
45.8k lines across the repairs, and about half of that growth is repetition rather than coverage. It
is redundant rather than misleading, so it does not threaten these labels, but it inflates every
reader's load and should be deduplicated by emitting each distinct source region once.

Round 3's second pass is bound to the worksheet it was produced from by a worksheet identifier and a
per-item digest. This closes a hole in our own verifier rather than in the extraction: item ids are
positional and the draw seed is fixed, so a ratings file fits any worksheet of the same size, and the
digest check proved worksheet-against-corpus while never proving ratings-against-worksheet. Round 2's
0.858 was true but unprovable for exactly that reason, and it is reported here as superseded rather
than as a comparison.

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
