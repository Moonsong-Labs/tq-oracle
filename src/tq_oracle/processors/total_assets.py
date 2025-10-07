from __future__ import annotations

from ..processors.asset_aggregator import AggregatedAssets
from ..processors.price_calculator import RelativePrices


def calculate_total_assets(
    aggregated_assets: AggregatedAssets,
    relative_prices: RelativePrices,
) -> int:
    if aggregated_assets.assets.keys() != relative_prices.prices.keys():
        raise ValueError("Aggregated assets and relative prices have different keys")

    return sum(
        aggregated_assets.assets[i] * relative_prices.prices[i]
        for i in aggregated_assets.assets
    )
