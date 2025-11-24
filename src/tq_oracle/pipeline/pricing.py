"""Price fetching and validation."""

from __future__ import annotations

from typing import Any

import backoff

from ..adapters import PRICE_ADAPTERS
from ..adapters.price_adapters.base import PriceData
from ..checks.price_validators import PriceValidationError, run_price_validations
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
    """
    s = ctx.state.settings
    log = ctx.state.logger
    aggregated = ctx.aggregated_required

    asset_addresses = list(aggregated.assets)
    log.info("Fetching prices for %d assets...", len(asset_addresses))
    price_data: PriceData = PriceData(
        base_asset=ctx.base_asset_required,
        prices={},
        decimals={ctx.base_asset_required: 18},
    )

    price_adapters = [AdapterClass(s) for AdapterClass in PRICE_ADAPTERS]
    for price_adapter in price_adapters:
        price_data = await price_adapter.fetch_prices(asset_addresses, price_data)
        log.debug("Price adapter returned %d prices", len(price_data.prices))

    log.info(
        "Running price validations (max retries: %d, timeout: %.1fs)...",
        s.price_validation_retries,
        s.price_validation_timeout,
    )

    def _should_giveup(exc: Exception) -> bool:
        return isinstance(exc, PriceValidationError) and not exc.retry_recommended

    def _on_backoff(details: Any) -> None:
        log.warning(
            "Price validation failed (attempt %d of %d): %s",
            details["tries"],
            s.price_validation_retries + 1,
            details.get("exception", details.get("value")),
        )

    def _on_giveup(details: Any) -> None:
        exc = details.get("exception", details.get("value"))
        if isinstance(exc, PriceValidationError) and not exc.retry_recommended:
            log.error("Price validation failed (retry not recommended): %s", exc)
        else:
            log.error(
                "Price validations failed after %d attempts: %s",
                details["tries"],
                exc,
            )

    @backoff.on_exception(
        backoff.constant,
        PriceValidationError,
        max_tries=s.price_validation_retries + 1,
        interval=s.price_validation_timeout,
        giveup=_should_giveup,
        on_backoff=_on_backoff,
        on_giveup=_on_giveup,
    )
    async def _run_price_validations_with_retry() -> None:
        await run_price_validations(s, price_data)

    await _run_price_validations_with_retry()
    log.info("Price validations passed successfully")

    log.info("Calculating total assets in base asset...")
    log.debug(f"Assets found: {aggregated}")
    log.debug(f"Price data: {price_data}")
    total_assets = calculate_total_assets(aggregated, price_data)
    log.debug("Total assets in base asset: %d", total_assets)

    log.info("Deriving final prices via OracleHelper...")
    excluded_for_oracle = getattr(aggregated, "tvl_only_assets", set())
    final_prices = await derive_final_prices(
        s,
        total_assets,
        price_data,
        excluded_assets=excluded_for_oracle,
    )

    ctx.price_data = price_data
    ctx.total_assets = total_assets
    ctx.final_prices = final_prices
