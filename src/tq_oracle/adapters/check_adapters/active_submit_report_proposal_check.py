"""Check for active submitReport() proposals in Gnosis Safe."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from eth_typing import URI
from safe_eth.eth import EthereumClient, EthereumNetwork
from safe_eth.safe.api import TransactionServiceApi
from web3 import Web3

from tq_oracle.adapters.check_adapters.base import BaseCheckAdapter, CheckResult

if TYPE_CHECKING:
    from tq_oracle.settings import OracleSettings

logger = logging.getLogger(__name__)

# submitReports() function selector from IOracle.json methodIdentifiers
SUBMIT_REPORTS_SELECTOR = "0x8f88cbfb"


class ActiveSubmitReportProposalCheck(BaseCheckAdapter):
    """Check if there are any active submitReport() proposals being voted on."""

    def __init__(self, config: OracleSettings):
        super().__init__(config)
        self._config = config

    @property
    def name(self) -> str:
        return "Active submitReport() Proposal Check"

    async def run_check(self) -> CheckResult:
        """Check for active submitReport() proposals in the Safe.

        If config.ignore_active_proposal_check is True, this will PASS with a warning
        message instead of FAILING when active proposals are found.

        Returns:
            CheckResult indicating if there are active proposals
        """
        if not self._config.safe_address:
            logger.info("No Safe address configured, skipping active proposal checks")
            return CheckResult(
                passed=True,
                message="No Safe address configured (checks skipped)",
                retry_recommended=False,
            )

        try:
            active_proposals = await self._get_active_submit_report_proposals()

            if active_proposals:
                proposal_count = len(active_proposals)
                logger.warning(
                    f"Found {proposal_count} active submitReport() proposal(s)"
                )

                if self._config.ignore_active_proposal_check:
                    return CheckResult(
                        passed=True,
                        message=f"Found {proposal_count} active submitReport() proposal(s) - WARNING: proceeding anyway due to --ignore-active-proposal-check flag",
                        retry_recommended=False,
                    )
                else:
                    return CheckResult(
                        passed=False,
                        message=f"Found {proposal_count} active submitReport() proposal(s) pending approval",
                        retry_recommended=True,
                    )

            return CheckResult(
                passed=True,
                message="No active submitReport() proposals found",
                retry_recommended=False,
            )

        except Exception as e:
            logger.error(f"Error checking for active proposals: {e}")
            return CheckResult(
                passed=False,
                message=f"Error checking for active proposals: {str(e)}",
                retry_recommended=False,
            )

    async def _get_active_submit_report_proposals(self) -> list[object]:
        """Get active submitReport() proposals from the Safe.

        Returns:
            List of active submitReport() proposals
        """
        network = EthereumNetwork(self._config.chain_id)
        ethereum_client = EthereumClient(URI(self._config.vault_rpc_required))

        api_key = (
            self._config.safe_txn_srvc_api_key.get_secret_value()
            if self._config.safe_txn_srvc_api_key
            else None
        )
        tx_service = TransactionServiceApi(network, ethereum_client, api_key=api_key)

        safe_checksum = Web3.to_checksum_address(self._config.safe_address)

        pending_txs = await asyncio.to_thread(
            tx_service.get_transactions,
            safe_checksum,
            queued=True,  # pyrefly: ignore
            limit=100,  # pyrefly: ignore
        )

        active_submit_report_proposals = []

        for tx in pending_txs:
            if not tx.get("isExecuted", False):
                tx_data = tx.get("data", "")
                if tx_data and tx_data.startswith(SUBMIT_REPORTS_SELECTOR):
                    active_submit_report_proposals.append(tx)

        return active_submit_report_proposals
