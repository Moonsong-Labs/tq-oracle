from __future__ import annotations

from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_validators.base import BasePriceValidator
from tq_oracle.adapters.price_adapters.chainlink import ChainlinkAdapter

if TYPE_CHECKING:
    from tq_oracle.adapters.price_adapters.base import PriceData
    from tq_oracle.config import OracleCLIConfig


class ChainlinkValidator(BasePriceValidator):
    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self.chainlink_adapter = ChainlinkAdapter(config)

    @property
    def name(self) -> str:
        return "Chainlink Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        asset_addresses = list(price_data.prices.keys())
        chainlink_prices = PriceData(base_asset=price_data.base_asset, prices={})
        chainlink_prices = await self.chainlink_adapter.fetch_prices(
            asset_addresses, chainlink_prices
        )

        for asset_address, chainlink_price in chainlink_prices.prices.items():
            asset_price = price_data.prices[asset_address]
            delta_percentage = self._calculate_price_deviation_percentage(
                chainlink_price, asset_price
            )
            if delta_percentage > 1:
                return CheckResult(
                    passed=False,
                    message=f"Chainlink price for {asset_address} is {delta_percentage:.2f}% off from the actual price",
                    retry_recommended=False,
                )

        return CheckResult(
            passed=True,
            message="All prices are within acceptable deviation from Chainlink",
            retry_recommended=False,
        )

    def _calculate_price_deviation_percentage(
        self, reference_price: int, actual_price: int
    ) -> float:
        """Calculate the percentage deviation between two prices.

        Args:
            reference_price: The reference price (e.g., from Chainlink)
            actual_price: The actual price being validated

        Returns:
            Absolute percentage deviation between the prices

        Raises:
            ValueError: If actual_price is zero
        """
        if actual_price == 0:
            raise ValueError("actual_price cannot be zero")

        return abs((reference_price - actual_price) / actual_price * 100)
