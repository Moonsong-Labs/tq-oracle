"""CLI entrypoint for the TQ Oracle."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated

import typer
from web3 import Web3

from .constants import (
    BASE_ORACLE_HELPER,
    DEFAULT_BASE_RPC_URL,
    DEFAULT_MAINNET_RPC_URL,
    DEFAULT_SEPOLIA_RPC_URL,
    HL_PROD_EVM_RPC,
    HL_TEST_EVM_RPC,
    MAINNET_ORACLE_HELPER,
    SEPOLIA_ORACLE_HELPER,
)
from .logger import setup_logging
from .settings import CCTPEnv, HyperliquidEnv, Network, OracleSettings
from .state import AppState

NETWORK_RPC_DEFAULTS = {
    Network.MAINNET: DEFAULT_MAINNET_RPC_URL,
    Network.SEPOLIA: DEFAULT_SEPOLIA_RPC_URL,
    Network.BASE: DEFAULT_BASE_RPC_URL,
}

NETWORK_ORACLE_HELPER_DEFAULTS = {
    Network.MAINNET: MAINNET_ORACLE_HELPER,
    Network.SEPOLIA: SEPOLIA_ORACLE_HELPER,
    Network.BASE: BASE_ORACLE_HELPER,
}

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    add_help_option=True,
    pretty_exceptions_enable=True,
    pretty_exceptions_short=True,
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
    help="TVL reporting and Safe submission tool.",
)


def _build_logger() -> logging.Logger:
    """Build a logger instance."""
    return logging.getLogger("tq_oracle")


def _redacted_dump(settings: OracleSettings) -> dict:
    """Return settings as dict with secrets redacted."""
    return settings.as_safe_dict()


@app.callback(invoke_without_command=True)
def report(
    vault_address: Annotated[
        str | None, typer.Argument(help="Vault address to report.")
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="Path to a TOML config file (can include [tq_oracle] table).",
        ),
    ] = None,
    network: Annotated[
        Network | None,
        typer.Option(
            "--network",
            "-n",
            help="Network to use (mainnet, sepolia, or base).",
        ),
    ] = None,
    block_number: Annotated[
        int | None,
        typer.Option(
            "--block-number",
            help="Block number to use for rpc calls. If not provided, the latest block will be used.",
        ),
    ] = None,
    hl_block_number: Annotated[
        int | None,
        typer.Option(
            "--hl-block-number",
            help="Block number to use for hyperliquid rpc calls. If not provided, the latest block will be used.",
        ),
    ] = None,
    hyperliquid_env: Annotated[
        HyperliquidEnv | None,
        typer.Option(
            "--hyperliquid-env",
            help="Hyperliquid environment (mainnet or testnet); overrides env/config.",
        ),
    ] = None,
    cctp_env: Annotated[
        CCTPEnv | None,
        typer.Option(
            "--cctp-env",
            help="CCTP environment (mainnet or testnet); overrides env/config.",
        ),
    ] = None,
    dry_run: Annotated[
        bool | None,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Do not post onchain; overrides env/config.",
        ),
    ] = None,
    show_config: Annotated[
        bool,
        typer.Option(
            "--show-config",
            help="Print effective config (with secrets redacted) and exit.",
        ),
    ] = False,
):
    """Build a TVL report and (optionally) submit to Safe.

    This is the default command that loads configuration, applies network-specific
    defaults, validates settings, and executes the TVL reporting pipeline.
    """
    if config_path:
        os.environ["TQ_ORACLE_CONFIG"] = str(config_path)

    init_kwargs: dict[str, Network | HyperliquidEnv | CCTPEnv | bool | int] = {}
    if network is not None:
        init_kwargs["network"] = network
    if block_number is not None:
        init_kwargs["block_number"] = block_number
    if hl_block_number is not None:
        init_kwargs["hl_block_number"] = hl_block_number
    if hyperliquid_env is not None:
        init_kwargs["hyperliquid_env"] = hyperliquid_env
    if cctp_env is not None:
        init_kwargs["cctp_env"] = cctp_env
    if dry_run is not None:
        init_kwargs["dry_run"] = dry_run

    settings = OracleSettings(**init_kwargs)

    used_default_vault_rpc = False
    if settings.vault_rpc is None:
        settings.vault_rpc = NETWORK_RPC_DEFAULTS[settings.network]
        used_default_vault_rpc = True

    if settings.oracle_helper_address is None:
        settings.oracle_helper_address = NETWORK_ORACLE_HELPER_DEFAULTS[
            settings.network
        ]

    if settings.block_number is None:
        w3 = Web3(Web3.HTTPProvider(settings.vault_rpc_required))
        settings.block_number = w3.eth.block_number

    default_hl_rpc = (
        HL_TEST_EVM_RPC if settings.hyperliquid_env == "testnet" else HL_PROD_EVM_RPC
    )

    used_default_hl_rpc = False
    if settings.hl_rpc is None:
        settings.hl_rpc = default_hl_rpc
        used_default_hl_rpc = True
    else:
        fields_set = getattr(settings, "model_fields_set", set())
        if "hl_rpc" not in fields_set and settings.hl_rpc == default_hl_rpc:
            used_default_hl_rpc = True

    if settings.hl_block_number is None:
        w3 = Web3(Web3.HTTPProvider(settings.hl_rpc_required))
        settings.hl_block_number = w3.eth.block_number

    settings.using_default_rpc = used_default_vault_rpc or used_default_hl_rpc

    setup_logging(settings.log_level)
    logger = _build_logger()
    state = AppState(settings=settings, logger=logger)

    if show_config:
        typer.echo(json.dumps(_redacted_dump(settings), indent=2))
        raise typer.Exit(code=0)

    if vault_address:
        state.settings.vault_address = vault_address

    if not state.settings.vault_address:
        raise typer.BadParameter("vault_address must be configured")
    if not state.settings.vault_rpc:
        raise typer.BadParameter("vault_rpc must be configured")
    if not state.settings.oracle_helper_address:
        raise typer.BadParameter("oracle_helper_address must be configured")
    if not state.settings.hl_rpc:
        raise typer.BadParameter("hl_rpc must be configured")

    if not state.settings.dry_run:
        if not state.settings.safe_address:
            raise typer.BadParameter(
                "safe_address is required when running with --no-dry-run.",
                param_hint=["--safe-address", "TQ_ORACLE_SAFE_ADDRESS"],
            )
        if not state.settings.private_key:
            raise typer.BadParameter(
                "private_key is required when running with --no-dry-run.",
                param_hint=["--private-key", "TQ_ORACLE_PRIVATE_KEY"],
            )

    from .pipeline.run import run_report

    asyncio.run(run_report(state, state.settings.vault_address_required))


def run() -> None:
    """Entrypoint used by the console script."""
    app()


if __name__ == "__main__":
    run()
