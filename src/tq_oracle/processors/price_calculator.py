from __future__ import annotations

from dataclasses import dataclass

from ..adapters.price_adapters.base import PriceData


@dataclass
class RelativePrices:
    """Relative prices for assets against a base asset."""

    base_asset: str
    prices: dict[str, int]  # asset_address -> relative_price (18 decimals)


async def calculate_relative_prices(
    asset_addresses: list[str],
    price_data: list[PriceData],
    base_asset: str,
) -> RelativePrices:
    """Calculate relative prices for non-base assets.

    Args:
        asset_addresses: List of asset addresses to price
        price_data: Price data from Chainlink
        base_asset: The base asset address to price against

    Returns:
        Relative prices for all assets against the base asset

    This corresponds to the "Calculate Relative Prices for Non-Base Assets" step in the flowchart.
    """
    price_map = {p.asset_address: p.price_usd for p in price_data}
    base_price = price_map.get(base_asset, 10**18)  # default to 1.0

    relative_prices: dict[str, int] = {}
    for asset in asset_addresses:
        if asset == base_asset:
            relative_prices[asset] = 10**18  # 1.0
        else:
            asset_price = price_map.get(asset, 0)
            if base_price > 0:
                # Calculate relative price: (asset_price / base_price) * 10^18
                relative_prices[asset] = (asset_price * 10**18) // base_price
            else:
                relative_prices[asset] = 0

    return RelativePrices(base_asset=base_asset, prices=relative_prices)
