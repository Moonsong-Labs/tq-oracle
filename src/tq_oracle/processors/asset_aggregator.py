from __future__ import annotations

from dataclasses import dataclass

from ..adapters.asset_adapters.base import AssetData


@dataclass
class AggregatedAssets:
    """Aggregated asset data from multiple protocols."""

    assets: dict[str, int]  # asset_address -> total_amount


async def compute_total_aggregated_assets(
    protocol_assets: list[list[AssetData]],
) -> AggregatedAssets:
    """Compute total assets by aggregating data from multiple protocols.

    Args:
        protocol_assets: List of asset data lists from each protocol adapter

    Returns:
        Aggregated assets with totals per asset address

    This corresponds to the "Compute Total Assets" step in the flowchart.
    """
    aggregated: dict[str, int] = {}

    for adapter_assets in protocol_assets:
        for asset in adapter_assets:
            current = aggregated.get(asset.asset_address, 0)
            aggregated[asset.asset_address] = current + asset.amount

    return AggregatedAssets(assets=aggregated)
