"""Price fetching and validation."""

from __future__ import annotations

from ..adapters import PRICE_ADAPTERS
from ..adapters.price_adapters.base import PriceData
from ..checks.price_validators import PriceValidationError, run_price_validations
from ..constants import ETH_ASSET
from ..processors import (
    calculate_total_assets,
    derive_final_prices,
)
from .context import PipelineContext


async def price_assets(ctx: PipelineContext) -> None:
    """Fetch prices for assets and validate them.

    Args:
        ctx: Pipeline context containing state and aggregated assets

    Sets the price data, total assets, and final prices in the context.

    Raises:
        PriceValidationError: If price validation fails
        RuntimeError: If aggregated assets are not set
    """
    s = ctx.state.settings
    log = ctx.state.logger
    aggregated = ctx.aggregated
    if aggregated is None:
        raise RuntimeError("Aggregated assets are not set")

    asset_addresses = list(aggregated.assets)

    log.info("Fetching prices for %d assets...", len(asset_addresses))
    price_data: PriceData = PriceData(base_asset=ETH_ASSET, prices={})

    price_adapters = [AdapterClass(s) for AdapterClass in PRICE_ADAPTERS]
    for price_adapter in price_adapters:
        price_data = await price_adapter.fetch_prices(asset_addresses, price_data)
        log.debug("Price adapter returned %d prices", len(price_data.prices))

    log.info("Running price validations...")
    try:
        await run_price_validations(s, price_data)
        log.info("Price validations passed successfully")
    except PriceValidationError as e:
        log.error("Price validations failed: %s", e)
        raise

    log.info("Calculating total assets in base asset...")
    log.debug(f"Assets found: {aggregated}")
    log.debug(f"Price data: {price_data}")
    total_assets = calculate_total_assets(aggregated, price_data)
    log.debug("Total assets in base asset: %d", total_assets)

    log.info("Deriving final prices via OracleHelper...")
    final_prices = await derive_final_prices(s, total_assets, price_data)

    ctx.price_data = price_data
    ctx.total_assets = total_assets
    ctx.final_prices = final_prices
