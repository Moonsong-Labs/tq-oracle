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
    oracle_helper_address: Annotated[
        str,
        typer.Option(
            "--oracle-helper-address",
            "-o",
            help="OracleHelper contract address to query.",
        ),
    ],
    destination: Annotated[
        str,
        typer.Option(
            "--destination",
            "-d",
            help="Destination EOA that should receive the transaction.",
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
            help="Private key for signing (required when --no-dry-run).",
        ),
    ] = None,
) -> None:
    """Collect TVL data for the requested vault."""
    if not dry_run and not private_key:
        raise typer.BadParameter(
            "Provide --private-key when running with --no-dry-run.",
            param_hint=["--private-key"],
        )

    config = OracleCLIConfig(
        vault_address=vault_address,
        oracle_helper_address=oracle_helper_address,
        destination=destination,
        mainnet_rpc=mainnet_rpc,
        hl_rpc=hl_rpc,
        testnet=testnet,
        dry_run=dry_run,
        backoff=backoff,
        private_key=private_key,
    )

    asyncio.run(execute_oracle_flow(config))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
