from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .adapters import ASSET_ADAPTERS, PRICE_ADAPTERS
from .adapters.asset_adapters.base import AssetData
from .checks.pre_checks import run_pre_checks
from .processors import (
    calculate_relative_prices,
    compute_total_assets,
    derive_final_prices,
)
from .report import generate_report, publish_report

if TYPE_CHECKING:
    from .config import OracleCLIConfig


async def execute_oracle_flow(config: OracleCLIConfig) -> None:
    """Execute the complete oracle control flow.

    This implements the flowchart:
    1. Pre-checks (already published? pending vote?)
    2. Fork: Parallel adapter queries
    3. Compute total assets
    4. Calculate relative prices
    5. Derive final prices via OracleHelper
    6. Generate report
    7. Publish (stdout if dry run, Safe if not)

    Args:
        config: CLI configuration containing all parameters
    """
    await run_pre_checks(config, config.vault_address)

    asset_adapters = [AdapterClass(config) for AdapterClass in ASSET_ADAPTERS]

    asset_results = await asyncio.gather(
        *[adapter.fetch_assets(config.vault_address) for adapter in asset_adapters],
        return_exceptions=True,
    )

    price_adapters = [AdapterClass(config) for AdapterClass in PRICE_ADAPTERS]

    asset_data: list[list[AssetData]] = []
    for result in asset_results:
        if isinstance(result, list):
            asset_data.append(result)

    aggregated = await compute_total_assets(asset_data)

    asset_addresses = list(aggregated.assets.keys())

    price_data = []
    for price_adapter in price_adapters:
        prices = await price_adapter.fetch_prices(asset_addresses)
        price_data.extend(prices)

    base_asset = asset_addresses[0] if asset_addresses else ""
    relative_prices = await calculate_relative_prices(
        asset_addresses,
        price_data,
        base_asset,
    )

    final_prices = await derive_final_prices(config, relative_prices)

    report = await generate_report(
        config.vault_address,
        aggregated,
        final_prices,
    )

    await publish_report(config, report)
