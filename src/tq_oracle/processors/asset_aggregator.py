from __future__ import annotations

from dataclasses import dataclass, field

from web3 import Web3

from ..adapters.asset_adapters.base import AssetData


@dataclass
class AggregatedAssets:
    """Aggregated asset data from multiple protocols."""

    assets: dict[str, int]  # asset_address -> total_amount
    tvl_only_assets: set[str] = field(default_factory=set)


async def compute_total_aggregated_assets(
    protocol_assets: list[list[AssetData]],
) -> AggregatedAssets:
    """Compute total assets by aggregating data from multiple protocols.

    Args:
        protocol_assets: List of asset data lists from each protocol adapter

    Returns:
        Aggregated assets with totals per asset address

    This corresponds to the "Compute Total Assets" step in the flowchart.

    Note: All asset addresses are normalized to EIP-55 checksummed format to ensure
    consistent aggregation regardless of how different adapters format addresses.
    """
    aggregated: dict[str, int] = {}
    tvl_only_assets: set[str] = set()
    non_tvl_only_assets: set[str] = set()

    for adapter_assets in protocol_assets:
        for asset in adapter_assets:
            checksummed_address = Web3.to_checksum_address(asset.asset_address)
            current = aggregated.get(checksummed_address, 0)
            aggregated[checksummed_address] = current + asset.amount
            if getattr(asset, "tvl_only", False):
                tvl_only_assets.add(checksummed_address)
            else:
                non_tvl_only_assets.add(checksummed_address)
    if tvl_only_assets & non_tvl_only_assets:
        raise ValueError(
            f"Assets with conflicting tvl_only flags: {tvl_only_assets & non_tvl_only_assets}"
        )
    return AggregatedAssets(assets=aggregated, tvl_only_assets=tvl_only_assets)
