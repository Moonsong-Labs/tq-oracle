from __future__ import annotations

from ..processors.asset_aggregator import AggregatedAssets
from ..adapters.price_adapters.base import PriceData


def calculate_total_assets(
    aggregated_assets: AggregatedAssets,
    prices: PriceData,
) -> int:
    missing_assets = aggregated_assets.assets.keys() - prices.prices.keys()
    if missing_assets:
        raise ValueError(f"Prices missing for assets: {sorted(missing_assets)}")

    invalid_prices = []
    for asset, price in prices.prices.items():
        if price <= 0:
            invalid_prices.append((asset, price))

    if invalid_prices:
        invalid_details = ", ".join(
            f"{addr}: {price}" for addr, price in invalid_prices
        )
        raise ValueError(f"Invalid prices for assets: {invalid_details}")

    return sum(
        aggregated_assets.assets[i] * prices.prices[i] for i in aggregated_assets.assets
    )
