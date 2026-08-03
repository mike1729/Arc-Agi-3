"""ES source adapter for tu93 — versioned wrapper over the GI-2 estate (increment 1)."""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="tu93", adapter_version=1)
