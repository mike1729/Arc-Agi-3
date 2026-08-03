"""ES source adapter for ls20 — versioned wrapper over the GI-2 estate (increment 1)."""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="ls20", adapter_version=1)
