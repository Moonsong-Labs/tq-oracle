from __future__ import annotations

from ..processors.asset_aggregator import AggregatedAssets
from ..adapters.price_adapters.base import PriceData


def calculate_total_assets(
    aggregated_assets: AggregatedAssets,
    prices: PriceData,
) -> int:
    if aggregated_assets.assets.keys() != prices.prices.keys():
        raise ValueError("Aggregated assets and relative prices have different keys")

    return sum(
        aggregated_assets.assets[i] * prices.prices[i] for i in aggregated_assets.assets
    )
