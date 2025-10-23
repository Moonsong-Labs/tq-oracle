"""Gnosis Safe state validation check adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from tq_oracle.adapters.check_adapters.base import BaseCheckAdapter, CheckResult

if TYPE_CHECKING:
    from tq_oracle.config import OracleCLIConfig

logger = logging.getLogger(__name__)


class SafeStateAdapter(BaseCheckAdapter):
    """Validates Gnosis Safe state before publishing oracle data."""

    @property
    def name(self) -> str:
        return "Gnosis Safe State Validation"

    async def run_check(self) -> CheckResult:
        """Check Safe state (already published, pending vote).

        Skips checks if no Safe address is configured.

        Returns:
            CheckResult indicating if Safe state allows publishing
        """
        config = cast("OracleCLIConfig", self.config)

        # Skip checks if no Safe address configured
        if not config.safe_address:
            logger.info("No Safe address configured, skipping Safe state checks")
            return CheckResult(
                passed=True,
                message="No Safe address configured (checks skipped)",
                retry_recommended=False,
            )

        try:
            vault_address = config.vault_address_required
            if await self._check_already_published(config, vault_address):
                return CheckResult(
                    passed=False,
                    message=f"Report already published for vault {vault_address}",
                    retry_recommended=False,
                )

            if await self._check_pending_vote(config, vault_address):
                return CheckResult(
                    passed=False,
                    message=f"Report already pending vote for vault {vault_address}",
                    retry_recommended=False,
                )

            return CheckResult(
                passed=True,
                message="Safe state validation passed",
                retry_recommended=False,
            )

        except Exception as e:
            logger.error(f"Error checking Safe state: {e}")
            return CheckResult(
                passed=False,
                message=f"Error checking Safe state: {str(e)}",
                retry_recommended=False,
            )

    async def _check_already_published(
        self,
        config: OracleCLIConfig,
        vault_address: str,
    ) -> bool:
        """Check if a report has already been published for this vault.

        Args:
            config: CLI configuration with RPC endpoints and Safe address
            vault_address: The vault contract address

        Returns:
            True if already published, False otherwise

        TODO: Implement actual Safe contract state check via Gnosis Safe API
        """
        # TODO: Query Gnosis Safe transaction service API or contract state
        # to check if a report has already been published for this vault
        return False

    async def _check_pending_vote(
        self,
        config: OracleCLIConfig,
        vault_address: str,
    ) -> bool:
        """Check if a report is already pending vote for this vault.

        Args:
            config: CLI configuration with RPC endpoints and Safe address
            vault_address: The vault contract address

        Returns:
            True if report is pending, False otherwise

        TODO: Implement actual Safe voting state check via Gnosis Safe API
        """
        # TODO: Query Gnosis Safe transaction service API or contract state
        # to check if there's a pending transaction for this vault
        return False
