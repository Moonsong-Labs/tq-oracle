from __future__ import annotations

from dataclasses import asdict, dataclass

from ..processors.asset_aggregator import AggregatedAssets
from ..processors.oracle_helper import FinalPrices


@dataclass
class OracleReport:
    """Oracle report containing asset data and prices."""

    vault_address: str
    total_assets: dict[str, int]
    final_prices: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        """Convert report to dictionary format."""
        return asdict(self)


async def generate_report(
    vault_address: str,
    aggregated_assets: AggregatedAssets,
    final_prices: FinalPrices,
) -> OracleReport:
    """Generate an oracle report from processed data.

    Args:
        vault_address: The vault contract address
        aggregated_assets: Aggregated asset data
        final_prices: Final oracle prices

    Returns:
        Complete oracle report ready for publishing

    This corresponds to the "Generate Report" step in the flowchart.
    """
    return OracleReport(
        vault_address=vault_address,
        total_assets=aggregated_assets.assets,
        final_prices=final_prices.prices,
    )
