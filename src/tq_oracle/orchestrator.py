from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .constants import ETH_ASSET
from .adapters.price_adapters.base import PriceData
from .adapters import ASSET_ADAPTERS, PRICE_ADAPTERS
from .adapters.asset_adapters.base import AssetData
from .checks.pre_checks import PreCheckError, run_pre_checks
from .logger import get_logger
from .processors import (
    compute_total_aggregated_assets,
    derive_final_prices,
    calculate_total_assets,
)

from .report import generate_report, publish_report

if TYPE_CHECKING:
    from .config import OracleCLIConfig

logger = get_logger(__name__)


async def execute_oracle_flow(config: OracleCLIConfig) -> None:
    """Execute the complete oracle control flow.

    This implements the flowchart:
    1. Pre-checks (Safe validations + adapter checks)
    2. Fork: Parallel adapter queries
    3. Compute total assets
    4. Calculate relative prices
    5. Derive final prices via OracleHelper
    6. Generate report
    7. Publish (stdout if dry run, Safe if not)

    Args:
        config: CLI configuration containing all parameters
    """
    logger.info("Starting oracle flow for vault: %s", config.vault_address)
    logger.debug("Configuration: %s", config.as_safe_dict())

    logger.info(
        "Running pre-checks (max retries: %d, timeout: %.1fs)...",
        config.pre_check_retries,
        config.pre_check_timeout,
    )

    retry_count = 0

    while retry_count <= config.pre_check_retries:
        try:
            if retry_count > 0:
                logger.info(
                    "Pre-check retry attempt %d of %d...",
                    retry_count,
                    config.pre_check_retries,
                )

            await run_pre_checks(config, config.vault_address)
            logger.info("Pre-checks passed successfully")
            break

        except PreCheckError as e:
            if not e.retry_recommended:
                logger.error("Pre-check failed (retry not recommended): %s", e)
                raise

            retry_count += 1

            if retry_count > config.pre_check_retries:
                logger.error(
                    "Pre-checks failed after %d attempts: %s",
                    config.pre_check_retries + 1,
                    e,
                )
                raise

            logger.warning(
                "Pre-check failed (attempt %d of %d): %s",
                retry_count,
                config.pre_check_retries + 1,
                e,
            )
            logger.info(
                "Waiting %.1f seconds before retry...",
                config.pre_check_timeout,
            )
            await asyncio.sleep(config.pre_check_timeout)

    logger.info("Initializing %d asset adapters", len(ASSET_ADAPTERS))
    asset_adapters = [AdapterClass(config) for AdapterClass in ASSET_ADAPTERS]

    logger.info("Fetching assets from %d adapters in parallel...", len(asset_adapters))
    asset_results = await asyncio.gather(
        *[adapter.fetch_assets(config.vault_address) for adapter in asset_adapters],
        return_exceptions=True,
    )

    price_adapters = [AdapterClass(config) for AdapterClass in PRICE_ADAPTERS]

    asset_data: list[list[AssetData]] = []
    for adapter, result in zip(asset_adapters, asset_results):
        if isinstance(result, Exception):
            logger.error("Asset adapter '%s' failed: %s", adapter.adapter_name, result)
        elif isinstance(result, list):
            logger.debug(
                "Asset adapter '%s' returned %d assets",
                adapter.adapter_name,
                len(result),
            )
            asset_data.append(result)

    logger.info("Computing agreggated assets...")
    aggregated = await compute_total_aggregated_assets(asset_data)
    logger.debug("Total aggregated assets: %d", len(aggregated.assets))

    asset_addresses = list(aggregated.assets.keys())

    logger.info("Fetching prices for %d assets...", len(asset_addresses))
    price_data: PriceData = PriceData(base_asset=ETH_ASSET, prices={})
    for price_adapter in price_adapters:
        price_data = await price_adapter.fetch_prices(asset_addresses, price_data)
        logger.debug("Price adapter returned %d prices", len(price_data.prices))

    logger.info("Calculating total assets in base asset...")
    total_assets = calculate_total_assets(aggregated, price_data)
    logger.debug("Total assets in base asset: %d", total_assets)

    logger.info("Deriving final prices via OracleHelper...")
    final_prices = await derive_final_prices(config, total_assets, price_data)

    logger.info("Generating report...")
    report = await generate_report(
        config.vault_address,
        aggregated,
        final_prices,
    )

    logger.info("Publishing report (dry_run=%s)...", config.dry_run)
    await publish_report(config, report)
    logger.info("Oracle flow completed successfully")
