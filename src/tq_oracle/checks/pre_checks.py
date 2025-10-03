from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import OracleCLIConfig


class PreCheckError(Exception):
    """Raised when a pre-check fails and execution should stop."""

    pass


async def check_already_published(
    config: OracleCLIConfig,
    vault_address: str,
) -> bool:
    """Check if a report has already been published for this vault.

    Args:
        config: CLI configuration with RPC endpoints
        vault_address: The vault contract address

    Returns:
        True if already published, False otherwise

    This corresponds to the "Already published?" decision in the flowchart.

    TODO: Implement actual contract state check
    """
    return False


async def check_pending_vote(
    config: OracleCLIConfig,
    vault_address: str,
) -> bool:
    """Check if a report is already pending vote for this vault.

    Args:
        config: CLI configuration with RPC endpoints
        vault_address: The vault contract address

    Returns:
        True if report is pending, False otherwise

    This corresponds to the "Report already being voted on?" decision in the flowchart.

    TODO: Implement actual voting state check
    """
    return False


async def run_pre_checks(
    config: OracleCLIConfig,
    vault_address: str,
) -> None:
    """Run all pre-checks before proceeding with oracle flow.

    Args:
        config: CLI configuration
        vault_address: The vault contract address

    Raises:
        PreCheckError: If any pre-check fails

    This encapsulates the pre-check logic from the flowchart:
    - Already published? -> STOP
    - Report already being voted on? -> STOP
    """
    if await check_already_published(config, vault_address):
        raise PreCheckError(
            f"Report already published for vault {vault_address}. Exiting."
        )

    if await check_pending_vote(config, vault_address):
        raise PreCheckError(
            f"Report already pending vote for vault {vault_address}. Exiting."
        )
