from __future__ import annotations

from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import CheckResult

if TYPE_CHECKING:
    from tq_oracle.adapters.price_adapters.base import PriceData
    from tq_oracle.config import OracleCLIConfig


class ChainLinkLastLookValidator:
    def __init__(self, config: OracleCLIConfig):
        self._config = config

    @property
    def name(self) -> str:
        return "Chainlink Last Look Validator"

    async def validate_prices(self, price_data: PriceData) -> CheckResult:
        return CheckResult(
            passed=True,
            message="Chainlink last look validation not implemented",
            retry_recommended=False,
        )
