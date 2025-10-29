from __future__ import annotations

import logging

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_adapters.base import PriceData
from tq_oracle.adapters.price_adapters.pyth import PythAdapter
from tq_oracle.adapters.price_validators.base import BasePriceValidator
from tq_oracle.settings import OracleSettings

logger = logging.getLogger(__name__)


class PythValidator(BasePriceValidator):
    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self.pyth_adapter = PythAdapter(config)
        self.warning_tolerance = config.price_warning_tolerance_percentage
        self.failure_tolerance = config.price_failure_tolerance_percentage

    @property
    def name(self) -> str:
        return "Pyth Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        if not self.config.pyth_enabled:
            return CheckResult(
                passed=True,
                message="Pyth validation is disabled",
                retry_recommended=False,
            )

        logger.debug(
            f" Starting validation with price_data.prices keys: {list(price_data.prices.keys())}"
        )

        asset_addresses = [
            addr for addr in price_data.prices.keys() if addr != price_data.base_asset
        ]
        logger.debug(
            f" Asset addresses to validate (excluding base asset): {asset_addresses}"
        )

        pyth_prices = PriceData(base_asset=price_data.base_asset, prices={})

        try:
            pyth_prices = await self.pyth_adapter.fetch_prices(
                asset_addresses, pyth_prices
            )
        except Exception as e:
            logger.error(f"Pyth API error: {e}")
            return CheckResult(
                passed=False, message=f"Pyth API error: {e}", retry_recommended=True
            )

        logger.debug(f" Fetched prices for {len(pyth_prices.prices)} assets")
        logger.debug(f" Pyth price keys: {list(pyth_prices.prices.keys())}")

        for asset_address, pyth_price in pyth_prices.prices.items():
            logger.debug(f" Processing asset {asset_address}")
            oracle_price = price_data.prices[asset_address]
            logger.debug(
                f" {asset_address}: Pyth price={pyth_price}, Oracle price={oracle_price}"
            )

            deviation_pct = self._calculate_price_deviation_percentage(
                pyth_price, oracle_price
            )
            logger.debug(f" {asset_address}: Deviation = {deviation_pct:.2f}%")

            if deviation_pct > self.failure_tolerance:
                return CheckResult(
                    passed=False,
                    message=f"Pyth price for {asset_address} is {deviation_pct:.2f}% off from oracle price (failure threshold: {self.failure_tolerance}%)",
                    retry_recommended=False,
                )

            if deviation_pct > self.warning_tolerance:
                logger.warning(
                    f"Pyth price for {asset_address} is {deviation_pct:.2f}% off from oracle price (warning threshold: {self.warning_tolerance}%)"
                )

        return CheckResult(
            passed=True,
            message="All prices are within acceptable deviation from Pyth",
            retry_recommended=False,
        )
