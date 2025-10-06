from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import OracleCLIConfig
    from .price_calculator import RelativePrices


@dataclass
class FinalPrices:
    """Final oracle prices derived via OracleHelper contract."""

    prices: dict[str, int]  # asset_address -> final_price (18 decimals)


@dataclass
class EncodedAssetPrices:
    """Encoded asset prices."""

    asset_prices: list[tuple[str, int]]


async def derive_final_prices(
    config: OracleCLIConfig,
    relative_prices: RelativePrices,
) -> FinalPrices:
    """Derive final prices via OracleHelper contract.

    Args:
        config: CLI configuration with RPC endpoints
        relative_prices: Relative prices from price calculator

    Returns:
        Final oracle prices

    This corresponds to the "Derive Final Prices via OracleHelper" step in the flowchart.

    TODO: Implement actual OracleHelper contract interaction
    """

    return FinalPrices(prices=relative_prices.prices)


def encode_asset_prices(relative_prices: RelativePrices) -> EncodedAssetPrices:
    """Encode asset prices for OracleHelper contract."""
    asset_prices = sorted(relative_prices.prices.items(), key=lambda item: item[0])
    return EncodedAssetPrices(asset_prices=asset_prices)
