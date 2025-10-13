from __future__ import annotations

from ..processors.asset_aggregator import AggregatedAssets
from ..adapters.price_adapters.base import PriceData


def calculate_total_assets(
    aggregated_assets: AggregatedAssets,
    prices: PriceData,
) -> int:
    """Calculate total assets in base asset terms.
    missing_assets = aggregated_assets.assets.keys() - prices.prices.keys()
    if missing_assets:
        raise ValueError(f"Prices missing for assets: {sorted(missing_assets)}")

    Args:
        aggregated_assets: Aggregated asset amounts by address
        prices: Price data with base asset and relative prices

    Returns:
        Total value in base asset terms

    Note:
        The base asset doesn't need to be in prices.prices as it has an
        implicit 1:1 ratio (price of 10**18 in 18-decimal representation).
    """
    # Validate that all non-base assets have prices
    missing_prices = [
        asset
        for asset in aggregated_assets.assets
        if asset != prices.base_asset and asset not in prices.prices
    ]
    if missing_prices:
        raise ValueError(f"Missing prices for assets: {missing_prices}")

    # Calculate total, treating base asset as having price of 10**18
    total = 0
    for asset_address, amount in aggregated_assets.assets.items():
        if asset_address == prices.base_asset:
            # Base asset has implied price of 10**18 (1:1 ratio in 18 decimals)
            price = 10**18
        else:
            price = prices.prices[asset_address]

        total += amount * price

    return total
