from __future__ import annotations

from typing import TYPE_CHECKING

from tq_oracle.adapters.check_adapters.base import BaseCheckAdapter, CheckResult

if TYPE_CHECKING:
    from tq_oracle.config import OracleCLIConfig


class ChainLinkLastLookAdapter(BaseCheckAdapter):
    def __init__(self, config: OracleCLIConfig):
        super().__init__(config)
        self._config = config

    @property
    def name(self) -> str:
        return "Chainlink Last Look Check"

    async def run_check(self) -> CheckResult:
        return CheckResult(
            passed=True,
            message="Chainlink last look check not implemented",
            retry_recommended=False,
        )
