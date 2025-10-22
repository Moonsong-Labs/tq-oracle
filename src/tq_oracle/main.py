from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from tq_oracle.constants import HL_PROD_EVM_RPC, HL_TEST_EVM_RPC

from .config import OracleCLIConfig
from .constants import (
    DEFAULT_MAINNET_RPC_URL,
    DEFAULT_SEPOLIA_RPC_URL,
    MAINNET_ORACLE_HELPER,
    SEPOLIA_ORACLE_HELPER,
)
from .logger import setup_logging
from .orchestrator import execute_oracle_flow

setup_logging()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
    help="Collect TVL data from vault protocols using modular adapters.",
)


@app.command("report")
def report(
    vault_address: Annotated[
        str,
        typer.Argument(
            help="Vault contract address to query.",
        ),
    ],
    oracle_helper_address: Annotated[
        Optional[str],
        typer.Option(
            "--oracle-helper-address",
            "-h",
            help="OracleHelper contract address to query (defaults to mainnet/testnet based on --testnet flag).",
        ),
    ] = None,
    l1_rpc: Annotated[
        Optional[str],
        typer.Option(
            "--l1-rpc",
            envvar="L1_RPC",
            help="Ethereum L1 RPC endpoint (defaults to mainnet/testnet based on --testnet flag).",
        ),
    ] = None,
    safe_address: Annotated[
        Optional[str],
        typer.Option(
            "--safe-address",
            "-s",
            help="Gnosis Safe address for multi-sig submission (optional).",
        ),
    ] = None,
    hl_rpc: Annotated[
        Optional[str],
        typer.Option(
            "--hl-rpc",
            envvar="HL_EVM_RPC",
            help="hyperliquid RPC endpoint (optional).",
        ),
    ] = None,
    l1_subvault_address: Annotated[
        Optional[str],
        typer.Option(
            "--l1-subvault-address",
            envvar="L1_SUBVAULT_ADDRESS",
            help="L1 subvault address for CCTP bridge monitoring (optional).",
        ),
    ] = None,
    hl_subvault_address: Annotated[
        Optional[str],
        typer.Option(
            "--hl-subvault-address",
            envvar="HL_SUBVAULT_ADDRESS",
            help="Hyperliquid subvault address to query (optional, defaults to vault address).",
        ),
    ] = None,
    testnet: Annotated[
        bool,
        typer.Option(
            "--testnet/--no-testnet",
            help="Use testnet instead of mainnet.",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Preview actions without sending a transaction.",
        ),
    ] = True,
    private_key: Annotated[
        Optional[str],
        typer.Option(
            "--private-key",
            envvar="PRIVATE_KEY",
            help="Private key for signing transactions",
        ),
    ] = None,
    safe_txn_srvc_api_key: Annotated[
        Optional[str],
        typer.Option(
            "--safe-key",
            envvar="SAFE_TRANSACTION_SERVICE_API_KEY",
            help="API key for the Safe Transaction Service (optional, but recommended).",
        ),
    ] = None,
    ignore_empty_vault: Annotated[
        bool,
        typer.Option(
            "--ignore-empty-vault/--no-ignore-empty-vault",
            help="Suppress errors when vault has no assets or OracleHelper doesn't recognize assets (useful for testing pre-deployment).",
        ),
    ] = False,
    ignore_timeout_check: Annotated[
        bool,
        typer.Option(
            "--ignore-timeout-check/--no-ignore-timeout-check",
            help="Warn but don't block when timeout hasn't elapsed since last report (allows forced submission).",
        ),
    ] = False,
    ignore_active_proposal_check: Annotated[
        bool,
        typer.Option(
            "--ignore-active-proposal-check/--no-ignore-active-proposal-check",
            help="Warn but don't block when there are active submitReports() proposals in the Safe (allows duplicate submission).",
        ),
    ] = False,
    pre_check_retries: Annotated[
        int,
        typer.Option(
            "--pre-check-retries",
            help="Number of times to retry pre-checks if they fail (default: 3).",
        ),
    ] = 3,
    pre_check_timeout: Annotated[
        float,
        typer.Option(
            "--pre-check-timeout",
            help="Timeout in seconds between pre-check retries (default: 12.0).",
        ),
    ] = 12.0,
    chainlink_price_warning_tolerance_percentage: Annotated[
        float,
        typer.Option(
            "--chainlink-warning-tolerance",
            help="Chainlink price deviation percentage to trigger warning (default: 0.5).",
        ),
    ] = 0.5,
    chainlink_price_failure_tolerance_percentage: Annotated[
        float,
        typer.Option(
            "--chainlink-failure-tolerance",
            help="Chainlink price deviation percentage to fail validation (default: 1.0).",
        ),
    ] = 1.0,
) -> None:
    """Collect TVL data and submit via Safe (optional)."""
    if not dry_run and not safe_address and not private_key:
        raise typer.BadParameter(
            "Either --safe-address OR --private-key required when running with --no-dry-run.",
            param_hint=["--safe-address", "--private-key"],
        )

    if safe_address and not dry_run and not private_key:
        raise typer.BadParameter(
            "--private-key required when using --safe-address with --no-dry-run.",
            param_hint=["--private-key"],
        )

    using_default_rpc = l1_rpc is None or hl_rpc is None

    if l1_rpc is None:
        l1_rpc = DEFAULT_SEPOLIA_RPC_URL if testnet else DEFAULT_MAINNET_RPC_URL

    if oracle_helper_address is None:
        oracle_helper_address = (
            SEPOLIA_ORACLE_HELPER if testnet else MAINNET_ORACLE_HELPER
        )

    if hl_rpc is None:
        hl_rpc = HL_PROD_EVM_RPC if not testnet else HL_TEST_EVM_RPC

    config = OracleCLIConfig(
        vault_address=vault_address,
        oracle_helper_address=oracle_helper_address,
        l1_rpc=l1_rpc,
        l1_subvault_address=l1_subvault_address,
        safe_address=safe_address,
        hl_rpc=hl_rpc,
        hl_subvault_address=hl_subvault_address,
        using_default_rpc=using_default_rpc,
        testnet=testnet,
        dry_run=dry_run,
        private_key=private_key,
        safe_txn_srvc_api_key=safe_txn_srvc_api_key,
        ignore_empty_vault=ignore_empty_vault,
        ignore_timeout_check=ignore_timeout_check,
        ignore_active_proposal_check=ignore_active_proposal_check,
        pre_check_retries=pre_check_retries,
        pre_check_timeout=pre_check_timeout,
        chainlink_price_warning_tolerance_percentage=chainlink_price_warning_tolerance_percentage,
        chainlink_price_failure_tolerance_percentage=chainlink_price_failure_tolerance_percentage,
    )

    asyncio.run(execute_oracle_flow(config))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
