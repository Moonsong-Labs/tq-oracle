from __future__ import annotations

from dataclasses import dataclass

from ..state import AppState
from ..processors import AggregatedAssets
from ..processors import FinalPrices
from ..adapters.price_adapters.base import PriceData


@dataclass
class PipelineContext:
    state: AppState
    vault_address: str
    aggregated: AggregatedAssets | None = None
    price_data: PriceData | None = None
    total_assets: int | None = None
    final_prices: FinalPrices | None = None
