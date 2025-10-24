"""Price fetching and validation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..adapters import PRICE_ADAPTERS
from ..adapters.price_adapters.base import PriceData
from ..checks.price_validators import PriceValidationError, run_price_validations
from ..constants import ETH_ASSET
from ..processors import calculate_total_assets, derive_final_prices, FinalPrices

if TYPE_CHECKING:
    from ..processors import AggregatedAssets
    from ..state import AppState


async def price_assets(
    state: AppState, aggregated: AggregatedAssets
) -> tuple[PriceData, int, FinalPrices]:
    """Fetch prices for assets and validate them.

    Args:
        state: Application state containing settings and logger
        aggregated: Aggregated assets to price

    Returns:
        Tuple of (price_data, total_assets, final_prices)

    Raises:
        PriceValidationError: If price validation fails
    """
    s = state.settings
    log = state.logger

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
    total_assets = calculate_total_assets(aggregated, price_data)
    log.debug("Total assets in base asset: %d", total_assets)

    log.info("Deriving final prices via OracleHelper...")
    final_prices = await derive_final_prices(s, total_assets, price_data)

    return price_data, total_assets, final_prices
