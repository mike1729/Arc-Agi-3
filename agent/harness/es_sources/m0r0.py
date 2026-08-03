"""ES source adapter for m0r0 — versioned wrapper over the GI-2 estate (increment 1)."""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="m0r0", adapter_version=1)
