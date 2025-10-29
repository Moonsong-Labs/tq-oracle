from __future__ import annotations

import logging

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_validators.base import BasePriceValidator
from tq_oracle.adapters.price_adapters.chainlink import ChainlinkAdapter

from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.settings import OracleSettings

logger = logging.getLogger(__name__)


class ChainlinkValidator(BasePriceValidator):
    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.chainlink_adapter = ChainlinkAdapter(config)
        self.warning_tolerance = config.price_warning_tolerance_percentage
        self.failure_tolerance = config.price_failure_tolerance_percentage

    @property
    def name(self) -> str:
        return "Chainlink Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        logger.debug(
            f" Starting validation with price_data.prices keys: {list(price_data.prices.keys())}"
        )
        asset_addresses = list(price_data.prices.keys())
        logger.debug(f" Asset addresses to validate: {asset_addresses}")
        chainlink_prices = PriceData(base_asset=price_data.base_asset, prices={})
        chainlink_prices = await self.chainlink_adapter.fetch_prices(
            asset_addresses, chainlink_prices
        )
        logger.debug(f" Fetched prices for {len(chainlink_prices.prices)} assets")
        logger.debug(f" Chainlink price keys: {list(chainlink_prices.prices.keys())}")

        for asset_address, chainlink_price in chainlink_prices.prices.items():
            logger.debug(f" Processing asset {asset_address}")
            asset_price = price_data.prices[asset_address]
            logger.debug(
                f" {asset_address}: Chainlink price={chainlink_price}, Oracle price={asset_price}"
            )
            delta_percentage = self._calculate_price_deviation_percentage(
                chainlink_price, asset_price
            )
            logger.debug(f" {asset_address}: Deviation = {delta_percentage:.2f}%")

            if delta_percentage > self.failure_tolerance:
                return CheckResult(
                    passed=False,
                    message=f"Chainlink price for {asset_address} is {delta_percentage:.2f}% off from the actual price (failure threshold: {self.failure_tolerance}%)",
                    retry_recommended=False,
                )

            if delta_percentage > self.warning_tolerance:
                logger.warning(
                    f"Chainlink price for {asset_address} is {delta_percentage:.2f}% off from the actual price (warning threshold: {self.warning_tolerance}%)"
                )

        return CheckResult(
            passed=True,
            message="All prices are within acceptable deviation from Chainlink",
            retry_recommended=False,
        )
