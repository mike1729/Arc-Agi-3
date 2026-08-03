"""ES source adapter for dc22 — versioned wrapper over the GI-2 estate (increment 1)."""

from es_sources import GameAdapter

ADAPTER = GameAdapter(env="dc22", adapter_version=1)
