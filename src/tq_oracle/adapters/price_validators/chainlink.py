from __future__ import annotations

from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import CheckResult
from tq_oracle.adapters.price_validators.base import BasePriceValidator

if TYPE_CHECKING:
    from tq_oracle.adapters.price_adapters.base import PriceData
    from tq_oracle.config import OracleCLIConfig


class ChainlinkValidator(BasePriceValidator):
    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)

    @property
    def name(self) -> str:
        return "Chainlink Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        return CheckResult(
            passed=True,
            message="Chainlink validation not implemented",
            retry_recommended=False,
        )
