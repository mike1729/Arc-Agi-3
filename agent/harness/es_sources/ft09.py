"""ES source adapter for ft09 — versioned wrapper over the GI-2 estate (increment 1)."""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="ft09", adapter_version=1)
