# Methods — the human replay corpus

*Written 2026-07-28, the day the ingestion was built (§5 standing obligation). Implementation:
`agent/harness/s2_replay_ingest.py`; output `logs/s2_replay_sessions.json`.*

## Provenance

The corpus is the public human-testing release accompanying the interactive benchmark, comprising
step-by-step recordings of human play across the twenty-five public environments. We obtained it twice
by independent routes — the archive published by the benchmark authors, and a third-party mirror
redistributed on the competition platform — and verified that the two agree file for file under a
content hash, with no path present in one and absent from the other. We work from the mirror because
it can be attached to a submission notebook in the offline execution environment, and we retain the
authors' archive as the provenance record. The verification exists because the mirror is the copy we
use and its uploader is not the data's author; agreement with the authored archive is what licenses
that substitution, and it is cheap enough that assuming it would have been the only reason not to
check.

We record separately that redistribution rights are not established by any of this. The authors
describe the release as open, but the archive carries no licence file, and the platform mirrors carry
licence declarations made by uploaders who do not hold the rights they purport to grant. Provenance is
settled; permission to redistribute inside a published artifact is not, and is treated as an open
question rather than a resolved one.

## The unit of observation

We take the recording as the unit and report a count of files, not of plays. The distinction is not
pedantic. Each recording ends with a summary object whose fields are parallel arrays with one slot per
play, and three of the recordings describe two plays: one real, one an abandoned stub with no
recording of its own. Counting slots yields three more observations than there are recordings, and
those three carry another session's zero-action abandonment.

The archive holds three hundred and forty recordings where the authors' published per-environment
table reports three hundred and forty-two plays. The shortfall is not distributed. It falls entirely
on one environment, and three independent counts agree on its size: plays, where the table exceeds the
archive by two; solves, where the table reports one more than the archive contains; and the separately
published post-play ratings, of which every row but one joins a recording, the exception naming that
same environment and recording a solve. Two sessions from one environment are absent from the release,
one of them successful, and an artifact of one survives in the ratings file. We therefore report
counts from the data, note that the affected environment's solve rate is understated by the loss, and
treat the published table as a description of what was played rather than of what was released.

## Per-level action costs

The field naming per-level progress is cumulative, not per-level. Each entry pairs a level index with
the total number of actions elapsed at the moment that level was completed, measured from the start of
the session. Per-level cost is its first difference.

We state this at length because the field's name, and the description accompanying at least one
republication of the data, both invite the literal reading, and because the literal reading fails in a
way that is very difficult to detect downstream. The error is zero for the first level of every
session and grows monotonically with level index, so a corpus read literally does not look corrupt. It
looks like a corpus in which later levels are much more expensive than earlier ones — which is
independently true, and which is exactly the qualitative claim such a corpus would be used to
support. Nothing about the resulting distribution invites suspicion.

The differencing is validated externally rather than asserted. The competition distributes, for each
environment, a per-level human action baseline used in its own scoring; this is a separate artifact,
in the opposite convention, and was not derived by us. Comparing our differenced per-level medians
against it across one hundred and eighty-three environment-levels gives a median ratio of one, with
ninety-four exact ties. Read literally instead, the same comparison diverges systematically and
increasingly with depth. We therefore report two things: that the differencing is correct, and that
the competition's published baseline is the median per-level human cost computed over these same
sessions — an identification that makes the scoring denominator reproducible from the corpus rather
than accepted on the organisers' authority.

## Action totals are read, not reconstructed

Each recording is a sequence of per-action records terminated by the summary. The obvious integrity
check is that the records number the declared action total, and it is wrong. Scanning every record of
every session, three conventions coexist. In most sessions the declared total excludes both an initial
reset frame and any undo actions. In twenty-three sessions no initial reset frame is recorded at all,
and the declared total equals the record count. In twenty-two others, drawn from two environments,
undo actions are scored after all. Mid-session resets are scored throughout. One environment
additionally encodes action identifiers as strings where every other encodes them as integers, and
that encoding coincides with the absence of the initial reset frame, which suggests two client
versions rather than a per-environment rule.

We therefore treat the declared action total as authoritative and record the discrepancy against the
record count as an observation rather than an error. The declared total and the cumulative per-level
field are in the same units as each other, which is the consistency the per-level costs actually
depend on, and the external agreement above confirms it. Reconstructing the total from the record
stream would have introduced a per-environment bias of unknown sign into the denominator of every
efficiency figure. Our first implementation asserted the naive rule and reported three hundred and
twenty-one violations, which is how the three conventions were found; we note this because the
assertion failing loudly is the only reason the corpus was not silently accepted with a wrong
denominator for one environment in twelve.

## Post-play ratings

A small companion file records subjective ratings of enjoyment and difficulty against session
identifiers. Every rating that joins our corpus belongs to a session that succeeded. The file is
therefore a difficulty judgment conditioned on success, not a sample of participants' experience, and
cannot be read as a difficulty ordering over the environments as encountered. Used with that
restriction it is informative, but weakly so. The difficulty ordering it induces correlates with the
solve-rate ordering computed independently from the recordings at a rank correlation of −0.44 across
the twenty-five environments — the expected sign, and far from agreement. Since both quantities are
conditioned on the same successful sessions, we read this as evidence that perceived difficulty and
completion rate are not interchangeable, and use neither as a proxy for the other.

## Limitations

One environment contributes fifty-four of the three hundred and forty recordings because it was
included in an earlier preview of the benchmark, and its sessions therefore come from an older build.
Its recorded version hash matches the current distribution, so we do not exclude it, but any analysis
sensitive to environment revision should treat it separately, and any per-environment average computed
over the pooled corpus is weighted toward it by a factor of roughly five.

The corpus describes twenty-five public environments out of a benchmark of one hundred and thirty-five.
Public environments are known to be materially easier than held-out ones, and no property measured here
transfers to the held-out set by construction. We use the corpus to measure the distribution of
structures across environments, never to enumerate the structures of these particular environments, and
we record frequencies rather than instances for that reason.

Finally, the participant sample is small — ten to fifteen sessions per environment, before conditioning
on success — so per-level costs at depth rest on very few observations. The number of sessions
contributing to each level falls away with depth as participants stop advancing, and we report that
count alongside every per-level statistic rather than presenting deep-level medians as though they
were supported at the same strength as shallow ones.
