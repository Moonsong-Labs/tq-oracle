from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_validators.base import BasePriceValidator

if TYPE_CHECKING:
    from tq_oracle.adapters.price_adapters.base import PriceData
    from tq_oracle.config import OracleCLIConfig

logger = logging.getLogger(__name__)


class PositivePricesValidator(BasePriceValidator):
    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "Positive Prices Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        invalid_prices = []

        for asset_address, price in price_data.prices.items():
            if price <= 0:
                invalid_prices.append((asset_address, price))
                logger.error(f"Invalid price for {asset_address}: {price}")

        if invalid_prices:
            invalid_details = ", ".join(
                f"{addr}: {price}" for addr, price in invalid_prices
            )
            return CheckResult(
                passed=False,
                message=f"Found {len(invalid_prices)} asset(s) with non-positive prices: {invalid_details}",
                retry_recommended=False,
            )

        return CheckResult(
            passed=True,
            message=f"All {len(price_data.prices)} prices are positive",
            retry_recommended=False,
        )
