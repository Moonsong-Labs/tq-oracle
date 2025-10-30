from __future__ import annotations

from dataclasses import dataclass

from ..state import AppState
from ..processors import AggregatedAssets


@dataclass
class PipelineContext:
    state: AppState
    vault_address: str
    aggregated: AggregatedAssets | None = None
