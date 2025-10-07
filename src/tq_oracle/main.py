from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

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
            envvar="L1_RPC_URL",
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
            envvar="HL_RPC_URL",
            help="hyperliquid RPC endpoint (optional).",
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

    if l1_rpc is None:
        l1_rpc = DEFAULT_SEPOLIA_RPC_URL if testnet else DEFAULT_MAINNET_RPC_URL

    if oracle_helper_address is None:
        oracle_helper_address = (
            SEPOLIA_ORACLE_HELPER if testnet else MAINNET_ORACLE_HELPER
        )

    config = OracleCLIConfig(
        vault_address=vault_address,
        oracle_helper_address=oracle_helper_address,
        l1_rpc=l1_rpc,
        safe_address=safe_address,
        hl_rpc=hl_rpc,
        hl_subvault_address=hl_subvault_address,
        testnet=testnet,
        dry_run=dry_run,
        private_key=private_key,
        safe_txn_srvc_api_key=safe_txn_srvc_api_key,
        ignore_empty_vault=ignore_empty_vault,
    )

    asyncio.run(execute_oracle_flow(config))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
