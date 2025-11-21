from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tq_oracle.checks.price_validators import PriceValidationError
from tq_oracle.pipeline.pricing import price_assets
from tq_oracle.pipeline.context import PipelineContext
from tq_oracle.state import AppState
from tq_oracle.settings import OracleSettings
from tq_oracle.processors import AggregatedAssets, FinalPrices


class StubAdapter:
    """Minimal price adapter that sets a fixed price for each asset."""

    def __init__(self, config):
        self.config = config

    async def fetch_prices(self, asset_addresses, prices_accumulator):
        for addr in asset_addresses:
            prices_accumulator.prices[addr] = 10**18  # 1 base unit
        return prices_accumulator


@pytest.fixture
def config():
    return OracleSettings(
        vault_address="0xVAULT",
        oracle_helper_address="0xORACLE_HELPER",
        vault_rpc="https://eth.example",
        price_validation_retries=1,
        price_validation_timeout=0.0,
    )


def make_ctx(config: OracleSettings) -> PipelineContext:
    logger = MagicMock()
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    state = AppState(settings=config, logger=logger)
    ctx = PipelineContext(state=state, vault_address="0xVAULT")
    ctx.base_asset = "0xBASE"
    ctx.aggregated = AggregatedAssets(assets={"0xASSET": 100})
    return ctx


@pytest.mark.asyncio
@patch("tq_oracle.pipeline.pricing.PRICE_ADAPTERS", [StubAdapter])
@patch(
    "tq_oracle.pipeline.pricing.derive_final_prices",
    AsyncMock(return_value=FinalPrices(prices={})),
)
async def test_no_retry_when_not_recommended(config):
    ctx = make_ctx(config)
    call_count = {"n": 0}

    async def failing_validation(*_args, **_kwargs):
        call_count["n"] += 1
        raise PriceValidationError("fail once", retry_recommended=False)

    with patch(
        "tq_oracle.pipeline.pricing.run_price_validations", new=failing_validation
    ):
        with pytest.raises(PriceValidationError):
            await price_assets(ctx)

    assert call_count["n"] == 1


@pytest.mark.asyncio
@patch("tq_oracle.pipeline.pricing.PRICE_ADAPTERS", [StubAdapter])
@patch(
    "tq_oracle.pipeline.pricing.derive_final_prices",
    AsyncMock(return_value=FinalPrices(prices={})),
)
async def test_retry_and_eventual_success(config):
    ctx = make_ctx(config)
    call_count = {"n": 0}

    async def flaky_validation(*_args, **_kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise PriceValidationError("transient", retry_recommended=True)
        return None

    with patch(
        "tq_oracle.pipeline.pricing.run_price_validations", new=flaky_validation
    ):
        await price_assets(ctx)

    assert call_count["n"] == 2  # retried once (retries=1)


@pytest.mark.asyncio
@patch("tq_oracle.pipeline.pricing.PRICE_ADAPTERS", [StubAdapter])
@patch(
    "tq_oracle.pipeline.pricing.derive_final_prices",
    AsyncMock(return_value=FinalPrices(prices={})),
)
async def test_retry_exhaustion_failure(config):
    ctx = make_ctx(config)
    call_count = {"n": 0}

    async def always_fails(*_args, **_kwargs):
        call_count["n"] += 1
        raise PriceValidationError("always bad", retry_recommended=True)

    with patch("tq_oracle.pipeline.pricing.run_price_validations", new=always_fails):
        with pytest.raises(PriceValidationError):
            await price_assets(ctx)

    # retries=1 ⇒ total attempts = 2
    assert call_count["n"] == 2
