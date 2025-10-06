from __future__ import annotations

import asyncio
from typing import Annotated, Optional

import typer

from .config import OracleCLIConfig
from .logger import setup_logging
from .orchestrator import execute_oracle_flow

DEFAULT_MAINNET_RPC_URL = "https://eth.drpc.org"

setup_logging()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Collect TVL data from vault protocols using modular adapters.",
)


@app.command("report")
def report(
    vault_address: Annotated[
        str,
        typer.Option(
            "--vault-address",
            "-v",
            help="Vault contract address to query.",
        ),
    ],
    oracle_address: Annotated[
        str,
        typer.Option(
            "--oracle-address",
            "-o",
            help="IOracle contract address to call submitReports on.",
        ),
    ],
    mainnet_rpc: Annotated[
        str,
        typer.Option(
            "--mainnet-rpc",
            envvar="MAINNET_RPC_URL",
            show_default=True,
            help="Ethereum mainnet RPC endpoint.",
        ),
    ] = DEFAULT_MAINNET_RPC_URL,
    safe_address: Annotated[
        Optional[str],
        typer.Option(
            "--safe-address",
            "-s",
            help="Gnosis Safe address for multi-sig submission (optional).",
        ),
    ] = None,
    chain_id: Annotated[
        int,
        typer.Option(
            "--chain-id",
            "-c",
            help="Network chain ID (1=mainnet, 11155111=sepolia).",
        ),
    ] = 1,
    hl_rpc: Annotated[
        Optional[str],
        typer.Option(
            "--hl-rpc",
            envvar="HL_RPC_URL",
            help="hyperliquid RPC endpoint (optional).",
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
    backoff: Annotated[
        bool,
        typer.Option(
            "--backoff/--no-backoff",
            help="Enable exponential backoff retry logic.",
        ),
    ] = True,
    private_key: Annotated[
        Optional[str],
        typer.Option(
            "--private-key",
            envvar="PRIVATE_KEY",
            help="Private key for signing (required for direct submission).",
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

    resolved_chain_id = chain_id
    if testnet and chain_id == 1:
        resolved_chain_id = 11155111  # Sepolia

    config = OracleCLIConfig(
        vault_address=vault_address,
        oracle_address=oracle_address,
        mainnet_rpc=mainnet_rpc,
        safe_address=safe_address,
        chain_id=resolved_chain_id,
        hl_rpc=hl_rpc,
        testnet=testnet,
        dry_run=dry_run,
        backoff=backoff,
        private_key=private_key,
        safe_txn_srvc_api_key=safe_txn_srvc_api_key,
    )

    asyncio.run(execute_oracle_flow(config))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
