"""ES source adapter for vc33 — versioned wrapper over the GI-2 estate (increment 1).

vc33 carries the accepted 2026-07-30 settled-frame fidelity erratum: replay equality is
required on settled, solved-terminal, and next-level frames; intermediate animation-frame
divergence is recorded but is not a fidelity failure (gate_manifest -> es ->
corpus.vc33_fidelity; gi2_ar_freeze.json pins the acceptance).
"""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="vc33", adapter_version=1, settled_frame_erratum=True)
