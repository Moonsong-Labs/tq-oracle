from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..processors.asset_aggregator import AggregatedAssets
from ..processors.oracle_helper import FinalPrices
from ..adapters.price_adapters.base import PriceData


@dataclass
class OracleReport:
    """Oracle report containing asset data and prices."""

    vault_address: str
    base_asset: str
    tvl_in_base_asset: int
    total_assets: dict[str, int]
    final_prices: dict[str, int]
    adapter_prices: dict[str, str] = field(default_factory=dict)
    total_shares: int = 0

    def to_dict(self) -> dict[str, object]:
        """Convert report to dictionary format."""
        return asdict(self)


async def generate_report(
    vault_address: str,
    base_asset: str,
    tvl_in_base_asset: int,
    aggregated_assets: AggregatedAssets,
    final_prices: FinalPrices,
    price_data: PriceData | None = None,
    total_shares: int = 0,
) -> OracleReport:
    """Generate an oracle report from processed data.

    Args:
        vault_address: The vault contract address
        base_asset: The address of the base asset used for reporting
        tvl_in_base_asset: Total value locked expressed in the base asset (18 decimals)
        aggregated_assets: Aggregated asset balances per asset address
        final_prices: Final oracle prices
        price_data: Raw price data from adapters (for enhanced reporting)
        total_shares: Total shares from the vault's share manager

    Returns:
        Complete oracle report ready for publishing

    This corresponds to the "Generate Report" step in the flowchart.
    """
    adapter_prices: dict[str, str] = {}
    if price_data:
        adapter_prices = {addr: str(price) for addr, price in price_data.prices.items()}

    return OracleReport(
        vault_address=vault_address,
        base_asset=base_asset,
        tvl_in_base_asset=tvl_in_base_asset,
        total_assets=aggregated_assets.assets,
        final_prices=final_prices.prices,
        adapter_prices=adapter_prices,
        total_shares=total_shares,
    )
